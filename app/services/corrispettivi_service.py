"""
CORRISPETTIVI SERVICE - Con Controlli di Sicurezza
==================================================

Servizio unificato per la gestione corrispettivi con:
- Validazione business rules
- Controlli di sicurezza pre-operazione
- Propagazione automatica a Prima Nota Cassa
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import hashlib
import logging
import uuid
import defusedxml.ElementTree as ET  # sicurezza: blocca XXE/entity expansion su XML esterni

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
        self.db = db or Database.get_db()
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

        # 2. Check duplicato
        content_hash = hashlib.sha256(xml_content).hexdigest()
        existing = await self.corrispettivi.find_one({"content_hash": content_hash})
        if existing:
            return {
                "status": "duplicate",
                "corrispettivo_id": str(existing.get("id")),
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
            return {
                "status": "duplicate",
                "corrispettivo_id": str(existing_date.get("id")),
                "message": f"Corrispettivo per {parsed['data']} già presente"
            }

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
            "data": parsed["data"],
            "progressivo": parsed.get("progressivo", ""),
            "id_dispositivo": parsed.get("id_dispositivo", ""),
            
            # Importi
            "totale": parsed["totale"],
            "totale_complessivo": parsed["totale"],
            "pagato_contanti": parsed.get("pagato_contanti", 0),
            "pagato_pos": parsed.get("pagato_pos", 0),
            "non_riscosso": parsed.get("non_riscosso", 0),
            
            # IVA
            "totale_iva": parsed.get("totale_iva", 0),
            "imponibile": parsed.get("imponibile", 0),
            "riepilogo_iva": parsed.get("riepilogo_iva", []),
            
            # Stati
            "status": CorrispettivoStatus.IMPORTED.value,
            "entity_status": EntityStatus.ACTIVE.value,
            
            # Metadata
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),

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
    
    def _parse_corrispettivo_xml(self, xml_content: bytes) -> Dict[str, Any]:
        """Parse XML corrispettivo formato RT."""
        root = ET.fromstring(xml_content)
        
        # Namespace handling
        ns = {'': root.tag.split('}')[0].strip('{') if '}' in root.tag else ''}
        
        def find_text(element, path, default=""):
            el = element.find(path, ns) if ns[''] else element.find(path)
            return el.text if el is not None and el.text else default
        
        # Estrai dati principali
        data = find_text(root, ".//DataOraRilevazione", "")[:10]
        if not data:
            data = find_text(root, ".//Data", datetime.now().strftime("%Y-%m-%d"))
        
        totale = float(find_text(root, ".//ImportoTotale", "0").replace(",", "."))
        if totale == 0:
            totale = float(find_text(root, ".//Totale", "0").replace(",", "."))
        
        # Estrai pagamenti
        pagato_contanti = 0
        pagato_pos = 0
        
        for pagamento in root.findall(".//Pagamento", ns) or root.findall(".//Pagamento"):
            tipo = find_text(pagamento, "Tipo", "").upper()
            importo = float(find_text(pagamento, "Importo", "0").replace(",", "."))
            
            if "CONTANTI" in tipo or "CASH" in tipo or tipo == "":
                pagato_contanti += importo
            elif "POS" in tipo or "CARTA" in tipo or "ELETTRONICO" in tipo:
                pagato_pos += importo
        
        # Se non ci sono pagamenti dettagliati, tutto contanti
        if pagato_contanti == 0 and pagato_pos == 0:
            pagato_contanti = totale
        
        # Estrai IVA
        riepilogo_iva = []
        totale_iva = 0
        
        for aliquota in root.findall(".//Aliquota", ns) or root.findall(".//AliquotaIVA", ns):
            perc = float(find_text(aliquota, "Percentuale", "22").replace(",", "."))
            impon = float(find_text(aliquota, "Imponibile", "0").replace(",", "."))
            imposta = float(find_text(aliquota, "Imposta", "0").replace(",", "."))
            
            riepilogo_iva.append({
                "aliquota": perc,
                "imponibile": impon,
                "imposta": imposta
            })
            totale_iva += imposta
        
        return {
            "data": data,
            "totale": totale,
            "pagato_contanti": pagato_contanti,
            "pagato_pos": pagato_pos,
            "non_riscosso": max(0, totale - pagato_contanti - pagato_pos),
            "totale_iva": totale_iva,
            "imponibile": totale - totale_iva,
            "riepilogo_iva": riepilogo_iva,
            "progressivo": find_text(root, ".//Progressivo", ""),
            "id_dispositivo": find_text(root, ".//IdDispositivo", "")
        }
    
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
