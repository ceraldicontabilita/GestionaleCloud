"""
Router per la gestione delle Sanificazioni attrezzature e apparecchi refrigeranti.
Registra pulizie giornaliere con aggiornamento automatico.

SEZIONI:
1. Sanificazione Attrezzature (giornaliera)
2. Sanificazione Apparecchi Refrigeranti (frigoriferi/congelatori) - ogni 7-10 giorni

Ogni registrazione e' firmata da chi la esegue (PIN o sessione verificata, vedi
`servizi/registro_haccp.py`). L'operatore designato e' un incarico, non una
firma: non viene mai scritto da solo su una registrazione.

RIFERIMENTI NORMATIVI:
- Reg. CE 852/2004 - Igiene dei prodotti alimentari
- D.Lgs. 193/2007 - Attuazione delle direttive CE

OPERATORE DESIGNATO (incarico, non firma): SANKAPALA ARACHCHILAGE JANANIE AYACHANA DISSANAYAKA
"""

from fastapi import APIRouter, Depends, Query, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict
from datetime import datetime, timezone
import uuid

# Qui c'era `import random`, con una nota che lo dava per «generazione dati demo
# HACCP». Non erano dati demo: erano registrazioni di sanificazione scritte
# nell'archivio vero, con operatore, prodotto usato e un 10% di «non eseguita»
# per farle sembrare autentiche. Le due funzioni che lo usavano erano orfane —
# nessuno le chiamava piu' — e sono state tolte il 20/09/2026.

from html import escape as html_escape

from app.lotti.auth import require_admin
from app.lotti.servizi.haccp_attendibilita import caselle_segnate, non_attendibile_in
from app.lotti.servizi.registro_haccp import (
    conserva_precedente,
    firma_registrazione,
    giorno_registrabile,
    verifica_nessun_futuro,
)

router = APIRouter(prefix="/sanificazione", tags=["Sanificazione"])

# MongoDB connection
# ==================== OPERATORE SANIFICAZIONE ====================

OPERATORE_SANIFICAZIONE = "SANKAPALA ARACHCHILAGE JANANIE AYACHANA DISSANAYAKA"

# ==================== MODELLI ====================


class SchedaSanificazione(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    mese: int
    anno: int
    azienda: str = "Ceraldi Group S.R.L."
    indirizzo: str = "Piazza Carità 14 Napoli"
    area: str = "Sala e Servizi"
    # {attrezzatura: {giorno: "X" o ""}}
    registrazioni: Dict[str, Dict[str, str]] = {}
    operatore_responsabile: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SchedaSanificazioneApparecchi(BaseModel):
    """Scheda per sanificazione frigoriferi e congelatori"""

    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    anno: int
    azienda: str = "Ceraldi Group S.R.L."
    indirizzo: str = "Piazza Carità 14, 80134 Napoli (NA)"
    operatore: str = ""
    # {apparecchio_id: [{data: "DD/MM/YYYY", eseguita: bool, note: str}]}
    registrazioni_frigoriferi: Dict[str, List[dict]] = {}
    registrazioni_congelatori: Dict[str, List[dict]] = {}
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AggiornaSchedaRequest(BaseModel):
    registrazioni: Dict[str, Dict[str, str]]
    operatore: str = ""


# Attrezzature standard da Excel
ATTREZZATURE_SANIFICAZIONE = [
    "Lavabo, Forno, Banchi, Cappa, Frigo, Friggitrice, Affettatrice, Piastra",
    "Pavimentazione",
    "Tagliere, Coltelli",
    "Lavabo, Macch.Espresso, Macinino, Banco Erogatore, Banco Frigo, Scaffali, Vetrine",
    "Attrezzature Laboratorio",
    "Attrezzature Bar",
    "Montacarichi",
    "Deposito",
]

# ==================== HELPER FUNZIONI ====================






async def get_or_create_scheda_apparecchi(anno: int) -> dict:
    """Ottiene o crea la scheda annuale di sanificazione apparecchi"""
    scheda = await db.sanificazione_apparecchi.find_one({"anno": anno}, {"_id": 0})

    if not scheda:
        # A missing annual sheet is an operational obligation, not proof that
        # cleanings happened.  Do not persist a reconstructed calendar.
        return {
            "anno": anno,
            "stato": "DA_VERIFICARE",
            "registrazioni_frigoriferi": {},
            "registrazioni_congelatori": {},
            "nota": "Scheda non ancora registrata: servono evidenze dell'operatore.",
        }

    if "_id" in scheda:
        del scheda["_id"]

    return scheda


async def get_or_create_scheda(mese: int, anno: int) -> dict:
    """Ottiene o crea la scheda mensile di sanificazione attrezzature"""
    scheda = await db.sanificazione_schede.find_one({"mese": mese, "anno": anno}, {"_id": 0})

    if not scheda:
        nuova_scheda = {
            "id": str(uuid.uuid4()),
            "mese": mese,
            "anno": anno,
            "azienda": "Ceraldi Group S.R.L.",
            "indirizzo": "Piazza Carità 14 Napoli",
            "area": "Sala e Servizi",
            "registrazioni": {attr: {} for attr in ATTREZZATURE_SANIFICAZIONE},
            # nessun nome di default: il responsabile e' chi firma le registrazioni
            "operatore_responsabile": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.sanificazione_schede.insert_one(nuova_scheda)
        scheda = nuova_scheda

    if "_id" in scheda:
        del scheda["_id"]

    return scheda


# ==================== ENDPOINTS SANIFICAZIONE ATTREZZATURE ====================


@router.get("")
async def get_sanificazione_lista():
    """GET base — restituisce le ultime 12 schede mensili (anno corrente)"""
    anno = datetime.now().year
    schede = []
    for mese in range(1, 13):
        s = await db.sanificazione_schede.find_one({"anno": anno, "mese": mese}, {"_id": 0})
        if s:
            schede.append(s)
    return schede


@router.get("/scheda/{anno}/{mese}")
async def get_scheda_mensile(anno: int, mese: int):
    """Ottiene la scheda mensile di sanificazione attrezzature"""
    scheda = await get_or_create_scheda(mese, anno)
    return scheda


def _segna_firma(scheda: dict, attrezzatura: str, giorno: int, valore: str, firma: dict) -> None:
    """Chi ha segnato la casella, accanto alla casella (la «X» resta com'era)."""
    firme = scheda.setdefault("firme", {}).setdefault(attrezzatura, {})
    voce = {
        "valore": valore,
        "operatore": firma.get("operatore") or "",
        "dipendente_id": firma.get("dipendente_id") or "",
        "firma_verificata": bool(firma.get("firma_verificata")),
        "firma_via": firma.get("firma_via") or "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    precedente = firme.get(str(giorno))
    if precedente is None and scheda["registrazioni"].get(attrezzatura, {}).get(str(giorno)):
        precedente = {"valore": scheda["registrazioni"][attrezzatura][str(giorno)]}
    conserva_precedente(voce, precedente, firma)
    firme[str(giorno)] = voce
    if firma.get("firma_verificata") and firma.get("operatore"):
        scheda["operatore_responsabile"] = firma["operatore"]


@router.post("/scheda/{anno}/{mese}/registra")
async def registra_sanificazione(
    anno: int, mese: int, giorno: int, attrezzatura: str, eseguita: bool = True,
    operatore: str = "", pin: str = Query(default="", description="PIN personale: e' la firma"),
    request: Request = None,
):
    """Registra una sanificazione per un giorno specifico, con la firma di chi l'ha fatta."""
    giorno_registrabile(anno, mese, giorno)
    firma = await firma_registrazione(request, pin, operatore)
    scheda = await get_or_create_scheda(mese, anno)

    if attrezzatura not in scheda["registrazioni"]:
        scheda["registrazioni"][attrezzatura] = {}

    valore = "X" if eseguita else ""
    _segna_firma(scheda, attrezzatura, giorno, valore, firma)
    scheda["registrazioni"][attrezzatura][str(giorno)] = valore
    scheda["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.sanificazione_schede.update_one({"mese": mese, "anno": anno}, {"$set": scheda})

    return {
        "success": True,
        "message": f"Sanificazione registrata per {attrezzatura} giorno {giorno}",
        "firma_verificata": firma["firma_verificata"],
    }


@router.put("/scheda/{anno}/{mese}")
async def aggiorna_scheda_completa(anno: int, mese: int, data: AggiornaSchedaRequest, _admin=Depends(require_admin)):
    """Aggiorna l'intera scheda mensile"""
    # Riscrittura intera: niente giorni futuri, e il nome dichiarato non
    # diventa il responsabile (non e' una firma verificata).
    verifica_nessun_futuro(data.registrazioni, anno, mese)
    scheda = await get_or_create_scheda(mese, anno)

    scheda["registrazioni"] = data.registrazioni
    scheda["updated_at"] = datetime.now(timezone.utc).isoformat()
    scheda["riscritta_il"] = scheda["updated_at"]
    if data.operatore:
        scheda["operatore_dichiarato"] = data.operatore

    await db.sanificazione_schede.update_one({"mese": mese, "anno": anno}, {"$set": scheda})

    return {"success": True, "message": "Scheda aggiornata"}


@router.post("/scheda/{anno}/{mese}/giorno-completo")
async def registra_giorno_completo(
    anno: int, mese: int, giorno: int, operatore: str = "",
    pin: str = Query(default="", description="PIN personale: e' la firma"),
    request: Request = None,
):
    """Registra tutte le sanificazioni di un giorno (tutte X), firmate da chi le ha fatte."""
    giorno_registrabile(anno, mese, giorno)
    firma = await firma_registrazione(request, pin, operatore)
    scheda = await get_or_create_scheda(mese, anno)

    for attr in scheda["registrazioni"]:
        _segna_firma(scheda, attr, giorno, "X", firma)
        scheda["registrazioni"][attr][str(giorno)] = "X"

    scheda["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.sanificazione_schede.update_one({"mese": mese, "anno": anno}, {"$set": scheda})

    return {
        "success": True,
        "message": f"Tutte le sanificazioni registrate per giorno {giorno}",
        "firma_verificata": firma["firma_verificata"],
    }


@router.get("/attrezzature")
async def get_attrezzature():
    """Lista attrezzature da sanificare"""
    return ATTREZZATURE_SANIFICAZIONE


@router.post("/attrezzature")
async def aggiungi_attrezzatura(nome: str, _admin=Depends(require_admin)):
    """Aggiunge una nuova attrezzatura"""
    if nome not in ATTREZZATURE_SANIFICAZIONE:
        ATTREZZATURE_SANIFICAZIONE.append(nome)
    return {"success": True, "attrezzature": ATTREZZATURE_SANIFICAZIONE}


@router.get("/storico")
async def get_storico(anno: int = None):
    """Ottiene lo storico delle schede"""
    query = {}
    if anno:
        query["anno"] = anno

    schede = (
        await db.sanificazione_schede.find(query, {"_id": 0})
        .sort([("anno", -1), ("mese", -1)])
        .to_list(100)
    )
    return schede




# ==================== ENDPOINTS SANIFICAZIONE APPARECCHI REFRIGERANTI ====================


@router.get("/apparecchi/{anno}")
async def get_scheda_apparecchi(anno: int):
    """
    Ottiene la scheda annuale di sanificazione apparecchi refrigeranti.
    Include date di pulizia per frigoriferi e congelatori con intervallo 7-10 giorni.
    """
    scheda = await get_or_create_scheda_apparecchi(anno)
    return scheda


@router.get("/apparecchi/{anno}/frigorifero/{numero}")
async def get_sanificazioni_frigorifero(anno: int, numero: int):
    """Ottiene le sanificazioni di un singolo frigorifero"""
    scheda = await get_or_create_scheda_apparecchi(anno)

    chiave = str(numero)
    sanificazioni = scheda.get("registrazioni_frigoriferi", {}).get(chiave, [])

    return {
        "anno": anno,
        "frigorifero": numero,
        "nome": f"Frigorifero N°{numero}",
        "operatore_designato": OPERATORE_SANIFICAZIONE,
        "sanificazioni": sanificazioni,
        "totale": len(sanificazioni),
        "eseguite": len([s for s in sanificazioni if s.get("eseguita", False)]),
        "non_eseguite": len([s for s in sanificazioni if not s.get("eseguita", True)]),
    }


@router.get("/apparecchi/{anno}/congelatore/{numero}")
async def get_sanificazioni_congelatore(anno: int, numero: int):
    """Ottiene le sanificazioni di un singolo congelatore"""
    scheda = await get_or_create_scheda_apparecchi(anno)

    chiave = str(numero)
    sanificazioni = scheda.get("registrazioni_congelatori", {}).get(chiave, [])

    return {
        "anno": anno,
        "congelatore": numero,
        "nome": f"Congelatore N°{numero}",
        "operatore_designato": OPERATORE_SANIFICAZIONE,
        "sanificazioni": sanificazioni,
        "totale": len(sanificazioni),
        "eseguite": len([s for s in sanificazioni if s.get("eseguita", False)]),
        "non_eseguite": len([s for s in sanificazioni if not s.get("eseguita", True)]),
    }


@router.get("/apparecchi/{anno}/mese/{mese}")
async def get_sanificazioni_mese(anno: int, mese: int):
    """Ottiene tutte le sanificazioni apparecchi per un mese specifico"""
    scheda = await get_or_create_scheda_apparecchi(anno)

    sanificazioni_mese = {"frigoriferi": {}, "congelatori": {}}

    # Filtra frigoriferi per mese
    for chiave, sanifs in scheda.get("registrazioni_frigoriferi", {}).items():
        sanifs_mese = [s for s in sanifs if s.get("mese") == mese]
        if sanifs_mese:
            sanificazioni_mese["frigoriferi"][chiave] = sanifs_mese

    # Filtra congelatori per mese
    for chiave, sanifs in scheda.get("registrazioni_congelatori", {}).items():
        sanifs_mese = [s for s in sanifs if s.get("mese") == mese]
        if sanifs_mese:
            sanificazioni_mese["congelatori"][chiave] = sanifs_mese

    return {
        "anno": anno,
        "mese": mese,
        "operatore_designato": OPERATORE_SANIFICAZIONE,
        "sanificazioni": sanificazioni_mese,
    }


@router.post("/apparecchi/{anno}/registra")
async def registra_sanificazione_apparecchio(
    anno: int,
    tipo: str = Query(..., description="frigorifero o congelatore"),
    numero: int = Query(..., description="Numero apparecchio (1-12)"),
    giorno: int = Query(...),
    mese: int = Query(...),
    eseguita: bool = Query(default=True),
    note: str = Query(default=""),
    prodotto: str = Query(default="", description="Prodotto usato, come scritto da chi sanifica"),
    operatore: str = Query(default=""),
    pin: str = Query(default="", description="PIN personale: e' la firma"),
    request: Request = None,
):
    """Registra una sanificazione di un apparecchio, firmata da chi l'ha eseguita.

    Prima l'operatore era sempre quello designato e il prodotto sempre
    «Detergente alimentare professionale», chiunque avesse sanificato e con
    qualunque prodotto: il registro attestava una persona e un prodotto che
    nessuno aveva dichiarato.
    """
    if tipo not in ("frigorifero", "congelatore"):
        raise HTTPException(status_code=422, detail="tipo deve essere frigorifero o congelatore")
    giorno_registrabile(anno, mese, giorno)
    firma = await firma_registrazione(request, pin, operatore)
    scheda = await get_or_create_scheda_apparecchi(anno)
    if scheda.get("stato") == "DA_VERIFICARE":
        # prima registrazione dell'anno: la scheda nasce qui, vuota
        scheda = {
            "id": str(uuid.uuid4()),
            "anno": anno,
            "operatore": "",
            "registrazioni_frigoriferi": {},
            "registrazioni_congelatori": {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.sanificazione_apparecchi.insert_one(dict(scheda))

    chiave = str(numero)
    data_str = f"{giorno:02d}/{mese:02d}/{anno}"

    nuova_registrazione = {
        "data": data_str,
        "giorno": giorno,
        "mese": mese,
        "eseguita": eseguita,
        "operatore": firma.get("operatore") or "",
        "dipendente_id": firma.get("dipendente_id") or "",
        "firma_verificata": bool(firma.get("firma_verificata")),
        "firma_via": firma.get("firma_via") or "",
        "note": note,
        "prodotto": prodotto.strip() if eseguita else "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if tipo == "frigorifero":
        if chiave not in scheda["registrazioni_frigoriferi"]:
            scheda["registrazioni_frigoriferi"][chiave] = []
        scheda["registrazioni_frigoriferi"][chiave].append(nuova_registrazione)
    else:
        if chiave not in scheda["registrazioni_congelatori"]:
            scheda["registrazioni_congelatori"][chiave] = []
        scheda["registrazioni_congelatori"][chiave].append(nuova_registrazione)

    scheda["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.sanificazione_apparecchi.update_one({"anno": anno}, {"$set": scheda})

    return {
        "success": True,
        "message": f"Sanificazione {tipo} N°{numero} registrata per {data_str}",
        "eseguita": eseguita,
    }


@router.post("/apparecchi/{anno}/rigenera")
async def rigenera_calendario_apparecchi(anno: int, _admin=Depends(require_admin)):
    raise HTTPException(
        status_code=410,
        detail="Bloccato: il calendario non puo attestare esiti o operatori non verificati.",
    )


@router.get("/operatore")
async def get_operatore():
    """Restituisce l'operatore designato per la sanificazione"""
    return {
        "operatore": OPERATORE_SANIFICAZIONE,
        "ruolo": "Addetto Sanificazione e Lavaggio",
        "mansioni": [
            "Sanificazione apparecchiature refrigeranti",
            "Pulizia locali e attrezzature",
            "Registrazione interventi",
        ],
    }


@router.get("/statistiche/{anno}")
async def get_statistiche_sanificazione(anno: int):
    """Statistiche annuali sulle sanificazioni"""
    scheda = await get_or_create_scheda_apparecchi(anno)

    # Conta sanificazioni frigoriferi
    tot_frigo = 0
    eseguite_frigo = 0
    for sanifs in scheda.get("registrazioni_frigoriferi", {}).values():
        tot_frigo += len(sanifs)
        eseguite_frigo += len([s for s in sanifs if s.get("eseguita", False)])

    # Conta sanificazioni congelatori
    tot_cong = 0
    eseguite_cong = 0
    for sanifs in scheda.get("registrazioni_congelatori", {}).values():
        tot_cong += len(sanifs)
        eseguite_cong += len([s for s in sanifs if s.get("eseguita", False)])

    return {
        "anno": anno,
        "operatore_designato": OPERATORE_SANIFICAZIONE,
        "frigoriferi": {
            "totale_sanificazioni": tot_frigo,
            "eseguite": eseguite_frigo,
            "non_eseguite": tot_frigo - eseguite_frigo,
            "percentuale_completamento": round(
                (eseguite_frigo / tot_frigo * 100) if tot_frigo > 0 else 0, 1
            ),
        },
        "congelatori": {
            "totale_sanificazioni": tot_cong,
            "eseguite": eseguite_cong,
            "non_eseguite": tot_cong - eseguite_cong,
            "percentuale_completamento": round(
                (eseguite_cong / tot_cong * 100) if tot_cong > 0 else 0, 1
            ),
        },
        "totale": {
            "sanificazioni_programmate": tot_frigo + tot_cong,
            "sanificazioni_eseguite": eseguite_frigo + eseguite_cong,
            "percentuale_completamento": round(
                (
                    ((eseguite_frigo + eseguite_cong) / (tot_frigo + tot_cong) * 100)
                    if (tot_frigo + tot_cong) > 0
                    else 0
                ),
                1,
            ),
        },
    }


# ==================== EXPORT PDF SANIFICAZIONE ====================

from fastapi.responses import HTMLResponse

from app.lotti.db import database as db

MESI_IT = [
    "Gennaio",
    "Febbraio",
    "Marzo",
    "Aprile",
    "Maggio",
    "Giugno",
    "Luglio",
    "Agosto",
    "Settembre",
    "Ottobre",
    "Novembre",
    "Dicembre",
]


@router.get("/export-pdf/{anno}/{mese}", response_class=HTMLResponse)
async def export_pdf_sanificazione(anno: int, mese: int):
    """
    Genera report PDF della sanificazione attrezzature per il mese.
    Conforme a Reg. CE 852/2004.
    """
    scheda = await db.sanificazione_schede.find_one({"mese": mese, "anno": anno}, {"_id": 0})

    if not scheda:
        scheda = {"registrazioni": {}}

    registrazioni = scheda.get("registrazioni", {})
    firme = scheda.get("firme") or {}
    segnate = caselle_segnate(scheda)
    # In stampa firma chi ha firmato davvero (PIN o sessione verificata), non
    # l'operatore designato: prima ogni mese usciva col suo nome anche vuoto.
    firmatari = sorted({
        v.get("operatore")
        for righe in (scheda.get("firme") or {}).values()
        for v in (righe or {}).values()
        if isinstance(v, dict) and v.get("firma_verificata") and v.get("operatore")
    })
    firmato_da = ", ".join(firmatari) if firmatari else "nessuna firma verificata"

    # Giorni nel mese
    if mese in [1, 3, 5, 7, 8, 10, 12]:
        num_giorni = 31
    elif mese in [4, 6, 9, 11]:
        num_giorni = 30
    else:
        num_giorni = 29 if (anno % 4 == 0 and anno % 100 != 0) or (anno % 400 == 0) else 28

    html = f"""
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <title>Registro Sanificazione {MESI_IT[mese-1]} {anno}</title>
        <style>
            @page {{ size: A4 landscape; margin: 10mm; }}
            @media print {{ .no-print {{ display: none; }} }}
            body {{ font-family: Arial, sans-serif; font-size: 9pt; color: #333; }}
            .header {{ text-align: center; border-bottom: 3px solid #1976d2; padding-bottom: 10px; margin-bottom: 15px; }}
            .header h1 {{ color: #1976d2; margin: 0; font-size: 16pt; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ border: 1px solid #ddd; padding: 4px; text-align: center; font-size: 8pt; }}
            th {{ background: #1976d2; color: white; }}
            .check {{ background: #e8f5e9; color: #2e7d32; font-weight: bold; }}
            .nd {{ background: #f4f1ea; color: #8a6f47; font-size: 9px; font-weight: bold; }}
            .na {{ background: #faf7f0; color: #6b6358; border: 1px dashed #b8ad99; font-size: 8px; font-style: italic; }}
            .btn-print {{ padding: 10px 25px; background: #1976d2; color: white; border: none; border-radius: 5px; cursor: pointer; }}
            .footer {{ margin-top: 20px; font-size: 8pt; color: #999; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📋 REGISTRO SANIFICAZIONE ATTREZZATURE</h1>
            <p><strong>Ceraldi Group S.R.L.</strong> | {MESI_IT[mese-1]} {anno}</p>
            <p>Firmato da: {html_escape(firmato_da)}</p>
        </div>
        
        <table>
            <tr>
                <th style="width:25%">Attrezzatura</th>
    """

    # Header giorni
    for g in range(1, num_giorni + 1):
        html += f"<th>{g}</th>"
    html += "</tr>"

    # Righe attrezzature
    for attr in ATTREZZATURE_SANIFICAZIONE:
        giorni_attr = registrazioni.get(attr, {})
        html += f"<tr><td style='text-align:left'><strong>{attr}</strong></td>"
        for g in range(1, num_giorni + 1):
            valore = giorni_attr.get(str(g), "")
            # "N/D" = giorno passato senza NESSUNA registrazione, dichiarato dal
            # recupero automatico: davanti a un controllo "non fatto" e "nessuno
            # l'ha registrato" sono due cose diverse, e la cella vuota non lo
            # diceva (AUDIT_REGISTRI_STAMPE §4).
            firma = (firme.get(attr) or {}).get(str(g))
            if valore in ("X", "x") and non_attendibile_in(segnate, (attr, str(g)), firma):
                # GC-02h: «X» senza firma verificata, conservata ma non attendibile
                html += "<td class='na' title='Registrazione senza firma verificata'>n.a.</td>"
                continue
            if valore == "X":
                classe = "check"
            elif valore == "N/D":
                classe = "nd"
            else:
                classe = ""
            html += f"<td class='{classe}'>{valore}</td>"
        html += "</tr>"

    html += f"""
        </table>
        
        <div class="footer">
            <p><strong>X</strong> = sanificazione eseguita e registrata &nbsp;·&nbsp;
               <strong>N/D</strong> = nessuna registrazione per quel giorno
               (sistema non attivo) &nbsp;·&nbsp; cella vuota = giorno non ancora chiuso</p>
            <p><strong>n.a.</strong> = valore in archivio senza firma verificata, non attendibile
               (conservato nel sistema)</p>
            <p>Conforme a Reg. CE 852/2004 - Igiene prodotti alimentari</p>
            <p>Generato il: {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
        </div>
        
        <div class="no-print" style="text-align:center; margin-top:20px;">
            <button onclick="window.print()" class="btn-print">🖨️ Stampa PDF</button>
        </div>
    </body>
    </html>
    """

    return HTMLResponse(content=html)


# ─────────────────────────────────────────────────────────────────────────────
# PIANO DI SANIFICAZIONE — ogni quanto si lava cosa, e con quale prodotto
#
# Il registro diceva CHE una pulizia era stata fatta, mai ogni quanto andava
# fatta ne' con cosa. Davanti a un'ispezione il piano di sanificazione e'
# proprio questo: area, frequenza, prodotto, diluizione, tempo di contatto.
#
# Frequenza e prodotti NON hanno un valore di ripiego: li stabilisce il
# responsabile. Un detergente scritto a caso su un manuale HACCP e' peggio di
# una casella vuota — rimanda a una scheda di sicurezza che non c'entra.
# ─────────────────────────────────────────────────────────────────────────────

FREQUENZE = {
    # Il manuale la usa per utensili e taglieri. Il registro segna i giorni,
    # non gli utilizzi: puo' provare che oggi la pulizia c'e' stata, non che
    # c'e' stata dopo ogni uso. Qui vale come «almeno una volta nel giorno».
    "dopo_ogni_uso": {"etichetta": "Dopo ogni utilizzo", "giorni": 1},
    "giornaliera": {"etichetta": "Ogni giorno", "giorni": 1},
    "due_giorni": {"etichetta": "Ogni due giorni", "giorni": 2},
    "settimanale": {"etichetta": "Ogni settimana", "giorni": 7},
    "quindicinale": {"etichetta": "Ogni quindici giorni", "giorni": 15},
    "mensile": {"etichetta": "Ogni mese", "giorni": 30},
}

_DOC_PIANO = "piano_sanificazione"


class VoceDelPiano(BaseModel):
    area: str
    frequenza: str = ""          # una chiave di FREQUENZE
    prodotto: str = ""           # nome commerciale del detergente/sanificante
    diluizione: str = ""         # es. "2%" o "20 ml/l"
    tempo_contatto: str = ""     # es. "5 minuti"
    note: str = ""


async def _piano_salvato() -> dict:
    doc = await db.impostazioni.find_one({"_id": _DOC_PIANO}) or {}
    return doc.get("voci", {}) if isinstance(doc.get("voci"), dict) else {}


@router.get("/piano")
async def leggi_piano_sanificazione():
    """Il piano per area: frequenza, prodotto, diluizione, tempo di contatto.

    Le aree sono quelle vere del registro. Quelle non ancora compilate
    escono con i campi vuoti e finiscono in `da_completare`: sono le righe
    che in stampa resterebbero senza piano.
    """
    from app.lotti.servizi.sanificazione_catalogo import DETERGENTI, FREQUENZA_SUGGERITA

    salvato = await _piano_salvato()
    voci, da_completare = [], []
    for area in ATTREZZATURE_SANIFICAZIONE:
        voce = salvato.get(area) or {}
        suggerita, perche = FREQUENZA_SUGGERITA.get(area, ("", ""))
        riga = {
            "area": area,
            "frequenza": voce.get("frequenza", ""),
            "frequenza_etichetta": FREQUENZE.get(voce.get("frequenza", ""), {}).get("etichetta", ""),
            "prodotto": voce.get("prodotto", ""),
            "diluizione": voce.get("diluizione", ""),
            "tempo_contatto": voce.get("tempo_contatto", ""),
            "note": voce.get("note", ""),
            # Proposta, non impostazione: il piano resta vuoto finche' non lo
            # conferma il responsabile. Dove il manuale non dice niente
            # (montacarichi, deposito) non c'e' nessuna proposta.
            "frequenza_suggerita": suggerita,
            "frequenza_suggerita_fonte": perche,
        }
        voci.append(riga)
        if not riga["frequenza"] or not riga["prodotto"]:
            da_completare.append(area)
    return {
        "voci": voci,
        "frequenze_disponibili": [
            {"id": k, "etichetta": v["etichetta"], "giorni": v["giorni"]}
            for k, v in FREQUENZE.items()
        ],
        # Le tipologie che il manuale HACCP dell'attivita' gia' prescrive, con
        # pH, diluizione e tempo di contatto dove li dichiara. Il nome
        # commerciale lo scrive il responsabile: e' quello che rimanda alla
        # scheda di sicurezza vera.
        "detergenti_dal_manuale": DETERGENTI,
        "da_completare": da_completare,
        "completo": not da_completare,
    }


@router.put("/piano")
async def salva_piano_sanificazione(
    voci: List[VoceDelPiano], _admin=Depends(require_admin),
):
    """Imposta frequenza e prodotto per una o piu' aree."""
    salvato = await _piano_salvato()
    aggiornate = []
    for voce in voci:
        area = (voce.area or "").strip()
        if area not in ATTREZZATURE_SANIFICAZIONE:
            raise HTTPException(
                status_code=400,
                detail=f"Area non riconosciuta: «{area}». Sono quelle del registro.",
            )
        if voce.frequenza and voce.frequenza not in FREQUENZE:
            raise HTTPException(
                status_code=400,
                detail=f"Frequenza non valida: «{voce.frequenza}». "
                       f"Ammesse: {', '.join(FREQUENZE)}",
            )
        salvato[area] = {
            "frequenza": voce.frequenza,
            "prodotto": (voce.prodotto or "").strip(),
            "diluizione": (voce.diluizione or "").strip(),
            "tempo_contatto": (voce.tempo_contatto or "").strip(),
            "note": (voce.note or "").strip(),
            "aggiornato_il": datetime.now(timezone.utc).isoformat(),
        }
        aggiornate.append(area)
    await db.impostazioni.update_one(
        {"_id": _DOC_PIANO},
        {"$set": {"_id": _DOC_PIANO, "voci": salvato,
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"success": True, "aggiornate": aggiornate}


@router.get("/scadute")
async def sanificazioni_scadute():
    """Cosa e' in ritardo rispetto al piano, oggi.

    Una pulizia «ogni due giorni» fatta cinque giorni fa e' in ritardo: il
    registro da solo non lo diceva, perche' segnava soltanto i giorni fatti.
    Le aree senza piano non sono ne' in regola ne' in ritardo: sono da
    compilare, e si dicono a parte.
    """
    from datetime import date as _date

    piano = await _piano_salvato()
    oggi = _date.today()
    scheda = await db.sanificazione_schede.find_one(
        {"anno": oggi.year, "mese": oggi.month},
        {"_id": 0, "registrazioni": 1, "firme": 1, "non_attendibili": 1},
    ) or {}
    registrazioni = scheda.get("registrazioni", {})
    firme = scheda.get("firme") or {}
    segnate = caselle_segnate(scheda)

    in_ritardo, senza_piano, in_regola = [], [], []
    for area in ATTREZZATURE_SANIFICAZIONE:
        voce = piano.get(area) or {}
        frequenza = voce.get("frequenza")
        if not frequenza:
            senza_piano.append(area)
            continue
        giorni_previsti = FREQUENZE[frequenza]["giorni"]
        fatti = [
            int(g) for g, v in (registrazioni.get(area) or {}).items()
            if str(g).isdigit() and v in ("X", "x", "1", True)
            and not non_attendibile_in(segnate, (area, str(g)), (firme.get(area) or {}).get(str(g)))
        ]
        ultimo = max(fatti) if fatti else None
        giorni_passati = (oggi.day - ultimo) if ultimo else None
        riga = {"area": area, "frequenza": frequenza,
                "ultima_pulizia_giorno": ultimo, "giorni_passati": giorni_passati,
                "prodotto": voce.get("prodotto", "")}
        if ultimo is None or giorni_passati > giorni_previsti:
            in_ritardo.append(riga)
        else:
            in_regola.append(riga)
    return {"data": oggi.isoformat(), "in_ritardo": in_ritardo,
            "in_regola": in_regola, "senza_piano": senza_piano}
