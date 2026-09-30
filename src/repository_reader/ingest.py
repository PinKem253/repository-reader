from pathlib import Path 
from repository_reader import embedding, vector_store, generation, db
from typing import Optional
import subprocess

CLONE_BASE_DIR = Path("cloned_repos")

VALID_EXT = {".py", ".md", ".rst"}
EXCLUDE = {"tests", ".git", "__pycache__"}

def list_valid_files(repo_path):
    result = []
    
    for p in Path(repo_path).rglob("*"):
        if p.is_file() and p.suffix in VALID_EXT and not EXCLUDE.intersection(p.parts):
            result.append(p)
    return result


def chunk_file(path):
    lines = path.read_text(encoding = "utf-8", errors = "ignore").splitlines()
    chunks = []
    
    for i in range(0, len(lines), 40):
        chunk_lines = lines[i: i+50]
        if not chunk_lines:
            continue
        chunks.append({
            "file": str(path),
            "start_line": i+1,
            "end_line": i + len(chunk_lines),
            "text": "\n".join(chunk_lines)
        })
    return chunks

def get_all_chunks(repo_path):
    all_valid_files = list_valid_files(repo_path= repo_path)
    all_chunks = []
    for p in all_valid_files:
        all_chunks.extend(chunk_file(p))
    return all_chunks

def clone_repo(url: str, repo_id: int) -> Path:
    target_dir = CLONE_BASE_DIR / str(repo_id)
    CLONE_BASE_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", url, str(target_dir)],
        check= True,
    )
    return target_dir


def get_default_branch(repo_path: Path) -> Optional[str]:
    """UX citation: lay TEN NHANH THAT SU git da checkout ngay sau
    clone_repo() -- day CHINH LA nhanh mac dinh cua repo tren GitHub (git
    clone luon tu dong checkout dung nhanh do). KHONG doan cung "main"
    hay "master" -- nhieu repo cu tren GitHub van dung "master", doan sai
    se ra link hong.

    Dung de UI (ui.py) dung xay link truc tiep toi file tren GitHub cho
    tung citation. Loi o day (vd git khong co san, thu muc khong phai
    git repo that) CHI lam link khong hien trong UI, KHONG duoc phep lam
    sap ca luong ingest chinh -- vi vay bat loi, tra None thay vi raise.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or None
    except (subprocess.CalledProcessError, OSError):
        return None

    
async def ingest_repo(url: str, owner_id: Optional[int] = None) -> int:
    # Track 4 muc 1 Part C: nhan them owner_id (tuy chon, mac dinh None
    # de khong pha loi goi cu tu script/test), truyen thang xuong
    # db.create_repo() de repo moi duoc gan dung chu tu luc tao.
    repo_id = await db.create_repo(url, owner_id=owner_id)
    repo_path = clone_repo(url, repo_id)

    # UX citation: luu nhanh mac dinh NGAY sau clone, truoc ca chunk/embed
    # -- buoc nay re (1 lenh git cuc bo, khong goi API ngoai), va neu
    # chunk/embed ben duoi that bai (vd all_chunks rong -> status=
    # "failed") thi default_branch van duoc luu dung, khong bi anh huong.
    branch = get_default_branch(repo_path)
    if branch:
        await db.update_repo_branch(repo_id, branch)

    all_chunks = get_all_chunks(repo_path=repo_path)
    
    if not all_chunks:
        await db.update_repo_status(repo_id, "failed")
        raise ValueError(
            f"Repo {url} không có file nào khớp {VALID_EXT} — không thể ingest."
        )
    
    dense_vecs = embedding.embed_texts([c["text"] for c in all_chunks])
    vector_store.upsert_chunks(all_chunks=all_chunks, dense_vecs= dense_vecs, repo_id= repo_id)
    await db.update_repo_status(repo_id, "ready")
    return repo_id
    
    


if __name__ == "__main__":
    pass
