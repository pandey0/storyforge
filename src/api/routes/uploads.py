from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter(prefix="/cases", tags=["uploads"])

_ALLOWED_SUFFIXES = {".pdf", ".txt", ".md", ".jpg", ".jpeg", ".png", ".webp"}
_MAX_BYTES = 50 * 1024 * 1024  # 50 MB


@router.post("/{slug}/uploads")
async def upload_research_file(slug: str, file: UploadFile = File(...)):
    """Upload a research file (PDF, image, or text) for a case."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            400,
            f"Unsupported file type {suffix!r}. Allowed: {sorted(_ALLOWED_SUFFIXES)}",
        )

    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(400, f"File too large ({len(content) // 1024 // 1024} MB). Max 50 MB.")

    safe_name = "".join(
        c if (c.isalnum() or c in "-_.") else "_"
        for c in (file.filename or "upload")
    )
    uploads_dir = Path(f"data/cases/{slug}/uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)

    dest = uploads_dir / safe_name
    dest.write_bytes(content)

    return {"filename": safe_name, "size": len(content), "type": suffix.lstrip(".")}


@router.get("/{slug}/uploads")
async def list_uploads(slug: str):
    """List uploaded research files for a case."""
    uploads_dir = Path(f"data/cases/{slug}/uploads")
    if not uploads_dir.exists():
        return []
    return [
        {"filename": f.name, "size": f.stat().st_size, "type": f.suffix.lstrip(".")}
        for f in sorted(uploads_dir.iterdir())
        if f.is_file()
    ]


@router.delete("/{slug}/uploads/{filename}")
async def delete_upload(slug: str, filename: str):
    """Delete an uploaded research file."""
    if "/" in filename or "\\" in filename:
        raise HTTPException(400, "Invalid filename")
    path = Path(f"data/cases/{slug}/uploads/{filename}")
    if not path.exists():
        raise HTTPException(404, f"File {filename!r} not found")
    path.unlink()
    return {"deleted": True, "filename": filename}
