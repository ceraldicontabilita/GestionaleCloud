"""Rilettura dell'archivio cedolini con il motore unico.

Rilegge i PDF delle buste gia' nel registro ``cedolini`` con
``cedolini_motore.leggi_pdf`` — lo stesso lettore deterministico di posta,
Drive e Documenti > Import — e salva accanto al documento l'esito della
rilettura, senza toccare i campi originali.

Fino al 07/10/2026 questo servizio aveva un secondo lettore tutto suo
(`enhanced_document_parser`, immagini → modello AI) che scriveva campi
paralleli ``*_enhanced``: un netto «calcolato» da competenze meno trattenute,
uno zero al posto del dato mancante, nessuno stato del netto. Quel lettore
non esiste piu': il netto e' quello della cella, lo stato lo dice
``stato_netto`` e il dato mancante resta nullo (CLAUDE.md §58, §59, §103).

La parte F24 non c'e' piu' (AV3-06): rileggeva i modelli con un secondo lettore
e scriveva campi paralleli `_enhanced` su collezioni dismesse (`f24_models`,
`f24`, `f24_uploaded`) che in produzione non esistono. I modelli hanno un solo
lettore, `parser_f24`, e un solo ingresso, `f24_canonico.importa_modello_bytes`.
"""

import asyncio
import base64
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.database import Database
from app.services.cedolini_hr_riverifica import busta_della_riga, buste_della_riga
from app.services.cedolini_motore import leggi_pdf

logger = logging.getLogger(__name__)

#: Il blocco scritto accanto al cedolino: una rilettura sola, l'ultima.
CAMPO_RILETTURA = "rilettura_motore_unico"
VERSIONE_RILETTURA = "motore_unico_v1"

# Quanti documenti tenere in memoria per volta. Prima se ne caricavano fino a
# 5.000 in una lista sola, ognuno col proprio PDF in base64: poche centinaia
# di cedolini bastavano a esaurire la memoria del servizio e farlo cadere.
DIMENSIONE_BLOCCO = 25
LIMITE_DOCUMENTI = 100000

#: Campi della busta riletta che vale la pena conservare per il confronto.
#: Il netto c'e' solo se il lettore lo ha verificato dalla cella: altrimenti
#: resta nullo, mai zero.
_CAMPI_BUSTA = (
    "stato_netto", "netto_fonte", "netto_calcolato", "lordo", "totale_trattenute",
    "tfr_quota", "tfr_quota_anno", "ore_lavorate", "giorni_lavorati",
    "ferie_permessi", "formato_rilevato", "tipo_cedolino", "mese", "anno",
    "codice_fiscale", "dati_chiave", "dati_extra",
)


async def _identificativi(coll, filtro: Dict[str, Any]) -> List[Any]:
    """Solo gli _id: e' una lettura leggera, senza i PDF."""
    cursore = coll.find(filtro, {"_id": 1})
    return [doc["_id"] for doc in await cursore.to_list(length=LIMITE_DOCUMENTI)]


async def _blocco(coll, identificativi: List[Any],
                  proiezione: Dict[str, int]) -> List[Dict[str, Any]]:
    """Carica i documenti di un blocco, PDF compresi."""
    cursore = coll.find({"_id": {"$in": identificativi}}, proiezione)
    return await cursore.to_list(length=len(identificativi))


def _riga(doc: Dict[str, Any]) -> Dict[str, Any]:
    """L'identita' del cedolino d'archivio nella forma che il matcher capisce."""
    return {
        "cf": doc.get("codice_fiscale") or doc.get("cf"),
        "anno": doc.get("anno"),
        "mese": doc.get("mese"),
        "tipo": doc.get("tipo_cedolino") or "mensile",
    }


def abbina_busta(doc: Dict[str, Any], lettura: Dict[str, Any]) -> Dict[str, Any]:
    """Quale busta del PDF riletto e' il cedolino d'archivio, e con che esito.

    Usa lo stesso criterio della riverifica HR (`cedolini_hr_riverifica`):
    codice fiscale, anno, tipo e, per le mensili, mese. Un cedolino storico
    senza identita' si abbina solo se il PDF contiene una busta sola.
    """
    buste = lettura.get("buste") or []
    riga = _riga(doc)
    if riga["cf"] and riga["anno"] and riga["mese"]:
        esito = busta_della_riga(riga, buste)
        candidate = buste_della_riga(riga, buste)
    elif len(buste) == 1:
        busta = buste[0]
        esito = {"esito": "ritrovata"}
        candidate = [busta]
    else:
        esito, candidate = {"esito": "non_ritrovata"}, []
    busta: Optional[Dict[str, Any]] = (
        candidate[0] if candidate and esito["esito"] in ("ritrovata", "netto_non_verificato") else None
    )
    return {"esito": esito["esito"], "busta": busta, "stato_netto": esito.get("stato_netto"),
            "netti": esito.get("netti")}


def rilettura(doc: Dict[str, Any], lettura: Dict[str, Any], *, adesso: str) -> Dict[str, Any]:
    """Il blocco da salvare accanto al cedolino.

    ``netto`` e' valorizzato soltanto quando la busta abbinata ha il netto
    verificato dalla cella; negli altri casi e' nullo e ``stato_netto`` dice
    perche'. Non si calcola nulla da competenze meno trattenute.
    """
    abbinamento = abbina_busta(doc, lettura)
    blocco: Dict[str, Any] = {
        "versione": VERSIONE_RILETTURA,
        "il": adesso,
        "esito_lettura": lettura.get("esito"),
        "motivo": lettura.get("motivo"),
        "buste_nel_pdf": len(lettura.get("buste") or []),
        "esito": abbinamento["esito"],
        "netto": None,
        "stato_netto": abbinamento.get("stato_netto"),
    }
    if abbinamento.get("netti"):
        blocco["netti_candidati"] = abbinamento["netti"]
    busta = abbinamento["busta"]
    if busta is None:
        return blocco
    for campo in _CAMPI_BUSTA:
        if campo in busta:
            blocco[campo] = busta[campo]
    if abbinamento["esito"] == "ritrovata":
        blocco["netto"] = busta.get("netto")
    return blocco


def aggiornamento(doc: Dict[str, Any], blocco: Dict[str, Any]) -> Dict[str, Any]:
    """Cosa scrivere sul cedolino: la rilettura e i dati chiave che mancano.

    ``dati_chiave`` e' il campo canonico che il lettore unico scrive sulle
    buste nuove (acconto recuperato, anticipo TFR, ratei): su un cedolino
    storico che non lo ha si aggiunge; dove c'e' gia', i valori esistenti
    vincono e si aggiungono solo le chiavi mancanti.
    """
    update: Dict[str, Any] = {CAMPO_RILETTURA: blocco}
    letti = blocco.get("dati_chiave")
    if isinstance(letti, dict) and letti:
        esistenti = doc.get("dati_chiave") if isinstance(doc.get("dati_chiave"), dict) else {}
        uniti = {**letti, **esistenti}
        if uniti != esistenti:
            update["dati_chiave"] = uniti
    return update


class BatchReprocessingService:
    """Rilegge i cedolini in archivio con il motore unico."""

    def __init__(self):
        self.db = None
        self.stats = {
            "cedolini_total": 0,
            "cedolini_processed": 0,
            "cedolini_success": 0,
            "cedolini_errors": 0,
            "esiti": {},
            "start_time": None,
            "end_time": None,
            "errors": []
        }

    async def init_db(self):
        """Inizializza connessione database."""
        self.db = Database.get_db()
        if self.db is None:
            raise Exception("Database non connesso")

    async def _riprocessa_cedolino(self, coll, coll_name: str, doc: Dict[str, Any],
                                   dry_run: bool) -> None:
        """Rilegge un cedolino e gli aggiunge l'esito del motore unico.

        Nessun inserimento, nessuna sovrascrittura dei dati
        originali, e un errore su un documento non ferma gli altri.
        """
        try:
            doc_id = doc.get("_id")
            pdf_data = (doc.get("pdf_data") or doc.get("file_base64")
                        or doc.get("pdf_base64"))
            if not pdf_data:
                return

            pdf_bytes = base64.b64decode(pdf_data)

            # Conta il tentativo prima della lettura.
            self.stats["cedolini_processed"] += 1

            # Lettura deterministica: parsing CPU fuori dall'event loop.
            lettura = await asyncio.to_thread(leggi_pdf, pdf_bytes)
            blocco = rilettura(doc, lettura, adesso=datetime.now(timezone.utc).isoformat())

            self.stats["cedolini_success"] += 1
            esiti = self.stats["esiti"]
            esiti[blocco["esito"]] = esiti.get(blocco["esito"], 0) + 1

            if not dry_run:
                await coll.update_one({"_id": doc_id}, {"$set": aggiornamento(doc, blocco)})

            dipendente = doc.get("dipendente_nome") or doc.get("codice_fiscale") or "N/D"
            periodo = f"{doc.get('mese', '?')}/{doc.get('anno', '?')}"
            logger.info("Cedolino %s %s riletto: %s (stato netto %s)",
                        dipendente, periodo, blocco["esito"], blocco.get("stato_netto"))

        except Exception as e:
            self.stats["cedolini_errors"] += 1
            self.stats["errors"].append({
                "type": "cedolino",
                "collection": coll_name,
                "doc_id": str(doc.get("_id")),
                "error": f"{type(e).__name__}: {e}",
            })
            logger.error("Errore rilettura cedolino %s: %s: %s", doc.get("_id"), type(e).__name__, e)

    async def reprocess_all_cedolini(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Rilegge tutti i cedolini con PDF disponibile.

        Args:
            dry_run: Se True, non salva le modifiche (solo test)

        Returns:
            Statistiche della rilettura
        """
        await self.init_db()

        if not self.stats["start_time"]:
            self.stats["start_time"] = datetime.now(timezone.utc).isoformat()

        # Unica collezione dei cedolini con PDF
        collections = ["cedolini"]

        for coll_name in collections:
            try:
                coll = self.db[coll_name]

                filtro = {"$or": [
                    {"pdf_data": {"$exists": True, "$ne": None}},
                    {"file_base64": {"$exists": True, "$ne": None}},
                    {"pdf_base64": {"$exists": True, "$ne": None}},
                ]}
                proiezione = {
                    "_id": 1, "pdf_data": 1, "file_base64": 1, "pdf_base64": 1,
                    "id": 1, "filename": 1, "dipendente_nome": 1, "mese": 1, "anno": 1,
                    "codice_fiscale": 1, "cf": 1, "tipo_cedolino": 1, "dati_chiave": 1,
                }
                identificativi = await _identificativi(coll, filtro)
                self.stats["cedolini_total"] += len(identificativi)

                logger.info(f"Trovati {len(identificativi)} cedolini con PDF in {coll_name}")

                for inizio in range(0, len(identificativi), DIMENSIONE_BLOCCO):
                    gruppo = identificativi[inizio:inizio + DIMENSIONE_BLOCCO]
                    for doc in await _blocco(coll, gruppo, proiezione):
                        await self._riprocessa_cedolino(coll, coll_name, doc, dry_run)

            except Exception as e:
                logger.error(f"Errore accesso collezione {coll_name}: {e}")

        self.stats["end_time"] = datetime.now(timezone.utc).isoformat()
        return self.stats

    async def reprocess_all(self, dry_run: bool = False) -> Dict[str, Any]:
        """Rilegge tutti i cedolini (l'unico documento che questo servizio rilegge)."""
        logger.info(f"Avvio rilettura batch {'(DRY RUN)' if dry_run else ''}")
        await self.reprocess_all_cedolini(dry_run)
        self.stats["totale_documenti"] = self.stats["cedolini_total"]
        self.stats["totale_processati"] = self.stats["cedolini_processed"]
        self.stats["totale_successi"] = self.stats["cedolini_success"]
        self.stats["totale_errori"] = self.stats["cedolini_errors"]
        self.stats["dry_run"] = dry_run
        logger.info(f"Rilettura completata: {self.stats['totale_successi']}/{self.stats['totale_processati']} successi")
        return self.stats


# Funzione helper per eseguire il batch
async def run_batch_reprocessing(dry_run: bool = False) -> Dict[str, Any]:
    """
    Esegue la rilettura batch di tutti i cedolini.

    Args:
        dry_run: Se True, esegue solo un test senza salvare

    Returns:
        Statistiche della rilettura
    """
    service = BatchReprocessingService()
    return await service.reprocess_all(dry_run)
