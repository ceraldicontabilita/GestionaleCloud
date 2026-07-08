"""
CASCADE OPERATIONS - Gestione relazioni tra entità
===================================================

Questo modulo gestisce le operazioni a cascata tra entità correlate:
- CASCADE DELETE: eliminazione di dati correlati
- CASCADE UPDATE: aggiornamento di dati correlati
- DOPPIA CONFERMA: per operazioni su dati registrati

SCHEMA RELAZIONI:
-----------------
FATTURA (invoices)
    ├── dettaglio_righe_fatture (righe fattura)
    ├── prima_nota_banca / prima_nota_cassa (movimento contabile)
    ├── scadenziario_fornitori (scadenza pagamento)
    ├── warehouse_movements (movimenti magazzino)
    ├── magazzino_doppia_verita (giacenze)
    └── riconciliazioni (match bancari)

FORNITORE (suppliers/fornitori)
    ├── invoices (fatture del fornitore)
    ├── warehouse_inventory (prodotti del fornitore)
    └── magazzino_doppia_verita (giacenze prodotti)

ASSEGNO (assegni)
    └── invoices (fattura collegata)
"""

import logging
from typing import Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class CascadeOperations:
    """Gestisce le operazioni a cascata tra entità correlate."""
    
    # ==================== CASCADE DELETE ====================
    
    @staticmethod
    async def delete_fattura_cascade(db, fattura_id: str, hard_delete: bool = False) -> Dict[str, Any]:
        """
        Elimina una fattura e tutti i dati correlati.
        
        Args:
            db: Database connection
            fattura_id: ID della fattura da eliminare
            hard_delete: Se True elimina fisicamente, altrimenti soft-delete
            
        Returns:
            Riepilogo delle entità eliminate
        """
        risultato = {
            "fattura_id": fattura_id,
            "entita_eliminate": {},
            "errori": []
        }
        
        now = datetime.now(timezone.utc).isoformat()
        
        try:
            # 1. Elimina righe dettaglio fattura
            if hard_delete:
                r = await db["dettaglio_righe_fatture"].delete_many({"fattura_id": fattura_id})
            else:
                r = await db["dettaglio_righe_fatture"].update_many(
                    {"fattura_id": fattura_id},
                    {"$set": {"deleted": True, "deleted_at": now}}
                )
            risultato["entita_eliminate"]["righe_fattura"] = r.deleted_count if hard_delete else r.modified_count
            
            # 2. Elimina/archivia Prima Nota Banca
            # NB: "status": "deleted" (non solo "deleted": True) è il campo
            # che TUTTE le query di riepilogo prima nota controllano davvero
            # (cassa.py, banca.py, finanziaria.py, sync.py, bilancio.py — vedi
            # "status": {"$nin": ["deleted","archived"]}); senza impostarlo
            # anche qui, un movimento sganciato da una fattura cancellata
            # restava "vivo" in Prima Nota, Finanziaria e Bilancio nonostante
            # la fattura fosse sparita. "deleted": True resta per compatibilità
            # con eventuale codice legacy, ma non è letto da nessuna query.
            if hard_delete:
                r = await db["prima_nota_banca"].delete_many({"fattura_id": fattura_id})
            else:
                r = await db["prima_nota_banca"].update_many(
                    {"fattura_id": fattura_id},
                    {"$set": {"deleted": True, "status": "deleted", "deleted_at": now, "note": f"Eliminato per rimozione fattura {fattura_id}"}}
                )
            risultato["entita_eliminate"]["prima_nota_banca"] = r.deleted_count if hard_delete else r.modified_count

            # 3. Elimina/archivia Prima Nota Cassa (stesso motivo del punto 2)
            if hard_delete:
                r = await db["prima_nota_cassa"].delete_many({"fattura_id": fattura_id})
            else:
                r = await db["prima_nota_cassa"].update_many(
                    {"fattura_id": fattura_id},
                    {"$set": {"deleted": True, "status": "deleted", "deleted_at": now, "note": f"Eliminato per rimozione fattura {fattura_id}"}}
                )
            risultato["entita_eliminate"]["prima_nota_cassa"] = r.deleted_count if hard_delete else r.modified_count
            
            # 4. Elimina scadenze
            if hard_delete:
                r = await db["scadenziario_fornitori"].delete_many({"fattura_id": fattura_id})
            else:
                r = await db["scadenziario_fornitori"].update_many(
                    {"fattura_id": fattura_id},
                    {"$set": {"deleted": True, "deleted_at": now, "stato": "annullato"}}
                )
            risultato["entita_eliminate"]["scadenze"] = r.deleted_count if hard_delete else r.modified_count
            
            # 5. Annulla movimenti magazzino (NON elimina, segna come annullati)
            r = await db["warehouse_movements"].update_many(
                {"fattura_id": fattura_id},
                {"$set": {"annullato": True, "annullato_at": now, "note_annullamento": f"Fattura {fattura_id} eliminata"}}
            )
            risultato["entita_eliminate"]["movimenti_magazzino"] = r.modified_count
            
            # 6. Rimuovi riconciliazioni
            r = await db["riconciliazioni"].delete_many({"scadenza_id": {"$regex": fattura_id}})
            risultato["entita_eliminate"]["riconciliazioni"] = r.deleted_count
            
            # 7. Sgancia assegni collegati (non elimina, solo sgancia)
            r = await db["assegni"].update_many(
                {"fattura_collegata": fattura_id},
                {"$unset": {"fattura_collegata": "", "numero_fattura": "", "data_fattura": ""}}
            )
            risultato["entita_eliminate"]["assegni_sganciati"] = r.modified_count

            # 7-bis. Pulisci sistema relazionale (partite aperte, alert, match)
            # Fondamentale: senza questa pulizia i contatori Dashboard Relazionale
            # restano "gonfi" con partite/alert che puntano a fatture inesistenti.
            try:
                # Partite aperte collegate: soft-delete se soft, hard se hard
                if hard_delete:
                    r_pa = await db["partite_aperte"].delete_many({
                        "tipo": "fattura_fornitore",
                        "documento_id": fattura_id,
                    })
                    risultato["entita_eliminate"]["partite_aperte"] = r_pa.deleted_count
                else:
                    r_pa = await db["partite_aperte"].update_many(
                        {
                            "tipo": "fattura_fornitore",
                            "documento_id": fattura_id,
                            "stato": {"$in": ["aperta", "parziale"]},
                        },
                        {"$set": {"stato": "annullata", "annullata_at": now,
                                  "motivo_annullamento": f"Fattura {fattura_id} eliminata"}}
                    )
                    risultato["entita_eliminate"]["partite_aperte"] = r_pa.modified_count

                # Alert aperti sulla fattura: sempre risolti (anche in soft delete)
                r_al = await db["alerts"].update_many(
                    {
                        "entita_id": fattura_id,
                        "stato": "aperto",
                    },
                    {"$set": {
                        "stato": "risolto",
                        "risolto": True,
                        "resolved_at": now,
                        "resolved_by": "cascade_delete",
                        "note_risoluzione": f"Fattura {fattura_id} eliminata",
                    }}
                )
                risultato["entita_eliminate"]["alerts_risolti"] = r_al.modified_count

                # Match riconciliazione: marcati come respinti
                r_rm = await db["riconciliazioni_match"].update_many(
                    {
                        "$or": [
                            {"partita_id": {"$regex": fattura_id}},
                            {"documento_id": fattura_id},
                        ],
                        "stato": {"$in": ["confermato", "candidato"]},
                    },
                    {"$set": {"stato": "respinto", "respinto_at": now,
                              "motivo": "fattura eliminata"}}
                )
                risultato["entita_eliminate"]["match_respinti"] = r_rm.modified_count
            except Exception as e_rel:
                logger.exception(f"Errore pulizia sistema relazionale per fattura {fattura_id}")
                risultato["errori"].append(f"Pulizia relazionale: {e_rel}")

            # 8. Infine elimina/archivia la fattura stessa
            if hard_delete:
                # Elimina da entrambe le collezioni (invoices e fatture_ricevute)
                r1 = await db["invoices"].delete_one({"id": fattura_id})
                r2 = await db["invoices"].delete_one({"id": fattura_id})
                risultato["entita_eliminate"]["fattura"] = r1.deleted_count + r2.deleted_count
            else:
                r1 = await db["invoices"].update_one(
                    {"id": fattura_id},
                    {"$set": {"status": "deleted", "entity_status": "deleted", "deleted_at": now}}
                )
                r2 = await db["invoices"].update_one(
                    {"id": fattura_id},
                    {"$set": {"status": "deleted", "entity_status": "deleted", "deleted_at": now}}
                )
                risultato["entita_eliminate"]["fattura"] = r1.modified_count + r2.modified_count
            
            logger.info(f"CASCADE DELETE fattura {fattura_id}: {risultato['entita_eliminate']}")
            
        except Exception as e:
            logger.error(f"Errore CASCADE DELETE fattura {fattura_id}: {e}")
            risultato["errori"].append(str(e))
        
        return risultato
    
    @staticmethod
    async def delete_fornitore_cascade(db, fornitore_id: str, fornitore_piva: str) -> Dict[str, Any]:
        """
        Elimina un fornitore e tutti i suoi prodotti dal magazzino.
        Le fatture NON vengono eliminate, solo sganciate.
        """
        risultato = {
            "fornitore_id": fornitore_id,
            "entita_eliminate": {},
            "errori": []
        }
        
        now = datetime.now(timezone.utc).isoformat()
        
        try:
            # 1. Elimina prodotti dal magazzino
            r = await db["warehouse_inventory"].delete_many({
                "$or": [
                    {"supplier_id": fornitore_id},
                    {"fornitore_piva": fornitore_piva},
                    {"supplier_piva": fornitore_piva}
                ]
            })
            risultato["entita_eliminate"]["prodotti_inventory"] = r.deleted_count
            
            # 2. Elimina da magazzino doppia verità
            r = await db["magazzino_doppia_verita"].delete_many({
                "$or": [
                    {"fornitore_id": fornitore_id},
                    {"fornitore_piva": fornitore_piva}
                ]
            })
            risultato["entita_eliminate"]["prodotti_dv"] = r.deleted_count
            
            # 3. Elimina da warehouse_stocks
            r = await db["warehouse_stocks"].delete_many({
                "$or": [
                    {"supplier_id": fornitore_id},
                    {"fornitore_piva": fornitore_piva},
                    {"supplier_piva": fornitore_piva}
                ]
            })
            risultato["entita_eliminate"]["warehouse_stocks"] = r.deleted_count
            
            # 4. Segna fatture come "fornitore eliminato" (NON elimina)
            r = await db["invoices"].update_many(
                {"supplier_vat": fornitore_piva},
                {"$set": {"fornitore_eliminato": True, "fornitore_eliminato_at": now}}
            )
            risultato["entita_eliminate"]["fatture_segnate"] = r.modified_count
            
            # 5. Elimina il fornitore
            r1 = await db["fornitori"].delete_one({"id": fornitore_id})
            r2 = await db["fornitori"].delete_one({"id": fornitore_id})
            risultato["entita_eliminate"]["fornitore"] = r1.deleted_count + r2.deleted_count
            
            logger.info(f"CASCADE DELETE fornitore {fornitore_id}: {risultato['entita_eliminate']}")
            
        except Exception as e:
            logger.error(f"Errore CASCADE DELETE fornitore {fornitore_id}: {e}")
            risultato["errori"].append(str(e))
        
        return risultato
    
    # ==================== CASCADE UPDATE ====================
    
    @staticmethod
    async def update_fattura_cascade(db, fattura_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aggiorna una fattura e propaga le modifiche alle entità correlate.
        
        Campi che propagano:
        - importo_totale → prima_nota, scadenze
        - data_documento → prima_nota, scadenze
        - fornitore_* → prima_nota, scadenze
        """
        risultato = {
            "fattura_id": fattura_id,
            "entita_aggiornate": {},
            "errori": []
        }
        
        now = datetime.now(timezone.utc).isoformat()
        
        try:
            # 1. Aggiorna fattura
            await db["invoices"].update_one({"id": fattura_id}, {"$set": {**updates, "updated_at": now}})
            await db["invoices"].update_one({"id": fattura_id}, {"$set": {**updates, "updated_at": now}})
            risultato["entita_aggiornate"]["fattura"] = 1
            
            # 2. Propaga importo a Prima Nota
            if "importo_totale" in updates or "total_amount" in updates:
                importo = updates.get("importo_totale") or updates.get("total_amount")
                r = await db["prima_nota_banca"].update_many(
                    {"fattura_id": fattura_id},
                    {"$set": {"importo": importo, "updated_at": now}}
                )
                risultato["entita_aggiornate"]["prima_nota_banca"] = r.modified_count
                
                r = await db["prima_nota_cassa"].update_many(
                    {"fattura_id": fattura_id},
                    {"$set": {"importo": importo, "updated_at": now}}
                )
                risultato["entita_aggiornate"]["prima_nota_cassa"] = r.modified_count
            
            # 3. Propaga importo a Scadenze
            if "importo_totale" in updates or "total_amount" in updates:
                importo = updates.get("importo_totale") or updates.get("total_amount")
                r = await db["scadenziario_fornitori"].update_many(
                    {"fattura_id": fattura_id},
                    {"$set": {"importo_totale": importo, "updated_at": now}}
                )
                risultato["entita_aggiornate"]["scadenze"] = r.modified_count
            
            # 4. Propaga data a Prima Nota
            if "data_documento" in updates or "invoice_date" in updates:
                data = updates.get("data_documento") or updates.get("invoice_date")
                r = await db["prima_nota_banca"].update_many(
                    {"fattura_id": fattura_id},
                    {"$set": {"data": data, "updated_at": now}}
                )
                risultato["entita_aggiornate"]["prima_nota_banca_data"] = r.modified_count
            
            # 5. Propaga fornitore a Prima Nota
            if "fornitore_ragione_sociale" in updates or "supplier_name" in updates:
                nome = updates.get("fornitore_ragione_sociale") or updates.get("supplier_name")
                r = await db["prima_nota_banca"].update_many(
                    {"fattura_id": fattura_id},
                    {"$set": {"fornitore_nome": nome, "updated_at": now}}
                )
                risultato["entita_aggiornate"]["prima_nota_fornitore"] = r.modified_count
                
                r = await db["scadenziario_fornitori"].update_many(
                    {"fattura_id": fattura_id},
                    {"$set": {"fornitore_nome": nome, "updated_at": now}}
                )
                risultato["entita_aggiornate"]["scadenze_fornitore"] = r.modified_count
            
            logger.info(f"CASCADE UPDATE fattura {fattura_id}: {risultato['entita_aggiornate']}")
            
        except Exception as e:
            logger.error(f"Errore CASCADE UPDATE fattura {fattura_id}: {e}")
            risultato["errori"].append(str(e))
        
        return risultato
    
    # ==================== VERIFICA STATO ====================
    
    @staticmethod
    async def is_fattura_registrata(db, fattura_id: str) -> Dict[str, Any]:
        """
        Verifica se una fattura ha operazioni registrate che richiedono doppia conferma.
        
        Returns:
            {
                "registrata": bool,
                "dettagli": {
                    "ha_prima_nota": bool,
                    "ha_scadenze": bool,
                    "ha_movimenti_magazzino": bool,
                    "ha_pagamenti": bool,
                    "ha_riconciliazioni": bool
                }
            }
        """
        dettagli = {
            "ha_prima_nota": False,
            "ha_scadenze": False,
            "ha_movimenti_magazzino": False,
            "ha_pagamenti": False,
            "ha_riconciliazioni": False
        }
        
        # Check Prima Nota
        pn_banca = await db["prima_nota_banca"].find_one({"fattura_id": fattura_id, "deleted": {"$ne": True}})
        pn_cassa = await db["prima_nota_cassa"].find_one({"fattura_id": fattura_id, "deleted": {"$ne": True}})
        dettagli["ha_prima_nota"] = pn_banca is not None or pn_cassa is not None
        
        # Check Scadenze
        scadenza = await db["scadenziario_fornitori"].find_one({"fattura_id": fattura_id, "deleted": {"$ne": True}})
        dettagli["ha_scadenze"] = scadenza is not None
        
        # Check Movimenti Magazzino
        movimento = await db["warehouse_movements"].find_one({"fattura_id": fattura_id, "annullato": {"$ne": True}})
        dettagli["ha_movimenti_magazzino"] = movimento is not None
        
        # Check Pagamenti
        fattura = await db["invoices"].find_one({"id": fattura_id}, {"pagato": 1, "payment_status": 1})
        if fattura:
            dettagli["ha_pagamenti"] = fattura.get("pagato") == True or fattura.get("payment_status") == "paid"
        
        # Check Riconciliazioni
        ric = await db["riconciliazioni"].find_one({"$or": [{"fattura_id": fattura_id}, {"scadenza_id": {"$regex": fattura_id}}]})
        dettagli["ha_riconciliazioni"] = ric is not None
        
        registrata = any(dettagli.values())
        
        return {
            "registrata": registrata,
            "dettagli": dettagli
        }
    
    @staticmethod
    async def get_entita_correlate(db, fattura_id: str) -> Dict[str, Any]:
        """
        Restituisce tutte le entità correlate a una fattura.
        Utile per mostrare all'utente cosa verrà eliminato/modificato.
        """
        correlate = {
            "righe_dettaglio": await db["dettaglio_righe_fatture"].count_documents({"fattura_id": fattura_id}),
            "prima_nota_banca": await db["prima_nota_banca"].count_documents({"fattura_id": fattura_id}),
            "prima_nota_cassa": await db["prima_nota_cassa"].count_documents({"fattura_id": fattura_id}),
            "scadenze": await db["scadenziario_fornitori"].count_documents({"fattura_id": fattura_id}),
            "movimenti_magazzino": await db["warehouse_movements"].count_documents({"fattura_id": fattura_id}),
            "riconciliazioni": await db["riconciliazioni"].count_documents({"scadenza_id": {"$regex": fattura_id}}),
            "assegni_collegati": await db["assegni"].count_documents({"fattura_collegata": fattura_id})
        }
        
        correlate["totale_entita"] = sum(correlate.values())
        
        return correlate
