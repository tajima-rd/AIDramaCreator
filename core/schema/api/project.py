# core/schema/api/project.py
from pydantic import BaseModel


class ProjectCreateRequest(BaseModel):
    path: str
    name: str

class ProjectOpenRequest(BaseModel):
    path: str

class ProjectUpdatePathRequest(BaseModel):
    path: str

class ProjectPropertiesUpdateRequest(BaseModel):
    name: str
    server_base_url: str

class ProjectSaveAsRequest(BaseModel):
    path: str
    name: str | None = None

class ProjectInfo(BaseModel):
    protocol_version: str
    project_id: str
    name: str
    created_at: str
    modified_at: str
    server_base_url: str
    path: str

class ProjectListResult(BaseModel):
    projects: list[ProjectInfo]
