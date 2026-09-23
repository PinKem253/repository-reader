from sqlalchemy.ext.asyncio import create_async_engine
from repository_reader.config import Settings
import logging 
from datetime import datetime
from sqlmodel.ext.asyncio.session import AsyncSession
from repository_reader.models import Repo
from sqlmodel import select

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