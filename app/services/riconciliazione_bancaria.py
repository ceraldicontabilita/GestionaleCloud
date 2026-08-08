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
4. Una fattura richiede numero esplicito e importo identico al centesimo
5. Il fornitore deve essere coerente; fuzzy/data producono solo proposte

Punto di ingresso unico: `riconcilia_movimenti_banca()`, richiamata dallo
scheduler (ogni 30 min) e da app/routers/bank/estratto_conto.py dopo ogni
upload — stesso pattern operativo già in produzione da mesi con il
"motore A".
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
import uuid
import logging
import re
import itertools

from app.database import Database, Collections
from app.services.payment_invoice_matching import amounts_equal_to_cent
from app.services.prima_nota_integrity import totale_pagabile_al_fornitore
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
COLLECTION_PRIMA_NOTA_BANCA = "prima_nota_banca"
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
                                   now: str, source: str,
                                   importo_pagamento: Optional[float] = None) -> None:
    """Applica il pagamento via banca in modo COERENTE con il resto dell'app:
    crea (idempotente) il movimento in prima_nota_banca, aggiorna TUTTI i flag
    usati dalle varie pagine (pagato/paid/stato_pagamento/prima_nota_*) e
    propaga l'evento FATTURA_PAGATA.

    Prima di questo helper la riconciliazione settava solo pagato/in_banca:
    la fattura risultava pagata ma NON compariva mai in Prima Nota Banca.
    """
    fattura_id = str(fattura.get("id") or fattura.get("_id"))
    importo_fattura = float(fattura.get("total_amount") or fattura.get("importo_totale") or 0)
    quota = round(float(importo_pagamento if importo_pagamento is not None else importo_fattura), 2)
    # Un movimento EC puo' pagare piu' fatture. L'idempotenza deve quindi
    # essere sulla coppia (movimento, fattura), non sul solo movimento:
    # altrimenti la seconda quota sovrascriverebbe la prima riga di banca.
    evidenza_esistente = await db["prima_nota_banca"].find_one({
        "$and": [
            {"$or": [
                {"movimento_estratto_conto_id": mov_id},
                {"estratto_conto_id": mov_id},
            ]},
            {"$or": [
                {"invoice_id": fattura_id},
                {"fattura_id": fattura_id},
            ]},
        ],
        "status": {"$nin": ["deleted", "archived"]},
    }, {"_id": 0}) if mov_id else None
    if not evidenza_esistente and mov_id:
        # Se l'import dell'EC ha già creato la riga generica dell'intero
        # addebito, un match singolo la completa con la fattura. Le quote di un
        # pagamento multi-fattura non coincidono con l'intero EC e restano
        # quindi righe distinte intenzionali.
        evidenza_esistente = await db["prima_nota_banca"].find_one({
            "$and": [
                {"$or": [
                    {"movimento_estratto_conto_id": mov_id},
                    {"estratto_conto_id": mov_id},
                ]},
                {"$or": [
                    {"invoice_id": {"$exists": False}}, {"invoice_id": None},
                ]},
                {"$or": [
                    {"fattura_id": {"$exists": False}}, {"fattura_id": None},
                ]},
            ],
            "source": "estratto_conto_auto",
            "importo": {"$gte": quota - 0.01, "$lte": quota + 0.01},
            "status": {"$nin": ["deleted", "archived"]},
        }, {"_id": 0})
    riga_generica_promossa = bool(
        evidenza_esistente and not (
            evidenza_esistente.get("invoice_id") or evidenza_esistente.get("fattura_id")
        )
    )
    evidenza_gia_applicata = bool(
        evidenza_esistente
        and str(evidenza_esistente.get("invoice_id") or evidenza_esistente.get("fattura_id") or "") == fattura_id
    )
    quota_da_applicare = 0.0 if evidenza_gia_applicata else quota
    gia_pagato = round(float(fattura.get("importo_pagato") or 0), 2)
    nuovo_pagato = round(min(importo_fattura, gia_pagato + quota_da_applicare), 2)
    pagata_interamente = abs(nuovo_pagato - importo_fattura) <= 0.005
    update = {
        "pagato": pagata_interamente,
        "paid": pagata_interamente,
        "stato_pagamento": "pagata" if pagata_interamente else "parziale",
        "payment_status": "paid" if pagata_interamente else "partial",
        "importo_pagato": nuovo_pagato,
        "importo_residuo": round(max(0.0, importo_fattura - nuovo_pagato), 2),
        "metodo_pagamento": metodo_label,
        "in_banca": True,
        "data_pagamento": data_ec,
        "riconciliato_con_ec": mov_id,
        "riconciliato_automaticamente": True,
        "match_score": score,
        "updated_at": now,
    }
    try:
        pn = evidenza_esistente
        pn_fields = {
            "invoice_id": fattura_id, "fattura_id": fattura_id,
            "movimento_estratto_conto_id": mov_id, "estratto_conto_id": mov_id,
            "riconciliato": True, "riconciliazione_automatica": True,
            "match_score": score,
            "data_riconciliazione": data_ec, "updated_at": now,
        }
        if riga_generica_promossa:
            pn_fields.update({
                "importo": quota, "categoria": "Fatture", "source": source,
                "descrizione": f"Pagamento {metodo_label} fattura "
                               f"{fattura.get('invoice_number') or fattura.get('numero_fattura') or ''}".strip(),
            })
        if pn:
            await db["prima_nota_banca"].update_one({"id": pn["id"]}, {"$set": pn_fields})
            pn_id = pn["id"]
        else:
            from app.services.scritture_contabili import scrivi_movimento
            pn_id = await scrivi_movimento(db, "banca", {
                "data": str(data_ec)[:10], "tipo": "uscita", "importo": quota,
                "descrizione": f"Pagamento {metodo_label} fattura "
                               f"{fattura.get('invoice_number') or fattura.get('numero_fattura') or ''}".strip(),
                "categoria": "Fatture", "source": source, **pn_fields,
            })
        update["prima_nota_id"] = pn_id
        update["prima_nota_tipo"] = "banca"
        update["prima_nota_banca_id"] = pn_id
    except Exception:
        logger.exception(f"Errore registrazione prima nota banca per fattura {fattura_id}")

    filtro = {"_id": fattura["_id"]} if fattura.get("_id") is not None else {"id": fattura.get("id")}
    await db[Collections.INVOICES].update_one(filtro, {"$set": update})
    if quota_da_applicare > 0:
        from app.services.scadenze_rate_service import applica_quota_scadenze
        await applica_quota_scadenze(
            db, fattura_id=fattura_id, quota=quota,
            evidenza_id=f"banca:{mov_id}:{fattura_id}", metodo=metodo_label,
            data_pagamento=str(data_ec)[:10],
        )
    if pagata_interamente:
        await _propaga_fattura_pagata(
            db, fattura_id=fattura_id, metodo=metodo_label, data_pag=data_ec,
            movimento_id=mov_id, importo=quota, source=source,
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


def _importo_atteso_per_movimento(fattura: Dict[str, Any], importo_movimento: float) -> float:
    """Totale da usare nel controllo differenze: per una fattura rateizzata
    e' la rata XML compatibile, non il totale documento."""
    for rata in fattura.get("pagamento_rate") or []:
        if not isinstance(rata, dict):
            continue
        valore = float(rata.get("importo") or 0)
        if abs(valore - importo_movimento) <= 0.005:
            return valore
    return float(fattura.get("importo_residuo") or fattura.get("importo_totale")
                 or fattura.get("total_amount") or 0)


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


def _numero_fattura_citato_esplicitamente(numero_fattura: str, descrizione: str) -> bool:
    """Match prudente per i bonifici cumulativi.

    Per ripartire automaticamente un movimento su piu' fatture non basta il
    fuzzy match generico: ogni numero deve essere davvero leggibile nella
    causale. Si confrontano sia la forma compatta sia la variante senza zeri
    iniziali, mantenendo una lunghezza minima per evitare che numeri brevi
    (giorni, anni, ABI/CAB) vengano scambiati per fatture.
    """
    if not numero_fattura or not descrizione:
        return False

    numero = re.sub(
        r'^(?:FT|FAT|FATT|FATTURA|INV|N\.?|NR\.?)\s*',
        '', str(numero_fattura).strip().upper(),
    )
    numero_compatto = re.sub(r'[^A-Z0-9]', '', numero)
    descrizione_compatta = re.sub(r'[^A-Z0-9]', '', str(descrizione).upper())
    if len(numero_compatto) >= 4 and numero_compatto in descrizione_compatta:
        return True

    senza_zeri = numero_compatto.lstrip('0')
    if len(senza_zeri) >= 4 and senza_zeri in descrizione_compatta:
        return True

    # Alcuni fornitori espongono nell'XML un numero composito con serie e
    # anno (es. V1-2026-007590), mentre nel bonifico scrivono esplicitamente
    # soltanto il progressivo finale ("fattura 7590"). E' ammesso solo
    # l'ultimo segmento numerico, con almeno quattro cifre, e soltanto dopo
    # una parola documentale: non e' quindi un fuzzy match su CRO/date.
    segmenti_numerici = re.findall(r'\d+', numero)
    if segmenti_numerici:
        progressivo = segmenti_numerici[-1].lstrip('0')
        if len(progressivo) >= 4:
            pattern_progressivo = (
                r'(?:FATTURA|FATT|FAT|FT|INV|DOCUMENTO|DOC)\s*'
                r'(?:N[.°º]?\s*)?0*' + re.escape(progressivo)
                + r'(?![0-9])'
            )
            if re.search(pattern_progressivo, str(descrizione).upper()):
                return True

    # Numeri corti alfanumerici (es. 25/D) sono ammessi soltanto nella forma
    # originale, delimitata da caratteri non alfanumerici. I numeri di una o
    # due cifre (es. fattura 56) richiedono anche la parola FATTURA/FT/INV:
    # senza quel contesto sarebbero indistinguibili da giorni, mesi o codici.
    if 2 <= len(numero_compatto) < 4:
        parti = [re.escape(p) for p in re.findall(r'[A-Z0-9]+', numero) if p]
        if parti:
            corpo = r'(?<![A-Z0-9])' + r'[\s./_-]*'.join(parti) + r'(?![A-Z0-9])'
            if len(numero_compatto) <= 2:
                pattern = r'(?:FATTURA|FATT|FAT|FT|INV|DOCUMENTO|DOC)\s*(?:N[.°º]?\s*)?' + corpo
            else:
                pattern = corpo
            return re.search(pattern, str(descrizione).upper()) is not None
    return False


def _riferimenti_fattura_dichiarati(descrizione: str) -> List[str]:
    """Estrae l'elenco dichiarato dopo FATTURE/INVOICE in una causale.

    Serve a distinguere una ripartizione completa da una causale che cita
    documenti non ancora importati nel gestionale.
    """
    match = re.search(
        r"\b(?:FATTURE?|FATT|FAT|FT|INVOICES?|INV)\b[\s:.-]*(.+)$",
        str(descrizione or ""), re.IGNORECASE,
    )
    if not match:
        return []
    riferimenti = []
    for token in re.findall(r"[A-Z0-9][A-Z0-9./_-]*", match.group(1).upper()):
        compatto = re.sub(r"[^A-Z0-9]", "", token).lstrip("0")
        if len(compatto) >= 4 and any(ch.isdigit() for ch in compatto):
            riferimenti.append(compatto)
    return list(dict.fromkeys(riferimenti))


def _quota_aperta_fattura(fattura: Dict[str, Any]) -> float:
    """Quota ancora aperta da usare nella ripartizione del bonifico."""
    totale = totale_pagabile_al_fornitore(fattura)
    if fattura.get("importo_residuo") is not None:
        return round(max(0.0, float(fattura.get("importo_residuo") or 0)), 2)
    return round(max(0.0, totale - float(fattura.get("importo_pagato") or 0)), 2)


def _chiave_fornitore_fattura(fattura: Dict[str, Any]) -> str:
    """Identita' stabile del fornitore per evitare ripartizioni cross-fornitore."""
    piva = (
        fattura.get("supplier_vat") or fattura.get("cedente_piva")
        or fattura.get("fornitore_piva") or ""
    )
    if piva:
        return "PIVA:" + re.sub(r'\W', '', str(piva).upper())
    nome = (
        fattura.get("cedente_denominazione") or fattura.get("supplier_name")
        or fattura.get("fornitore_ragione_sociale") or ""
    )
    nome_norm = re.sub(r'\W', '', str(nome).upper())
    return "NOME:" + nome_norm if nome_norm else ""


def _evidenza_forte_fattura_banca(
    fattura: Dict[str, Any], descrizione: str, importo_movimento: float
) -> Dict[str, bool]:
    """Regola canonica per l'auto-match fattura/banca.

    Il solo importo, anche unico e con data plausibile, non prova il pagamento.
    Servono importo al centesimo e le due identita' leggibili nella causale:
    fornitore e numero fattura. Questa regola impedisce che due fatture dello
    stesso importo (es. TIMAS e Carta & Party) vengano scambiate. Per le
    fatture rateizzate e' ammesso
    l'importo esatto della rata XML o del residuo ancora aperto.
    """
    totale = totale_pagabile_al_fornitore(fattura)
    residuo = float(
        fattura.get("importo_residuo")
        if fattura.get("importo_residuo") is not None
        else max(0.0, totale - float(fattura.get("importo_pagato") or 0))
    )
    rate = [
        float(rata.get("importo") or 0)
        for rata in fattura.get("pagamento_rate") or []
        if isinstance(rata, dict)
    ]
    importo_esatto = any(
        valore > 0 and amounts_equal_to_cent(valore, importo_movimento)
        for valore in [totale, residuo, *rate]
    )
    fornitore = (
        fattura.get("cedente_denominazione")
        or fattura.get("fornitore_ragione_sociale")
        or fattura.get("supplier_name")
        or ""
    )
    numero = (
        fattura.get("numero_fattura")
        or fattura.get("numero_documento")
        or fattura.get("invoice_number")
        or ""
    )
    fornitore_presente = match_fornitore_descrizione(fornitore, descrizione) > 0
    # Il matcher esplicito evita che numeri brevi, date, CRO o ABI/CAB siano
    # interpretati come numero fattura.
    numero_presente = _numero_fattura_citato_esplicitamente(numero, descrizione)
    numero_assegno_banca = extract_assegno_number(descrizione)
    metodo_fattura = str(
        fattura.get("metodo_pagamento")
        or fattura.get("metodo_pagamento_effettivo") or ""
    )
    numero_assegno_fattura = extract_assegno_number(metodo_fattura)
    assegno_identico = bool(
        numero_assegno_banca and numero_assegno_fattura
        and numero_assegno_banca == numero_assegno_fattura
    )
    return {
        "importo_esatto": importo_esatto,
        "fornitore_presente": fornitore_presente,
        "numero_presente": numero_presente,
        "assegno_identico": assegno_identico,
        "auto_ammesso": importo_esatto and (
            (fornitore_presente and numero_presente) or assegno_identico
        ),
    }


def _evidenza_sdd_fattura_banca(
    fattura: Dict[str, Any], descrizione: str, importo_movimento: float,
    data_movimento: str,
) -> Dict[str, Any]:
    """Evidenza forte alternativa per domiciliazioni SDD.

    Una causale SDD normalmente non contiene il numero fattura. In quel caso
    il mandato/creditore bancario, il fornitore leggibile, l'importo al
    centesimo e una fattura antecedente entro 62 giorni formano la prova. I
    collettori PayPal/Nexi/NUMIA sono esclusi: richiedono i propri statement.
    """
    testo = str(descrizione or "")
    testo_upper = testo.upper()
    sdd = "SDD" in testo_upper
    collettore = any(nome in testo_upper for nome in ("PAYPAL", "NEXI", "NUMIA"))
    totale = _quota_aperta_fattura(fattura)
    importo_esatto = totale > 0 and amounts_equal_to_cent(totale, importo_movimento)
    fornitore = (
        fattura.get("cedente_denominazione")
        or fattura.get("fornitore_ragione_sociale")
        or fattura.get("supplier_name") or ""
    )
    fornitore_presente = match_fornitore_descrizione(fornitore, testo) > 0
    if not fornitore_presente:
        # I creditori SDD usano spesso il marchio breve ("Eni Spa") mentre
        # la fattura contiene la ragione sociale completa ("Eni Plenitude
        # S.p.A."). Il primo token aziendale, delimitato come parola, e'
        # comunque identita' del creditore; importo e finestra temporale
        # restano obbligatori.
        token_fornitore = next((
            token for token in re.findall(r"[A-Z0-9]+", str(fornitore).upper())
            if len(token) >= 3 and token not in {"SRL", "SPA", "SNC", "SAS"}
        ), "")
        fornitore_presente = bool(
            token_fornitore
            and re.search(rf"(?<![A-Z0-9]){re.escape(token_fornitore)}(?![A-Z0-9])", testo_upper)
        )
    data_fattura = fattura.get("data") or fattura.get("invoice_date") or ""
    giorni = _giorni_pagamento_plausibili(data_movimento, data_fattura)
    data_coerente = giorni is not None and 0 <= giorni <= 62
    return {
        "sdd": sdd,
        "collettore_escluso": collettore,
        "importo_esatto": importo_esatto,
        "fornitore_presente": fornitore_presente,
        "giorni_da_fattura": giorni,
        "auto_ammesso": bool(
            sdd and not collettore and importo_esatto
            and fornitore_presente and data_coerente
        ),
    }


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


async def riconcilia_movimenti_banca(
    movimento_ids: Optional[List[str]] = None,
    data_dal: Optional[str] = None,
) -> Dict[str, Any]:
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
        "riconciliati_movimenti_multi_fattura": 0,
        "fatture_ripartite_multi": 0,
        "commissioni_ignorate": 0,
        "dubbi": 0,
        "non_trovati": 0,
        "errors": []
    }

    # Gli assegni hanno un ciclo proprio (compilazione -> XML -> estratto
    # conto) e devono essere risolti prima dei match bancari generici. Questo
    # rende equivalenti tutti gli ordini di arrivo delle tre fonti e impedisce
    # che il movimento venga consumato da un secondo motore senza aggiornare
    # l'assegno. La funzione e' idempotente sugli ID EC/assegno.
    try:
        from app.services.assegni_estratto_conto import (
            sincronizza_assegni_da_estratto_conto,
        )
        esito_assegni = await sincronizza_assegni_da_estratto_conto(
            db, movimento_ids=movimento_ids, data_dal=data_dal,
        )
        results["assegni_sincronizzati"] = esito_assegni
        results["riconciliati_assegni"] = esito_assegni.get("assegni_riconciliati", 0)
        results["riconciliati_fatture"] += esito_assegni.get("fatture_associate", 0)
        results["errors"].extend(esito_assegni.get("errori", []))
    except Exception as exc:
        # Un'anomalia circoscritta agli assegni non deve impedire a POS, F24,
        # bonifici e SDD di essere processati nello stesso estratto conto.
        results["errors"].append(f"Sincronizzazione assegni: {exc}")

    # Carica movimenti EC non riconciliati. Dopo un import il chiamante passa
    # gli ID appena inseriti/promossi: riesaminare ogni volta l'intero storico
    # (fino a 5.000 righe) moltiplicava le query su fatture, F24, POS e cassa e
    # poteva bloccare la coda Drive per minuti. Lo scheduler continua invece a
    # chiamare senza filtro ed esegue la riconciliazione generale periodica.
    from app.services.bank_evidence import filtro_solo_evidenza_ufficiale
    filtri_movimenti = [
        {"riconciliato": {"$ne": True}},
        filtro_solo_evidenza_ufficiale(),
    ]
    ids_richiesti = list(dict.fromkeys(
        str(movimento_id).strip()
        for movimento_id in (movimento_ids or [])
        if str(movimento_id).strip()
    ))
    if movimento_ids is not None:
        if not ids_richiesti:
            results["ambito"] = "nuovi_movimenti"
            return results
        filtri_movimenti.append({"id": {"$in": ids_richiesti}})
        results["ambito"] = "nuovi_movimenti"
    else:
        results["ambito"] = "completo"
    if data_dal:
        filtri_movimenti.append({"data": {"$gte": str(data_dal)}})
        results["data_dal"] = str(data_dal)

    movimenti_ec = await db[COLLECTION_ESTRATTO_CONTO].find(
        {"$and": filtri_movimenti},
        {"_id": 0},
    ).to_list(5000)
    # Ordine cronologico deterministico senza dipendere dal metodo ``sort``
    # del cursore: mantiene compatibilita' con adapter/test minimali e con
    # import legacy che restituiscono gia' una lista materializzata.
    movimenti_ec.sort(key=lambda movimento: str(movimento.get("data") or ""))

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
            blocca_match_singolo = False

            # === 0. PAGAMENTO CUMULATIVO CON PIU' NUMERI FATTURA ===
            # Un bonifico puo' riportare in causale l'elenco delle fatture
            # saldate. In quel caso la prova forte non e' il totale della
            # singola fattura, ma: numeri espliciti + stesso fornitore + somma
            # dei residui uguale al movimento. Ogni fattura riceve la propria
            # quota e la propria riga in Prima Nota Banca, tutte collegate allo
            # stesso movimento EC.
            riferimenti_potenziali = set(re.findall(
                r'(?<![A-Z0-9])[A-Z0-9]*\d[A-Z0-9./_-]{2,}(?![A-Z0-9])',
                str(descrizione).upper(),
            ))
            riferimenti_strutturati = {
                riferimento for riferimento in riferimenti_potenziali
                if "/" in riferimento or "-" in riferimento
            }
            causale_indica_fatture = bool(
                re.search(r'\b(?:FATTURA|FATTURE|FATT|FAT|FT|INVOICE|INV)\b',
                          str(descrizione), re.IGNORECASE)
                # Senza una parola esplicita, due riferimenti devono almeno
                # avere la forma tipica di un documento (es. 1855/01): evita
                # di scansire come fatture CRO, ABI/CAB, date e altri numeri.
                or len(riferimenti_strutturati) >= 2
            )
            if tipo == "uscita" and causale_indica_fatture:
                riferimenti_dichiarati = _riferimenti_fattura_dichiarati(descrizione)
                fatture_aperte = await db[Collections.INVOICES].find({
                    "pagato": {"$ne": True},
                    "stato_pagamento": {"$nin": ["pagata", "paid", "sospesa"]},
                }, {
                    "id": 1, "invoice_number": 1, "numero_fattura": 1,
                    "numero_documento": 1, "supplier_vat": 1,
                    "cedente_piva": 1, "fornitore_piva": 1,
                    "supplier_name": 1, "cedente_denominazione": 1,
                    "fornitore_ragione_sociale": 1,
                    "total_amount": 1, "importo_totale": 1,
                    "importo_pagato": 1, "importo_residuo": 1,
                    "invoice_date": 1, "data": 1,
                }).to_list(5000)

                riferimenti_presenti = set()
                if riferimenti_dichiarati:
                    tutte_le_fatture_citate = await db[Collections.INVOICES].find(
                        {}, {"_id": 0, "invoice_number": 1,
                             "numero_fattura": 1, "numero_documento": 1},
                    ).to_list(5000)
                    for fattura in tutte_le_fatture_citate:
                        numero = (
                            fattura.get("invoice_number")
                            or fattura.get("numero_fattura")
                            or fattura.get("numero_documento") or ""
                        )
                        if _numero_fattura_citato_esplicitamente(numero, descrizione):
                            riferimenti_presenti.add(
                                re.sub(r"[^A-Z0-9]", "", str(numero).upper()).lstrip("0")
                            )

                fatture_esplicite = []
                ids_espliciti = set()
                for fattura in fatture_aperte:
                    numero = (
                        fattura.get("invoice_number") or fattura.get("numero_fattura")
                        or fattura.get("numero_documento") or ""
                    )
                    quota = _quota_aperta_fattura(fattura)
                    fattura_id = str(fattura.get("id") or fattura.get("_id"))
                    if (
                        quota > 0
                        and fattura_id not in ids_espliciti
                        and _numero_fattura_citato_esplicitamente(numero, descrizione)
                    ):
                        ids_espliciti.add(fattura_id)
                        fatture_esplicite.append((fattura, quota))

                if len(fatture_esplicite) >= 2:
                    riferimenti_trovati = {
                        re.sub(
                            r"[^A-Z0-9]", "", str(
                                fattura.get("invoice_number")
                                or fattura.get("numero_fattura")
                                or fattura.get("numero_documento") or ""
                            ).upper(),
                        ).lstrip("0")
                        for fattura, _ in fatture_esplicite
                    }
                    riferimenti_mancanti = [
                        riferimento for riferimento in riferimenti_dichiarati
                        if riferimento not in riferimenti_presenti
                    ]
                    riferimenti_gia_chiusi = [
                        riferimento for riferimento in riferimenti_dichiarati
                        if riferimento in riferimenti_presenti
                        and riferimento not in riferimenti_trovati
                    ]
                    totale_quote = round(sum(quota for _, quota in fatture_esplicite), 2)
                    chiavi_fornitore = {
                        chiave for chiave in (
                            _chiave_fornitore_fattura(fattura)
                            for fattura, _ in fatture_esplicite
                        ) if chiave
                    }
                    stesso_fornitore = len(chiavi_fornitore) <= 1
                    somma_esatta = amounts_equal_to_cent(totale_quote, importo)
                    fornitore_documento = (
                        fatture_esplicite[0][0].get("cedente_denominazione")
                        or fatture_esplicite[0][0].get("supplier_name")
                        or fatture_esplicite[0][0].get("fornitore_ragione_sociale")
                        or ""
                    )
                    fornitore_presente = (
                        match_fornitore_descrizione(fornitore_documento, descrizione) > 0
                    )

                    dettagli_fatture = [{
                        "fattura_id": str(fattura.get("id") or fattura.get("_id")),
                        "numero_fattura": (
                            fattura.get("invoice_number") or fattura.get("numero_fattura")
                            or fattura.get("numero_documento")
                        ),
                        "fornitore": (
                            fattura.get("cedente_denominazione") or fattura.get("supplier_name")
                            or fattura.get("fornitore_ragione_sociale")
                        ),
                        "quota": quota,
                    } for fattura, quota in fatture_esplicite]

                    elenco_completo = not riferimenti_mancanti and not riferimenti_gia_chiusi
                    if somma_esatta and stesso_fornitore and fornitore_presente and elenco_completo:
                        metodo_pagamento = "Bonifico"
                        num_assegno_multi = extract_assegno_number(descrizione)
                        if num_assegno_multi:
                            metodo_pagamento = f"Assegno N.{num_assegno_multi}"

                        for fattura, quota in fatture_esplicite:
                            await _applica_pagamento_banca(
                                db, fattura, metodo_pagamento, data_ec, mov_id,
                                20, now, source="ric_auto_multi_fattura_causale",
                                importo_pagamento=quota,
                            )

                        match_found = True
                        match_type = "fatture_multiple_causale"
                        match_details = {
                            "metodo_pagamento": metodo_pagamento,
                            "importo_movimento": importo,
                            "importo_ripartito": totale_quote,
                            "numero_fatture": len(dettagli_fatture),
                            "fatture": dettagli_fatture,
                            "riferimenti_dichiarati": riferimenti_dichiarati,
                            "match_type": "numeri_fattura+somma_residui+fornitore",
                        }
                        results["riconciliati_fatture"] += 1
                        results["riconciliati_movimenti_multi_fattura"] += 1
                        results["fatture_ripartite_multi"] += len(dettagli_fatture)
                    else:
                        # I numeri sono leggibili ma la somma non quadra o i
                        # documenti appartengono a fornitori diversi: non si
                        # inventano quote. Si blocca il match singolo e si crea
                        # una sola proposta idempotente da confermare.
                        blocca_match_singolo = True
                        motivo = (
                            f"Causale con {len(dettagli_fatture)} fatture esplicite; "
                            f"movimento €{importo:.2f}, somma residui €{totale_quote:.2f}, "
                            f"stesso fornitore: {'si' if stesso_fornitore else 'no'}, "
                            f"fornitore presente: {'si' if fornitore_presente else 'no'}, "
                            f"riferimenti mancanti: {len(riferimenti_mancanti)}, "
                            f"gia chiusi/non aperti: {len(riferimenti_gia_chiusi)}"
                        )
                        operazione = {
                            "id": str(uuid.uuid4()),
                            "tipo": "riconciliazione_dubbio",
                            "movimento_ec_id": mov_id,
                            "data": data_ec,
                            "importo": importo,
                            "descrizione": descrizione,
                            "tipo_movimento": tipo,
                            "match_type": "fatture_multiple_causale",
                            "confidence": "alto",
                            "dettagli": {
                                "fatture_candidate": dettagli_fatture,
                                "importo_movimento": importo,
                                "somma_residui": totale_quote,
                                "differenza": round(importo - totale_quote, 2),
                                "stesso_fornitore": stesso_fornitore,
                                "fornitore_presente": fornitore_presente,
                                "riferimenti_dichiarati": riferimenti_dichiarati,
                                "riferimenti_mancanti": riferimenti_mancanti,
                                "riferimenti_gia_chiusi": riferimenti_gia_chiusi,
                                "motivo_dubbio": motivo,
                            },
                            "stato": "da_confermare",
                            "created_at": now,
                        }
                        creata = await _crea_operazione_da_confermare_idempotente(db, operazione)
                        results["dubbi"] += 1
                        if creata:
                            await _alert_match_ambiguo(db, mov_id, motivo)

            # === 1. CERCA FATTURE (per USCITE) ===
            if tipo == "uscita" and not match_found and not blocca_match_singolo:
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
                            {"importo_totale": {"$gte": importo - 0.01, "$lte": importo + 0.01}},
                            {"total_amount": {"$gte": importo - 0.01, "$lte": importo + 0.01}},
                            # Match parziale (il pagamento è circa 50-200% della fattura)
                            {"importo_totale": {"$gte": importo * 0.5, "$lte": importo * 2}},
                            {"total_amount": {"$gte": importo * 0.5, "$lte": importo * 2}},
                            {"pagamento_rate": {"$exists": True, "$ne": []}}
                        ]}
                    ]
                    # NB: niente proiezione {"_id": 0} — l'_id serve per l'update
                    # (prima ogni match falliva con KeyError '_id' e finiva in errors)
                }).to_list(500)

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
                    rate = [
                        float(r.get("importo") or 0)
                        for r in f.get("pagamento_rate") or [] if isinstance(r, dict)
                    ]
                    rata_esatta = any(abs(rata - importo) <= 0.005 for rata in rate)
                    residuo = float(
                        f.get("importo_residuo")
                        if f.get("importo_residuo") is not None
                        else max(0, float(imp_fatt) - float(f.get("importo_pagato") or 0))
                    )
                    if abs(residuo - importo) <= 0.01:
                        score += 10  # Match esatto
                    elif rata_esatta and importo <= residuo + 0.005:
                        score += 10  # Importo esatto di una rata del piano XML
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

                # Filtro duro: il solo importo/data non prova un pagamento.
                # L'auto-match richiede importo esatto al centesimo e almeno
                # un'identita' leggibile nella causale (fornitore o numero).
                evidenze_fatture = {}
                filtrate = []
                for fattura, score in fatture_scored:
                    fid = str(fattura.get("id") or fattura.get("_id"))
                    forte = _evidenza_forte_fattura_banca(
                        fattura, descrizione, importo
                    )
                    sdd = _evidenza_sdd_fattura_banca(
                        fattura, descrizione, importo, data_ec
                    )
                    evidenze_fatture[fid] = {"forte": forte, "sdd": sdd}
                    if forte["auto_ammesso"] or sdd["auto_ammesso"]:
                        filtrate.append((fattura, score))
                fatture_scored = filtrate

                # Per canoni/utenze ricorrenti dello stesso importo, abbina la
                # fattura antecedente piu' vicina. Se due candidate hanno la
                # stessa distanza il caso resta ambiguo.
                if len(fatture_scored) > 1 and "SDD" in descrizione.upper():
                    per_distanza = []
                    for fattura, score in fatture_scored:
                        fid = str(fattura.get("id") or fattura.get("_id"))
                        giorni = evidenze_fatture[fid]["sdd"].get("giorni_da_fattura")
                        if giorni is not None:
                            per_distanza.append((giorni, fattura, score))
                    per_distanza.sort(key=lambda item: item[0])
                    if per_distanza and (
                        len(per_distanza) == 1
                        or per_distanza[0][0] < per_distanza[1][0]
                    ):
                        fatture_scored = [(per_distanza[0][1], per_distanza[0][2])]

                # Una sola candidata con importo+identita' e' un match sicuro.
                if len(fatture_scored) == 1 and fatture_scored[0][1] >= 10:
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
                                "fattura_id": str(fattura.get("id") or fattura.get("_id")),
                                "fornitore": fattura.get("cedente_denominazione") or fattura.get("supplier_name"),
                                "stato": "incassato",
                                "updated_at": now
                            }},
                            upsert=True
                        )
                        results["riconciliati_assegni"] += 1

                    await _applica_pagamento_banca(
                        db, fattura, metodo_pagamento, data_ec, mov_id,
                        fatture_scored[0][1], now, source="ric_auto_identita_unica",
                        importo_pagamento=importo,
                    )

                    match_details = {
                        "fattura_id": str(fattura.get("id") or fattura.get("_id")),
                        "numero_fattura": fattura.get("numero_fattura") or fattura.get("invoice_number"),
                        "fornitore": fattura.get("cedente_denominazione") or fattura.get("supplier_name"),
                        "metodo_pagamento": metodo_pagamento,
                        "match_score": fatture_scored[0][1],
                        "match_type": (
                            "sdd+fornitore+importo+data"
                            if "SDD" in descrizione.upper()
                            else "importo+fornitore+numero"
                        )
                    }
                    results["riconciliati_fatture"] += 1
                    imp_fatt_match = _importo_atteso_per_movimento(fattura, importo)
                    await _alert_differenza_importo(db, mov_id, importo, float(imp_fatt_match), match_details["fattura_id"])

                # Piu' fatture con identita' compatibile: la scelta resta
                # sempre da confermare da un operatore.
                elif len(fatture_scored) > 1:
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
                            importo_pagamento=importo,
                        )

                        match_details = {
                            "fattura_id": str(fattura.get("_id")),
                            "numero_fattura": fattura.get("numero_fattura") or fattura.get("invoice_number"),
                            "fornitore": fattura.get("cedente_denominazione") or fattura.get("supplier_name"),
                            "metodo_pagamento": metodo_pagamento,
                            "match_score": fatture_scored[0][1]
                        }
                        results["riconciliati_fatture"] += 1
                        imp_fatt_match = _importo_atteso_per_movimento(fattura, importo)
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
                # NUMIA accredita separatamente bancomat, carte e Amex. La
                # riconciliazione certa e' la somma delle componenti con il
                # trasferimento POS del giorno di vendita, non la conferma
                # manuale di ogni singola riga.
                from app.services.pos_evidence import _e_accredito_pos_numia_con_giorno
                if _e_accredito_pos_numia_con_giorno(descrizione):
                    from app.services.scritture_contabili import riconcilia_accredito_pos_ec
                    gestito = await riconcilia_accredito_pos_ec(db, mov)
                    if gestito:
                        aggiornato = await db[COLLECTION_ESTRATTO_CONTO].find_one(
                            {"id": mov_id}, {"_id": 0, "riconciliato": 1}
                        )
                        if (aggiornato or {}).get("riconciliato") is True:
                            results["riconciliati_pos"] += 1
                        # Se il gruppo e' ancora parziale resta aperto, ma e'
                        # gia' classificato e non deve produrre un alert o una
                        # richiesta di conferma generica.
                        continue
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
                        banca_attesa = await db[COLLECTION_PRIMA_NOTA_BANCA].find_one({
                            "$or": [
                                {"prima_nota_cassa_id": versamento["id"]},
                                {"trasferimento_collegato_id": versamento["id"]},
                            ],
                            "status": {"$nin": ["deleted", "archived"]},
                        })
                        if banca_attesa:
                            banca_versamento_id = banca_attesa["id"]
                            await db[COLLECTION_PRIMA_NOTA_BANCA].update_one(
                                {"id": banca_versamento_id},
                                {"$set": {
                                    "data": data_ec,
                                    "estratto_conto_id": mov_id,
                                    "riconciliato": True,
                                    "provvisorio": False,
                                    "stato": "riconciliato",
                                    "source": "riconciliazione_ec_versamento",
                                    "updated_at": now,
                                }},
                            )
                        else:
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
                                "riconciliato": True,
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
            elif not blocca_match_singolo:
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
