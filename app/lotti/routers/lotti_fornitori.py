"""
Router per la gestione dei Lotti Fornitori.
Traccia lotti con scadenze estratti dalle fatture XML (SAIMA, Naturissime, GE.FI.AL., etc.)
Per fornitori senza lotto (Rondinella, Fiorentino, ecc.) usa il numero fattura come tracciabilità.
Gestisce lo scalaggio automatico delle scorte per lotto quando si usano ingredienti nelle ricette.
"""

import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pymongo import UpdateOne
from app.lotti.db import database as db
from app.lotti.auth import require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lotti-fornitori", tags=["Lotti Fornitori"])


# ──────────────────────────────────────────────────────────────────────────────
# NORMALIZZAZIONE NOME CANONICO
# Il match FIFO ricetta↔lotto avviene su `prodotto_nome_norm`. Se questo resta il
# nome grezzo della fattura ("CAT.A UOVA FRESCHE COD.3..."), la ricetta ("Uova
# Fresche") non lo trova. Qui calcoliamo un nome canonico riutilizzando lo stesso
# dizionario di normalizzazione del resto del sistema (collezione nome_mapping +
# sinonimi statici), così lotti e ricette parlano la stessa lingua.
# ──────────────────────────────────────────────────────────────────────────────

def _pulisci_descrizione(desc: str) -> str:
    """Toglie codici, pesi e riferimenti lotto dalla descrizione grezza."""
    d = re.sub(r"\s*//.*$", "", desc or "", flags=re.IGNORECASE).strip()
    d = re.sub(r"\bL\.?\s*[A-Z0-9\-/]{4,}\b", "", d, flags=re.IGNORECASE)  # riferimenti lotto
    d = re.sub(r"\b\d+[\.,]?\d*\s*(kg|g|gr|ml|lt|l|pz|cl|x\d+)?\b", " ", d, flags=re.IGNORECASE)
    d = re.sub(r"\b[A-Z0-9]{5,}\b", " ", d)  # codici prodotto lunghi
    d = re.sub(r"\s+", " ", d).strip()
    return d


def _consolida(canonico: Optional[str]) -> Optional[str]:
    """Applica il consolidamento varianti del matcher unico (es. 'Margarina Sfoglia'
    → 'Margarina'). Import pigro per evitare cicli a livello di modulo."""
    if not canonico:
        return canonico
    try:
        from app.lotti.routers.ingredienti import _consolida_canonico
        return _consolida_canonico(canonico)
    except Exception:
        return canonico


async def calcola_nome_canonico(descrizione: str, usa_llm: bool = True) -> Optional[str]:
    """Ritorna il nome canonico per una descrizione grezza, o None se ignoto.
    Priorità: 1) mapping salvato (nome_mapping) 2) sinonimi statici del modulo
    normalizzazione 3) matcher unico ingredienti (L1→L2→L3, stesso del resto del
    sistema) 4) None. In tutti i casi il risultato passa per il consolidamento varianti
    così lotti e ricette parlano la stessa lingua (un solo 'Margarina')."""
    if not descrizione:
        return None
    desc_low = descrizione.lower().strip()
    desc_clean = _pulisci_descrizione(descrizione).lower().strip()
    try:
        from app.lotti.routers.normalizzazione import canonico_incoerente_con_finito
    except Exception:
        canonico_incoerente_con_finito = lambda d, c: False  # noqa: E731

    # 1) mapping già salvato in DB (per descrizione_key esatta o contenuta)
    try:
        doc = await db.nome_mapping.find_one(
            {"descrizione_key": desc_low}, {"_id": 0, "nome_canc": 1}
        )
        if not doc and desc_clean:
            doc = await db.nome_mapping.find_one(
                {"descrizione_key": desc_clean}, {"_id": 0, "nome_canc": 1}
            )
        if doc and doc.get("nome_canc"):
            c = _consolida(doc["nome_canc"])
            if not canonico_incoerente_con_finito(descrizione, c):
                return c
    except Exception:
        logger.debug("[lotti_fornitori] errore non bloccante ignorato")

    # 2) sinonimi statici condivisi (stessa fonte usata dall'import prodotti)
    try:
        from app.lotti.routers.normalizzazione import cerca_in_sinonimi_statici
        match = cerca_in_sinonimi_statici(descrizione)
        if match and match.get("nome_canc"):
            c = _consolida(match["nome_canc"])
            if not canonico_incoerente_con_finito(descrizione, c):
                return c
    except Exception:
        logger.debug("[lotti_fornitori] errore non bloccante ignorato")

    # 3) matcher unico di ingredienti (L1→L2→L3 + consolida + impara): un'unica
    #    autorità di normalizzazione, niente dizionario parallelo che si disallinea.
    try:
        from app.lotti.routers.ingredienti import normalizza_ingrediente
        res = await normalizza_ingrediente(descrizione, usa_llm=usa_llm)
        if res.get("ingrediente_canonico"):
            c = res["ingrediente_canonico"]  # già consolidato dal matcher
            if not canonico_incoerente_con_finito(descrizione, c):
                return c
    except Exception:
        logger.debug("[lotti_fornitori] errore non bloccante ignorato")

    return None




def parse_lotto_saima(riferimento_testo: str) -> dict:
    """
    Parsa il campo AltriDatiGestionali SAIMA.
    Formato: 'Id: 617435 - Scadenza: 04/04/2026 - Qt: 2'
    """
    result = {}

    id_match = re.search(r"Id:\s*(\w+)", riferimento_testo, re.IGNORECASE)
    scad_match = re.search(r"Scadenza:\s*(\d{2}/\d{2}/\d{4})", riferimento_testo, re.IGNORECASE)
    # 'Qt:', 'Qta:', 'Qtà:' — la 'à' non rientra in [a-z], quindi si matcha tutto fino ai ':'
    qt_match = re.search(r"Qt[^:\d]*:\s*([\d.]+)", riferimento_testo, re.IGNORECASE)

    if id_match:
        result["lotto_id_fornitore"] = id_match.group(1)
    if scad_match:
        result["data_scadenza"] = scad_match.group(1)
    if qt_match:
        result["quantita_originale"] = float(qt_match.group(1))

    return result


def parse_lotto_naturissime(riferimento_testo: str, riferimento_data: str = None) -> dict:
    """
    Parsa il campo AltriDatiGestionali Naturissime.
    Formato testo: 'IT 016064 C17'
    Formato data: '09/04/2026'
    """
    result = {}
    if riferimento_testo:
        result["lotto_id_fornitore"] = riferimento_testo.strip()
    if riferimento_data:
        result["data_scadenza"] = riferimento_data.strip()
    return result


async def extract_and_save_lotti_from_fattura(fattura_data: dict, prodotti_xml: list):
    """
    Estrae i dati di lotto dai prodotti XML di una fattura e li salva in lotti_fornitori.

    LOGICA:
    - Se il prodotto ha _lotto_data (SAIMA, Naturissime, ecc.) → salva con lotto_id_fornitore + data_scadenza
    - Se il prodotto NON ha _lotto_data (Rondinella, Fiorentino, ecc.) → salva con
      numero_fattura come riferimento e data_fattura come data tracciabilità

    Chiamato durante l'importazione XML.
    """
    fornitore = (fattura_data.get("fornitore", "") or "").strip().strip('"').strip()
    numero_fattura = fattura_data.get("numero_fattura", "")
    data_fattura = fattura_data.get("data_fattura", "")

    saved = 0
    for prodotto in prodotti_xml:
        prezzo_unitario = float(str(prodotto.get("prezzo", 0) or 0))
        # Ignora prodotti gratuiti (sconto merce) — già gestiti dalla collection sconti_merce
        if prezzo_unitario <= 0:
            continue

        descrizione = re.sub(r"\s+", " ", prodotto.get("descrizione", "").strip())
        # Alcune fatture (SAIMA) arrivano col testo lotto APPICCICATO alla descrizione:
        # 'MELANGE ... | Id: 615526 - Scadenza: 31/05/2026 - Qtà: 30'.
        # Lo estraiamo come dati lotto (fallback se _lotto_data manca) e puliamo il nome.
        lotto_inline = {}
        m_inline = re.search(r"\|?\s*Id:\s*\w+.*$", descrizione, flags=re.IGNORECASE)
        if m_inline and "scadenza" in m_inline.group(0).lower():
            lotto_inline = parse_lotto_saima(m_inline.group(0))
            descrizione = descrizione[: m_inline.start()].strip(" |-")
        # Rimuovi info lotto dalla descrizione per normalizzazione
        descrizione_pulita = re.sub(r"\s*//.*$", "", descrizione, flags=re.IGNORECASE).strip()
        # nome_norm = nome CANONICO (dal dizionario) così la ricetta lo ritrova nel FIFO;
        # fallback alla descrizione pulita se il prodotto non è ancora nel dizionario.
        _canonico = await calcola_nome_canonico(descrizione_pulita)
        nome_norm = (_canonico.lower().strip() if _canonico else descrizione_pulita.lower().strip())

        if not nome_norm:
            continue

        quantita = float(str(prodotto.get("quantita", 0) or 0))
        unita = prodotto.get("unita_misura", "KG").upper()

        lotto_data = prodotto.get("_lotto_data", {}) or lotto_inline
        # Riga XML con qta fittizia (1 collo) ma quantità reale nel testo lotto → usa quella
        if lotto_inline.get("quantita_originale") and quantita <= 1:
            quantita = float(lotto_inline["quantita_originale"])

        if lotto_data and lotto_data.get("lotto_id_fornitore"):
            # ── CASO 1: Prodotto CON lotto fornitore (SAIMA, Naturissime, ecc.) ──
            lotto_id = lotto_data.get("lotto_id_fornitore")
            data_scadenza = lotto_data.get("data_scadenza", "")

            # Controlla se lotto già esistente (stesso id + fornitore)
            existing = await db.lotti_fornitori.find_one(
                {"lotto_id_fornitore": lotto_id, "fornitore": fornitore}
            )
            if existing:
                continue

            giorni_alla_scadenza = None
            scaduto = False
            try:
                if data_scadenza and "/" in data_scadenza:
                    dt_scad = datetime.strptime(data_scadenza, "%d/%m/%Y")
                    now = datetime.now()
                    giorni_alla_scadenza = (dt_scad - now).days
                    scaduto = giorni_alla_scadenza < 0
            except Exception:
                pass  # Data scadenza non parsabile — lotto saltato

            qt_orig = lotto_data.get("quantita_originale", quantita)

            lotto_doc = {
                "id": str(uuid.uuid4()),
                "fornitore": fornitore,
                "prodotto_nome": descrizione_pulita,
                "prodotto_nome_norm": nome_norm,
                "nome_canonico": (_canonico or ""),
                "lotto_id_fornitore": lotto_id,
                "tipo_tracciabilita": "lotto_fornitore",  # SAIMA, Naturissime...
                "data_scadenza": data_scadenza,
                "giorni_alla_scadenza": giorni_alla_scadenza,
                "scaduto": scaduto,
                "quantita_originale": qt_orig,
                "quantita_acquistata": quantita,
                "quantita_disponibile": quantita,
                "unita_misura": unita,
                "prezzo_unitario": prezzo_unitario,
                "fattura_ref": numero_fattura,
                "data_fattura": data_fattura,
                "esaurito": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

        else:
            # ── CASO 2: Prodotto SENZA lotto (Rondinella, Fiorentino, ecc.) ──
            # Usa numero fattura + prodotto come chiave di deduplicazione
            existing = await db.lotti_fornitori.find_one(
                {
                    "fattura_ref": numero_fattura,
                    "prodotto_nome_norm": nome_norm,
                    "fornitore": fornitore,
                }
            )
            if existing:
                continue

            lotto_doc = {
                "id": str(uuid.uuid4()),
                "fornitore": fornitore,
                "prodotto_nome": descrizione_pulita,
                "prodotto_nome_norm": nome_norm,
                "nome_canonico": (_canonico or ""),
                "lotto_id_fornitore": f"FAT-{numero_fattura}",  # usa n. fattura come ID tracciabilità
                "tipo_tracciabilita": "fattura",  # Rondinella, Fiorentino, ecc.
                "data_scadenza": "",  # non disponibile
                "giorni_alla_scadenza": None,
                "scaduto": False,
                "quantita_originale": quantita,
                "quantita_acquistata": quantita,
                "quantita_disponibile": quantita,
                "unita_misura": unita,
                "prezzo_unitario": prezzo_unitario,
                "fattura_ref": numero_fattura,
                "data_fattura": data_fattura,
                "esaurito": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

        await db.lotti_fornitori.insert_one(lotto_doc)
        saved += 1

    return saved


# ==================== ENDPOINTS ====================


@router.get("")
async def get_lotti_fornitori(
    fornitore: Optional[str] = None,
    prodotto: Optional[str] = None,
    esaurito: Optional[bool] = None,
    in_scadenza_giorni: Optional[int] = None,  # es. 30 = scade entro 30 giorni
    limit: Optional[int] = None,  # opzionale, default nessun limite
):
    """Lista lotti fornitori con stato scorte"""
    query = {}
    if fornitore:
        query["fornitore"] = {"$regex": fornitore, "$options": "i"}
    if prodotto:
        query["prodotto_nome_norm"] = {"$regex": prodotto.lower(), "$options": "i"}
    if esaurito is not None:
        query["esaurito"] = esaurito

    # Aggiorna giorni alla scadenza
    now = datetime.now()

    lotti = await db.lotti_fornitori.find(query, {"_id": 0}).to_list(500)

    # Aggiorna giorni_alla_scadenza in real-time
    result = []
    for l in lotti:
        try:
            if l.get("data_scadenza") and "/" in l["data_scadenza"]:
                dt = datetime.strptime(l["data_scadenza"], "%d/%m/%Y")
                l["giorni_alla_scadenza"] = (dt - now).days
                l["scaduto"] = l["giorni_alla_scadenza"] < 0
        except Exception as e:
            logging.exception(f"[lotti_fornitori] Errore non gestito: {e}")

        if in_scadenza_giorni is not None:
            giorni = l.get("giorni_alla_scadenza")
            if giorni is None or giorni > in_scadenza_giorni:
                continue

        result.append(l)

    # Ordina per data scadenza: più prossima prima, poi scaduti (giorni negativi) alla fine
    def sort_key(l):
        g = l.get("giorni_alla_scadenza")
        if g is None:
            return 9999
        if g < 0:  # scaduto → manda in fondo agli scaduti ma prima dei senza data
            return 5000 + abs(g)
        return g  # in scadenza/ok → ordine crescente (più vicino prima)

    result.sort(key=sort_key)
    if limit is not None:
        result = result[:limit]
    return result


@router.delete("/pulizia-scaduti")
async def rimuovi_lotti_scaduti(giorni_grazia: int = 0, _admin=Depends(require_admin)):
    """
    Rimuove i lotti fornitori già scaduti (o scaduti da più di giorni_grazia giorni).
    Chiamato dopo ogni aggiornamento fatture per tenere pulita la lista.
    """
    now = datetime.now()
    lotti = await db.lotti_fornitori.find(
        {}, {"_id": 0, "id": 1, "data_scadenza": 1, "prodotto_nome": 1}
    ).to_list(5000)
    eliminati = []
    for l in lotti:
        ds = l.get("data_scadenza", "")
        if not ds or "/" not in ds:
            continue
        try:
            dt = datetime.strptime(ds, "%d/%m/%Y")
            giorni = (dt - now).days
            if giorni < -giorni_grazia:
                await db.lotti_fornitori.delete_one({"id": l["id"]})
                eliminati.append(
                    {
                        "id": l["id"],
                        "prodotto": l.get("prodotto_nome"),
                        "scadenza": ds,
                        "giorni": giorni,
                    }
                )
        except Exception as e:
            logger.warning(f"[lotti_fornitori] Pulizia lotto fallita: {e}")
    return {"success": True, "eliminati": len(eliminati), "dettagli": eliminati}


@router.delete("/{lotto_id}")
async def elimina_lotto(lotto_id: str, _admin=Depends(require_admin)):
    result = await db.lotti_fornitori.delete_one({"id": lotto_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Lotto non trovato")
    return {"success": True}


@router.post("/normalizza-nomi")
async def normalizza_nomi_lotti(
    solo_vuoti: bool = False, usa_llm: bool = False, batch: int = 500
):
    """
    Ricalcola `prodotto_nome_norm` e `nome_canonico` per i lotti fornitori, usando il
    matcher unico (L1→L2→L3 + consolidamento). È ciò che permette al FIFO di trovare i
    lotti a partire dal nome ingrediente della ricetta.

    - solo_vuoti=True: tocca solo i lotti senza prodotto_nome_norm.
    - usa_llm=False (default): solo L1+L2, deterministico e veloce → niente timeout.
      Mettere True solo per un giro di recupero sui residui non riconosciuti.
    - Scorre a cursore (no cap a 5000) e scrive in bulk a blocchi di `batch`.

    `prodotto_nome_norm` viene impostato al nome canonico (minuscolo) se riconosciuto,
    altrimenti alla descrizione pulita minuscola (fallback, comunque migliore del grezzo).
    """
    query = {} if not solo_vuoti else {
        "$or": [{"prodotto_nome_norm": {"$in": ["", None]}}, {"prodotto_nome_norm": {"$exists": False}}]
    }

    # PERF: precarica nome_mapping una sola volta e matcha in-memory.
    # Evita ~3 query Atlas per lotto (era la causa del timeout su tutta la collection).
    mapping = {}
    async for m in db.nome_mapping.find({}, {"_id": 0, "descrizione_key": 1, "nome_canc": 1}):
        k, v = m.get("descrizione_key"), m.get("nome_canc")
        if k and v:
            mapping[k] = v
    try:
        from app.lotti.routers.ingredienti import match_livello2, _consolida_canonico
    except Exception:
        match_livello2 = lambda n: None  # noqa: E731
        _consolida_canonico = lambda c: c  # noqa: E731
    try:
        from app.lotti.routers.normalizzazione import cerca_in_sinonimi_statici
    except Exception:
        cerca_in_sinonimi_statici = None

    def _match_inmemory(raw):
        low = raw.lower().strip()
        clean = _pulisci_descrizione(raw).lower().strip()
        c = mapping.get(low) or (mapping.get(clean) if clean else None)
        if not c and cerca_in_sinonimi_statici:
            try:
                mm = cerca_in_sinonimi_statici(raw)
                if mm and mm.get("nome_canc"):
                    c = mm["nome_canc"]
            except Exception:
                logger.debug("[lotti_fornitori] errore non bloccante ignorato")
        if not c:
            c = match_livello2(raw)  # keyword in-memory, già consolidato
        c = _consolida_canonico(c) if c else None
        # Guardia dominio: un prodotto finito/aroma non è un ingrediente madre.
        if c and cerca_in_sinonimi_statici:
            try:
                from app.lotti.routers.normalizzazione import canonico_incoerente_con_finito
                if canonico_incoerente_con_finito(raw, c):
                    c = None
            except Exception:
                logger.debug("[lotti_fornitori] errore non bloccante ignorato")
        return c

    aggiornati = 0
    riconosciuti = 0
    fallback = 0
    esempi = []
    ops = []

    async def _flush():
        if ops:
            await db.lotti_fornitori.bulk_write(ops, ordered=False)
            ops.clear()

    cursor = db.lotti_fornitori.find(query, {
        "_id": 0, "id": 1, "prodotto_nome": 1, "fornitore": 1,
        "data_scadenza": 1, "quantita_disponibile": 1, "quantita_acquistata": 1,
        "quantita_originale": 1, "unita_misura": 1, "lotto_id_fornitore": 1,
    })
    riparati_fornitore = 0
    riparati_saima = 0
    async for l in cursor:
        nome_raw = l.get("prodotto_nome") or ""
        if not nome_raw:
            continue
        set_extra = {}

        # ── Riparazione fornitore: virgolette residue dall'XML ('"RONDINELLA..."') ──
        forn = (l.get("fornitore") or "").strip()
        forn_clean = forn.strip('"').strip()
        if forn_clean and forn_clean != forn:
            set_extra["fornitore"] = forn_clean
            riparati_fornitore += 1
        if forn_clean:
            set_extra["fornitore_norm"] = forn_clean.lower()

        # ── Riparazione coda lotto Saima rimasta nel nome ('... | Id: x - Scadenza: ... - Qtà: n') ──
        m = re.search(r"\|?\s*Id:\s*\w+.*$", nome_raw, flags=re.IGNORECASE | re.DOTALL)
        if m and "scadenza" in m.group(0).lower():
            dati = parse_lotto_saima(m.group(0))
            nome_raw = re.sub(r"\s+", " ", nome_raw[: m.start()]).strip(" |-").strip()
            set_extra["prodotto_nome"] = nome_raw
            set_extra["descrizione_completa"] = nome_raw
            if dati.get("lotto_id_fornitore") and str(l.get("lotto_id_fornitore", "")).startswith("FAT-"):
                set_extra["lotto_id_fornitore"] = dati["lotto_id_fornitore"]
                set_extra["tipo_tracciabilita"] = "lotto_fornitore"
            if dati.get("data_scadenza") and not (l.get("data_scadenza") or "").strip():
                set_extra["data_scadenza"] = dati["data_scadenza"]
            # Quantità fittizia (1 collo, unità vuota) ma quantità reale nel testo lotto
            qta_vera = dati.get("quantita_originale")
            if qta_vera and float(l.get("quantita_disponibile") or 0) <= 1 \
                    and float(l.get("quantita_acquistata") or 0) <= 1:
                set_extra["quantita_originale"] = qta_vera
                set_extra["quantita_acquistata"] = qta_vera
                set_extra["quantita_disponibile"] = qta_vera
                if not (l.get("unita_misura") or "").strip():
                    set_extra["unita_misura"] = "KG"
            riparati_saima += 1

        canonico = _match_inmemory(nome_raw)
        # LLM solo se esplicitamente richiesto e solo sui residui non riconosciuti
        if not canonico and usa_llm:
            canonico = await calcola_nome_canonico(nome_raw, usa_llm=True)
        if canonico:
            nuovo_norm = canonico.lower().strip()
            riconosciuti += 1
        else:
            nuovo_norm = _pulisci_descrizione(nome_raw).lower().strip() or nome_raw.lower().strip()
            fallback += 1
        ops.append(UpdateOne(
            {"id": l["id"]},
            {"$set": {"prodotto_nome_norm": nuovo_norm, "nome_canonico": canonico or "", **set_extra}},
        ))
        aggiornati += 1
        if len(esempi) < 12:
            esempi.append({"da": nome_raw[:45], "norm": nuovo_norm, "canonico": canonico or "(grezzo)"})
        if len(ops) >= batch:
            await _flush()
    await _flush()

    return {
        "success": True,
        "lotti_processati": aggiornati,
        "riconosciuti_dal_dizionario": riconosciuti,
        "fallback_descrizione_pulita": fallback,
        "riparati_fornitore": riparati_fornitore,
        "riparati_coda_saima": riparati_saima,
        "usa_llm": usa_llm,
        "esempi": esempi,
    }


@router.post("/reimporta-da-fatture")
async def reimporta_lotti_da_fatture(azzera: bool = False, _admin=Depends(require_admin)):
    """
    Re-importa tutti i lotti dalle fatture nel DB.
    Aggiunge anche gli ingredienti di fornitori senza lotto (es. Rondinella, Fiorentino)
    usando il numero fattura come riferimento di tracciabilità.

    Se azzera=True, svuota prima la collection lotti_fornitori.
    """
    if azzera:
        await db.lotti_fornitori.delete_many({})

    # Legge fornitori esclusi
    fornitori_esclusi_docs = await db.fornitori.find(
        {"escluso": True}, {"_id": 0, "nome": 1}
    ).to_list(1000)
    nomi_esclusi = {f["nome"].strip().lower() for f in fornitori_esclusi_docs if f.get("nome")}

    fatture = await db.fatture.find({}, {"_id": 0}).to_list(10000)
    totale_salvati = 0
    totale_saltati = 0
    fatture_elaborate = 0

    for fattura in fatture:
        fornitore = fattura.get("fornitore", "").strip()
        if not fornitore or fornitore.lower() in nomi_esclusi:
            continue

        prodotti_xml = fattura.get("prodotti", [])
        saved = await extract_and_save_lotti_from_fattura(fattura, prodotti_xml)
        totale_salvati += saved
        totale_saltati += len(prodotti_xml) - saved
        fatture_elaborate += 1

    return {
        "success": True,
        "fatture_elaborate": fatture_elaborate,
        "lotti_salvati": totale_salvati,
        "righe_saltate": totale_saltati,
        "totale_lotti_db": await db.lotti_fornitori.count_documents({}),
    }
