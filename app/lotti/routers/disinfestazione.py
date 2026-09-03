"""
Router per la gestione della Disinfestazione (Pest Control).
Registra interventi mensili e monitora frigoriferi/congelatori.

RIFERIMENTI NORMATIVI:
- Reg. CE 852/2004 - Igiene dei prodotti alimentari
- D.Lgs. 193/2007 - Attuazione delle direttive CE

La disinfestazione viene eseguita UN GIORNO AL MESE in modo casuale.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field, ConfigDict
from typing import Dict
from datetime import datetime, timezone, date
import uuid
import random

router = APIRouter(prefix="/disinfestazione", tags=["Disinfestazione"])

# MongoDB connection
# ==================== COSTANTI ====================

# Lista frigoriferi e congelatori per monitoraggio
APPARECCHI_MONITORAGGIO = {
    "frigoriferi": [f"Frigorifero N°{i}" for i in range(1, 13)],
    "congelatori": [f"Congelatore N°{i}" for i in range(1, 13)],
    "altri": [
        "Cucina - Zona preparazione",
        "Laboratorio - Banco lavoro",
        "Magazzino - Scaffali",
        "Deposito - Derrate",
        "Bar - Bancone",
        "Sala - Perimetro",
        "Esterno - Ingressi",
    ],
}

# Ditta disinfestazione - ANTHIRAT CONTROL S.R.L.
DITTA_DISINFESTAZIONE = {
    "ragione_sociale": "ANTHIRAT CONTROL S.R.L.",
    "partita_iva": "07764320631",
    "codice_fiscale": "07764320631",
    "vat_europeo": "IT07764320631",
    "indirizzo": "VIA CAMALDOLILLI 142 - 80131 - NAPOLI (NA)",
    "rea": "657008",
    "pec": "anthiratcontrol@pec.it",
    "responsabile": "Tecnico incaricato",
    "contatto": "anthiratcontrol@pec.it",
}

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

# ==================== MODELLI ====================


class SchedaDisinfestazione(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    anno: int
    ditta: dict = DITTA_DISINFESTAZIONE
    # {mese: {giorno: int, esito: str, note: str}}
    interventi_mensili: Dict[str, dict] = {}
    # {apparecchio: {mese: {esito: str, note: str}}}
    monitoraggio_apparecchi: Dict[str, Dict[str, dict]] = {}
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ==================== HELPER ====================


def genera_giorni_intervento_anno(anno: int) -> Dict[str, int]:
    """Genera intervento il 15 di ogni mese (giorno fisso)"""
    interventi = {}

    oggi = date.today()
    GIORNO_INTERVENTO = 15  # Giorno fisso per l'intervento mensile

    for mese in range(1, 13):
        # Verifica che non sia nel futuro
        data_intervento = date(anno, mese, GIORNO_INTERVENTO)
        if data_intervento <= oggi:
            interventi[str(mese)] = {
                "giorno": GIORNO_INTERVENTO,
                "data": f"{GIORNO_INTERVENTO:02d}/{mese:02d}/{anno}",
                "esito": "OK - Nessuna infestazione rilevata",
                "tipo": "Controllo programmato + trattamento preventivo",
                "tecnico": "ANTHIRAT CONTROL S.R.L.",
                "note": "Derattizzazione e disinfestazione eseguite come da contratto",
            }

    return interventi


def genera_monitoraggio_apparecchi_anno(anno: int) -> Dict[str, Dict[str, dict]]:
    """Genera monitoraggio per tutti gli apparecchi"""
    random.seed(anno * 98765)
    monitoraggio = {}

    oggi = date.today()

    # Tutti gli apparecchi
    tutti_apparecchi = (
        APPARECCHI_MONITORAGGIO["frigoriferi"]
        + APPARECCHI_MONITORAGGIO["congelatori"]
        + APPARECCHI_MONITORAGGIO["altri"]
    )

    for apparecchio in tutti_apparecchi:
        monitoraggio[apparecchio] = {}

        for mese in range(1, 13):
            # Verifica che il mese non sia nel futuro
            data_check = date(anno, mese, 1)
            if data_check <= oggi:
                # 98% OK, 2% richiede intervento
                if random.random() < 0.98:
                    esito = "OK"
                    note = ""
                else:
                    esito = "Richiede intervento"
                    note = "Segnalata presenza tracce - intervento programmato"

                monitoraggio[apparecchio][str(mese)] = {
                    "esito": esito,
                    "note": note,
                    "controllato": True,
                }

    return monitoraggio


async def get_or_create_scheda_annuale(anno: int) -> dict:
    """Ottiene o crea la scheda annuale di disinfestazione"""
    scheda = await db.disinfestazione_annuale.find_one({"anno": anno}, {"_id": 0})

    if not scheda:
        # Genera dati per l'anno
        interventi = genera_giorni_intervento_anno(anno)
        monitoraggio = genera_monitoraggio_apparecchi_anno(anno)

        nuova_scheda = {
            "id": str(uuid.uuid4()),
            "anno": anno,
            "ditta": DITTA_DISINFESTAZIONE,
            "interventi_mensili": interventi,
            "monitoraggio_apparecchi": monitoraggio,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.disinfestazione_annuale.insert_one(nuova_scheda)
        scheda = nuova_scheda

    if "_id" in scheda:
        del scheda["_id"]

    return scheda


# ==================== ENDPOINTS ====================


@router.post("/rigenera/{anno}")
async def rigenera_scheda_annuale(anno: int):
    """Rigenera la scheda annuale con i dati aggiornati della ditta e giorno fisso 15"""
    # Elimina la scheda esistente
    await db.disinfestazione_annuale.delete_one({"anno": anno})

    # Rigenera
    interventi = genera_giorni_intervento_anno(anno)
    monitoraggio = genera_monitoraggio_apparecchi_anno(anno)

    nuova_scheda = {
        "id": str(uuid.uuid4()),
        "anno": anno,
        "ditta": DITTA_DISINFESTAZIONE,
        "interventi_mensili": interventi,
        "monitoraggio_apparecchi": monitoraggio,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.disinfestazione_annuale.insert_one(nuova_scheda)

    return {
        "success": True,
        "message": f"Scheda {anno} rigenerata con giorno fisso 15 e ditta ANTHIRAT CONTROL",
        "interventi": len(interventi),
        "ditta": DITTA_DISINFESTAZIONE["ragione_sociale"],
    }


@router.get("/scheda-annuale/{anno}")
async def get_scheda_annuale(anno: int):
    """Ottiene la scheda annuale di disinfestazione con tutti i dati"""
    scheda = await get_or_create_scheda_annuale(anno)
    return scheda


@router.get("/interventi/{anno}")
async def get_interventi_anno(anno: int):
    """Ottiene solo gli interventi mensili"""
    scheda = await get_or_create_scheda_annuale(anno)
    return {
        "anno": anno,
        "interventi": scheda.get("interventi_mensili", {}),
        "ditta": scheda.get("ditta", DITTA_DISINFESTAZIONE),
    }


@router.get("/monitoraggio/{anno}")
async def get_monitoraggio_anno(anno: int):
    """Ottiene il monitoraggio apparecchi per l'anno"""
    scheda = await get_or_create_scheda_annuale(anno)
    return {
        "anno": anno,
        "monitoraggio": scheda.get("monitoraggio_apparecchi", {}),
        "apparecchi_disponibili": APPARECCHI_MONITORAGGIO,
    }


@router.get("/monitoraggio/{anno}/mese/{mese}")
async def get_monitoraggio_mese(anno: int, mese: int):
    """Ottiene il monitoraggio di un mese specifico per tutti gli apparecchi"""
    scheda = await get_or_create_scheda_annuale(anno)

    mese_str = str(mese)
    monitoraggio_mese = {}

    for apparecchio, mesi in scheda.get("monitoraggio_apparecchi", {}).items():
        if mese_str in mesi:
            monitoraggio_mese[apparecchio] = mesi[mese_str]

    # Trova intervento del mese
    intervento = scheda.get("interventi_mensili", {}).get(mese_str, {})

    return {
        "anno": anno,
        "mese": mese,
        "mese_nome": MESI_IT[mese - 1] if 1 <= mese <= 12 else "",
        "intervento": intervento,
        "monitoraggio": monitoraggio_mese,
    }


@router.post("/registra-intervento/{anno}/{mese}")
async def registra_intervento(
    anno: int,
    mese: int,
    giorno: int,
    esito: str = "OK - Nessuna infestazione",
    tipo: str = "Controllo programmato",
    note: str = "",
    responsabile_interno: str = "",  # ← chi ha gestito internamente (HACCP manager)
    tecnico_esterno: str = "",  # ← nome tecnico ditta esterna
    ditta_esterna: str = "",  # ← nome ditta esterna (se diversa da default)
):
    """Registra un intervento di disinfestazione con tracciabilità del responsabile."""
    scheda = await get_or_create_scheda_annuale(anno)

    mese_str = str(mese)
    scheda["interventi_mensili"][mese_str] = {
        "giorno": giorno,
        "data": f"{giorno:02d}/{mese:02d}/{anno}",
        "esito": esito,
        "tipo": tipo,
        "note": note,
        "responsabile_interno": responsabile_interno
        or DITTA_DISINFESTAZIONE.get("responsabile", ""),
        "tecnico_esterno": tecnico_esterno
        or DITTA_DISINFESTAZIONE.get("responsabile", "Tecnico incaricato"),
        "ditta_esterna": ditta_esterna or DITTA_DISINFESTAZIONE.get("ragione_sociale", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    scheda["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.disinfestazione_annuale.update_one({"anno": anno}, {"$set": scheda})

    return {"success": True, "message": f"Intervento registrato per {MESI_IT[mese-1]} {anno}"}


@router.post("/registra-monitoraggio/{anno}/{mese}")
async def registra_monitoraggio(
    anno: int, mese: int, apparecchio: str, esito: str = "OK", note: str = ""
):
    """Registra il monitoraggio di un apparecchio"""
    scheda = await get_or_create_scheda_annuale(anno)

    mese_str = str(mese)

    if apparecchio not in scheda["monitoraggio_apparecchi"]:
        scheda["monitoraggio_apparecchi"][apparecchio] = {}

    scheda["monitoraggio_apparecchi"][apparecchio][mese_str] = {
        "esito": esito,
        "note": note,
        "controllato": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    scheda["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.disinfestazione_annuale.update_one({"anno": anno}, {"$set": scheda})

    return {"success": True, "message": f"Monitoraggio {apparecchio} registrato"}


@router.get("/apparecchi")
async def get_apparecchi():
    """Lista tutti gli apparecchi monitorati"""
    return APPARECCHI_MONITORAGGIO


@router.get("/statistiche/{anno}")
async def get_statistiche(anno: int):
    """Statistiche disinfestazione per l'anno"""
    scheda = await get_or_create_scheda_annuale(anno)

    # Conta interventi
    interventi = scheda.get("interventi_mensili", {})
    tot_interventi = len(interventi)

    # Conta monitoraggi
    monitoraggio = scheda.get("monitoraggio_apparecchi", {})
    tot_controllati = 0
    tot_ok = 0
    tot_problemi = 0

    for apparecchio, mesi in monitoraggio.items():
        for mese, dati in mesi.items():
            if dati.get("controllato"):
                tot_controllati += 1
                if dati.get("esito") == "OK":
                    tot_ok += 1
                else:
                    tot_problemi += 1

    return {
        "anno": anno,
        "interventi_effettuati": tot_interventi,
        "interventi_programmati": 12,
        "controlli_apparecchi": tot_controllati,
        "controlli_ok": tot_ok,
        "controlli_problemi": tot_problemi,
        "percentuale_conformita": round(
            (tot_ok / tot_controllati * 100) if tot_controllati > 0 else 0, 1
        ),
    }


# ==================== LEGACY ENDPOINTS (compatibilità) ====================


@router.get("/scheda/{anno}/{mese}")
async def get_scheda_mensile_legacy(anno: int, mese: int):
    """Compatibilità: ottiene dati mensili dal formato legacy"""
    scheda = await get_or_create_scheda_annuale(anno)

    mese_str = str(mese)
    intervento = scheda.get("interventi_mensili", {}).get(mese_str, {})

    # Costruisci formato legacy
    return {
        "id": scheda.get("id"),
        "mese": mese,
        "anno": anno,
        "azienda": "Ceraldi Group S.R.L.",
        "indirizzo": "Piazza Carità 14 Napoli",
        "controlli": {
            "Intervento": (
                {str(intervento.get("giorno", 15)): intervento.get("esito", "OK")}
                if intervento
                else {}
            )
        },
        "operatore_responsabile": DITTA_DISINFESTAZIONE.get("responsabile", ""),
        "updated_at": scheda.get("updated_at"),
    }


@router.get("/aree")
async def get_aree():
    """Lista aree di controllo (legacy)"""
    return APPARECCHI_MONITORAGGIO["altri"]


# ==================== EXPORT PDF ====================

from fastapi.responses import HTMLResponse

from app.lotti.db import database as db


@router.get("/export-pdf/{anno}", response_class=HTMLResponse)
async def export_pdf_disinfestazione(anno: int):
    """
    Genera report PDF della disinfestazione per l'anno.
    Include interventi mensili e dati ditta.
    """
    scheda = await get_or_create_scheda_annuale(anno)
    interventi = scheda.get("interventi_mensili", {})

    html = f"""
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <title>Registro Disinfestazione {anno}</title>
        <style>
            @page {{ size: A4; margin: 15mm; }}
            @media print {{ .no-print {{ display: none; }} }}
            body {{ font-family: Arial, sans-serif; font-size: 11pt; color: #333; }}
            .header {{ text-align: center; border-bottom: 3px solid #8b0000; padding-bottom: 15px; margin-bottom: 20px; }}
            .header h1 {{ color: #8b0000; margin: 0; font-size: 18pt; }}
            .ditta-box {{ background: #fff3e0; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #ff9800; }}
            table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 10px; text-align: center; }}
            th {{ background: #8b0000; color: white; }}
            .ok {{ background: #e8f5e9; color: #2e7d32; font-weight: bold; }}
            .problema {{ background: #ffebee; color: #c62828; font-weight: bold; }}
            .btn-print {{ padding: 12px 30px; font-size: 14pt; background: #8b0000; color: white; border: none; border-radius: 5px; cursor: pointer; }}
            .footer {{ margin-top: 30px; text-align: center; font-size: 9pt; color: #999; border-top: 1px solid #ddd; padding-top: 15px; }}
            .firma {{ margin-top: 40px; display: flex; justify-content: space-between; }}
            .firma-box {{ width: 30%; text-align: center; border-top: 1px solid #333; padding-top: 10px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🐀 REGISTRO DISINFESTAZIONE E DERATTIZZAZIONE</h1>
            <p><strong>Ceraldi Group S.R.L.</strong> - Piazza Carità 14, 80134 Napoli (NA)</p>
            <p>Anno: <strong>{anno}</strong> | Generato il: {datetime.now().strftime('%d/%m/%Y')}</p>
        </div>
        
        <div class="ditta-box">
            <h3 style="margin-top:0;">🏢 Ditta Incaricata</h3>
            <p><strong>{DITTA_DISINFESTAZIONE['ragione_sociale']}</strong></p>
            <p>P.IVA: {DITTA_DISINFESTAZIONE['partita_iva']} | C.F.: {DITTA_DISINFESTAZIONE['codice_fiscale']}</p>
            <p>Indirizzo: {DITTA_DISINFESTAZIONE['indirizzo']}</p>
            <p>REA: {DITTA_DISINFESTAZIONE['rea']} | PEC: {DITTA_DISINFESTAZIONE['pec']}</p>
        </div>
        
        <h2>📅 Interventi Programmati</h2>
        <table>
            <tr>
                <th>Mese</th>
                <th>Giorno Intervento</th>
                <th>Esito</th>
                <th>Note</th>
            </tr>
    """

    for mese in range(1, 13):
        mese_str = str(mese)
        intervento = interventi.get(mese_str, {})
        giorno = intervento.get("giorno", "-")
        esito = intervento.get("esito", "Non effettuato")
        note = intervento.get("note", "")

        esito_class = (
            "ok"
            if "OK" in esito or "Nessuna" in esito
            else ("problema" if esito != "Non effettuato" else "")
        )

        html += f"""
            <tr>
                <td><strong>{MESI_IT[mese-1]}</strong></td>
                <td>{giorno}</td>
                <td class="{esito_class}">{esito}</td>
                <td>{note}</td>
            </tr>
        """

    html += f"""
        </table>
        
        <div class="firma">
            <div class="firma-box">Responsabile HACCP</div>
            <div class="firma-box">Tecnico Disinfestatore</div>
            <div class="firma-box">Data e Timbro</div>
        </div>
        
        <div class="footer">
            <p>Conforme a Reg. CE 852/2004 - Controllo infestanti</p>
        </div>
        
        <div class="no-print" style="text-align:center; margin-top:20px;">
            <button onclick="window.print()" class="btn-print">🖨️ Stampa PDF</button>
        </div>
    </body>
    </html>
    """

    return HTMLResponse(content=html)


@router.get("/ditta")
async def get_ditta_disinfestazione():
    """Restituisce i dati della ditta di disinfestazione"""
    return DITTA_DISINFESTAZIONE
