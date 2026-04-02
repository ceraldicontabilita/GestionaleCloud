"""
AGENTE PIPELINE — Motore di auto-miglioramento continuo del gestionale HACCP.

Eseguito automaticamente:
  - Dopo ogni import fatture PEC
  - Ogni notte alle 01:00 (dallo scheduler)
  - Su richiesta manuale via GET /api/pipeline/esegui

Step eseguiti in sequenza:
  1. allergeni      → rileva 14 allergeni UE dalle ricette senza dati
  2. prezzi         → aggiorna prezzi/kg dizionario da fatture ultime 30gg
  3. dedup          → rimuove prodotti duplicati nel dizionario
  4. acquaviva      → ricalcola costo/pezzo dai pesi reali in fattura
  5. lotti          → marca scaduti, rimuove esauriti >1 anno
  6. fornitori      → aggiorna statistiche fornitori (num fatture, ultima data)
"""
import os, re, logging, uuid
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pipeline", tags=["Pipeline Agente"])

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME   = os.environ.get("DB_NAME")
client    = AsyncIOMotorClient(MONGO_URL)
db        = client[DB_NAME]

# ── 14 Allergeni Reg. UE 1169/2011 Allegato II ────────────────────────────
MAPPA_ALLERGENI = {
    "Glutine":            ["farina","frumento","grano","glutine","semola","orzo","segale","avena","farro","kamut","spelta","pasta","pane","pangrattato","sfoglia","brioche","pizza","crackers","malto","lievito madre","crostata","biscotto"],
    "Uova":               ["uova","uovo","albume","tuorlo","maionese","meringa","pasta all'uovo","pasta uovo","crema pasticcera","frittata","zabaione"],
    "Latte":              ["latte","panna","burro","formaggio","mozzarella","ricotta","yogurt","yoghurt","mascarpone","grana","parmigiano","pecorino","provolone","brie","emmental","scamorza","stracchino","besciamella","latticini","latte in polvere","caseina","fiordilatte","caciocavallo"],
    "Frutta a guscio":    ["mandorle","mandorla","nocciole","nocciola","noci","noce","pistacchi","pistacchio","anacardi","pinoli","pinolo","noci pecan","macadamia"],
    "Arachidi":           ["arachidi","arachide","burro di arachidi"],
    "Soia":               ["soia","soy","tofu","tempeh","edamame","latte di soia","salsa di soia"],
    "Pesce":              ["pesce","baccalà","merluzzo","salmone","tonno","acciughe","acciuga","alice","sardine","sgombro","branzino","orata"],
    "Crostacei":          ["gamberi","gambero","scampi","aragosta","granchio","astice","mazzancolle"],
    "Molluschi":          ["cozze","ostriche","vongole","polpo","calamari","seppie","frutti di mare"],
    "Sedano":             ["sedano","sedano rapa"],
    "Senape":             ["senape","mostarda"],
    "Sesamo":             ["sesamo","tahina","tahini","semi di sesamo"],
    "Anidride solforosa": ["vino","aceto","solfiti","frutta secca","uva passa","albicocche secche"],
    "Lupini":             ["lupini","lupino","farina di lupino"],
}

def _allergeni_da_ingredienti(nomi: set) -> list:
    trovati = []
    for all_, kws in MAPPA_ALLERGENI.items():
        if any(kw in nome for nome in nomi for kw in kws):
            trovati.append(all_)
    return trovati


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 1 — Allergeni
# ─────────────────────────────────────────────────────────────────────────────
async def step_allergeni(log: dict):
    ricette = await db.ricette.find(
        {"$or": [{"allergeni": {"$exists": False}}, {"allergeni": []}, {"allergeni": None}]},
        {"_id": 0, "id": 1, "ingredienti_dettaglio": 1, "ingredienti": 1}
    ).to_list(5000)
    aggiornate = 0
    for r in ricette:
        nomi = set()
        for ing in (r.get("ingredienti_dettaglio") or []):
            n = (ing.get("nome") or "").lower().strip()
            if n: nomi.add(n)
        for ing in (r.get("ingredienti") or []):
            if isinstance(ing, str): nomi.add(ing.lower().strip())
        allergeni = _allergeni_da_ingredienti(nomi)
        await db.ricette.update_one({"id": r["id"]}, {"$set": {"allergeni": allergeni, "allergeni_auto": True}})
        aggiornate += 1
    log["allergeni_aggiornate"] = aggiornate


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 2 — Prezzi dizionario da fatture recenti
# ─────────────────────────────────────────────────────────────────────────────
async def step_prezzi_dizionario(log: dict):
    da = (datetime.now(timezone.utc) - timedelta(days=45)).strftime("%Y-%m-%d")
    fatture = await db.fatture.find(
        {"data_fattura": {"$gte": da}},
        {"_id": 0, "prodotti": 1, "fornitore": 1, "data_fattura": 1}
    ).to_list(1000)
    aggiornati = 0
    for f in fatture:
        for p in f.get("prodotti", []):
            desc = (p.get("descrizione") or "").strip()
            if not desc: continue
            try:
                prezzo = float(str(p.get("prezzo", "0") or "0").replace(",", "."))
            except Exception:
                continue
            if prezzo <= 0: continue
            nome_norm = re.sub(r"\s+", " ", desc.lower().strip())
            res = await db.dizionario_prodotti.update_one(
                {"nome_normalizzato": nome_norm},
                {"$set": {
                    "ultimo_prezzo_fattura": prezzo,
                    "ultima_data_fattura": f.get("data_fattura"),
                    "pipeline_updated": datetime.now(timezone.utc).isoformat()
                }}
            )
            if res.matched_count > 0:
                aggiornati += 1
    log["prezzi_dizionario_aggiornati"] = aggiornati


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 3 — Deduplicazione dizionario prodotti
# ─────────────────────────────────────────────────────────────────────────────
async def step_dedup(log: dict):
    pipeline = [
        {"$group": {"_id": "$nome_normalizzato", "count": {"$sum": 1}, "ids": {"$push": "$_id"}}},
        {"$match": {"count": {"$gt": 1}}}
    ]
    duplicati = await db.dizionario_prodotti.aggregate(pipeline).to_list(1000)
    rimossi = 0
    for dup in duplicati:
        ids_da_rimuovere = dup["ids"][1:]
        await db.dizionario_prodotti.delete_many({"_id": {"$in": ids_da_rimuovere}})
        rimossi += len(ids_da_rimuovere)
    log["duplicati_rimossi"] = rimossi


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 4 — Costi Acquaviva/Vandemoortele da ultime 2 fatture
# ─────────────────────────────────────────────────────────────────────────────
async def step_costi_acquaviva(log: dict):
    fatture = await db.fatture.find(
        {"fornitore": {"$regex": "vandemoortele|acquaviva", "$options": "i"}},
        {"_id": 0, "prodotti": 1, "fornitore": 1, "data_fattura": 1}
    ).sort("data_fattura", -1).to_list(2)
    aggiornati = 0
    for f in fatture:
        for p in f.get("prodotti", []):
            desc = (p.get("descrizione") or "").strip().upper()
            if not desc: continue
            try:
                prezzo_cart = float(str(p.get("prezzo", "0") or "0").replace(",", "."))
            except Exception:
                continue
            if prezzo_cart <= 0: continue

            m_g = re.search(r"(\d+[.,]?\d*)\s*G\b", desc)
            m_kg_all = re.findall(r"([\d]+[.,]?[\d]*)\s*KG", desc)
            peso_g = float(m_g.group(1).replace(",", ".")) if m_g else 0
            kg_cart = None
            for v in reversed(m_kg_all):
                val = float(v.replace(",", "."))
                if 0.5 < val < 50:
                    kg_cart = val; break
            if not kg_cart and m_kg_all:
                v = float(m_kg_all[-1].replace(",", "."))
                if v > 50: kg_cart = round(v / 100, 2)

            if not kg_cart or not peso_g or peso_g <= 0: continue
            pezzi = round(kg_cart * 1000 / peso_g)
            if pezzi <= 0: continue
            costo_pz   = round(prezzo_cart / pezzi, 4)
            prezzo_kg  = round(prezzo_cart / kg_cart, 4)
            nome_norm  = re.sub(r"\s+", " ", desc.lower()[:60])

            await db.dizionario_prodotti.update_one(
                {"nome_normalizzato": {"$regex": re.escape(nome_norm[:20]), "$options": "i"},
                 "fornitore": {"$regex": "vandemoortele|acquaviva", "$options": "i"}},
                {"$set": {
                    "prezzo_kg": prezzo_kg, "prezzo_pezzo": costo_pz,
                    "pezzi_cartone": pezzi, "peso_pezzo_g": peso_g,
                    "peso_confezione": kg_cart,
                    "pipeline_updated": datetime.now(timezone.utc).isoformat()
                }}
            )
            aggiornati += 1
    log["costi_acquaviva_aggiornati"] = aggiornati


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 5 — Lotti: marca scaduti, rimuove vecchi
# ─────────────────────────────────────────────────────────────────────────────
async def step_lotti(log: dict):
    """
    Marca lotti scaduti confrontando date in formato dd/mm/yyyy (come salvate nel DB).
    NON usare confronto stringa ISO vs dd/mm/yyyy — produce falsi positivi.
    """
    oggi = datetime.now(timezone.utc).date()
    un_anno_fa = oggi.replace(year=oggi.year - 1)

    # Fetch tutti i lotti non ancora marcati scaduti/esauriti
    candidati = await db.lotti.find(
        {"stato": {"$nin": ["scaduto", "esaurito", "smaltito"]}},
        {"_id": 0, "id": 1, "lotto_id": 1, "data_scadenza": 1}
    ).to_list(5000)

    ids_scaduti = []
    for l in candidati:
        scad_str = l.get("data_scadenza", "")
        if not scad_str:
            continue
        try:
            parts = scad_str.split("/")
            if len(parts) == 3:
                d = datetime(int(parts[2]), int(parts[1]), int(parts[0])).date()
                if d < oggi:
                    ids_scaduti.append(l.get("id") or l.get("lotto_id"))
        except Exception:
            continue

    if ids_scaduti:
        await db.lotti.update_many(
            {"$or": [{"id": {"$in": ids_scaduti}}, {"lotto_id": {"$in": ids_scaduti}}]},
            {"$set": {"stato": "scaduto", "pipeline_flagged": True}}
        )

    # Rimuove lotti esauriti più vecchi di 1 anno (data_produzione in formato dd/mm/yyyy)
    candidati_vecchi = await db.lotti.find(
        {"stato": "esaurito"},
        {"_id": 0, "id": 1, "lotto_id": 1, "data_produzione": 1}
    ).to_list(5000)

    ids_da_rimuovere = []
    for l in candidati_vecchi:
        prod_str = l.get("data_produzione", "")
        if not prod_str:
            continue
        try:
            parts = prod_str.split("/")
            if len(parts) == 3:
                d = datetime(int(parts[2]), int(parts[1]), int(parts[0])).date()
                if d < un_anno_fa:
                    ids_da_rimuovere.append(l.get("id") or l.get("lotto_id"))
        except Exception:
            continue

    rimossi_count = 0
    if ids_da_rimuovere:
        res = await db.lotti.delete_many(
            {"$or": [{"id": {"$in": ids_da_rimuovere}}, {"lotto_id": {"$in": ids_da_rimuovere}}]}
        )
        rimossi_count = res.deleted_count

    log["lotti_scaduti_marcati"] = len(ids_scaduti)
    log["lotti_vecchi_rimossi"]  = rimossi_count


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 6 — Statistiche fornitori
# ─────────────────────────────────────────────────────────────────────────────
async def step_fornitori(log: dict):
    stats = await db.fatture.aggregate([
        {"$group": {"_id": "$fornitore", "ultima": {"$max": "$data_fattura"}, "num": {"$sum": 1}}}
    ]).to_list(500)
    aggiornati = 0
    for s in stats:
        if not s["_id"]: continue
        res = await db.fornitori.update_one(
            {"nome": s["_id"]},
            {"$set": {"ultima_fattura": s["ultima"], "num_fatture": s["num"],
                      "pipeline_sync": datetime.now(timezone.utc).isoformat()}}
        )
        if res.matched_count > 0:
            aggiornati += 1
    log["fornitori_aggiornati"] = aggiornati


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────────
async def esegui_pipeline_post_import(motivo: str = "manuale"):
    start = datetime.now(timezone.utc)
    log = {"motivo": motivo, "avviata": start.isoformat()}
    logger.info(f"[PIPELINE] Avvio — {motivo}")
    try:
        await step_allergeni(log)
        await step_prezzi_dizionario(log)
        await step_dedup(log)
        await step_costi_acquaviva(log)
        await step_lotti(log)
        await step_fornitori(log)
        # ── Step 7 — Aggiorna Manuale HACCP dinamico ──────────────────────
        try:
            from routers.haccp_manuale_auto import aggiorna_sezioni_manuale
            sezioni = await aggiorna_sezioni_manuale()
            log["manuale_haccp_aggiornato"] = True
            log["fornitori_in_scheda_qualifica"] = (
                sezioni["fornitori_qualificati"]["totale"] +
                sezioni["fornitori_qualificati"]["in_attesa_verifica"]
            )
        except Exception as e_m:
            log["manuale_haccp_aggiornato"] = False
            log["manuale_haccp_errore"] = str(e_m)
        log["durata_s"] = round((datetime.now(timezone.utc) - start).total_seconds(), 1)
        log["esito"] = "OK"
    except Exception as e:
        log["esito"] = "ERRORE"; log["errore"] = str(e)
        logger.error(f"[PIPELINE] Errore: {e}")
    finally:
        await db.pipeline_logs.insert_one({**log})
    logger.info(f"[PIPELINE] Fine — {log.get('esito')} in {log.get('durata_s','?')}s")
    return log


# ─────────────────────────────────────────────────────────────────────────────
#  ENDPOINT REST
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/esegui")
async def trigger_pipeline(motivo: str = "manuale"):
    """Esegue l'intera pipeline di auto-miglioramento."""
    return await esegui_pipeline_post_import(motivo=motivo)


@router.get("/logs")
async def get_logs(limit: int = 20):
    """Storico esecuzioni pipeline con dettaglio per step."""
    return await db.pipeline_logs.find({}, {"_id": 0}).sort("avviata", -1).to_list(limit)


@router.get("/stato")
async def get_stato():
    """Dashboard stato sistema: anomalie, gap da correggere."""
    ricette_no_all  = await db.ricette.count_documents({"$or":[{"allergeni":{"$exists":False}},{"allergeni":[]},{"allergeni":None}]})
    prod_no_prezzo  = await db.dizionario_prodotti.count_documents({"$or":[{"prezzo_kg":0},{"prezzo_kg":None},{"prezzo_kg":{"$exists":False}}]})
    lotti_scaduti   = await db.lotti.count_documents({"stato":"scaduto"})
    fornitori_att   = await db.fornitori.count_documents({"in_attesa":True,"escluso":False})
    ultima          = await db.pipeline_logs.find_one({},{"_id":0},sort=[("avviata",-1)])
    return {
        "ricette_senza_allergeni":        ricette_no_all,
        "prodotti_senza_prezzo":          prod_no_prezzo,
        "lotti_scaduti":                  lotti_scaduti,
        "fornitori_in_attesa":            fornitori_att,
        "ultima_esecuzione":              ultima.get("avviata") if ultima else None,
        "ultima_esito":                   ultima.get("esito") if ultima else None,
        "ultima_durata_s":                ultima.get("durata_s") if ultima else None,
    }
