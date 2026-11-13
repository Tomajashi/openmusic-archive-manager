from typing import Any, Dict, List
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.models import ImportItem, ImportProject
from backend.app.schemas import (
    ImportItemCreate,
    ImportItemOut,
    ImportItemUpdate,
    ImportProjectCreate,
    ImportProjectOut,
)
from backend.app.services.import_service import (
    ImportValidationError,
    get_template_content,
    parse_import_content,
)
from backend.app.services.logger_service import log_event

router = APIRouter(prefix="/api/v1/imports", tags=["Imports"])


@router.post("/preview")
async def preview_import_file(
    file: UploadFile | None = File(default=None),
    raw_content: str = Form(default=""),
    format_hint: str = Form(default=""),
) -> Dict[str, Any]:
    content = ""
    fmt = format_hint.strip()

    if file is not None:
        raw_bytes = await file.read()
        try:
            content = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                content = raw_bytes.decode("cp1252")
            except UnicodeDecodeError as exc:
                raise HTTPException(status_code=400, detail="File must be UTF-8 encoded text.") from exc
        if not fmt and file.filename and "." in file.filename:
            fmt = file.filename.rsplit(".", 1)[-1]
    elif raw_content:
        content = raw_content
    else:
        raise HTTPException(status_code=400, detail="Provide either an uploaded file or raw_content.")

    if not fmt:
        stripped = content.lstrip("\ufeff").lstrip()
        first_line = stripped.splitlines()[0] if stripped.splitlines() else ""
        if stripped.startswith("{") or stripped.startswith("["):
            fmt = "JSON"
        elif any(sep in first_line for sep in (",", ";", "\t")):
            fmt = "CSV"
        else:
            fmt = "YAML"

    try:
        items, warnings = parse_import_content(content, fmt)
        return {
            "format": fmt.upper(),
            "count": len(items),
            "items": [it.model_dump() for it in items],
            "warnings": warnings,
        }
    except ImportValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/templates/{fmt}")
def download_template(fmt: str) -> Response:
    content, media_type, filename = get_template_content(fmt)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/projects", response_model=List[ImportProjectOut])
def list_projects(db: Session = Depends(get_db)) -> List[ImportProject]:
    return db.query(ImportProject).order_by(ImportProject.created_at.desc()).all()


@router.post("/projects", response_model=ImportProjectOut)
def create_project(payload: ImportProjectCreate, db: Session = Depends(get_db)) -> ImportProject:
    proj = ImportProject(
        name=payload.name.strip(),
        description=payload.description.strip(),
        source_format=payload.source_format.upper(),
    )
    db.add(proj)
    db.flush()

    for it in payload.items:
        db.add(
            ImportItem(
                project_id=proj.id,
                artist=it.artist.strip(),
                album=it.album.strip(),
                track=it.track.strip(),
                year=it.year,
            )
        )

    db.commit()
    db.refresh(proj)
    log_event(
        "INFO",
        "IMPORT",
        f"Saved import project '{proj.name}' with {len(proj.items)} entries.",
        {"project_id": proj.id, "format": proj.source_format},
        db=db,
    )
    return proj


@router.get("/projects/{project_id}", response_model=ImportProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)) -> ImportProject:
    proj = db.query(ImportProject).filter(ImportProject.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    return proj


@router.delete("/projects/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)) -> Dict[str, str]:
    proj = db.query(ImportProject).filter(ImportProject.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    db.delete(proj)
    db.commit()
    return {"status": "deleted"}


@router.post("/projects/{project_id}/items", response_model=ImportItemOut)
def add_project_item(
    project_id: int,
    payload: ImportItemCreate,
    db: Session = Depends(get_db),
) -> ImportItem:
    proj = db.query(ImportProject).filter(ImportProject.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    item = ImportItem(
        project_id=project_id,
        artist=payload.artist.strip(),
        album=payload.album.strip(),
        track=payload.track.strip(),
        year=payload.year,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/items/{item_id}", response_model=ImportItemOut)
def update_project_item(
    item_id: int,
    payload: ImportItemUpdate,
    db: Session = Depends(get_db),
) -> ImportItem:
    item = db.query(ImportItem).filter(ImportItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Import item not found.")
    if payload.artist is not None:
        item.artist = payload.artist.strip()
    if payload.album is not None:
        item.album = payload.album.strip()
    if payload.track is not None:
        item.track = payload.track.strip()
    if payload.year is not None:
        item.year = payload.year
    if payload.status is not None:
        item.status = payload.status
    db.commit()
    db.refresh(item)
    return item


@router.delete("/items/{item_id}")
def delete_project_item(item_id: int, db: Session = Depends(get_db)) -> Dict[str, str]:
    item = db.query(ImportItem).filter(ImportItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Import item not found.")
    db.delete(item)
    db.commit()
    return {"status": "deleted"}
