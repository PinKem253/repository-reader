"""
agent.py — Vòng lặp Agent Loop thật (ReAct: Reasoning -> Action -> Observation).

B1 (Harness) + B2 (Agent Loop) + B3 (sinh câu trả lời cuối) gộp chung ở đây,
tối giản nhất có thể — mục tiêu duy nhất của bước này: chứng minh MODEL tự
quyết định có gọi tool hay không, thay vì code cố định gọi search_semantic
1 lần như app.py cũ (Giai đoạn 1/2).
"""

import logging
import json
from datetime import datetime, timezone
from pathlib import Path

from google import genai
from google.genai import types

from repository_reader import tools
from repository_reader.config import settings

import time
from google.genai import errors as genai_errors

logger = logging.getLogger(__name__)

# File JSONL ghi lại "số vòng thực tế đã dùng" mỗi lần run() kết thúc — mục
# đích DUY NHẤT: tích lũy dữ liệu THẬT để sau này tính percentile (vd p95)
# làm cơ sở chỉnh MAX_TURNS dựa trên bằng chứng, thay vì đặt cảm tính như
# hiện tại (đã thảo luận: mẫu quá nhỏ nên chưa tính percentile được, phải
# gom dữ liệu trước).
#
# Đây KHÔNG phải B5 (Log & Persist) đầy đủ trong roadmap Track 4 — B5 lưu
# vào Postgres cho nhiều mục đích (audit trail, phân tích hội thoại...). Ở
# đây chỉ ghi tối thiểu ra 1 file JSONL cục bộ, đủ dùng cho mục đích thống
# kê MAX_TURNS trước mắt, không kéo theo migration DB.
#
# Path tương đối "logs/" giống hệt cách CLONE_BASE_DIR trong ingest.py đang
# làm — giả định process chạy từ project root (đúng với cách uvicorn đang
# được khởi động hiện tại).
_RUN_LOG_PATH = Path("logs") / "agent_runs.jsonl"


def _log_run_stats(question: str, repo_id: int, round_num: int, exhausted_budget: bool) -> None:
    """Ghi 1 dòng JSON thống kê cho 1 lần run() -- xem giải thích ở _RUN_LOG_PATH."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repo_id": repo_id,
        "question": question,
        "round_num": round_num,
        "exhausted_budget": exhausted_budget,
    }
    try:
        _RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_RUN_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        # Ghi log thống kê là nice-to-have, KHÔNG được phép làm sập request
        # thật -- lỗi ở đây (vd disk đầy, quyền ghi) chỉ log cảnh báo rồi bỏ
        # qua, không raise.
        logger.warning("Không ghi được _RUN_LOG_PATH (bỏ qua, không chặn response)", exc_info=True)

# 1 client dùng chung cho cả module — cùng pattern với vector_store.py/
# generation.py: khởi tạo 1 lần lúc import, không tạo lại mỗi lần gọi run().
client = genai.Client(api_key=settings.llm_api_key)

MODEL_NAME = "gemini-3.5-flash-lite"

# "Session budget" (B4 trong roadmap): giới hạn số vòng lặp tối đa. Không có
# giới hạn này, nếu model kẹt gọi sai tool liên tục sẽ lặp vô hạn — vừa treo
# request vừa tốn tiền API thật mỗi lần gọi model.
MAX_TURNS = 10


MAX_RETRIES = 10
BASE_DELAY_SECONDS = 2  # 2s, 4s, 8s cho 3 lần thử

# Harness tối thiểu (B1) — instructions cố định, không đổi theo từng câu hỏi.
#
# 3 đoạn thêm sau, mỗi đoạn sinh từ 1 bug hành vi thật đã gặp khi test:
# (1) multi-part: model từng trả lời phần dễ, lờ hẳn phần khó của câu hỏi
#     nhiều-phần mà không báo gì.
# (2) file lớn/JSON: model từng kết luận vội chỉ dựa trên 100 dòng đầu của
#     merged_framework.ipynb (toàn metadata, chưa phải code thật).
# (3) chống lặp search_semantic: sau khi thêm (1)+(2), model kiên trì hơn
#     nhưng "kiên trì sai cách" -- lặp lại search_semantic với query khác
#     thay vì đọc thẳng file .ipynb đã biết tên, tốn hết MAX_TURNS mà chưa
#     từng chạm tới file đó.
SYSTEM_INSTRUCTIONS = (
    "Bạn là trợ lý trả lời câu hỏi về 1 GitHub repository cụ thể. "
    "Bạn CHỈ được biết thông tin về repo này qua các tool được cung cấp — "
    "không được tự bịa nội dung code/docs không có trong observation trả về. "
    "Khi trả lời cuối cùng, LUÔN trích dẫn nguồn dạng [file:start-end] lấy từ "
    "observation. Nếu sau khi thử tool vẫn không tìm thấy thông tin liên quan, "
    "hãy nói rõ là không tìm thấy, không được đoán.\n\n"
    "Nếu câu hỏi có NHIỀU PHẦN (vd 'A và B là gì'), phải trả lời TỪNG PHẦN "
    "riêng biệt — không được chỉ trả lời phần dễ rồi bỏ qua phần khó. Với "
    "phần nào chưa đủ observation để trả lời, phải nói rõ 'chưa tìm thấy "
    "thông tin về phần này' thay vì lờ đi, không nhắc tới.\n\n"
    "Với file lớn hoặc có cấu trúc (vd .ipynb là định dạng JSON): nếu đoạn "
    "đầu đọc được (thường chỉ là metadata/markdown cell mở đầu) chưa trả lời "
    "được câu hỏi, PHẢI đọc tiếp bằng read_file với start_line lớn hơn, hoặc "
    "dùng search_exact để định vị đúng đoạn liên quan — không được kết luận "
    "chỉ dựa trên 100 dòng đầu tiên của 1 file dài.\n\n"
    "KHÔNG được gọi search_semantic 2 lần liên tiếp với các query khác nhau "
    "cho cùng 1 mục đích tìm kiếm — nếu lần gọi đầu đã ra kết quả (dù score "
    "thấp), đó là tín hiệu semantic search KHÔNG giúp được gì thêm cho câu "
    "hỏi này. Thay vào đó, dùng list_repo_structure (nếu chưa gọi) để biết "
    "tên file cụ thể, rồi đọc THẲNG file nghi ngờ nhất bằng read_file, hoặc "
    "dùng search_exact với từ khóa cụ thể (vd 'config', 'def ', "
    "'argparse', 'parser.add_argument') thay vì tìm kiếm ngữ nghĩa lần nữa.\n\n"
    "QUY TẮC RIÊNG cho định dạng trích dẫn [file:start-end]: phần 'file' "
    "BẮT BUỘC là 1 đường dẫn file THẬT trong repo (lấy nguyên từ citation "
    "trong observation của search_semantic/search_exact/read_file) — TUYỆT "
    "ĐỐI KHÔNG được dùng TÊN TOOL (vd 'list_repo_structure', "
    "'search_semantic') làm 'file'. Output của list_repo_structure là cây "
    "thư mục, KHÔNG PHẢI 1 file thật nên KHÔNG có gì để trích dẫn theo "
    "dòng — khi trả lời dựa trên list_repo_structure (vd mô tả tổng quan "
    "cấu trúc), chỉ mô tả bằng lời, KHÔNG bịa ra 1 citation [file:start-"
    "end] giả cho phần đó."
)

# Instruction CHỈ dùng cho lượt "ép trả lời cuối" (xem run(), nhánh hết
# MAX_TURNS) — sinh từ 1 rủi ro phát hiện khi thiết kế cơ chế graceful
# fallback: nếu chỉ đơn giản ép model "trả lời ngay đi", nó có thể bắt đầu
# đoán để lấp chỗ trống, PHÁ VỠ đúng quy tắc "không tìm thấy thì nói không
# tìm thấy" đã dày công dạy ở SYSTEM_INSTRUCTIONS. Đoạn này nhắc lại ràng
# buộc đó riêng cho tình huống model bị dồn vào chân tường.
FORCED_FINAL_INSTRUCTION = (
    "Đây là lượt cuối cùng — hệ thống đã tắt toàn bộ tool, bạn không thể gọi "
    "thêm search_semantic/search_exact/read_file/list_repo_structure nữa. "
    "Dựa DUY NHẤT vào những observation đã có ở các lượt trước, tổng hợp "
    "câu trả lời tốt nhất có thể ngay bây giờ. Với phần nào của câu hỏi CHƯA "
    "có đủ observation để trả lời, PHẢI nói rõ 'chưa tìm thấy thông tin về "
    "phần này' — TUYỆT ĐỐI không được đoán hay bịa thêm chỉ vì đây là lượt "
    "cuối và bạn đang bị buộc phải nói gì đó."
)

# Convert list dict trong tools.py sang đúng type SDK google-genai cần.
# types.Tool tự nhận list dict và convert thành FunctionDeclaration bên trong.
_TOOL_CONFIG = types.Tool(function_declarations=tools.ALL_TOOL_DECLARATIONS)
_GENERATE_CONFIG = types.GenerateContentConfig(
    system_instruction=SYSTEM_INSTRUCTIONS,
    tools=[_TOOL_CONFIG],
)

# Config riêng cho lượt "ép trả lời cuối": KHÔNG khai báo tools ở đây.
# Đây là chặn CỨNG ở tầng API (Gemini không có function nào để gọi, dù model
# có muốn cũng không được), mạnh hơn hẳn so với việc chỉ "dặn" nó qua prompt
# — tương tự lý do repo_id không cho model tự chọn mà hệ thống áp đặt cứng.
_FINAL_ANSWER_CONFIG = types.GenerateContentConfig(
    system_instruction=SYSTEM_INSTRUCTIONS,
)


def _generate_with_retry(**kwargs):
    """
    Bọc client.models.generate_content() với retry + exponential backoff.

    ServerError (5xx, vd 503 UNAVAILABLE) = lỗi TẠM THỜI phía Google, không
    phải bug của mình -- đáng thử lại.

    ClientError 429 (RESOURCE_EXHAUSTED -- hết quota/rate limit) LÀ 1 NGOẠI
    LỆ trong nhóm 4xx: đã kiểm tra trực tiếp mã nguồn google.genai.errors,
    mọi status_code 400-499 đều bị raise thành ClientError, kể cả 429 -- tức
    là TRƯỚC ĐÂY (bug) code này coi 429 giống hệt 400/401/403 (raise ngay,
    không retry), dù về bản chất 429 là tín hiệu "chậm lại rồi thử lại",
    đúng nghĩa nên retry+backoff giống ServerError. Các ClientError 4xx KHÁC
    (400 sai request, 401 sai key, 403 không có quyền...) vẫn raise ngay --
    đó mới là bug thật, retry không giúp gì, chỉ giấu lỗi.

    LƯU Ý: nếu 429 này là do QUOTA THEO NGÀY đã hết (không phải rate limit
    theo phút), backoff ở đây (tối đa cộng dồn ~34 phút qua đủ MAX_RETRIES
    lần) sẽ KHÔNG giúp gì -- vẫn raise sau khi hết lượt thử. Đọc
    e.message/e.details của lỗi để biết chính xác đang chạm giới hạn nào
    (per-minute hay per-day) trước khi kết luận retry có ý nghĩa hay không.
    """
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            return client.models.generate_content(**kwargs)
        except genai_errors.ServerError as e:
            last_error = e
            delay = BASE_DELAY_SECONDS * (2 ** attempt)
            logger.warning(
                f"Gemini lỗi server (lần {attempt + 1}/{MAX_RETRIES}): {e}. "
                f"Thử lại sau {delay}s..."
            )
            time.sleep(delay)
        except genai_errors.ClientError as e:
            if e.code == 429:
                last_error = e
                delay = BASE_DELAY_SECONDS * (2 ** attempt)
                logger.warning(
                    f"Gemini hết quota/rate limit (429, lần {attempt + 1}/"
                    f"{MAX_RETRIES}): {e}. Thử lại sau {delay}s..."
                )
                time.sleep(delay)
            else:
                # 4xx khác (400/401/403...) = bug thật -- raise ngay như cũ.
                raise
    raise last_error


def run(question: str, repo_id: int) -> dict:
    """
    Chạy vòng lặp ReAct cho 1 câu hỏi, trả về dict:
        {"answer": str, "exhausted_budget": bool}

    "exhausted_budget" = True nghĩa là model KHÔNG tự kết thúc sớm (không có
    lượt nào nó chủ động dừng gọi tool) — câu trả lời trong "answer" là kết
    quả của 1 lượt ÉP trả lời riêng sau khi đã dùng hết MAX_TURNS, không
    phải model tự nguyện trả lời. Đây là METADATA đi kèm, tách khỏi nội dung
    text — để nơi gọi (app.py -> UI, hoặc log debug) tự quyết định cách hiển
    thị, thay vì nhét lời cảnh báo vào ngay trong "answer".

    repo_id truyền từ ngoài vào, không nằm trong quyền model tự chọn — cùng
    lý do đã giải thích ở execute_tool(): đây là Scope hệ thống áp đặt.
    """
    # "contents" vừa là State (B1) vừa là lịch sử ReAct của riêng lần chạy
    # này — mỗi lượt Reasoning/Action/Observation được append vào đây để
    # model "nhớ" đã làm gì, vì mỗi lần generate_content() là stateless,
    # không tự giữ ngữ cảnh giữa các lần gọi.
    contents = [
        types.Content(role="user", parts=[types.Part.from_text(text=question)])
    ]

    for turn in range(MAX_TURNS):
        round_num = turn + 1  # hiển thị 1-indexed (R1, R2...) cho dễ đọc log --
                              # biến `turn` nội bộ vẫn 0-indexed vì range() tự nhiên vậy

        response = _generate_with_retry(
            model=MODEL_NAME,
            contents=contents,
            config=_GENERATE_CONFIG,
        )

        candidate = response.candidates[0]
        part = candidate.content.parts[0]

        # --- Reasoning: model chọn hành động (gọi tool hay trả lời luôn) ---
        if part.function_call is not None:
            fn_name = part.function_call.name
            fn_args = dict(part.function_call.args)

            # Lưu lượt "model quyết định gọi tool" vào lịch sử — bắt buộc,
            # thiếu bước này model sẽ quên đã gọi tool gì ở vòng kế tiếp.
            contents.append(candidate.content)

            # --- Action: thực thi tool thật ---
            observation = tools.execute_tool(fn_name, fn_args, repo_id=repo_id)

            # Cắt ngắn observation khi LOG (không cắt bản đưa cho model) --
            # tránh tràn màn hình terminal khi observation dài (vd cả 1 file).
            observation_preview = observation[:300] + ("..." if len(observation) > 300 else "")

            logger.info(
                f"\n========== R{round_num} ==========\n"
                f"Tool gọi   : {fn_name}\n"
                f"Args       : {fn_args}\n"
                f"Observation: {observation_preview}"
            )

            # --- Observation: đưa kết quả ngược lại cho model đọc ---
            # Gemini API chưa có role "tool" riêng — quy ước là bọc kết quả
            # qua Part.from_function_response() rồi gửi dưới role "user"
            # (đại diện "đây là dữ liệu hệ thống cấp tiếp", không phải người
            # dùng gõ thật).
            function_response_part = types.Part.from_function_response(
                name=fn_name,
                response={"result": observation},
            )
            contents.append(
                types.Content(role="user", parts=[function_response_part])
            )
            continue  # quay lại đầu loop để model Reasoning tiếp

        # --- Không gọi tool nữa -> đây là câu trả lời cuối cùng, model TỰ dừng ---
        logger.info(
            f"\n========== R{round_num} (FINAL) ==========\n"
            f"Model dừng gọi tool, trả lời trực tiếp.\n"
            f"Answer: {response.text[:300]}"
        )
        _log_run_stats(question, repo_id, round_num, exhausted_budget=False)
        return {"answer": response.text, "exhausted_budget": False}

    # --- Hết MAX_TURNS mà model vẫn chưa tự dừng: ép 1 lượt trả lời cuối ---
    # Trước đây (bug cũ): trả thẳng 1 câu tiếng Việt cứng "Xin lỗi, không thể
    # tạo câu trả lời..." -- bỏ phí toàn bộ observation đã thu thập được qua
    # N vòng trước đó, dù model có thể đã đủ dữ kiện để trả lời 1 phần.
    #
    # Cách mới: gọi lại model 1 lần nữa với NGUYÊN lịch sử "contents" đã có
    # (không mất context), nhưng dùng _FINAL_ANSWER_CONFIG (không có tools)
    # để chặn cứng khả năng gọi tool tiếp -- buộc model phải trả lời bằng
    # text ngay, đồng thời thêm FORCED_FINAL_INSTRUCTION để nhắc nó không
    # được đoán bừa chỉ vì bị dồn vào chân tường.
    logger.warning(
        f"\n========== HẾT {MAX_TURNS} VÒNG, ÉP MODEL TRẢ LỜI LƯỢT CUỐI ==========\n"
        f"Câu hỏi: {question}"
    )
    contents.append(
        types.Content(
            role="user", parts=[types.Part.from_text(text=FORCED_FINAL_INSTRUCTION)]
        )
    )
    final_response = _generate_with_retry(
        model=MODEL_NAME,
        contents=contents,
        config=_FINAL_ANSWER_CONFIG,
    )

    # Banner cảnh báo NỔI BẬT riêng cho developer đọc log terminal -- phân
    # biệt rõ với block "R{n} (FINAL)" bình thường ở trên, để không nhầm
    # đây là model tự nguyện kết thúc sớm.
    logger.warning(
        "\n"
        "########################################################\n"
        "# CẢNH BÁO: câu trả lời dưới đây được ÉP SINH sau khi hết\n"
        f"# {MAX_TURNS} vòng loop -- KHÔNG PHẢI model tự kết thúc sớm.\n"
        "# Độ tin cậy có thể thấp hơn bình thường, xem lại trace ở trên.\n"
        "########################################################\n"
        f"Câu hỏi: {question}\n"
        f"Answer : {final_response.text[:300]}"
    )
    _log_run_stats(question, repo_id, MAX_TURNS, exhausted_budget=True)
    return {"answer": final_response.text, "exhausted_budget": True}


if __name__ == "__main__":
    # Test độc lập, chưa cần app.py: repo_id=9 (Spoon-Knife, đã ingest sẵn
    # từ Giai đoạn 2) + 1 câu hỏi buộc model phải tự gọi search_semantic.

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    # Xem giải thích ở app.py -- ép các logger ồn ào của thư viện bên thứ 3
    # lên WARNING để terminal chỉ còn log R1/R2/... của riêng agent.py.
    for _noisy_logger in ("httpx", "httpcore", "urllib3", "huggingface_hub", "FlagEmbedding"):
        logging.getLogger(_noisy_logger).setLevel(logging.WARNING)

    result = run("What is this repository about?", repo_id=13)
    print(result["answer"])
    if result["exhausted_budget"]:
        print("[DEBUG] Câu trả lời trên bị ép sinh sau khi hết MAX_TURNS.")
