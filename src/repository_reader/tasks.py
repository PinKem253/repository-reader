"""Track 4 muc 3 (Async task queue -- Celery): dinh nghia task THAT.

Tach rieng khoi celery_app.py (chi lo config) va ingest.py (chi lo logic
ingest thuan tuy, khong biet gi ve Celery) -- moi file 1 trach nhiem,
dung pattern da theo suot project.
"""
import asyncio
from typing import Optional

from repository_reader.celery_app import celery_app
from repository_reader import ingest


@celery_app.task(name="ingest_task")
def ingest_task(url: str, owner_id: Optional[int] = None) -> int:
    """Wrapper DONG BO quanh ingest.ingest_repo() (async def).

    Task cua Celery mac dinh la ham dong bo -- worker khong tu hieu
    async/await. asyncio.run() o day AN TOAN vi task nay chay trong
    TIEN TRINH WORKER RIENG (lenh `celery worker`), khong co event loop
    nao khac dang chay de xung dot -- khac han boi canh app.py, noi
    FastAPI/uvicorn DA CO SAN 1 event loop dang chay, khong the goi
    asyncio.run() long vao trong do (se raise RuntimeError).

    Tra ve int (repo_id that) -- Celery tu dong luu gia tri return nay
    vao result backend, app.py doc lai qua AsyncResult(task_id).result.
    """
    return asyncio.run(ingest.ingest_repo(url, owner_id=owner_id))


if __name__ == "__main__":
    pass
