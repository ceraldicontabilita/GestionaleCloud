from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.database import Database
from app.services.pagamenti_buoni import (
    COLLECTION,
    GOOD_PAYMENT_COLUMNS,
    import_rows,
    parse_csv,
    serialize_record,
)

router = APIRouter()


@router.get("")
async def list_pagamenti_buoni(
    year: int | None = Query(None, ge=2000, le=2100),
    limit: int = Query(500, ge=1, le=1000),
):
    db = Database.get_db()
    query = {"accounting_year": year} if year is not None else {}
    records = await db[COLLECTION].find(query, {"_id": 0}).sort(
        [("accounting_date", -1), ("imported_at", -1)]
    ).to_list(limit)
    return [serialize_record(record) for record in records]


@router.post("/import")
async def import_pagamenti_buoni(file: UploadFile = File(...)):
    filename = file.filename or "pagamenti-buoni.csv"
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="Pagamenti buoni: selezionare un file CSV")
    content = await file.read(50 * 1024 * 1024 + 1)
    if not content:
        raise HTTPException(status_code=422, detail="Pagamenti buoni: file vuoto")
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Pagamenti buoni: file oltre il limite massimo")
    try:
        rows, errors = parse_csv(content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = await import_rows(Database.get_db(), rows, filename, errors)
    result["columns"] = list(GOOD_PAYMENT_COLUMNS)
    return result
