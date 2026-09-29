import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True,  # ep ghi de handler cu (uvicorn co the da tu cau hinh logging
                 # truoc khi app.py duoc import) -- dam bao log cua minh luon
                 # hien thi, bat ke thu tu khoi tao voi uvicorn
)

# Thu vien ben thu 3 (httpx goi Gemini, httpcore ben duoi httpx,
# huggingface_hub/FlagEmbedding luc load embedding model) tu log rat nhieu
# dong rieng cua chung (connect_tcp, send_request_headers, HTTP Request...)
# -- khong lien quan gi toi log ReAct cua agent.py, chi lam roi terminal.
# Ep cac logger nay len WARNING de terminal chi con log CUA MINH.
for _noisy_logger in ("httpx", "httpcore", "urllib3", "huggingface_hub", "FlagEmbedding"):
    logging.getLogger(_noisy_logger).setLevel(logging.WARNING)

import fastapi
import pydantic

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from repository_reader import vector_store, generation, db, ingest, auth
from repository_reader.models import User


logger = logging.getLogger(__name__)
app = FastAPI()

@app.get("/health")
async def read_health():
    return {"status": "ok"}

@app.get("/")
async def global_status():
    return {"status": "global status"}

class post_echo(BaseModel):
    message:str

@app.post("/echo")
async def read_message(item: post_echo):
    return {"message": item.message}


class ItemOut(BaseModel):
    item_id: int

@app.get("/items/{item_id}", response_model=ItemOut)
async def retrieve_id(item_id: int):
    return {"item_id": item_id, "note": "test"}

@app.get("/items")
async def query_retrieve_id(limit: int):
    return {"limit": limit}

class QueryRequest(BaseModel):
    question:str

# @app.post("/repo/{repo_id}")
# async def query_repo(repo_id: int, body: QueryRequest, top_k: int=5):
#     logger.info(f"repo_id={repo_id}, body={body}")
#     return {"repo_id": repo_id,
#             "body": body,
#             "top_k": top_k,
#             }



import asyncio
from repository_reader import vector_store, generation, db, ingest, agent  # them agent


@app.post("/repo/{repo_id}")
async def query_repo(repo_id: int, body: QueryRequest):
    """
    Giai doan 3: goi Agent Loop that (agent.run) thay vi pipeline co dinh
    search_semantic -> generate_answer nhu Giai doan 1/2.

    asyncio.to_thread(agent.run, ...) chay ham dong bo agent.run() trong 1
    thread rieng cua thread pool -- event loop chinh khong bi chan, cac
    request khac (vd health check, hoac cau hoi cua user khac) van duoc xu
    ly song song trong luc loop nay dang doi Gemini tra loi.
    """
    logger.info(f"repo_id={repo_id}, body={body}")
    # agent.run() gio tra ve dict {"answer": ..., "exhausted_budget": ...}
    # thay vi str thuan -- "exhausted_budget" la metadata tach rieng khoi
    # noi dung answer, de client (UI Streamlit / Swagger debug) tu quyet
    # dinh cach hien thi, thay vi nhet canh bao vao ngay trong answer.
    result = await asyncio.to_thread(agent.run, body.question, repo_id)
    return {
        "repo_id": repo_id,
        "answer": result["answer"],
        "exhausted_budget": result["exhausted_budget"],
    }

@app.get("/repos")
async def get_repos():
    repos = await db.list_repos()
    return [{"id": r.id, "url": r.url, "status": r.status} for r in repos]


class IngestRequest(BaseModel):
    url: str


@app.post("/repos")
async def create_repo_endpoint(body: IngestRequest):
    repo_id = await ingest.ingest_repo(body.url)
    return {"repo_id": repo_id}


# ================= Track 4 muc 1 (Auth) -- Part B =================
# Signup + Login + dependency get_current_user. Chua dung toi
# /repos hay /repo/{repo_id} o day (Part D moi ap dung filter owner_id
# vao 2 endpoint do) -- Part B chi lo dung 1 duong: tao tai khoan -> dang
# nhap -> nhan token -> goi 1 endpoint test rieng (/me) de xac nhan token
# hop le, tach biet hoan toan voi logic repo/agent da co.

class SignupRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@app.post("/signup")
async def signup(body: SignupRequest):
    """Tao tai khoan moi. KHONG tu dong dang nhap luon (khong tra token o
    day) -- dung quy uoc OAuth2 chuan: signup va login la 2 buoc tach
    biet, chi /login moi phat hanh token."""
    existing = await db.get_user_by_username(body.username)
    if existing is not None:
        # 400 (Bad Request), KHONG phai 401 -- day la loi INPUT cua nguoi
        # dung (username da bi trung), khong phai loi xac thuc danh tinh.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username da ton tai",
        )
    hashed = auth.hash_password(body.password)
    user_id = await db.create_user(body.username, hashed)
    return {"id": user_id, "username": body.username}


@app.post("/login", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """OAuth2PasswordRequestForm (can python-multipart de FastAPI parse
    duoc) bat request phai gui DANG FORM voi dung 2 field ten
    'username'/'password' -- doi lai, FastAPI tu ve duoc khung dang nhap
    that trong /docs (nut 'Authorize'), khong can tu viet form test tay."""
    user = await db.get_user_by_username(form_data.username)
    if user is None or not auth.verify_password(form_data.password, user.hashed_password):
        # Co y KHONG noi ro la sai username hay sai password rieng --
        # gop chung 1 thong bao de tranh lo thong tin "username nay co
        # ton tai trong he thong hay khong" (chong user enumeration).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sai username hoac password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth.create_access_token(user_id=user.id, username=user.username)
    return TokenResponse(access_token=token)


# tokenUrl="login" chi de /docs biet ve dung nut "Authorize" tro toi dau --
# KHONG tu goi request nao ca. FastAPI tu doc header
# "Authorization: Bearer <token>" cua moi request can dependency nay, tu
# raise 401 san neu thieu han header truoc khi get_current_user duoc goi.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """Dependency dung cho MOI endpoint can dang nhap moi goi duoc (Part D
    se ap dung tiep vao /repos, /repo/{repo_id}). Day la noi DUY NHAT
    "bien" 1 token thanh 1 User object that -- endpoint khac chi can khai
    `user: User = Depends(get_current_user)`, khong tu decode token."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token khong hop le hoac da het han",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = auth.decode_access_token(token)
    if payload is None:
        raise unauthorized
    user = await db.get_user_by_id(int(payload["sub"]))
    if user is None:
        # Token con han nhung user da bi xoa khoi DB -- truong hop hiem
        # nhung van phai xu ly, khong duoc gia dinh user luon ton tai.
        raise unauthorized
    return user


@app.get("/me")
async def read_current_user(user: User = Depends(get_current_user)):
    """Endpoint rieng de TEST Part B doc lap voi phan repo/agent da co.
    Goi duoc endpoint nay voi 1 token hop le tuc la ca 3 buoc
    signup/login/verify da chay dung tu dau toi cuoi."""
    return {"id": user.id, "username": user.username}
