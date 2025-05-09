from sqlmodel import SQLModel, Field
from typing import Optional

# Define the User model
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str
    hashed_password: str

# Define the Employee model
class Employee(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    position: str

# Define the AgentDecomposition model
class AgentDecomposition(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    document_url: Optional[str] = Field(default=None, max_length=500)
    date: Optional[str] = Field(default=None)
    document_id: Optional[int] = Field(default=None)
    decomposition: Optional[str] = Field(default=None)
    source: Optional[str] = Field(default=None, max_length=50)

# Define the AgentLog model
class AgentLog(SQLModel, table=True):
    Id: Optional[int] = Field(default=None, primary_key=True)
    StartTime: Optional[str] = Field(default=None)
    Status: Optional[str] = Field(default=None, max_length=50)
    EndTime: Optional[str] = Field(default=None)
    LastDocumentId: Optional[int] = Field(default=None)
    ErrorLog: Optional[str] = Field(default=None)
    Source: Optional[str] = Field(default=None, max_length=50)