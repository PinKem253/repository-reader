import pydantic_settings
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings): 
    llm_api_key: str        
    model_config = SettingsConfigDict(
        env_file = '.env'
    )

if __name__ == "__main__":
    pass
        
        