"""
auth.py -- Co che loi cua Authentication (Track 4 muc 1, Part A).

Phan nay CHUA co endpoint (signup/login) -- do la Part B/C, se noi vao
app.py o buoc sau. O day chi co 2 nhom co che DOC LAP, tach rieng de
hieu/test tung phan truoc khi rap vao HTTP:

1. Hash/verify password -- goi thang thu vien `bcrypt`, KHONG qua
   passlib. Ly do cu the: passlib 1.7.4 (ban moi nhat, dot 2026) co bug
   tuong thich voi bcrypt >=4.1 (bcrypt da go bo module noi bo
   `__about__` ma passlib doc de lay version, gay AttributeError ngay
   lan hash dau tien) -- goi thang `bcrypt.hashpw`/`bcrypt.checkpw` tranh
   duoc lop phu thuoc trung gian nay, it code hon cho dung 1 viec can lam.
2. Tao/giai ma JWT access token -- dung `pyjwt`. Token la STATELESS: KHONG
   luu gi vao DB ca -- ai dang giu 1 token con hop le (dung chu ky, chua
   het han) deu duoc he thong coi la da dang nhap, dung dinh nghia JWT.
"""

import jwt  # PyJWT
import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Optional

from repository_reader.config import settings


# ---------- Phan 1: Password hashing ----------

def hash_password(plain_password: str) -> str:
    """Bam password bang bcrypt -- bcrypt.gensalt() tu sinh 1 salt NGAU
    NHIEN moi lan goi, nen 2 user cung dung 1 password van ra 2 hash khac
    nhau (chong rainbow-table attack). Tra ve str (khong phai bytes) de
    luu thang vao cot hashed_password kieu str cua model User."""
    hashed_bytes = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt())
    return hashed_bytes.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """So khop password nguoi dung nhap luc login voi hash da luu trong
    DB. KHONG BAO GIO tu hash lai roi so == -- bcrypt.checkpw tu doc salt
    da nam san trong hashed_password de bam lai dung cach truoc khi so
    khop, day la ly do phai dung ham nay thay vi tu viet so sanh string."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


# ---------- Phan 2: JWT access token ----------

def create_access_token(user_id: int, username: str) -> str:
    """Tao access token. Payload (con goi la 'claims') gom:
    - sub (subject, chuan JWT): user_id, dang str -- day la thu duoc
      dung o Part D de loc owner_id, KHONG duoc tin tuong bat ky field
      nao khac trong request de xac dinh danh tinh user.
    - username: chi de tien debug/hien thi, khong dung de phan quyen.
    - exp (expiration, chuan JWT): thu vien jwt tu kiem tra het han khi
      decode, khong can tu so sanh datetime tay."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {"sub": str(user_id), "username": username, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[dict]:
    """Giai ma + tu dong verify chu ky + verify het han. Tra ve None neu
    token sai chu ky / het han / sai dinh dang -- KHONG raise loi o day.
    Nguoi goi ham nay (Part B: dependency get_current_user trong app.py)
    tu quyet dinh bien None thanh HTTPException 401 -- tach rach "giai ma
    token" (logic thuan) khoi "tra loi HTTP" (concern cua tang API)."""
    try:
        return jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError:
        return None
