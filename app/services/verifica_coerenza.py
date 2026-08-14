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
        from app.services.iva_liquidation_query import get_iva_period_snapshot

        snapshot = await get_iva_period_snapshot(self.db, anno=anno, mese=mese)
        count_fatture = snapshot["conteggi"]["fatture_periodo_attribuito"]
        # Il confronto mensile usa la competenza fiscale completa. Non deve
        # usare il residuo ancora disponibile per una nuova liquidazione:
        # ``iva_utilizzata`` indica consumo, non esclusione dal mese.
        iva_credito_fatture = snapshot.get("iva_acquisti_competenza")
        return {
            "iva_credito_fatture": iva_credito_fatture,
            "iva_credito_fatture_cents": snapshot.get("iva_acquisti_competenza_cents"),
            "iva_fatture_lorde": iva_credito_fatture,
            "iva_note_credito": 0.0 if iva_credito_fatture is not None else None,
            "num_fatture": count_fatture,
            "conteggi": snapshot["conteggi"],
            "periodo": f"{MESI_NOMI[mese]} {anno}",
            "stato_calcolo": snapshot["stato_calcolo"],
            "fonte_calcolo": snapshot["fonte_calcolo"],
        }
    
    async def verifica_iva_debito_mensile(self, anno: int, mese: int) -> Dict[str, float]:
        """
        Verifica IVA Debito per un mese specifico.
        Confronta: Corrispettivi vs Calcolo Liquidazione
        """
        from app.services.iva_liquidation_query import get_iva_period_snapshot

        snapshot = await get_iva_period_snapshot(self.db, anno=anno, mese=mese)
        return {
            "iva_debito_corrispettivi": snapshot.get("iva_vendite"),
            "iva_debito_corrispettivi_cents": snapshot.get("iva_vendite_cents"),
            "num_corrispettivi": snapshot.get("corrispettivi_inclusi", 0),
            "periodo": f"{MESI_NOMI[mese]} {anno}",
            "stato_calcolo": snapshot["stato_calcolo"],
            "fonte_calcolo": snapshot["fonte_calcolo"],
        }

    async def trova_f24_iva_mensile(self, anno: int, mese: int) -> Dict[str, Any]:
        """Trova la riga IVA nel modello F24 ricevuto dalla commercialista.

        Il confronto riguarda la singola riga tributo 6001..6012. Gli altri
        codici dello stesso F24 (per esempio 1040) restano righe distinte e
        l'eventuale addebito bancario dell'intero modello non modifica il
        valore IVA da confrontare.
        """
        from app.routers.ritenute import _tributi_di
        from app.services.f24_payment_evidence import stato_evidenza_pagamento
        from app.services.tax_payment_query import TaxPaymentQueryService

        periodo = f"{anno}-{mese:02d}"
        codice = str(6000 + mese)
        docs = getattr(self, "_f24_docs_cache", None)
        if docs is None:
            docs = await TaxPaymentQueryService(self.db).list_documents()
            self._f24_docs_cache = docs
        candidati = []
        for f24 in docs:
            righe = _tributi_di(f24)
            for riga in righe:
                if riga.get("codice") != codice:
                    continue
                periodo_riga = riga.get("periodo")
                source = next((
                    item for item in (f24.get("righe_tributo_normalizzate") or [])
                    if item.get("ordinal") - 1 == riga.get("indice")
                ), {})
                source_fields = source.get("source_fields") or {}
                explicit_year = str(
                    source_fields.get("anno_riferimento") or source_fields.get("anno") or ""
                )
                periodo_verificato = periodo_riga == periodo or (
                    not periodo_riga and explicit_year == str(anno)
                )
                if periodo_riga and periodo_riga != periodo:
                    continue
                candidati.append({
                    "f24": f24,
                    "riga": riga,
                    "periodo_verificato": periodo_verificato,
                    "altri_codici": sorted({
                        t.get("codice") for t in righe
                        if t.get("codice") and t.get("codice") != codice
                    }),
                })

        # Deduplica la stessa sorgente eventualmente salvata con più alias.
        unici = {}
        for c in candidati:
            f24 = c["f24"]
            identita = str(
                f24.get("id") or f24.get("document_id") or f24.get("sha256")
                or f24.get("filename") or f24.get("file_name") or ""
            )
            key = (identita, c["riga"].get("indice"))
            unici[key] = c
        candidati = list(unici.values())

        if not candidati:
            return {
                "codice_tributo": codice,
                "periodo": periodo,
                "stato": "in_attesa_f24",
                "importo_f24": None,
                "documenti_candidati": 0,
            }

        verificati = [c for c in candidati if c["periodo_verificato"]]
        migliori = verificati or candidati
        if len(migliori) != 1:
            return {
                "codice_tributo": codice,
                "periodo": periodo,
                "stato": "f24_ambiguo",
                "importo_f24": None,
                "documenti_candidati": len(migliori),
            }

        c = migliori[0]
        f24 = c["f24"]
        evidenza = stato_evidenza_pagamento(f24)
        importo_cents = (
            c["riga"].get("importo_cents") if c["periodo_verificato"] else None
        )
        return {
            "codice_tributo": codice,
            "periodo": periodo,
            "stato": "f24_ricevuto" if c["periodo_verificato"] else "periodo_f24_da_verificare",
            # Il valore numerico resta per compatibilita' della UI; ogni
            # confronto usa esclusivamente l'intero in centesimi.
            "importo_f24": importo_cents / 100 if importo_cents is not None else None,
            "importo_f24_cents": importo_cents,
            "periodo_verificato": c["periodo_verificato"],
            "documenti_candidati": 1,
            "f24_multi_tributo": bool(c["altri_codici"]),
            "altri_codici_tributo": c["altri_codici"],
            "stato_pagamento_intero_f24": evidenza["stato"],
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
        f24_iva_mensile = []
        for mese in range(1, 13):
            iva_credito = await self.verifica_iva_credito_mensile(anno, mese)
            iva_debito = await self.verifica_iva_debito_mensile(anno, mese)
            f24_iva = await self.trova_f24_iva_mensile(anno, mese)
            
            iva_mensile.append({
                "mese": mese,
                "mese_nome": MESI_NOMI[mese],
                **iva_credito,
                **iva_debito
            })
            f24_iva_mensile.append({"mese": mese, "mese_nome": MESI_NOMI[mese], **f24_iva})
        
        risultati["verifiche"]["iva_mensile"] = iva_mensile
        
        # Calcola totali IVA annuali
        from app.services.iva_liquidation_query import euros

        totale_iva_credito_cents = sum(
            int(m.get("iva_credito_fatture_cents") or 0) for m in iva_mensile
        )
        totale_iva_debito_cents = sum(
            int(m.get("iva_debito_corrispettivi_cents") or 0) for m in iva_mensile
        )
        
        risultati["verifiche"]["iva_annuale"] = {
            "iva_credito_totale": euros(totale_iva_credito_cents),
            "iva_credito_totale_cents": totale_iva_credito_cents,
            "iva_debito_totale": euros(totale_iva_debito_cents),
            "iva_debito_totale_cents": totale_iva_debito_cents,
            "saldo_iva": euros(totale_iva_debito_cents - totale_iva_credito_cents),
            "saldo_iva_cents": totale_iva_debito_cents - totale_iva_credito_cents,
            "mesi_non_calcolati": sum(
                1 for item in iva_mensile if item.get("stato_calcolo") == "NON_CALCOLATO"
            )
        }
        risultati["verifiche"]["f24_iva"] = {
            "mensile": f24_iva_mensile,
            "ricevuti": sum(1 for r in f24_iva_mensile if r["stato"] == "f24_ricevuto"),
            "in_attesa": sum(1 for r in f24_iva_mensile if r["stato"] == "in_attesa_f24"),
            "da_verificare": sum(
                1 for r in f24_iva_mensile
                if r["stato"] in ("f24_ambiguo", "periodo_f24_da_verificare")
            ),
        }

        mesi_non_calcolati = risultati["verifiche"]["iva_annuale"]["mesi_non_calcolati"]
        if mesi_non_calcolati:
            self.discrepanze.append({
                "categoria": "IVA",
                "sottocategoria": "Copertura annuale",
                "severita": "warning",
                "descrizione": (
                    f"{mesi_non_calcolati} mesi su 12 non hanno un calcolo IVA completo; "
                    "la verifica annuale non puo essere dichiarata OK."
                ),
                "periodo": str(anno),
                "valore_atteso": 12,
                "valore_trovato": 12 - mesi_non_calcolati,
                "differenza": -mesi_non_calcolati,
                "suggerimento": "Completa o classifica i documenti IVA dei mesi mancanti.",
            })

        # Il vecchio confronto "Versamenti Cassa vs Banca" non rappresenta
        # l'IVA e produceva falsi allarmi. La pagina di coerenza usa ora le
        # righe IVA dei modelli F24 ricevuti dalla commercialista.

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
        from app.services.iva_liquidation_query import (
            euros, get_iva_period_snapshot, money_cents,
        )

        self.discrepanze = []
        periodo = f"{MESI_NOMI[mese]} {anno}"
        snapshot = await get_iva_period_snapshot(self.db, anno=anno, mese=mese)
        iva_credito_fatture = snapshot.get("iva_acquisti_competenza")
        iva_debito_corrispettivi = snapshot.get("iva_vendite")
        iva_credito_cents = snapshot.get("iva_acquisti_competenza_cents")
        iva_debito_cents = snapshot.get("iva_vendite_cents")
        saldo_gestionale_cents = (
            int(iva_debito_cents) - int(iva_credito_cents)
            if iva_debito_cents is not None and iva_credito_cents is not None
            else None
        )
        saldo_gestionale = (
            euros(saldo_gestionale_cents)
            if saldo_gestionale_cents is not None else None
        )
        f24_iva = await self.trova_f24_iva_mensile(anno, mese)
        importo_f24_cents = f24_iva.get("importo_f24_cents")
        scostamento_f24_cents = (
            int(importo_f24_cents) - max(int(saldo_gestionale_cents), 0)
            if importo_f24_cents is not None and saldo_gestionale_cents is not None
            else None
        )
        scostamento_f24 = (
            euros(scostamento_f24_cents)
            if scostamento_f24_cents is not None else None
        )
        
        risultato = {
            "periodo": periodo,
            "anno": anno,
            "mese": mese,
            "iva_credito": {
                "da_fatture": iva_credito_fatture,
                "da_fatture_cents": iva_credito_cents,
                "da_liquidazione": iva_credito_fatture,
                "ancora_disponibile": snapshot.get("iva_acquisti_disponibile"),
                "ancora_disponibile_cents": snapshot.get("iva_acquisti_disponibile_cents"),
                "num_fatture": snapshot["conteggi"]["fatture_periodo_attribuito"],
                "conteggi": snapshot["conteggi"],
                "coerente": True if iva_credito_fatture is not None else None,
            },
            "iva_debito": {
                "da_corrispettivi": iva_debito_corrispettivi,
                "da_corrispettivi_cents": snapshot.get("iva_vendite_cents"),
                "num_corrispettivi": snapshot.get("corrispettivi_inclusi", 0),
            },
            "saldo": {
                "iva_da_versare": None if saldo_gestionale is None else max(saldo_gestionale, 0),
                "iva_a_credito": None if saldo_gestionale is None else max(-saldo_gestionale, 0),
                "saldo_cents": snapshot.get("saldo_cents"),
            },
            "f24_commercialista": {
                **f24_iva,
                "scostamento_gestionale": scostamento_f24,
                "scostamento_gestionale_cents": scostamento_f24_cents,
                "coerente": (
                    abs(scostamento_f24_cents) <= money_cents(self.tolleranza)
                    if scostamento_f24_cents is not None else None
                ),
            },
            "stato_calcolo": snapshot["stato_calcolo"],
            "fonte_calcolo": snapshot["fonte_calcolo"],
            "scadenza_nominale": snapshot["scadenza_nominale"],
            "scadenza_legale": snapshot["scadenza_legale"],
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
