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
    # UX citation -- Optional vi cung ly do tren: cac repo da ingest TRUOC
    # khi co field nay se co gia tri NULL cho toi khi duoc ingest lai. Luu
    # dung TEN NHANH THAT SU git da checkout luc clone (xem
    # ingest.get_default_branch()) -- KHONG doan "main"/"master", vi nhieu
    # repo cu tren GitHub van dung "master". Dung de UI (ui.py) dung link
    # truc tiep toi file tren GitHub cho tung citation.
    default_branch: Optional[str] = Field(default=None)


class Conversation(SQLModel, table=True):
    """Track 4 muc 13 -- 1 dong = 1 LUOT hoi-dap (khong phai 1 phien). Nhieu
    luot gop thanh 1 phien qua field conversation_id tu-tro (self-referencing):
    luot DAU TIEN cua 1 phien co conversation_id = chinh id cua no (gan sau
    khi insert, xem db.create_conversation_turn()); cac luot SAU trong CUNG
    phien truyen lai dung conversation_id nay. Nho vay khong can them bang
    moi -- chi dung lai bang conversations da co san (truoc gio chua dung
    toi)."""
    __tablename__ = "conversations"
    id: Optional[int] = Field(default=None, primary_key=True)
    repo_id: Optional[int] = Field(default=None, foreign_key="repos.id")
    question: str
    created_at: datetime
    # Track 4 muc 13: cau tra loi cua agent cho CHINH question nay -- truoc
    # gio bang nay chi luu question, khong luu answer (scaffolding bo quen
    # tu Track 3 muc 3), nen khong the dung lam "lich su" cho model doc lai.
    answer: str = ""
    # Nhom nhieu luot thanh 1 phien hoi-dap (xem docstring class o tren).
    # Optional vi tu luu None luc moi insert luot dau tien -- code tu gan lai
    # = id cua chinh dong do NGAY SAU KHI insert (xem db.py), nen tren thuc
    # te field nay luon co gia tri sau khi ham db tra ve.
    conversation_id: Optional[int] = Field(default=None, foreign_key="conversations.id")
    # Chu cua phien hoi-dap -- can de kiem tra quyen (1 user khong duoc doc
    # tiep phien cua nguoi khac bang cach doan conversation_id), cung
    # nguyen tac voi Repo.owner_id o tren.
    owner_id: Optional[int] = Field(default=None, foreign_key="users.id")
