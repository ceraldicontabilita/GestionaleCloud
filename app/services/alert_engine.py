"""
Alert Engine — Gestionale Ceraldi Group
=========================================
Motore centralizzato per la generazione, risoluzione e gestione
degli alert di sistema. Tutti gli alert usano codici standardizzati
dal catalogo ALERT_CATALOG.

Utilizzo:
    from app.services.alert_engine import genera_alert, risolvi_alert
    
    await genera_alert("FORN_MP_MANCANTE", fornitore_id, "fornitori",
                       "Fornitore XYZ senza metodo pagamento", db)
    
    await risolvi_alert("FORN_MP_MANCANTE", fornitore_id, db)
"""
import logging
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Collection name — importare da db_collections.py quando aggiornato
COLL_ALERTS = "alerts"
COLL_ALERT_DEFINITIONS = "alert_definitions"


# ============================================================
# CATALOGO ALERT — Fonte di verità per tutti i codici
# ============================================================
ALERT_CATALOG: Dict[str, Dict[str, Any]] = {
    # --- Fornitori ---
    "FORN_MP_MANCANTE": {
        "modulo": "fornitori",
        "severita": "warning",
        "titolo": "Metodo pagamento mancante",
        "condizione_chiusura": "metodo_pagamento valorizzato"
    },
    "FORN_NUOVO_INCOMPLETO": {
        "modulo": "fornitori",
        "severita": "info",
        "titolo": "Fornitore nuovo da completare",
        "condizione_chiusura": "Campi minimi completati"
    },
    "FORN_IBAN_MANCANTE": {
        "modulo": "fornitori",
        "severita": "warning",
        "titolo": "IBAN mancante per fornitore bancario",
        "condizione_chiusura": "IBAN valorizzato"
    },
    "FORN_DUPLICATO": {
        "modulo": "fornitori",
        "severita": "warning",
        "titolo": "Possibile fornitore duplicato",
        "condizione_chiusura": "Utente conferma o merge"
    },
    "FORN_DATI_INCOERENTI": {
        "modulo": "fornitori",
        "severita": "warning",
        "titolo": "Dati fiscali incoerenti",
        "condizione_chiusura": "Dati corretti"
    },
    "FORN_INATTIVO_USATO": {
        "modulo": "fornitori",
        "severita": "info",
        "titolo": "Fornitore inattivo con nuovi documenti",
        "condizione_chiusura": "Fornitore riattivato o docs spostati"
    },
    
    # --- Fatture ---
    "FAT_DUPLICATA": {
        "modulo": "fatture",
        "severita": "warning",
        "titolo": "Fattura potenzialmente duplicata",
        "condizione_chiusura": "Utente conferma"
    },
    "FAT_FORN_NON_TROVATO": {
        "modulo": "fatture",
        "severita": "critical",
        "titolo": "Fornitore non riconosciuto",
        "condizione_chiusura": "Fornitore collegato"
    },
    "FAT_MP_NON_DEFINITO": {
        "modulo": "fatture",
        "severita": "warning",
        "titolo": "Metodo pagamento non definito — fattura sospesa",
        "condizione_chiusura": "MP impostato su fornitore"
    },
    "FAT_TIPO_AMBIGUO": {
        "modulo": "fatture",
        "severita": "warning",
        "titolo": "Tipo documento ambiguo",
        "condizione_chiusura": "Tipo confermato"
    },
    "FAT_RIGHE_MERCE_NON_RISOLTE": {
        "modulo": "fatture",
        "severita": "info",
        "titolo": "Righe merce senza match magazzino",
        "condizione_chiusura": "Match confermato"
    },
    "FAT_DATI_INCOMPLETI": {
        "modulo": "fatture",
        "severita": "warning",
        "titolo": "Dati fattura incompleti",
        "condizione_chiusura": "Dati completati"
    },
    "FAT_ESTERA_DA_VERIFICARE": {
        "modulo": "fatture",
        "severita": "warning",
        "titolo": "Fattura estera letta dall'AI — da verificare",
        "condizione_chiusura": "Utente conferma o corregge i dati letti"
    },
    "FAT_DA_PAGARE_SCADUTA": {
        "modulo": "fatture",
        "severita": "critical",
        "titolo": "Fattura scaduta non pagata",
        "condizione_chiusura": "Pagamento registrato"
    },
    
    # --- F24 ---
    "F24_ATTESO_NON_ACQUISITO": {
        "modulo": "f24",
        "severita": "warning",
        "titolo": "F24 atteso ma documento non acquisito",
        "condizione_chiusura": "Documento acquisito"
    },
    "F24_NON_PAGATO": {
        "modulo": "f24",
        "severita": "warning",
        "titolo": "F24 acquisito ma non pagato",
        "condizione_chiusura": "Pagamento confermato"
    },
    "F24_SCADUTO": {
        "modulo": "f24",
        "severita": "critical",
        "titolo": "F24 scaduto non pagato",
        "condizione_chiusura": "Pagamento avvenuto"
    },
    "F24_NON_RICONCILIATO": {
        "modulo": "f24",
        "severita": "info",
        "titolo": "F24 pagato ma non riconciliato con banca",
        "condizione_chiusura": "Match bancario confermato"
    },
    "F24_DUPLICATO": {
        "modulo": "f24",
        "severita": "warning",
        "titolo": "Possibile F24 duplicato",
        "condizione_chiusura": "Utente conferma"
    },
    "F24_PARSER_INCOMPLETO": {
        "modulo": "f24",
        "severita": "info",
        "titolo": "Dati F24 estratti incompleti",
        "condizione_chiusura": "Dati completati"
    },
    
    # --- Cedolini ---
    "CED_TIPO_NON_RICONOSCIUTO": {
        "modulo": "cedolini",
        "severita": "warning",
        "titolo": "Tipo cedolino non riconosciuto",
        "condizione_chiusura": "Tipo confermato"
    },
    "CED_DIP_NON_TROVATO": {
        "modulo": "cedolini",
        "severita": "critical",
        "titolo": "Dipendente non trovato per cedolino",
        "condizione_chiusura": "Dipendente collegato"
    },
    "CED_DUPLICATO": {
        "modulo": "cedolini",
        "severita": "warning",
        "titolo": "Possibile cedolino duplicato",
        "condizione_chiusura": "Utente conferma"
    },
    "CED_DATI_ECONOMICI_INCOMPLETI": {
        "modulo": "cedolini",
        "severita": "warning",
        "titolo": "Dati economici incompleti (netto/lordo/TFR)",
        "condizione_chiusura": "Dati completati"
    },
    "CED_PRIMA_NOTA_NON_GENERATA": {
        "modulo": "cedolini",
        "severita": "info",
        "titolo": "Cedolino valido senza movimento prima nota",
        "condizione_chiusura": "Movimento generato"
    },
    "CED_TFR_NON_AGGIORNATO": {
        "modulo": "cedolini",
        "severita": "info",
        "titolo": "Accantonamento TFR non aggiornato",
        "condizione_chiusura": "TFR aggiornato"
    },
    "CED_NON_PAGATO": {
        "modulo": "cedolini",
        "severita": "warning",
        "titolo": "Cedolino importato ma stipendio non pagato",
        "condizione_chiusura": "Pagamento confermato"
    },
    "CED_MATCH_BANCA_AMBIGUO": {
        "modulo": "cedolini",
        "severita": "info",
        "titolo": "Match bancario stipendio ambiguo",
        "condizione_chiusura": "Match confermato o respinto"
    },
    "CED_INCOERENZA_PRESENZE": {
        "modulo": "cedolini",
        "severita": "info",
        "titolo": "Incoerenza tra cedolino e presenze",
        "condizione_chiusura": "Differenza spiegata"
    },
    "TRATTENUTA_NON_IN_CEDOLINO": {
        "modulo": "cedolini",
        "severita": "warning",
        "titolo": "Trattenuta verbale non trovata nel cedolino",
        "condizione_chiusura": "Trattenuta trovata in un cedolino successivo o gestita dall'utente"
    },
    
    # --- Dipendenti ---
    "DIP_INCOMPLETO": {
        "modulo": "dipendenti",
        "severita": "warning",
        "titolo": "Anagrafica dipendente incompleta",
        "condizione_chiusura": "Campi completati"
    },
    "DIP_IBAN_MANCANTE": {
        "modulo": "dipendenti",
        "severita": "warning",
        "titolo": "IBAN stipendio mancante",
        "condizione_chiusura": "IBAN valorizzato"
    },
    "DIP_DUPLICATO": {
        "modulo": "dipendenti",
        "severita": "warning",
        "titolo": "Possibile dipendente duplicato",
        "condizione_chiusura": "Utente conferma o merge"
    },
    "DIP_CESSATO_FLUSSI_ATTIVI": {
        "modulo": "dipendenti",
        "severita": "warning",
        "titolo": "Dipendente cessato con flussi attivi",
        "condizione_chiusura": "Utente verifica"
    },
    "DIP_CONTRATTO_MANCANTE": {
        "modulo": "dipendenti",
        "severita": "info",
        "titolo": "Contratto dipendente mancante",
        "condizione_chiusura": "Contratto inserito"
    },
    
    # --- Banca ---
    "BNK_NON_CLASSIFICATO": {
        "modulo": "banca",
        "severita": "info",
        "titolo": "Movimento bancario non classificato",
        "condizione_chiusura": "Classificato"
    },
    "BNK_DUPLICATO": {
        "modulo": "banca",
        "severita": "warning",
        "titolo": "Possibile movimento bancario duplicato",
        "condizione_chiusura": "Confermato"
    },
    "BNK_FAT_SENZA_RISCONTRO": {
        "modulo": "banca",
        "severita": "warning",
        "titolo": "Fattura bancaria senza riscontro pagamento",
        "condizione_chiusura": "Pagamento trovato"
    },
    "BNK_POS_NON_RICONCILIATO": {
        "modulo": "banca",
        "severita": "warning",
        "titolo": "Accredito POS atteso non riconciliato",
        "condizione_chiusura": "Match confermato"
    },
    "BNK_F24_NON_RICONCILIATO": {
        "modulo": "banca",
        "severita": "warning",
        "titolo": "Addebito F24 non riconciliato",
        "condizione_chiusura": "Match confermato"
    },
    "BNK_TRASFERIMENTO_INCOMPLETO": {
        "modulo": "banca",
        "severita": "info",
        "titolo": "Trasferimento interno incompleto",
        "condizione_chiusura": "Lato opposto collegato"
    },
    "BNK_DIFFERENZA_IMPORTO": {
        "modulo": "banca",
        "severita": "info",
        "titolo": "Differenza importo in match bancario",
        "condizione_chiusura": "Differenza spiegata"
    },
    
    # --- Cassa ---
    "CAS_DUPLICATO": {
        "modulo": "cassa",
        "severita": "warning",
        "titolo": "Possibile movimento cassa duplicato",
        "condizione_chiusura": "Confermato"
    },
    "CAS_SENZA_CAUSALE": {
        "modulo": "cassa",
        "severita": "info",
        "titolo": "Movimento cassa senza causale chiara",
        "condizione_chiusura": "Causale inserita"
    },
    "CAS_FAT_CONTANTI_NON_REGOLATA": {
        "modulo": "cassa",
        "severita": "warning",
        "titolo": "Fattura contanti non regolata",
        "condizione_chiusura": "Pagamento confermato"
    },
    "CAS_DIFFERENZA_SALDO": {
        "modulo": "cassa",
        "severita": "critical",
        "titolo": "Differenza saldo cassa teorico vs reale",
        "condizione_chiusura": "Rettifica registrata"
    },
    "CAS_CORRISPETTIVI_INCOERENTI": {
        "modulo": "cassa",
        "severita": "warning",
        "titolo": "Quota contanti corrispettivi incoerente",
        "condizione_chiusura": "Corretto"
    },
    
    # --- Magazzino ---
    "MAG_PRODOTTO_INCOMPLETO": {
        "modulo": "magazzino",
        "severita": "info",
        "titolo": "Prodotto nuovo da configurare",
        "condizione_chiusura": "Categoria impostata"
    },
    "MAG_MATCH_DUBBIO": {
        "modulo": "magazzino",
        "severita": "info",
        "titolo": "Match prodotto incerto",
        "condizione_chiusura": "Match confermato"
    },
    "MAG_UNITA_INCOERENTE": {
        "modulo": "magazzino",
        "severita": "warning",
        "titolo": "Unità di misura incoerente per prodotto",
        "condizione_chiusura": "Conversione definita"
    },
    "MAG_DUPLICATO_PRODOTTO": {
        "modulo": "magazzino",
        "severita": "info",
        "titolo": "Possibile prodotto duplicato",
        "condizione_chiusura": "Merge o conferma"
    },
    
    # --- Documenti/Inbox ---
    "DOC_NON_CLASSIFICATO": {
        "modulo": "documenti",
        "severita": "info",
        "titolo": "Documento non classificato",
        "condizione_chiusura": "Classificato"
    },
    "DOC_PARSER_FALLITO": {
        "modulo": "documenti",
        "severita": "warning",
        "titolo": "Parser fallito su documento",
        "condizione_chiusura": "Parser corretto o rilanciato"
    },
    "FATTURA_CASSA_PAGATA_BANCA": {
        "modulo": "prima_nota",
        "severita": "warning",
        "titolo": "Fattura pagata per BANCA nonostante metodo cassa",
        "condizione_chiusura": "Presa visione (registrazione già corretta in banca)"
    },
    "DOC_DUPLICATO": {
        "modulo": "documenti",
        "severita": "info",
        "titolo": "Documento duplicato rilevato",
        "condizione_chiusura": "Confermato"
    },
    "DOC_ENTITA_NON_TROVATA": {
        "modulo": "documenti",
        "severita": "warning",
        "titolo": "Entità target non trovata per documento",
        "condizione_chiusura": "Entità trovata o creata"
    },
    "DOC_REPROCESSING_NECESSARIO": {
        "modulo": "documenti",
        "severita": "info",
        "titolo": "Documento da rielaborare con nuove regole",
        "condizione_chiusura": "Rielaborato"
    },
    "DOC_QUADRATURA_DRIVE": {
        "modulo": "documenti",
        "severita": "warning",
        "titolo": "Quadratura Drive: fatture archiviate senza record recuperate",
        "condizione_chiusura": "Verificato l'esito del recupero"
    },
    "CEDOLINO_MAI_PROCESSATO": {
        "modulo": "cedolini",
        "severita": "warning",
        "titolo": "Cedolino arrivato ma mai diventato un cedolino vero in contabilità",
        "condizione_chiusura": "Verificato/riprocessato manualmente"
    },
    "FATTURA_ANNUNCIATA_NON_ARRIVATA": {
        "modulo": "documenti",
        "severita": "warning",
        "titolo": "Fattura annunciata da email Aruba ma XML mai arrivato",
        "condizione_chiusura": "XML importato (riscontro) o attesa annullata"
    },
    "FATTURA_ATTESA_OLTRE_TERMINE": {
        "modulo": "documenti",
        "severita": "critical",
        "titolo": "Fattura attesa oltre il termine normativo (12 giorni SDI)",
        "condizione_chiusura": "XML importato, fornitore sollecitato o attesa annullata"
    },
    "EMAIL_ARUBA_NON_LEGGIBILE": {
        "modulo": "documenti",
        "severita": "info",
        "titolo": "Notifica Aruba non interpretabile automaticamente",
        "condizione_chiusura": "Attesa completata a mano o annullata"
    },

    # --- Noleggio auto ---
    "NOL_FATTURA_MANCANTE": {
        "modulo": "fatture",
        "severita": "warning",
        "titolo": "Veicolo attivo senza fatture di noleggio recenti (da verificare)",
        "condizione_chiusura": "Nuova fattura arrivata o contratto marcato cessato"
    },
    "NOL_CESSAZIONE_RILEVATA": {
        "modulo": "fatture",
        "severita": "info",
        "titolo": "Probabile cessazione contratto noleggio (dicitura in fattura)",
        "condizione_chiusura": "Stato contratto confermato dall'utente sulla scheda veicolo"
    },

    # --- Riconciliazione ---
    "RIC_NON_RICONCILIATO": {
        "modulo": "riconciliazione",
        "severita": "info",
        "titolo": "Movimento senza match riconciliazione",
        "condizione_chiusura": "Match trovato"
    },
    "RIC_MATCH_AMBIGUO": {
        "modulo": "riconciliazione",
        "severita": "warning",
        "titolo": "Match riconciliazione ambiguo",
        "condizione_chiusura": "Utente sceglie"
    },
    "RIC_DIFFERENZA_IMPORTO": {
        "modulo": "riconciliazione",
        "severita": "info",
        "titolo": "Differenza importo in riconciliazione",
        "condizione_chiusura": "Differenza spiegata"
    },
    "RIC_PARTITA_VECCHIA": {
        "modulo": "riconciliazione",
        "severita": "warning",
        "titolo": "Partita aperta oltre soglia temporale",
        "condizione_chiusura": "Chiusa o giustificata"
    },
    "RIC_POS_NON_QUADRATO": {
        "modulo": "riconciliazione",
        "severita": "warning",
        "titolo": "Totale POS atteso non quadra con accrediti",
        "condizione_chiusura": "Quadratura completata"
    },
    "RIC_PAGAMENTO_MULTIPLO": {
        "modulo": "riconciliazione",
        "severita": "info",
        "titolo": "Pagamento multiplo non risolvibile automaticamente",
        "condizione_chiusura": "Utente risolve"
    },
}


# ============================================================
# FUNZIONI PRINCIPALI
# ============================================================

async def genera_alert(
    codice: str,
    entita_id: str,
    entita_collection: str,
    dettaglio: str,
    db,
    extra: Optional[Dict] = None
) -> Optional[Dict]:
    """
    Genera un alert se non ne esiste già uno aperto con stesso codice+entità.
    Idempotente: se l'alert esiste già aperto, non lo duplica.
    
    Returns: il documento alert creato, o None se già esistente.
    """
    if codice not in ALERT_CATALOG:
        logger.warning(f"Codice alert sconosciuto: {codice}")
        return None
    
    cat = ALERT_CATALOG[codice]
    
    # Idempotenza: controlla se esiste già aperto
    existing = await db[COLL_ALERTS].find_one({
        "codice": codice,
        "entita_id": entita_id,
        "stato": "aperto"
    })
    
    if existing:
        logger.debug(f"Alert {codice} già aperto per {entita_id}, skip")
        return None
    
    alert = {
        "id": f"alert_{uuid.uuid4().hex[:12]}",
        "codice": codice,
        "modulo": cat["modulo"],
        "severita": cat["severita"],
        "titolo": cat["titolo"],
        "dettaglio": dettaglio,
        "condizione_chiusura": cat["condizione_chiusura"],
        "entita_id": entita_id,
        "entita_collection": entita_collection,
        "stato": "aperto",
        "letto": False,
        "risolto": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "resolved_at": None,
        "resolved_by": None,
    }
    
    if extra:
        alert["extra"] = extra
    
    await db[COLL_ALERTS].insert_one(alert)
    logger.info(f"Alert generato: {codice} per {entita_collection}/{entita_id}")
    return alert


async def risolvi_alert(
    codice: str,
    entita_id: str,
    db,
    resolved_by: str = "sistema"
) -> int:
    """
    Chiude tutti gli alert aperti con codice+entità dati.
    
    Returns: numero di alert chiusi.
    """
    result = await db[COLL_ALERTS].update_many(
        {
            "codice": codice,
            "entita_id": entita_id,
            "stato": "aperto"
        },
        {
            "$set": {
                "stato": "risolto",
                "risolto": True,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "resolved_by": resolved_by
            }
        }
    )
    
    if result.modified_count > 0:
        logger.info(
            f"Alert risolti: {result.modified_count}x {codice} "
            f"per {entita_id} (da {resolved_by})"
        )
    
    return result.modified_count


async def risolvi_alert_multi(
    codici: List[str],
    entita_id: str,
    db,
    resolved_by: str = "sistema"
) -> int:
    """Chiude alert multipli per la stessa entità."""
    total = 0
    for codice in codici:
        total += await risolvi_alert(codice, entita_id, db, resolved_by)
    return total


async def verifica_alert_aperti(
    entita_id: str,
    db
) -> List[Dict]:
    """Ritorna tutti gli alert aperti per un'entità."""
    alerts = await db[COLL_ALERTS].find(
        {"entita_id": entita_id, "stato": "aperto"},
        {"_id": 0}
    ).to_list(100)
    return alerts


async def conta_alert_per_modulo(db) -> Dict[str, Dict[str, int]]:
    """Ritorna conteggio alert aperti raggruppati per modulo e severità."""
    pipeline = [
        {"$match": {"stato": "aperto"}},
        {"$group": {
            "_id": {"modulo": "$modulo", "severita": "$severita"},
            "count": {"$sum": 1}
        }}
    ]
    
    result = {}
    async for doc in db[COLL_ALERTS].aggregate(pipeline):
        modulo = doc["_id"]["modulo"]
        severita = doc["_id"]["severita"]
        if modulo not in result:
            result[modulo] = {}
        result[modulo][severita] = doc["count"]
    
    return result


async def ignora_alert(
    alert_id: str,
    db,
    ignored_by: str = "utente"
) -> bool:
    """Segna un alert come ignorato dall'utente."""
    result = await db[COLL_ALERTS].update_one(
        {"id": alert_id, "stato": "aperto"},
        {
            "$set": {
                "stato": "ignorato",
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "resolved_by": ignored_by
            }
        }
    )
    return result.modified_count > 0


# ============================================================
# SEED: inserire definizioni alert in MongoDB
# ============================================================
async def seed_alert_definitions(db):
    """Inserisce/aggiorna il catalogo alert_definitions in MongoDB."""
    for codice, dati in ALERT_CATALOG.items():
        await db[COLL_ALERT_DEFINITIONS].update_one(
            {"codice": codice},
            {"$set": {
                "codice": codice,
                **dati,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
    logger.info(f"Seed alert_definitions: {len(ALERT_CATALOG)} codici")
