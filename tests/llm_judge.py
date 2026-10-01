"""
tests/llm_judge.py — LLM-as-judge cho eval set của agent.py (Track 4 mục 4).

KHÔNG dùng để so khớp câu trả lời với 1 đáp án mẫu (không tồn tại đáp án mẫu
duy nhất cho câu hỏi tự do) -- dùng để CHẤM câu trả lời theo 1 RUBRIC (danh
sách tiêu chí cụ thể, xem field "rubric" trong eval_questions.py), tương tự
cách 1 người review chấm theo checklist thay vì so chữ với 1 bài mẫu.

Quyết định thiết kế quan trọng: judge CHỈ làm phần "so khớp ngôn ngữ tự
nhiên" (từng tiêu chí thoả mãn hay không, kèm giải thích) -- phần TỔNG HỢP
pass/fail cuối cùng (AND của mọi tiêu chí) được TÍNH BẰNG CODE PYTHON
THƯỜNG trong judge_answer(), KHÔNG giao cho LLM tự cộng. Lý do: "so khớp 1
câu với 1 tiêu chí" là việc LLM làm tốt (đọc hiểu ngôn ngữ tự nhiên), nhưng
"N tiêu chí này AND lại ra true/false" là logic rời rạc đơn giản -- để code
tính sẽ xác định 100%, không phụ thuộc model có cộng đúng hay không. Đây là
áp dụng lại đúng nguyên tắc đã dùng ở citation_file_exists() trong ui.py:
chỉ dùng LLM cho việc THỰC SỰ cần LLM.
"""

from typing import List

from pydantic import BaseModel
from google.genai import types

# Tái dùng CHUNG 1 client + helper retry+backoff đã có sẵn trong agent.py --
# logic retry cho 429 (rate limit)/5xx đã được viết và test kỹ ở đó (xem
# _generate_with_retry trong agent.py), không viết lại 1 bản khác cho judge
# để tránh trùng lặp + lệch nhau giữa 2 nơi theo thời gian.
from repository_reader.agent import client, _generate_with_retry  # noqa: F401 (client giữ để rõ nguồn)


# Model đóng vai "giám khảo" -- tạm dùng CHUNG model với agent (rẻ, nhất
# quán với phần còn lại của project). Đổi hằng số này sang 1 model khác (vd
# mạnh hơn agent) nếu sau này thấy judge chấm không đủ tin cậy -- không cần
# sửa gì khác trong file này.
JUDGE_MODEL_NAME = "gemini-3.5-flash-lite"

JUDGE_SYSTEM_INSTRUCTIONS = (
    "Bạn là giám khảo chấm câu trả lời của 1 AI assistant khác (bạn KHÔNG "
    "tự trả lời câu hỏi). Bạn sẽ nhận 1 câu hỏi, 1 câu trả lời (answer) của "
    "assistant đó, và 1 danh sách tiêu chí (rubric). Với MỖI tiêu chí trong "
    "rubric, xác định answer có thoả mãn tiêu chí đó hay không (satisfied: "
    "true/false) và giải thích ngắn gọn tại sao (reason).\n\n"
    "Chỉ dựa DUY NHẤT vào nội dung answer được cung cấp -- không tự đoán "
    "thêm, không cộng điểm cho ý 'nghe có vẻ đúng' nếu answer không nói rõ, "
    "và không bị ảnh hưởng bởi việc answer viết dài/tự tin hay ngắn/khiêm "
    "tốn. Trả về ĐÚNG 1 kết quả cho MỖI tiêu chí trong rubric, theo đúng "
    "thứ tự đã cho, không bỏ sót, không thêm tiêu chí mới."
)


class CriterionResult(BaseModel):
    criterion: str
    satisfied: bool
    reason: str


class JudgeOutput(BaseModel):
    criteria_results: List[CriterionResult]


def _build_judge_prompt(question: str, answer: str, rubric: List[str]) -> str:
    rubric_lines = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(rubric))
    return (
        f"Câu hỏi gốc:\n{question}\n\n"
        f"Câu trả lời cần chấm (answer):\n{answer}\n\n"
        f"Rubric (danh sách tiêu chí cần chấm):\n{rubric_lines}"
    )


def judge_answer(question: str, answer: str, rubric: List[str]) -> dict:
    """
    Chấm 1 answer theo rubric bằng LLM-as-judge, trả về:
        {
            "overall_pass": bool,        # tính bằng code = AND mọi satisfied
            "criteria_results": [        # chi tiết từng tiêu chí, để debug
                {"criterion": str, "satisfied": bool, "reason": str}, ...
            ],
        }
    """
    prompt = _build_judge_prompt(question, answer, rubric)

    # response_schema=JudgeOutput: ép Gemini trả ĐÚNG JSON theo shape của
    # JudgeOutput (SDK google-genai tự validate + parse, response.parsed
    # trả về instance JudgeOutput thật, không phải string JSON thô phải tự
    # json.loads()) -- cùng ý tưởng JSON Schema đã học ở B2/tool-calling,
    # nhưng áp dụng cho OUTPUT thay vì khai báo tool.
    response = _generate_with_retry(
        model=JUDGE_MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=JUDGE_SYSTEM_INSTRUCTIONS,
            response_mime_type="application/json",
            response_schema=JudgeOutput,
        ),
    )

    parsed: JudgeOutput = response.parsed
    criteria_results = [c.model_dump() for c in parsed.criteria_results]
    overall_pass = all(c["satisfied"] for c in criteria_results)

    return {"overall_pass": overall_pass, "criteria_results": criteria_results}


if __name__ == "__main__":
    pass
