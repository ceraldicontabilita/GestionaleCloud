"""
SUPERVISORE OPERATIVO — Controllo giornaliero di tutti gli automatismi HACCP.

Eseguito ad ogni apertura dell'app (GET /api/supervisor/stato).
Genera una lista di ALERT con priorità e link diretto alla sezione da completare.

Documentazione: /app/SUPERVISORE.md
"""

import logging
from datetime import datetime, timezone, timedelta, date
from fastapi import APIRouter, Depends, HTTPException

from app.lotti.auth import require_admin

from app.lotti.db import database as db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/supervisor", tags=["Supervisore Operativo"])

# ── Costanti configurabili (vedi SUPERVISORE.md) ──────────────────────────
SOGLIA_FORNITORE_INATTIVO_GG = 16  # giorni senza fatture → alert
SOGLIA_LOTTI_SCADUTI = 5  # lotti scaduti tollerati
SOGLIA_SCADENZA_LOTTO_GG = 2  # giorni prima della scadenza → alert
TEMP_POSITIVO_MAX = 8.0  # °C massimo frigo positivo
TEMP_POSITIVO_MIN = -1.0  # °C minimo frigo positivo
TEMP_NEGATIVO_MAX = -15.0  # °C massimo frigo negativo
TEMP_NEGATIVO_MIN = -25.0  # °C minimo frigo negativo

PRIORITA = {"critica": 0, "alta": 1, "media": 2, "bassa": 3}

# I lotti hanno DUE campi storici per "non è più in giro": stato (stringa
# "smaltito"/"esaurito") e i flag booleani esaurito/consumato. Non tutti gli
# endpoint li settano entrambi: ogni controllo deve escluderli TUTTI, sennò
# un lotto archiviato col solo flag booleano resta negli alert per sempre
# (era il "lo sistemo ma ricompare" segnalato da Enzo il 03/07/2026).
# Filtro canonico "lotto attivo": definizione unica in routers.utils (re-export
# qui per compatibilità con gli usi interni di questo modulo).
from app.lotti.routers.utils import FILTRO_LOTTO_APERTO  # noqa: E402


def _alert(
    id_: str, titolo: str, descrizione: str, priorita: str, route: str, contatore: int = 0
) -> dict:
    return {
        "id": id_,
        "titolo": titolo,
        "descrizione": descrizione,
        "priorita": priorita,  # critica | alta | media | bassa
        "route": route,  # hash URL dove mandare l'utente
        "contatore": contatore,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  CONTROLLI GIORNALIERI HACCP
# ─────────────────────────────────────────────────────────────────────────────
def _ora_locale():
    """Ora locale di Napoli (UTC+1/+2 con ora legale, senza dipendenze)."""
    utc = datetime.now(timezone.utc)
    # ora legale europea: ultima domenica di marzo -> ultima domenica di ottobre
    anno = utc.year
    def ultima_domenica(mese):
        d = datetime(anno, mese + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
        return d - timedelta(days=(d.weekday() + 1) % 7)
    legale = ultima_domenica(3) <= utc < ultima_domenica(10)
    return utc + timedelta(hours=2 if legale else 1)


async def check_temperature_oggi(alerts: list):
    """T1/T2 — Temperature registrate oggi?

    Struttura reale DB:
      temperature_positive: {anno, frigorifero_numero, temperature: {mese_str: {giorno_str: float|dict}}}
      temperature_negative: {anno, congelatore_numero, temperature: {mese_str: {giorno_str: float|dict}}}
    """
    # REGOLA: le temperature si registrano alle 07:00 — prima delle 07:30 locali
    # la mancata registrazione di oggi NON e' un'anomalia, e' solo mattina presto.
    ora = _ora_locale()
    if ora.hour < 7 or (ora.hour == 7 and ora.minute < 30):
        return
    oggi = datetime.now(timezone.utc)
    anno = oggi.year
    mese_str = str(oggi.month)  # es. "3"
    giorno_str = str(oggi.day)  # es. "30"
    campo = f"temperature.{mese_str}.{giorno_str}"

    # Temperature positive — basta che almeno UN frigorifero abbia la rilevazione odierna
    doc_pos = await db.temperature_positive.find_one({"anno": anno, campo: {"$exists": True}})
    if not doc_pos:
        alerts.append(
            _alert(
                "T1",
                "Temperature positive non registrate oggi",
                f"Nessuna rilevazione temperatura frigo per il {oggi.strftime('%d/%m/%Y')}. "
                "Il sistema le registra automaticamente ogni notte. Se mancano vai su Temp. Positive → compila manualmente.",
                "critica",
                "temp_positive",
            )
        )

    # Temperature negative — basta che almeno UN congelatore abbia la rilevazione odierna
    doc_neg = await db.temperature_negative.find_one({"anno": anno, campo: {"$exists": True}})
    if not doc_neg:
        alerts.append(
            _alert(
                "T2",
                "Temperature negative non registrate oggi",
                f"Nessuna rilevazione temperatura congelatore per il {oggi.strftime('%d/%m/%Y')}. "
                "Vai su Temp. Negative → compila manualmente.",
                "critica",
                "temp_negative",
            )
        )


async def check_sanificazione_oggi(alerts: list):
    """S1 — Sanificazione registrata oggi?

    Struttura reale DB:
      sanificazione: {anno, mese, registrazioni: {attrezzatura: {giorno_str: "X"|""}}}
    """
    # REGOLA: la sanificazione si registra a fine lavorazioni — prima delle 17:00
    # locali la mancata registrazione di oggi non e' un'anomalia.
    ora = _ora_locale()
    if ora.hour < 17:
        return
    oggi = datetime.now(timezone.utc)
    anno = oggi.year
    mese = oggi.month
    giorno_str = str(oggi.day)  # es. "30"

    # Cerca scheda del mese corrente con almeno un'attrezzatura marcata oggi
    doc = await db.sanificazione_schede.find_one({"anno": anno, "mese": mese})
    trovata = False
    if doc:
        registrazioni = doc.get("registrazioni", {})
        for attrezzatura, giorni in registrazioni.items():
            if isinstance(giorni, dict) and giorni.get(giorno_str) in ("X", "x", True, "true", "1"):
                trovata = True
                break

    if not trovata:
        alerts.append(
            _alert(
                "S1",
                "Sanificazione non registrata oggi",
                f"Nessuna scheda sanificazione per il {oggi.strftime('%d/%m/%Y')}. "
                "Registrare al termine delle operazioni di pulizia.",
                "alta",
                "sanificazione",
            )
        )


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
        alerts.append(
            _alert(
                "P1",
                "Nessun lotto registrato oggi",
                f"Nessuna produzione registrata per il {oggi}. "
                "Se è un giorno produttivo, registra i lotti dal Tablet. "
                "Se è giorno di riposo, usa il toggle 'Giorno Non Produttivo' in Dashboard.",
                "media",
                "tablet/pasticceria",
                0,
            )
        )


# ─────────────────────────────────────────────────────────────────────────────
#  CONTROLLI QUALITÀ DATI
# ─────────────────────────────────────────────────────────────────────────────
_ULTIMO_AUTORILEVA_ALLERGENI = {"ts": 0.0}


async def check_allergeni(alerts: list):
    """A1 — Ricette senza allergeni.
    PRIMA di segnalare, il sistema PROVA DA SOLO il rilevamento automatico
    (regola Enzo 03/07/2026: "la logica automatica la deve fare il sistema").
    Restano nell'alert solo le ricette dove l'automatismo non può fare nulla
    (nessun ingrediente su cui lavorare) — quelle sì richiedono una mano.
    """
    filtro_non_verificate = {
        "$or": [
            {"allergeni_verificato": {"$exists": False}},
            {"allergeni_verificato": False},
            {"allergeni_verificato": None},
        ]
    }
    n = await db.ricette.count_documents(filtro_non_verificate)
    if n > 0:
        # auto-rilevamento al massimo una volta l'ora (il /stato gira a ogni
        # apertura dell'app: non deve riscansionare le ricette ogni volta)
        import time
        if time.time() - _ULTIMO_AUTORILEVA_ALLERGENI["ts"] > 3600:
            _ULTIMO_AUTORILEVA_ALLERGENI["ts"] = time.time()
            try:
                from app.lotti.routers.food_cost import auto_rileva_allergeni_tutte
                await auto_rileva_allergeni_tutte(force=False)
                n = await db.ricette.count_documents(filtro_non_verificate)
            except Exception:
                logger_sup = __import__("logging").getLogger("supervisor")
                logger_sup.debug("[A1] auto-rilevamento allergeni non bloccante fallito")
    if n > 0:
        a = _alert(
            "A1",
            f"{n} ricett{'a' if n==1 else 'e'} senza allergeni (automatismo impossibile)",
            f"Il rilevamento automatico è già stato eseguito: queste ricette non hanno "
            f"ingredienti su cui lavorare. Aggiungi gli ingredienti (o gli allergeni a mano) "
            f"— obbligatorio per legge (Reg. UE 1169/2011).",
            "alta" if n > 5 else "media",
            "ricette",
            n,
        )
        # elenco diretto dei colpevoli: tocco -> scheda ricetta, tab allergeni
        colpevoli = await db.ricette.find(
            filtro_non_verificate,
            {"_id": 0, "id": 1, "nome": 1},
        ).to_list(60)
        a["items"] = [{"id": r.get("id"), "nome": r.get("nome", "?")} for r in colpevoli]
        a["items_tab"] = "allergeni"
        alerts.append(a)

    # A1b — allergeni compilati dall'AUTOMATISMO in attesa di conferma umana
    # (decisione Enzo 04/07/2026: "verificato" deve voler dire che un umano ha
    # guardato). Priorità bassa e silenziabile: ricorda, non blocca. La conferma
    # è il salvataggio della ricetta dal tab allergeni.
    n_conf = await db.ricette.count_documents({"allergeni_da_confermare": True})
    if n_conf > 0:
        a = _alert(
            "A1b",
            f"{n_conf} ricett{'a' if n_conf==1 else 'e'} con allergeni auto-rilevati da confermare",
            "Il sistema ha compilato gli allergeni da solo (parole chiave): apri la "
            "ricetta, controlla ed eventualmente correggi, poi Salva — quello vale "
            "come conferma. Non urgente, ma davanti a un controllo fa la differenza.",
            "bassa",
            "ricette",
            n_conf,
        )
        da_conf = await db.ricette.find(
            {"allergeni_da_confermare": True}, {"_id": 0, "id": 1, "nome": 1}
        ).to_list(60)
        a["items"] = [{"id": r.get("id"), "nome": r.get("nome", "?")} for r in da_conf]
        a["items_tab"] = "allergeni"
        alerts.append(a)


async def check_fornitori_qualifica(alerts: list):
    """A2 — Fornitori in attesa di qualifica HACCP."""
    n = await db.fornitori_qualifica.count_documents({"stato": "in_attesa_verifica"})
    if n > 0:
        docs = await db.fornitori_qualifica.find(
            {"stato": "in_attesa_verifica"}, {"_id": 0, "id": 1, "ragione_sociale": 1}
        ).to_list(60)
        a = _alert(
                "A2",
                f"{n} fornitore{'i' if n>1 else ''} in attesa di qualifica HACCP",
                f"Verificare e approvare i fornitori nel Registro Qualifica "
                f"(Reg. CE 178/2002 art. 18). Vai su Fornitori → Registro Qualifica HACCP.",
                "alta",
                "fornitori",
                n,
            )
        a["items"] = [{"id": d.get("id"), "nome": d.get("ragione_sociale", "?")} for d in docs]
        alerts.append(a)


async def check_lotti_scaduti(alerts: list):
    """A3 — Lotti scaduti non smaltiti.

    La collection 'lotti' usa data_scadenza in formato 'dd/mm/yyyy' o 'yyyy-mm-dd'.
    Conta i lotti con data_scadenza < oggi e stato != 'smaltito'.
    """
    oggi = datetime.now(timezone.utc)
    tutti = await db.lotti.find(
        dict(FILTRO_LOTTO_APERTO),
        {"_id": 0, "id": 1, "data_scadenza": 1, "stato": 1, "prodotto": 1, "numero_lotto": 1},
    ).sort("data_scadenza", 1).to_list(3000)  # i piu' urgenti per primi, tetto difensivo

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
            logger.debug("[supervisor_operativo] errore non bloccante ignorato")

    n = len(scaduti)
    # HACCP: anche UN solo lotto scaduto va segnalato (niente tolleranza silenziosa)
    if n > 0:
        a = _alert(
            "A3",
            f"{n} lott{'o' if n==1 else 'i'} scadut{'o' if n==1 else 'i'} da smaltire",
            f"Lotti con data scadenza superata e non smaltiti. "
            f"Tocca per l'elenco: ogni voce apre Lotti filtrato sugli scaduti.",
            "critica" if n > 20 else ("alta" if n > SOGLIA_LOTTI_SCADUTI else "media"),
            "lotti",
            n,
        )
        # I 60 mostrati siano i PIÙ scaduti (data_scadenza è a formato misto: il
        # sort del DB era lessicografico). Ordino per data reale crescente.
        from app.lotti.routers.utils import parse_data_flessibile
        scaduti.sort(key=lambda l: parse_data_flessibile(l.get("data_scadenza")) or date.min)
        a["items"] = [
            {"id": l.get("id"),
             "nome": f"{l.get('prodotto','?')} · lotto {l.get('numero_lotto','?')} · scad. {l.get('data_scadenza','')}"}
            for l in scaduti[:60]
        ]
        alerts.append(a)


async def check_lotti_in_scadenza(alerts: list):
    """Lotti che scadono entro SOGLIA_SCADENZA_LOTTO_GG giorni.

    Confronta data_scadenza (dd/mm/yyyy o yyyy-mm-dd) con la finestra futura.
    """
    oggi = datetime.now(timezone.utc).replace(tzinfo=None)
    fra_gg = oggi + timedelta(days=SOGLIA_SCADENZA_LOTTO_GG)

    tutti = await db.lotti.find(
        dict(FILTRO_LOTTO_APERTO),
        {"_id": 0, "id": 1, "data_scadenza": 1, "prodotto": 1, "numero_lotto": 1},
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
            logger.debug("[supervisor_operativo] errore non bloccante ignorato")

    n = len(in_scadenza)
    if n > 0:
        a = _alert(
            "A3b",
            f"{n} lott{'o' if n==1 else 'i'} in scadenza entro {SOGLIA_SCADENZA_LOTTO_GG} giorni",
            f"Lotti che scadono nei prossimi {SOGLIA_SCADENZA_LOTTO_GG} giorni. "
            f"Utilizzare o smaltire per evitare sprechi. Tocca per l'elenco.",
            "critica" if n >= 3 else "alta",
            "lotti",
            n,
        )
        a["items"] = [
            {"id": l.get("id"),
             "nome": f"{l.get('prodotto','?')} · lotto {l.get('numero_lotto','?')} · scad. {l.get('data_scadenza','')}"}
            for l in in_scadenza[:60]
        ]
        alerts.append(a)


async def check_prodotti_senza_prezzo(alerts: list):
    """A4 — Prodotti ACQUISTATI ma senza prezzo/kg nel dizionario.
    I prezzi vengono SOLO dalle fatture (regola del progetto): un prodotto mai
    comprato senza prezzo è normale e NON va segnalato (era un alert eterno
    che nessuno poteva sistemare). Anomalia vera = comprato ma prezzo mancante
    (fattura senza importo o normalizzazione fallita)."""
    filtro = {
        "conteggio_acquisti": {"$gt": 0},
        "$or": [{"prezzo_kg": 0}, {"prezzo_kg": None}, {"prezzo_kg": {"$exists": False}}],
    }
    docs = await db.dizionario_prodotti.find(
        filtro, {"_id": 0, "nome_canonico": 1, "nome_normalizzato": 1}
    ).to_list(500)
    n = len(docs)
    if n > 0:
        a = _alert(
            "A4",
            f"{n} prodott{'o' if n==1 else 'i'} comprat{'o' if n==1 else 'i'} ma senza prezzo",
            "Prodotti presenti in fattura ma senza prezzo nel dizionario: il "
            "food cost delle ricette che li usano sarà errato. Il prezzo si "
            "aggiorna da solo alla prossima fattura con importo valido.",
            "media",
            # comparatore = pagina prezzi ingredienti (route "ricette" apriva
            # una scheda ricetta a caso: l'item è un INGREDIENTE, non una ricetta)
            "comparatore",
            n,
        )
        a["items"] = [
            {"id": (d.get("nome_normalizzato") or d.get("nome_canonico") or "?"),
             "nome": (d.get("nome_canonico") or d.get("nome_normalizzato") or "?")}
            for d in docs[:60]
        ]
        alerts.append(a)


async def check_dati_da_completare(alerts: list):
    """DATI1/2/3 — Dati da completare dopo gli import (richiesta Enzo
    03/07/2026): prodotti bar senza soglia minima (il riordino automatico
    non li vede), prodotti in vendita senza prezzo, fornitori attivi senza
    sito web nella scheda (serve per le schede tecniche → ricette)."""
    # DATI1: prodotti bar movimentati ma senza soglia minima
    prods = await db.magazzino_bar_prodotti.find(
        {"$or": [{"soglia_minima": {"$exists": False}}, {"soglia_minima": {"$in": [0, None]}}],
         "stock": {"$gt": 0}},
        {"_id": 0, "id": 1, "nome": 1},
    ).to_list(500)
    if prods:
        a = _alert(
            "DATI1",
            f"{len(prods)} prodotti di magazzino senza soglia minima",
            "Il riordino automatico non può proporli: imposta la soglia dal "
            "Backoffice o dalla card in Ordini → Catalogo.",
            "media", "ordini", len(prods),
        )
        a["items"] = [{"id": p.get("id"), "nome": p.get("nome", "?")} for p in prods[:60]]
        alerts.append(a)

    # DATI2: prodotti in vendita attivi senza prezzo di vendita
    pv = await db.prodotti_vendita.find(
        {"attivo": {"$ne": False},
         "$or": [{"prezzo_vendita": {"$exists": False}}, {"prezzo_vendita": {"$in": [0, None]}}]},
        {"_id": 0, "id": 1, "nome": 1},
    ).to_list(500)
    if pv:
        a = _alert(
            "DATI2",
            f"{len(pv)} prodotti in vendita senza prezzo",
            "Senza prezzo non compaiono correttamente al banco: impostalo da "
            "Listini & Vendita → Imposta Prezzi.",
            "media", "prodotti", len(pv),
        )
        a["items"] = [{"id": p.get("id"), "nome": p.get("nome", "?")} for p in pv[:60]]
        alerts.append(a)

    # DATI4: righe fattura dei fornitori Magazzino+Lotti senza nome canonico
    # nel Dizionario — finché non le battezzi, il matching esatto nelle
    # ricette non è garantito (richiesta Enzo 04/07/2026: "ricordami di
    # compilare quei campi").
    non_completi_docs = await db.fornitori.find(
        {"$or": [{"tipo_fornitura": {"$in": ["solo_magazzino", "escluso"]}}, {"escluso": True}]},
        {"_id": 0, "nome": 1},
    ).to_list(300)
    nomi_nc = {(f.get("nome") or "").strip().lower() for f in non_completi_docs}
    scoperte = await db.dizionario_prodotti.find(
        {"$and": [
            # le righe escluse a mano (bevande/alcolici/vini/non-merce,
            # 23/07/2026) non vanno più ricordate: sono fuori dal battesimo
            {"escluso_ricette": {"$ne": True}},
            {"$or": [{"ingrediente_canonico": {"$in": [None, ""]}},
                     {"ingrediente_canonico": {"$exists": False}}]},
            {"$or": [{"nome_canonico": {"$in": [None, ""]}},
                     {"nome_canonico": {"$exists": False}}]},
        ]},
        {"_id": 0, "id": 1, "nome_originale": 1, "nome_normalizzato": 1, "fornitore": 1},
    ).to_list(2000)
    scoperte = [
        d for d in scoperte
        if (d.get("fornitore") or "").strip().lower() not in nomi_nc
    ]
    if scoperte:
        a = _alert(
            "DATI4",
            f"{len(scoperte)} righe fattura da battezzare nel Dizionario",
            "Righe XML dei fornitori Magazzino+Lotti ancora senza nome canonico: "
            "finché non le confermi, il collegamento esatto con le ricette non è "
            "garantito. Apri il Dizionario: la proposta è già accanto a ogni riga.",
            "media", "dizionario", len(scoperte),
        )
        a["items"] = [
            {"id": d.get("id"),
             "nome": f"{(d.get('nome_originale') or d.get('nome_normalizzato') or '?')[:60]} · {d.get('fornitore') or '?'}"}
            for d in scoperte[:60]
        ]
        alerts.append(a)

    # DATI3: fornitori attivi (con fatture) senza sito web in scheda
    attivi = await db.fornitori.find(
        {"escluso": {"$ne": True}, "num_fatture": {"$gt": 0}}, {"_id": 0, "nome": 1}
    ).to_list(500)
    con_sito = set()
    async for c in db.fornitori_anagrafica.find(
        {"sito_web": {"$nin": ["", None]}}, {"_id": 0, "nome": 1}
    ):
        con_sito.add((c.get("nome") or "").strip().lower())
    senza_sito = [f for f in attivi if (f.get("nome") or "").strip().lower() not in con_sito]
    if senza_sito:
        a = _alert(
            "DATI3",
            f"{len(senza_sito)} fornitori senza sito web in scheda",
            "Il sito serve a recuperare le schede tecniche dei prodotti "
            "(ingredienti/allergeni per le ricette): aggiungilo dalla scheda fornitore.",
            "bassa", "fornitori", len(senza_sito),
        )
        a["items"] = [{"id": f.get("nome"), "nome": f.get("nome", "?")} for f in senza_sito[:60]]
        alerts.append(a)


async def check_fornitori_inattivi(alerts: list):
    """A5 — Fornitori senza fatture da più di SOGLIA_FORNITORE_INATTIVO_GG giorni."""
    soglia = (datetime.now(timezone.utc) - timedelta(days=SOGLIA_FORNITORE_INATTIVO_GG)).strftime(
        "%Y-%m-%d"
    )
    schede = await db.fornitori_qualifica.find(
        {"stato": "approvato", "ultima_fornitura": {"$lt": soglia}},
        {"_id": 0, "nome_fornitore": 1, "ultima_fornitura": 1},
    ).to_list(50)
    if schede:
        nomi = [s["nome_fornitore"] for s in schede[:3]]
        alerts.append(
            _alert(
                "A5",
                f"{len(schede)} fornitore/i inattivi da >{SOGLIA_FORNITORE_INATTIVO_GG} giorni",
                f"Nessuna fattura recente da: {', '.join(nomi)}"
                f"{' e altri' if len(schede)>3 else ''}. "
                f"Verificare se il rapporto commerciale è ancora attivo.",
                "media",
                "fornitori",
                len(schede),
            )
        )


async def check_anomalie_senza_azione(alerts: list):
    """A6 — Anomalie aperte senza azione correttiva."""
    n = await db.anomalie.count_documents(
        {
            "stato": {"$nin": ["Risolta", "Chiusa", "risolta", "chiusa"]},
            "$or": [
                {"azione_correttiva": {"$exists": False}},
                {"azione_correttiva": ""},
                {"azione_correttiva": None},
            ],
        }
    )
    if n > 0:
        docs = await db.anomalie.find(
            {"stato": {"$nin": ["Risolta", "Chiusa", "risolta", "chiusa"]},
             "$or": [{"azione_correttiva": {"$exists": False}}, {"azione_correttiva": ""}, {"azione_correttiva": None}]},
            {"_id": 0, "id": 1, "tipo": 1, "descrizione": 1},
        ).to_list(60)
        a = _alert(
                "A6",
                f"{n} anomalia/e senza azione correttiva registrata",
                f"Le non conformità devono avere un'azione correttiva documentata "
                f"(Reg. CE 852/2004 Allegato II Cap. I).",
                "alta",
                "anomalie",
                n,
            )
        a["items"] = [{"id": d.get("id"),
                       "nome": (d.get("descrizione") or d.get("tipo") or "?")[:70]} for d in docs]
        alerts.append(a)


async def check_libretti_sanitari(alerts: list):
    """A7 — Libretti sanitari scaduti o in scadenza (obbligo di legge)."""
    from datetime import datetime as _dt

    operatori = await db.tablet_operatori.find(
        {"attivo": True}, {"_id": 0, "nome": 1, "ruolo": 1, "libretto_sanitario_scadenza": 1}
    ).to_list(200)
    oggi = datetime.now(timezone.utc).date()
    scaduti, in_scadenza = [], []
    for d in operatori:
        if d.get("ruolo") == "amministratore":
            continue
        scad = d.get("libretto_sanitario_scadenza") or ""
        if not scad:
            continue
        try:
            ds = _dt.strptime(scad[:10], "%Y-%m-%d").date()
        except Exception:
            continue
        giorni = (ds - oggi).days
        voce = {"id": d.get("nome"), "nome": f"{d.get('nome','?')} — scadenza {ds.strftime('%d/%m/%Y')}"}
        if giorni < 0:
            scaduti.append(voce)
        elif giorni <= 30:
            in_scadenza.append(voce)

    if scaduti:
        a = _alert(
            "A7",
            f"{len(scaduti)} libretto/i sanitario/i SCADUTO/I",
            "Un libretto sanitario scaduto impedisce al dipendente di operare. "
            "Rinnovo obbligatorio (Reg. CE 852/2004). Tocca per l'elenco.",
            "critica",
            "personale",
            len(scaduti),
        )
        a["items"] = scaduti[:60]
        alerts.append(a)
    if in_scadenza:
        a = _alert(
            "A7b",
            f"{len(in_scadenza)} libretto/i sanitario/i in scadenza (entro 30 giorni)",
            "Pianificare il rinnovo del libretto sanitario prima della scadenza.",
            "media",
            "personale",
            len(in_scadenza),
        )
        a["items"] = in_scadenza[:60]
        alerts.append(a)


async def check_pipeline(alerts: list):
    """Pipeline — ultima esecuzione e stato."""
    ultima = await db.pipeline_logs.find_one({}, {"_id": 0}, sort=[("avviata", -1)])
    if not ultima:
        alerts.append(
            _alert(
                "PL1",
                "Pipeline automatica mai eseguita",
                "Eseguire la pipeline per aggiornare allergeni, prezzi e manuale HACCP.",
                "alta",
                "dashboard",
            )
        )
        return
    if ultima.get("esito") == "ERRORE":
        alerts.append(
            _alert(
                "PL2",
                "Ultima esecuzione pipeline con errori",
                f"Errore: {ultima.get('errore','sconosciuto')}",
                "alta",
                "dashboard",
            )
        )
    # Se non gira da >28 ore
    try:
        avviata = datetime.fromisoformat(ultima["avviata"])
        ore_fa = (datetime.now(timezone.utc) - avviata).total_seconds() / 3600
        if ore_fa > 28:
            alerts.append(
                _alert(
                    "PL3",
                    f"Pipeline non eseguita da {int(ore_fa)}h",
                    "Lo scheduler notturno potrebbe non essere attivo.",
                    "media",
                    "dashboard",
                )
            )
    except Exception:
        logger.debug("[supervisor_operativo] errore non bloccante ignorato")


async def check_manuale_haccp(alerts: list):
    """M1 — Manuale HACCP aggiornato di recente?"""
    doc = await db.manuale_haccp_dinamico.find_one({"_id": "sezioni_dinamiche"})
    if not doc:
        alerts.append(
            _alert(
                "M1",
                "Manuale HACCP dinamico non generato",
                "Generare il manuale aggiornato per garantire la compliance.",
                "alta",
                "fornitori",
            )
        )
        return
    try:
        aggiornato = datetime.fromisoformat(doc["aggiornato_il"])
        ore_fa = (datetime.now(timezone.utc) - aggiornato).total_seconds() / 3600
        if ore_fa > 48:
            alerts.append(
                _alert(
                    "M1b",
                    f"Manuale HACCP non aggiornato da {int(ore_fa)}h",
                    "Il manuale verrà aggiornato automaticamente stanotte dalla pipeline.",
                    "bassa",
                    "fornitori",
                )
            )
    except Exception:
        logger.debug("[supervisor_operativo] errore non bloccante ignorato")


# ─────────────────────────────────────────────────────────────────────────────
#  NUOVI MODULI ePACKPRO
# ─────────────────────────────────────────────────────────────────────────────


async def check_controllo_olio_oggi(alerts: list):
    """Controlla se il monitoraggio olio frittura è stato registrato oggi."""
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = await db.controllo_olio.find_one({"data": oggi})
    if not doc:
        # Controlla se oggi c'è stato utilizzo della friggitrice (produzione)
        produzioni_con_fritto = await db.produzioni.count_documents(
            {"data": oggi, "ricetta_nome": {"$regex": "frit|donut|arancin|olio", "$options": "i"}}
        )
        if produzioni_con_fritto > 0 or datetime.now(timezone.utc).weekday() < 5:  # lun-ven
            alerts.append(
                _alert(
                    "olio_oggi",
                    "Controllo Olio Frittura mancante",
                    f"Nessun controllo olio registrato oggi. Verificare colore, odore e polarità.",
                    "alta",
                    "controllo_olio",
                    0,
                )
            )


async def check_temperature_cottura_oggi(alerts: list):
    """Controlla se le temperature di cottura sono state registrate oggi."""
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = await db.temperature_cottura.find_one({"data": oggi})
    if not doc:
        # Solo se ci sono produzioni oggi
        prod_oggi = await db.produzioni.count_documents({"data": oggi})
        if prod_oggi > 0:
            alerts.append(
                _alert(
                    "cottura_oggi",
                    "Temperature Cottura mancanti",
                    f"Sono state registrate {prod_oggi} produzioni oggi ma nessuna temperatura di cottura.",
                    "alta",
                    "temp_cottura",
                    prod_oggi,
                )
            )


async def check_ricezione_merce_oggi(alerts: list):
    """Controlla se sono state registrate ricezioni merce nelle ultime 48h."""
    da_quando = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%d")
    count = await db.ricezioni_merce.count_documents({"data": {"$gte": da_quando}})
    # Controlla se ci sono fatture recenti da verificare (lotti fornitori non ancora ricevuti)
    lotti_da_verificare = await db.lotti_fornitori.count_documents(
        {"created_at": {"$gte": da_quando}, "esaurito": {"$ne": True}, "solo_magazzino": {"$ne": True}}
    )
    if count == 0 and lotti_da_verificare > 3:
        alerts.append(
            _alert(
                "ricezione_48h",
                "Ricezione Merce non verificata",
                f"{lotti_da_verificare} forniture recenti non ancora verificate in accettazione.",
                "media",
                "ricezione_merce",
                lotti_da_verificare,
            )
        )


async def check_qualifiche_fornitori_scadenza(alerts: list):
    """Alert per qualifiche fornitore in scadenza (entro 30 giorni) o già scadute."""
    try:
        from app.lotti.routers.fornitori import get_scadenze_rinnovo_qualifica

        result = await get_scadenze_rinnovo_qualifica(giorni_soglia=30)

        scadute = result.get("scadute", [])
        if scadute:  # UN alert aggregato con l'elenco, non uno per fornitore
            a = _alert(
                "QUALIFICHE_SCADUTE",
                f"{len(scadute)} qualifica/he fornitore SCADUTA/E",
                "Qualifiche HACCP fornitore da rinnovare subito. Tocca per l'elenco.",
                "alta",
                "fornitori",
                len(scadute),
            )
            a["items"] = [
                {"id": (f.get("nome") or f.get("fornitore", "?")),
                 "nome": f"{f.get('nome') or f.get('fornitore','?')} — scaduta da {abs(f.get('giorni_alla_scadenza', 0))} gg"}
                for f in scadute[:60]
            ]
            alerts.append(a)

        in_scad = result.get("in_scadenza", [])
        if in_scad:
            a = _alert(
                "QUALIFICHE_IN_SCADENZA",
                f"{len(in_scad)} qualifica/he fornitore in scadenza (30 gg)",
                "Pianificare il rinnovo delle qualifiche HACCP. Tocca per l'elenco.",
                "media",
                "fornitori",
                len(in_scad),
            )
            a["items"] = [
                {"id": (f.get("nome") or f.get("fornitore", "?")),
                 "nome": f"{f.get('nome') or f.get('fornitore','?')} — scade il {f.get('scadenza_qualifica','?')}"}
                for f in in_scad[:60]
            ]
            alerts.append(a)
    except Exception:
        logger.debug("[supervisor_operativo] errore non bloccante ignorato")


async def check_alert_prezzi_ingredienti(alerts: list):
    """Legge gli alert prezzi non letti e li propaga nel supervisore come UN
    alert aggregato con elenco (prima era una sfilza di alert singoli criptici
    — segnalato da Enzo 04/07/2026). FILTRO RUMORE (Enzo 13/06/2026): mai voci
    di servizio/non-food e mai doppioni con lo stesso titolo.
    La ✕ su questo alert marca le voci come LETTE nel registro alert_prezzi
    (vedi silenzia_alert): prima nessuno le marcava mai e ricomparivano
    all'infinito."""
    from app.lotti.routers.classificatore_alimenti import e_non_food_certo
    nuovi = (
        await db.alert_prezzi.find({"letto": False}, {"_id": 0})
        .sort("creato_il", -1)
        .limit(60)
        .to_list(60)
    )
    voci, visti = [], set()
    for a in nuovi:
        titolo = a.get("titolo", "")
        nome_prod = titolo.split(":")[0].strip()
        if e_non_food_certo(nome_prod):
            continue
        if titolo in visti:
            continue
        visti.add(titolo)
        voci.append({"id": a.get("id") or titolo, "nome": titolo})
    if voci:
        a = _alert(
            "PREZZI_INGREDIENTI",
            f"{len(voci)} variazion{'e' if len(voci)==1 else 'i'} di prezzo ingredienti da controllare",
            "Prezzo al kg ricalcolato dalle ultime fatture. ATTENZIONE: cali "
            "fortissimi (−70%…−99%) di solito NON sono sconti veri — è la stessa "
            "merce letta con confezione/peso diversi tra una fattura e l'altra. "
            "Tocca una voce per controllarla nel Comparatore; la ✕ le segna "
            "tutte come viste (tornano solo variazioni NUOVE).",
            "media",
            # SEMPRE "comparatore": un alert di prezzo riguarda un INGREDIENTE
            # (mandare a "ricette" apriva una pagina a caso).
            "comparatore",
            len(voci),
        )
        a["items"] = voci[:60]
        alerts.append(a)


# ─────────────────────────────────────────────────────────────────────────────
#  FREQUENZA ACQUISTI — alert intelligenti su prodotti del dizionario
# ─────────────────────────────────────────────────────────────────────────────

# Soglie configurabili: prodotto → giorni massimi senza acquisto
# Se non specificato, usa la soglia di default (60 giorni)
SOGLIE_PRODOTTI = {
    "farina": 30,
    "burro": 20,
    "uova": 20,
    "lievito": 20,
    "latte": 14,
    "panna": 14,
    "zucchero": 30,
    "sale": 60,
    "olio": 30,
    "staccante": 20,
    "mandorle": 45,
    "cioccolato": 30,
    "ricotta": 14,
    "vaniglia": 60,
    "lievito madre": 20,
}
SOGLIA_DEFAULT_GG = 60  # giorni senza acquisto → alert
SOGLIA_DOPPIO_ACQUISTO_GG = 30  # finestra per rilevare doppio acquisto nello stesso mese


async def check_prodotti_non_acquistati(alerts: list):
    """
    Alert per prodotti del dizionario non acquistati da troppo tempo.
    Usa ultima_fattura_data per calcolare i giorni dall'ultimo acquisto.
    Genera messaggi del tipo:
      'Non stai acquistando mandorle da oltre 45 giorni'
      'Non stai comprando staccante per teglie da oltre 20 giorni'
    """
    oggi = datetime.now(timezone.utc).replace(tzinfo=None)

    # Legge solo prodotti con ultima_fattura_data valorizzata e conteggio > 0
    prodotti = await db.dizionario_prodotti.find(
        {
            "ultima_fattura_data": {"$exists": True, "$ne": ""},
            "conteggio_acquisti": {"$gt": 0},
        },
        {
            "_id": 0,
            "nome_normalizzato": 1,
            "nome_canonico": 1,
            "ultima_fattura_data": 1,
            "conteggio_acquisti": 1,
        },
    ).to_list(2000)

    fermi = []  # UN alert aggregato, non uno per prodotto (riempiva il pannello)
    for p in prodotti:
        nome = (p.get("nome_canonico") or p.get("nome_normalizzato") or "").strip()
        if not nome or len(nome) < 3:
            continue

        # Trova soglia specifica o usa default
        soglia_gg = SOGLIA_DEFAULT_GG
        for keyword, gg in SOGLIE_PRODOTTI.items():
            if keyword in nome.lower():
                soglia_gg = gg
                break

        # Calcola giorni dall'ultimo acquisto
        ufd = (p.get("ultima_fattura_data") or "").strip()
        if not ufd:
            continue
        try:
            if "-" in ufd:
                data_ult = datetime.strptime(ufd[:10], "%Y-%m-%d")
            else:
                data_ult = datetime.strptime(ufd[:10], "%d/%m/%Y")
        except Exception:
            continue

        giorni = (oggi - data_ult).days
        if giorni >= soglia_gg:
            fermi.append({"nome": nome, "giorni": giorni,
                          "ultimo": data_ult.strftime("%d/%m/%Y")})

    if fermi:
        fermi.sort(key=lambda f: -f["giorni"])
        primo = fermi[0]
        a = _alert(
            "ACQ_FERMI",
            f"{len(fermi)} prodott{'o' if len(fermi)==1 else 'i'} che non compri da troppo tempo",
            f"Il più fermo: {primo['nome']} (ultimo acquisto {primo['ultimo']}, "
            f"{primo['giorni']} giorni fa). Tocca per l'elenco completo — se un "
            f"prodotto non serve più, ignoralo pure con la ✕.",
            "media",
            "ordini",
            len(fermi),
        )
        a["items"] = [
            {"id": f["nome"], "nome": f"{f['nome']} — {f['giorni']} gg (ultimo {f['ultimo']})"}
            for f in fermi[:60]
        ]
        alerts.append(a)


async def check_doppio_acquisto_mese(alerts: list):
    """
    Alert SOLO per veri sospetti di doppio ordine: stesso prodotto, stesso
    fornitore, STESSO GIORNO, 2+ righe. Comprare uova 40 volte al mese è la
    normalità di una pasticceria, non un'anomalia (Enzo, 13/06/2026).
    """
    oggi = datetime.now(timezone.utc).replace(tzinfo=None)
    inizio_finestra = oggi - timedelta(days=SOGLIA_DOPPIO_ACQUISTO_GG)

    # Conta acquisti per prodotto nel mese corrente guardando lotti_fornitori
    pipeline = [
        {
            "$match": {
                "data_fattura": {"$exists": True, "$ne": ""},
                "created_at": {"$gte": inizio_finestra.isoformat()},
            }
        },
        {
            "$group": {
                "_id": {
                    "prodotto": "$prodotto_nome_norm",
                    "fornitore": "$fornitore",
                    "giorno": "$data_fattura",
                },
                "conteggio": {"$sum": 1},
                "prodotto_nome": {"$first": "$prodotto_nome"},
                "date": {"$push": "$data_fattura"},
            }
        },
        {"$match": {"conteggio": {"$gte": 2}}},
        {"$sort": {"conteggio": -1}},
        {"$limit": 10},
    ]

    try:
        cursor = db.lotti_fornitori.aggregate(pipeline)
        duplicati = await cursor.to_list(20)
    except Exception:
        return

    for d in duplicati:
        nome = (d.get("prodotto_nome") or d["_id"].get("prodotto") or "").strip().title()
        n = d["conteggio"]
        date_acq = sorted(set(d.get("date", [])))
        fornitore = d["_id"].get("fornitore", "")

        if not nome or len(nome) < 3:
            continue

        alerts.append(
            _alert(
                f"DOPPIO_ACQ_{nome[:20].upper().replace(' ','_')}",
                f"Possibile doppio ordine: {nome} {n} volte lo stesso giorno",
                (
                    f"'{nome}' (da {fornitore}) compare {n} volte in data {date_acq[0] if date_acq else '?'}. "
                    f"Verifica se è un doppio ordine per errore."
                ),
                "bassa",
                "ordini",
                n,
            )
        )


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────────
async def check_ordini_da_convalidare(alerts: list):
    """Alert quando ci sono ordini creati (bozza) non ancora inviati al fornitore.
    È il modo per avvisare l'admin che il pasticcere ha messo qualcosa nel carrello."""
    try:
        n = await db.ordini_fornitori.count_documents({"stato": "bozza"})
    except Exception:
        return
    if n > 0:
        docs = await db.ordini_fornitori.find(
            {"stato": "bozza"}, {"_id": 0, "id": 1, "fornitore": 1, "data_creazione": 1, "creato_da": 1}
        ).to_list(40)
        a = _alert(
            "ORD",
            f"{n} ordine/i da convalidare",
            "Ordini in bozza pronti da rivedere e inviare ai fornitori. Tocca per l'elenco.",
            "alta",
            "ordini",  # il tab "revisione_ordini" non esiste: portava a pagina bianca
            contatore=n,
        )
        a["items"] = [
            {"id": d.get("id"),
             "nome": f"{d.get('fornitore','?')} · {str(d.get('data_creazione',''))[:10]}" + (f" · {d.get('creato_da')}" if d.get("creato_da") else "")}
            for d in docs
        ]
        alerts.append(a)


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
    await check_dati_da_completare(alerts)
    await check_fornitori_inattivi(alerts)
    await check_anomalie_senza_azione(alerts)
    await check_libretti_sanitari(alerts)
    await check_pipeline(alerts)
    await check_manuale_haccp(alerts)
    # Nuovi moduli ePackPro
    await check_controllo_olio_oggi(alerts)
    await check_temperature_cottura_oggi(alerts)
    await check_ricezione_merce_oggi(alerts)
    # Frequenza acquisti
    await check_prodotti_non_acquistati(alerts)
    await check_doppio_acquisto_mese(alerts)
    await check_alert_prezzi_ingredienti(alerts)
    await check_qualifiche_fornitori_scadenza(alerts)
    await check_ordini_da_convalidare(alerts)

    # Alert silenziati oggi (tocco sulla ✕): spariscono fino a domani, o per
    # sempre finché il contatore non CAMBIA (se il problema cresce, riappare).
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    silenziati = {}
    async for s in db.supervisor_alerts_silenziati.find(
        {"data": oggi}, {"_id": 0, "alert_id": 1, "contatore": 1}
    ):
        silenziati[s["alert_id"]] = s.get("contatore")
    # Gli alert CRITICI (obblighi di legge: temperature, libretti sanitari)
    # NON sono silenziabili (decisione Enzo 04/07/2026): si tolgono solo
    # risolvendo il problema. Il filtro li ignora anche se un documento di
    # silenziamento esistesse (enforcement lato server, non solo UI).
    alerts = [
        a for a in alerts
        if a["priorita"] == "critica"
        or not (a["id"] in silenziati and silenziati[a["id"]] == a.get("contatore"))
    ]

    # Ordina per priorità
    alerts.sort(key=lambda a: PRIORITA.get(a["priorita"], 9))

    critici = len([a for a in alerts if a["priorita"] == "critica"])
    alti = len([a for a in alerts if a["priorita"] == "alta"])

    return {
        "data_controllo": datetime.now(timezone.utc).isoformat(),
        "totale_alert": len(alerts),
        "critici": critici,
        "alti": alti,
        "medi": len([a for a in alerts if a["priorita"] == "media"]),
        "bassi": len([a for a in alerts if a["priorita"] == "bassa"]),
        "semaforo": "rosso" if critici > 0 else ("arancione" if alti > 0 else "verde"),
        "alerts": alerts,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  ENDPOINT REST
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/alerts/{alert_id}/silenzia")
async def silenzia_alert(
    alert_id: str, contatore: int = 0, priorita: str = "", _admin=Depends(require_admin)
):
    """Silenzia un alert per OGGI (richiesta Enzo 03/07/2026: "quando clicco
    scompare"). Se il problema peggiora (contatore diverso), l'alert riappare
    da solo: non si può silenziare un incendio che cresce.
    Gli alert CRITICI non si silenziano (decisione Enzo 04/07/2026): il vero
    enforcement è nel filtro di esegui_tutti_i_controlli, qui si dà solo il
    messaggio chiaro.
    25/07/2026 (TRANCHE 2 sicurezza): nascondere un avviso è una decisione del
    titolare, non di chi passa davanti allo schermo — il pannello Supervisore
    vive solo nel gestionale, che è già suo."""
    if priorita == "critica":
        raise HTTPException(
            403,
            "Gli alert critici non si possono nascondere: sono obblighi di legge, "
            "spariscono solo risolvendo il problema.",
        )
    if alert_id == "PREZZI_INGREDIENTI":
        # La ✕ sulle variazioni prezzo = "le ho viste": marca LETTE le voci nel
        # registro alert_prezzi. Senza questo tornavano ogni giorno per sempre
        # (nessun percorso le marcava mai lette — segnalato da Enzo 04/07/2026).
        await db.alert_prezzi.update_many({"letto": False}, {"$set": {"letto": True}})
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await db.supervisor_alerts_silenziati.update_one(
        {"alert_id": alert_id, "data": oggi},
        {"$set": {"alert_id": alert_id, "data": oggi, "contatore": contatore,
                  "silenziato_alle": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"ok": True, "alert_id": alert_id, "fino_a": oggi}


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
        "semaforo": result["semaforo"],
        "totale_alert": result["totale_alert"],
        "critici": result["critici"],
        "alti": result["alti"],
    }


# Cache del cruscotto: 60s di validità. Su Render free le aggregate costano
# secondi: la home deve aprirsi SUBITO. Il bus eventi la invalida quando
# succede qualcosa che cambia i numeri (fattura, ordine, stock).
_CRUSCOTTO_CACHE = {"dati": None, "scade": 0.0}

def invalida_cache_cruscotto():
    _CRUSCOTTO_CACHE["dati"] = None
    _CRUSCOTTO_CACHE["scade"] = 0.0


@router.get("/cruscotto")
async def cruscotto():
    """Tutti i numeri della home in una chiamata: KPI + serie temperature 7gg +
    urgenze. Un solo round-trip invece di sei. Cache 60s + invalidazione a evento."""
    import time as _time
    if _CRUSCOTTO_CACHE["dati"] is not None and _time.monotonic() < _CRUSCOTTO_CACHE["scade"]:
        return _CRUSCOTTO_CACHE["dati"]
    oggi = _ora_locale()
    anno = oggi.year

    # 1) spesa ultimo mese (fatture)
    cutoff = oggi - timedelta(days=30)
    fatture = await db.fatture.find({}, {"_id": 0, "data_fattura": 1, "importo_totale": 1, "totale": 1}).to_list(3000)
    def _pd(s):
        for f in ("%d/%m/%Y", "%Y-%m-%d"):
            try: return datetime.strptime((s or "")[:10], f)
            except Exception: pass
        return None
    spesa_mese = 0.0
    for f in fatture:
        d = _pd(f.get("data_fattura"))
        if d and d.replace(tzinfo=None) >= cutoff.replace(tzinfo=None):
            spesa_mese += float(f.get("importo_totale") or f.get("totale") or 0)

    # 2) giacenze: sotto scorta + esauriti
    prods = await db.magazzino_bar_prodotti.find({}, {"_id": 0, "stock": 1, "soglia_minima": 1}).to_list(2000)
    sotto = sum(1 for p in prods if float(p.get("soglia_minima") or 0) > 0 and float(p.get("stock") or 0) < float(p.get("soglia_minima") or 0))
    esauriti = sum(1 for p in prods if float(p.get("stock") or 0) <= 0)

    # 3) lotti in scadenza (<=7gg) e scaduti
    lotti = await db.lotti.find(dict(FILTRO_LOTTO_APERTO), {"_id": 0, "data_scadenza": 1}).to_list(3000)
    scaduti = in_scad = 0
    for l in lotti:
        d = _pd(l.get("data_scadenza"))
        if not d: continue
        gg = (d.replace(tzinfo=None) - oggi.replace(tzinfo=None)).days
        if gg < 0: scaduti += 1
        elif gg <= 7: in_scad += 1

    # 4) ordini bozza da convalidare
    ordini_bozza = await db.ordini_fornitori.count_documents({"stato": "bozza"})

    # 5) serie temperature ultimi 7 giorni: media giornaliera frigoriferi
    schede = await db.temperature_positive.find({"anno": anno}, {"_id": 0, "temperature": 1}).to_list(50)
    serie = []
    for i in range(6, -1, -1):
        giorno = oggi - timedelta(days=i)
        m, d = str(giorno.month), str(giorno.day)
        valori = []
        for s in schede:
            cella = ((s.get("temperature") or {}).get(m) or {}).get(d)
            if isinstance(cella, dict) and cella.get("temp") is not None:
                valori.append(float(cella["temp"]))
            elif isinstance(cella, (int, float)):
                valori.append(float(cella))
        media = round(sum(valori) / len(valori), 1) if valori else None
        serie.append({"giorno": giorno.strftime("%d/%m"), "media": media, "letture": len(valori)})

    risultato = {
        "kpi": {
            "spesa_mese": round(spesa_mese, 2),
            "fatture_mese": sum(1 for f in fatture if (_pd(f.get("data_fattura")) and _pd(f.get("data_fattura")).replace(tzinfo=None) >= cutoff.replace(tzinfo=None))),
            "sotto_scorta": sotto,
            "esauriti": esauriti,
            "lotti_scaduti": scaduti,
            "lotti_in_scadenza": in_scad,
            "ordini_bozza": ordini_bozza,
        },
        "temperature_7gg": serie,
    }
    _CRUSCOTTO_CACHE["dati"] = risultato
    _CRUSCOTTO_CACHE["scade"] = _time.monotonic() + 60
    return risultato


@router.get("/lotti-in-scadenza")
async def get_lotti_in_scadenza(giorni: int = 7, limit: int = 10):
    """Lotti che scadono entro N giorni — endpoint leggero per la Dashboard.
    Restituisce solo i campi necessari, senza caricare tutti i 300+ lotti."""
    oggi = datetime.now(timezone.utc).replace(tzinfo=None)
    fra = oggi + timedelta(days=giorni)

    tutti = await db.lotti.find(
        dict(FILTRO_LOTTO_APERTO),
        {
            "_id": 0,
            "id": 1,
            "prodotto": 1,
            "data_scadenza": 1,
            "numero_lotto": 1,
            "quantita": 1,
            "unita_misura": 1,
            "frigo_numero": 1,
        },
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
            if data <= fra:
                l["giorni_alla_scadenza"] = (data - oggi).days
                in_scadenza.append(l)
        except Exception:
            logger.debug("[supervisor_operativo] errore non bloccante ignorato")

    in_scadenza.sort(key=lambda x: x["giorni_alla_scadenza"])
    return {"lotti": in_scadenza[:limit], "totale": len(in_scadenza)}


@router.get("/alert-prezzi")
async def get_alert_prezzi(limit: int = 20, solo_non_letti: bool = True):
    """Alert variazioni prezzo ingredienti > 5% — da mostrare nel supervisore."""
    query = {"letto": False} if solo_non_letti else {}
    alerts = (
        await db.alert_prezzi.find(query, {"_id": 0})
        .sort("creato_il", -1)
        .limit(limit)
        .to_list(limit)
    )
    return {"alerts": alerts, "totale": len(alerts)}


@router.patch("/alert-prezzi/{alert_id}/letto")
async def segna_alert_prezzo_letto(alert_id: str):
    await db.alert_prezzi.update_one({"id": alert_id}, {"$set": {"letto": True}})
    return {"ok": True}
