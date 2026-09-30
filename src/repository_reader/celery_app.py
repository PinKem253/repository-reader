"""Track 4 muc 3 (Async task queue -- Celery).

File nay CHI lo cau hinh 1 instance Celery duy nhat cho ca app -- khong
dinh nghia task thuc te o day (xem tasks.py), giu dung nguyen tac tach
trach nhiem da theo suot project (config vs logic).
"""
from celery import Celery
from repository_reader.config import settings

# 1 instance Celery duy nhat, dung chung redis_url lam CA 2 vai tro:
# - broker: hang doi noi app.py DAY task vao (khong chay ngay)
# - backend: noi WORKER ghi trang thai/ket qua task SAU KHI chay xong,
#   de app.py doc lai qua AsyncResult(task_id) ma khong can giu ket noi
#   HTTP mo lien tuc.
celery_app = Celery(
    "repository_reader",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

# task_track_started=True: Celery mac dinh CHI phan biet PENDING/SUCCESS/
# FAILURE, bo qua trang thai "worker da nhan task, dang chay thuc su".
# Bat co nay de them trang thai STARTED -- can thiet de UI (ui.py) phan
# biet duoc "con nam cho trong hang doi" vs "dang chay that".
celery_app.conf.update(
    task_track_started=True,
)


if __name__ == "__main__":
    pass
