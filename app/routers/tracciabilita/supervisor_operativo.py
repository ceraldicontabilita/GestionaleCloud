"""
SUPERVISORE OPERATIVO — Controllo giornaliero di tutti gli automatismi HACCP.

Eseguito ad ogni apertura dell'app (GET /api/supervisor/stato).
Genera una lista di ALERT con priorità e link diretto alla sezione da completare.

Documentazione: /app/SUPERVISORE.md
"""
import os, logging
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/supervisor", tags=["Supervisore Operativo"])

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME   = os.environ.get("DB_NAME")
client    = AsyncIOMotorClient(MONGO_URL)
db        = client[DB_NAME]

# ── Costanti configurabili (vedi SUPERVISORE.md) ──────────────────────────
SOGLIA_FORNITORE_INATTIVO_GG = 16      # giorni senza fatture → alert
SOGLIA_LOTTI_SCADUTI         = 5       # lotti scaduti tollerati
SOGLIA_SCADENZA_LOTTO_GG     = 2       # giorni prima della scadenza → alert
TEMP_POSITIVO_MAX            = 8.0     # °C massimo frigo positivo
TEMP_POSITIVO_MIN            = -1.0    # °C minimo frigo positivo
TEMP_NEGATIVO_MAX            = -15.0   # °C massimo frigo negativo
TEMP_NEGATIVO_MIN            = -25.0   # °C minimo frigo negativo

PRIORITA = {"critica": 0, "alta": 1, "media": 2, "bassa": 3}


def _alert(id_: str, titolo: str, descrizione: str, priorita: str,
           route: str, contatore: int = 0) -> dict:
    return {
        "id": id_,
        "titolo": titolo,
        "descrizione": descrizione,
        "priorita": priorita,          # critica | alta | media | bassa
        "route": route,                # hash URL dove mandare l'utente
        "contatore": contatore,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  CONTROLLI GIORNALIERI HACCP
# ─────────────────────────────────────────────────────────────────────────────
async def check_temperature_oggi(alerts: list):
    """T1/T2 — Temperature registrate oggi?
    
    Struttura reale DB:
      temperature_positive: {anno, frigorifero_numero, temperature: {mese_str: {giorno_str: float|dict}}}
      temperature_negative: {anno, congelatore_numero, temperature: {mese_str: {giorno_str: float|dict}}}
    """
    oggi = datetime.now(timezone.utc)
    anno      = oggi.year
    mese_str  = str(oggi.month)     # es. "3"
    giorno_str= str(oggi.day)       # es. "30"
    campo     = f"temperature.{mese_str}.{giorno_str}"

    # Temperature positive — basta che almeno UN frigorifero abbia la rilevazione odierna
    doc_pos = await db.temperature_positive.find_one(
        {"anno": anno, campo: {"$exists": True}}
    )
    if not doc_pos:
        alerts.append(_alert(
            "T1", "Temperature positive non registrate oggi",
            f"Nessuna rilevazione temperatura frigo per il {oggi.strftime('%d/%m/%Y')}. "
            "Il sistema le registra automaticamente ogni notte. Se mancano vai su Temp. Positive → compila manualmente.",
            "critica", "temp_positive"
        ))

    # Temperature negative — basta che almeno UN congelatore abbia la rilevazione odierna
    doc_neg = await db.temperature_negative.find_one(
        {"anno": anno, campo: {"$exists": True}}
    )
    if not doc_neg:
        alerts.append(_alert(
            "T2", "Temperature negative non registrate oggi",
            f"Nessuna rilevazione temperatura congelatore per il {oggi.strftime('%d/%m/%Y')}. "
            "Vai su Temp. Negative → compila manualmente.",
            "critica", "temp_negative"
        ))


async def check_sanificazione_oggi(alerts: list):
    """S1 — Sanificazione registrata oggi?
    
    Struttura reale DB:
      sanificazione: {anno, mese, registrazioni: {attrezzatura: {giorno_str: "X"|""}}}
    """
    oggi       = datetime.now(timezone.utc)
    anno       = oggi.year
    mese       = oggi.month
    giorno_str = str(oggi.day)    # es. "30"

    # Cerca scheda del mese corrente con almeno un'attrezzatura marcata oggi
    doc = await db.sanificazione_schede.find_one(
        {"anno": anno, "mese": mese}
    )
    trovata = False
    if doc:
        registrazioni = doc.get("registrazioni", {})
        for attrezzatura, giorni in registrazioni.items():
            if isinstance(giorni, dict) and giorni.get(giorno_str) in ("X", "x", True, "true", "1"):
                trovata = True
                break

    if not trovata:
        alerts.append(_alert(
            "S1", "Sanificazione non registrata oggi",
            f"Nessuna scheda sanificazione per il {oggi.strftime('%d/%m/%Y')}. "
            "Registrare al termine delle operazioni di pulizia.",
            "alta", "sanificazione"
        ))


async def check_lotti_oggi(alerts: list):
    """P1 — Lotti produzione registrati oggi?
    
    Soppresso se il giorno corrente è marcato come 'giorno non produttivo'.
    """
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Controlla se oggi è giorno non produttivo
    giorno_np = await db.giorni_non_produttivi.find_one({"data": oggi})
    if giorno_np:
        return  # Sopprime l'alert — giorno non produttivo
    
    lotti_oggi = await db.lotti.count_documents({"data_produzione": oggi})
    if lotti_oggi == 0:
        alerts.append(_alert(
            "P1", "Nessun lotto registrato oggi",
            f"Nessuna produzione registrata per il {oggi}. "
            "Se è un giorno produttivo, registra i lotti dal Tablet. "
            "Se è giorno di riposo, usa il toggle 'Giorno Non Produttivo' in Dashboard.",
            "media", "tablet/pasticceria", 0
        ))


# ─────────────────────────────────────────────────────────────────────────────
#  CONTROLLI QUALITÀ DATI
# ─────────────────────────────────────────────────────────────────────────────
async def check_allergeni(alerts: list):
    """A1 — Ricette senza allergeni."""
    n = await db.ricette.count_documents(
        {"$or": [{"allergeni": {"$exists": False}}, {"allergeni": []}, {"allergeni": None}]}
    )
    if n > 0:
        alerts.append(_alert(
            "A1", f"{n} ricett{'a' if n==1 else 'e'} senza allergeni dichiarati",
            f"Obbligatorio per legge (Reg. UE 1169/2011). "
            f"Apri la scheda ricetta → tab 'Allergeni & Nutri' → Rileva automaticamente.",
            "alta" if n > 5 else "media",
            "ricette", n
        ))


async def check_fornitori_qualifica(alerts: list):
    """A2 — Fornitori in attesa di qualifica HACCP."""
    n = await db.fornitori_qualifica.count_documents({"stato": "in_attesa_verifica"})
    if n > 0:
        alerts.append(_alert(
            "A2", f"{n} fornitore{'i' if n>1 else ''} in attesa di qualifica HACCP",
            f"Verificare e approvare i fornitori nel Registro Qualifica "
            f"(Reg. CE 178/2002 art. 18). Vai su Fornitori → Registro Qualifica HACCP.",
            "alta", "fornitori", n
        ))


async def check_lotti_scaduti(alerts: list):
    """A3 — Lotti scaduti non smaltiti.
    
    La collection 'lotti' usa data_scadenza in formato 'dd/mm/yyyy' o 'yyyy-mm-dd'.
    Conta i lotti con data_scadenza < oggi e stato != 'smaltito'.
    """
    oggi = datetime.now(timezone.utc)
    oggi_str_iso  = oggi.strftime("%Y-%m-%d")          # 2026-03-30
    oggi_str_it   = oggi.strftime("%d/%m/%Y")           # 30/03/2026

    # Lotti con stato smaltito (da escludere)
    tutti = await db.lotti.find(
        {"stato": {"$ne": "smaltito"}},
        {"_id": 0, "id": 1, "data_scadenza": 1, "stato": 1}
    ).to_list(2000)

    scaduti = []
    for l in tutti:
        ds = (l.get("data_scadenza") or "").strip()
        if not ds:
            continue
        try:
            # Formato dd/mm/yyyy (italiano)
            if "/" in ds:
                dd, mm, yyyy = ds.split("/")
                data = datetime(int(yyyy), int(mm), int(dd))
            else:
                # Formato yyyy-mm-dd (ISO)
                data = datetime.strptime(ds, "%Y-%m-%d")
            if data < oggi.replace(tzinfo=None):
                scaduti.append(l)
        except Exception:
            pass

    n = len(scaduti)
    if n > SOGLIA_LOTTI_SCADUTI:
        alerts.append(_alert(
            "A3", f"{n} lotti scaduti da smaltire",
            f"Sono presenti {n} lotti di produzione con data scadenza superata, "
            f"non ancora marcati come smaltiti. Vai su Lotti → Smalti Tutti.",
            "alta" if n > 20 else "media",
            "lotti", n
        ))


async def check_lotti_in_scadenza(alerts: list):
    """Lotti che scadono entro SOGLIA_SCADENZA_LOTTO_GG giorni.
    
    Confronta data_scadenza (dd/mm/yyyy o yyyy-mm-dd) con la finestra futura.
    """
    oggi = datetime.now(timezone.utc).replace(tzinfo=None)
    fra_gg = oggi + timedelta(days=SOGLIA_SCADENZA_LOTTO_GG)

    tutti = await db.lotti.find(
        {"stato": {"$nin": ["smaltito", "esaurito"]}},
        {"_id": 0, "id": 1, "data_scadenza": 1}
    ).to_list(2000)

    in_scadenza = []
    for l in tutti:
        ds = (l.get("data_scadenza") or "").strip()
        if not ds:
            continue
        try:
            if "/" in ds:
                dd, mm, yyyy = ds.split("/")
                data = datetime(int(yyyy), int(mm), int(dd))
            else:
                data = datetime.strptime(ds, "%Y-%m-%d")
            if oggi <= data <= fra_gg:
                in_scadenza.append(l)
        except Exception:
            pass

    n = len(in_scadenza)
    if n > 0:
        alerts.append(_alert(
            "A3b", f"{n} lotto/i in scadenza entro {SOGLIA_SCADENZA_LOTTO_GG} giorni",
            f"Lotti che scadono nei prossimi {SOGLIA_SCADENZA_LOTTO_GG} giorni. Utilizzare o smaltire per evitare sprechi.",
            "alta", "lotti", n
        ))


async def check_prodotti_senza_prezzo(alerts: list):
    """A4 — Prodotti nel dizionario senza prezzo/kg."""
    n = await db.dizionario_prodotti.count_documents(
        {"$or": [{"prezzo_kg": 0}, {"prezzo_kg": None}, {"prezzo_kg": {"$exists": False}}]}
    )
    if n > 0:
        alerts.append(_alert(
            "A4", f"{n} prodott{'o' if n==1 else 'i'} senza prezzo nel dizionario",
            f"Il food cost di ricette che usano questi ingredienti sarà errato.",
            "media", "ricette", n
        ))


async def check_fornitori_inattivi(alerts: list):
    """A5 — Fornitori senza fatture da più di SOGLIA_FORNITORE_INATTIVO_GG giorni."""
    soglia = (datetime.now(timezone.utc) - timedelta(days=SOGLIA_FORNITORE_INATTIVO_GG)).strftime("%Y-%m-%d")
    schede = await db.fornitori_qualifica.find(
        {"stato": "approvato", "ultima_fornitura": {"$lt": soglia}},
        {"_id": 0, "nome_fornitore": 1, "ultima_fornitura": 1}
    ).to_list(50)
    if schede:
        nomi = [s["nome_fornitore"] for s in schede[:3]]
        alerts.append(_alert(
            "A5", f"{len(schede)} fornitore/i inattivi da >{SOGLIA_FORNITORE_INATTIVO_GG} giorni",
            f"Nessuna fattura recente da: {', '.join(nomi)}"
            f"{' e altri' if len(schede)>3 else ''}. "
            f"Verificare se il rapporto commerciale è ancora attivo.",
            "media", "fornitori", len(schede)
        ))


async def check_anomalie_senza_azione(alerts: list):
    """A6 — Anomalie aperte senza azione correttiva."""
    n = await db.anomalie.count_documents({
        "stato": {"$nin": ["Risolta", "Chiusa", "risolta", "chiusa"]},
        "$or": [
            {"azione_correttiva": {"$exists": False}},
            {"azione_correttiva": ""},
            {"azione_correttiva": None},
        ]
    })
    if n > 0:
        alerts.append(_alert(
            "A6", f"{n} anomalia/e senza azione correttiva registrata",
            f"Le non conformità devono avere un'azione correttiva documentata "
            f"(Reg. CE 852/2004 Allegato II Cap. I).",
            "alta", "anomalie", n
        ))


async def check_pipeline(alerts: list):
    """Pipeline — ultima esecuzione e stato."""
    ultima = await db.pipeline_logs.find_one({}, {"_id":0}, sort=[("avviata",-1)])
    if not ultima:
        alerts.append(_alert(
            "PL1", "Pipeline automatica mai eseguita",
            "Eseguire la pipeline per aggiornare allergeni, prezzi e manuale HACCP.",
            "alta", "dashboard"
        ))
        return
    if ultima.get("esito") == "ERRORE":
        alerts.append(_alert(
            "PL2", "Ultima esecuzione pipeline con errori",
            f"Errore: {ultima.get('errore','sconosciuto')}",
            "alta", "dashboard"
        ))
    # Se non gira da >28 ore
    try:
        avviata = datetime.fromisoformat(ultima["avviata"])
        ore_fa = (datetime.now(timezone.utc) - avviata).total_seconds() / 3600
        if ore_fa > 28:
            alerts.append(_alert(
                "PL3", f"Pipeline non eseguita da {int(ore_fa)}h",
                "Lo scheduler notturno potrebbe non essere attivo.",
                "media", "dashboard"
            ))
    except Exception:
        pass


async def check_manuale_haccp(alerts: list):
    """M1 — Manuale HACCP aggiornato di recente?"""
    doc = await db.manuale_haccp_dinamico.find_one({"_id": "sezioni_dinamiche"})
    if not doc:
        alerts.append(_alert(
            "M1", "Manuale HACCP dinamico non generato",
            "Generare il manuale aggiornato per garantire la compliance.",
            "alta", "fornitori"
        ))
        return
    try:
        aggiornato = datetime.fromisoformat(doc["aggiornato_il"])
        ore_fa = (datetime.now(timezone.utc) - aggiornato).total_seconds() / 3600
        if ore_fa > 48:
            alerts.append(_alert(
                "M1b", f"Manuale HACCP non aggiornato da {int(ore_fa)}h",
                "Il manuale verrà aggiornato automaticamente stanotte dalla pipeline.",
                "bassa", "fornitori"
            ))
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
#  NUOVI MODULI ePACKPRO
# ─────────────────────────────────────────────────────────────────────────────

async def check_controllo_olio_oggi(alerts: list):
    """Controlla se il monitoraggio olio frittura è stato registrato oggi."""
    import re
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = await db.controllo_olio.find_one({"data": oggi})
    if not doc:
        # Controlla se oggi c'è stato utilizzo della friggitrice (produzione)
        produzioni_con_fritto = await db.produzioni.count_documents({
            "data": oggi,
            "ricetta_nome": {"$regex": "frit|donut|arancin|olio", "$options": "i"}
        })
        if produzioni_con_fritto > 0 or datetime.now(timezone.utc).weekday() < 5:  # lun-ven
            alerts.append(_alert(
                "olio_oggi",
                "Controllo Olio Frittura mancante",
                f"Nessun controllo olio registrato oggi. Verificare colore, odore e polarità.",
                "alta",
                "controllo_olio",
                0
            ))

async def check_temperature_cottura_oggi(alerts: list):
    """Controlla se le temperature di cottura sono state registrate oggi."""
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = await db.temperature_cottura.find_one({"data": oggi})
    if not doc:
        # Solo se ci sono produzioni oggi
        prod_oggi = await db.produzioni.count_documents({"data": oggi})
        if prod_oggi > 0:
            alerts.append(_alert(
                "cottura_oggi",
                "Temperature Cottura mancanti",
                f"Sono state registrate {prod_oggi} produzioni oggi ma nessuna temperatura di cottura.",
                "alta",
                "temp_cottura",
                prod_oggi
            ))

async def check_ricezione_merce_oggi(alerts: list):
    """Controlla se sono state registrate ricezioni merce nelle ultime 48h."""
    da_quando = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%d")
    count = await db.ricezioni_merce.count_documents({"data": {"$gte": da_quando}})
    # Controlla se ci sono fatture recenti da verificare (lotti fornitori non ancora ricevuti)
    lotti_da_verificare = await db.lotti_fornitori.count_documents({
        "created_at": {"$gte": da_quando},
        "esaurito": {"$ne": True}
    })
    if count == 0 and lotti_da_verificare > 3:
        alerts.append(_alert(
            "ricezione_48h",
            "Ricezione Merce non verificata",
            f"{lotti_da_verificare} forniture recenti non ancora verificate in accettazione.",
            "media",
            "ricezione_merce",
            lotti_da_verificare
        ))

async def check_lotti_scadenza_48h(alerts: list):
    """Notifica lotti in scadenza nelle prossime 48 ore."""
    import re
    ora = datetime.now(timezone.utc)
    soglia_48h = (ora + timedelta(hours=48)).strftime("%Y-%m-%d")
    oggi_str = ora.strftime("%Y-%m-%d")

    lotti = await db.lotti.find(
        {"stato": {"$nin": ["smaltito", "esaurito"]}},
        {"_id": 0, "id": 1, "prodotto": 1, "numero_lotto": 1, "data_scadenza": 1}
    ).to_list(500)

    in_scadenza = []
    for lotto in lotti:
        ds = lotto.get("data_scadenza", "")
        if not ds:
            continue
        try:
            # Normalizza formato data
            if re.match(r"\d{2}/\d{2}/\d{4}", ds):
                parts = ds.split("/")
                ds_iso = f"{parts[2]}-{parts[1]}-{parts[0]}"
            else:
                ds_iso = ds[:10]
            if oggi_str <= ds_iso <= soglia_48h:
                in_scadenza.append(lotto.get("prodotto", "?"))
        except Exception:
            continue

    if in_scadenza:
        nomi = ", ".join(in_scadenza[:5])
        alerts.append(_alert(
            "scadenza_48h",
            f"{len(in_scadenza)} lotti in scadenza entro 48h",
            f"Verificare: {nomi}" + (f" + altri {len(in_scadenza)-5}" if len(in_scadenza) > 5 else ""),
            "critica" if len(in_scadenza) >= 3 else "alta",
            "lotti",
            len(in_scadenza)
        ))


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────────
async def esegui_tutti_i_controlli() -> dict:
    alerts = []
    # Esegui tutti i check
    await check_temperature_oggi(alerts)
    await check_sanificazione_oggi(alerts)
    await check_lotti_oggi(alerts)
    await check_allergeni(alerts)
    await check_fornitori_qualifica(alerts)
    await check_lotti_scaduti(alerts)
    await check_lotti_in_scadenza(alerts)
    await check_prodotti_senza_prezzo(alerts)
    await check_fornitori_inattivi(alerts)
    await check_anomalie_senza_azione(alerts)
    await check_pipeline(alerts)
    await check_manuale_haccp(alerts)
    # Nuovi moduli ePackPro
    await check_controllo_olio_oggi(alerts)
    await check_temperature_cottura_oggi(alerts)
    await check_ricezione_merce_oggi(alerts)
    await check_lotti_scadenza_48h(alerts)

    # Ordina per priorità
    alerts.sort(key=lambda a: PRIORITA.get(a["priorita"], 9))

    critici = len([a for a in alerts if a["priorita"] == "critica"])
    alti    = len([a for a in alerts if a["priorita"] == "alta"])

    return {
        "data_controllo":   datetime.now(timezone.utc).isoformat(),
        "totale_alert":     len(alerts),
        "critici":          critici,
        "alti":             alti,
        "medi":             len([a for a in alerts if a["priorita"] == "media"]),
        "bassi":            len([a for a in alerts if a["priorita"] == "bassa"]),
        "semaforo":         "rosso" if critici > 0 else ("arancione" if alti > 0 else "verde"),
        "alerts":           alerts,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  ENDPOINT REST
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/stato")
async def get_stato_supervisore():
    """
    Controllo completo di tutti gli automatismi e procedure.
    Chiamato ad ogni apertura dell'app dal frontend.
    """
    return await esegui_tutti_i_controlli()


@router.get("/sommario")
async def get_sommario():
    """Solo contatori e semaforo — per il badge nella navbar."""
    result = await esegui_tutti_i_controlli()
    return {
        "semaforo":     result["semaforo"],
        "totale_alert": result["totale_alert"],
        "critici":      result["critici"],
        "alti":         result["alti"],
    }
