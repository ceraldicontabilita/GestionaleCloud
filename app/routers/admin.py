"""Admin router - Administrative functions."""
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from typing import Dict, Any, List
from datetime import datetime, timezone
import logging
import asyncio
import uuid

from app.database import Database
from app.utils.dependencies import get_current_user, get_current_admin_user
from app.utils.ruoli import richiedi_admin

logger = logging.getLogger(__name__)
router = APIRouter()


_supabase_migration_jobs: Dict[str, Dict[str, Any]] = {}


def _supabase_runtime_config(settings: Any) -> Dict[str, str]:
    return {
        "SUPABASE_URL": str(settings.SUPABASE_URL or "").strip(),
        "SUPABASE_PUBLISHABLE_KEY": str(
            settings.SUPABASE_PUBLISHABLE_KEY or ""
        ).strip(),
        "SUPABASE_RUNTIME_SECRET": str(
            settings.SUPABASE_RUNTIME_SECRET or ""
        ).strip(),
    }


async def _run_supabase_migration_job(job_id: str) -> None:
    """Copia ogni documento gia' idratato in memoria dentro
    gestionale.documents su Supabase.

    Sola lettura dalla cache di processo gia' caricata all'avvio: nessuna
    nuova chiamata remota, quindi non rallenta il traffico applicativo in
    corso. Scrittura idempotente (upsert per collection+id su Supabase):
    rilanciabile senza duplicare nulla se si interrompe o va rieseguita.
    Supabase e' ormai l'unico backend supportato: questo job resta come
    strumento di preparazione per un'eventuale migrazione futura verso un
    altro archivio, non per un cutover da Sheets (gia' completato).
    """
    job = _supabase_migration_jobs[job_id]
    try:
        from app.config import settings
        from app.services.supabase_runtime_database import SupabaseRuntimeDatabase

        origine = Database.get_db()
        if isinstance(origine, SupabaseRuntimeDatabase):
            raise RuntimeError("Il backend attivo e' gia' Supabase: niente da migrare")

        nomi = await origine.list_collection_names()
        destinazione = SupabaseRuntimeDatabase(
            "gestionale_migrazione", _supabase_runtime_config(settings),
        )
        dettaglio: List[Dict[str, Any]] = []
        errori: List[Dict[str, Any]] = []
        totale = 0
        try:
            for nome in nomi:
                documenti = await origine[nome].find({}).to_list(None)
                try:
                    scritte = await destinazione.mirror_collection(nome, documenti)
                    verifica = await destinazione.verify_collection(nome, documenti)
                    if not verifica["coincide"]:
                        raise RuntimeError(
                            "verifica conteggio/impronta non coincidente"
                        )
                except Exception as exc:  # noqa: BLE001 - una collezione non deve bloccare le altre
                    logger.error("[SUPABASE-MIGRATE] collezione=%s errore: %s", nome, exc)
                    errori.append({"collezione": nome, "errore": str(exc)})
                    continue
                dettaglio.append({
                    "collezione": nome,
                    "righe": scritte,
                    "verifica": verifica,
                })
                totale += scritte
        finally:
            destinazione.close()

        job.update(
            status="completed" if not errori else "completed_con_errori",
            result={
                "backend_origine": type(origine).__name__,
                "collezioni": len(dettaglio),
                "righe_totali": totale,
                "dettaglio": dettaglio,
                "errori": errori,
            },
        )
    except Exception as exc:
        logger.exception("Migrazione Supabase fallita")
        job.update(status="failed", error=str(exc))
    finally:
        job["finished_at"] = datetime.now(timezone.utc).isoformat()


@router.post("/supabase-migration/jobs")
async def avvia_migrazione_supabase(
    payload: Dict[str, Any] = Body(...),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Avvia la copia una tantum del backend attivo verso
    gestionale.documents su Supabase.

    Richiede conferma esplicita nel body per evitare avvii accidentali.
    Non modifica DATA_BACKEND: e' una copia di sola preparazione. Con
    Supabase gia' unico backend supportato, oggi fallisce sempre con
    "niente da migrare"; resta predisposta per un'eventuale migrazione
    futura verso un altro archivio.
    """
    if payload.get("conferma") != "MIGRA":
        raise HTTPException(
            status_code=400,
            detail="Conferma mancante: inviare {\"conferma\": \"MIGRA\"} nel body",
        )
    from app.config import settings
    if not all(_supabase_runtime_config(settings).values()):
        raise HTTPException(
            status_code=503,
            detail=(
                "Collegamento Supabase incompleto: configurare URL, chiave "
                "pubblicabile e secret runtime prima di avviare la migrazione"
            ),
        )
    running = next(
        (item for item in _supabase_migration_jobs.values() if item["status"] == "running"),
        None,
    )
    if running:
        return running
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id, "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    _supabase_migration_jobs[job_id] = job
    asyncio.create_task(_run_supabase_migration_job(job_id))
    return job


@router.get("/supabase-migration/jobs/{job_id}")
async def stato_migrazione_supabase(
    job_id: str = Path(...),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    job = _supabase_migration_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Elaborazione non trovata o server riavviato")
    return job


@router.get("/bank-supplier-rules")
async def list_bank_supplier_rules() -> List[Dict[str, Any]]:
    return await Database.get_db()["bank_supplier_rules"].find({}, {"_id": 0}).sort("supplier_name", 1).to_list(1000)

@router.post("/bank-supplier-rules")
async def upsert_bank_supplier_rule(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    from app.services.bank_supplier_rules import save_rule
    return await save_rule(Database.get_db(), payload)

@router.delete("/bank-supplier-rules/{rule_id}")
async def delete_bank_supplier_rule(rule_id: str) -> Dict[str, Any]:
    result = await Database.get_db()["bank_supplier_rules"].delete_one({"id": rule_id})
    if not result.deleted_count:
        raise HTTPException(status_code=404, detail="Regola non trovata")
    return {"deleted": True, "id": rule_id}

@router.post("/bank-supplier-rules/reprocess/{year}")
async def reprocess_bank_supplier_rules(year: int) -> Dict[str, Any]:
    from app.services.bank_supplier_rules import reprocess_rules
    return await reprocess_rules(Database.get_db(), year)


@router.get("/dashboard-summary", summary="Aggregated dashboard summary for admin page")
async def get_dashboard_summary() -> Dict[str, Any]:
    """Restituisce in un'unica chiamata tutti i dati per la pagina admin."""
    db = Database.get_db()

    async def _stats():
        return {
            "invoices": await db["invoices"].count_documents({}),
            "suppliers": await db["fornitori"].count_documents({}),
            "employees": await db["dipendenti"].count_documents({}),
            "prima_nota_cassa": await db["prima_nota_cassa"].count_documents({}),
            "prima_nota_banca": await db["prima_nota_banca"].count_documents({}),
            "f24": await db["f24_unificato"].count_documents({}),
        }

    async def _alert_count():
        count = await db["alerts"].count_documents({"letto": {"$ne": True}, "risolto": {"$ne": True}})
        return {"non_letti": count}

    async def _agenti_count():
        count = await db["agenti_segnalazioni"].count_documents({"letta": {"$ne": True}})
        return {"non_lette": count}

    async def _sync_status():
        fatture = await db["invoices"].count_documents({})
        cassa = await db["prima_nota_cassa"].count_documents({})
        banca = await db["prima_nota_banca"].count_documents({})
        return {"fatture": fatture, "prima_nota_cassa": cassa, "prima_nota_banca": banca}

    async def _commercialista_alert():
        from datetime import date
        today = date.today()
        # Controlla se siamo nel periodo di invio (primi 10 giorni del mese)
        if today.day <= 10:
            prev_month = today.month - 1 if today.month > 1 else 12
            prev_year = today.year if today.month > 1 else today.year - 1
            return {
                "show_alert": True,
                "mese": prev_month,
                "anno": prev_year
            }
        return {"show_alert": False}

    stats, alerts, agenti, sync, comm_alert = await asyncio.gather(
        _stats(), _alert_count(), _agenti_count(), _sync_status(), _commercialista_alert()
    )

    return {
        "stats": stats,
        "alerts": alerts,
        "agenti": agenti,
        "sync": sync,
        "commercialista_alert": comm_alert,
        "health": {"status": "healthy", "database": "connected"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get(
    "/stats",
    summary="Get database statistics"
)
async def get_stats(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get statistics for main collections."""
    db = Database.get_db()

    stats = {
        "invoices": await db["invoices"].count_documents({}),
        "suppliers": await db["fornitori"].count_documents({}),
        "products": await db["warehouse_inventory"].count_documents({}),
        "employees": await db["dipendenti"].count_documents({}),
        "prima_nota_cassa": await db["prima_nota_cassa"].count_documents({}),
        "prima_nota_banca": await db["prima_nota_banca"].count_documents({}),
        "f24": await db["f24_unificato"].count_documents({})
    }

    return stats


@router.get(
    "/year-opening-balances/{year}",
    summary="Get year opening balances"
)
async def get_year_opening_balances(
    year: int = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get opening balances for a year."""
    db = Database.get_db()
    balances = await db["opening_balances"].find_one({"year": year}, {"_id": 0})
    return balances or {"year": year, "balances": {}}


@router.put(
    "/year-opening-balances/{year}",
    summary="Update year opening balances"
)
async def update_year_opening_balances(
    data: Dict[str, Any] = Body(...),
    year: int = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Update opening balances for a year."""
    db = Database.get_db()
    data["year"] = year
    data["updated_at"] = datetime.now(timezone.utc)
    await db["opening_balances"].update_one({"year": year}, {"$set": data}, upsert=True)
    return {"message": "Balances updated"}


@router.get(
    "/collections",
    summary="Get collections list"
)
async def get_collections(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get list of collections and counts."""
    db = Database.get_db()
    cols = await db.list_collection_names()
    results = []
    for c in cols:
        count = await db[c].count_documents({})
        results.append({"name": c, "count": count})
    return results


@router.post(
    "/reset-collections",
    summary="Reset selected collections"
)
async def reset_collections(
    selected: List[str] = Query(None),
    delete_files: bool = False,
    confirmation: str = Query(
        ...,
        pattern="^RESET_SELECTED_COLLECTIONS$",
        description="Conferma esplicita per l'operazione distruttiva",
    ),
    current_user: Dict[str, Any] = Depends(get_current_admin_user)
) -> Dict[str, Any]:
    """
    Reset selected collections (Delete all data).
    If selected is None or empty, NOTHING happens unless specific 'all' logic is added.
    Frontend sends selected=...
    """
    db = Database.get_db()
    deleted_stats = {}

    # Protect critical collections
    protected = {
        "users", "system_settings", "settings", "sistema_stato",
        "token_blacklist", "mfa_settings", "audit_log",
        "prima_nota_migrazioni_audit", "migration_runs",
        "scheduler_leases", "admin_destructive_audit",
    }

    targets = list(dict.fromkeys(selected or []))
    if not targets:
        raise HTTPException(status_code=422, detail="Seleziona almeno una collection")
    if len(targets) > 20:
        raise HTTPException(status_code=422, detail="Massimo 20 collection per operazione")
    invalid = [
        col for col in targets
        if col in protected or not col.replace("_", "").isalnum()
    ]
    if invalid:
        raise HTTPException(
            status_code=403,
            detail={"message": "Collection protetta o non valida", "collections": invalid},
        )
    existing_collections = set(await db.list_collection_names())

    for col in targets:
        if col not in existing_collections:
            continue

        result = await db[col].delete_many({})
        deleted_stats[col] = {"deleted": result.deleted_count}

    audit_id = str(uuid.uuid4())
    await db["admin_destructive_audit"].insert_one({
        "id": audit_id,
        "azione": "reset_collections",
        "collections": deleted_stats,
        "delete_files_requested": bool(delete_files),
        "actor": current_user.get("sub") or current_user.get("username") or "admin",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {
        "message": "Collections reset",
        "deleted_collections": deleted_stats,
        "audit_id": audit_id,
    }


# ============================================================================
# BONIFICA: doppioni di Prima Nota derivati dai corrispettivi (audit 03/09/2026)
# ============================================================================

@router.post(
    "/bonifica-prima-nota-doppioni",
    summary="Marca (mai cancella) le copie doppie di corrispettivi/POS in Prima Nota",
)
async def bonifica_prima_nota_doppioni(
    dry_run: bool = Query(True, description="True = solo analisi; False = marca le copie"),
    current_user: Dict[str, Any] = Depends(richiedi_admin),
) -> Dict[str, Any]:
    """Audit del commercialista 03/09/2026, PR 5 e PR 3.

    Stesso ``corrispettivo_id`` (PR 5) o stesso ``estratto_conto_id`` di un
    assegno (PR 3, registro logico ``banca_assegni``) scritto due volte da
    processi con cache diverse. Con ``dry_run=true`` ritorna conteggi e
    importi per registro (cassa entrate, cassa uscite POS, banca crediti
    POS, banca assegni) e l'elenco delle coppie; con ``dry_run=false``
    marca la copia piu' recente ``entity_status="deleted"`` +
    ``duplicate_of`` e assegna ``idempotency_key`` (prerequisito della
    migrazione ``supabase/migrations/20260903_idempotency_key.sql``).
    """
    from app.services.bonifica_prima_nota_conti import (
        esegui as esegui_conti,
        integra_nel_report as integra_conti,
    )
    from app.services.bonifica_prima_nota_doppioni import esegui
    from app.services.bonifica_prima_nota_doppioni_assegni import (
        esegui as esegui_assegni,
        integra_nel_report,
    )

    db = Database.get_db()
    actor = current_user.get("sub") or current_user.get("username") or "admin"
    esito_corrispettivi = await esegui(db, dry_run=dry_run, actor=actor)
    esito_assegni = await esegui_assegni(db, dry_run=dry_run, actor=actor)
    # Audit 03/09/2026 §2 (PR 7): stesso punto unico di manutenzione anche
    # per le righe senza conto CEE (conto di tesoreria + contropartita).
    esito_conti = await esegui_conti(db, dry_run=dry_run, actor=actor)
    return integra_conti(integra_nel_report(esito_corrispettivi, esito_assegni), esito_conti)


@router.post(
    "/riallinea-pagamenti-fatture",
    summary="Riallinea fattura/scadenza/partita/EC/Prima Nota con il motore canonico",
)
async def riallinea_pagamenti_fatture(
    dry_run: bool = Query(True, description="True = solo analisi; False = riallinea e crea le proposte"),
    current_user: Dict[str, Any] = Depends(richiedi_admin),
) -> Dict[str, Any]:
    """Audit del commercialista 03/09/2026, §1 PR 2.

    Per ogni riga di Prima Nota Banca con ``fattura_id`` ricalcola gli stati
    collegati con l'unico motore ``persist_bank_invoice_allocations``
    (fattura, scadenze, partita aperta, estratto conto, Prima Nota,
    relazione, stesso ``operation_id``). Cio' che non e' risolvibile in
    automatico (fattura non in archivio, movimento antecedente alla fattura,
    quota non quadrata, EC gia' riconciliato altrove) finisce come proposta
    in ``operazioni_da_confermare``. Idempotente: un secondo giro non scrive.
    """
    from app.services.riallinea_pagamenti_fatture import esegui

    db = Database.get_db()
    actor = current_user.get("sub") or current_user.get("username") or "admin"
    return await esegui(db, dry_run=dry_run, actor=actor)


# ============================================================================
# CLEANUP: rollback Task 4 trattenute disciplinari
# ============================================================================
# Endpoint one-shot per eliminare eventuali record orfani creati durante la
# breve esistenza del sistema trattenute disciplinari (PR #50 mergiata e poi
# rollbackata in PR successiva). Identificati da source='trattenute_disciplinari'.
# Da chiamare una volta dopo il deploy del rollback. Idempotente.

@router.delete(
    "/cleanup-trattenute-disciplinari",
    summary="One-shot: rimuove record orfani del sistema trattenute disciplinari (Task 4 rollback)",
)
async def cleanup_trattenute_disciplinari(
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Cancella tutti i record di trattenute_dipendenti con
    source='trattenute_disciplinari' creati dal sistema poi annullato.

    NON tocca i record legacy (verbali noleggio, anticipi, pignoramenti)
    che usano altri valori di source o non hanno source.

    Idempotente: se non ci sono record da eliminare restituisce 0.
    """
    db = Database.get_db()

    # Conteggio prima dell'eliminazione (per audit)
    query = {"source": "trattenute_disciplinari"}
    count_before = await db["trattenute_dipendenti"].count_documents(query)

    if count_before == 0:
        return {
            "success": True,
            "message": "Nessun record da pulire (collection già pulita)",
            "eliminati": 0,
        }

    result = await db["trattenute_dipendenti"].delete_many(query)
    logger.warning(
        f"[CLEANUP TASK 4] Eliminati {result.deleted_count} record "
        f"trattenute disciplinari (rollback PR #50)"
    )

    return {
        "success": True,
        "message": f"Cleanup completato: {result.deleted_count} record eliminati",
        "eliminati": result.deleted_count,
        "trovati_prima": count_before,
    }


# ============================================================================
# BACKFILL: AltriDatiGestionali/DatiContratto su fatture noleggio già importate
# ============================================================================

@router.post(
    "/noleggio/backfill-dati-gestionali",
    summary="Ri-parsa xml_raw delle fatture noleggio per popolare AltriDatiGestionali/DatiContratto"
)
async def backfill_noleggio_dati_gestionali(
    dry_run: bool = Query(True, description="Se True, non scrive nulla: restituisce solo le statistiche"),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Il parser app/parsers/fattura_elettronica_parser.py scartava i blocchi
    AltriDatiGestionali (codice cliente, contratto, telaio, causali reali) e
    DatiContratto: le fatture importate PRIMA del fix non hanno questi dati.
    Questo endpoint ri-parsa xml_raw (già salvato ad ogni import) delle
    fatture dei fornitori noleggio e aggiorna solo linee/dati_contratto,
    senza toccare il resto del documento.
    """
    from app.services.noleggio import FORNITORI_NOLEGGIO
    from app.parsers.fattura_elettronica_parser import parse_fattura_xml_body

    db = Database.get_db()

    query = {
        "supplier_vat": {"$in": list(FORNITORI_NOLEGGIO.values())},
        "xml_raw": {"$exists": True, "$ne": ""},
    }

    aggiornate = 0
    saltate_gia_ok = 0
    errori = 0
    esaminate = 0

    cursor = db["invoices"].find(query, {"xml_raw": 1, "linee": 1, "dati_contratto": 1, "xml_body_index": 1})
    async for inv in cursor:
        esaminate += 1
        ha_gia_dati = bool(inv.get("dati_contratto")) or any(
            l.get("altri_dati_gestionali") for l in (inv.get("linee") or [])
        )
        if ha_gia_dati:
            saltate_gia_ok += 1
            continue

        # xml_raw può essere condiviso da più fatture (file FatturaPA con più
        # <FatturaElettronicaBody> raggruppati): body_index seleziona quella
        # giusta, altrimenti si ri-scriverebbero linee/dati_contratto della
        # PRIMA fattura del file su una fattura diversa (bug reale, review
        # Codex PR #71).
        parsed = parse_fattura_xml_body(inv["xml_raw"], inv.get("xml_body_index", 0))
        if parsed.get("error") or not parsed.get("linee"):
            errori += 1
            continue

        if not dry_run:
            await db["invoices"].update_one(
                {"_id": inv["_id"]},
                {"$set": {
                    "linee": parsed["linee"],
                    "dati_contratto": parsed.get("dati_contratto", []),
                }},
            )
        aggiornate += 1

    return {
        "dry_run": dry_run,
        "esaminate": esaminate,
        "aggiornate": aggiornate,
        "saltate_gia_ok": saltate_gia_ok,
        "errori_parsing": errori,
    }


# ============================================================================
# RECUPERO PREGRESSO FATTURE
# ============================================================================
# Due difetti corretti il 19/09/2026 hanno lasciato dati sbagliati in
# archivio. Le riparazioni stanno in
# `app/services/recupero_fatture_pregresso.py`: qui solo le rotte.

@router.post(
    "/fatture/ricalcola-scadenze",
    summary="Riporta data_scadenza alla scadenza dichiarata nell'XML",
)
async def fatture_ricalcola_scadenze(
    dry_run: bool = Query(True, description="Se True non scrive: restituisce solo cosa cambierebbe"),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Il canale automatico calcolava la scadenza come data fattura + 30
    giorni anche quando l'XML ne dichiarava una. Le `pagamento_rate` sono
    rimaste sulla fattura, quindi la scadenza vera si ricalcola da li' senza
    rileggere nessun file.

    Misurato in produzione il 19/09/2026: 414 fatture attive del canale
    Drive, 390 con la scadenza anticipata in media di 29 giorni e 24
    posticipata fino a 58.
    """
    richiedi_admin(current_user)
    from app.services import recupero_fatture_pregresso as recupero

    return await recupero.ricalcola_scadenze(Database.get_db(), dry_run=dry_run)


@router.post(
    "/fatture/ripubblica-evento-created",
    summary="Ripubblica fattura.created per le fatture rimaste senza partita aperta",
)
async def fatture_ripubblica_evento_created(
    dry_run: bool = Query(True, description="Se True conta soltanto le candidate, senza propagare"),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """L'import massivo del 14/09/2026 e le fatture entrate dal Drive senza
    `data_documento` non hanno propagato `fattura.created`: nessuno dei suoi
    handler e' partito, quindi niente partita aperta verso il fornitore,
    niente alert, niente audit. Sono 296 fatture per 173.184,83 EUR.

    Ripubblica **lo stesso evento sugli stessi handler**, che sono
    idempotenti: rilanciarlo non duplica partite ne' alert. Salta le fatture
    storiche archiviate di proposito (`stato_import: archivio_storico`), per
    cui l'evento non e' mai dovuto partire.

    Gira in background (§4) con lo stato in `sistema_stato`: si legge con
    `GET /fatture/ripubblica-evento-created/stato`.
    """
    richiedi_admin(current_user)
    from app.services import recupero_fatture_pregresso as recupero

    return await recupero.avvia_ripubblicazione(Database.get_db(), dry_run=dry_run)


@router.get(
    "/fatture/ripubblica-evento-created/stato",
    summary="Esito dell'ultima ripubblicazione di fattura.created",
)
async def fatture_ripubblica_evento_created_stato(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    richiedi_admin(current_user)
    from app.services import recupero_fatture_pregresso as recupero

    return await recupero.stato_ripubblicazione(Database.get_db())
