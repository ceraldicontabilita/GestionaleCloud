"""Trattenute disciplinari (multe, generiche) — Task 4 roadmap acconti.

Gestisce trattenute con workflow di approvazione:
    proposta → approvata → applicata
                          ↘ annullata

Distinzione importante:
- Le trattenute "tecniche" da acconto scalato sono gestite dal Task 3
  (campo cedolino_id sull'acconto, NON viene creato un record qui).
- Questo router gestisce SOLO trattenute disciplinari/contrattuali con:
    * tipo = "multa" | "generica"
    * Allegato PDF OBBLIGATORIO (lettera contestazione, prova del danno, ecc.)
    * Workflow proposta/approvata/applicata

Permessi:
- Proporre, modificare in stato proposta, eliminare in stato proposta:
  qualunque utente loggato
- Approvare: solo role==admin (controllato via get_current_admin_user)
- Applicare al cedolino, annullare: solo role==admin

Allegato PDF:
- Salvato come base64 nella stessa collection
  (campo allegato_pdf_data + allegato_pdf_nome + allegato_pdf_size)
- Endpoint dedicato GET /trattenute/{id}/allegato per download
- Limite 10MB per file (oltre, errore 413)

Collection: trattenute_dipendenti
Schema esteso (campi nuovi rispetto a quanto già scritto da cedolini.py):
    tipo:                  "multa" | "generica" (nuovo: prima era flat)
    data_evento:           YYYY-MM-DD
    riferimento_normativo: stringa libera (es. "Art. 24 CCNL Turismo")
    allegato_pdf_id:       uuid (per dedup), allegato_pdf_data (base64),
                           allegato_pdf_nome, allegato_pdf_size, allegato_pdf_mime
    stato:                 "proposta" | "approvata" | "applicata" | "annullata"
    proposta_il, proposta_da, approvata_il, approvata_da,
    applicata_il, cedolino_id, motivo_annullamento

Indici utili (in app/database.py):
- (dipendente_id, anno, mese): query per fascicolo
- stato: filtri lifecycle
- cedolino_id (sparse): lookup inverso da cedolino
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from uuid import uuid4
import logging
import base64
import io

from app.database import Database
from app.utils.dependencies import get_current_user, get_current_admin_user
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()

# Collection
COLL_TRATTENUTE = "trattenute_dipendenti"
COLL_DIPENDENTI = "dipendenti"
COLL_CEDOLINI = "cedolini"

# Validazione
TIPI_DISCIPLINARI = {"multa", "generica"}
STATI_DISCIPLINARI = {"proposta", "approvata", "applicata", "annullata"}
MAX_PDF_SIZE = 10 * 1024 * 1024  # 10MB


# ============================================================================
# MODELLI
# ============================================================================

class TrattenutaProponiInput(BaseModel):
    """Body per creare proposta. NB: in realtà l'endpoint usa multipart/form-data
    per accettare il file PDF, quindi questa è solo documentazione del JSON
    equivalente — i campi vengono passati via Form()."""
    dipendente_id: str
    tipo: str  # "multa" | "generica"
    importo: float
    descrizione: str
    data_evento: str  # YYYY-MM-DD
    mese: int  # mese cedolino target
    anno: int  # anno cedolino target
    riferimento_normativo: Optional[str] = None
    note: Optional[str] = None


class TrattenutaModificaInput(BaseModel):
    """Modifica una trattenuta in stato 'proposta'."""
    importo: Optional[float] = None
    descrizione: Optional[str] = None
    data_evento: Optional[str] = None
    mese: Optional[int] = None
    anno: Optional[int] = None
    riferimento_normativo: Optional[str] = None
    note: Optional[str] = None


class TrattenutaAnnullaInput(BaseModel):
    motivo_annullamento: str


# ============================================================================
# CRUD
# ============================================================================

@router.post("", summary="Crea proposta di trattenuta disciplinare con PDF allegato")
@handle_errors
async def proponi_trattenuta(
    dipendente_id: str = Form(...),
    tipo: str = Form(...),
    importo: float = Form(...),
    descrizione: str = Form(...),
    data_evento: str = Form(...),
    mese: int = Form(...),
    anno: int = Form(...),
    riferimento_normativo: Optional[str] = Form(None),
    note: Optional[str] = Form(None),
    allegato_pdf: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Crea una nuova proposta di trattenuta disciplinare.

    Stato iniziale: 'proposta'. Solo dopo approvazione (POST /approva)
    e applicazione (POST /applica) la trattenuta produrrà effetti
    contabili sul cedolino.

    Validazioni:
    - tipo deve essere 'multa' o 'generica'
    - importo > 0
    - mese 1-12, anno 2020-2030
    - PDF obbligatorio, max 10MB, mime application/pdf
    - dipendente deve esistere

    Audit: registra proposta_da, proposta_il con dati current_user.
    """
    db = Database.get_db()

    # Validazione tipo
    if tipo not in TIPI_DISCIPLINARI:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo non valido. Usa: {', '.join(sorted(TIPI_DISCIPLINARI))}",
        )

    # Validazione importo
    if importo <= 0:
        raise HTTPException(status_code=400, detail="L'importo deve essere positivo")

    # Validazione periodo
    if not (1 <= mese <= 12):
        raise HTTPException(status_code=400, detail="Mese deve essere 1-12")
    if not (2020 <= anno <= 2030):
        raise HTTPException(status_code=400, detail="Anno fuori range (2020-2030)")

    # Validazione data_evento (formato ISO)
    try:
        datetime.strptime(data_evento, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"data_evento non valida (atteso YYYY-MM-DD): {data_evento}",
        )

    # Verifica dipendente
    dip = await db[COLL_DIPENDENTI].find_one(
        {"id": dipendente_id},
        {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "nome_completo": 1, "codice_fiscale": 1},
    )
    if not dip:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")

    # Validazione PDF
    if not allegato_pdf.filename:
        raise HTTPException(status_code=400, detail="Allegato PDF obbligatorio")

    pdf_bytes = await allegato_pdf.read()
    pdf_size = len(pdf_bytes)
    if pdf_size == 0:
        raise HTTPException(status_code=400, detail="Allegato PDF vuoto")
    if pdf_size > MAX_PDF_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"PDF troppo grande ({pdf_size} bytes, max {MAX_PDF_SIZE})",
        )

    mime_type = allegato_pdf.content_type or "application/pdf"
    # Accettiamo solo PDF — protezione minimale (la verifica magic bytes
    # è in altre parti del sistema; qui ci fidiamo del mime + estensione)
    if not (mime_type == "application/pdf" or allegato_pdf.filename.lower().endswith(".pdf")):
        raise HTTPException(
            status_code=400,
            detail=f"Solo PDF accettati (mime: {mime_type})",
        )

    # Codifica PDF in base64
    pdf_b64 = base64.b64encode(pdf_bytes).decode()

    now_iso = datetime.now(timezone.utc).isoformat()
    trattenuta_id = str(uuid4())
    user_id = current_user.get("id") or current_user.get("email") or "anonimo"
    user_name = current_user.get("nome") or current_user.get("email") or user_id

    nome_completo_dip = (
        dip.get("nome_completo")
        or f"{dip.get('cognome', '')} {dip.get('nome', '')}".strip()
    )

    trattenuta = {
        "id": trattenuta_id,
        "dipendente_id": dipendente_id,
        "dipendente_cf": dip.get("codice_fiscale"),
        "dipendente_nome": nome_completo_dip,

        "tipo": tipo,
        "importo": round(importo, 2),
        "descrizione": descrizione.strip(),
        "data_evento": data_evento,
        "mese": int(mese),
        "anno": int(anno),
        "riferimento_normativo": (riferimento_normativo or "").strip() or None,
        "note": (note or "").strip() or None,

        # Allegato PDF
        "allegato_pdf_id": str(uuid4()),
        "allegato_pdf_data": pdf_b64,
        "allegato_pdf_nome": allegato_pdf.filename,
        "allegato_pdf_size": pdf_size,
        "allegato_pdf_mime": mime_type,

        # Stato lifecycle
        "stato": "proposta",
        "proposta_il": now_iso,
        "proposta_da": user_id,
        "proposta_da_nome": user_name,
        "approvata_il": None,
        "approvata_da": None,
        "applicata_il": None,
        "cedolino_id": None,
        "motivo_annullamento": None,

        # Audit
        "source": "trattenute_disciplinari",
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    await db[COLL_TRATTENUTE].insert_one(trattenuta.copy())

    # Risposta senza il PDF base64 (troppo pesante per essere echo-ato)
    response = {k: v for k, v in trattenuta.items() if k != "allegato_pdf_data"}
    response.pop("_id", None)

    return {
        "success": True,
        "messaggio": f"Trattenuta {tipo} di €{importo:.2f} proposta per {nome_completo_dip}. In attesa di approvazione.",
        "trattenuta": response,
    }


@router.get("", summary="Lista trattenute disciplinari (con filtri)")
@handle_errors
async def lista_trattenute(
    dipendente_id: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None, description="multa | generica"),
    stato: Optional[str] = Query(None),
    anno: Optional[int] = Query(None),
    mese: Optional[int] = Query(None, ge=1, le=12),
    limit: int = Query(default=500, ge=1, le=2000),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Lista trattenute disciplinari con filtri opzionali.

    NB: vengono restituite SOLO le trattenute con tipo in
    {multa, generica} — il vecchio endpoint /api/cedolini/dipendente/{id}/trattenute
    può vedere anche record con tipo legacy ('verbale', 'pignoramento', ecc.).
    Questo endpoint è dedicato al nuovo sistema.

    L'allegato_pdf_data NON viene incluso nella response (troppo pesante).
    Per scaricare il PDF usa GET /trattenute/{id}/allegato.
    """
    db = Database.get_db()

    query: Dict[str, Any] = {
        "tipo": {"$in": list(TIPI_DISCIPLINARI)},
        "source": "trattenute_disciplinari",
    }

    if dipendente_id:
        query["dipendente_id"] = dipendente_id
    if tipo:
        if tipo not in TIPI_DISCIPLINARI:
            raise HTTPException(
                status_code=400,
                detail=f"Tipo non valido. Usa: {', '.join(sorted(TIPI_DISCIPLINARI))}",
            )
        query["tipo"] = tipo
    if stato:
        if stato not in STATI_DISCIPLINARI:
            raise HTTPException(
                status_code=400,
                detail=f"Stato non valido. Usa: {', '.join(sorted(STATI_DISCIPLINARI))}",
            )
        query["stato"] = stato
    if anno:
        query["anno"] = int(anno)
    if mese:
        query["mese"] = int(mese)

    items = (
        await db[COLL_TRATTENUTE]
        .find(query, {"_id": 0, "allegato_pdf_data": 0})  # esclude PDF dalla list
        .sort([("anno", -1), ("mese", -1), ("data_evento", -1)])
        .to_list(limit)
    )

    # Aggregazione per stato
    per_stato: Dict[str, Dict[str, float]] = {}
    for it in items:
        s = it.get("stato", "proposta")
        if s not in per_stato:
            per_stato[s] = {"count": 0, "totale": 0.0}
        per_stato[s]["count"] += 1
        per_stato[s]["totale"] += float(it.get("importo", 0) or 0)
    for s in per_stato:
        per_stato[s]["totale"] = round(per_stato[s]["totale"], 2)

    return {
        "count": len(items),
        "totale": round(sum(float(t.get("importo", 0) or 0) for t in items), 2),
        "per_stato": per_stato,
        "trattenute": items,
    }


@router.get("/{trattenuta_id}", summary="Dettaglio trattenuta (senza PDF)")
@handle_errors
async def dettaglio_trattenuta(
    trattenuta_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Restituisce il dettaglio completo della trattenuta. Il PDF è escluso
    per non appesantire la response."""
    db = Database.get_db()
    t = await db[COLL_TRATTENUTE].find_one(
        {"id": trattenuta_id},
        {"_id": 0, "allegato_pdf_data": 0},
    )
    if not t:
        raise HTTPException(status_code=404, detail="Trattenuta non trovata")
    return t


@router.get("/{trattenuta_id}/allegato", summary="Scarica il PDF allegato")
@handle_errors
async def download_allegato(
    trattenuta_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Streamming download del PDF allegato alla trattenuta."""
    db = Database.get_db()
    t = await db[COLL_TRATTENUTE].find_one({"id": trattenuta_id})
    if not t:
        raise HTTPException(status_code=404, detail="Trattenuta non trovata")
    if not t.get("allegato_pdf_data"):
        raise HTTPException(status_code=404, detail="Nessun allegato per questa trattenuta")

    pdf_bytes = base64.b64decode(t["allegato_pdf_data"])
    filename = t.get("allegato_pdf_nome") or f"trattenuta_{trattenuta_id}.pdf"
    mime = t.get("allegato_pdf_mime") or "application/pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type=mime,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.put("/{trattenuta_id}", summary="Modifica trattenuta in stato 'proposta'")
@handle_errors
async def modifica_trattenuta(
    trattenuta_id: str,
    payload: TrattenutaModificaInput,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Modifica una trattenuta. Permesso SOLO se stato == 'proposta'.

    Una volta approvata (o applicata), per modifica serve prima annullare
    e creare una nuova proposta. Questo per garantire tracciabilità
    storica.
    """
    db = Database.get_db()
    t = await db[COLL_TRATTENUTE].find_one({"id": trattenuta_id})
    if not t:
        raise HTTPException(status_code=404, detail="Trattenuta non trovata")
    if t.get("stato") != "proposta":
        raise HTTPException(
            status_code=400,
            detail=f"Solo trattenute in stato 'proposta' possono essere modificate. "
                   f"Stato attuale: {t.get('stato')}. Annulla e crea nuova proposta.",
        )

    update_fields: Dict[str, Any] = {}
    if payload.importo is not None:
        if payload.importo <= 0:
            raise HTTPException(status_code=400, detail="L'importo deve essere positivo")
        update_fields["importo"] = round(payload.importo, 2)
    if payload.descrizione is not None:
        update_fields["descrizione"] = payload.descrizione.strip()
    if payload.data_evento is not None:
        try:
            datetime.strptime(payload.data_evento, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="data_evento non valida")
        update_fields["data_evento"] = payload.data_evento
    if payload.mese is not None:
        if not (1 <= payload.mese <= 12):
            raise HTTPException(status_code=400, detail="Mese deve essere 1-12")
        update_fields["mese"] = int(payload.mese)
    if payload.anno is not None:
        if not (2020 <= payload.anno <= 2030):
            raise HTTPException(status_code=400, detail="Anno fuori range")
        update_fields["anno"] = int(payload.anno)
    if payload.riferimento_normativo is not None:
        update_fields["riferimento_normativo"] = payload.riferimento_normativo.strip() or None
    if payload.note is not None:
        update_fields["note"] = payload.note.strip() or None

    if update_fields:
        update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db[COLL_TRATTENUTE].update_one(
            {"id": trattenuta_id}, {"$set": update_fields}
        )

    return {
        "success": True,
        "messaggio": "Trattenuta modificata",
        "campi_aggiornati": sorted(update_fields.keys()),
    }


@router.delete("/{trattenuta_id}", summary="Elimina trattenuta in stato 'proposta'")
@handle_errors
async def elimina_trattenuta(
    trattenuta_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Elimina una trattenuta. Permesso SOLO se stato == 'proposta'.

    Per trattenute in stato successivo (approvata/applicata) usa /annulla.
    """
    db = Database.get_db()
    t = await db[COLL_TRATTENUTE].find_one({"id": trattenuta_id})
    if not t:
        raise HTTPException(status_code=404, detail="Trattenuta non trovata")
    if t.get("stato") != "proposta":
        raise HTTPException(
            status_code=400,
            detail=f"Solo trattenute in stato 'proposta' possono essere eliminate. "
                   f"Stato attuale: {t.get('stato')}. Usa l'endpoint /annulla.",
        )

    await db[COLL_TRATTENUTE].delete_one({"id": trattenuta_id})
    return {"success": True, "messaggio": "Trattenuta eliminata"}


# ============================================================================
# WORKFLOW: APPROVAZIONE / APPLICAZIONE / ANNULLAMENTO
# ============================================================================

@router.post("/{trattenuta_id}/approva", summary="Approva proposta (solo admin)")
@handle_errors
async def approva_trattenuta(
    trattenuta_id: str,
    admin_user: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Approva una trattenuta (transizione: proposta → approvata).

    Permesso solo per utenti con role == 'admin' (titolare).
    Dopo l'approvazione, la trattenuta non è più modificabile né
    eliminabile, ma può essere applicata o annullata.
    """
    db = Database.get_db()
    t = await db[COLL_TRATTENUTE].find_one({"id": trattenuta_id})
    if not t:
        raise HTTPException(status_code=404, detail="Trattenuta non trovata")
    if t.get("stato") != "proposta":
        raise HTTPException(
            status_code=400,
            detail=f"Solo proposte possono essere approvate. Stato attuale: {t.get('stato')}",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    user_id = admin_user.get("id") or admin_user.get("email") or "admin"
    user_name = admin_user.get("nome") or admin_user.get("email") or user_id

    await db[COLL_TRATTENUTE].update_one(
        {"id": trattenuta_id},
        {"$set": {
            "stato": "approvata",
            "approvata_il": now_iso,
            "approvata_da": user_id,
            "approvata_da_nome": user_name,
            "updated_at": now_iso,
        }},
    )

    return {
        "success": True,
        "messaggio": f"Trattenuta approvata. Pronta per essere applicata sul cedolino di {t.get('mese')}/{t.get('anno')}.",
        "stato": "approvata",
    }


@router.post("/{trattenuta_id}/applica", summary="Applica trattenuta al cedolino (solo admin)")
@handle_errors
async def applica_trattenuta(
    trattenuta_id: str,
    admin_user: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Applica una trattenuta approvata al cedolino del mese (transizione:
    approvata → applicata).

    Cerca il cedolino con (dipendente_id|codice_fiscale, anno, mese) e:
    - Linka cedolino_id alla trattenuta
    - Decrementa il netto del cedolino (campo 'netto')
    - Incrementa 'altre_trattenute' del cedolino
    - Push entry su 'trattenute_applicate' del cedolino per tracciabilità

    400 se non c'è cedolino per quel periodo (devi prima caricarlo).
    """
    db = Database.get_db()
    t = await db[COLL_TRATTENUTE].find_one({"id": trattenuta_id})
    if not t:
        raise HTTPException(status_code=404, detail="Trattenuta non trovata")
    if t.get("stato") != "approvata":
        raise HTTPException(
            status_code=400,
            detail=f"Solo trattenute approvate possono essere applicate. Stato attuale: {t.get('stato')}",
        )

    # Cerca cedolino per periodo
    mese = t.get("mese")
    anno = t.get("anno")
    dipendente_id = t.get("dipendente_id")
    cf = t.get("dipendente_cf")

    cedolino = await db[COLL_CEDOLINI].find_one({
        "$or": [
            {"dipendente_id": dipendente_id},
            {"codice_fiscale": cf} if cf else {"_id": None},
        ],
        "mese": mese,
        "anno": anno,
    })

    if not cedolino:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Nessun cedolino trovato per {mese}/{anno} di "
                f"{t.get('dipendente_nome')}. Carica prima il cedolino."
            ),
        )

    importo = float(t.get("importo", 0) or 0)
    cedolino_id = cedolino["id"]
    now_iso = datetime.now(timezone.utc).isoformat()

    # Aggiorna cedolino
    await db[COLL_CEDOLINI].update_one(
        {"id": cedolino_id},
        {
            "$set": {
                "altre_trattenute": float(cedolino.get("altre_trattenute", 0) or 0) + importo,
                "trattenute_disciplinari": float(cedolino.get("trattenute_disciplinari", 0) or 0) + importo,
                "netto": float(cedolino.get("netto", 0) or 0) - importo,
                "updated_at": now_iso,
            },
            "$push": {
                "trattenute_applicate": {
                    "id": trattenuta_id,
                    "tipo": t.get("tipo"),
                    "importo": importo,
                    "descrizione": t.get("descrizione"),
                    "data_evento": t.get("data_evento"),
                    "applicata_il": now_iso,
                }
            },
        },
    )

    # Aggiorna trattenuta
    await db[COLL_TRATTENUTE].update_one(
        {"id": trattenuta_id},
        {"$set": {
            "stato": "applicata",
            "applicata_il": now_iso,
            "cedolino_id": cedolino_id,
            "updated_at": now_iso,
        }},
    )

    return {
        "success": True,
        "messaggio": (
            f"Trattenuta di €{importo:.2f} applicata al cedolino "
            f"{mese}/{anno} di {t.get('dipendente_nome')}"
        ),
        "stato": "applicata",
        "cedolino_id": cedolino_id,
        "importo_applicato": round(importo, 2),
    }


@router.post("/{trattenuta_id}/annulla", summary="Annulla trattenuta (solo admin)")
@handle_errors
async def annulla_trattenuta(
    trattenuta_id: str,
    payload: TrattenutaAnnullaInput,
    admin_user: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Annulla una trattenuta (transizione: qualsiasi → annullata).

    Se la trattenuta era già 'applicata' al cedolino, ripristina:
    - Reincrementa il netto del cedolino
    - Decrementa altre_trattenute / trattenute_disciplinari
    - Pull dell'entry da trattenute_applicate

    motivo_annullamento è obbligatorio per audit.
    """
    db = Database.get_db()
    t = await db[COLL_TRATTENUTE].find_one({"id": trattenuta_id})
    if not t:
        raise HTTPException(status_code=404, detail="Trattenuta non trovata")
    if t.get("stato") == "annullata":
        raise HTTPException(status_code=400, detail="Trattenuta già annullata")
    if not payload.motivo_annullamento or not payload.motivo_annullamento.strip():
        raise HTTPException(status_code=400, detail="motivo_annullamento obbligatorio")

    now_iso = datetime.now(timezone.utc).isoformat()
    user_id = admin_user.get("id") or admin_user.get("email") or "admin"

    # Se era applicata, ripristina cedolino
    if t.get("stato") == "applicata" and t.get("cedolino_id"):
        cedolino_id = t["cedolino_id"]
        importo = float(t.get("importo", 0) or 0)
        cedolino = await db[COLL_CEDOLINI].find_one({"id": cedolino_id})
        if cedolino:
            await db[COLL_CEDOLINI].update_one(
                {"id": cedolino_id},
                {
                    "$set": {
                        "altre_trattenute": max(0.0, float(cedolino.get("altre_trattenute", 0) or 0) - importo),
                        "trattenute_disciplinari": max(0.0, float(cedolino.get("trattenute_disciplinari", 0) or 0) - importo),
                        "netto": float(cedolino.get("netto", 0) or 0) + importo,
                        "updated_at": now_iso,
                    },
                    "$pull": {
                        "trattenute_applicate": {"id": trattenuta_id},
                    },
                },
            )

    await db[COLL_TRATTENUTE].update_one(
        {"id": trattenuta_id},
        {"$set": {
            "stato": "annullata",
            "motivo_annullamento": payload.motivo_annullamento.strip(),
            "annullata_il": now_iso,
            "annullata_da": user_id,
            "updated_at": now_iso,
        }},
    )

    return {
        "success": True,
        "messaggio": "Trattenuta annullata" + (
            " e cedolino ripristinato" if t.get("stato") == "applicata" else ""
        ),
        "stato": "annullata",
    }
