"""Dump e restore dell'intero DB (Admin) — vedi app/services/db_backup.py.

Protetto dal login admin (require_admin) piu' una password dedicata
(db_ops_password_hash) verificata in ogni endpoint: il dump contiene dati
personali reali (nomi/email allenatori) e il restore sovrascrive l'intero DB.
"""
import io
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.services.auth_service import require_admin, verify_password
from app.services.db_backup import create_dump, restore_dump

router = APIRouter(prefix="/admin/db", tags=["admin-db"])


class DumpRequest(BaseModel):
    password: str


def _verify_ops_password(password: str) -> None:
    if not verify_password(password, settings.db_ops_password_hash):
        raise HTTPException(status_code=403, detail="Password errata")


@router.post("/dump")
def dump_database(body: DumpRequest, _admin: str = Depends(require_admin)):
    _verify_ops_password(body.password)
    dump_bytes = create_dump()
    filename = f"ft-platform_{settings.db_name}_{datetime.now():%Y%m%d_%H%M%S}.sql"
    return StreamingResponse(
        io.BytesIO(dump_bytes),
        media_type="application/sql",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/restore")
async def restore_database(
    password: str = Form(...),
    file: UploadFile = File(...),
    _admin: str = Depends(require_admin),
):
    if not settings.allow_db_restore:
        raise HTTPException(status_code=403, detail="Restore disabilitato in questo ambiente")
    _verify_ops_password(password)
    sql_bytes = await file.read()
    restore_dump(sql_bytes)
    return {"ok": True}
