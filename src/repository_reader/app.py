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

import asyncio
import fastapi
import pydantic
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from repository_reader import vector_store, generation, db, agent, auth, ingest
from repository_reader.models import User
# Track 4 muc 3: import task (khong phai ingest_repo() truc tiep nua --
# xem tasks.py) + celery_app (can truyen vao AsyncResult de no biet dung
# broker/backend nao ma tra cuu) + AsyncResult de tra cuu trang thai task
# theo task_id.
from repository_reader.tasks import ingest_task
from repository_reader.celery_app import celery_app
from celery.result import AsyncResult


logger = logging.getLogger(__name__)
app = FastAPI()


# ================= Track 4 muc 1 (Auth) -- Part B =================
# Dat NGAY SAU app = FastAPI() (truoc moi endpoint khac) vi Part C ben
# duoi can dung Depends(get_current_user) o cac endpoint /repos va
# /repo/{repo_id} -- default argument duoc Python danh gia ngay luc dinh
# nghia ham, nen get_current_user PHAI ton tai truoc do trong file.

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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sai username hoac password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth.create_access_token(user_id=user.id, username=user.username)
    return TokenResponse(access_token=token)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """Dependency dung cho MOI endpoint can dang nhap moi goi duoc. Day
    la noi DUY NHAT "bien" 1 token thanh 1 User object that -- endpoint
    khac chi can khai `user: User = Depends(get_current_user)`, khong tu
    decode token."""
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
        raise unauthorized
    return user


@app.get("/me")
async def read_current_user(user: User = Depends(get_current_user)):
    """Endpoint rieng de TEST Part B doc lap voi phan repo/agent."""
    return {"id": user.id, "username": user.username}


# ================= Track 4 muc 1 (Auth) -- Part C =================
# Ap dung get_current_user vao cac endpoint repo/agent that ben duoi:
# moi user chi thay/dung duoc repo cua chinh minh (Repo.owner_id).


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
    question: str
    # Track 4 muc 13 (multi-turn memory): None = cau hoi doc lap, giu nguyen
    # hanh vi cu. Co gia tri = tiep tuc 1 phien hoi-dap da co (client -- ui.py
    # -- tu luu lai conversation_id tra ve tu lan goi truoc).
    conversation_id: Optional[int] = None

# @app.post("/repo/{repo_id}")
# async def query_repo(repo_id: int, body: QueryRequest, top_k: int=5):
#     logger.info(f"repo_id={repo_id}, body={body}")
#     return {"repo_id": repo_id,
#             "body": body,
#             "top_k": top_k,
#             }


@app.post("/repo/{repo_id}")
async def query_repo(repo_id: int, body: QueryRequest, user: User = Depends(get_current_user)):
    """
    Giai doan 3: goi Agent Loop that (agent.run) thay vi pipeline co dinh
    search_semantic -> generate_answer nhu Giai doan 1/2.

    asyncio.to_thread(agent.run, ...) chay ham dong bo agent.run() trong 1
    thread rieng cua thread pool -- event loop chinh khong bi chan, cac
    request khac (vd health check, hoac cau hoi cua user khac) van duoc xu
    ly song song trong luc loop nay dang doi Gemini tra loi.

    Track 4 muc 1 Part C: kiem tra repo co ton tai VA thuoc dung user
    dang goi khong, TRUOC khi cho agent chay (tranh ton chi phi Gemini
    API cho 1 request se bi tu choi).
    """
    repo = await db.get_repo(repo_id)
    if repo is None or repo.owner_id != user.id:
        # Gop chung 2 truong hop "khong ton tai" va "ton tai nhung khong
        # phai cua ban" thanh CUNG 1 ma loi 404 -- dung nguyen tac chong
        # user enumeration da ap dung o /login (khong lo repo_id nao co
        # ton tai nhung thuoc nguoi khac).
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repo khong ton tai",
        )

    # Track 4 muc 13: neu client gui conversation_id (tiep tuc 1 phien hoi-
    # dap da co), lay lai cac luot TRUOC cua CHINH phien do de agent.run()
    # "nho" ngu canh -- luon kem owner_id khi tra cuu (cung nguyen tac 404
    # enumeration-safety o tren: khong cho doan conversation_id de doc phien
    # cua nguoi khac).
    prior_turns = None
    if body.conversation_id is not None:
        prior_turns = await db.get_conversation_turns(body.conversation_id, owner_id=user.id)
        if not prior_turns:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cuoc tro chuyen khong ton tai",
            )

    logger.info(f"repo_id={repo_id}, body={body}")
    # agent.run() gio tra ve dict {"answer": ..., "exhausted_budget": ...}
    # thay vi str thuan -- "exhausted_budget" la metadata tach rieng khoi
    # noi dung answer, de client (UI Streamlit / Swagger debug) tu quyet
    # dinh cach hien thi, thay vi nhet canh bao vao ngay trong answer.
    result = await asyncio.to_thread(agent.run, body.question, repo_id, prior_turns)

    # Luu lai LUOT nay (Track 4 muc 13) -- conversation_id=None (luot dau
    # tien cua 1 phien moi) khien db.create_conversation_turn() tu gan
    # nguoc conversation_id = id cua chinh dong nay; client nhan gia tri nay
    # ve de gui lai cho luot ke tiep.
    turn = await db.create_conversation_turn(
        repo_id=repo_id,
        owner_id=user.id,
        question=body.question,
        answer=result["answer"],
        conversation_id=body.conversation_id,
    )

    return {
        "repo_id": repo_id,
        "answer": result["answer"],
        "exhausted_budget": result["exhausted_budget"],
        "conversation_id": turn.conversation_id,
    }

@app.get("/repos")
async def get_repos(user: User = Depends(get_current_user)):
    # Track 4 muc 1 Part C: truyen owner_id=user.id -- chi tra ve repo
    # cua dung user dang goi, khong con thay repo cua nguoi khac.
    repos = await db.list_repos(owner_id=user.id)
    # UX citation: them default_branch -- ui.py can gia tri nay + url de
    # tu xay link truc tiep toi tung file/dong trich dan tren GitHub. Repo
    # ingest TRUOC khi co field nay se tra ve None (xem models.py), UI tu
    # xu ly truong hop thieu bang cach khong hien link.
    return [
        {"id": r.id, "url": r.url, "status": r.status, "default_branch": r.default_branch}
        for r in repos
    ]


class IngestRequest(BaseModel):
    url: str


@app.post("/repos")
async def create_repo_endpoint(body: IngestRequest, user: User = Depends(get_current_user)):
    # Track 4 muc 3: KHONG con await ingest.ingest_repo() truc tiep --
    # .delay() chi serialize tham so + day vao Redis (message broker) roi
    # tra ve NGAY 1 AsyncResult chua task_id, KHONG cho ingest chay o day.
    # Viec ingest that su (clone/chunk/embed) chay o TIEN TRINH WORKER
    # rieng (xem tasks.py), doc lap hoan toan voi request nay -- request
    # ket thuc trong mili-giay thay vi phai treo vai phut cho ingest xong.
    #
    # Chu y: KHONG con repo_id de tra ve ngay luc nay -- repo (va repo_id
    # cua no) chi thuc su duoc tao (db.create_repo() ben trong
    # ingest_repo()) khi WORKER chay task, chua xay ra tai thoi diem nay.
    #
    # UX hardening (2026-10-01): lam SACH url NGAY TAI DAY (truoc khi dua
    # vao Celery) -- vi 2 ly do: (1) tra 400 NGAY LAP TUC cho input ro rang
    # khong phai link GitHub, thay vi de task chay xong vai giay/phut roi
    # moi bao FAILURE qua polling; (2) gia tri "clean_url" (khong con
    # tracking parameter nhu "?fbclid=...") la ban SE DUOC LUU vao
    # Repo.url trong ingest_repo() -- phai sach tu day vi ui.py dung LAI
    # CHINH field nay de xay link GitHub citation ve sau (github_file_url()),
    # khong the de "sach luc clone, ban luc hien thi".
    try:
        clean_url = ingest.extract_github_url(body.url)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    task = ingest_task.delay(clean_url, user.id)
    return {"task_id": task.id}


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str, user: User = Depends(get_current_user)):
    """Track 4 muc 3: client (ui.py) goi lap lai endpoint nay (poll) de
    hoi "task nay toi dau roi" -- thay vi phai giu 1 ket noi HTTP mo lien
    tuc. AsyncResult tra cuu thang trong Result Backend (Redis) bang
    task_id, khong can biet gi ve worker nao da/dang chay task do.

    Khong kiem tra task nay co thuoc ve user hien tai khong (task_id la
    UUID ngau nhien, khong doan duoc, tuong duong 1 "capability token" --
    du chap nhan duoc cho quy mo portfolio nay; kiem tra chat hon se can
    luu owner_id cua task o dau do, ngoai pham vi muc nay).
    """
    result = AsyncResult(task_id, app=celery_app)
    response = {"task_id": task_id, "status": result.status}
    if result.status == "SUCCESS":
        response["repo_id"] = result.result
    elif result.status == "FAILURE":
        # str(result.result): result.result luc FAILURE la chinh exception
        # object (vd ValueError tu ingest_repo() khi all_chunks rong) --
        # convert sang string de tra ve duoc qua JSON.
        response["error"] = str(result.result)
    return response
