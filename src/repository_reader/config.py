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

    # --- Track 4 muc 3 (Async task queue -- Celery) ---
    # redis_url: dung LAM CA 2 vai tro -- message broker (hang doi task
    # giua app.py va celery worker) VA result backend (noi luu trang thai/
    # ket qua task sau khi worker chay xong). Co default (khac
    # database_url/jwt_secret_key khong co default) vi Redis local luc dev
    # luon co dia chi co dinh nay -- khac connection string DB (co password
    # that) hay secret key (bat buoc random rieng tung nguoi).
    redis_url: str = "redis://localhost:6379/0"

    # --- Track 4 muc 6 (Observability -- Langfuse tracing + cost tracking) ---
    # Co default rong "" (KHAC llm_api_key/database_url/jwt_secret_key --
    # nhung field do khong co default vi la dependency BAT BUOC app moi chay
    # duoc). Langfuse chi la tool QUAN SAT, khong phai nen tang -- app van
    # phai chay binh thuong du chua dien key nay. agent.py tu kiem tra 2
    # field key co rong hay khong de quyet dinh BAT/TAT tracing, khong de
    # Settings() raise loi luc import nhu jwt_secret_key dang lam.
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = "https://cloud.langfuse.com"

    model_config = SettingsConfigDict(
        env_file = '.env'
    )

if __name__ == "__main__":
    pass

settings = Settings()
