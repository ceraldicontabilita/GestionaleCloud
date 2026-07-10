"""
Trattenute Verbali — Gestionale Ceraldi Group
==============================================
Ciclo di vita della trattenuta in busta paga generata da un verbale
(multa) pagato dalla società al posto del dipendente.

Stati:
    proposta → confermata → comunicata_consulente → in_attesa_cedolino
        → recuperata_in_busta | non_trovata_nel_cedolino | esclusa | da_verificare

Il modulo contiene:
- funzioni PURE (testabili senza DB): calcolo mese successivo,
  validazione formato mese, matching voci trattenuta nel cedolino,
  estrazione testo ricercabile da un documento cedolino;
- helper asincroni per costruire i campi standard della trattenuta e
  per la verifica al momento dell'import del cedolino.
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

COLL_TRATTENUTE = "trattenute_dipendenti"

# ── Stati del ciclo di vita ─────────────────────────────────────────────
STATO_PROPOSTA = "proposta"
STATO_CONFERMATA = "confermata"
STATO_COMUNICATA = "comunicata_consulente"
STATO_IN_ATTESA = "in_attesa_cedolino"
STATO_RECUPERATA = "recuperata_in_busta"
STATO_NON_TROVATA = "non_trovata_nel_cedolino"
STATO_ESCLUSA = "esclusa"
STATO_DA_VERIFICARE = "da_verificare"

# Stato legacy dei record già in produzione (pipeline pre-ciclo di vita):
# equivale a "proposta" — senza questo alias le trattenute esistenti
# sparirebbero dal cruscotto e non sarebbero confermabili.
STATO_LEGACY_DA_APPLICARE = "da_applicare"

# La conferma (sempre dell'utente) parte solo da questi stati
STATI_CONFERMABILI = (STATO_PROPOSTA, STATO_DA_VERIFICARE, STATO_LEGACY_DA_APPLICARE)
# Stati in cui si aspetta il riscontro nel cedolino (percorso on-import)
STATI_ATTESA_VERIFICA = (STATO_COMUNICATA, STATO_IN_ATTESA)
# Stati ripescati dalla verifica retroattiva sui cedolini già archiviati
STATI_VERIFICA_RETRO = (STATO_CONFERMATA, STATO_COMUNICATA, STATO_IN_ATTESA)
# Stati terminali: non escludibili / non modificabili
STATI_TERMINALI = (STATO_RECUPERATA, STATO_ESCLUSA)

NOTA_CONSULENTE_DEFAULT = (
    "Verbale pagato dalla società. Importo da recuperare in busta paga "
    "tramite trattenuta."
)

# Parole cercate (case-insensitive) nel testo/voci del cedolino per
# riconoscere la trattenuta applicata dal consulente (da specifica utente).
PAROLE_VOCE_TRATTENUTA: List[str] = [
    "trattenuta verbale",
    "multa",
    "recupero verbale",
    "trattenuta dipendente",
    "addebito auto",
]

# Chiavi da NON scandire quando si estrae il testo del cedolino
# (contenuti binari/base64: una sequenza base64 può contenere per caso
# parole come "multa" e generare falsi positivi).
_CHIAVI_BINARIE = ("pdf_data", "pdf_bytes", "base64", "quietanza_pdf", "content")

_RE_MESE_YYYY_MM = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


# ============================================================
# FUNZIONI PURE
# ============================================================

def valida_mese_cedolino(valore: Any) -> bool:
    """True se il valore è un mese in formato 'YYYY-MM' valido."""
    return bool(isinstance(valore, str) and _RE_MESE_YYYY_MM.match(valore.strip()))


def periodo_yyyymm(mese: Any, anno: Any) -> Optional[str]:
    """Converte mese/anno numerici in 'YYYY-MM'. None se non validi."""
    try:
        m = int(mese)
        a = int(anno)
    except (TypeError, ValueError):
        return None
    if not (1 <= m <= 12) or not (1900 <= a <= 2200):
        return None
    return f"{a:04d}-{m:02d}"


def mese_successivo(data_pagamento: Any) -> Optional[str]:
    """
    Mese cedolino suggerito = mese SUCCESSIVO al pagamento della società,
    formato 'YYYY-MM'. Accetta date ISO ('2026-01-15', '2026-01-15T10:00:00Z')
    o oggetti datetime/date. None se la data non è interpretabile.
    """
    dt: Optional[datetime] = None
    if isinstance(data_pagamento, datetime):
        dt = data_pagamento
    elif hasattr(data_pagamento, "year") and hasattr(data_pagamento, "month"):
        # datetime.date
        return periodo_yyyymm(
            1 if data_pagamento.month == 12 else data_pagamento.month + 1,
            data_pagamento.year + 1 if data_pagamento.month == 12 else data_pagamento.year,
        )
    elif isinstance(data_pagamento, str) and data_pagamento.strip():
        raw = data_pagamento.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            # fallback: prova a leggere solo YYYY-MM dall'inizio stringa
            m = re.match(r"^(\d{4})-(\d{2})", raw)
            if m:
                return periodo_yyyymm(
                    1 if int(m.group(2)) == 12 else int(m.group(2)) + 1,
                    int(m.group(1)) + 1 if int(m.group(2)) == 12 else int(m.group(1)),
                )
            return None
    if dt is None:
        return None
    if dt.month == 12:
        return periodo_yyyymm(1, dt.year + 1)
    return periodo_yyyymm(dt.month + 1, dt.year)


def trova_voce_trattenuta(testo: Any) -> Optional[str]:
    """
    Cerca nel testo del cedolino le parole che indicano la trattenuta
    applicata. Ritorna la prima parola trovata (per audit) o None.
    Case-insensitive; gli spazi multipli/newline vengono normalizzati.
    """
    if not testo or not isinstance(testo, str):
        return None
    normalizzato = re.sub(r"\s+", " ", testo).lower()
    for parola in PAROLE_VOCE_TRATTENUTA:
        if parola in normalizzato:
            return parola
    return None


def estrai_testo_cedolino(doc: Any, _profondita: int = 0) -> str:
    """
    Concatena i valori testuali di un documento cedolino (dict) in un'unica
    stringa ricercabile, incluse eventuali liste di voci annidate.
    Salta le chiavi con contenuto binario/base64 (vedi _CHIAVI_BINARIE).
    """
    if _profondita > 4 or doc is None:
        return ""
    if isinstance(doc, str):
        return doc
    parti: List[str] = []
    if isinstance(doc, dict):
        for chiave, valore in doc.items():
            k = str(chiave).lower()
            if any(bin_k in k for bin_k in _CHIAVI_BINARIE):
                continue
            testo = estrai_testo_cedolino(valore, _profondita + 1)
            if testo:
                parti.append(testo)
    elif isinstance(doc, (list, tuple)):
        for item in doc:
            testo = estrai_testo_cedolino(item, _profondita + 1)
            if testo:
                parti.append(testo)
    return " ".join(parti)


def periodo_cedolino(doc: Any) -> Optional[str]:
    """Periodo 'YYYY-MM' di un documento cedolino dai campi mese/anno."""
    if not isinstance(doc, dict):
        return None
    return periodo_yyyymm(doc.get("mese"), doc.get("anno"))


def cedolini_candidati(
    cedolini: List[Dict[str, Any]], periodo_min: Optional[str]
) -> List[Dict[str, Any]]:
    """
    Seleziona i cedolini candidati per la verifica retroattiva di una
    trattenuta attesa dal mese `periodo_min` ('YYYY-MM'):
    - periodo cedolino >= periodo_min (il recupero può avvenire anche
      in un mese successivo a quello suggerito);
    - se periodo_min non è ricostruibile → tutti i cedolini;
    - i cedolini senza mese/anno leggibili restano inclusi (best-effort:
      possono comunque contenere la voce di trattenuta) ma in coda.
    Ordinati per periodo crescente (prima il mese atteso), pure function.
    """
    if not cedolini:
        return []
    candidati = []
    for doc in cedolini:
        periodo = periodo_cedolino(doc)
        if periodo_min and periodo and periodo < periodo_min:
            continue  # cedolino precedente al mese atteso: non rilevante
        candidati.append(doc)
    # Il confronto lessicografico su 'YYYY-MM' equivale a quello cronologico;
    # i cedolini senza periodo finiscono in coda.
    return sorted(candidati, key=lambda d: (periodo_cedolino(d) is None,
                                            periodo_cedolino(d) or ""))


# ============================================================
# COSTRUZIONE RECORD TRATTENUTA (usata dai punti di creazione)
# ============================================================

async def dati_dipendente_per_trattenuta(
    db,
    driver_id: Optional[str] = None,
    codice_fiscale: Optional[str] = None,
    nome_fallback: str = "",
) -> Dict[str, Any]:
    """
    Recupera nome, codice fiscale e matricola del dipendente (se disponibili)
    dalle collection employees / dipendenti. Best-effort: mai eccezioni.
    """
    out = {
        "dipendente": nome_fallback or "",
        "codice_fiscale": (codice_fiscale or "").upper(),
        "matricola": None,
    }
    try:
        if driver_id:
            emp = await db["employees"].find_one(
                {"id": driver_id},
                {"_id": 0, "nome": 1, "cognome": 1, "codice_fiscale": 1, "matricola": 1},
            )
            if emp:
                nome = f"{emp.get('nome', '')} {emp.get('cognome', '')}".strip()
                if nome:
                    out["dipendente"] = nome
                if emp.get("codice_fiscale"):
                    out["codice_fiscale"] = str(emp["codice_fiscale"]).upper()
                if emp.get("matricola"):
                    out["matricola"] = emp["matricola"]
        # La matricola di norma vive nell'anagrafica 'dipendenti' (canale cedolini)
        if not out["matricola"] and out["codice_fiscale"]:
            dip = await db["dipendenti"].find_one(
                {"codice_fiscale": out["codice_fiscale"]},
                {"_id": 0, "matricola": 1, "nome_completo": 1},
            )
            if dip:
                if dip.get("matricola"):
                    out["matricola"] = dip["matricola"]
                if not out["dipendente"] and dip.get("nome_completo"):
                    out["dipendente"] = dip["nome_completo"]
    except Exception:
        logger.exception("Errore lookup dipendente per trattenuta verbale")
    return out


async def costruisci_trattenuta_da_verbale(
    db,
    verbale: Dict[str, Any],
    data_pagamento: Optional[str],
    importo_pagato: float,
    fonte: str = "verbale_pagato",
) -> Dict[str, Any]:
    """
    Costruisce il record completo della PROPOSTA di trattenuta a partire
    dal verbale pagato dalla società. Non scrive su DB.
    """
    dip = await dati_dipendente_per_trattenuta(
        db,
        driver_id=verbale.get("driver_id"),
        codice_fiscale=verbale.get("driver_cf"),
        nome_fallback=verbale.get("driver", ""),
    )
    importo_verbale = float(verbale.get("importo", 0) or 0)
    importo_pagato = float(importo_pagato or 0) or importo_verbale
    mese_sugg = mese_successivo(data_pagamento) or mese_successivo(
        datetime.now(timezone.utc)
    )
    return {
        "id": str(uuid.uuid4()),
        "tipo": "verbale_multa",
        # Dipendente
        "dipendente": dip["dipendente"],
        "dipendente_id": verbale.get("driver_id") or verbale.get("driver_cf"),
        "dipendente_nome": dip["dipendente"],  # compat con record legacy
        "codice_fiscale": dip["codice_fiscale"],
        "matricola": dip["matricola"],
        # Verbale
        "verbale_id": verbale.get("id"),
        "numero_verbale": verbale.get("numero_verbale"),
        "targa": verbale.get("targa"),
        "data_infrazione": verbale.get("data_infrazione")
        or verbale.get("data_verbale")
        or verbale.get("data"),
        # Importi
        "importo_verbale": importo_verbale,
        "importo_pagato_societa": importo_pagato,
        "importo_da_recuperare": importo_pagato,
        "importo": importo_pagato,  # compat con record legacy
        # Ciclo di vita
        "mese_cedolino_suggerito": mese_sugg,
        "stato": STATO_PROPOSTA,
        "nota_consulente": NOTA_CONSULENTE_DEFAULT,
        # Documenti collegati (riferimenti, non binari)
        "documento_verbale": {
            "disponibile": bool(verbale.get("pdf_data") or verbale.get("pdf_filename")),
            "filename": verbale.get("pdf_filename"),
        },
        "documento_pagamento": {
            "disponibile": bool(
                verbale.get("quietanza_pdf")
                or verbale.get("quietanza_filename")
                or verbale.get("pdf_ricevuta_path")
            ),
            "filename": verbale.get("quietanza_filename")
            or verbale.get("pdf_ricevuta_path"),
        },
        "data_pagamento": data_pagamento,
        "descrizione": (
            f"TRATTENUTA VERBALE {verbale.get('numero_verbale', '')} - "
            f"Targa {verbale.get('targa', '')}"
        ),
        "fonte": fonte,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================
# VERIFICA CEDOLINO (agganciata a on_cedolino_importato)
# ============================================================

async def _applica_esito_verifica(
    db,
    trattenuta: Dict[str, Any],
    periodo: str,
    cedolino_id: Optional[str],
    parola_trovata: Optional[str],
    fonte: str,
    stati_ammessi,
) -> Optional[str]:
    """
    Transizione condivisa tra verifica on-import e retroattiva:
    voce trovata → recuperata_in_busta (+ flag chiusura sul verbale, alert
    risolto); mancante → non_trovata_nel_cedolino + alert TRATTENUTA_NON_IN_CEDOLINO
    (genera_alert è idempotente: nessun doppione se già aperto).
    Claim atomico sugli stati ammessi: una trattenuta già recuperata/chiusa
    non viene mai toccata. Ritorna il nuovo stato applicato, o None se il
    claim non è riuscito (già processata da un altro percorso).
    """
    from app.services.audit_logger import log_evento
    from app.services.alert_engine import genera_alert, risolvi_alert

    tid = trattenuta.get("id")
    stato_prec = trattenuta.get("stato")
    now_iso = datetime.now(timezone.utc).isoformat()

    if parola_trovata:
        nuovo_stato = STATO_RECUPERATA
        update = {
            "stato": nuovo_stato,
            "recuperata_at": now_iso,
            "cedolino_id_riscontro": cedolino_id,
            "voce_cedolino_match": parola_trovata,
            "updated_at": now_iso,
        }
    else:
        nuovo_stato = STATO_NON_TROVATA
        update = {
            "stato": nuovo_stato,
            "verificata_at": now_iso,
            "cedolino_id_riscontro": cedolino_id,
            "updated_at": now_iso,
        }

    # Claim atomico: aggiorna solo se ancora negli stati ammessi (idempotente)
    res = await db[COLL_TRATTENUTE].update_one(
        {"id": tid, "stato": {"$in": list(stati_ammessi)}},
        {"$set": update},
    )
    if not res.modified_count:
        return None

    await log_evento(
        modulo="trattenute_verbali",
        azione="verifica_cedolino",
        entita_id=tid,
        entita_collection=COLL_TRATTENUTE,
        db=db,
        vecchio_stato={"stato": stato_prec},
        nuovo_stato={"stato": nuovo_stato},
        fonte=fonte,
        dettaglio=(
            f"Cedolino {periodo} {trattenuta.get('dipendente') or trattenuta.get('dipendente_nome', '')}: "
            + (
                f"trattenuta verbale {trattenuta.get('numero_verbale', '')} trovata "
                f"(voce '{parola_trovata}')"
                if parola_trovata
                else f"trattenuta verbale {trattenuta.get('numero_verbale', '')} NON trovata"
            )
        ),
        extra={"cedolino_id": cedolino_id},
    )

    if parola_trovata:
        # Chiusura lato verbale (flag dedicato: non tocca verbale.stato
        # per non interferire con le query pagato/riconciliato esistenti)
        if trattenuta.get("verbale_id"):
            try:
                await db["verbali_noleggio"].update_one(
                    {"id": trattenuta["verbale_id"]},
                    {"$set": {
                        "trattenuta_recuperata": True,
                        "trattenuta_recuperata_at": now_iso,
                        "trattenuta_recuperata_periodo": periodo,
                    }},
                )
            except Exception:
                logger.exception("Errore chiusura verbale %s", trattenuta.get("verbale_id"))
        # Se in passato era stato alzato l'alert, risolvilo
        try:
            await risolvi_alert("TRATTENUTA_NON_IN_CEDOLINO", tid, db)
        except Exception:
            logger.exception("Errore risoluzione alert trattenuta %s", tid)
    else:
        await genera_alert(
            "TRATTENUTA_NON_IN_CEDOLINO",
            tid,
            COLL_TRATTENUTE,
            (
                f"Trattenuta verbale {trattenuta.get('numero_verbale', '')} "
                f"({trattenuta.get('dipendente') or trattenuta.get('dipendente_nome', '')}, "
                f"€{float(trattenuta.get('importo_da_recuperare') or trattenuta.get('importo') or 0):.2f}) "
                f"attesa nel cedolino {periodo} ma non trovata"
            ),
            db,
            extra={"cedolino_id": cedolino_id, "verbale_id": trattenuta.get("verbale_id")},
        )

    return nuovo_stato


async def verifica_trattenute_cedolino(event: Dict[str, Any], db) -> Dict[str, Any]:
    """
    All'import di un cedolino: per ogni trattenuta del dipendente in stato
    comunicata_consulente/in_attesa_cedolino attesa per QUEL mese, cerca nel
    testo/voci del cedolino le parole di PAROLE_VOCE_TRATTENUTA.
    - trovata  → stato recuperata_in_busta (+ flag chiusura sul verbale)
    - mancante → stato non_trovata_nel_cedolino + alert TRATTENUTA_NON_IN_CEDOLINO
    Best-effort: gli errori vengono loggati, mai propagati al chiamante.
    """
    esito = {"verificate": 0, "recuperate": 0, "non_trovate": 0}

    cedolino_id = event.get("cedolino_id")
    codice_fiscale = (event.get("codice_fiscale") or "").upper()
    dipendente_id = event.get("dipendente_id")
    periodo = periodo_yyyymm(event.get("mese"), event.get("anno"))
    if not periodo or not (codice_fiscale or dipendente_id):
        return esito

    # Trattenute del dipendente in attesa di riscontro
    filtro_dip = []
    if codice_fiscale:
        filtro_dip.append({"codice_fiscale": codice_fiscale})
    if dipendente_id:
        filtro_dip.append({"dipendente_id": dipendente_id})
    trattenute = await db[COLL_TRATTENUTE].find(
        {"stato": {"$in": list(STATI_ATTESA_VERIFICA)}, "$or": filtro_dip},
        {"_id": 0},
    ).to_list(100)
    if not trattenute:
        return esito

    # Testo ricercabile: testo PDF passato nell'evento + campi del documento
    testo = str(event.get("pdf_text") or "")
    if cedolino_id:
        try:
            doc = await db["cedolini"].find_one({"id": cedolino_id})
            if doc:
                testo = f"{testo} {estrai_testo_cedolino(doc)}"
        except Exception:
            logger.exception("Errore lettura cedolino %s per verifica trattenute", cedolino_id)
    parola_trovata = trova_voce_trattenuta(testo)

    for t in trattenute:
        atteso = t.get("mese_cedolino_suggerito") or periodo_yyyymm(
            t.get("mese"), t.get("anno")
        )
        if atteso != periodo:
            continue  # il cedolino non è quello del mese atteso
        esito["verificate"] += 1
        applicato = await _applica_esito_verifica(
            db, t, periodo, cedolino_id, parola_trovata,
            fonte="cedolino_import", stati_ammessi=STATI_ATTESA_VERIFICA,
        )
        if applicato == STATO_RECUPERATA:
            esito["recuperate"] += 1
        elif applicato == STATO_NON_TROVATA:
            esito["non_trovate"] += 1

    return esito


# ============================================================
# VERIFICA RETROATTIVA (cedolini già archiviati)
# ============================================================

async def verifica_trattenute_retroattiva(db) -> Dict[str, Any]:
    """
    Ripescaggio sui cedolini GIÀ presenti nel gestionale (arrivati da posta
    o Drive in qualsiasi momento, anche prima della conferma della trattenuta):
    per ogni trattenuta in stato confermata/comunicata_consulente/
    in_attesa_cedolino cerca nei cedolini del dipendente con periodo >=
    mese_cedolino_suggerito (tutti, se il periodo non è ricostruibile) la
    stessa voce di trattenuta del percorso on-import e applica le stesse
    transizioni di stato/alert (_applica_esito_verifica).

    Idempotente: le trattenute già recuperata_in_busta/esclusa non vengono
    toccate (claim atomico sugli stati ammessi) e genera_alert non duplica
    alert già aperti. Nessuna cancellazione dati.
    Lo stato non_trovata_nel_cedolino scatta SOLO se il cedolino del mese
    atteso è già in archivio senza la voce (stessa semantica dell'on-import);
    se il cedolino atteso non è ancora arrivato, la trattenuta resta com'è.
    """
    esito = {"verificate": 0, "recuperate": 0, "non_trovate": 0}

    trattenute = await db[COLL_TRATTENUTE].find(
        {"stato": {"$in": list(STATI_VERIFICA_RETRO)}},
        {"_id": 0},
    ).to_list(500)

    for t in trattenute:
        try:
            codice_fiscale = (t.get("codice_fiscale") or "").upper()
            dipendente_id = t.get("dipendente_id")
            if not (codice_fiscale or dipendente_id):
                continue

            filtro_dip = []
            if codice_fiscale:
                filtro_dip.append({"codice_fiscale": codice_fiscale})
            if dipendente_id:
                filtro_dip.append({"dipendente_id": dipendente_id})
            cedolini = await db["cedolini"].find(
                {"$or": filtro_dip},
                {"_id": 0, "pdf_data": 0},
            ).to_list(200)

            periodo_min = t.get("mese_cedolino_suggerito") or periodo_yyyymm(
                t.get("mese"), t.get("anno")
            )
            candidati = cedolini_candidati(cedolini, periodo_min)
            if not candidati:
                continue

            # Cerca la voce nel primo cedolino (in ordine di periodo) che la contiene
            match_doc = None
            match_parola = None
            for doc in candidati:
                parola = trova_voce_trattenuta(estrai_testo_cedolino(doc))
                if parola:
                    match_doc = doc
                    match_parola = parola
                    break

            if match_doc:
                esito["verificate"] += 1
                periodo_match = periodo_cedolino(match_doc) or periodo_min or ""
                applicato = await _applica_esito_verifica(
                    db, t, periodo_match, match_doc.get("id"), match_parola,
                    fonte="verifica_retroattiva", stati_ammessi=STATI_VERIFICA_RETRO,
                )
                if applicato == STATO_RECUPERATA:
                    esito["recuperate"] += 1
            else:
                # Voce assente: segnala solo se il cedolino del mese ATTESO
                # esiste già in archivio (stessa regola dell'on-import).
                atteso_doc = next(
                    (d for d in candidati if periodo_cedolino(d) == periodo_min),
                    None,
                ) if periodo_min else None
                if not atteso_doc:
                    continue  # cedolino atteso non ancora arrivato: nessuna azione
                esito["verificate"] += 1
                applicato = await _applica_esito_verifica(
                    db, t, periodo_min, atteso_doc.get("id"), None,
                    fonte="verifica_retroattiva", stati_ammessi=STATI_VERIFICA_RETRO,
                )
                if applicato == STATO_NON_TROVATA:
                    esito["non_trovate"] += 1
        except Exception:
            logger.exception(
                "Errore verifica retroattiva trattenuta %s", t.get("id")
            )

    logger.info(f"[TRATTENUTE-RETRO] esito ripescaggio: {esito}")
    return esito
