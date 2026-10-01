"""
tests/conftest.py — pytest hook dùng chung cho toàn bộ tests/.

pytest không tự nhận argument tuỳ ý ngoài các cờ built-in (--verbose, -k,
...) -- pytest_addoption là cơ chế CHUẨN để khai thêm 1 cờ CLI mới (ở đây
--repo-id), tương đương argparse.add_argument() đã dùng trong run_eval.py
cũ, nhưng theo đúng quy ước pytest (đọc được qua request.config.getoption).
"""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--repo-id",
        action="store",
        type=int,
        default=None,
        help=(
            "repo_id đã ingest thật (xem GET /repos) để chạy "
            "test_agent_eval.py -- vd: pytest tests/test_agent_eval.py "
            "--repo-id=13"
        ),
    )


@pytest.fixture
def repo_id(request):
    """Fixture dùng trong test_agent_eval.py -- đọc --repo-id từ CLI.

    Nếu không truyền --repo-id, SKIP (không FAIL) toàn bộ test cần repo
    thật -- phân biệt rõ "chưa có dữ liệu để test" khỏi "code có bug", 2
    trạng thái pytest báo khác nhau (skipped vs failed) đúng với bản chất.
    """
    value = request.config.getoption("--repo-id")
    if value is None:
        pytest.skip(
            "Cần --repo-id=<id> (1 repo đã ingest thật) để chạy eval test "
            "-- vd: pytest tests/test_agent_eval.py --repo-id=13"
        )
    return value
