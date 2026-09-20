import logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

import fastapi
import pydantic 

from fastapi import FastAPI
from pydantic import BaseModel

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

@app.post("/repo/{repo_id}")
async def query_repo(repo_id: int, body: QueryRequest, top_k: int=5):
    logger.info(f"repo_id={repo_id}, body={body}")
    return {"repo_id": repo_id,
            "body": body,
            "top_k": top_k,
            }

