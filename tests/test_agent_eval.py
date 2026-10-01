"""
tests/test_agent_eval.py — Track 4 mục 4: test tự động cho output của
agent.py, thay thế vai trò "đọc bằng mắt" của run_eval.py bằng PASS/FAIL
tự động (run_eval.py vẫn giữ lại để debug thủ công khi cần đọc log chi
tiết từng turn, 2 file phục vụ 2 mục đích khác nhau).

Cách chạy (từ project root, sau khi đã ingest ít nhất 1 repo thật):
    uv run pytest tests/test_agent_eval.py --repo-id=13 -v

Thiếu --repo-id: toàn bộ test SKIP (không FAIL) -- xem conftest.py.

Mỗi item trong EVAL_QUESTIONS trở thành 1 test case RIÊNG qua parametrize.
LƯU Ý: pytest mặc định chạy các case này TUẦN TỰ (không song song như
vector hoá numpy) -- khác biệt thật so với vòng `for` của run_eval.py cũ
nằm ở cách BÁO CÁO (mỗi case có PASS/FAIL độc lập, 1 câu fail không làm
mất thông tin của các câu khác), không nằm ở tốc độ chạy.

2 lớp kiểm tra, THEO ĐÚNG THỨ TỰ (rẻ/xác định trước, đắt/cần LLM sau):
  1. Rule cứng (regex, so sánh bool) -- không gọi thêm API nào, fail ngay
     nếu sai, không tốn thêm 1 lời gọi Gemini vô ích cho judge.
  2. LLM-as-judge theo rubric (tests/llm_judge.py) -- CHỈ gọi nếu lớp 1 đã
     pass.
"""

import re

import pytest

from eval_questions import EVAL_QUESTIONS
from llm_judge import judge_answer

from repository_reader import agent

# Cùng ý tưởng regex đã dùng ở ui.py (format_citations): 1 cụm trong ngoặc
# vuông được coi là "có hình dạng citation" nếu chứa dấu ":" -- và nếu đã
# mang hình dạng đó thì BẮT BUỘC phải khớp đúng "file:start-end" (start/end
# là số). Citation có hình dạng gần đúng nhưng sai cú pháp là 1 regression
# THẬT (sai định dạng đã dạy riêng trong SYSTEM_INSTRUCTIONS của agent.py),
# phát hiện được bằng regex thuần -- không cần LLM judge mới thấy được.
_CITATION_LIKE_RE = re.compile(r"\[([^\[\]]*:[^\[\]]*)\]")
_VALID_CITATION_RE = re.compile(r"^\s*[^,:\[\]]+\s*:\s*\d+\s*-\s*\d+\s*$")


def _assert_citation_syntax_valid(answer: str) -> None:
    malformed = [
        m for m in _CITATION_LIKE_RE.findall(answer)
        if not _VALID_CITATION_RE.match(m)
    ]
    assert not malformed, f"Có citation sai định dạng [file:start-end]: {malformed}"


@pytest.mark.parametrize(
    "item", EVAL_QUESTIONS, ids=[item["id"] for item in EVAL_QUESTIONS]
)
def test_agent_answer(item, repo_id):
    result = agent.run(item["question"], repo_id)
    answer = result["answer"]

    # --- Lớp 1: rule cứng, không cần LLM ---
    _assert_citation_syntax_valid(answer)

    # Không câu nào trong EVAL_QUESTIONS hiện tại CỐ Ý test việc hết
    # MAX_TURNS (đó là việc riêng của tests/run_eval.py + logs/agent_runs.jsonl
    # cho mục đích percentile) -- nên mặc định mọi câu đều kỳ vọng model TỰ
    # dừng (exhausted_budget=False). Item nào sau này cố ý test hành vi ép
    # trả lời cuối có thể khai thêm "expect_exhausted_budget": True trong
    # eval_questions.py để override, không cần sửa file test này.
    expect_exhausted = item.get("expect_exhausted_budget", False)
    assert result["exhausted_budget"] == expect_exhausted, (
        f"exhausted_budget={result['exhausted_budget']}, kỳ vọng "
        f"{expect_exhausted} -- model có thể đã kẹt loop hoặc "
        f"SYSTEM_INSTRUCTIONS/MAX_TURNS vừa bị sửa gây hồi quy."
    )

    # --- Lớp 2: LLM-as-judge theo rubric, CHỈ chạy nếu lớp 1 đã pass ---
    verdict = judge_answer(item["question"], answer, item["rubric"])
    failed = [c for c in verdict["criteria_results"] if not c["satisfied"]]
    assert verdict["overall_pass"], (
        f"Answer KHÔNG đạt {len(failed)}/{len(item['rubric'])} tiêu chí:\n"
        + "\n".join(f"- {c['criterion']}: {c['reason']}" for c in failed)
        + f"\n\nAnswer thật:\n{answer}"
    )
