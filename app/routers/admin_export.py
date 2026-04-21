"""Endpoint di download per file generati in /app/uploads/ (export CSV/JSON/PDF)."""
import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/admin/export", tags=["Admin Export"])

ALLOWED_DIRS = ["/app/uploads"]


def _safe_path(filename: str) -> str:
    """Anti path-traversal: solo file sotto /app/uploads/."""
    # Blocca separatori e traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Filename non valido")
    for base in ALLOWED_DIRS:
        candidate = os.path.realpath(os.path.join(base, filename))
        if candidate.startswith(base + os.sep) and os.path.exists(candidate):
            return candidate
    raise HTTPException(404, "File non trovato")


@router.get("/{filename}")
async def download_export(filename: str):
    path = _safe_path(filename)
    ext = os.path.splitext(filename)[1].lower()
    media = {
        ".csv": "text/csv",
        ".json": "application/json",
        ".pdf": "application/pdf",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }.get(ext, "application/octet-stream")
    return FileResponse(path, media_type=media, filename=filename)


@router.get("")
async def lista_export():
    """Lista file disponibili in /app/uploads/ (utility per UI)."""
    out = []
    for base in ALLOWED_DIRS:
        if not os.path.isdir(base):
            continue
        for name in os.listdir(base):
            p = os.path.join(base, name)
            if os.path.isfile(p):
                st = os.stat(p)
                out.append({
                    "filename": name,
                    "size": st.st_size,
                    "modified": st.st_mtime,
                    "url": f"/api/admin/export/{name}",
                })
    return sorted(out, key=lambda x: x["modified"], reverse=True)
