from sqlalchemy.ext.asyncio import create_async_engine
from repository_reader.config import Settings
import logging 
from datetime import datetime
from sqlmodel.ext.asyncio.session import AsyncSession
from repository_reader.models import Repo, User
from sqlmodel import select
from typing import Optional

logger = logging.getLogger(__name__)

try: 
    settings = Settings()
    engine = create_async_engine(settings.database_url)
    logger.info("Create engine successfully")
except Exception as e:
    
    #logger.error("Create engine failed")
    logger.exception("Create engine failed")
    raise e

async def create_repo(url: str, owner_id: Optional[int] = None) -> int:
    """Track 4 muc 1 Part C: them tham so owner_id. None khi khong
    truyen (vd goi tu script/test cu) -- nhung tu app.py (sau Part C)
    luon truyen owner_id that vi endpoint da bat buoc dang nhap."""
    async with AsyncSession(engine) as session:
        repo = Repo(
            url=url,
            status="pending",
            created_at=datetime.utcnow(),
            owner_id=owner_id,
        )
        session.add(repo)
        await session.commit()
        await session.refresh(repo)
        return repo.id
    
    
async def update_repo_status(repo_id: int, status: str) -> None:
    async with AsyncSession(engine) as session:
        repo = await session.get(Repo, repo_id)
        repo.status = status
        session.add(repo)
        await session.commit()


async def update_repo_branch(repo_id: int, branch: str) -> None:
    """UX citation: cung pattern voi update_repo_status() o tren -- goi
    ngay sau khi ingest.clone_repo() thanh cong, luu ten nhanh mac dinh
    THAT SU da duoc git checkout (xem ingest.get_default_branch()). Tach
    rieng ham thay vi nhet vao update_repo_status() vi 2 thu update 2
    field khac nhau, khong lien quan ve mat y nghia (status = trang thai
    pipeline ingest, branch = metadata cua repo tren GitHub)."""
    async with AsyncSession(engine) as session:
        repo = await session.get(Repo, repo_id)
        repo.default_branch = branch
        session.add(repo)
        await session.commit()


async def get_repo(repo_id: int) -> Optional[Repo]:
    """Track 4 muc 1 Part C: lay 1 repo theo primary key -- dung o
    POST /repo/{repo_id} de kiem tra owner_id truoc khi cho Agent Loop
    chay. Tach rieng khoi list_repos() vi day la lay 1 dong theo id,
    khong phai list/filter nhieu dong."""
    async with AsyncSession(engine) as session:
        return await session.get(Repo, repo_id)

    
async def list_repos(owner_id: Optional[int] = None) -> list[Repo]:
    """Track 4 muc 1 Part C: them tham so owner_id (tuy chon).
    Co truyen -> chi tra ve repo cua DUNG user do (dung o GET /repos sau
    khi endpoint da bat buoc dang nhap). Khong truyen (None) -> tra ve
    TOAN BO repo -- giu lai hanh vi cu cho muc dich noi bo/debug, khong
    con expose qua API nua tu sau Part C."""
    async with AsyncSession(engine) as session:
        query = select(Repo)
        if owner_id is not None:
            query = query.where(Repo.owner_id == owner_id)
        result = await session.exec(query)
        return result.all()


# ---------- Track 4 muc 1 (Auth) -- Part B ----------

async def create_user(username: str, hashed_password: str) -> int:
    """Tao 1 dong User moi -- hashed_password PHAI la gia tri da qua
    auth.hash_password() tu truoc, ham nay khong tu hash (tach rach ro
    trach nhiem: db.py chi lo luu tru, auth.py lo bam mat khau)."""
    async with AsyncSession(engine) as session:
        user = User(
            username=username,
            hashed_password=hashed_password,
            created_at=datetime.utcnow(),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user.id


async def get_user_by_username(username: str) -> Optional[User]:
    """Dung o /login -- tra ve None neu khong ton tai (khong raise), de
    app.py tu quyet dinh tra 401 the nao, cung pattern None cua
    auth.decode_access_token()."""
    async with AsyncSession(engine) as session:
        result = await session.exec(select(User).where(User.username == username))
        return result.first()


async def get_user_by_id(user_id: int) -> Optional[User]:
    """Dung o get_current_user() -- token chi mang user_id (claim sub),
    can tra lai DB de lay username/kiem tra user con ton tai khong (vd
    user da bi xoa nhung token cu chua het han)."""
    async with AsyncSession(engine) as session:
        return await session.get(User, user_id)
