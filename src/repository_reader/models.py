from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class Repo(SQLModel, table=True):
    __tablename__ = "repos"
    id: Optional[int] = Field(default=None, primary_key=True)
    url: str
    status: str
    created_at: datetime
        
class Conversation(SQLModel, table = True):
    __tablename__ = "conversations"
    id: Optional[int] = Field(default=None, primary_key=True)
    repo_id: Optional[int] = Field(default=None, foreign_key="repos.id")
    question: str 
    created_at: datetime