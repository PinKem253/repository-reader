"""Track 4 muc 3 (Async task queue -- Celery): dinh nghia task THAT.

Tach rieng khoi celery_app.py (chi lo config) va ingest.py (chi lo logic
ingest thuan tuy, khong biet gi ve Celery) -- moi file 1 trach nhiem,
dung pattern da theo suot project.
"""
import asyncio
from typing import Optional

from repository_reader.celery_app import celery_app
from repository_reader import ingest, db


async def _run_ingest(url: str, owner_id: Optional[int]) -> int:
    """Chay ingest_repo() RỒI DISPOSE engine -- xem giai thich bug o
    duoi `ingest_task`. `try/finally` dam bao dispose() LUON duoc goi
    (ke ca khi ingest_repo() raise loi, vd all_chunks rong), khong de
    connection cu song sot qua lan goi asyncio.run() ke tiep."""
    try:
        return await ingest.ingest_repo(url, owner_id=owner_id)
    finally:
        await db.engine.dispose()


@celery_app.task(name="ingest_task")
def ingest_task(url: str, owner_id: Optional[int] = None) -> int:
    """Wrapper DONG BO quanh ingest.ingest_repo() (async def).

    Task cua Celery mac dinh la ham dong bo -- worker khong tu hieu
    async/await. asyncio.run() o day AN TOAN vi task nay chay trong
    TIEN TRINH WORKER RIENG (lenh `celery worker`), khong co event loop
    nao khac dang chay de xung dot -- khac han boi canh app.py, noi
    FastAPI/uvicorn DA CO SAN 1 event loop dang chay, khong the goi
    asyncio.run() long vao trong do (se raise RuntimeError).

    BUG THUC TE da gap (2026-10-01): asyncio.run() tao 1 event loop MOI
    cho MOI lan goi, roi DONG HAN loop do khi xong -- nhung `db.engine`
    (ket noi Postgres) la bien GLOBAL tao 1 LAN DUY NHAT luc import
    module, song suot doi tien trinh worker (khac uvicorn, noi chi co
    DUNG 1 event loop song suot nen khong gap van de nay). Lan ingest
    THU HAI trong cung 1 worker se tai dung connection cu van con tro
    toi event loop DAU TIEN (da bi dong) -> crash kieu
    "AttributeError: 'NoneType' object has no attribute 'send'" khi co
    gang viet du lieu qua connection da "chet". Sua bang _run_ingest()
    o tren: dispose() connection pool ngay sau MOI lan task chay xong,
    de lan ingest ke tiep luon tao connection MOI tren event loop MOI,
    khong con tham chieu nao sang event loop da dong.

    Tra ve int (repo_id that) -- Celery tu dong luu gia tri return nay
    vao result backend, app.py doc lai qua AsyncResult(task_id).result.
    """
    return asyncio.run(_run_ingest(url, owner_id))


if __name__ == "__main__":
    pass
