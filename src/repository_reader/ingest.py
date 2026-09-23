from pathlib import Path 
from repository_reader import embedding, vector_store, generation, db
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
    
async def ingest_repo(url: str) -> int:
    repo_id = await db.create_repo(url)
    repo_path = clone_repo(url, repo_id)
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
    
    
    
    
    
    
    
    
    
   

