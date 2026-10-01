"""
eval_questions.py — Bộ câu hỏi eval cố định cho agent.py.

Câu hỏi nhóm "large_file" đang trỏ vào repo thật:
https://github.com/PinKem253/tabm (TabM -- model học sâu cho dữ liệu dạng
bảng, ICLR 2025). Repo này có: README.md, LICENSE, pyproject.toml,
example.ipynb -- nhưng KHÔNG có thư mục tests/ hay .github/workflows/, nên
câu multi-part-1 dưới đây sẽ hợp lệ có 2/5 phần trả lời "chưa tìm thấy" --
đúng là điều muốn test (model phải nói rõ thiếu, không được lờ đi/đoán).

Mỗi câu hỏi gắn 1 "category" mô tả nó đang thử hành vi nào của agent loop:

- simple             : câu hỏi cơ bản, ít turns, dùng làm baseline/sanity
                        check (nếu câu này cũng lỗi thì có bug nghiêm trọng
                        hơn, không cần test các nhóm khác trước).
- multi_part         : nhiều phần độc lập, cần đọc nhiều file khác nhau --
                        test cơ chế "ép trả lời cuối" (forced final answer)
                        khi repo đủ lớn để hợp lệ cần nhiều turns thật.
- large_file         : file dài/có cấu trúc (vd .ipynb) -- test model có đọc
                        tiếp bằng start_line lớn hơn thay vì kết luận vội từ
                        ~100 dòng đầu hay không.
- nonexistent        : hỏi về thứ KHÔNG có trong repo -- test model có tự
                        nhận ra "không tìm thấy" và dừng đúng lúc, hay cứ
                        đổi cách hỏi search_semantic/search_exact tới hết
                        vòng.
- adversarial_repeat : câu hỏi mơ hồ, KHÁC với câu bug gốc đã vá (không phải
                        replay lại đúng bug cũ) -- test quy tắc chống lặp
                        search_semantic có tổng quát hoá được sang tình
                        huống mới, hay chỉ vá đúng 1 case đã thấy.

--- Track 4 mục 4 (Automated testing cho LLM outputs) ---

Mỗi câu hỏi giờ có thêm field "rubric": list[str], mỗi string là 1 tiêu chí
CỤ THỂ, dùng bởi tests/llm_judge.py (LLM-as-judge) để chấm tự động. "notes"
giữ nguyên nguyên bản (văn xuôi, cho người đọc hiểu nhanh ý định của câu
hỏi) -- "rubric" là bản CHUYỂN THỂ của notes sang dạng tiêu chí rời rạc, máy
chấm được. 2 field không trùng nhau 100% vì mục đích khác nhau: notes có
thể giải thích BỐI CẢNH (vd repo nào, vì sao hỏi câu này), rubric chỉ chứa
ĐIỀU KIỆN cần kiểm tra trên chính answer.

KHÔNG phải unit test theo nghĩa chặt (so khớp == giá trị cố định) -- xem
giải thích đầy đủ về LLM-as-judge + rule cứng ở tests/test_agent_eval.py.
"""

EVAL_QUESTIONS = [
    {
        "id": "simple-1",
        "category": "simple",
        "question": "Repository này là gì, dùng để làm gì?",
        "notes": (
            "Nên trả lời trong 1-2 turns, có trích dẫn [file:start-end]. "
            "Kỳ vọng: mô tả TabM là model học sâu cho dữ liệu dạng bảng "
            "(ensemble of k models, ICLR 2025)."
        ),
        "rubric": [
            "Answer mô tả TabM là 1 model/phương pháp học sâu (deep "
            "learning) cho dữ liệu dạng bảng (tabular data)",
            "Answer có nhắc tới ý tưởng ensemble/nhiều submodel (k models) "
            "hoặc tham chiếu ICLR 2025",
            "Answer có ít nhất 1 trích dẫn dạng [file:start-end]",
        ],
    },
    {
        "id": "simple-2",
        "category": "simple",
        "question": "File README.md nói gì về mục đích chính của dự án?",
        "notes": "Đọc thẳng README, không cần search_semantic.",
        "rubric": [
            "Answer mô tả đúng mục đích chính của dự án như README.md viết",
            "Answer có trích dẫn tham chiếu tới README.md",
        ],
    },
    {
        "id": "multi-part-1",
        "category": "multi_part",
        "question": (
            "Repo này làm gì, dùng license gì, cách cài đặt/dependencies ra "
            "sao, có testing framework nào không, và có CI/CD pipeline "
            "(vd GitHub Actions) không?"
        ),
        "notes": (
            "Repo TabM CÓ README/LICENSE/pyproject.toml -- 3 phần đầu phải "
            "trả lời được, có trích dẫn. Repo KHÔNG có thư mục tests/ hay "
            ".github/workflows/ -- 2 phần cuối PHẢI được nói rõ 'chưa tìm "
            "thấy', không được lờ đi hay đoán bừa là 'có pytest' chẳng hạn."
        ),
        "rubric": [
            "Có mô tả repo TabM làm gì (model học sâu cho dữ liệu dạng "
            "bảng)",
            "Có nhắc tới license của repo (MIT, theo LICENSE file)",
            "Có đề cập cách cài đặt/dependencies dựa trên pyproject.toml",
            "Nói RÕ KHÔNG tìm thấy testing framework -- không bịa là có "
            "pytest/unittest",
            "Nói RÕ KHÔNG tìm thấy CI/CD pipeline -- không bịa là có "
            "GitHub Actions",
        ],
    },
    {
        "id": "multi-part-2",
        "category": "multi_part",
        "question": (
            "Cấu trúc thư mục của dự án như thế nào, và entry point chính "
            "để chạy chương trình là gì?"
        ),
        "notes": (
            "Cần list_repo_structure trước. Repo TabM không phải app chạy "
            "được (không có main.py rõ ràng) -- entry point thực tế là "
            "import tabm.py như 1 package/module, hoặc chạy example.ipynb. "
            "Xem model có nhận ra và mô tả đúng thay vì bịa 1 entry point "
            "không tồn tại."
        ),
        "rubric": [
            "Có mô tả cấu trúc thư mục ở mức hợp lý (dựa trên "
            "list_repo_structure)",
            "KHÔNG bịa ra 1 entry point dạng main.py/app chạy trực tiếp mà "
            "không tồn tại trong repo",
            "Có nhận ra và mô tả đúng cách dùng thực tế là import tabm.py "
            "như module, hoặc chạy qua example.ipynb",
        ],
    },
    {
        "id": "large-file-1",
        "category": "large_file",
        "question": (
            "File example.ipynb dùng để làm gì, và các bước chính trong đó "
            "để huấn luyện/sử dụng model TabM là gì?"
        ),
        "notes": (
            "example.ipynb là notebook thật trong repo TabM. Model phải đọc "
            "tiếp bằng start_line lớn hơn nếu ~100 dòng đầu chỉ là metadata "
            "JSON của notebook (cell markdown mở đầu), không được kết luận "
            "vội chỉ từ đó."
        ),
        "rubric": [
            "Answer mô tả được các bước chính THẬT trong notebook (không "
            "chỉ nói chung chung kiểu 'đây là notebook ví dụ')",
            "Answer có ít nhất 1 trích dẫn [file:start-end] trỏ tới "
            "example.ipynb, cho thấy đã đọc sâu hơn phần metadata/markdown "
            "mở đầu chứ không kết luận vội từ ~100 dòng đầu",
        ],
    },
    {
        "id": "nonexistent-1",
        "category": "nonexistent",
        "question": (
            "File config.yaml dùng để cấu hình training pipeline có những "
            "tham số mặc định gì?"
        ),
        "notes": (
            "Repo TabM không có file config.yaml ở gốc. Câu trả lời PHẢI "
            "nói rõ 'chưa tìm thấy', không được đoán tham số bừa."
        ),
        "rubric": [
            "Answer nói rõ KHÔNG tìm thấy file config.yaml / không có "
            "thông tin này trong repo",
            "Answer KHÔNG tự bịa ra các tham số mặc định cụ thể không có "
            "trong repo",
        ],
    },
    {
        "id": "nonexistent-2",
        "category": "nonexistent",
        "question": (
            "Dự án này kết nối tới database nào, và connection string được "
            "cấu hình ở đâu?"
        ),
        "notes": (
            "TabM là 1 model/package nghiên cứu, không có phần database -- "
            "kỳ vọng trả lời trung thực là không có, không lặp tìm kiếm vô "
            "ích."
        ),
        "rubric": [
            "Answer nói rõ dự án này KHÔNG kết nối database / không có "
            "phần này trong repo",
            "Answer KHÔNG bịa ra tên database hay connection string cụ thể "
            "không có trong repo",
        ],
    },
    {
        "id": "adversarial-repeat-1",
        "category": "adversarial_repeat",
        "question": (
            "Thuật toán tối ưu hoá (optimizer) chính được dùng khi huấn "
            "luyện TabM hoạt động như thế nào?"
        ),
        "notes": (
            "Cố ý mơ hồ để dễ ra kết quả search_semantic yếu (tabm.py có "
            "thể không nói rõ optimizer, phần đó thường nằm ở code "
            "training trong paper/ hoặc example.ipynb) -- xem model có đổi "
            "sang list_repo_structure/search_exact sau 1 lần thử, hay lặp "
            "search_semantic nhiều lần với query khác nhau (biến thể MỚI "
            "của bug đã vá, không phải replay lại y hệt)."
        ),
        "rubric": [
            "Answer mô tả optimizer dựa trên nội dung THẬT tìm được trong "
            "repo (có trích dẫn), hoặc nói rõ KHÔNG tìm thấy thông tin cụ "
            "thể -- KHÔNG bịa tên 1 optimizer cụ thể (vd 'Adam') nếu answer "
            "không trích dẫn được bằng chứng nào cho điều đó",
        ],
    },
]
