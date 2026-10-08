"""
Router Attrezzature — gestione dinamica di frigoriferi e congelatori.

GET  /api/attrezzature/                      — lista unificata (legge da config o defaults HACCP)
GET  /api/attrezzature/frigo                 — solo frigoriferi
GET  /api/attrezzature/congelatori           — solo congelatori

POST /api/attrezzature/frigo                 — aggiunge nuovo frigorifero
POST /api/attrezzature/congelatore           — aggiunge nuovo congelatore

PUT  /api/attrezzature/frigo/{numero}/rinomina    — rinomina frigorifero
PUT  /api/attrezzature/congelatore/{numero}/rinomina — rinomina congelatore
PUT  /api/attrezzature/{tipo}/{numero}/responsabile — responsabile (dipendente HR, titolare, nessuno)

DELETE /api/attrezzature/frigo/{numero}      — elimina frigorifero
DELETE /api/attrezzature/congelatore/{numero} — elimina congelatore

I nomi personalizzati vengono salvati nella collection `attrezzature_config`:
  { tipo: "frigo"|"congelatore", numero: int, nome: str, attivo: bool }

Questi nomi vengono propagati automaticamente ai dropdown di:
  - SchedaProdottoView (Calcolatore)
  - ModalRegistraLotto (tablet, scelta del luogo di stoccaggio)
  - TemperaturePositiveView / TemperatureNegativeView (colonne tabella)
  - AttrezzatureView (pagina «Frigoriferi e congelatori», Amministrazione)

25/07/2026 — aggiunta/rinomina/eliminazione sono riservate all'amministratore:
rinominare un apparecchio riscrive il nome su TUTTI i controlli temperatura già
registrati (update_many sullo storico), quindi è una modifica ai registri, non
una preferenza di visualizzazione. La lettura resta libera perché serve ai
tablet di reparto per scegliere dove mettere il lotto.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime, timezone

from app.lotti.auth import require_admin, require_permesso
from app.lotti.db import database as db
from app.lotti.servizi.responsabile_haccp import (
    ID_TITOLARE, responsabile_apparecchio, responsabile_predefinito,
)

router = APIRouter(prefix="/attrezzature", tags=["Attrezzature"])


# ─── Modello ──────────────────────────────────────────────────────────────────
class NuovaAttrezzatura(BaseModel):
    nome: str
    numero: int | None = None  # se None, viene auto-assegnato


# ─── Helper ───────────────────────────────────────────────────────────────────
async def _get_config(tipo: str) -> list[dict]:
    """Legge la config dalla collection dedicata, ordinata per numero."""
    docs = (
        await db.attrezzature_config.find({"tipo": tipo, "attivo": {"$ne": False}}, {"_id": 0})
        .sort("numero", 1)
        .to_list(None)
    )
    return docs


async def _next_numero(tipo: str) -> int:
    """Calcola il prossimo numero disponibile per il tipo indicato."""
    docs = await db.attrezzature_config.find(
        {"tipo": tipo, "attivo": {"$ne": False}}, {"_id": 0, "numero": 1}
    ).to_list(None)
    usati = {d["numero"] for d in docs}
    n = 1
    while n in usati:
        n += 1
    return n


def _label_default(tipo: str, numero: int) -> str:
    return f"Frigorifero N°{numero}" if tipo == "frigo" else f"Congelatore N°{numero}"


async def _build_list(tipo: str, fallback_tipo: str) -> list[dict]:
    """
    Restituisce la lista degli elementi del tipo indicato: quelli censiti in
    `attrezzature_config`; se non ce n'e' nessuno, i numeri che hanno una
    scheda HACCP reale (in sola lettura, senza censirli).
    """
    # Nessuna scrittura in lettura: prima qui un GET copiava in
    # `attrezzature_config` ogni numero trovato nelle schede, comprese le 12
    # schede vuote che la pagina temperature creava da sola. Un apparecchio
    # si censisce solo da «Frigoriferi e congelatori».
    docs = await _get_config(tipo)
    if docs:
        predefinito = await responsabile_predefinito()
        return [
            {"tipo": tipo, "numero": d["numero"], "nome": d["nome"], "label": d["nome"],
             "fuori_servizio": bool(d.get("fuori_servizio")),
             **responsabile_apparecchio(d, predefinito)}
            for d in docs
        ]

    coll = db.temperature_positive if tipo == "frigo" else db.temperature_negative
    campo_num = "frigorifero_numero" if tipo == "frigo" else "congelatore_numero"
    haccp_docs = await coll.find({}, {"_id": 0, campo_num: 1}).to_list(None)
    haccp_numeri = {d.get(campo_num) for d in haccp_docs if d.get(campo_num)}

    # Nessun apparecchio inventato: senza configurazione o scheda HACCP reale
    # il tablet deve chiedere di censirlo.
    numeri = sorted(haccp_numeri)
    return [
        {
            "tipo": tipo,
            "numero": n,
            "nome": _label_default(tipo, n),
            "label": _label_default(tipo, n),
        }
        for n in numeri
    ]


async def _build_destinazioni(tipo: str) -> list[dict]:
    """Elenco leggero per la posizione di un lotto nel tablet.

    La lista amministrativa completa aggiunge il responsabile HACCP leggendo
    anche le impostazioni azienda. La produzione non deve dipendere da quella
    lettura: se e' lenta, frigoriferi e congelatori devono restare selezionabili.
    """
    docs = await _get_config(tipo)
    if docs:
        return [
            {
                "tipo": tipo,
                "numero": d["numero"],
                "nome": d["nome"],
                "label": d["nome"],
                "fuori_servizio": bool(d.get("fuori_servizio")),
            }
            for d in docs
        ]

    coll = db.temperature_positive if tipo == "frigo" else db.temperature_negative
    campo_num = "frigorifero_numero" if tipo == "frigo" else "congelatore_numero"
    haccp_docs = await coll.find({}, {"_id": 0, campo_num: 1}).to_list(None)
    numeri = sorted({d.get(campo_num) for d in haccp_docs if d.get(campo_num)})
    return [
        {
            "tipo": tipo,
            "numero": n,
            "nome": _label_default(tipo, n),
            "label": _label_default(tipo, n),
            "fuori_servizio": False,
        }
        for n in numeri
    ]


# ─── GET principale ───────────────────────────────────────────────────────────
@router.get("/")
async def get_attrezzature():
    """Restituisce lista unificata frigoriferi + congelatori."""
    frigoriferi = await _build_list("frigo", "frigo")
    congelatori = await _build_list("congelatore", "congelatore")
    return {
        "frigoriferi": frigoriferi,
        "congelatori": congelatori,
        "tutti": frigoriferi + congelatori,
    }


@router.get("/destinazioni")
async def get_destinazioni_lotto():
    """Lista operativa, senza responsabili o firme amministrative."""
    frigoriferi = await _build_destinazioni("frigo")
    congelatori = await _build_destinazioni("congelatore")
    return {"frigoriferi": frigoriferi, "congelatori": congelatori}


@router.get("/frigo")
async def get_frigoriferi():
    return await _build_list("frigo", "frigo")


@router.get("/congelatori")
async def get_congelatori():
    return await _build_list("congelatore", "congelatore")


# ─── AGGIUNGI ─────────────────────────────────────────────────────────────────
@router.post("/frigo")
async def aggiungi_frigo(body: NuovaAttrezzatura, _ruolo=Depends(require_permesso("frigoriferi"))):
    """Aggiunge un nuovo frigorifero. Il numero viene auto-assegnato se non indicato."""
    numero = body.numero or await _next_numero("frigo")
    # Verifica duplicati
    existing = await db.attrezzature_config.find_one(
        {"tipo": "frigo", "numero": numero, "attivo": {"$ne": False}}
    )
    if existing:
        raise HTTPException(400, f"Frigorifero N°{numero} esiste già")
    nome = body.nome.strip() or f"Frigorifero N°{numero}"
    await db.attrezzature_config.insert_one(
        {
            "tipo": "frigo",
            "numero": numero,
            "nome": nome,
            "attivo": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {"success": True, "tipo": "frigo", "numero": numero, "nome": nome}


@router.post("/congelatore")
async def aggiungi_congelatore(body: NuovaAttrezzatura, _ruolo=Depends(require_permesso("frigoriferi"))):
    """Aggiunge un nuovo congelatore."""
    numero = body.numero or await _next_numero("congelatore")
    existing = await db.attrezzature_config.find_one(
        {"tipo": "congelatore", "numero": numero, "attivo": {"$ne": False}}
    )
    if existing:
        raise HTTPException(400, f"Congelatore N°{numero} esiste già")
    nome = body.nome.strip() or f"Congelatore N°{numero}"
    await db.attrezzature_config.insert_one(
        {
            "tipo": "congelatore",
            "numero": numero,
            "nome": nome,
            "attivo": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {"success": True, "tipo": "congelatore", "numero": numero, "nome": nome}


# ─── RINOMINA ─────────────────────────────────────────────────────────────────
@router.put("/frigo/{numero}/rinomina")
async def rinomina_frigo(numero: int, nome: str = Query(...), _ruolo=Depends(require_permesso("frigoriferi"))):
    """Rinomina un frigorifero (anche in temperature_positive per retrocompatibilità)."""
    nome = nome.strip()
    if not nome:
        raise HTTPException(400, "Il nome non può essere vuoto")
    await db.attrezzature_config.update_one(
        {"tipo": "frigo", "numero": numero},
        {
            "$set": {
                "nome": nome,
                "attivo": True,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )
    # Aggiorna anche i documenti HACCP per retrocompatibilità
    await db.temperature_positive.update_many(
        {"frigorifero_numero": numero}, {"$set": {"frigorifero_nome": nome}}
    )
    return {
        "success": True,
        "message": f"Frigorifero N°{numero} rinominato in '{nome}'",
        "numero": numero,
        "nome": nome,
    }


@router.put("/congelatore/{numero}/rinomina")
async def rinomina_congelatore(numero: int, nome: str = Query(...), _ruolo=Depends(require_permesso("frigoriferi"))):
    """Rinomina un congelatore."""
    nome = nome.strip()
    if not nome:
        raise HTTPException(400, "Il nome non può essere vuoto")
    await db.attrezzature_config.update_one(
        {"tipo": "congelatore", "numero": numero},
        {
            "$set": {
                "nome": nome,
                "attivo": True,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )
    await db.temperature_negative.update_many(
        {"congelatore_numero": numero}, {"$set": {"congelatore_nome": nome}}
    )
    return {
        "success": True,
        "message": f"Congelatore N°{numero} rinominato in '{nome}'",
        "numero": numero,
        "nome": nome,
    }


# ─── ELIMINA ──────────────────────────────────────────────────────────────────
@router.delete("/frigo/{numero}")
async def elimina_frigo(numero: int, _admin=Depends(require_admin)):
    """
    Elimina un frigorifero dalla lista (soft delete — mette attivo=False).
    I lotti già associati a questo frigo non vengono modificati.
    """
    result = await db.attrezzature_config.update_one(
        {"tipo": "frigo", "numero": numero},
        {"$set": {"attivo": False, "deleted_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.matched_count == 0:
        # Il frigo esiste solo come default (HACCP) — lo marchiamo come eliminato
        await db.attrezzature_config.insert_one(
            {
                "tipo": "frigo",
                "numero": numero,
                "nome": f"Frigorifero N°{numero}",
                "attivo": False,
                "deleted_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return {"success": True, "message": f"Frigorifero N°{numero} rimosso dalla lista"}


@router.delete("/congelatore/{numero}")
async def elimina_congelatore(numero: int, _admin=Depends(require_admin)):
    """Elimina un congelatore dalla lista (soft delete)."""
    result = await db.attrezzature_config.update_one(
        {"tipo": "congelatore", "numero": numero},
        {"$set": {"attivo": False, "deleted_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.matched_count == 0:
        await db.attrezzature_config.insert_one(
            {
                "tipo": "congelatore",
                "numero": numero,
                "nome": f"Congelatore N°{numero}",
                "attivo": False,
                "deleted_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return {"success": True, "message": f"Congelatore N°{numero} rimosso dalla lista"}


# ─── Responsabile dell'apparecchio ────────────────────────────────────────────
# Ogni apparecchio ha un responsabile: e' lui che ne rileva la temperatura, ed
# e' il suo nome che deve comparire sul registro. L'assegnazione vive QUI, sulla
# scheda dell'apparecchio, non su quella del dipendente: gli apparecchi sono 24
# e i dipendenti cambiano, mentre il frigorifero N°3 resta il frigorifero N°3.
# L'identita' resta quella di HR (`operatore_id` = id del dipendente): il nome
# e' solo una copia leggibile per la stampa, e si riallinea a ogni assegnazione.
# Senza assegnazione il responsabile e' il titolare (`ID_TITOLARE`), col nome
# delle Impostazioni (`servizi/responsabile_haccp.py`).


class AssegnaResponsabile(BaseModel):
    operatore_id: str = ""     # id HR, `titolare`, oppure vuoto = nessuna assegnazione (vale il titolare)


@router.get("/assegnazioni")
async def elenco_assegnazioni():
    """Chi e' responsabile di cosa, per la pagina di configurazione e per il
    turno del mattino. Senza assegnazione risponde il titolare; resta «senza
    responsabile» solo l'apparecchio per cui nessun nome e' disponibile."""
    predefinito = await responsabile_predefinito()
    righe = []
    for tipo in ("frigo", "congelatore"):
        for doc in await _get_config(tipo):
            righe.append({
                "tipo": tipo,
                "numero": doc.get("numero"),
                "nome": doc.get("nome", ""),
                **responsabile_apparecchio(doc, predefinito),
            })
    senza = [r for r in righe if not r["operatore_nome"]]
    return {
        "attrezzature": righe,
        "totale": len(righe),
        "assegnate": len(righe) - len(senza),
        "responsabile_predefinito": predefinito.get("operatore_nome") or "",
        "senza_responsabile": [r["nome"] for r in senza],
    }


@router.put("/{tipo}/{numero}/responsabile")
async def assegna_responsabile(
    tipo: str, numero: int, dati: AssegnaResponsabile, _ruolo=Depends(require_permesso("frigoriferi")),
):
    """Assegna il responsabile di un apparecchio: un dipendente di HR, il
    titolare, oppure nessuno (e allora vale il titolare).

    Il nome non si scrive a mano: per un dipendente si prende dall'anagrafica
    HR a partire dall'id, per il titolare dalle Impostazioni, cosi' il
    registro non puo' portare un nome che in azienda non esiste o e' scritto
    in un altro modo."""
    if tipo not in ("frigo", "congelatore"):
        raise HTTPException(status_code=400, detail="Tipo non valido: frigo o congelatore")

    operatore_id = (dati.operatore_id or "").strip()
    nome = ""
    if operatore_id == ID_TITOLARE:
        nome = (await responsabile_predefinito()).get("operatore_nome") or ""
        if not nome:
            raise HTTPException(
                status_code=409,
                detail="Scrivi prima il nome del responsabile HACCP nelle Impostazioni azienda",
            )
    elif operatore_id:
        from app.lotti.routers.tablet_operatori import operatore_per_id

        operatore = await operatore_per_id(operatore_id)
        if not operatore:
            raise HTTPException(
                status_code=404,
                detail="Dipendente non trovato o non in forza: l'assegnazione userebbe un nome che non c'e'",
            )
        nome = operatore.get("nome_completo") or ""

    esito = await db.attrezzature_config.update_one(
        {"tipo": tipo, "numero": numero},
        {"$set": {
            "operatore_id": operatore_id,
            "operatore_nome": nome,
            "operatore_assegnato_il": datetime.now(timezone.utc).isoformat(),
        }},
    )
    if esito.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"{tipo} N°{numero} non trovato")
    return {
        "success": True,
        "tipo": tipo, "numero": numero,
        "operatore_id": operatore_id,
        "operatore_nome": nome,
        "responsabile_predefinito": not operatore_id,
        "message": (f"Responsabile: {nome}" if nome else "Nessuna assegnazione: risponde il titolare"),
    }


# ─── Fuori servizio ───────────────────────────────────────────────────────────
# Quando il responsabile trova un apparecchio guasto lo mette fuori servizio:
# da quel momento il turno del mattino smette di aprirgli le caselle, e il
# registro non si riempie di giornate che nessuno poteva rilevare. Il motivo e
# la data restano scritti — a un'ispezione «il frigo era fermo dal 12 al 19,
# assistenza richiesta il 12» e' una risposta; una colonna vuota no.


class FuoriServizio(BaseModel):
    motivo: str = ""
    assistenza_richiesta: bool = False
    temperatura_rilevata: float | None = None


@router.put("/{tipo}/{numero}/fuori-servizio")
async def metti_fuori_servizio(
    tipo: str, numero: int, dati: FuoriServizio, _ruolo=Depends(require_permesso("frigoriferi")),
):
    if tipo not in ("frigo", "congelatore"):
        raise HTTPException(status_code=400, detail="Tipo non valido: frigo o congelatore")
    if not (dati.motivo or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Serve il motivo: un apparecchio fermo senza motivo scritto "
                   "e' un buco nel registro, non una spiegazione",
        )
    adesso = datetime.now(timezone.utc).isoformat()
    esito = await db.attrezzature_config.update_one(
        {"tipo": tipo, "numero": numero},
        {"$set": {
            "fuori_servizio": True,
            "fuori_servizio_dal": adesso,
            "fuori_servizio_motivo": dati.motivo.strip(),
            "assistenza_richiesta": bool(dati.assistenza_richiesta),
            "temperatura_rilevata_al_guasto": dati.temperatura_rilevata,
            "rientrato_in_servizio_il": None,
        }},
    )
    if esito.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"{tipo} N°{numero} non trovato")
    return {
        "success": True, "tipo": tipo, "numero": numero,
        "message": f"{tipo} N°{numero} fuori servizio: {dati.motivo.strip()}",
    }


@router.put("/{tipo}/{numero}/rientro-in-servizio")
async def rientro_in_servizio(tipo: str, numero: int, _ruolo=Depends(require_permesso("frigoriferi"))):
    """L'apparecchio torna in funzione: il turno ricomincia ad aprirgli le caselle."""
    if tipo not in ("frigo", "congelatore"):
        raise HTTPException(status_code=400, detail="Tipo non valido: frigo o congelatore")
    esito = await db.attrezzature_config.update_one(
        {"tipo": tipo, "numero": numero},
        {"$set": {
            "fuori_servizio": False,
            "rientrato_in_servizio_il": datetime.now(timezone.utc).isoformat(),
            "assistenza_richiesta": False,
        }},
    )
    if esito.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"{tipo} N°{numero} non trovato")
    return {"success": True, "message": f"{tipo} N°{numero} di nuovo in servizio"}
