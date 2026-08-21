"""
CORRISPETTIVI SERVICE - Con Controlli di Sicurezza
==================================================

Servizio unificato per la gestione corrispettivi con:
- Validazione business rules
- Controlli di sicurezza pre-operazione
- Propagazione automatica a Prima Nota Cassa
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import uuid

from app.database import Database
from app.services.business_rules import (
    BusinessRules,
    CorrispettivoStatus,
    EntityStatus
)

logger = logging.getLogger(__name__)


class CorrispettiviService:
    """
    Servizio corrispettivi con controlli di sicurezza integrati.

    FLUSSO:
    1. Upload XML corrispettivo → Parse dati
    2. Verifica duplicato
    3. Salva corrispettivo
    4. Propaga a Prima Nota Cassa (incasso giornaliero)
    """

    def __init__(self, db=None):
        # SheetDatabase vieta intenzionalmente bool(db): usare
        # sempre il confronto esplicito, altrimenti il job Drive fallisce
        # prima ancora di leggere il primo XML.
        self.db = db if db is not None else Database.get_db()
        self.corrispettivi = self.db["corrispettivi"]
        self.cash_movements = self.db["prima_nota_cassa"]  # Usa collection corretta

    def _generate_id(self) -> str:
        """Bug scoperto il 14/07/2026: mancava del tutto — process_xml e
        create_manual (che lo chiamano per l'id del corrispettivo) andavano
        in AttributeError ad ogni chiamata reale. L'unico chiamante di
        process_xml in produzione è drive_corrispettivi_ingest.py (il
        canale Drive corrispettivi appena attivato): ogni sync sarebbe
        fallito su ogni singolo file."""
        return str(uuid.uuid4())

    # ==================== CREATE ====================

    async def process_xml(self, xml_content: bytes, filename: str,
                           applica_filtro_anno: bool = False) -> Dict[str, Any]:
        """
        Processa un file XML corrispettivo.

        `applica_filtro_anno` (richiesta utente 14/07/2026, propagazione
        dello stesso filtro già applicato all'import Drive delle fatture:
        SOLO l'ingest automatico da Drive lo attiva): se True e la data del
        corrispettivo non è nell'anno di importazione attivo configurato
        (vedi app.services.config_import), il corrispettivo viene comunque
        salvato per consultazione ma marcato `stato_import="archivio_storico"`
        e NON propagato a Prima Nota né all'event bus (niente Coerenza POS,
        niente calendario accrediti) — un corrispettivo storico non deve
        alterare il saldo cassa/banca dell'anno attivo. Default False:
        l'import manuale da UI resta invariato.
        """
        logger.info(f"Processing corrispettivo XML: {filename}")

        # 1. Parse XML
        try:
            parsed = self._parse_corrispettivo_xml(xml_content)
        except Exception as e:
            logger.error(f"XML parse error: {e}")
            return {"status": "error", "message": f"Errore parsing XML: {str(e)}"}

        # Una chiusura eseguita poco dopo mezzanotte appartiene al giorno
        # precedente solo quando quel giorno non ha ancora un valore. La data
        # fiscale originale resta conservata nella provenienza XML.
        await self._resolve_effective_date(parsed)

        # 2. Check duplicato esatto. source_hashes copre anche gli XML gia'
        # sommati in una chiusura giornaliera esistente.
        content_hash = hashlib.sha256(xml_content).hexdigest()
        existing = await self.corrispettivi.find_one({"content_hash": content_hash})
        if existing is None:
            existing = await self.corrispettivi.find_one({"source_hashes": content_hash})
        if existing:
            # Recupero conservativo dei PeriodoInattivo gia' importati dal
            # vecchio parser con data odierna: non sono vendite e non devono
            # alterare Prima Nota. L'hash deve essere identico e la data vera
            # deve appartenere a un anno storico rispetto a quello attivo.
            if applica_filtro_anno and parsed.get("_periodo_inattivo"):
                from app.services.config_import import get_anno_importazione_attivo
                anno_attivo = await get_anno_importazione_attivo(self.db)
                data_reale = parsed.get("data") or ""
                anno_reale = int(data_reale[:4]) if data_reale[:4].isdigit() else None
                if anno_reale and anno_reale != anno_attivo:
                    from app.routers.invoices.corrispettivi_helpers import (
                        _delete_prima_nota_for_corrispettivo,
                    )
                    corr_id = existing.get("id")
                    await _delete_prima_nota_for_corrispettivo(
                        self.db, corr_id, existing.get("data", "")
                    )
                    await self.corrispettivi.update_one(
                        {"id": corr_id},
                        {"$set": {
                            "data": data_reale,
                            "progressivo": parsed.get("progressivo", ""),
                            "id_dispositivo": parsed.get("id_dispositivo", ""),
                            # Alias pubblico usato dalla pagina Corrispettivi.
                            # Manteniamo anche id_dispositivo per dedup e
                            # compatibilita' con i record storici.
                            "matricola_rt": parsed.get("id_dispositivo", ""),
                            "totale": parsed.get("totale", 0),
                            "totale_complessivo": parsed.get("totale", 0),
                            "pagato_contanti": parsed.get("pagato_contanti", 0),
                            "pagato_pos": parsed.get("pagato_pos", 0),
                            "pagato_elettronico": parsed.get("pagato_pos", 0),
                            "non_riscosso": parsed.get("non_riscosso", 0),
                            "totale_iva": parsed.get("totale_iva", 0),
                            "imponibile": parsed.get("imponibile", 0),
                            "riepilogo_iva": parsed.get("riepilogo_iva", []),
                            "status": "archiviata",
                            "stato_import": "archivio_storico",
                            "prima_nota_id": None,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }},
                    )
                    return {
                        "status": "archiviata",
                        "corrispettivo_id": str(corr_id),
                        "data": data_reale,
                        "totale": parsed.get("totale", 0),
                        "prima_nota_id": None,
                        "message": "Periodo inattivo storico riallineato dal documento originale",
                    }
            return {
                "status": "duplicate",
                "corrispettivo_id": str(existing.get("id")),
                "repaired_accounting": await self._repair_duplicate_accounting(
                    existing, parsed, applica_filtro_anno, exact_source=True,
                ),
                "message": "Corrispettivo già presente"
            }

        # Check duplicato per data + dispositivo. Bug segnalato dall'utente
        # 15/07/2026 (saldo Prima Nota sballato di decine di migliaia di
        # euro): il controllo guardava SOLO la data, ignorando
        # id_dispositivo (la matricola del registratore telematico che ha
        # emesso il corrispettivo). L'attività ha UN SOLO registratore, ma
        # la sua matricola può cambiare nel tempo (es. al risigillo
        # triennale obbligatorio in occasione della verifica fiscale
        # periodica — precisazione utente 15/07/2026, non sono PDV/casse
        # multiple): senza guardare la matricola, un corrispettivo con la
        # matricola nuova poteva essere scartato come "duplicato" di uno
        # con matricola diversa sulla stessa data, sparendo del tutto da
        # Prima Nota Cassa/Banca invece di essere salvato.
        dup_query = {
            "data": parsed["data"],
            "entity_status": {"$ne": EntityStatus.DELETED.value}
        }
        if parsed.get("id_dispositivo"):
            dup_query["id_dispositivo"] = parsed["id_dispositivo"]
        existing_date = await self.corrispettivi.find_one(dup_query)
        if existing_date:
            return await self._merge_distinct_xml(
                existing_date, parsed, filename, content_hash,
                applica_filtro_anno=applica_filtro_anno,
            )

        # Filtro anno: data mancante/illeggibile resta nel flusso attivo di
        # proposito (mai archiviare alla cieca un XML sospetto).
        archivia_solo = False
        if applica_filtro_anno:
            from app.services.config_import import get_anno_importazione_attivo
            anno_attivo = await get_anno_importazione_attivo(self.db)
            data_str = parsed.get("data") or ""
            anno_corr = int(data_str[:4]) if data_str[:4].isdigit() else None
            archivia_solo = bool(anno_corr and anno_corr != anno_attivo)

        # 3. Prepara documento
        corr_doc = {
            "id": self._generate_id(),
            "filename": filename,
            "content_hash": content_hash,
            "source_hashes": [content_hash],
            "source_files": [filename],
            "chiusure_xml": [self._xml_component(parsed, filename, content_hash)],
            "data": parsed["data"],
            "data_rilevazione_xml": parsed.get("data_originale_xml", parsed["data"]),
            "chiusura_post_mezzanotte": bool(parsed.get("chiusura_post_mezzanotte")),
            "progressivo": parsed.get("progressivo", ""),
            "id_dispositivo": parsed.get("id_dispositivo", ""),
            "matricola_rt": parsed.get("id_dispositivo", ""),

            # Importi
            "totale": parsed["totale"],
            "totale_complessivo": parsed["totale"],
            "pagato_contanti": parsed.get("pagato_contanti", 0),
            "pagato_pos": parsed.get("pagato_pos", 0),
            # Campo canonico letto da Coerenza POS. Manteniamo pagato_pos
            # come alias storico per compatibilita' con le viste esistenti.
            "pagato_elettronico": parsed.get("pagato_pos", 0),
            "non_riscosso": parsed.get("non_riscosso", 0),
            "numero_documenti": parsed.get("numero_documenti", 0),

            # IVA
            "totale_iva": parsed.get("totale_iva", 0),
            "imponibile": parsed.get("imponibile", 0),
            "riepilogo_iva": parsed.get("riepilogo_iva", []),

            # Stati
            "status": CorrispettivoStatus.IMPORTED.value,
            "entity_status": EntityStatus.ACTIVE.value,
            "stato": "definitivo_xml",
            "totale_xml": parsed["totale"],

            # Metadata
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "data_import_xml": datetime.now(timezone.utc).isoformat(),
            "source": "xml",

            # Relazioni
            "prima_nota_id": None
        }

        if archivia_solo:
            corr_doc["status"] = "archiviata"
            corr_doc["stato_import"] = "archivio_storico"
            await self.corrispettivi.insert_one(corr_doc.copy())
            logger.info(f"Corrispettivo archiviato (anno storico): {corr_doc['id']}")
            return {
                "status": "archiviata",
                "corrispettivo_id": corr_doc["id"],
                "data": corr_doc["data"],
                "totale": corr_doc["totale"],
                "prima_nota_id": None,
                "message": "Corrispettivo di un anno storico: archiviato per sola consultazione, "
                           "non registrato in Prima Nota"
            }

        # Calendario accrediti POS: se c'e' quota elettronica, il corrispettivo
        # entra "in attesa accredito" con la data prevista dal calendario
        # (giorni lavorativi + festivi, mai il semplice mese contabile).
        if corr_doc["pagato_pos"] and corr_doc["pagato_pos"] > 0:
            from app.utils.pos_accredito import data_accredito_prevista_str
            prevista = data_accredito_prevista_str(corr_doc["data"])
            if prevista:
                corr_doc["data_prevista_accredito"] = prevista
                corr_doc["stato_accredito"] = "in_attesa_accredito"

        # 4. Salva corrispettivo
        await self.corrispettivi.insert_one(corr_doc.copy())
        corr_id = corr_doc["id"]

        # 5. Propaga a Prima Nota Cassa
        prima_nota_id = await self._create_prima_nota_entry(corr_doc)
        if prima_nota_id:
            await self.corrispettivi.update_one(
                {"id": corr_id},
                {"$set": {"prima_nota_id": prima_nota_id}}
            )

        logger.info(f"Corrispettivo created: {corr_id}")

        # ── EVENTO: pubblica sul bus unico per prima nota e check POS ──
        try:
            from app.services.event_bus import propagate_event, EventTypes
            await propagate_event(EventTypes.CORRISPETTIVI_IMPORTATI, {
                "corrispettivi": [corr_doc],
                "data":          corr_doc.get("data"),
                "totale":        corr_doc.get("totale"),
                "id":            corr_id,
            }, self.db, source_module="corrispettivi_service")
        except Exception as _ev:
            logger.debug(f"[CorrispettiviService] Event Bus: {_ev}")

        return {
            "status": "created",
            "corrispettivo_id": corr_id,
            "data": corr_doc["data"],
            "totale": corr_doc["totale"],
            "prima_nota_id": prima_nota_id,
            "message": "Corrispettivo importato con successo"
        }

    async def create_manual(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crea un corrispettivo manuale (non da XML).
        """
        # Validazioni
        if not data.get("data"):
            return {"status": "error", "message": "Data obbligatoria"}
        if not data.get("totale") or data["totale"] <= 0:
            return {"status": "error", "message": "Totale deve essere maggiore di 0"}

        # Check duplicato per data
        existing = await self.corrispettivi.find_one({
            "data": data["data"],
            "entity_status": {"$ne": EntityStatus.DELETED.value}
        })
        if existing:
            return {
                "status": "duplicate",
                "message": f"Corrispettivo per {data['data']} già presente"
            }

        corr_doc = {
            "id": self._generate_id(),
            "data": data["data"],
            "totale": data["totale"],
            "totale_complessivo": data["totale"],
            "pagato_contanti": data.get("pagato_contanti", data["totale"]),
            "pagato_pos": data.get("pagato_pos", 0),
            "non_riscosso": data.get("non_riscosso", 0),
            "descrizione": data.get("descrizione", "Corrispettivo manuale"),
            "source": "manual",

            "status": CorrispettivoStatus.IMPORTED.value,
            "entity_status": EntityStatus.ACTIVE.value,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "prima_nota_id": None
        }

        await self.corrispettivi.insert_one(corr_doc.copy())

        # Propaga a Prima Nota
        prima_nota_id = await self._create_prima_nota_entry(corr_doc)
        if prima_nota_id:
            await self.corrispettivi.update_one(
                {"id": corr_doc["id"]},
                {"$set": {"prima_nota_id": prima_nota_id}}
            )

        return {
            "status": "created",
            "corrispettivo_id": corr_doc["id"],
            "prima_nota_id": prima_nota_id,
            "message": "Corrispettivo creato"
        }

    # ==================== READ ====================

    async def get_all(self, filters: Dict[str, Any] = None,
                      skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """Recupera tutti i corrispettivi."""
        query = {"entity_status": {"$ne": EntityStatus.DELETED.value}}

        if filters:
            if filters.get("year"):
                query["data"] = {"$regex": f"^{filters['year']}"}
            if filters.get("month"):
                year = filters.get("year", datetime.now().year)
                month = str(filters["month"]).zfill(2)
                query["data"] = {"$regex": f"^{year}-{month}"}

        cursor = self.corrispettivi.find(query, {"_id": 0}).skip(skip).limit(limit).sort("data", -1)
        return await cursor.to_list(limit)

    async def get_by_id(self, corr_id: str) -> Optional[Dict[str, Any]]:
        """Recupera un corrispettivo per ID."""
        return await self.corrispettivi.find_one(
            {"id": corr_id, "entity_status": {"$ne": EntityStatus.DELETED.value}},
            {"_id": 0}
        )

    async def get_by_date(self, data: str) -> Optional[Dict[str, Any]]:
        """Recupera un corrispettivo per data."""
        return await self.corrispettivi.find_one(
            {"data": data, "entity_status": {"$ne": EntityStatus.DELETED.value}},
            {"_id": 0}
        )

    # ==================== UPDATE ====================

    async def update(self, corr_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Aggiorna un corrispettivo con validazione."""
        corr = await self.get_by_id(corr_id)
        if not corr:
            return {"status": "error", "message": "Corrispettivo non trovato"}

        # Valida modifica
        validation = BusinessRules.can_modify_corrispettivo(corr)
        if not validation.is_valid:
            return {
                "status": "error",
                "message": "Modifica non consentita",
                "errors": validation.errors
            }

        # Applica modifica
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        await self.corrispettivi.update_one(
            {"id": corr_id},
            {"$set": update_data}
        )

        # Se cambiato totale, aggiorna Prima Nota
        if "totale" in update_data and corr.get("prima_nota_id"):
            await self._update_prima_nota_entry(corr["prima_nota_id"], update_data)

        return {"status": "success", "message": "Corrispettivo aggiornato"}

    # ==================== DELETE ====================

    async def delete(self, corr_id: str, force: bool = False) -> Dict[str, Any]:
        """Elimina (soft-delete) un corrispettivo."""
        corr = await self.get_by_id(corr_id)
        if not corr:
            return {"status": "error", "message": "Corrispettivo non trovato"}

        # Valida eliminazione
        validation = BusinessRules.can_delete_corrispettivo(corr)
        if not validation.is_valid:
            return {
                "status": "error",
                "message": "Eliminazione non consentita",
                "errors": validation.errors
            }

        # Soft-delete
        await self.corrispettivi.update_one(
            {"id": corr_id},
            {"$set": {
                "entity_status": EntityStatus.DELETED.value,
                "deleted_at": datetime.now(timezone.utc).isoformat()
            }}
        )

        # Annulla movimento Prima Nota collegato
        if corr.get("prima_nota_id"):
            await self.cash_movements.update_one(
                {"id": corr["prima_nota_id"]},
                {"$set": {"status": "cancelled"}}
            )

        return {"status": "success", "message": "Corrispettivo eliminato"}

    # ==================== HELPERS ====================

    @staticmethod
    def _number(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    async def _resolve_effective_date(self, parsed: Dict[str, Any]) -> None:
        """Attribuisce al giorno precedente una chiusura post-mezzanotte.

        La correzione si applica soltanto prima delle 04:00, con importi o
        documenti reali, e soltanto se il giorno precedente non e' gia'
        valorizzato per lo stesso registratore. La data XML non viene persa.
        """
        raw = str(parsed.get("data_ora_rilevazione") or "")
        if not raw or not (self._number(parsed.get("totale")) > 0
                           or int(parsed.get("numero_documenti", 0) or 0) > 0):
            return
        try:
            detected = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return
        if detected.hour >= 4:
            return

        original_date = str(parsed.get("data") or detected.date().isoformat())[:10]
        previous_date = (detected.date() - timedelta(days=1)).isoformat()
        query = {
            "data": previous_date,
            "entity_status": {"$ne": EntityStatus.DELETED.value},
            # I residui archiviati restano nel registro Drive/Sheets per audit, ma non sono
            # una chiusura attiva. Se li consideriamo "giorno valorizzato"
            # impediscono alla chiusura post-mezzanotte di tornare al giorno
            # corretto (caso reale XML 04/04/2026 attribuito al 03/04).
            "status": {"$nin": ["deleted", "archived", "archiviata"]},
        }
        if parsed.get("id_dispositivo"):
            query["id_dispositivo"] = parsed["id_dispositivo"]
        previous = await self.corrispettivi.find_one(query)
        previous_valued = bool(previous and (
            self._number(previous.get("totale")) > 0
            or int(previous.get("numero_documenti", 0) or 0) > 0
        ))
        if previous_valued:
            return

        parsed["data_originale_xml"] = original_date
        parsed["data"] = previous_date
        parsed["chiusura_post_mezzanotte"] = True

    @staticmethod
    def _xml_component(parsed: Dict[str, Any], filename: str,
                       content_hash: str) -> Dict[str, Any]:
        return {
            "content_hash": content_hash,
            "filename": filename,
            "data_effettiva": parsed.get("data"),
            "data_rilevazione_xml": parsed.get("data_originale_xml", parsed.get("data")),
            "data_ora_rilevazione": parsed.get("data_ora_rilevazione", ""),
            "data_ora_trasmissione": parsed.get("data_ora_trasmissione", ""),
            "progressivo": parsed.get("progressivo", ""),
            "totale": round(float(parsed.get("totale", 0) or 0), 2),
            "pagato_contanti": round(float(parsed.get("pagato_contanti", 0) or 0), 2),
            "pagato_pos": round(float(parsed.get("pagato_pos", 0) or 0), 2),
            "non_riscosso": round(float(parsed.get("non_riscosso", 0) or 0), 2),
            "totale_iva": round(float(parsed.get("totale_iva", 0) or 0), 2),
            "imponibile": round(float(parsed.get("imponibile", 0) or 0), 2),
            "numero_documenti": int(parsed.get("numero_documenti", 0) or 0),
            "riepilogo_iva": parsed.get("riepilogo_iva", []),
            "chiusura_post_mezzanotte": bool(parsed.get("chiusura_post_mezzanotte")),
        }

    @classmethod
    def _aggregate_riepilogo_iva(cls, components: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[tuple, Dict[str, Any]] = {}
        for component in components:
            for row in component.get("riepilogo_iva", []) or []:
                key = (str(row.get("aliquota_iva", "")), str(row.get("natura", "")))
                target = grouped.setdefault(key, {
                    "aliquota_iva": key[0], "natura": key[1],
                    "imposta": 0.0, "ammontare": 0.0,
                    "importo_parziale": 0.0, "importo_lordo": 0.0,
                })
                for field in ("imposta", "ammontare", "importo_parziale", "importo_lordo"):
                    target[field] += cls._number(row.get(field))
        for target in grouped.values():
            for field in ("imposta", "ammontare", "importo_parziale", "importo_lordo"):
                target[field] = round(target[field], 2)
        return list(grouped.values())

    async def _merge_distinct_xml(
        self, existing: Dict[str, Any], parsed: Dict[str, Any], filename: str,
        content_hash: str, *, applica_filtro_anno: bool,
    ) -> Dict[str, Any]:
        """Somma chiusure XML distinte della stessa data/registratore.

        Gli hash esatti sono intercettati prima di questo metodo. Qui ogni
        componente conserva provenienza e importi, mentre la riga giornaliera
        e le scritture contabili vengono ricalcolate in modo idempotente.
        """
        components = list(existing.get("chiusure_xml") or [])
        if not components:
            legacy = {
                "data": existing.get("data"),
                "data_originale_xml": existing.get("data_rilevazione_xml", existing.get("data")),
                "data_ora_rilevazione": existing.get("data_ora_rilevazione", ""),
                "data_ora_trasmissione": existing.get("data_ora_trasmissione", ""),
                "progressivo": existing.get("progressivo", ""),
                "totale": existing.get("totale", 0),
                "pagato_contanti": existing.get("pagato_contanti", 0),
                "pagato_pos": existing.get("pagato_pos", 0) or existing.get("pagato_elettronico", 0),
                "non_riscosso": existing.get("non_riscosso", 0),
                "totale_iva": existing.get("totale_iva", 0),
                "imponibile": existing.get("imponibile", existing.get("totale_imponibile", 0)),
                "numero_documenti": existing.get("numero_documenti", 0),
                "riepilogo_iva": existing.get("riepilogo_iva", []),
                "chiusura_post_mezzanotte": existing.get("chiusura_post_mezzanotte", False),
            }
            components.append(self._xml_component(
                legacy, existing.get("filename", "fonte_precedente.xml"),
                existing.get("content_hash", "legacy:" + str(existing.get("id", ""))),
            ))
        components.append(self._xml_component(parsed, filename, content_hash))

        def summed(field: str) -> float:
            return round(sum(self._number(c.get(field)) for c in components), 2)

        pos = summed("pagato_pos")
        source_hashes = list(dict.fromkeys(
            [h for h in (existing.get("source_hashes") or [existing.get("content_hash")]) if h]
            + [content_hash]
        ))
        source_files = list(dict.fromkeys(
            [f for f in (existing.get("source_files") or [existing.get("filename")]) if f]
            + [filename]
        ))
        canonical = {
            "source_hashes": source_hashes,
            "source_files": source_files,
            "chiusure_xml": components,
            "chiusure_sommate": len(components),
            "totale": summed("totale"),
            "totale_complessivo": summed("totale"),
            "totale_xml": summed("totale"),
            "pagato_contanti": summed("pagato_contanti"),
            "pagato_pos": pos,
            "pagato_elettronico": pos,
            "non_riscosso": summed("non_riscosso"),
            "totale_iva": summed("totale_iva"),
            "imponibile": summed("imponibile"),
            "totale_imponibile": summed("imponibile"),
            "numero_documenti": int(sum(int(c.get("numero_documenti", 0) or 0) for c in components)),
            "riepilogo_iva": self._aggregate_riepilogo_iva(components),
            "progressivi_xml": [c.get("progressivo") for c in components if c.get("progressivo")],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if pos > 0:
            from app.utils.pos_accredito import data_accredito_prevista_str
            prevista = data_accredito_prevista_str(existing.get("data", parsed.get("data")))
            if prevista:
                canonical["data_prevista_accredito"] = prevista
                canonical["stato_accredito"] = "in_attesa_accredito"

        await self.corrispettivi.update_one({"id": existing.get("id")}, {"$set": canonical})
        merged = dict(existing)
        merged.update(canonical)

        archived = (merged.get("status") == "archiviata"
                    or merged.get("stato_import") == "archivio_storico")
        prima_nota_id = None
        if not archived:
            prima_nota_id = await self._create_prima_nota_entry(merged)
            if prima_nota_id:
                await self.corrispettivi.update_one(
                    {"id": existing.get("id")}, {"$set": {"prima_nota_id": prima_nota_id}},
                )

            try:
                from app.services.event_bus import propagate_event, EventTypes
                await propagate_event(EventTypes.CORRISPETTIVI_IMPORTATI, {
                    "corrispettivi": [merged], "data": merged.get("data"),
                    "totale": merged.get("totale"), "id": merged.get("id"),
                }, self.db, source_module="corrispettivi_service")
            except Exception as exc:
                logger.debug("Corrispettivi aggregati - Event Bus: %s", exc)

        return {
            "status": "aggregated",
            "corrispettivo_id": str(existing.get("id")),
            "data": merged.get("data"),
            "totale": merged.get("totale"),
            "chiusure_sommate": len(components),
            "prima_nota_id": prima_nota_id,
            "message": "Chiusura XML distinta sommata al corrispettivo giornaliero",
        }

    def _parse_corrispettivo_xml(self, xml_content: bytes) -> Dict[str, Any]:
        """Adatta il parser COR10 canonico allo schema del servizio.

        Il vecchio parser locale applicava il namespace del solo elemento
        radice anche ai figli non qualificati dei file AdE, perdendo data,
        matricola e importi. Tutti i canali usano ora la stessa lettura.
        """
        from app.parsers.corrispettivi_parser import parse_corrispettivo_xml

        testo = None
        for encoding in ("utf-8-sig", "utf-8", "iso-8859-1", "cp1252"):
            try:
                testo = xml_content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if testo is None:
            raise ValueError("Codifica XML non riconosciuta")

        parsed = parse_corrispettivo_xml(testo)
        if parsed.get("error"):
            raise ValueError(parsed["error"])

        totale = float(parsed.get("totale_corrispettivi", parsed.get("totale", 0)) or 0)
        totale_iva = float(parsed.get("totale_iva", 0) or 0)
        return {
            "data": parsed.get("data"),
            "data_ora_rilevazione": parsed.get("data_ora_rilevazione", ""),
            "data_ora_trasmissione": parsed.get("data_ora_trasmissione", ""),
            "totale": totale,
            "pagato_contanti": float(parsed.get("pagato_contanti", 0) or 0),
            "pagato_pos": float(parsed.get("pagato_elettronico", 0) or 0),
            "non_riscosso": float(parsed.get("pagato_non_riscosso", 0) or 0),
            "totale_iva": totale_iva,
            "imponibile": float(parsed.get("totale_imponibile", totale - totale_iva) or 0),
            "riepilogo_iva": parsed.get("riepilogo_iva", []),
            "progressivo": parsed.get("numero_documento", ""),
            "numero_documenti": int(parsed.get("numero_documenti", 0) or 0),
            "id_dispositivo": parsed.get("matricola_rt", ""),
            "_periodo_inattivo": bool(parsed.get("periodo_inattivo")),
        }

    async def _repair_duplicate_accounting(
        self,
        existing: Dict[str, Any],
        parsed: Dict[str, Any],
        applica_filtro_anno: bool,
        *,
        exact_source: bool,
    ) -> bool:
        """Un retry non duplica il corrispettivo ma ripara i collegamenti.

        Se l'hash e' identico, l'XML e' la stessa fonte e puo' completare i
        campi canonici mancanti. Un duplicato solo per data/matricola non
        sovrascrive invece gli importi gia' registrati. In entrambi i casi il
        writer idempotente ricrea esclusivamente le scritture di Prima Nota
        assenti, senza cancellare quelle esistenti.
        """
        if existing.get("status") == "archiviata" or existing.get("stato_import") == "archivio_storico":
            return False
        data = str(parsed.get("data") or existing.get("data") or "")[:10]
        if applica_filtro_anno and data[:4].isdigit():
            from app.services.config_import import get_anno_importazione_attivo
            if int(data[:4]) != await get_anno_importazione_attivo(self.db):
                return False

        corr = dict(existing)
        # Un retry di una delle fonti di un aggregato non deve mai riportare
        # il totale giornaliero al valore della singola chiusura.
        if exact_source and len(existing.get("chiusure_xml") or []) <= 1:
            canonical = {
                "data": parsed.get("data"),
                "data_rilevazione_xml": parsed.get(
                    "data_originale_xml", parsed.get("data")
                ),
                "chiusura_post_mezzanotte": bool(
                    parsed.get("chiusura_post_mezzanotte")
                ),
                "progressivo": parsed.get("progressivo", ""),
                "id_dispositivo": parsed.get("id_dispositivo", ""),
                "matricola_rt": parsed.get("id_dispositivo", ""),
                "totale": parsed.get("totale", 0),
                "totale_complessivo": parsed.get("totale", 0),
                "pagato_contanti": parsed.get("pagato_contanti", 0),
                "pagato_pos": parsed.get("pagato_pos", 0),
                "pagato_elettronico": parsed.get("pagato_pos", 0),
                "non_riscosso": parsed.get("non_riscosso", 0),
                "totale_iva": parsed.get("totale_iva", 0),
                "imponibile": parsed.get("imponibile", 0),
                "riepilogo_iva": parsed.get("riepilogo_iva", []),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            corr.update(canonical)
            await self.corrispettivi.update_one(
                {"id": existing.get("id")}, {"$set": canonical},
            )
        corr.setdefault("matricola_rt", corr.get("id_dispositivo", ""))
        corr.setdefault("pagato_elettronico", corr.get("pagato_pos", 0))

        # Cancella e rigenera perche' un retry puo' aver corretto data,
        # quota POS o totale aggregato; il writer "se assente" da solo non
        # aggiornerebbe una scrittura storica gia' presente.
        prima_nota_id = await self._create_prima_nota_entry(corr)
        if prima_nota_id and not existing.get("prima_nota_id"):
            await self.corrispettivi.update_one(
                {"id": existing.get("id")},
                {"$set": {"prima_nota_id": prima_nota_id}},
            )
        return bool(prima_nota_id)

    async def _create_prima_nota_entry(self, corr: Dict[str, Any]) -> Optional[str]:
        """
        Crea i movimenti Prima Nota per il corrispettivo.

        Bug scoperto il 14/07/2026 mentre si estendeva il filtro anno
        all'ingest Drive dei corrispettivi: questa era una TERZA
        implementazione parallela della stessa regola contabile già
        unificata altrove in app/routers/invoices/corrispettivi_helpers.py
        (_create_prima_nota_movements, usata dal caricamento diretto e
        dallo scheduler prima_nota_module/sync.py). Leggeva
        `pagato_pos` invece di `pagato_elettronico` (il nome scritto dal
        parser XML ufficiale, confermato dall'utente) e — più grave — non
        creava MAI la riga entrata in prima_nota_banca: i corrispettivi
        importati da questo canale (Drive corrispettivi, e create_manual
        che riusa questo stesso metodo) non alimentavano mai Coerenza POS,
        esattamente come il "Bug A" della quick-form POS già corretto in
        Prima Nota. Ora delega alla stessa implementazione condivisa.
        """
        try:
            from app.routers.invoices.corrispettivi_helpers import (
                _create_prima_nota_movements, _delete_prima_nota_for_corrispettivo,
            )
            corr_id = corr.get("id", "")
            data = corr.get("data", "")
            # Pulisce eventuali movimenti precedenti per lo stesso corrispettivo
            # (stessa idempotenza già garantita dal vecchio dedup su
            # corrispettivo_id) prima di rigenerarli con la regola corretta.
            await _delete_prima_nota_for_corrispettivo(self.db, corr_id, data)
            risultato = await _create_prima_nota_movements(self.db, corr)
            return risultato.get("prima_nota_cassa_id")
        except Exception as e:
            logger.error(f"Error creating prima nota entry: {e}")
            return None


def get_corrispettivi_service(db=None) -> CorrispettiviService:
    """Factory function per CorrispettiviService."""
    return CorrispettiviService(db=db)
