from sqlalchemy.ext.asyncio import create_async_engine
from repository_reader.config import Settings

settings = Settings()
engine = create_async_engine(settings.database_url)