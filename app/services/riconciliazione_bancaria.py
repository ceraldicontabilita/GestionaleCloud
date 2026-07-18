"""
Riconciliazione Bancaria — motore unico.

Prima esistevano due motori automatici paralleli agganciati a due punti
diversi (entrambi "vivi" nel codice): questo file (ex
app/routers/accounting/riconciliazione_automatica.py, "motore A") era
l'unico dei due davvero raggiunto dal flusso di upload reale
(PrimaNota.jsx -> /api/estratto-conto-movimenti/import); il secondo
("motore B", app/services/riconciliazione_engine.py + gli handler in
app/services/handlers/banca_handlers.py, innescati dall'evento
movimento_banca.importato) non veniva mai propagato da nessun upload
realmente usato, quindi non aveva mai girato su dati reali — vedi
memoria/endpoints/RICONCILIAZIONE_AUDIT.md.

Motore B è stato rimosso; la sua unica idea utile — l'astrazione
"partita aperta" materializzata (app/services/partite_aperte_engine.py),
usata dalla Dashboard Relazionale — resta viva e viene ora aggiornata
anche da QUESTO motore (best-effort, non bloccante) così le due viste
restano coerenti invece di divergere.

REGOLE FONDAMENTALI:
1. Se TROVO match in estratto conto banca → posso mettere "Bonifico" o "Assegno N.XXX"
2. Se NON TROVO in estratto conto → NON posso mettere "Bonifico"
3. Devo rispettare il metodo di pagamento del fornitore (Cassa, Bonifico, etc.)
4. Match ESATTO per importo (±0.05€) o match parziale (pagamento rate)
5. Fuzzy matching per nome fornitore

Punto di ingresso unico: `riconcilia_movimenti_banca()`, richiamata dallo
scheduler (ogni 30 min) e da app/routers/bank/estratto_conto.py dopo ogni
upload — stesso pattern operativo già in produzione da mesi con il
"motore A".
"""
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import uuid
import logging
import re
import itertools

from app.database import Database, Collections
from app.services.scritture_contabili import scrivi_movimento

# Fuzzy matching per nomi fornitori
try:
    from rapidfuzz import fuzz
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False

logger = logging.getLogger(__name__)

COLLECTION_ESTRATTO_CONTO = "estratto_conto_movimenti"
COLLECTION_PRIMA_NOTA_CASSA = "prima_nota_cassa"
COLLECTION_OPERAZIONI_DA_CONFERMARE = "operazioni_da_confermare"
# Canonica: "fornitori" — "suppliers" era un alias vuoto: i lookup metodo
# pagamento fornitore non trovavano mai nulla.
COLLECTION_SUPPLIERS = "fornitori"
COLLECTION_ASSEGNI = "assegni"

# Importi commissioni bancarie da ignorare
IMPORTI_COMMISSIONI = [0.75, 1.00, 1.10, 1.50, 2.00, 2.50, 3.00]


async def _propaga_fattura_pagata(db, fattura_id: str, metodo: str, data_pag: str,
                                   movimento_id: Optional[str] = None,
                                   importo: Optional[float] = None,
                                   source: str = "riconciliazione_bancaria") -> None:
    """
    Helper per propagare FATTURA_PAGATA dopo update invoice in questo file.
    Centralizza i punti di pagamento per evitare duplicazione di codice.
    Fail-safe: logga l'errore senza mai propagarlo.
    """
    try:
        from app.services.event_bus import propagate_event, EventTypes
        await propagate_event(EventTypes.FATTURA_PAGATA, {
            "fattura_id": fattura_id,
            "metodo_pagamento": metodo,
            "data_pagamento": data_pag,
            "movimento_id": movimento_id,
            "importo": importo,
        }, db, source_module=source)
    except Exception:
        logger.exception(f"Errore propagazione fattura.pagata ({source}) fat={fattura_id}")


async def _propaga_f24_pagato(db, f24_id: str, data_pag: str,
                               movimento_id: Optional[str] = None,
                               importo: Optional[float] = None,
                               source: str = "riconciliazione_bancaria") -> None:
    """
    Helper per propagare F24_PAGATO in questo file.
    Fail-safe.
    """
    try:
        from app.services.event_bus import propagate_event, EventTypes
        await propagate_event(EventTypes.F24_PAGATO, {
            "f24_id": f24_id,
            "data_pagamento": data_pag,
            "movimento_id": movimento_id,
            "importo_totale": importo,
        }, db, source_module=source)
    except Exception:
        logger.exception(f"Errore propagazione f24.pagato ({source}) f24={f24_id}")


async def _registra_match_partita_aperta(db, tipo: str, documento_id: str, importo: float,
                                          movimento_id: Optional[str], now: str) -> None:
    """Convergenza best-effort con la Dashboard Relazionale: se esiste una
    partita aperta collegata a questo documento (creata da
    on_fattura_created_crea_partita/on_f24_acquisito_crea_partita), la chiude
    e registra il match in riconciliazioni_match — la stessa collezione letta
    da GET /api/riconciliazione/stats. Non blocca né fa fallire la
    riconciliazione principale se qualcosa qui va storto."""
    try:
        from app.services.partite_aperte_engine import COLL_PARTITE, chiudi_partita

        partita = await db[COLL_PARTITE].find_one(
            {"documento_id": documento_id, "tipo": tipo, "stato": {"$in": ["aperta", "parziale"]}},
            {"_id": 0, "id": 1},
        )
        if not partita:
            return

        match_id = f"rm_{uuid.uuid4().hex[:12]}"
        await chiudi_partita(partita["id"], match_id, importo, db)
        await db["riconciliazioni_match"].insert_one({
            "id": match_id,
            "movimento_id": movimento_id,
            "movimento_collection": COLLECTION_ESTRATTO_CONTO,
            "partita_id": partita["id"],
            "partita_collection": COLL_PARTITE,
            "tipo_match": tipo,
            "importo_riconciliato": round(importo, 2),
            "confidenza": 1.0,
            "origine": "auto",
            "stato": "confermato",
            "created_at": now,
            "confirmed_at": now,
            "confirmed_by": "sistema",
        })
    except Exception:
        logger.exception(f"Errore convergenza partita_aperta per {tipo}/{documento_id}")


async def _alert_match_ambiguo(db, mov_id: Optional[str], motivo: str) -> None:
    """Genera l'alert RIC_MATCH_AMBIGUO quando più fatture candidate hanno
    punteggio di match simile per lo stesso movimento bancario e l'operazione
    finisce in operazioni_da_confermare — prima definito in alert_engine.py
    ma mai generato (vedi memoria/moduli/RICONCILIAZIONE.md). Best-effort,
    non blocca la riconciliazione principale."""
    if not mov_id:
        return
    try:
        from app.services.alert_engine import genera_alert
        await genera_alert(
            "RIC_MATCH_AMBIGUO", mov_id, COLLECTION_ESTRATTO_CONTO, motivo, db,
        )
    except Exception:
        logger.exception(f"Errore generazione alert RIC_MATCH_AMBIGUO per {mov_id}")


async def _crea_operazione_da_confermare_idempotente(db, operazione: dict) -> bool:
    """Inserisce una riga in operazioni_da_confermare SOLO se non ne esiste già
    una aperta (stato="da_confermare") per lo stesso movimento_ec_id.

    Bug trovato nell'audit funzionale del 15/07/2026: lo scheduler rilancia la
    riconciliazione ogni 30 minuti; un movimento ambiguo (più fatture
    candidate con punteggio simile) resta `riconciliato=False` finché
    l'utente non conferma/ignora, quindi ad ogni passaggio veniva rielaborato
    e finiva di nuovo qui — senza questo controllo si creava un nuovo record
    duplicato ogni 30 minuti per lo stesso movimento, invece di riusare
    quello già aperto. Ritorna True se ha davvero inserito (per non
    rigenerare anche l'alert collegato quando il record esisteva già)."""
    esistente = await db[COLLECTION_OPERAZIONI_DA_CONFERMARE].find_one({
        "movimento_ec_id": operazione["movimento_ec_id"],
        "stato": "da_confermare",
    })
    if esistente:
        return False
    await db[COLLECTION_OPERAZIONI_DA_CONFERMARE].insert_one(operazione.copy())
    return True


async def _alert_differenza_importo(db, mov_id: Optional[str], importo_banca: float, importo_fattura: float, fattura_id: Optional[str]) -> None:
    """Genera l'alert RIC_DIFFERENZA_IMPORTO quando una fattura viene
    riconciliata con un movimento bancario di importo diverso (rata,
    commissione trattenuta, arrotondamento) — il motore accetta il match
    per tolleranza ma prima non spiegava mai la differenza, gap #1/#6
    memoria/moduli/RICONCILIAZIONE.md. Additivo, non cambia l'esito del
    match (già deciso), solo lo rende visibile."""
    if not mov_id:
        return
    diff = round(importo_banca - importo_fattura, 2)
    if abs(diff) <= 0.05:
        return
    try:
        from app.services.alert_engine import genera_alert
        await genera_alert(
            "RIC_DIFFERENZA_IMPORTO", mov_id, COLLECTION_ESTRATTO_CONTO,
            f"Movimento banca €{importo_banca:.2f} riconciliato con fattura €{importo_fattura:.2f} "
            f"(differenza €{diff:.2f}) — verificare se è una rata, una commissione trattenuta o un arrotondamento.",
            db, extra={"fattura_id": fattura_id} if fattura_id else None,
        )
    except Exception:
        logger.exception(f"Errore generazione alert RIC_DIFFERENZA_IMPORTO per {mov_id}")


async def _alert_non_riconciliato(db, mov_id: Optional[str], importo: float, descrizione: str) -> None:
    """Genera l'alert RIC_NON_RICONCILIATO quando un movimento EC esce dal
    motore senza alcun match (nessuna fattura/F24/POS/versamento candidato) —
    stesso gap di RIC_MATCH_AMBIGUO: definito in alert_engine.py ma mai
    generato (vedi memoria/moduli/RICONCILIAZIONE.md, gap #6). Idempotente
    (genera_alert non duplica se già aperto), best-effort, non blocca la
    riconciliazione principale."""
    if not mov_id:
        return
    try:
        from app.services.alert_engine import genera_alert
        await genera_alert(
            "RIC_NON_RICONCILIATO", mov_id, COLLECTION_ESTRATTO_CONTO,
            f"Movimento di €{importo:.2f} ({descrizione[:80]}) senza match automatico", db,
        )
    except Exception:
        logger.exception(f"Errore generazione alert RIC_NON_RICONCILIATO per {mov_id}")


async def _alert_pagamento_multiplo(db, mov_id: Optional[str], importo: float) -> None:
    """Genera l'alert RIC_PAGAMENTO_MULTIPLO quando un movimento in uscita
    resta senza match singolo ma la somma di 2-3 fatture fornitore ancora
    aperte combacia (±0.05€) col suo importo — il caso "bonifico cumulativo"
    mai gestito dal motore (gap #7 memoria/moduli/RICONCILIAZIONE.md). Solo
    rilevamento/segnalazione: NON marca nulla come pagato né riconcilia
    automaticamente, la combinazione va sempre confermata da un operatore.
    Best-effort, non blocca la riconciliazione principale."""
    if not mov_id or importo <= 0:
        return
    try:
        candidates = await db[Collections.INVOICES].find(
            {
                "pagato": {"$ne": True},
                # "sospesa" = l'utente ha bloccato la fattura in Prima Nota
                # Provvisoria: non deve essere toccata dal matching automatico.
                "stato_pagamento": {"$nin": ["pagata", "paid", "sospesa"]},
            },
            {"_id": 1, "numero_fattura": 1, "invoice_number": 1,
             "importo_totale": 1, "total_amount": 1,
             "cedente_denominazione": 1, "supplier_name": 1}
        ).limit(40).to_list(40)

        righe = []
        for f in candidates:
            imp = f.get("importo_totale") or f.get("total_amount") or 0
            if imp and 0 < imp < importo:
                righe.append((f, round(float(imp), 2)))

        if len(righe) < 2:
            return

        combo_trovata = None
        for r in (2, 3):
            for combo in itertools.combinations(righe, r):
                if abs(sum(c[1] for c in combo) - importo) <= 0.05:
                    combo_trovata = combo
                    break
            if combo_trovata:
                break

        if not combo_trovata:
            return

        from app.services.alert_engine import genera_alert
        dettaglio_fatture = ", ".join(
            f"{(c[0].get('numero_fattura') or c[0].get('invoice_number') or '?')} €{c[1]:.2f}"
            for c in combo_trovata
        )
        await genera_alert(
            "RIC_PAGAMENTO_MULTIPLO", mov_id, COLLECTION_ESTRATTO_CONTO,
            f"Movimento di €{importo:.2f} senza match singolo — possibile pagamento cumulativo "
            f"di {len(combo_trovata)} fatture (somma combacia): {dettaglio_fatture}",
            db,
            extra={
                "importo_movimento": importo,
                "fatture_candidate": [
                    {"id": str(c[0].get("_id")),
                     "numero": c[0].get("numero_fattura") or c[0].get("invoice_number"),
                     "importo": c[1]}
                    for c in combo_trovata
                ],
            },
        )
    except Exception:
        logger.exception(f"Errore generazione alert RIC_PAGAMENTO_MULTIPLO per {mov_id}")


async def _applica_pagamento_banca(db, fattura: Dict[str, Any], metodo_label: str,
                                   data_ec: str, mov_id: Optional[str], score: int,
                                   now: str, source: str) -> None:
    """Applica il pagamento via banca in modo COERENTE con il resto dell'app:
    crea (idempotente) il movimento in prima_nota_banca, aggiorna TUTTI i flag
    usati dalle varie pagine (pagato/paid/stato_pagamento/prima_nota_*) e
    propaga l'evento FATTURA_PAGATA.

    Prima di questo helper la riconciliazione settava solo pagato/in_banca:
    la fattura risultava pagata ma NON compariva mai in Prima Nota Banca.
    """
    from app.routers.prima_nota_module.sync import registra_pagamento_fattura

    fattura_id = str(fattura.get("id") or fattura.get("_id"))
    importo_fattura = fattura.get("total_amount") or fattura.get("importo_totale") or 0
    update = {
        "pagato": True,
        "paid": True,
        "stato_pagamento": "pagata",
        "metodo_pagamento": metodo_label,
        "in_banca": True,
        "data_pagamento": data_ec,
        "riconciliato_con_ec": mov_id,
        "riconciliato_automaticamente": True,
        "match_score": score,
        "updated_at": now,
    }
    try:
        pn = await registra_pagamento_fattura(fattura, "banca")
        if pn.get("banca"):
            update["prima_nota_id"] = pn["banca"]
            update["prima_nota_tipo"] = "banca"
            update["prima_nota_banca_id"] = pn["banca"]
    except Exception:
        logger.exception(f"Errore registrazione prima nota banca per fattura {fattura_id}")

    filtro = {"_id": fattura["_id"]} if fattura.get("_id") is not None else {"id": fattura.get("id")}
    await db[Collections.INVOICES].update_one(filtro, {"$set": update})
    await _propaga_fattura_pagata(
        db, fattura_id=fattura_id, metodo=metodo_label, data_pag=data_ec,
        movimento_id=mov_id, importo=importo_fattura, source=source,
    )
    await _registra_match_partita_aperta(
        db, tipo="fattura_fornitore", documento_id=fattura_id,
        importo=float(importo_fattura or 0), movimento_id=mov_id, now=now,
    )


def _giorni_pagamento_plausibili(data_ec: str, data_fattura: str) -> Optional[int]:
    """Giorni fra data fattura e movimento EC (None se date non parsabili)."""
    try:
        dt_ec = datetime.strptime(str(data_ec)[:10], "%Y-%m-%d")
        dt_fatt = datetime.strptime(str(data_fattura)[:10], "%Y-%m-%d")
        return (dt_ec - dt_fatt).days
    except (ValueError, TypeError):
        return None


def is_commissione(desc: str, imp: float) -> bool:
    """Verifica se è una commissione bancaria da ignorare."""
    desc_upper = (desc or "").upper()
    imp_abs = abs(imp)

    if any(kw in desc_upper for kw in ['COMMISSIONI', 'COMM.', 'SPESE TENUTA', 'CANONE', 'BOLLO', 'IMPOSTA']):
        return True

    if any(abs(imp_abs - c) < 0.01 for c in IMPORTI_COMMISSIONI) and imp_abs <= 3.00:
        return True

    return False


def match_fornitore_descrizione(fornitore: str, descrizione: str, fuzzy_threshold: int = 80) -> int:
    """
    Verifica se il nome fornitore è presente nella descrizione dell'estratto conto.
    Usa fuzzy matching per gestire variazioni nel nome.

    Returns:
        - 0: Nessun match
        - 1: Match parziale (fuzzy)
        - 2: Match esatto (parole esatte trovate)
    """
    if not fornitore or not descrizione:
        return 0

    desc_upper = descrizione.upper()
    fornitore_upper = fornitore.upper()

    # Rimuovi forme giuridiche comuni per il confronto
    forme_giuridiche = ['S.R.L.', 'SRL', 'S.P.A.', 'SPA', 'S.A.S.', 'SAS', 'S.N.C.', 'SNC', 'DI', 'DI.', 'SOCIETA', 'SOCIETÀ']
    fornitore_clean = fornitore_upper
    for fg in forme_giuridiche:
        fornitore_clean = fornitore_clean.replace(fg, '')

    # Pulisci anche la descrizione
    desc_clean = desc_upper
    for fg in forme_giuridiche:
        desc_clean = desc_clean.replace(fg, '')

    # Estrai parole significative (>3 caratteri)
    parole_fornitore = [p.strip() for p in fornitore_clean.split() if len(p.strip()) > 3]

    if not parole_fornitore:
        return 0

    # === 1. Match esatto: cerca parole del fornitore nella descrizione ===
    matches_esatti = sum(1 for p in parole_fornitore if p in desc_upper)

    # Match se almeno il 50% delle parole o almeno 1 parola significativa
    if matches_esatti >= max(1, len(parole_fornitore) // 2):
        return 2  # Match esatto

    # === 2. Fuzzy matching (se disponibile) ===
    if FUZZY_AVAILABLE:
        # Estrai possibili nomi dalla descrizione (sequenze di parole maiuscole)
        possibili_nomi = re.findall(r'[A-Z][A-Z\s\.\']{3,}(?:S\.?R\.?L\.?|S\.?P\.?A\.?)?', desc_upper)

        for possibile_nome in possibili_nomi:
            # Calcola similarità tra il fornitore e ogni possibile nome estratto
            score = fuzz.ratio(fornitore_clean.strip(), possibile_nome.strip())
            if score >= fuzzy_threshold:
                return 1  # Match fuzzy

            # Prova anche partial_ratio per match parziali (es. "CERALDI" in "CERALDI GROUP")
            partial_score = fuzz.partial_ratio(fornitore_clean.strip(), possibile_nome.strip())
            if partial_score >= 90:  # Soglia alta per partial
                return 1

            # Token set ratio: gestisce parole in ordine diverso
            token_score = fuzz.token_set_ratio(fornitore_clean.strip(), possibile_nome.strip())
            if token_score >= fuzzy_threshold:
                return 1

    return 0


def match_numero_fattura_descrizione(numero_fattura: str, descrizione: str) -> bool:
    """
    Verifica se il numero fattura è presente nella descrizione dell'estratto conto.
    """
    if not numero_fattura or not descrizione:
        return False

    desc_upper = descrizione.upper()
    num_clean = numero_fattura.strip().upper()

    # Rimuovi prefissi comuni (FT, FAT, etc.) e separatori
    num_clean = re.sub(r'^(FT|FAT|FATT|INV|N\.?|NR\.?)[\s\-/]*', '', num_clean)
    # Rimuovi anno e separatori (es. 2024/001234 -> 001234)
    num_clean = re.sub(r'^\d{4}[\s\-/]+', '', num_clean)

    # Cerca il numero nella descrizione
    if num_clean and num_clean in desc_upper:
        return True

    # Cerca anche senza zeri iniziali
    num_no_zeros = num_clean.lstrip('0')
    if num_no_zeros and len(num_no_zeros) >= 3 and num_no_zeros in desc_upper:
        return True

    # Estrai solo numeri dal numero fattura originale
    solo_numeri = re.sub(r'[^\d]', '', numero_fattura)
    if solo_numeri and len(solo_numeri) >= 4 and solo_numeri in desc_upper:
        return True

    return False


def extract_invoice_number(descrizione: str) -> Optional[str]:
    """Estrae numero fattura dalla descrizione estratto conto."""
    if not descrizione:
        return None

    desc_upper = descrizione.upper()

    patterns = [
        r'(?:FAT(?:TURA)?|FT|FATT)[\s\.\-:]*N?[\s\.\-:]*(\d+[\/-]?\d*)',
        r'(?:SALDO|PAG(?:AMENTO)?)\s+(?:FAT(?:TURA)?|FT)\s*N?[\s\.\-:]*(\d+[\/-]?\d*)',
        r'RIF\.?\s*[:\s]*(\d{3,}[\/-]?\d*)',
        r'(?:N|NR|NUM)\.?\s*(\d{3,}[\/-]?\d*)',
        r'[\s\-](\d{4,})(?:\s|$)',
    ]

    for pattern in patterns:
        match = re.search(pattern, desc_upper)
        if match:
            num = match.group(1).strip()
            if len(num) <= 8 and not (len(num) == 8 and num.startswith('20')):
                return num

    return None


def extract_assegno_number(descrizione: str) -> Optional[str]:
    """Estrae numero assegno dalla descrizione."""
    if not descrizione:
        return None

    patterns = [
        r'(?:VOSTRO\s+)?ASSEGNO\s+N\.?\s*(\d+)',
        r'ASS\.?\s+N\.?\s*(\d+)',
        r'CHQ\.?\s*(\d+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, descrizione.upper())
        if match:
            return match.group(1).strip()

    return None


def extract_supplier_name(descrizione: str) -> Optional[str]:
    """Estrae nome fornitore dalla descrizione."""
    if not descrizione:
        return None

    desc_upper = descrizione.upper()

    patterns = [
        r'(?:BENEF(?:ICIARIO)?|A FAVORE DI|VERSO|PER|FAVORE)[\s:]+([A-Z][A-Z\s\.\']+(?:S\.?R\.?L\.?|S\.?P\.?A\.?|S\.?A\.?S\.?|S\.?N\.?C\.?)?)',
        r'([A-Z][A-Z\s\']+(?:S\.?R\.?L\.?|S\.?P\.?A\.?))',
    ]

    for pattern in patterns:
        match = re.search(pattern, desc_upper)
        if match:
            name = match.group(1).strip()
            if len(name) > 3:
                return name

    return None


async def riconcilia_movimenti_banca() -> Dict[str, Any]:
    """
    Motore unico di riconciliazione automatica estratto conto ↔ fatture/F24/
    POS/versamenti.

    REGOLE:
    1. Cerca match ESATTO per importo (±0.05€)
    2. Se trova in EC → metodo = Bonifico o Assegno
    3. Se NON trova in EC → NON può mettere Bonifico
    4. Rispetta metodo fornitore se definito
    """
    db = Database.get_db()
    now = datetime.now(timezone.utc).isoformat()

    results = {
        "movimenti_analizzati": 0,
        "riconciliati_fatture": 0,
        "riconciliati_assegni": 0,
        "riconciliati_f24": 0,
        "riconciliati_pos": 0,
        "riconciliati_versamenti": 0,
        "commissioni_ignorate": 0,
        "dubbi": 0,
        "non_trovati": 0,
        "errors": []
    }

    # Carica movimenti EC non riconciliati
    movimenti_ec = await db[COLLECTION_ESTRATTO_CONTO].find({
        "riconciliato": {"$ne": True}
    }, {"_id": 0}).to_list(5000)

    results["movimenti_analizzati"] = len(movimenti_ec)

    # Metodo pagamento per fornitore (fonte di verità: anagrafica fornitori).
    # Se il fornitore paga in CONTANTI, un match banca sul solo importo è
    # quasi certamente un falso positivo: serve evidenza forte.
    metodo_fornitori: Dict[str, str] = {}
    async for s in db[COLLECTION_SUPPLIERS].find(
        {"metodo_pagamento": {"$exists": True, "$ne": ""}},
        {"_id": 0, "partita_iva": 1, "piva": 1, "vat_number": 1, "metodo_pagamento": 1}
    ):
        for k in (s.get("partita_iva"), s.get("piva"), s.get("vat_number")):
            if k:
                metodo_fornitori[k] = (s.get("metodo_pagamento") or "").lower()

    for mov in movimenti_ec:
        try:
            mov_id = mov.get("id")
            importo = abs(float(mov.get("importo", 0)))
            data_ec = mov.get("data", "")
            descrizione = mov.get("descrizione_originale", "") or mov.get("descrizione", "")
            tipo = mov.get("tipo", "")  # "entrata" o "uscita"

            if importo == 0:
                continue

            # === IGNORA COMMISSIONI ===
            if is_commissione(descrizione, importo):
                await db[COLLECTION_ESTRATTO_CONTO].update_one(
                    {"id": mov_id},
                    {"$set": {
                        "riconciliato": True,
                        "tipo_riconciliazione": "commissione_ignorata",
                        "updated_at": now
                    }}
                )
                results["commissioni_ignorate"] += 1
                continue

            match_found = False
            match_type = None
            match_details = {}

            # === 1. CERCA FATTURE (per USCITE) ===
            if tipo == "uscita" and not match_found:
                num_fattura_ec = extract_invoice_number(descrizione)
                num_assegno = extract_assegno_number(descrizione)
                supplier_name_ec = extract_supplier_name(descrizione)

                # RICERCA MIGLIORATA:
                # 1. Match esatto importo (±0.05€)
                # 2. Match parziale importo (pagamento rate - 10% tolleranza)

                # Query per fatture candidate (importo esatto O importo parziale)
                fatture_candidate = await db[Collections.INVOICES].find({
                    "$and": [
                        {"pagato": {"$ne": True}},
                        # Coerenza: alcuni flussi marcano il pagamento solo qui.
                        # "sospesa" = bloccata manualmente in Prima Nota
                        # Provvisoria, esclusa dal matching automatico.
                        {"stato_pagamento": {"$nin": ["pagata", "paid", "sospesa"]}},
                        {"$or": [
                            # Match esatto
                            {"importo_totale": {"$gte": importo - 0.05, "$lte": importo + 0.05}},
                            {"total_amount": {"$gte": importo - 0.05, "$lte": importo + 0.05}},
                            # Match parziale (il pagamento è circa 50-200% della fattura)
                            {"importo_totale": {"$gte": importo * 0.5, "$lte": importo * 2}},
                            {"total_amount": {"$gte": importo * 0.5, "$lte": importo * 2}}
                        ]}
                    ]
                    # NB: niente proiezione {"_id": 0} — l'_id serve per l'update
                    # (prima ogni match falliva con KeyError '_id' e finiva in errors)
                }).to_list(50)

                # Calcola score per ogni fattura
                fatture_scored = []
                for f in fatture_candidate:
                    score = 0
                    fornitore_fatt = f.get("cedente_denominazione") or f.get("supplier_name") or ""
                    numero_fatt = f.get("numero_fattura") or f.get("invoice_number") or ""
                    data_fatt = f.get("data") or f.get("invoice_date") or ""
                    data_scadenza = f.get("data_scadenza") or ""

                    # Score 1: Importo esatto (+10) vs importo parziale (+3)
                    imp_fatt = f.get("importo_totale") or f.get("total_amount") or 0
                    if abs(imp_fatt - importo) <= 0.05:
                        score += 10  # Match esatto
                    elif abs(imp_fatt - importo) <= imp_fatt * 0.1:  # ±10%
                        score += 5  # Match quasi esatto
                    else:
                        score += 2  # Match parziale (possibile rata)

                    # Score 2: Match fornitore nella descrizione EC (con fuzzy)
                    fornitore_match = match_fornitore_descrizione(fornitore_fatt, descrizione)
                    if fornitore_match == 2:
                        score += 5  # Match esatto
                    elif fornitore_match == 1:
                        score += 3  # Match fuzzy

                    # Score 3: Match numero fattura nella descrizione EC
                    if match_numero_fattura_descrizione(numero_fatt, descrizione):
                        score += 5

                    # Score 4: Numero fattura estratto da EC corrisponde
                    if num_fattura_ec and numero_fatt:
                        num_fatt_clean = re.sub(r'^(FT|FAT|FATT|INV|N\.?|NR\.?)\s*', '', numero_fatt.upper())
                        if num_fattura_ec in num_fatt_clean or num_fatt_clean in num_fattura_ec:
                            score += 5

                    # Score 5: Data movimento vicina a data scadenza (+2)
                    if data_ec and data_scadenza:
                        try:
                            dt_ec = datetime.fromisoformat(data_ec.replace('Z', '+00:00')) if isinstance(data_ec, str) else data_ec
                            dt_scad = datetime.fromisoformat(data_scadenza.replace('Z', '+00:00')) if isinstance(data_scadenza, str) else data_scadenza
                            diff_days = abs((dt_ec - dt_scad).days)
                            if diff_days <= 7:
                                score += 2
                        except Exception:
                            pass

                    # Sanità date: un pagamento non precede la fattura né
                    # dista oltre ~13 mesi. Penalizza i match cross-periodo
                    # (il solo importo non basta più a marcarli "pagati").
                    giorni = _giorni_pagamento_plausibili(data_ec, data_fatt)
                    if giorni is not None and (giorni < -5 or giorni > 400):
                        score -= 5

                    # Metodo fornitore: se in anagrafica paga in CONTANTI,
                    # accetta il match banca solo con evidenza forte
                    # (importo + fornitore/numero in descrizione).
                    piva_fatt = f.get("supplier_vat") or f.get("cedente_piva") or ""
                    if metodo_fornitori.get(piva_fatt) in ("contanti", "cassa", "cash", "contante") and score < 15:
                        continue

                    fatture_scored.append((f, score))

                # Ordina per score decrescente
                fatture_scored.sort(key=lambda x: x[1], reverse=True)

                # Se c'è una fattura con score >= 15 (importo + fornitore + numero) → match sicuro
                if fatture_scored and fatture_scored[0][1] >= 15:
                    fattura = fatture_scored[0][0]
                    match_found = True
                    match_type = "fattura_match_completo"

                    metodo_pagamento = "Bonifico"
                    if num_assegno:
                        metodo_pagamento = f"Assegno N.{num_assegno}"
                        await db[COLLECTION_ASSEGNI].update_one(
                            {"numero": num_assegno},
                            {"$set": {
                                "numero": num_assegno,
                                "importo": importo,
                                "data_emissione": data_ec,
                                "fattura_id": str(fattura.get("_id", fattura.get("id"))),
                                "fornitore": fattura.get("cedente_denominazione") or fattura.get("supplier_name"),
                                "stato": "incassato",
                                "updated_at": now
                            }},
                            upsert=True
                        )
                        results["riconciliati_assegni"] += 1

                    await _applica_pagamento_banca(
                        db, fattura, metodo_pagamento, data_ec, mov_id,
                        fatture_scored[0][1], now, source="ric_auto_esatto_multi",
                    )

                    match_details = {
                        "fattura_id": str(fattura.get("_id")),
                        "numero_fattura": fattura.get("numero_fattura") or fattura.get("invoice_number"),
                        "fornitore": fattura.get("cedente_denominazione") or fattura.get("supplier_name"),
                        "metodo_pagamento": metodo_pagamento,
                        "match_score": fatture_scored[0][1],
                        "match_type": "importo+fornitore+numero"
                    }
                    results["riconciliati_fatture"] += 1
                    imp_fatt_match = fattura.get("importo_totale") or fattura.get("total_amount") or 0
                    await _alert_differenza_importo(db, mov_id, importo, float(imp_fatt_match), match_details["fattura_id"])

                # Se score >= 10 ma < 15 (solo importo + un altro criterio) → match con confidenza media
                elif fatture_scored and fatture_scored[0][1] >= 10 and fatture_scored[0][1] < 15:
                    # Se c'è una sola fattura con questo score → riconcilia
                    fatture_buone = [f for f, s in fatture_scored if s >= 10]

                    # P1-1 (LOGICA §6): la conferma automatica a confidenza media
                    # (importo + un solo altro criterio) NON deve marcare "pagata"
                    # senza una verifica di DATA plausibile. Se la data del
                    # movimento non è coerente con la fattura (pagamento prima
                    # della fattura o distante oltre ~6 mesi) l'auto-conferma
                    # viene declassata a suggerimento manuale.
                    data_plausibile = True
                    if len(fatture_buone) == 1:
                        _f0 = fatture_buone[0]
                        _giorni = _giorni_pagamento_plausibili(
                            data_ec, _f0.get("data") or _f0.get("invoice_date") or ""
                        )
                        if _giorni is not None and (_giorni < -5 or _giorni > 180):
                            data_plausibile = False

                    if len(fatture_buone) == 1 and data_plausibile:
                        fattura = fatture_buone[0]
                        match_found = True
                        match_type = "fattura_match_parziale"

                        metodo_pagamento = "Bonifico"
                        if num_assegno:
                            metodo_pagamento = f"Assegno N.{num_assegno}"

                        await _applica_pagamento_banca(
                            db, fattura, metodo_pagamento, data_ec, mov_id,
                            fatture_scored[0][1], now, source="ric_auto_parziale_singolo",
                        )

                        match_details = {
                            "fattura_id": str(fattura.get("_id")),
                            "numero_fattura": fattura.get("numero_fattura") or fattura.get("invoice_number"),
                            "fornitore": fattura.get("cedente_denominazione") or fattura.get("supplier_name"),
                            "metodo_pagamento": metodo_pagamento,
                            "match_score": fatture_scored[0][1]
                        }
                        results["riconciliati_fatture"] += 1
                        imp_fatt_match = fattura.get("importo_totale") or fattura.get("total_amount") or 0
                        await _alert_differenza_importo(db, mov_id, importo, float(imp_fatt_match), match_details["fattura_id"])
                    else:
                        # Più fatture con score simile → operazione da confermare
                        fatture_ordinate = sorted(
                            [f for f, s in fatture_scored if s >= 10],
                            key=lambda f: f.get("data", f.get("invoice_date", "1900-01-01")),
                            reverse=True
                        )

                        operazione = {
                            "id": str(uuid.uuid4()),
                            "tipo": "riconciliazione_dubbio",
                            "movimento_ec_id": mov_id,
                            "data": data_ec,
                            "importo": importo,
                            "descrizione": descrizione,
                            "tipo_movimento": tipo,
                            "match_type": "fatture_multiple",
                            "confidence": "medio",
                            "dettagli": {
                                "fatture_candidate": [
                                    {
                                        "id": str(f.get("_id", f.get("id"))),
                                        "numero": f.get("numero_fattura") or f.get("invoice_number"),
                                        "fornitore": f.get("cedente_denominazione") or f.get("supplier_name"),
                                        "importo": f.get("importo_totale") or f.get("total_amount"),
                                        "data": f.get("data") or f.get("invoice_date"),
                                        "score": next((s for ff, s in fatture_scored if ff == f), 0)
                                    }
                                    for f in fatture_ordinate[:10]
                                ],
                                "motivo_dubbio": f"Trovate {len(fatture_ordinate)} fatture con match parziale"
                            },
                            "stato": "da_confermare",
                            "created_at": now
                        }

                        creata = await _crea_operazione_da_confermare_idempotente(db, operazione)
                        results["dubbi"] += 1
                        if creata:
                            await _alert_match_ambiguo(db, mov_id, operazione["dettagli"]["motivo_dubbio"])

                # Se solo importo esatto (score = 10) e UNA sola fattura → riconcilia
                elif fatture_scored and fatture_scored[0][1] == 10:
                    fatture_esatte = [f for f, s in fatture_scored if s == 10]

                    if len(fatture_esatte) == 1:
                        fattura = fatture_esatte[0]
                        match_found = True
                        match_type = "fattura_solo_importo"

                        metodo_pagamento = "Bonifico"
                        if num_assegno:
                            metodo_pagamento = f"Assegno N.{num_assegno}"

                        await _applica_pagamento_banca(
                            db, fattura, metodo_pagamento, data_ec, mov_id,
                            10, now, source="ric_auto_solo_importo",
                        )

                        match_details = {
                            "fattura_id": str(fattura.get("_id")),
                            "numero_fattura": fattura.get("numero_fattura") or fattura.get("invoice_number"),
                            "fornitore": fattura.get("cedente_denominazione") or fattura.get("supplier_name"),
                            "metodo_pagamento": metodo_pagamento,
                            "match_score": 10,
                            "match_type": "solo_importo"
                        }
                        results["riconciliati_fatture"] += 1

                    elif len(fatture_esatte) > 1:
                        # Più fatture solo con importo → operazione da confermare (bassa confidenza)
                        fatture_ordinate = sorted(
                            fatture_esatte,
                            key=lambda f: f.get("data", f.get("invoice_date", "1900-01-01")),
                            reverse=True
                        )

                        operazione = {
                            "id": str(uuid.uuid4()),
                            "tipo": "riconciliazione_dubbio",
                            "movimento_ec_id": mov_id,
                            "data": data_ec,
                            "importo": importo,
                            "descrizione": descrizione,
                            "tipo_movimento": tipo,
                            "match_type": "fatture_multiple",
                            "confidence": "basso",
                            "dettagli": {
                                "fatture_candidate": [
                                    {
                                        "id": str(f.get("_id", f.get("id"))),
                                        "numero": f.get("numero_fattura") or f.get("invoice_number"),
                                        "fornitore": f.get("cedente_denominazione") or f.get("supplier_name"),
                                        "importo": f.get("importo_totale") or f.get("total_amount"),
                                        "data": f.get("data") or f.get("invoice_date")
                                    }
                                    for f in fatture_ordinate[:10]
                                ],
                                "motivo_dubbio": f"Trovate {len(fatture_esatte)} fatture con stesso importo (match solo importo)"
                            },
                            "stato": "da_confermare",
                            "created_at": now
                        }

                        creata = await _crea_operazione_da_confermare_idempotente(db, operazione)
                        results["dubbi"] += 1
                        if creata:
                            await _alert_match_ambiguo(db, mov_id, operazione["dettagli"]["motivo_dubbio"])

            # === 2. CERCA F24 (per USCITE) ===
            if tipo == "uscita" and not match_found and "F24" in descrizione.upper():
                f24 = await db["f24_unificato"].find_one({
                    "totale": {"$gte": importo - 0.05, "$lte": importo + 0.05},
                    "riconciliato": {"$ne": True}
                })

                if f24:
                    match_found = True
                    match_type = "f24"
                    f24_id = str(f24.get("id") or f24.get("_id"))
                    importo_f24 = f24.get("totale") or f24.get("importo_totale") or 0

                    await db["f24_unificato"].update_one(
                        {"_id": f24["_id"]},
                        {"$set": {
                            "riconciliato": True,
                            "pagato": True,
                            "in_banca": True,
                            "data_pagamento": data_ec,
                            "riconciliato_automaticamente": True,
                            "updated_at": now
                        }}
                    )
                    await _propaga_f24_pagato(
                        db, f24_id=f24_id, data_pag=data_ec, movimento_id=mov_id,
                        importo=importo_f24, source="ric_auto_f24",
                    )
                    await _registra_match_partita_aperta(
                        db, tipo="f24", documento_id=f24_id,
                        importo=float(importo_f24 or 0), movimento_id=mov_id, now=now,
                    )

                    match_details = {
                        "f24_id": str(f24.get("_id")),
                        "periodo": f24.get("periodo_riferimento"),
                        "importo_f24": f24.get("totale")
                    }
                    results["riconciliati_f24"] += 1

            # === 3. CERCA POS (per ENTRATE - accrediti) ===
            if tipo == "entrata" and not match_found:
                desc_upper = descrizione.upper()
                if any(kw in desc_upper for kw in ['POS', 'NEXI', 'SUMUP', 'CARTE', 'BANCOMAT']):
                    # Logica POS: Lun-Gio +1g, Ven-Dom → Lunedì
                    try:
                        dt_acc = datetime.strptime(data_ec, "%Y-%m-%d")
                        weekday = dt_acc.weekday()

                        if weekday == 0:  # Lunedì → cerca Ven+Sab+Dom
                            date_weekend = [
                                (dt_acc - timedelta(days=3)).strftime("%Y-%m-%d"),
                                (dt_acc - timedelta(days=2)).strftime("%Y-%m-%d"),
                                (dt_acc - timedelta(days=1)).strftime("%Y-%m-%d"),
                            ]

                            pos_weekend = await db[COLLECTION_PRIMA_NOTA_CASSA].find({
                                "data": {"$in": date_weekend},
                                "categoria": "POS",
                                "riconciliato": {"$ne": True}
                            }, {"_id": 0}).to_list(10)

                            somma_pos = sum(p.get("importo", 0) for p in pos_weekend)

                            if abs(somma_pos - importo) <= 1:
                                match_found = True
                                match_type = "pos_weekend"

                                for p in pos_weekend:
                                    await db[COLLECTION_PRIMA_NOTA_CASSA].update_one(
                                        {"id": p["id"]},
                                        {"$set": {
                                            "riconciliato": True,
                                            "in_banca": True,
                                            "riconciliato_con_ec": mov_id,
                                            "updated_at": now
                                        }}
                                    )

                                match_details = {"date_pos": date_weekend, "importo_totale": somma_pos}
                                results["riconciliati_pos"] += 1
                        else:
                            # Lun-Gio → cerca giorno precedente
                            data_pos = (dt_acc - timedelta(days=1)).strftime("%Y-%m-%d")

                            pos = await db[COLLECTION_PRIMA_NOTA_CASSA].find_one({
                                "data": data_pos,
                                "categoria": "POS",
                                "importo": {"$gte": importo - 1, "$lte": importo + 1},
                                "riconciliato": {"$ne": True}
                            })

                            if pos:
                                match_found = True
                                match_type = "pos_giornaliero"

                                await db[COLLECTION_PRIMA_NOTA_CASSA].update_one(
                                    {"id": pos["id"]},
                                    {"$set": {
                                        "riconciliato": True,
                                        "in_banca": True,
                                        "riconciliato_con_ec": mov_id,
                                        "updated_at": now
                                    }}
                                )

                                match_details = {"data_pos": data_pos, "importo_pos": pos.get("importo")}
                                results["riconciliati_pos"] += 1
                    except Exception:
                        pass

            # === 4. CERCA VERSAMENTI (per ENTRATE) ===
            if tipo == "entrata" and not match_found:
                if any(kw in descrizione.upper() for kw in ['VERS', 'VERSAMENTO', 'CONTANTI']):
                    versamento = await db[COLLECTION_PRIMA_NOTA_CASSA].find_one({
                        "data": data_ec,
                        "categoria": "Versamento Banca",
                        "importo": {"$gte": importo - 0.05, "$lte": importo + 0.05},
                        "riconciliato": {"$ne": True}
                    })

                    if versamento:
                        match_found = True
                        match_type = "versamento"

                        await db[COLLECTION_PRIMA_NOTA_CASSA].update_one(
                            {"id": versamento["id"]},
                            {"$set": {
                                "riconciliato": True,
                                "in_banca": True,
                                "riconciliato_con_ec": mov_id,
                                "updated_at": now
                            }}
                        )

                        # Bug segnalato dall'utente 15/07/2026: il match
                        # marcava riconciliati sia la riga cassa che l'EC, ma
                        # non creava MAI la voce in dare corrispondente in
                        # prima_nota_banca — il versamento risultava uscito
                        # dalla cassa senza mai comparire come entrata in
                        # banca. Idempotente per costruzione: una volta
                        # riconciliato, l'EC esce dalla query di riga 534 e
                        # non viene mai riprocessato.
                        banca_versamento_id = str(uuid.uuid4())
                        await scrivi_movimento(db, "banca", {
                            "id": banca_versamento_id,
                            "data": data_ec,
                            "tipo": "entrata",
                            "importo": versamento.get("importo", importo),
                            "descrizione": f"Versamento contanti in banca - {descrizione[:100]}",
                            "categoria": "Versamento Banca",
                            "estratto_conto_id": mov_id,
                            "prima_nota_cassa_id": versamento["id"],
                            "source": "riconciliazione_ec_versamento",
                            "created_at": now,
                        })

                        match_details = {
                            "versamento_id": versamento.get("id"),
                            "importo": versamento.get("importo"),
                            "prima_nota_banca_id": banca_versamento_id,
                        }
                        results["riconciliati_versamenti"] += 1

            # === AGGIORNA EC ===
            if match_found:
                await db[COLLECTION_ESTRATTO_CONTO].update_one(
                    {"id": mov_id},
                    {"$set": {
                        "riconciliato": True,
                        "riconciliato_automaticamente": True,
                        "tipo_riconciliazione": match_type,
                        "dettagli_riconciliazione": match_details,
                        "updated_at": now
                    }}
                )
            else:
                results["non_trovati"] += 1
                await _alert_non_riconciliato(db, mov_id, importo, descrizione)
                if tipo == "uscita":
                    await _alert_pagamento_multiplo(db, mov_id, importo)

        except Exception as e:
            results["errors"].append({"id": mov.get("id"), "error": str(e)})

    totale_riconciliati = (
        results["riconciliati_fatture"] +
        results["riconciliati_assegni"] +
        results["riconciliati_f24"] +
        results["riconciliati_pos"] +
        results["riconciliati_versamenti"]
    )

    return {
        "success": True,
        "message": f"Riconciliati {totale_riconciliati} movimenti, {results['dubbi']} da confermare",
        "totale_riconciliati": totale_riconciliati,
        **results
    }
