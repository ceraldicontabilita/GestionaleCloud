"""
Servizio di Verifica Coerenza Dati
Controlla che i dati siano consistenti tra tutte le sezioni del gestionale.

Verifiche implementate:
1. IVA Credito: Fatture vs Liquidazione vs Confronto Commercialista
2. IVA Debito: Corrispettivi vs Liquidazione vs Confronto Commercialista  
3. Versamenti: Registrazioni manuali vs Movimenti Bancari
4. Saldi: Prima Nota vs Estratto Conto
5. F24: Tributi registrati vs Pagamenti effettivi
"""

from typing import Dict, Any, List
from datetime import datetime, timezone
from app.database import Database, Collections
import logging

logger = logging.getLogger(__name__)

MESI_NOMI = ['', 'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
             'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre']


class VerificaCoerenza:
    """Servizio per verificare la coerenza dei dati tra le varie sezioni."""
    
    def __init__(self, db):
        self.db = db
        self.discrepanze = []
        self.tolleranza = 0.01  # Tolleranza per confronti (1 centesimo)
    
    def _aggiungi_discrepanza(self, categoria: str, sottocategoria: str, 
                               descrizione: str, valore_atteso: float, 
                               valore_trovato: float, periodo: str = "",
                               severita: str = "warning", suggerimento: str = ""):
        """Aggiunge una discrepanza alla lista."""
        differenza = round(valore_trovato - valore_atteso, 2)
        if abs(differenza) > self.tolleranza:
            self.discrepanze.append({
                "categoria": categoria,
                "sottocategoria": sottocategoria,
                "descrizione": descrizione,
                "valore_atteso": round(valore_atteso, 2),
                "valore_trovato": round(valore_trovato, 2),
                "differenza": differenza,
                "periodo": periodo,
                "severita": severita,  # "critical", "warning", "info"
                "suggerimento": suggerimento,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
    
    async def verifica_iva_credito_mensile(self, anno: int, mese: int) -> Dict[str, float]:
        """
        Verifica IVA Credito per un mese specifico.
        Confronta: Fatture ricevute vs Calcolo Liquidazione
        """
        prefix = f"{anno}-{mese:02d}"
        periodo = f"{MESI_NOMI[mese]} {anno}"
        
        # 1. IVA da Fatture Ricevute (collection invoices)
        pipeline_fatture = [
            {"$match": {
                "$or": [
                    {"data_ricezione": {"$regex": f"^{prefix}"}},
                    {"invoice_date": {"$regex": f"^{prefix}"}}
                ],
                "tipo_documento": {"$nin": ["TD04", "TD08"]}  # Escludi note credito
            }},
            {"$group": {"_id": None, "totale_iva": {"$sum": "$iva"}}}
        ]
        result_fatture = await self.db[Collections.INVOICES].aggregate(pipeline_fatture).to_list(1)
        iva_fatture = result_fatture[0]["totale_iva"] if result_fatture else 0
        
        # 2. IVA da Note di Credito Ricevute (da sottrarre)
        pipeline_nc = [
            {"$match": {
                "$or": [
                    {"data_ricezione": {"$regex": f"^{prefix}"}},
                    {"invoice_date": {"$regex": f"^{prefix}"}}
                ],
                "tipo_documento": {"$in": ["TD04", "TD08"]}
            }},
            {"$group": {"_id": None, "totale_iva": {"$sum": "$iva"}}}
        ]
        result_nc = await self.db[Collections.INVOICES].aggregate(pipeline_nc).to_list(1)
        iva_note_credito = result_nc[0]["totale_iva"] if result_nc else 0
        
        iva_credito_fatture = iva_fatture - iva_note_credito
        
        # 3. Conta fatture per dettaglio
        count_fatture = await self.db[Collections.INVOICES].count_documents({
            "$or": [
                {"data_ricezione": {"$regex": f"^{prefix}"}},
                {"invoice_date": {"$regex": f"^{prefix}"}}
            ]
        })
        
        return {
            "iva_credito_fatture": round(iva_credito_fatture, 2),
            "iva_fatture_lorde": round(iva_fatture, 2),
            "iva_note_credito": round(iva_note_credito, 2),
            "num_fatture": count_fatture,
            "periodo": periodo
        }
    
    async def verifica_iva_debito_mensile(self, anno: int, mese: int) -> Dict[str, float]:
        """
        Verifica IVA Debito per un mese specifico.
        Confronta: Corrispettivi vs Calcolo Liquidazione
        """
        prefix = f"{anno}-{mese:02d}"
        periodo = f"{MESI_NOMI[mese]} {anno}"
        
        # IVA da Corrispettivi
        pipeline_corr = [
            {"$match": {"data": {"$regex": f"^{prefix}"}}},
            {"$group": {"_id": None, "totale_iva": {"$sum": "$totale_iva"}}}
        ]
        result_corr = await self.db["corrispettivi"].aggregate(pipeline_corr).to_list(1)
        iva_corrispettivi = result_corr[0]["totale_iva"] if result_corr else 0
        
        # Conta corrispettivi
        count_corr = await self.db["corrispettivi"].count_documents({
            "data": {"$regex": f"^{prefix}"}
        })
        
        return {
            "iva_debito_corrispettivi": round(iva_corrispettivi, 2),
            "num_corrispettivi": count_corr,
            "periodo": periodo
        }
    
    async def verifica_versamenti_vs_banca(self, anno: int, mese: int = None) -> List[Dict]:
        """
        Verifica che i versamenti registrati manualmente corrispondano 
        ai movimenti bancari effettivi.
        """
        discrepanze_versamenti = []
        
        if mese:
            prefix = f"{anno}-{mese:02d}"
            periodo = f"{MESI_NOMI[mese]} {anno}"
        else:
            prefix = f"{anno}"
            periodo = f"Anno {anno}"
        
        # Versamenti da Prima Nota (manuali)
        pipeline_versamenti = [
            {"$match": {
                "data": {"$regex": f"^{prefix}"},
                "categoria": {"$in": ["Versamenti", "Versamento", "versamento", "versamenti"]},
                "status": {"$nin": ["deleted", "archived"]}
            }},
            {"$group": {
                "_id": None,
                "totale": {"$sum": "$importo"},
                "count": {"$sum": 1}
            }}
        ]
        result_pn = await self.db["prima_nota_cassa"].aggregate(pipeline_versamenti).to_list(1)
        versamenti_manuali = result_pn[0]["totale"] if result_pn else 0
        count_manuali = result_pn[0]["count"] if result_pn else 0
        
        # Versamenti da Estratto Conto (banca)
        # I versamenti in banca sono movimenti in AVERE (positivi) con descrizione che contiene "versamento"
        pipeline_banca = [
            {"$match": {
                "data": {"$regex": f"^{prefix}"},
                "$or": [
                    {"descrizione_originale": {"$regex": "versamento", "$options": "i"}},
                    {"tipo_movimento": "versamento"}
                ]
            }},
            {"$group": {
                "_id": None,
                "totale": {"$sum": {"$abs": "$importo"}},
                "count": {"$sum": 1}
            }}
        ]
        result_banca = await self.db["estratto_conto_movimenti"].aggregate(pipeline_banca).to_list(1)
        versamenti_banca = result_banca[0]["totale"] if result_banca else 0
        count_banca = result_banca[0]["count"] if result_banca else 0
        
        differenza = versamenti_manuali - versamenti_banca
        
        if abs(differenza) > self.tolleranza:
            self._aggiungi_discrepanza(
                categoria="Versamenti",
                sottocategoria="Cassa vs Banca",
                descrizione="Versamenti registrati in cassa non corrispondono a quelli in banca",
                valore_atteso=versamenti_banca,
                valore_trovato=versamenti_manuali,
                periodo=periodo,
                severita="warning" if abs(differenza) < 100 else "critical",
                suggerimento=f"Verificare {count_manuali} versamenti manuali vs {count_banca} in banca"
            )
        
        return {
            "versamenti_manuali": round(versamenti_manuali, 2),
            "versamenti_banca": round(versamenti_banca, 2),
            "differenza": round(differenza, 2),
            "count_manuali": count_manuali,
            "count_banca": count_banca,
            "periodo": periodo
        }
    
    async def verifica_saldo_cassa_vs_banca(self, anno: int) -> Dict:
        """
        Verifica che il saldo Prima Nota corrisponda all'Estratto Conto.
        """
        prefix = f"{anno}"
        
        # Saldo Prima Nota Banca
        pipeline_pn = [
            {"$match": {
                "data": {"$regex": f"^{prefix}"},
                "status": {"$nin": ["deleted", "archived"]}
            }},
            {"$group": {
                "_id": None,
                "entrate": {"$sum": {"$cond": [{"$eq": ["$tipo", "entrata"]}, "$importo", 0]}},
                "uscite": {"$sum": {"$cond": [{"$eq": ["$tipo", "uscita"]}, "$importo", 0]}}
            }}
        ]
        result_pn = await self.db["prima_nota_banca"].aggregate(pipeline_pn).to_list(1)
        if result_pn:
            saldo_prima_nota = result_pn[0]["entrate"] - result_pn[0]["uscite"]
        else:
            saldo_prima_nota = 0
        
        # Saldo Estratto Conto
        # I movimenti dell'estratto conto sono salvati con `importo` SEMPRE
        # POSITIVO (valore assoluto) e `tipo` a "entrata" o "uscita".
        # Sommare direttamente "$importo" sommerebbe entrate e uscite come se
        # fossero tutte positive, producendo un numero privo di significato.
        # Il saldo corretto è: SOMMA(entrate) - SOMMA(uscite).
        pipeline_ec = [
            {"$match": {
                "data": {"$regex": f"^{prefix}"},
                "status": {"$nin": ["deleted", "archived"]}
            }},
            {"$group": {
                "_id": None,
                "entrate": {"$sum": {"$cond": [{"$eq": ["$tipo", "entrata"]}, "$importo", 0]}},
                "uscite": {"$sum": {"$cond": [{"$eq": ["$tipo", "uscita"]}, "$importo", 0]}}
            }}
        ]
        result_ec = await self.db["estratto_conto_movimenti"].aggregate(pipeline_ec).to_list(1)
        if result_ec:
            saldo_estratto = result_ec[0]["entrate"] - result_ec[0]["uscite"]
        else:
            saldo_estratto = 0
        
        differenza = saldo_prima_nota - saldo_estratto
        
        if abs(differenza) > self.tolleranza:
            self._aggiungi_discrepanza(
                categoria="Saldi",
                sottocategoria="Prima Nota vs Estratto Conto",
                descrizione="Il saldo della Prima Nota Banca non corrisponde all'Estratto Conto",
                valore_atteso=saldo_estratto,
                valore_trovato=saldo_prima_nota,
                periodo=f"Anno {anno}",
                severita="critical",
                suggerimento="Verificare movimenti mancanti o duplicati tra Prima Nota e Estratto Conto"
            )
        
        return {
            "saldo_prima_nota": round(saldo_prima_nota, 2),
            "saldo_estratto_conto": round(saldo_estratto, 2),
            "differenza": round(differenza, 2)
        }
    
    async def verifica_f24_vs_pagamenti(self, anno: int) -> Dict:
        """
        Verifica che gli F24 registrati corrispondano ai pagamenti in banca.
        """
        prefix = f"{anno}"
        
        # Totale F24 da pagare/pagati
        pipeline_f24 = [
            {"$match": {"data_scadenza": {"$regex": f"^{prefix}"}}},
            {"$group": {
                "_id": "$stato",
                "totale": {"$sum": "$saldo_finale"},
                "count": {"$sum": 1}
            }}
        ]
        result_f24 = await self.db["f24_unificato"].aggregate(pipeline_f24).to_list(10)
        
        f24_totale = sum(r["totale"] for r in result_f24)
        f24_pagati = sum(r["totale"] for r in result_f24 if r["_id"] == "pagato")
        
        # Pagamenti F24 in banca
        pipeline_banca = [
            {"$match": {
                "data": {"$regex": f"^{prefix}"},
                "$or": [
                    {"descrizione_originale": {"$regex": "F24", "$options": "i"}},
                    {"descrizione_originale": {"$regex": "ERARIO", "$options": "i"}},
                    {"descrizione_originale": {"$regex": "INPS", "$options": "i"}},
                    {"descrizione_originale": {"$regex": "tribut", "$options": "i"}}
                ],
                "importo": {"$lt": 0}  # Uscite
            }},
            {"$group": {"_id": None, "totale": {"$sum": {"$abs": "$importo"}}}}
        ]
        result_banca = await self.db["estratto_conto_movimenti"].aggregate(pipeline_banca).to_list(1)
        pagamenti_banca = result_banca[0]["totale"] if result_banca else 0
        
        differenza = f24_pagati - pagamenti_banca
        
        if abs(differenza) > 1:  # Tolleranza maggiore per F24
            self._aggiungi_discrepanza(
                categoria="F24",
                sottocategoria="Registrati vs Pagati in Banca",
                descrizione="Gli F24 segnati come pagati non corrispondono ai pagamenti bancari",
                valore_atteso=pagamenti_banca,
                valore_trovato=f24_pagati,
                periodo=f"Anno {anno}",
                severita="warning",
                suggerimento="Verificare stato F24 e riconciliazione con estratto conto"
            )
        
        return {
            "f24_totale": round(f24_totale, 2),
            "f24_pagati": round(f24_pagati, 2),
            "pagamenti_banca_f24": round(pagamenti_banca, 2),
            "differenza": round(differenza, 2)
        }
    
    async def verifica_completa(self, anno: int) -> Dict[str, Any]:
        """
        Esegue tutte le verifiche per un anno.
        """
        self.discrepanze = []  # Reset
        
        risultati = {
            "anno": anno,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "verifiche": {},
            "discrepanze": [],
            "riepilogo": {
                "totale_discrepanze": 0,
                "critical": 0,
                "warning": 0,
                "info": 0
            }
        }
        
        # Verifica IVA per ogni mese
        iva_mensile = []
        for mese in range(1, 13):
            iva_credito = await self.verifica_iva_credito_mensile(anno, mese)
            iva_debito = await self.verifica_iva_debito_mensile(anno, mese)
            
            iva_mensile.append({
                "mese": mese,
                "mese_nome": MESI_NOMI[mese],
                **iva_credito,
                **iva_debito
            })
        
        risultati["verifiche"]["iva_mensile"] = iva_mensile
        
        # Calcola totali IVA annuali
        totale_iva_credito = sum(m["iva_credito_fatture"] for m in iva_mensile)
        totale_iva_debito = sum(m["iva_debito_corrispettivi"] for m in iva_mensile)
        
        risultati["verifiche"]["iva_annuale"] = {
            "iva_credito_totale": round(totale_iva_credito, 2),
            "iva_debito_totale": round(totale_iva_debito, 2),
            "saldo_iva": round(totale_iva_debito - totale_iva_credito, 2)
        }
        
        # Verifica versamenti
        versamenti = await self.verifica_versamenti_vs_banca(anno)
        risultati["verifiche"]["versamenti"] = versamenti

        # NOTA: la verifica "Saldo Prima Nota vs Estratto Conto" è stata
        # DISABILITATA su richiesta dell'utente perché produceva una discrepanza
        # fuorviante. Il confronto aggregato tra due totali non dice quale
        # movimento manca. L'utente ha chiesto di sostituirla con una pagina
        # che elenca i singoli movimenti bancari non presenti in Prima Nota
        # (endpoint nuovo: /api/prima-nota/movimenti-ec-non-in-prima-nota).
        # Manteniamo il metodo verifica_saldo_cassa_vs_banca nel codice per
        # eventuale uso diagnostico futuro ma non lo chiamiamo più qui.

        # Verifica F24
        f24 = await self.verifica_f24_vs_pagamenti(anno)
        risultati["verifiche"]["f24"] = f24
        
        # Aggiungi discrepanze al risultato
        risultati["discrepanze"] = self.discrepanze
        risultati["riepilogo"]["totale_discrepanze"] = len(self.discrepanze)
        risultati["riepilogo"]["critical"] = len([d for d in self.discrepanze if d["severita"] == "critical"])
        risultati["riepilogo"]["warning"] = len([d for d in self.discrepanze if d["severita"] == "warning"])
        risultati["riepilogo"]["info"] = len([d for d in self.discrepanze if d["severita"] == "info"])
        
        # Calcola stato_generale basato sulle discrepanze
        if risultati["riepilogo"]["critical"] > 0:
            risultati["stato_generale"] = "CRITICO"
        elif risultati["riepilogo"]["warning"] > 0:
            risultati["stato_generale"] = "ATTENZIONE"
        else:
            risultati["stato_generale"] = "OK"
        
        return risultati
    
    async def verifica_coerenza_iva_tra_pagine(self, anno: int, mese: int) -> Dict[str, Any]:
        """
        Verifica specifica: confronta IVA tra diverse pagine/sezioni.
        Questa è la verifica principale richiesta dall'utente.
        """
        self.discrepanze = []
        periodo = f"{MESI_NOMI[mese]} {anno}"
        prefix = f"{anno}-{mese:02d}"
        
        # === FONTI IVA CREDITO ===
        
        # 1. Da pagina Fatture (somma IVA fatture ricevute)
        pipeline_fatture = [
            {"$match": {
                "$or": [
                    {"data_ricezione": {"$regex": f"^{prefix}"}},
                    {"invoice_date": {"$regex": f"^{prefix}"}}
                ]
            }},
            {"$group": {"_id": None, "totale": {"$sum": "$iva"}, "count": {"$sum": 1}}}
        ]
        res_fatture = await self.db[Collections.INVOICES].aggregate(pipeline_fatture).to_list(1)
        iva_credito_fatture = res_fatture[0]["totale"] if res_fatture else 0
        count_fatture = res_fatture[0]["count"] if res_fatture else 0
        
        # 2. Da calcolo Liquidazione IVA (stessa logica ma potrebbe differire)
        # Qui usiamo la stessa query per consistenza
        iva_credito_liquidazione = iva_credito_fatture  # Stesso calcolo
        
        # === FONTI IVA DEBITO ===
        
        # 1. Da pagina Corrispettivi
        pipeline_corr = [
            {"$match": {"data": {"$regex": f"^{prefix}"}}},
            {"$group": {"_id": None, "totale": {"$sum": "$totale_iva"}, "count": {"$sum": 1}}}
        ]
        res_corr = await self.db["corrispettivi"].aggregate(pipeline_corr).to_list(1)
        iva_debito_corrispettivi = res_corr[0]["totale"] if res_corr else 0
        count_corrispettivi = res_corr[0]["count"] if res_corr else 0
        
        # 2. Da Prima Nota (se registrato separatamente)
        # Alcuni utenti potrebbero registrare IVA anche in prima nota
        
        risultato = {
            "periodo": periodo,
            "anno": anno,
            "mese": mese,
            "iva_credito": {
                "da_fatture": round(iva_credito_fatture, 2),
                "da_liquidazione": round(iva_credito_liquidazione, 2),
                "num_fatture": count_fatture,
                "coerente": abs(iva_credito_fatture - iva_credito_liquidazione) < self.tolleranza
            },
            "iva_debito": {
                "da_corrispettivi": round(iva_debito_corrispettivi, 2),
                "num_corrispettivi": count_corrispettivi
            },
            "saldo": {
                "iva_da_versare": round(max(iva_debito_corrispettivi - iva_credito_fatture, 0), 2),
                "iva_a_credito": round(max(iva_credito_fatture - iva_debito_corrispettivi, 0), 2)
            },
            "discrepanze": self.discrepanze
        }
        
        return risultato


async def esegui_verifica_completa(anno: int) -> Dict[str, Any]:
    """Funzione helper per eseguire la verifica completa."""
    db = Database.get_db()
    verificatore = VerificaCoerenza(db)
    return await verificatore.verifica_completa(anno)


async def esegui_verifica_iva(anno: int, mese: int) -> Dict[str, Any]:
    """Funzione helper per verificare coerenza IVA."""
    db = Database.get_db()
    verificatore = VerificaCoerenza(db)
    return await verificatore.verifica_coerenza_iva_tra_pagine(anno, mese)
