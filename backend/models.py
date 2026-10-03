from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class Credentials(BaseModel):
    model_config=ConfigDict(extra='forbid')
    username: str=Field(min_length=3,max_length=40,pattern=r'^[a-zA-Z0-9_.-]+$')
    password: str=Field(min_length=12,max_length=128)

class RoleChange(BaseModel):
    model_config=ConfigDict(extra='forbid')
    role: Literal['viewer','editor','admin']

class RecordOut(BaseModel):
    model_config=ConfigDict(extra='allow')
    id: int
    version: int
    created_at: str

class Page(BaseModel):
    items: list[RecordOut]
    total: int
    limit: int
    offset: int
