from fastapi import APIRouter

from app.services.zotero_scanner import scan_storage

router = APIRouter(prefix="/scan", tags=["scan"])


@router.post("")
def scan():
    return scan_storage()
