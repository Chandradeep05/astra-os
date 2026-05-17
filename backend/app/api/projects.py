from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session, select, desc
from typing import List
from app.schemas.project import Project, ProjectCreate, ProjectUpdate
from app.models.project import ProjectModel
from app.db import get_session
import uuid
from datetime import datetime
import json

router = APIRouter()

@router.get("/", response_model=List[Project])
async def list_projects(session: Session = Depends(get_session)):
    statement = select(ProjectModel).order_by(desc(ProjectModel.last_accessed_at))
    projects = session.exec(statement).all()
    return [Project(
        id=p.id, 
        name=p.name, 
        description=p.description, 
        project_type=p.project_type,
        created_at=p.created_at, 
        last_accessed_at=p.last_accessed_at,
        active=p.active,
        metadata=json.loads(p.metadata_json) if p.metadata_json else None,
        history=[]  # Don't load full history for listing — loaded on demand via get_project
    ) for p in projects]

@router.post("/", response_model=Project)
async def create_project(project_in: ProjectCreate, session: Session = Depends(get_session)):
    now = datetime.utcnow()
    project = ProjectModel(
        id=str(uuid.uuid4()),
        name=project_in.name,
        description=project_in.description,
        project_type=project_in.project_type or "general",
        metadata_json=json.dumps(project_in.metadata) if project_in.metadata else None,
        history_json=json.dumps(project_in.history) if project_in.history else "[]",
        created_at=now,
        last_accessed_at=now,
        active=True
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return Project(
        id=project.id,
        name=project.name,
        description=project.description,
        project_type=project.project_type,
        created_at=project.created_at,
        last_accessed_at=project.last_accessed_at,
        active=project.active,
        metadata=project_in.metadata,
        history=project_in.history
    )

@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: str, session: Session = Depends(get_session)):
    project = session.get(ProjectModel, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return Project(
        id=project.id,
        name=project.name,
        description=project.description,
        project_type=project.project_type,
        created_at=project.created_at,
        last_accessed_at=project.last_accessed_at,
        active=project.active,
        metadata=json.loads(project.metadata_json) if project.metadata_json else None,
        history=json.loads(project.history_json) if project.history_json else []
    )

@router.patch("/{project_id}", response_model=Project)
async def update_project(project_id: str, project_in: ProjectUpdate, session: Session = Depends(get_session)):
    project = session.get(ProjectModel, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    update_data = project_in.dict(exclude_unset=True)
    if "name" in update_data: project.name = update_data["name"]
    if "description" in update_data: project.description = update_data["description"]
    if "project_type" in update_data: project.project_type = update_data["project_type"]
    if "active" in update_data: project.active = update_data["active"]
    if "metadata" in update_data: project.metadata_json = json.dumps(update_data["metadata"])
    if "history" in update_data: project.history_json = json.dumps(update_data["history"])
    
    project.last_accessed_at = datetime.utcnow()
    session.add(project)
    session.commit()
    session.refresh(project)
    
    return Project(
        id=project.id,
        name=project.name,
        description=project.description,
        project_type=project.project_type,
        created_at=project.created_at,
        last_accessed_at=project.last_accessed_at,
        active=project.active,
        metadata=json.loads(project.metadata_json) if project.metadata_json else None,
        history=json.loads(project.history_json) if project.history_json else []
    )

@router.delete("/{project_id}")
async def delete_project(project_id: str, session: Session = Depends(get_session)):
    project = session.get(ProjectModel, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    session.delete(project)
    session.commit()
    return {"status": "success"}
