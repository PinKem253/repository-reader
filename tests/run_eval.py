"""
run_eval.py — Chạy bộ câu hỏi cố định (eval_questions.py) qua agent.run(),
in kết quả ra để ĐỌC BẰNG MẮT. KHÔNG có assertion tự động — câu trả lời LLM
không có 1 đáp án cố định để so khớp, xem giải thích ở eval_questions.py.

2 mục đích:
1) Hồi quy thủ công mỗi khi sửa SYSTEM_INSTRUCTIONS trong agent.py — chạy lại
   nguyên bộ câu hỏi này để xem có phá vỡ hành vi đã đúng ở câu khác không,
   thay vì chỉ re-test đúng 1 câu vừa sửa (cách đã làm thủ công 3 lần trước
   đây).
2) Mỗi lần chạy cũng tự động đổ thêm dữ liệu round_num thật vào
   logs/agent_runs.jsonl (agent.run() đã tự ghi mỗi lần gọi) -- tăng tốc gom
   mẫu để sau này tính percentile (p95) làm cơ sở chỉnh MAX_TURNS.

Cách chạy (từ project root, sau khi đã ingest ít nhất 1 repo):
    python tests/run_eval.py --repo-id 13

--repo-id PHẢI trỏ tới 1 repo ĐÃ ingest thật (xem GET /repos để lấy id).
Muốn nhóm "multi_part"/"large_file" có ý nghĩa (đủ nội dung để hợp lệ cần
nhiều turns thật, không chỉ do bug), nên trỏ vào 1 repo Python có kích thước
vừa -- không phải Spoon-Knife gần như rỗng.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

# Cho phép chạy trực tiếp "python tests/run_eval.py" từ project root mà
# không cần tests/ là 1 package (không cần __init__.py) -- thêm thư mục
# chứa file này vào sys.path để import được eval_questions.py cùng cấp.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_questions import EVAL_QUESTIONS  # noqa: E402

from repository_reader import agent  # noqa: E402

# Cùng path với _RUN_LOG_PATH trong agent.py -- đọc lại dòng cuối để lấy
# round_num thực tế của lần run() vừa gọi (agent.run() chỉ trả về
# {"answer", "exhausted_budget"}, không trả round_num trực tiếp).
_RUN_LOG_PATH = Path("logs") / "agent_runs.jsonl"


def _read_last_round_num() -> Optional[int]:
    if not _RUN_LOG_PATH.exists():
        return None
    with open(_RUN_LOG_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    if not lines:
        return None
    return json.loads(lines[-1]).get("round_num")


def main() -> None:
    parser = argparse.ArgumentParser(description="Chạy bộ câu hỏi eval qua agent.run()")
    parser.add_argument(
        "--repo-id", type=int, required=True, help="repo_id đã ingest thật (xem GET /repos)"
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=5.0,
        help=(
            "Số giây nghỉ giữa các câu hỏi -- giảm rủi ro chạm rate limit "
            "(429) khi bắn liên tục 8 câu, mỗi câu có thể tốn nhiều lượt "
            "gọi API bên trong. KHÔNG giúp gì nếu quota đã hết THEO NGÀY, "
            "chỉ giúp khi giới hạn là theo PHÚT."
        ),
    )
    args = parser.parse_args()

    print(f"Chạy {len(EVAL_QUESTIONS)} câu hỏi eval trên repo_id={args.repo_id}\n")

    for i, item in enumerate(EVAL_QUESTIONS):
        print("=" * 70)
        print(f"[{item['category']}] {item['id']}")
        print(f"Câu hỏi : {item['question']}")
        print(f"Kỳ vọng : {item['notes']}")

        try:
            result = agent.run(item["question"], args.repo_id)
        except Exception as e:
            # agent.py đã tự retry 429 (rate limit) với backoff -- nếu vẫn
            # raise tới đây nghĩa là đã hết lượt thử, thường do QUOTA THEO
            # NGÀY (không phải rate limit theo phút) -- chạy tiếp các câu
            # còn lại chỉ tốn thêm thời gian retry vô ích, nên DỪNG hẳn thay
            # vì lặp qua từng câu.
            print(f"\n[DỪNG] Câu '{item['id']}' lỗi: {e}")
            print(
                "Nếu đây là lỗi hết quota/rate limit (RESOURCE_EXHAUSTED, "
                "429): cần đợi quota reset (thường theo ngày) hoặc dùng "
                "key/tier khác, rồi chạy lại phần câu hỏi còn thiếu."
            )
            break

        round_num = _read_last_round_num()

        print(f"round_num thực tế : {round_num}")
        print(f"exhausted_budget  : {result['exhausted_budget']}")
        print(f"Answer:\n{result['answer']}\n")

        if i < len(EVAL_QUESTIONS) - 1:
            time.sleep(args.pause_seconds)


if __name__ == "__main__":
    main()
