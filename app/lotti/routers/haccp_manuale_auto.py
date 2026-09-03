"""
AGENTE HACCP MANUALE — Motore di aggiornamento automatico.

Il Manuale di Autocontrollo HACCP si aggiorna automaticamente ogni volta che:
  - Arriva una nuova fattura da fornitore sconosciuto → scheda qualifica
  - Viene registrata un'anomalia (temperatura, guasto, non conformità)
  - Cambia lo stato di un fornitore (escluso, approvato)
  - La pipeline notturna esegue i propri step

Reg. CE 852/2004 · Reg. CE 178/2002 art. 18 · D.Lgs. 193/2007
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta, date
from fastapi import APIRouter

from app.lotti.db import database as db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/haccp-auto-manuale", tags=["HACCP Manuale Automatico"])

# ─────────────────────────────────────────────────────────────────────────────
# SCHEDA QUALIFICA FORNITORE — Reg. CE 178/2002 art. 18
# ─────────────────────────────────────────────────────────────────────────────
CATEGORIE_PRODOTTI = {
    "carni": ["carne", "pollo", "maiale", "bovino", "manzo", "salame", "prosciutto", "würstel"],
    "latticini": ["latte", "panna", "burro", "formaggio", "mozzarella", "ricotta", "yogurt"],
    "farine": ["farina", "semola", "grano", "frumento", "farro", "orzo"],
    "surgelati": ["surgelat", "congelat", "abbattut", "vandemoortele", "acquaviva"],
    "verdure": ["verdur", "ortagg", "insalat", "pomодor", "zucchine", "melanzane", "peperone"],
    "uova": ["uova", "uovo", "albume", "tuorlo"],
    "pesci": ["pesce", "baccalà", "merluzzo", "salmone", "tonno", "gamberi", "cozze"],
    "oli_grassi": ["olio", "strutto", "margarina", "lardo"],
    "zuccheri": ["zucchero", "miele", "sciroppo", "glucosio"],
    "condimenti": ["sale", "pepe", "aceto", "senape", "maionese"],
}


def _categoria_fornitore(prodotti: list) -> str:
    """Deduce la categoria merceologica dal nome dei prodotti forniti."""
    testo = " ".join(p.get("descrizione", "").lower() for p in prodotti)
    for cat, kws in CATEGORIE_PRODOTTI.items():
        if any(kw in testo for kw in kws):
            return cat
    return "generi_alimentari"


def _temperatura_stoccaggio(categoria: str) -> str:
    mappa = {
        "carni": "+2°C / +4°C",
        "latticini": "+2°C / +6°C",
        "surgelati": "-18°C / -25°C",
        "pesci": "0°C / +2°C",
        "verdure": "+4°C / +8°C",
    }
    return mappa.get(categoria, "+4°C / +10°C")


async def crea_scheda_qualifica_fornitore(nome: str, piva: str, prodotti: list, fattura_id: str):
    """
    Crea (o aggiorna) la scheda qualifica di un fornitore nel DB.
    Chiamata automaticamente quando arriva una nuova fattura.
    """
    esistente = await db.fornitori_qualifica.find_one({"nome_fornitore": nome})
    if esistente:
        # Aggiorna ultima fattura e num prodotti
        await db.fornitori_qualifica.update_one(
            {"nome_fornitore": nome},
            {
                "$set": {
                    "ultima_fornitura": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "num_fatture": esistente.get("num_fatture", 0) + 1,
                    "aggiornato_il": datetime.now(timezone.utc).isoformat(),
                }
            },
        )
        return

    categoria = _categoria_fornitore(prodotti)
    temp_stoc = _temperatura_stoccaggio(categoria)
    prodotti_campione = list(
        {p.get("descrizione", "")[:60] for p in prodotti if p.get("descrizione")}
    )[:8]

    scheda = {
        "id": str(uuid.uuid4()),
        "nome_fornitore": nome,
        "piva": piva,
        "categoria_merceologica": categoria,
        "temperatura_stoccaggio_richiesta": temp_stoc,
        "prodotti_forniti_campione": prodotti_campione,
        "num_fatture": 1,
        "prima_fornitura": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "ultima_fornitura": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "fattura_origine_id": fattura_id,
        # Criteri di qualifica (da compilare manualmente o tramite audit)
        "criteri_qualifica": {
            "certificazioni_richieste": _certificazioni_per_categoria(categoria),
            "frequenza_audit": "Annuale",
            "modalita_verifica": "Visura DDT + campionamento periodico",
            "note": "Scheda generata automaticamente al primo import fattura — verificare e approvare",
        },
        "stato": "in_attesa_verifica",  # → approvato | sospeso | escluso
        "creato_il": datetime.now(timezone.utc).isoformat(),
        "aggiornato_il": datetime.now(timezone.utc).isoformat(),
    }
    await db.fornitori_qualifica.insert_one(scheda)
    logger.info(f"[HACCP] Scheda qualifica creata per: {nome} ({categoria})")


def _certificazioni_per_categoria(cat: str) -> list:
    base = ["Reg. CE 852/2004", "Reg. CE 178/2002"]
    extra = {
        "carni": ["Certificato sanitario ASL", "Reg. CE 853/2004", "HACCP operatore"],
        "latticini": ["Certificato sanitario ASL", "Reg. CE 853/2004"],
        "pesci": [
            "Certificato sanitario ASL",
            "Reg. CE 853/2004",
            "Documento trasporto temperatura",
        ],
        "surgelati": ["Certificazione catena del freddo", "Reg. CE 37/2005"],
        "farine": ["Certificato di origine", "Scheda tecnica prodotto"],
    }
    return base + extra.get(cat, ["Scheda tecnica prodotto", "HACCP dichiarato"])


# ─────────────────────────────────────────────────────────────────────────────
# AGGIORNAMENTO MANUALE HACCP — Sezioni dinamiche
# ─────────────────────────────────────────────────────────────────────────────
async def aggiorna_sezioni_manuale():
    """
    Rigenera le sezioni dinamiche del Manuale HACCP nel DB.
    Le sezioni statiche restano invariate; quelle dinamiche vengono
    riscritte con i dati più recenti. Chiamata dalla pipeline e da
    ogni evento significativo (nuova fattura, nuova anomalia).
    """
    now = datetime.now(timezone.utc)
    oggi = now.strftime("%d/%m/%Y %H:%M")

    # ── Carica dati aggiornati ────────────────────────────────────────────────
    fornitori_qualifica = await db.fornitori_qualifica.find({}, {"_id": 0}).to_list(500)
    fornitori_approvati = [f for f in fornitori_qualifica if f.get("stato") == "approvato"]
    fornitori_attesa = [f for f in fornitori_qualifica if f.get("stato") == "in_attesa_verifica"]
    fornitori_esclusi = await db.fornitori.find({"escluso": True}, {"_id": 0, "nome": 1}).to_list(
        200
    )

    # data_fattura è in formati misti (dd/mm/yyyy e ISO): un sort Mongo sulla
    # stringa ordina per giorno del mese, non per data — "ultime" va deciso
    # su date vere in Python.
    from app.lotti.routers.utils import parse_data_flessibile
    _tutte_fatt = await db.fatture.find(
        {}, {"_id": 0, "fornitore": 1, "numero_fattura": 1, "data_fattura": 1, "prodotti": 1}
    ).to_list(10000)
    ultime_fatture = sorted(
        _tutte_fatt,
        key=lambda f: parse_data_flessibile(f.get("data_fattura")) or date.min,
        reverse=True,
    )[:30]

    # il campo delle anomalie si chiama data_segnalazione (non "data": la
    # query precedente non trovava MAI nulla e il manuale usciva senza
    # anomalie recenti). Formato misto storico → filtro su date vere.
    _soglia_anom = (now - timedelta(days=90)).date()
    _anomalie = await db.anomalie.find({}, {"_id": 0}).to_list(3000)
    anomalie_recenti = sorted(
        (
            a for a in _anomalie
            if (parse_data_flessibile(a.get("data_segnalazione")) or date.min) >= _soglia_anom
        ),
        key=lambda a: parse_data_flessibile(a.get("data_segnalazione")) or date.min,
        reverse=True,
    )[:50]

    temperature_fuori_range = await db.temperature_positive.aggregate(
        [
            {"$unwind": {"path": "$mesi", "preserveNullAndEmptyArrays": False}},
            {"$unwind": {"path": "$mesi.rilevazioni", "preserveNullAndEmptyArrays": False}},
            {
                "$match": {
                    "$or": [
                        {"mesi.rilevazioni.valore": {"$gt": 8}},
                        {"mesi.rilevazioni.valore": {"$lt": -1}},
                    ]
                }
            },
            {"$sort": {"mesi.rilevazioni.data": -1}},
            {"$limit": 20},
            {
                "$project": {
                    "_id": 0,
                    "attrezzatura": "$nome",
                    "data": "$mesi.rilevazioni.data",
                    "valore": "$mesi.rilevazioni.valore",
                }
            },
        ]
    ).to_list(20)

    ricette_allergeni = (
        await db.ricette.find({}, {"_id": 0, "nome": 1, "allergeni": 1, "categoria": 1})
        .sort("nome", 1)
        .to_list(200)
    )
    lotti_scaduti = await db.lotti.count_documents({"stato": "scaduto"})
    lotti_attivi = await db.lotti.count_documents({"stato": {"$nin": ["scaduto", "esaurito"]}})

    # ── Costruisci JSON delle sezioni ─────────────────────────────────────────
    sezioni = {
        "aggiornato_il": now.isoformat(),
        "aggiornato_da": "pipeline_automatica",
        "fornitori_qualificati": {
            "totale": len(fornitori_approvati),
            "in_attesa_verifica": len(fornitori_attesa),
            "esclusi": len(fornitori_esclusi),
            "lista": [
                {
                    "nome": f["nome_fornitore"],
                    "piva": f.get("piva", ""),
                    "categoria": f.get("categoria_merceologica", ""),
                    "temperatura_stoccaggio": f.get("temperatura_stoccaggio_richiesta", ""),
                    "prodotti": f.get("prodotti_forniti_campione", []),
                    "ultima_fornitura": f.get("ultima_fornitura", ""),
                    "num_fatture": f.get("num_fatture", 0),
                    "stato": f.get("stato", ""),
                }
                for f in fornitori_approvati + fornitori_attesa
            ],
            "esclusi_lista": [f["nome"] for f in fornitori_esclusi],
        },
        "schede_ricevimento": {
            "totale_consegne": len(ultime_fatture),
            "ultime_30": [
                {
                    "data": f.get("data_fattura", ""),
                    "fornitore": f.get("fornitore", ""),
                    "numero_documento": f.get("numero_fattura", ""),
                    "num_prodotti": len(f.get("prodotti", [])),
                    "conforme": True,
                }
                for f in ultime_fatture
            ],
        },
        "anomalie_e_non_conformita": {
            "totale_ultimi_90gg": len(anomalie_recenti),
            "lista": [
                {
                    "data": a.get("data", ""),
                    "tipo": a.get("tipo", ""),
                    "attrezzatura": a.get("attrezzatura", "") or a.get("apparecchio", ""),
                    "descrizione": a.get("descrizione", "") or a.get("problema", ""),
                    "azione_correttiva": a.get("azione_correttiva", "") or a.get("soluzione", ""),
                    "operatore": a.get("operatore", "") or a.get("tecnico", ""),
                }
                for a in anomalie_recenti
            ],
        },
        "temperature_non_conformi": {
            "totale": len(temperature_fuori_range),
            "lista": temperature_fuori_range,
            "soglie": {"positivo_max": 8, "positivo_min": -1},
        },
        "registro_allergeni": {
            "totale_ricette": len(ricette_allergeni),
            "con_allergeni": len([r for r in ricette_allergeni if r.get("allergeni")]),
            "da_verificare": len([r for r in ricette_allergeni if not r.get("allergeni")]),
            "matrice": [
                {
                    "nome": r["nome"],
                    "categoria": r.get("categoria", ""),
                    "allergeni": r.get("allergeni", []),
                }
                for r in ricette_allergeni
            ],
        },
        "lotti": {
            "attivi": lotti_attivi,
            "scaduti_da_smaltire": lotti_scaduti,
        },
    }

    # ── Salva/aggiorna nel DB ────────────────────────────────────────────────
    await db.manuale_haccp_dinamico.replace_one(
        {"_id": "sezioni_dinamiche"}, {"_id": "sezioni_dinamiche", **sezioni}, upsert=True
    )
    logger.info(
        f"[HACCP] Manuale aggiornato — {len(fornitori_approvati)+len(fornitori_attesa)} fornitori, {len(anomalie_recenti)} anomalie, {len(ultime_fatture)} consegne"
    )
    return sezioni


# ─────────────────────────────────────────────────────────────────────────────
# HOOK — Chiamato da PEC import dopo ogni nuova fattura
# ─────────────────────────────────────────────────────────────────────────────
async def hook_nuova_fattura(fattura_data: dict, fattura_id: str):
    """
    Eseguito automaticamente dopo ogni import di fattura.
    1. Crea/aggiorna scheda qualifica fornitore
    2. Aggiorna le sezioni dinamiche del manuale
    """
    nome = fattura_data.get("fornitore", "")
    piva = fattura_data.get("piva", "")
    prodotti = fattura_data.get("prodotti", [])

    if nome:
        await crea_scheda_qualifica_fornitore(nome, piva, prodotti, fattura_id)

    await aggiorna_sezioni_manuale()


async def hook_nuova_anomalia(anomalia: dict):
    """Aggiorna il manuale ogni volta che viene registrata una nuova anomalia."""
    await aggiorna_sezioni_manuale()
    logger.info(f"[HACCP] Anomalia registrata → manuale aggiornato")


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT REST
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/aggiorna")
async def trigger_aggiornamento():
    """Aggiorna manualmente tutte le sezioni dinamiche del Manuale HACCP."""
    sezioni = await aggiorna_sezioni_manuale()
    return {
        "status": "ok",
        "aggiornato_il": sezioni["aggiornato_il"],
        "fornitori_qualificati": sezioni["fornitori_qualificati"]["totale"],
        "fornitori_attesa": sezioni["fornitori_qualificati"]["in_attesa_verifica"],
        "anomalie_90gg": sezioni["anomalie_e_non_conformita"]["totale_ultimi_90gg"],
        "ricette_senza_allergeni": sezioni["registro_allergeni"]["da_verificare"],
    }


@router.post("/qualifica-fornitore")
async def qualifica_fornitore_manuale(nome: str, approva: bool = True):
    """Approva o sospende un fornitore nel registro qualifica."""
    stato = "approvato" if approva else "sospeso"
    res = await db.fornitori_qualifica.update_one(
        {"nome_fornitore": nome},
        {"$set": {"stato": stato, "aggiornato_il": datetime.now(timezone.utc).isoformat()}},
    )
    if res.matched_count == 0:
        return {"status": "non_trovato", "nome": nome}
    # Aggiorna anche la collection fornitori principale
    await db.fornitori.update_one(
        {"nome": nome}, {"$set": {"qualificato": approva, "in_attesa": False}}
    )
    await aggiorna_sezioni_manuale()
    return {"status": stato, "nome": nome}


@router.get("/stato-manuale")
async def get_stato_manuale():
    """Restituisce lo stato attuale del Manuale HACCP dinamico."""
    doc = await db.manuale_haccp_dinamico.find_one({"_id": "sezioni_dinamiche"}, {"_id": 0})
    if not doc:
        return {"status": "non_generato", "messaggio": "Eseguire POST /aggiorna"}
    return {
        "aggiornato_il": doc.get("aggiornato_il"),
        "fornitori_qualificati": doc.get("fornitori_qualificati", {}).get("totale", 0),
        "fornitori_attesa": doc.get("fornitori_qualificati", {}).get("in_attesa_verifica", 0),
        "anomalie_90gg": doc.get("anomalie_e_non_conformita", {}).get("totale_ultimi_90gg", 0),
        "temperature_anomale": doc.get("temperature_non_conformi", {}).get("totale", 0),
        "lotti_scaduti": doc.get("lotti", {}).get("scaduti_da_smaltire", 0),
        "ricette_senza_allergeni": doc.get("registro_allergeni", {}).get("da_verificare", 0),
        "consegne_registrate": doc.get("schede_ricevimento", {}).get("totale_consegne", 0),
    }


@router.get("/schede-qualifica")
async def get_schede_qualifica(stato: str = None):
    """Lista schede qualifica fornitori (filtrabili per stato)."""
    filtro = {}
    if stato:
        filtro["stato"] = stato
    schede = (
        await db.fornitori_qualifica.find(filtro, {"_id": 0}).sort("creato_il", -1).to_list(500)
    )
    return schede
