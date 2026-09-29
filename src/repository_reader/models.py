from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class User(SQLModel, table=True):
    """Track 4 muc 1 (Auth) -- 1 dong = 1 tai khoan dang nhap that.
    KHONG BAO GIO luu password tho -- chi luu hashed_password (xem
    auth.py: hash_password() luc signup, verify_password() luc login)."""
    __tablename__ = "users"
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    hashed_password: str
    created_at: datetime


class Repo(SQLModel, table=True):
    __tablename__ = "repos"
    id: Optional[int] = Field(default=None, primary_key=True)
    url: str
    status: str
    created_at: datetime
    # Track 4 muc 1: Optional vi cac repo NGAY TRUOC KHI CO AUTH (vd
    # repo_id=6/9/13, ingest tu Giai doan 1-3) khong co owner -- repo MOI
    # ingest sau khi noi Auth vao app.py (Part D) se luon duoc set
    # owner_id, chi de nullable o tang DB de khong pha du lieu cu.
    owner_id: Optional[int] = Field(default=None, foreign_key="users.id")


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"
    id: Optional[int] = Field(default=None, primary_key=True)
    repo_id: Optional[int] = Field(default=None, foreign_key="repos.id")
    question: str
    created_at: datetime
