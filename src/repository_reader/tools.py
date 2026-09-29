"""
tools.py — Định nghĩa các "tool" mà Agent Loop (agent.py) được phép gọi.

Ở bước đầu của Giai đoạn 3, ta chỉ có 1 tool: search_semantic — tận dụng lại
hàm đã có sẵn trong vector_store.py từ Giai đoạn 1/2, không viết logic mới.

File này tách làm 2 phần, đúng tinh thần "framework-agnostic":
1. Khai báo tool (data thuần, không phụ thuộc SDK Gemini cụ thể nào)
2. execute_tool() — dispatcher: nhận lựa chọn của model, gọi đúng hàm thật

Việc convert khai báo này sang đúng format SDK Gemini (types.Tool,
types.FunctionDeclaration) sẽ làm ở agent.py — tools.py không cần biết
đang nói chuyện với Gemini hay model nào khác.
"""

from repository_reader import vector_store, ingest
from pathlib import Path
import re



# --- Phần 1: khai báo tool cho model biết ---
# Đây là dict thuần Python, theo chuẩn JSON Schema (giống hệt "parameters"
# JSON Schema đã học ở B2 khi làm request body Pydantic — chỉ khác chỗ dùng
# để mô tả THAM SỐ HÀM cho model, thay vì mô tả HTTP body cho FastAPI).
# Model đọc "description" để quyết định: có nên gọi tool này không, và nếu
# gọi thì điền "query" là gì.
SEARCH_SEMANTIC_DECLARATION = {
    "name": "search_semantic",
    "description": (
        "Tìm các đoạn code/document trong repository theo độ tương đồng "
        "ngữ nghĩa (semantic similarity). Dùng khi câu hỏi mang tính khái "
        "niệm chung, ví dụ 'hàm này dùng để làm gì', 'repo này xử lý ra sao'. "
        "KHÔNG dùng khi cần tìm chính xác tên hàm/biến/pattern cụ thể."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {
                "type": "STRING",
                "description": "Câu truy vấn dạng ngôn ngữ tự nhiên để tìm kiếm.",
            },
        },
        "required": ["query"],
    },
}

# 2. Giới hạn số kết quả trả về — lý do giống top_k của search_semantic:
# tránh observation quá dài tràn context nếu pattern khớp hàng trăm dòng.
MAX_MATCHES = 20

# 3. Khai báo tool thứ 2 — thêm ngay dưới SEARCH_SEMANTIC_DECLARATION
SEARCH_EXACT_DECLARATION = {
    "name": "search_exact",
    "description": (
        "Tìm các dòng khớp CHÍNH XÁC theo pattern (regex) trong toàn bộ file "
        "của repository. Dùng khi cần tìm chính xác tên hàm/biến/chuỗi cụ thể "
        "(vd 'def parse_url', 'class Repo'). KHÔNG dùng cho câu hỏi mang tính "
        "khái niệm chung -- lúc đó dùng search_semantic."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "pattern": {
                "type": "STRING",
                "description": (
                    "Regex pattern (cú pháp Python re) khớp trên từng dòng. "
                    "Có thể là chuỗi thường (vd 'parse_url') hoặc regex thật "
                    "(vd 'def \\\\w+_url')."
                ),
            },
        },
        "required": ["pattern"],
    },
}


MAX_READ_LINES = 200  # giới hạn số dòng đọc mỗi lần -- tránh model đọc nguyên 1 file lớn tràn context
READ_FILE_DECLARATION = {
    "name": "read_file",
    "description": (
        "Đọc nội dung thật của 1 file trong repository, theo path + khoảng "
        "dòng cụ thể. Dùng khi đã biết CHÍNH XÁC vị trí cần xem (thường sau "
        "khi search_semantic hoặc search_exact đã trỏ ra 1 file/dòng). "
        "KHÔNG dùng để tìm kiếm -- dùng search_semantic/search_exact trước."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "path": {
                "type": "STRING",
                "description": (
                    "Đường dẫn file, lấy từ citation của search_semantic/"
                    "search_exact (vd 'cloned_repos/13/README.md' hoặc "
                    "'README.md')."
                ),
            },
            "start_line": {
                "type": "INTEGER",
                "description": "Dòng bắt đầu đọc (1-indexed). Bỏ trống để đọc từ đầu file.",
            },
            "end_line": {
                "type": "INTEGER",
                "description": f"Dòng kết thúc. Bỏ trống để đọc tối đa {MAX_READ_LINES} dòng kể từ start_line.",
            },
        },
        "required": ["path"],  # start_line/end_line KHÔNG required -- optional
    },
}



MAX_STRUCTURE_LINES = 200

LIST_REPO_STRUCTURE_DECLARATION = {
    "name": "list_repo_structure",
    "description": (
        "Liệt kê cây thư mục (danh sách file + folder) của repository. Dùng "
        "cho câu hỏi tổng quan về cấu trúc, vd 'repo này có những file/folder "
        "nào', 'tổ chức code ra sao'. KHÔNG đọc nội dung file -- chỉ trả về "
        "tên, dùng read_file sau khi đã biết muốn xem file nào cụ thể."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {},  # không cần tham số nào -- repo_id hệ thống đã tự truyền vào
    },
}

# Danh sách tất cả tool hiện có. Sau này thêm search_exact/read_file/
# list_repo_structure chỉ cần: thêm 1 declaration vào đây + thêm 1 nhánh
# elif vào execute_tool() bên dưới — không phải sửa gì ở agent.py.
ALL_TOOL_DECLARATIONS = [
    SEARCH_SEMANTIC_DECLARATION,
    SEARCH_EXACT_DECLARATION,
    READ_FILE_DECLARATION,
    LIST_REPO_STRUCTURE_DECLARATION,
]


# 4. Hàm thật thực hiện search_exact — đặt trước execute_tool()
def _search_exact(pattern: str, repo_id: int) -> str:
    """
    Quét từng dòng của từng file hợp lệ trong repo đã clone (đúng phạm vi
    file đã ingest, tái dùng ingest.list_valid_files), tìm dòng khớp regex
    `pattern`. Trả về text kèm citation [file:line] để model trích dẫn.

    Dấu gạch dưới đầu tên hàm (_search_exact) là quy ước Python: hàm "nội
    bộ" của module, không nằm trong "API công khai" của tools.py -- chỉ
    execute_tool() gọi trực tiếp, code ngoài module không nên import hàm
    này (khác search_semantic của vector_store.py, được thiết kế để gọi từ
    nhiều nơi).
    """
    # Phòng thủ: model tự viết pattern, không đảm bảo là regex hợp lệ (vd
    # dấu ngoặc chưa đóng). Compile trước, bắt lỗi NGAY TẠI ĐÂY thay vì để
    # crash giữa chừng lúc đang quét hàng trăm file -- trả lỗi dạng text để
    # model tự sửa pattern ở vòng lặp kế tiếp, không phải Python exception
    # làm chết cả agent loop.
    try:
        compiled = re.compile(pattern)
    except re.error as e:
        return f"Lỗi: pattern regex không hợp lệ ('{pattern}'): {e}"

    repo_path = ingest.CLONE_BASE_DIR / str(repo_id)
    if not repo_path.exists():
        return f"Lỗi: không tìm thấy thư mục đã clone cho repo_id={repo_id}."

    # Tái dùng ĐÚNG danh sách file đã dùng lúc ingest -- để search_exact chỉ
    # tìm trong phạm vi file đã được index (khớp với search_semantic), tránh
    # quét cả file rác/binary/.git không liên quan.
    valid_files = ingest.list_valid_files(repo_path)

    matches = []
    for file_path in valid_files:
        lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line_number, line in enumerate(lines, start=1):
            if compiled.search(line):
                matches.append((file_path, line_number, line))
                if len(matches) >= MAX_MATCHES:
                    break
        if len(matches) >= MAX_MATCHES:
            break

    if not matches:
        return f"Không tìm thấy dòng nào khớp pattern '{pattern}'."

    lines_out = [
        f"[{file_path}:{line_number}] {line.strip()}"
        for file_path, line_number, line in matches
    ]
    header = ""
    if len(matches) >= MAX_MATCHES:
        header = f"(Chỉ hiện {MAX_MATCHES} kết quả đầu, có thể còn nhiều hơn)\n"
    return header + "\n".join(lines_out)


def _read_file(path: str, repo_id: int, start_line=None, end_line=None) -> str:
    """
    Đọc nội dung thật 1 file trong repo đã clone, theo path + khoảng dòng.

    An toàn: model có thể gửi path bất kỳ -- verify resolved path phải nằm
    TRONG thư mục đã clone của đúng repo_id này, không cho phép đọc file
    ngoài phạm vi (path traversal, file hệ thống...).
    """
    repo_root = (ingest.CLONE_BASE_DIR / str(repo_id)).resolve()
    if not repo_root.exists():
        return f"Lỗi: không tìm thấy thư mục đã clone cho repo_id={repo_id}."

    # BUG đã fix: Path(path).resolve() một mình sẽ resolve theo cwd của
    # TIẾN TRÌNH (nơi chạy uvicorn), không phải theo repo_root -- nên khi
    # model gửi path dạng bare filename (vd "README.md", đúng như mô tả
    # trong READ_FILE_DECLARATION cho phép), kết quả bị lệch ra ngoài
    # repo_root và luôn báo "nằm ngoài phạm vi" dù file có thật.
    #
    # Cách sửa: thử ưu tiên join path vào repo_root trước (trường hợp phổ
    # biến nhất -- model gửi path tương đối tính từ gốc repo). Chỉ khi
    # cách đó không ra file thật, mới fallback về resolve() thô (trường
    # hợp model gửi nguyên path citation dạng "cloned_repos/13/...").
    candidate = Path(path)
    if candidate.is_absolute():
        target = candidate.resolve()
    else:
        in_repo = (repo_root / candidate).resolve()
        target = in_repo if in_repo.exists() else candidate.resolve()

    # Kiểm tra bắt buộc: target phải nằm trong repo_root. is_relative_to()
    # trả False nếu target ở ngoài (kể cả path traversal kiểu "../..").
    if not target.is_relative_to(repo_root):
        return f"Lỗi: path '{path}' nằm ngoài phạm vi cho phép của repo này."

    if not target.exists() or not target.is_file():
        return f"Lỗi: không tìm thấy file '{path}' trong repo."

    lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()

    # Ép kiểu int phòng trường hợp SDK trả về số dạng float cho field INTEGER
    # (đã gặp kiểu lỗi tương tự với numpy vector ở Giai đoạn 1 -- luôn ép
    # kiểu tường minh khi nhận dữ liệu từ nguồn ngoài, không giả định sẵn).
    start_line = int(start_line) if start_line is not None else 1
    end_line = int(end_line) if end_line is not None else start_line + MAX_READ_LINES - 1

    start_idx = max(start_line - 1, 0)
    end_idx = min(end_line, len(lines))

    if start_idx >= len(lines):
        return f"Lỗi: file '{path}' chỉ có {len(lines)} dòng, không có dòng {start_line}."

    selected = lines[start_idx:end_idx]
    numbered = [f"{i + start_idx + 1}: {line}" for i, line in enumerate(selected)]
    return f"[{path}:{start_idx + 1}-{end_idx}]\n" + "\n".join(numbered)


def _list_repo_structure(repo_id: int) -> str:
    """
    Liệt kê cây thư mục của repo đã clone, đệ quy qua từng thư mục con.
    Không đọc nội dung file -- chỉ tên, nên tool này rẻ (nhanh) hơn nhiều
    so với search_exact (phải đọc hết nội dung mọi file).

    Tái dùng ingest.EXCLUDE để nhất quán: thư mục nào bị loại khỏi ingest
    (.git, __pycache__, tests) thì cũng bị loại khỏi structure view, tránh
    gây nhiễu bằng thông tin không liên quan tới phần đã được index.
    """
    repo_path = ingest.CLONE_BASE_DIR / str(repo_id)
    if not repo_path.exists():
        return f"Lỗi: không tìm thấy thư mục đã clone cho repo_id={repo_id}."

    lines = []
    truncated = False

    # Hàm lồng trong hàm (nested function) -- walk() chỉ tồn tại bên trong
    # _list_repo_structure(), dùng để đệ quy qua từng cấp thư mục con.
    # `nonlocal truncated` cho phép walk() SỬA biến `truncated` của hàm cha
    # (_list_repo_structure) -- khác `global` (chỉ dùng cho biến ở module-
    # level), nonlocal dùng khi biến thuộc 1 hàm bao ngoài, không phải module.
    def walk(current_dir: Path, prefix: str = ""):
        nonlocal truncated
        if truncated:
            return
        # sorted() để thứ tự hiển thị ổn định -- Path.iterdir() không đảm
        # bảo thứ tự cố định giữa các lần chạy (phụ thuộc OS/filesystem).
        entries = sorted(current_dir.iterdir(), key=lambda p: (p.is_file(), p.name))
        for entry in entries:
            if entry.name in ingest.EXCLUDE:
                continue
            if len(lines) >= MAX_STRUCTURE_LINES:
                truncated = True
                return
            if entry.is_dir():
                lines.append(f"{prefix}{entry.name}/")
                walk(entry, prefix + "  ")
            else:
                lines.append(f"{prefix}{entry.name}")

    walk(repo_path)

    if not lines:
        return "Repo rỗng hoặc không có file nào (sau khi loại bỏ thư mục hệ thống)."

    result = "\n".join(lines)
    if truncated:
        result += f"\n... (đã cắt bớt, chỉ hiện {MAX_STRUCTURE_LINES} dòng đầu)"
    return result




# Cập nhật execute_tool() -- thêm nhánh cuối cùng:
def execute_tool(name: str, args: dict, repo_id: int) -> str:
    if name == "search_semantic":
        query = args["query"]
        results = vector_store.search_semantic(query, repo_id=repo_id, top_k=5)

        if not results:
            return "Không tìm thấy kết quả nào khớp với truy vấn này."

        lines = []
        for r in results:
            lines.append(
                f"[{r['file']}:{r['start_line']}-{r['end_line']}] "
                f"(score={r['score']:.3f})\n{r['text']}"
            )
        return "\n\n".join(lines)

    elif name == "search_exact":
        pattern = args["pattern"]
        return _search_exact(pattern, repo_id=repo_id)

    elif name == "read_file":
        path = args["path"]
        start_line = args.get("start_line")
        end_line = args.get("end_line")
        return _read_file(path, repo_id=repo_id, start_line=start_line, end_line=end_line)

    elif name == "list_repo_structure":
        return _list_repo_structure(repo_id=repo_id)

    return f"Lỗi: không tồn tại tool tên '{name}'."


if __name__ == "__main__":
    # Test nhanh, độc lập với agent.py: gọi thẳng dispatcher như thể model
    # vừa "chọn" gọi search_semantic — xác nhận dispatch + format đúng
    # trước khi lắp vào vòng lặp thật (bug ở đây sẽ dễ tìm hơn nhiều so với
    # tìm trong cả vòng lặp ReAct).
    #output = execute_tool("search_semantic", {"query": "how does this repo work"}, repo_id=9)
    #output = execute_tool("search_exact", {"pattern": r"def \w+"}, repo_id=12)
    # output = execute_tool(
    #         "read_file",
    #         {"path": "cloned_repos/12/README.md", "start_line": None, "end_line": None},
    #         repo_id=12,
    #     )
    output = execute_tool(name="list_repo_structure", args={}, repo_id=12)

    print(output)

