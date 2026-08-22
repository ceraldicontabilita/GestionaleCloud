"""API nativa per ricezione merce, lotti e tracciabilita HACCP."""
from datetime import date
from typing import Any, Dict, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.database import Database
from app.db_collections import (
    COLL_HACCP_EQUIPMENT,
    COLL_HACCP_EXPECTATIONS,
    COLL_HACCP_LOTS,
    COLL_HACCP_PRODUCTIONS,
    COLL_HACCP_PURCHASE_LINES,
    COLL_HACCP_RECIPES,
    COLL_HACCP_REGISTER_ENTRIES,
)
from app.services.audit_logger import log_evento
from app.services.haccp_operations import (
    create_register_entry,
    domain_overview,
    list_register_entries,
    register_catalog,
    register_production,
    resolve_register_entry,
    save_equipment,
    save_recipe,
    update_equipment,
)
from app.services.haccp_traceability import (
    create_lot_from_purchase_line,
    haccp_overview,
    lot_trace,
    preview_invoice_sync,
    record_lot_movement,
    sync_invoice_lines,
)
from app.utils.dependencies import get_current_admin_user, get_current_user
from app.utils.ruoli import richiedi_scrittura

router = APIRouter()


class InvoiceSyncRequest(BaseModel):
    anno: int = Field(default=2026, ge=2018, le=2100)
    dry_run: bool = True


class LotCreateRequest(BaseModel):
    purchase_line_id: str = Field(min_length=1)
    lot_number: str = Field(min_length=1, max_length=120)
    expiry_date: str
    quantity_received: str = Field(min_length=1)
    received_date: str = Field(default_factory=lambda: date.today().isoformat())


class LotMovementRequest(BaseModel):
    movement_type: Literal["CONSUMO", "SCARTO"]
    quantity: str = Field(min_length=1)
    reason: str = Field(default="", max_length=500)
    client_operation_id: str = Field(min_length=8, max_length=120)


class RegisterEntryRequest(BaseModel):
    register_type: str = Field(min_length=1, max_length=80)
    event_date: str = Field(default_factory=lambda: date.today().isoformat())
    subject: str = Field(min_length=1, max_length=300)
    operator: str = Field(default="", max_length=200)
    client_operation_id: str = Field(min_length=8, max_length=160)
    value: str | None = None
    unit: str = Field(default="", max_length=30)
    threshold_min: str | None = None
    threshold_max: str | None = None
    equipment_id: str = Field(default="", max_length=160)
    compliant: bool | None = None
    corrective_action: str = Field(default="", max_length=1000)
    notes: str = Field(default="", max_length=2000)
    extra: dict[str, Any] = Field(default_factory=dict)


class ResolveRegisterRequest(BaseModel):
    corrective_action: str = Field(min_length=1, max_length=1000)
    verification_notes: str = Field(default="", max_length=2000)


class EquipmentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    equipment_type: str = Field(min_length=1, max_length=80)
    threshold_min: str | None = None
    threshold_max: str | None = None
    location: str = Field(default="", max_length=300)
    client_operation_id: str = Field(min_length=8, max_length=160)


class EquipmentUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    threshold_min: str | None = None
    threshold_max: str | None = None
    location: str | None = Field(default=None, max_length=300)
    active: bool | None = None


class RecipeIngredient(BaseModel):
    product_id: str = Field(default="", max_length=160)
    name: str = Field(min_length=1, max_length=300)
    quantity: str = Field(min_length=1, max_length=60)
    unit: str = Field(default="g", max_length=30)
    allergens: list[str] = Field(default_factory=list)


class RecipeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    department: str = Field(default="GENERALE", max_length=100)
    yield_quantity: str = Field(min_length=1, max_length=60)
    yield_unit: str = Field(default="pezzi", max_length=30)
    ingredients: list[RecipeIngredient] = Field(min_length=1, max_length=200)
    instructions: str = Field(default="", max_length=20000)
    allergens: list[str] = Field(default_factory=list)
    shelf_life_days: int | None = Field(default=None, ge=0, le=3650)
    storage: str = Field(default="", max_length=1000)
    client_operation_id: str = Field(min_length=8, max_length=160)


class ProductionLotAllocation(BaseModel):
    lot_id: str = Field(min_length=1, max_length=160)
    quantity: str = Field(min_length=1, max_length=60)


class ProductionRequest(BaseModel):
    recipe_id: str = Field(min_length=1, max_length=160)
    production_date: str = Field(default_factory=lambda: date.today().isoformat())
    quantity: str = Field(min_length=1, max_length=60)
    unit: str = Field(default="", max_length=30)
    lot_number: str = Field(default="", max_length=120)
    ingredient_lots: list[ProductionLotAllocation] = Field(default_factory=list, max_length=200)
    operator: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=2000)
    production_kind: str = Field(default="STANDARD", max_length=80)
    recovery_from_id: str = Field(default="", max_length=160)
    client_operation_id: str = Field(min_length=8, max_length=160)


def _actor(user: Dict[str, Any]) -> str:
    return user.get("email") or user.get("user_id") or "utente"


@router.get("/overview")
async def overview(
    anno: int = Query(2026, ge=2018, le=2100),
    _user: Dict[str, Any] = Depends(get_current_user),
):
    db = Database.get_db()
    return {**await haccp_overview(db, anno), **await domain_overview(db, anno)}


@router.get("/sync-preview")
async def sync_preview(
    anno: int = Query(2026, ge=2018, le=2100),
    _user: Dict[str, Any] = Depends(get_current_user),
):
    result = await preview_invoice_sync(Database.get_db(), anno)
    result.pop("_new_items", None)
    return result


@router.post("/sync-invoices")
async def sync_invoices(
    payload: InvoiceSyncRequest,
    admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    db = Database.get_db()
    result = await sync_invoice_lines(db, payload.anno, dry_run=payload.dry_run)
    if not payload.dry_run:
        await log_evento(
            modulo="haccp",
            azione="fatture_sincronizzate",
            entita_id=str(payload.anno),
            entita_collection=COLL_HACCP_PURCHASE_LINES,
            db=db,
            nuovo_stato=result,
            fonte="invoices",
            utente=admin.get("email") or admin.get("user_id") or "admin",
            dettaglio=f"Sincronizzate righe merce dalle fatture {payload.anno}",
        )
    return result


@router.get("/purchase-lines")
async def purchase_lines(
    anno: int = Query(2026, ge=2018, le=2100),
    stato: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    _user: Dict[str, Any] = Depends(get_current_user),
):
    query: dict[str, Any] = {"anno": anno}
    if stato:
        query["status"] = stato
    collection = Database.get_db()[COLL_HACCP_PURCHASE_LINES]
    total = await collection.count_documents(query)
    items = await collection.find(query, {"_id": 0}).sort("invoice_date", -1).skip(skip).limit(limit).to_list(limit)
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get("/lots")
async def lots(
    anno: int = Query(2026, ge=2018, le=2100),
    limit: int = Query(100, ge=1, le=500),
    _user: Dict[str, Any] = Depends(get_current_user),
):
    query = {"received_date": {"$regex": f"^{anno}-"}}
    collection = Database.get_db()[COLL_HACCP_LOTS]
    items = await collection.find(query, {"_id": 0}).sort("expiry_date", 1).limit(limit).to_list(limit)
    return {"items": items, "total": await collection.count_documents(query)}


@router.post("/lots")
async def create_lot(
    payload: LotCreateRequest,
    user: Dict[str, Any] = Depends(richiedi_scrittura),
):
    db = Database.get_db()
    try:
        lot, created = await create_lot_from_purchase_line(
            db,
            purchase_line_id=payload.purchase_line_id,
            lot_number=payload.lot_number,
            expiry_date=payload.expiry_date,
            quantity_received=payload.quantity_received,
            received_date=payload.received_date,
            user_id=user.get("email") or user.get("user_id") or "utente",
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if created:
        await log_evento(
            modulo="haccp",
            azione="lotto_ricevuto",
            entita_id=lot["canonical_id"],
            entita_collection=COLL_HACCP_LOTS,
            db=db,
            nuovo_stato=lot,
            fonte="ricezione_merce",
            utente=user.get("email") or user.get("user_id") or "utente",
            dettaglio=f"Lotto {lot['lot_number']} collegato alla fattura {lot['invoice_number']}",
        )
    return {"created": created, "lot": lot}


@router.get("/lots/{lot_id}/trace")
async def get_lot_trace(
    lot_id: str,
    _user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        return await lot_trace(Database.get_db(), lot_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/lots/{lot_id}/movements")
async def create_lot_movement(
    lot_id: str,
    payload: LotMovementRequest,
    user: Dict[str, Any] = Depends(richiedi_scrittura),
):
    db = Database.get_db()
    try:
        movement, lot, created = await record_lot_movement(
            db,
            lot_id=lot_id,
            movement_type=payload.movement_type,
            quantity=payload.quantity,
            reason=payload.reason,
            client_operation_id=payload.client_operation_id,
            user_id=user.get("email") or user.get("user_id") or "utente",
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if created:
        await log_evento(
            modulo="haccp",
            azione="lotto_scaricato",
            entita_id=lot_id,
            entita_collection=COLL_HACCP_LOTS,
            db=db,
            nuovo_stato={"movement": movement, "lot": lot},
            fonte="movimento_lotto",
            utente=user.get("email") or user.get("user_id") or "utente",
            dettaglio=f"{movement['movement_type']} {movement['quantity']} {movement['unit']}",
        )
    return {"created": created, "movement": movement, "lot": lot}


@router.get("/register-types")
async def register_types(_user: Dict[str, Any] = Depends(get_current_user)):
    return {"items": register_catalog()}


@router.get("/registers")
async def registers(
    anno: int = Query(2026, ge=2018, le=2100),
    tipo: str = "",
    limit: int = Query(500, ge=1, le=2000),
    _user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        items = await list_register_entries(
            Database.get_db(), year=anno, register_type=tipo, limit=limit
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"items": items, "total": len(items)}


@router.post("/registers")
async def create_register(
    payload: RegisterEntryRequest,
    user: Dict[str, Any] = Depends(richiedi_scrittura),
):
    db = Database.get_db()
    try:
        entry, created = await create_register_entry(
            db,
            **payload.model_dump(),
            user_id=_actor(user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if created:
        await log_evento(
            modulo="haccp",
            azione="controllo_registrato",
            entita_id=entry["canonical_id"],
            entita_collection=COLL_HACCP_REGISTER_ENTRIES,
            db=db,
            nuovo_stato=entry,
            fonte="registro_haccp",
            utente=_actor(user),
            dettaglio=f"{entry['register_type']}: {entry['subject']}",
        )
    return {"created": created, "entry": entry}


@router.post("/registers/{entry_id}/resolve")
async def resolve_register(
    entry_id: str,
    payload: ResolveRegisterRequest,
    user: Dict[str, Any] = Depends(richiedi_scrittura),
):
    db = Database.get_db()
    try:
        entry = await resolve_register_entry(
            db,
            entry_id=entry_id,
            corrective_action=payload.corrective_action,
            verification_notes=payload.verification_notes,
            user_id=_actor(user),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await log_evento(
        modulo="haccp",
        azione="non_conformita_risolta",
        entita_id=entry_id,
        entita_collection=COLL_HACCP_REGISTER_ENTRIES,
        db=db,
        nuovo_stato=entry,
        fonte="azione_correttiva",
        utente=_actor(user),
        dettaglio=payload.corrective_action,
    )
    return {"entry": entry}


@router.get("/expectations")
async def expectations(
    anno: int = Query(2026, ge=2018, le=2100),
    aperte: bool = True,
    limit: int = Query(500, ge=1, le=2000),
    _user: Dict[str, Any] = Depends(get_current_user),
):
    query: dict[str, Any] = {"anno": anno}
    if aperte:
        query["status"] = {"$in": ["ATTESO", "DA_VERIFICARE", "IN_ELABORAZIONE", "ERRORE"]}
    collection = Database.get_db()[COLL_HACCP_EXPECTATIONS]
    items = await collection.find(query, {"_id": 0}).sort("data", -1).limit(limit).to_list(limit)
    return {"items": items, "total": len(items)}


@router.get("/equipment")
async def equipment(_user: Dict[str, Any] = Depends(get_current_user)):
    collection = Database.get_db()[COLL_HACCP_EQUIPMENT]
    items = await collection.find({"active": {"$ne": False}}, {"_id": 0}).sort("name", 1).limit(500).to_list(500)
    return {"items": items, "total": len(items)}


@router.post("/equipment")
async def create_equipment(
    payload: EquipmentRequest,
    admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    db = Database.get_db()
    try:
        item, created = await save_equipment(db, **payload.model_dump(), user_id=_actor(admin))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if created:
        await log_evento(
            modulo="haccp",
            azione="attrezzatura_creata",
            entita_id=item["canonical_id"],
            entita_collection=COLL_HACCP_EQUIPMENT,
            db=db,
            nuovo_stato=item,
            fonte="configurazione_haccp",
            utente=_actor(admin),
            dettaglio=item["name"],
        )
    return {"created": created, "equipment": item}


@router.patch("/equipment/{equipment_id}")
async def patch_equipment(
    equipment_id: str,
    payload: EquipmentUpdateRequest,
    admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    db = Database.get_db()
    try:
        item = await update_equipment(
            db, equipment_id=equipment_id, **payload.model_dump(), user_id=_actor(admin)
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await log_evento(
        modulo="haccp",
        azione="attrezzatura_aggiornata",
        entita_id=equipment_id,
        entita_collection=COLL_HACCP_EQUIPMENT,
        db=db,
        nuovo_stato=item,
        fonte="configurazione_haccp",
        utente=_actor(admin),
        dettaglio=item["name"],
    )
    return {"equipment": item}


@router.get("/recipes")
async def recipes(
    search: str = "",
    limit: int = Query(500, ge=1, le=2000),
    _user: Dict[str, Any] = Depends(get_current_user),
):
    query: dict[str, Any] = {"status": {"$ne": "ARCHIVIATA"}}
    if search.strip():
        query["name"] = {"$regex": search.strip(), "$options": "i"}
    collection = Database.get_db()[COLL_HACCP_RECIPES]
    items = await collection.find(query, {"_id": 0}).sort("name", 1).limit(limit).to_list(limit)
    return {"items": items, "total": len(items)}


@router.post("/recipes")
async def create_recipe(
    payload: RecipeRequest,
    user: Dict[str, Any] = Depends(richiedi_scrittura),
):
    db = Database.get_db()
    try:
        item, created = await save_recipe(
            db,
            **payload.model_dump(),
            user_id=_actor(user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if created:
        await log_evento(
            modulo="haccp",
            azione="ricetta_creata",
            entita_id=item["canonical_id"],
            entita_collection=COLL_HACCP_RECIPES,
            db=db,
            nuovo_stato=item,
            fonte="ricettario_haccp",
            utente=_actor(user),
            dettaglio=item["name"],
        )
    return {"created": created, "recipe": item}


@router.put("/recipes/{recipe_id}")
async def update_recipe(
    recipe_id: str,
    payload: RecipeRequest,
    user: Dict[str, Any] = Depends(richiedi_scrittura),
):
    db = Database.get_db()
    try:
        item, _created = await save_recipe(
            db,
            **payload.model_dump(),
            recipe_id=recipe_id,
            user_id=_actor(user),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await log_evento(
        modulo="haccp",
        azione="ricetta_aggiornata",
        entita_id=recipe_id,
        entita_collection=COLL_HACCP_RECIPES,
        db=db,
        nuovo_stato=item,
        fonte="ricettario_haccp",
        utente=_actor(user),
        dettaglio=f"{item['name']} v{item['version']}",
    )
    return {"recipe": item}


@router.get("/productions")
async def productions(
    anno: int = Query(2026, ge=2018, le=2100),
    limit: int = Query(500, ge=1, le=2000),
    _user: Dict[str, Any] = Depends(get_current_user),
):
    collection = Database.get_db()[COLL_HACCP_PRODUCTIONS]
    items = await collection.find({"anno": anno}, {"_id": 0}).sort("production_date", -1).limit(limit).to_list(limit)
    return {"items": items, "total": len(items)}


@router.post("/productions")
async def create_production(
    payload: ProductionRequest,
    user: Dict[str, Any] = Depends(richiedi_scrittura),
):
    db = Database.get_db()
    try:
        item, created = await register_production(
            db,
            **payload.model_dump(),
            user_id=_actor(user),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if created:
        await log_evento(
            modulo="haccp",
            azione="produzione_registrata",
            entita_id=item["canonical_id"],
            entita_collection=COLL_HACCP_PRODUCTIONS,
            db=db,
            nuovo_stato=item,
            fonte="produzione_haccp",
            utente=_actor(user),
            dettaglio=f"{item['recipe_name']} lotto {item['lot_number']}",
        )
    return {"created": created, "production": item}
