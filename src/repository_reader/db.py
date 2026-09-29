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

async def create_repo(url: str) -> int:
    async with AsyncSession(engine) as session:
        repo = Repo(url = url, status = "pending", created_at = datetime.utcnow())
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
        
    
async def list_repos() -> list[Repo]:
    async with AsyncSession(engine) as session:
        result = await session.exec(select(Repo))
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
