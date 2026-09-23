import logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

import fastapi
import pydantic 

from fastapi import FastAPI
from pydantic import BaseModel
from repository_reader import vector_store, generation, db, ingest


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



@app.post("/repo/{repo_id}")
async def query_repo(repo_id: int, body: QueryRequest, top_k: int = 5):
    logger.info(f"repo_id={repo_id}, body={body}")
    chunks = vector_store.search_semantic(body.question, repo_id=repo_id, top_k=top_k)
    answer = generation.generate_answer(body.question, chunks)  
    return {
        "repo_id": repo_id,
        "answer": answer,
        "citations": [
            {"file": c["file"], "start_line": c["start_line"], "end_line": c["end_line"]}
            for c in chunks
        ],
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

