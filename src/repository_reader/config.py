import pydantic_settings
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    llm_api_key: str
    database_url: str

    # --- Track 4 muc 1 (Auth) ---
    # jwt_secret_key: BAT BUOC phai co trong .env, KHONG co default -- dung
    # nguyen tac Scope/B4 da hoc: secret khong hardcode trong code. Neu
    # thieu, Settings() se raise ValidationError ngay luc import, giong
    # het cach llm_api_key/database_url dang hoat dong.
    jwt_secret_key: str
    # HS256 = ky bang 1 khoa bi mat duy nhat (symmetric) -- du dung vi chi
    # co dung 1 server vua tu ky vua tu verify token, khong can cap khoa
    # public/private (RS256) nhu khi nhieu service doc lap can verify.
    jwt_algorithm: str = "HS256"
    # Token het han sau 24h -- qua thoi gian nay phai dang nhap lai du token
    # cu chua bi lo, giam thiet hai neu token bi ro ri.
    access_token_expire_minutes: int = 1440

    model_config = SettingsConfigDict(
        env_file = '.env'
    )

if __name__ == "__main__":
    pass

settings = Settings()
