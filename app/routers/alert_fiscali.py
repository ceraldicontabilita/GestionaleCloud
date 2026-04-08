"""
Router Alert Fiscali — Ceraldi ERP
PREFIX: /api/alert-fiscali

Monitora i pagamenti mancanti e imminenti scadenze fiscali.

REGOLE IMPLEMENTATE (fonte: normativa vigente):

CONTRIBUTI INPS (DM10/CXX):
  - Scadenza: 16 del mese successivo al periodo di riferimento
  - Entro 120 giorni dalla scadenza: ravvedimento spontaneo (sanzione ridotta al solo TUR)
  - Dopo 120 giorni: sanzione civile ordinaria (TUR + 5,5%) max 40%
  - In qualsiasi giorno di ritardo: DURC IRREGOLARE
  - Fonte: art.19 DL 2.3.2024 n.19, circ. INPS 34/2025

RITENUTE IRPEF (codice 1001):
  - Scadenza ordinaria: 16 del mese successivo
  - Termine ultimo senza conseguenze penali: data invio Modello 770
    (di norma 31 ottobre dell'anno successivo, dichiarabile entro 31/12)
  - Soglia reato penale: > 150.000€/anno (art.10-bis DLgs 74/2000)
  - Sanzione amministrativa: 25% dell'importo non versato
  - Fonte: art.10-bis DLgs 74/2000; Corte Cost. 175/2022

ALTRI TRIBUTI ERARIO (1701, 1704, IVA, ecc.):
  - Scadenza: indicata nella scadenza del relativo F24
  - Ravvedimento operoso entro 14 gg: sanzione 0,08%/gg
  - Ravvedimento entro 30 gg: sanzione 1,25%
  - Ravvedimento entro 90 gg: sanzione 1,39%
  - Oltre 90 gg: sanzione 3,125% (fino alla dichiarazione successiva)
  - Fonte: art.13 DLgs 472/97, DLgs 87/2024

CODICE ATTO (avviso bonario 9001/9002):
  - Termine pagamento senza sanzioni aggiuntive: 30 giorni dalla notifica
  - Rateizzabile in 20 rate trimestrali
  - Va incrociato con documenti in archivio
  - Fonte: art.36-bis DPR 600/73

Endpoints:
  GET /api/alert-fiscali/dashboard    → riepilogo tutti gli alert attivi
  GET /api/alert-fiscali/inps         → contributi INPS non pagati/in ritardo
  GET /api/alert-fiscali/ritenute     → ritenute 1001 non pagate
  GET /api/alert-fiscali/avvisi-bonari → avvisi bonari senza quietanza abbinata
  GET /api/alert-fiscali/f24-orfani   → F24 senza quietanza corrispondente
"""

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime, date

from app.database import get_database

router = APIRouter(prefix="/api/alert-fiscali", tags=["Alert Fiscali"])

AZIENDA_ID = "b0295759-35ce-4b34-a6b4-f01b883234ad"


def _scadenza_contributi(mese: int, anno: int) -> date:
    """Calcola scadenza contributi INPS: 16 del mese successivo."""
    if mese == 12:
        return date(anno + 1, 1, 16)
    return date(anno, mese + 1, 16)


def _scadenza_770(anno_ritenute: int) -> date:
    """
    Scadenza Modello 770: 31 ottobre dell'anno successivo a quello delle ritenute.
    Es: ritenute 2024 → 770 entro 31/10/2025 → termine penale entro 31/12/2025
    """
    return date(anno_ritenute + 1, 10, 31)


def _giorni_ritardo(scadenza: date) -> int:
    return (date.today() - scadenza).days


def _livello_urgenza_inps(giorni: int) -> dict:
    """
    Calcola livello urgenza per contributi INPS in ritardo.
    Basato su: 120 gg = fine ravvedimento spontaneo, DURC irregolare da subito.
    """
    if giorni <= 0:
        return {"livello": "ok", "colore": "success", "testo": "Nei termini"}
    elif giorni <= 15:
        return {
            "livello": "warning",
            "colore": "warning",
            "testo": f"Ritardo {giorni}gg — sanzione ridotta {giorni*0.08:.2f}% (ravvedimento sprint)",
            "sanzione_pct": round(giorni * 0.08, 2),
            "durc": "IRREGOLARE",
        }
    elif giorni <= 30:
        return {
            "livello": "warning",
            "colore": "warning",
            "testo": f"Ritardo {giorni}gg — sanzione 1,25% ravvedimento breve",
            "sanzione_pct": 1.25,
            "durc": "IRREGOLARE",
        }
    elif giorni <= 90:
        return {
            "livello": "danger",
            "colore": "danger",
            "testo": f"Ritardo {giorni}gg — sanzione 1,39% + DURC IRREGOLARE",
            "sanzione_pct": 1.39,
            "durc": "IRREGOLARE",
        }
    elif giorni <= 120:
        return {
            "livello": "danger",
            "colore": "danger",
            "testo": f"Ritardo {giorni}gg — ultimo periodo ravvedimento spontaneo (entro 120gg). DURC IRREGOLARE.",
            "sanzione_pct": 3.125,
            "durc": "IRREGOLARE",
            "avviso": "Ultimi giorni per ravvedimento spontaneo senza sanzione ordinaria INPS"
        }
    else:
        return {
            "livello": "critical",
            "colore": "danger",
            "testo": f"Ritardo {giorni}gg — SANZIONE CIVILE ORDINARIA (TUR+5.5% max 40%). DURC IRREGOLARE. Possibile avviso bonario INPS.",
            "sanzione_pct": min(round(giorni / 365 * 10.9, 2), 40.0),
            "durc": "IRREGOLARE",
            "avviso": "Rischio avviso bonario INPS. Contattare commercialista urgentemente."
        }


def _livello_urgenza_ritenute(giorni_al_770: int, importo_annuo: float) -> dict:
    """
    Calcola urgenza ritenute 1001 non versate.
    Soglia penale: > 150.000€/anno; termine: data 770.
    """
    soglia_penale = importo_annuo > 150000

    if giorni_al_770 > 180:
        livello = "info"
        testo = f"Ritenuta non versata — {giorni_al_770}gg al termine 770. Ravvedimento consigliato."
    elif giorni_al_770 > 90:
        livello = "warning"
        testo = f"Ritenuta non versata — {giorni_al_770}gg al 770. Sanzione 30% se non regolarizzata."
    elif giorni_al_770 > 0:
        livello = "danger"
        testo = f"Ritenuta non versata — solo {giorni_al_770}gg al termine 770. Agire subito."
    else:
        livello = "critical"
        testo = f"Termine 770 superato da {abs(giorni_al_770)}gg. Sanzione 30% dovuta."

    return {
        "livello": livello,
        "testo": testo,
        "soglia_penale": soglia_penale,
        "avviso_penale": "⚠️ ATTENZIONE: importo annuo > €150.000 — rischio penale art.10-bis DLgs 74/2000. Consultare avvocato." if soglia_penale else None,
    }


# ═══════════════════════════════════════════════════════════════
# GET /dashboard — tutti gli alert in un colpo
# ═══════════════════════════════════════════════════════════════
@router.get("/dashboard")
async def dashboard_alert(db: AsyncIOMotorDatabase = Depends(get_database)):
    """Riepilogo completo alert fiscali attivi per Ceraldi Group SRL."""

    risultati = {
        "generato_il": datetime.utcnow().isoformat(),
        "data_oggi": date.today().isoformat(),
        "alert_inps": [],
        "alert_ritenute": [],
        "alert_avvisi_bonari": [],
        "alert_f24_orfani": [],
        "sommario": {},
    }

    # ── Alert INPS ──────────────────────────────────────────────
    inps_resp = await _calcola_alert_inps(db)
    risultati["alert_inps"] = inps_resp

    # ── Alert ritenute 1001 ─────────────────────────────────────
    rit_resp = await _calcola_alert_ritenute(db)
    risultati["alert_ritenute"] = rit_resp

    # ── Alert avvisi bonari ─────────────────────────────────────
    av_resp = await _calcola_alert_avvisi_bonari(db)
    risultati["alert_avvisi_bonari"] = av_resp

    # ── F24 orfani (senza quietanza) ────────────────────────────
    orfani_resp = await _calcola_f24_orfani(db)
    risultati["alert_f24_orfani"] = orfani_resp

    # Sommario
    n_critical = sum(1 for a in inps_resp + rit_resp + av_resp if a.get("livello") in ("critical", "danger"))
    n_warning  = sum(1 for a in inps_resp + rit_resp + av_resp if a.get("livello") == "warning")

    risultati["sommario"] = {
        "totale_alert": len(inps_resp) + len(rit_resp) + len(av_resp),
        "critici_e_danger": n_critical,
        "warning": n_warning,
        "f24_senza_quietanza": len(orfani_resp),
        "durc_a_rischio": any(a.get("durc") == "IRREGOLARE" for a in inps_resp),
        "rischio_penale": any(a.get("soglia_penale") for a in rit_resp),
    }

    return risultati


async def _calcola_alert_inps(db) -> list:
    """
    Cerca F24 con sezione INPS (DM10/CXX) e verifica se sono stati pagati.
    Confronta con quietanze ricevute. Se manca quietanza → calcola ritardo.
    """
    alerts = []
    oggi = date.today()

    # Prende tutti i F24 non scartati con tributi INPS degli ultimi 6 mesi
    cutoff = date(oggi.year - 1, oggi.month, 1).isoformat()
    cursor = db["f24"].find({
        "azienda_id": AZIENDA_ID,
        "stato": {"$ne": "scartato"},
        "scadenza": {"$gte": cutoff},
        "tributi_flat.sezione": "INPS",
    }).sort("scadenza", -1)

    async for doc in cursor:
        # Controlla se ha quietanza abbinata
        ha_quietanza = bool(doc.get("riconciliazione_quietanza") or doc.get("f24_id"))

        # Legge i periodi INPS
        for t in doc.get("tributi_flat", []):
            if t.get("sezione") != "INPS":
                continue
            if t.get("debito", 0) == 0:
                continue

            causale = t.get("codice_tributo", "")
            periodo = t.get("periodo") or t.get("mese_rif", "")
            anno_rif = t.get("anno_rif", "")

            # Calcola scadenza teorica
            try:
                if "/" in str(periodo):
                    mese_p = int(str(periodo).split("/")[0])
                    anno_p = int(str(periodo).split("/")[-1]) if len(str(periodo).split("/")) > 1 else int(anno_rif or oggi.year)
                else:
                    mese_p = int(str(periodo)[:2]) if periodo else oggi.month
                    anno_p = int(anno_rif) if anno_rif else oggi.year
                scadenza_inps = _scadenza_contributi(mese_p, anno_p)
            except:
                continue

            giorni = _giorni_ritardo(scadenza_inps)

            if giorni <= 0 and ha_quietanza:
                continue  # pagato nei termini

            urgenza = _livello_urgenza_inps(giorni)

            if urgenza["livello"] != "ok":
                alerts.append({
                    "tipo": "INPS_NON_PAGATO" if not ha_quietanza else "INPS_PAGATO_TARDI",
                    "causale": causale,
                    "periodo": f"{mese_p:02d}/{anno_p}",
                    "scadenza": scadenza_inps.isoformat(),
                    "giorni_ritardo": max(0, giorni),
                    "importo": t.get("debito", 0),
                    "ha_quietanza": ha_quietanza,
                    "f24_id": str(doc["_id"]),
                    "f24_scadenza": doc.get("scadenza"),
                    **urgenza,
                })
            break  # un alert per F24

    return alerts


async def _calcola_alert_ritenute(db) -> list:
    """
    Cerca ritenute 1001 nei F24.
    Confronta con quietanze. Se non pagate, calcola urgenza rispetto al 770.
    Accumula per anno per verificare soglia penale 150k.
    """
    alerts = []
    oggi = date.today()

    # Raggruppa per anno
    ritenute_per_anno = {}

    cursor = db["f24"].find({
        "azienda_id": AZIENDA_ID,
        "stato": {"$ne": "scartato"},
        "tributi_flat.codice_tributo": "1001",
    }).sort("scadenza", -1)

    async for doc in cursor:
        ha_quietanza = bool(doc.get("riconciliazione_quietanza"))
        if ha_quietanza:
            continue  # già pagato con quietanza

        for t in doc.get("tributi_flat", []):
            if t.get("codice_tributo") != "1001":
                continue
            if t.get("debito", 0) == 0:
                continue

            anno_rif = t.get("anno_rif", str(oggi.year))
            try:
                anno = int(anno_rif)
            except:
                anno = oggi.year

            if anno not in ritenute_per_anno:
                ritenute_per_anno[anno] = {"totale": 0, "mesi_mancanti": [], "f24_ids": []}

            ritenute_per_anno[anno]["totale"] += t.get("debito", 0)
            mese = t.get("mese_rif", "")
            ritenute_per_anno[anno]["mesi_mancanti"].append(f"{mese}/{anno}")
            ritenute_per_anno[anno]["f24_ids"].append(str(doc["_id"]))

    for anno, dati in ritenute_per_anno.items():
        scadenza_770 = _scadenza_770(anno)
        giorni_al_770 = (scadenza_770 - oggi).days
        urgenza = _livello_urgenza_ritenute(giorni_al_770, dati["totale"])

        alerts.append({
            "tipo": "RITENUTE_1001_NON_PAGATE",
            "anno": anno,
            "importo_totale_non_versato": round(dati["totale"], 2),
            "mesi_interessati": list(set(dati["mesi_mancanti"])),
            "scadenza_770": scadenza_770.isoformat(),
            "giorni_al_770": giorni_al_770,
            "f24_ids": list(set(dati["f24_ids"])),
            **urgenza,
        })

    return alerts


async def _calcola_alert_avvisi_bonari(db) -> list:
    """
    Cerca quietanze con codice 9001/9002 (avviso bonario) e verifica:
    1. Se c'è un documento corrispondente in archivio (fatture/documenti)
    2. Se è stato pagato (quietanza trovata)
    3. Quanti giorni dalla generazione della quietanza
    """
    alerts = []
    oggi = date.today()

    cursor = db["quietanze"].find({
        "azienda_id": AZIENDA_ID,
        "note_avviso_bonario": True,
    }).sort("data_versamento", -1)

    async for doc in cursor:
        codice_atto = doc.get("codice_atto", "")

        # Cerca documento corrispondente in archivio (fatture passive, prima nota, ecc.)
        doc_correlato = None
        if codice_atto:
            # Cerca in fatture passive
            doc_correlato = await db["fatture_passive"].find_one({"codice_atto": codice_atto})
            if not doc_correlato:
                # Cerca in avvisi bonari (se collection esiste)
                doc_correlato = await db["avvisi_bonari"].find_one(
                    {"$or": [{"codice_atto": codice_atto}, {"numero": codice_atto}]}
                )

        # Calcola giorni dalla quietanza
        data_v = doc.get("data_versamento", "")
        try:
            data_versamento = date.fromisoformat(data_v)
            giorni = (oggi - data_versamento).days
        except:
            giorni = 0

        saldo = doc.get("saldo_finale", 0)
        tributi_9001 = [t for t in doc.get("tributi_flat", []) if t.get("codice_tributo") in ("9001", "9002")]

        alerts.append({
            "tipo": "AVVISO_BONARIO_PAGATO",
            "codice_atto": codice_atto,
            "data_pagamento": data_v,
            "importo_pagato": saldo,
            "protocollo": doc.get("protocollo_telematico"),
            "giorni_fa": giorni,
            "documento_correlato_trovato": bool(doc_correlato),
            "documento_correlato_id": str(doc_correlato["_id"]) if doc_correlato and "_id" in doc_correlato else None,
            "tributi": tributi_9001,
            "livello": "info",
            "testo": f"Avviso bonario (cod. {codice_atto}) pagato il {data_v} — €{saldo}. "
                     + ("Documento correlato trovato in archivio." if doc_correlato else "⚠️ Nessun documento correlato trovato — verificare in archivio."),
        })

    # Cerca anche F24 con codice 9001 non ancora riconciliati con quietanza
    cursor2 = db["f24"].find({
        "azienda_id": AZIENDA_ID,
        "stato": {"$ne": "scartato"},
        "tributi_flat.codice_tributo": {"$in": ["9001", "9002"]},
        "riconciliazione_quietanza": {"$exists": False},
    })
    async for doc in cursor2:
        codice_atto = doc.get("codice_atto", "")
        scadenza = doc.get("scadenza", "")

        # Calcola urgenza: 30 giorni dalla notifica per pagare senza sanzioni
        try:
            sc_date = date.fromisoformat(scadenza)
            giorni = (oggi - sc_date).days
        except:
            giorni = 0

        alerts.append({
            "tipo": "AVVISO_BONARIO_DA_PAGARE",
            "codice_atto": codice_atto,
            "scadenza": scadenza,
            "importo": doc.get("saldo_finale", 0),
            "f24_id": str(doc["_id"]),
            "giorni_dalla_notifica": giorni,
            "livello": "danger" if giorni > 30 else "warning",
            "testo": f"Avviso bonario (cod. {codice_atto}) — F24 importato ma senza quietanza. "
                     + (f"Scaduto da {giorni}gg" if giorni > 30 else f"{30-giorni}gg al termine di 30 giorni senza sanzioni extra"),
        })

    return alerts


async def _calcola_f24_orfani(db) -> list:
    """F24 pagati senza quietanza corrispondente (prove di pagamento mancanti)."""
    orfani = []
    cutoff = date(date.today().year - 1, 1, 1).isoformat()

    cursor = db["f24"].find({
        "azienda_id": AZIENDA_ID,
        "stato": {"$nin": ["scartato"]},
        "scadenza": {"$gte": cutoff},
        "riconciliazione_quietanza": {"$exists": False},
    }).sort("scadenza", -1)

    async for doc in cursor:
        orfani.append({
            "f24_id": str(doc["_id"]),
            "scadenza": doc.get("scadenza"),
            "saldo_finale": doc.get("saldo_finale"),
            "stato": doc.get("stato"),
            "livello": "info",
            "testo": "F24 senza quietanza ADE abbinata — caricare la quietanza per conferma definitiva pagamento",
        })

    return orfani


# ═══════════════════════════════════════════════════════════════
# Endpoint singoli
# ═══════════════════════════════════════════════════════════════
@router.get("/inps")
async def alert_inps(db: AsyncIOMotorDatabase = Depends(get_database)):
    return await _calcola_alert_inps(db)

@router.get("/ritenute")
async def alert_ritenute(db: AsyncIOMotorDatabase = Depends(get_database)):
    return await _calcola_alert_ritenute(db)

@router.get("/avvisi-bonari")
async def alert_avvisi_bonari(db: AsyncIOMotorDatabase = Depends(get_database)):
    return await _calcola_alert_avvisi_bonari(db)

@router.get("/f24-orfani")
async def alert_f24_orfani(db: AsyncIOMotorDatabase = Depends(get_database)):
    return await _calcola_f24_orfani(db)
