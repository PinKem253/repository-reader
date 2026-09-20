from sqlalchemy.ext.asyncio import create_async_engine
from repository_reader.config import Settings
import logging 

logger = logging.getLogger(__name__)

try: 
    settings = Settings()
    engine = create_async_engine(settings.database_url)
    logger.info("Create engine successfully")
except Exception as e:
    
    #logger.error("Create engine failed")
    logger.exception("Create engine failed")
    raise e
    