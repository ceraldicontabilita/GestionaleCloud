"""
Regole Avanzate di Contabilità - Sistema Intelligente
Basato su ricerche web approfondite 2025 per standard italiani
"""

from typing import Dict, List, Tuple

# ============================================================================
# CODICI TRIBUTO F24 - ERARIO
# ============================================================================

F24_ERARIO_CODES = {
    # IRES - Imposta sul Reddito delle Società
    "2001": {"descrizione": "IRES - Saldo", "conto": "4.3.02", "tipo": "imposte"},
    "2002": {"descrizione": "IRES - Acconto prima rata", "conto": "4.3.02", "tipo": "imposte"},
    "2003": {"descrizione": "IRES - Acconto seconda rata", "conto": "4.3.02", "tipo": "imposte"},
    "2007": {"descrizione": "IRES - Maggior acconto prima rata", "conto": "4.3.02", "tipo": "imposte"},
    "2008": {"descrizione": "IRES - Maggior acconto seconda rata", "conto": "4.3.02", "tipo": "imposte"},
    
    # IRAP - Imposta Regionale Attività Produttive
    "3800": {"descrizione": "IRAP - Saldo", "conto": "4.3.02", "tipo": "imposte"},
    "3812": {"descrizione": "IRAP - Acconto prima rata", "conto": "4.3.02", "tipo": "imposte"},
    "3813": {"descrizione": "IRAP - Acconto seconda rata", "conto": "4.3.02", "tipo": "imposte"},
    "3881": {"descrizione": "IRAP - Maggior acconto prima rata", "conto": "4.3.02", "tipo": "imposte"},
    "3882": {"descrizione": "IRAP - Maggior acconto seconda rata", "conto": "4.3.02", "tipo": "imposte"},
    
    # IVA
    "6001": {"descrizione": "IVA - Versamento saldo", "conto": "2.1.02", "tipo": "debiti_tributari"},
    "6002": {"descrizione": "IVA - Versamento acconto", "conto": "2.1.02", "tipo": "debiti_tributari"},
    
    # IRPEF (per imprenditori individuali o soci)
    "4001": {"descrizione": "IRPEF - Saldo", "conto": "4.3.02", "tipo": "imposte"},
    "4033": {"descrizione": "IRPEF - Acconto prima rata", "conto": "4.3.02", "tipo": "imposte"},
    "4034": {"descrizione": "IRPEF - Acconto seconda rata", "conto": "4.3.02", "tipo": "imposte"},
    
    # Ritenute d'acconto
    "1001": {"descrizione": "Ritenute IRPEF dipendenti", "conto": "2.1.02", "tipo": "debiti_tributari"},
    "1035": {"descrizione": "Ritenute lavoro autonomo", "conto": "2.1.02", "tipo": "debiti_tributari"},
    "1040": {"descrizione": "Ritenute redditi capitali", "conto": "2.1.02", "tipo": "debiti_tributari"},
    
    # Addizionali Regionali IRPEF
    "3801": {"descrizione": "Addizionale Regionale IRPEF - Saldo (contribuente)", "conto": "4.3.02", "tipo": "imposte"},
    "3802": {"descrizione": "Addizionale Regionale IRPEF - Ritenuta sostituto d'imposta", "conto": "2.1.02", "tipo": "debiti_tributari"},
    
    # Addizionali Comunali IRPEF
    "3843": {"descrizione": "Addizionale Comunale IRPEF - Acconto", "conto": "2.1.02", "tipo": "debiti_tributari"},
    "3848": {"descrizione": "Addizionale Comunale IRPEF - Saldo ritenuta sostituto", "conto": "2.1.02", "tipo": "debiti_tributari"},
}

# ============================================================================
# CODICI TRIBUTO F24 - INPS (CONTRIBUTI)
# ============================================================================

F24_INPS_CODES = {
    # Contributi dipendenti - più comuni per bar/ristorante
    "DM10": {"descrizione": "Contributo previdenziale dipendenti - quota datore", "conto": "4.2.01", "tipo": "costo_personale"},
    "DM11": {"descrizione": "Contributo previdenziale dipendenti - quota lavoratore", "conto": "2.1.03", "tipo": "debiti_previdenziali"},
    "DM12": {"descrizione": "Contributo assistenziale dipendenti - quota datore", "conto": "4.2.01", "tipo": "costo_personale"},
    "DM13": {"descrizione": "Contributo assistenziale dipendenti - quota lavoratore", "conto": "2.1.03", "tipo": "debiti_previdenziali"},
    
    # Gestione separata (collaboratori)
    "DM14": {"descrizione": "Gestione separata - committente", "conto": "4.2.01", "tipo": "costo_personale"},
    "DM15": {"descrizione": "Gestione separata - collaboratore", "conto": "2.1.03", "tipo": "debiti_previdenziali"},
    
    # Ticket licenziamento (contributo NASpI)
    "DLST": {"descrizione": "Ticket licenziamento - contributo NASpI", "conto": "4.2.01", "tipo": "costo_personale"},
    
    # TFR (per aziende +50 dipendenti)
    "TFR0": {"descrizione": "TFR versato al Fondo Tesoreria INPS", "conto": "2.1.06", "tipo": "debiti_previdenziali"},
}

# ============================================================================
# CODICI TRIBUTO INAIL
# ============================================================================

F24_INAIL_CODES = {
    "902025": {
        "descrizione": "Premi INAIL autoliquidazione 2025",
        "conto": "4.2.01",
        "tipo": "costo_personale",
        "centro_costo": "Personale - Assicurazioni",
        "sezione_f24": "INAIL"
    }
}

# ============================================================================
# CODICI TRIBUTO LICENZIAMENTO E TFR
# ============================================================================

CODICI_LICENZIAMENTO = {
    "tfr_liquidazione": {
        "descrizione": "TFR liquidazione dipendente",
        "conto": "2.1.05",  # Fondo TFR
        "conto_pagamento": "1.2.02",  # Banca
        "tipo": "pagamento_tfr",
        "centro_costo": "Personale - TFR"
    },
    "ticket_licenziamento": {
        "descrizione": "Ticket licenziamento (41% max NASpI - max 1562,82€/anno 2025)",
        "conto": "4.2.01",  # Costo personale
        "codice_f24": "DLST",
        "tipo": "contributo_licenziamento",
        "centro_costo": "Personale - Oneri licenziamento",
        "nota": "41% del massimale mensile NASpI per ogni 12 mesi di anzianità, max 3 anni"
    },
    "indennita_preavviso": {
        "descrizione": "Indennità sostitutiva mancato preavviso",
        "conto": "4.2.01",  # Costo personale
        "tipo": "indennita",
        "centro_costo": "Personale - Indennità",
        "nota": "Soggetta a contributi INPS e tassazione separata"
    },
    "imposta_tfr": {
        "descrizione": "Imposta sostitutiva su rivalutazione TFR",
        "conto": "4.3.02",  # Imposte
        "codice_f24": "1713",
        "tipo": "imposta_tfr",
        "centro_costo": "Imposte",
        "scadenza": "17 febbraio anno successivo (saldo) + acconti"
    }
}

# ============================================================================
# MAPPATURA VOCI BUSTA PAGA → CODICI F24
# ============================================================================

VOCI_BUSTA_PAGA_F24 = {
    # Ritenute IRPEF
    "ritenute_irpef": {
        "codice_f24": "1001",
        "descrizione": "Ritenute IRPEF dipendenti",
        "conto": "2.1.02",
        "tipo": "debito_tributario"
    },
    
    # Addizionali Regionali
    "addizionale_regionale": {
        "codice_f24": "3802",
        "descrizione": "Addizionale regionale IRPEF (sostituto)",
        "conto": "2.1.02",
        "tipo": "debito_tributario"
    },
    
    # Addizionali Comunali - Saldo
    "addizionale_comunale_saldo": {
        "codice_f24": "3848",
        "descrizione": "Addizionale comunale IRPEF - Saldo",
        "conto": "2.1.02",
        "tipo": "debito_tributario"
    },
    
    # Addizionali Comunali - Acconto
    "addizionale_comunale_acconto": {
        "codice_f24": "3843",
        "descrizione": "Addizionale comunale IRPEF - Acconto",
        "conto": "2.1.02",
        "tipo": "debito_tributario"
    },
    
    # Contributi INPS - quota dipendente
    "inps_dipendente": {
        "codice_f24": "DM11",  # o DM13 per assistenziale
        "descrizione": "Contributi INPS - quota dipendente",
        "conto": "2.1.03",
        "tipo": "debito_previdenziale"
    },
    
    # Contributi INPS - quota datore
    "inps_datore": {
        "codice_f24": "DM10",  # o DM12 per assistenziale
        "descrizione": "Contributi INPS - quota datore",
        "conto": "4.2.01",
        "tipo": "costo_personale"
    },
    
    # INAIL
    "inail": {
        "codice_f24": "902025",
        "descrizione": "Premi INAIL",
        "conto": "4.2.01",
        "tipo": "costo_personale",
        "centro_costo": "Personale - Assicurazioni"
    },
    
    # TFR
    "tfr_maturato": {
        "descrizione": "TFR maturato mensilmente (7.41% lordo)",
        "conto": "2.1.05",  # Fondo TFR
        "tipo": "accantonamento_tfr"
    }
}

def determina_centro_costo_da_f24(codice_tributo: str, sezione: str) -> str:
    """
    Determina il centro di costo basandosi sul codice tributo F24
    
    Args:
        codice_tributo: Codice tributo (es. "1001", "DM10", "902025")
        sezione: Sezione F24 (erario, inps, inail)
    
    Returns:
        Centro di costo suggerito
    """
    if sezione == "inail":
        return "Personale - Assicurazioni INAIL"
    
    if sezione == "inps":
        if codice_tributo in ["DM10", "DM12"]:
            return "Personale - Contributi datore"
        elif codice_tributo in ["DM11", "DM13"]:
            return "Personale - Contributi dipendente"
        elif codice_tributo == "DLST":
            return "Personale - Oneri licenziamento"
        elif codice_tributo == "TFR0":
            return "Personale - TFR"
        else:
            return "Personale - Contributi"
    
    if sezione == "erario":
        if codice_tributo in ["1001", "1035", "1040"]:
            return "Personale - Ritenute fiscali"
        elif codice_tributo in ["3802", "3843", "3848"]:
            return "Personale - Addizionali IRPEF"
        elif codice_tributo in ["2001", "2002", "2003"]:
            return "Imposte - IRES"
        elif codice_tributo in ["3800", "3812", "3813"]:
            return "Imposte - IRAP"
        elif codice_tributo in ["6001", "6002"]:
            return "IVA"
        elif codice_tributo == "1713":
            return "Personale - TFR (imposta)"
        else:
            return "Imposte"
    
    return "Non specificato"

# ============================================================================
# MOVIMENTI BANCARI - PATTERN E CATEGORIZZAZIONE
# ============================================================================

BANK_MOVEMENT_PATTERNS = {
    # Spese bancarie
    "spese_bancarie": {
        "keywords": ["commissioni", "commissione", "spese bancarie", "spese tenuta conto", "canone conto", "canone mensile", "canone trimestrale"],
        "conto": "4.3.01",  # Interessi passivi bancari / Spese bancarie
        "tipo": "oneri_finanziari",
        "dare": True  # Dare = costo
    },
    
    # Imposta di bollo
    "bollo": {
        "keywords": ["imposta bollo", "bollo", "imposta di bollo sul cc", "i.bollo"],
        "conto": "4.3.02",  # Imposte e tasse
        "tipo": "imposte",
        "dare": True
    },
    
    # Interessi passivi
    "interessi_passivi": {
        "keywords": ["interessi passivi", "int.passivi", "interessi debitori", "int.deb"],
        "conto": "4.3.01",
        "tipo": "oneri_finanziari",
        "dare": True
    },
    
    # Commissioni POS/carte
    "commissioni_pos": {
        "keywords": ["commissioni pos", "commissioni carte", "nexi", "sumup", "worldline", "axepta", "commissione carta"],
        "conto": "4.3.01",
        "tipo": "oneri_finanziari",
        "dare": True
    },
    
    # F24 Erario (riconoscimento da causale)
    "f24_erario": {
        "keywords": ["f24", "f 24", "tributi erariali", "agenzia entrate", "pagamento imposte"],
        "conto": None,  # Determinato da codice tributo
        "tipo": "f24_erario",
        "dare": True,
        "needs_code_analysis": True
    },
    
    # F24 INPS (riconoscimento da causale)
    "f24_inps": {
        "keywords": ["inps", "contributi inps", "contributi previdenziali", "dm10", "dm11"],
        "conto": "4.2.01",
        "tipo": "costo_personale",
        "dare": True
    },
    
    # Stipendi
    "stipendi": {
        "keywords": ["stipendio", "stipendi", "salario", "retribuzione", "busta paga", "cedolino"],
        "conto": "4.2.01",
        "tipo": "costo_personale",
        "dare": True
    },
    
    # Fornitori
    "pagamento_fornitori": {
        "keywords": ["bonifico", "pagamento fornitore", "saldo fattura", "pagam.fatt"],
        "conto": "2.1.01",  # Debiti verso fornitori
        "tipo": "pagamento_debito",
        "dare": True
    },
    
    # Incassi clienti
    "incasso_clienti": {
        "keywords": ["bonifico cliente", "incasso", "pagamento cliente", "ric.bonifico"],
        "conto": "1.2.03",  # Crediti verso clienti
        "tipo": "incasso_credito",
        "dare": False  # Avere = riduzione credito
    },
    
    # Prelievi bancomat
    "prelievi": {
        "keywords": ["prelievo", "prelievo bancomat", "prelievo atm", "prelevamento"],
        "conto": "1.2.01",  # Cassa
        "tipo": "movimento_interno",
        "dare": False  # Avere = uscita da banca, Dare su Cassa
    },
    
    # Affitti
    "affitto": {
        "keywords": ["affitto", "canone locazione", "fitto", "locazione"],
        "conto": "4.2.02",
        "tipo": "affitti",
        "dare": True
    },
    
    # Utenze
    "utenze": {
        "keywords": ["enel", "eni", "acea", "bolletta", "energia elettrica", "gas", "acqua", "telecom", "tim", "vodafone", "fastweb"],
        "conto": "4.2.03",
        "tipo": "utenze",
        "dare": True
    },
}

# ============================================================================
# OMAGGI - REGOLE DI CATEGORIZZAZIONE
# ============================================================================

OMAGGI_RULES = {
    "cliente_sotto_50": {
        "descrizione": "Omaggio a cliente (valore unitario <= 50€)",
        "deducibilita": 100,  # Percentuale
        "iva_detraibile": True,  # Se <= 25,82€
        "conto": "4.2.08",  # Spese di rappresentanza
        "note": "Interamente deducibile, IVA detraibile se <= 25,82€"
    },
    "cliente_sopra_50": {
        "descrizione": "Omaggio a cliente (valore unitario > 50€)",
        "deducibilita": 75,  # Percentuale (entro limite 1,5% ricavi)
        "iva_detraibile": False,
        "conto": "4.2.08",
        "note": "Deducibile 75% entro 1,5% ricavi, IVA indetraibile"
    },
    "dipendente": {
        "descrizione": "Omaggio a dipendente",
        "deducibilita": 100,
        "iva_detraibile": False,
        "conto": "4.2.01",  # Costo personale
        "note": "Interamente deducibile, IVA sempre indetraibile"
    },
}

# ============================================================================
# PARTITA DOPPIA - TEMPLATE SCRITTURE CONTABILI
# ============================================================================

DOUBLE_ENTRY_TEMPLATES = {
    "acquisto_merce_contanti": {
        "descrizione": "Acquisto merce con pagamento immediato in contanti",
        "righe": [
            {"conto": "4.1.01", "dare": "importo_netto", "avere": 0, "descrizione": "Merce c/acquisti"},
            {"conto": "iva_credito", "dare": "importo_iva", "avere": 0, "descrizione": "IVA a credito"},
            {"conto": "1.2.01", "dare": 0, "avere": "importo_totale", "descrizione": "Cassa"},
        ]
    },
    
    "acquisto_merce_credito": {
        "descrizione": "Acquisto merce a credito (fattura da pagare)",
        "righe": [
            {"conto": "4.1.01", "dare": "importo_netto", "avere": 0, "descrizione": "Merce c/acquisti"},
            {"conto": "iva_credito", "dare": "importo_iva", "avere": 0, "descrizione": "IVA a credito"},
            {"conto": "2.1.01", "dare": 0, "avere": "importo_totale", "descrizione": "Debiti verso fornitori"},
        ]
    },
    
    "pagamento_fornitore": {
        "descrizione": "Pagamento fattura fornitore",
        "righe": [
            {"conto": "2.1.01", "dare": "importo_totale", "avere": 0, "descrizione": "Debiti verso fornitori"},
            {"conto": "1.2.02", "dare": 0, "avere": "importo_totale", "descrizione": "Banca c/c"},
        ]
    },
    
    "vendita_contanti": {
        "descrizione": "Vendita con incasso immediato in contanti",
        "righe": [
            {"conto": "1.2.01", "dare": "importo_totale", "avere": 0, "descrizione": "Cassa"},
            {"conto": "3.1.01", "dare": 0, "avere": "importo_netto", "descrizione": "Ricavi vendite"},
            {"conto": "iva_debito", "dare": 0, "avere": "importo_iva", "descrizione": "IVA a debito"},
        ]
    },
    
    "vendita_credito": {
        "descrizione": "Vendita a credito (fattura attiva)",
        "righe": [
            {"conto": "1.2.03", "dare": "importo_totale", "avere": 0, "descrizione": "Crediti verso clienti"},
            {"conto": "3.1.01", "dare": 0, "avere": "importo_netto", "descrizione": "Ricavi vendite"},
            {"conto": "iva_debito", "dare": 0, "avere": "importo_iva", "descrizione": "IVA a debito"},
        ]
    },
    
    "incasso_cliente": {
        "descrizione": "Incasso bonifico da cliente",
        "righe": [
            {"conto": "1.2.02", "dare": "importo_totale", "avere": 0, "descrizione": "Banca c/c"},
            {"conto": "1.2.03", "dare": 0, "avere": "importo_totale", "descrizione": "Crediti verso clienti"},
        ]
    },
    
    "spese_bancarie": {
        "descrizione": "Addebito spese bancarie",
        "righe": [
            {"conto": "4.3.01", "dare": "importo_totale", "avere": 0, "descrizione": "Oneri bancari"},
            {"conto": "1.2.02", "dare": 0, "avere": "importo_totale", "descrizione": "Banca c/c"},
        ]
    },
    
    "f24_erario": {
        "descrizione": "Pagamento F24 Erario",
        "righe": [
            {"conto": "dynamic", "dare": "importo_totale", "avere": 0, "descrizione": "Imposte/Debiti tributari"},
            {"conto": "1.2.02", "dare": 0, "avere": "importo_totale", "descrizione": "Banca c/c"},
        ]
    },
    
    "f24_inps": {
        "descrizione": "Pagamento F24 INPS contributi",
        "righe": [
            {"conto": "4.2.01", "dare": "importo_totale", "avere": 0, "descrizione": "Costo del personale"},
            {"conto": "1.2.02", "dare": 0, "avere": "importo_totale", "descrizione": "Banca c/c"},
        ]
    },
    
    "stipendio": {
        "descrizione": "Pagamento stipendio dipendente",
        "righe": [
            {"conto": "4.2.01", "dare": "importo_lordo", "avere": 0, "descrizione": "Costo del personale (lordo)"},
            {"conto": "2.1.02", "dare": 0, "avere": "ritenute_irpef", "descrizione": "Debiti tributari (ritenute)"},
            {"conto": "2.1.03", "dare": 0, "avere": "contributi_dipendente", "descrizione": "Debiti previdenziali"},
            {"conto": "1.2.02", "dare": 0, "avere": "importo_netto", "descrizione": "Banca c/c (netto dipendente)"},
        ]
    },
    
    "omaggio_cliente": {
        "descrizione": "Omaggio a cliente",
        "righe": [
            {"conto": "4.2.08", "dare": "importo_netto", "avere": 0, "descrizione": "Spese rappresentanza (omaggio)"},
            {"conto": "iva_indetraibile", "dare": "importo_iva", "avere": 0, "descrizione": "IVA indetraibile"},
            {"conto": "1.2.01", "dare": 0, "avere": "importo_totale", "descrizione": "Cassa"},
        ]
    },
    
    "omaggio_dipendente": {
        "descrizione": "Omaggio a dipendente",
        "righe": [
            {"conto": "4.2.01", "dare": "importo_netto", "avere": 0, "descrizione": "Costo personale (benefit)"},
            {"conto": "iva_indetraibile", "dare": "importo_iva", "avere": 0, "descrizione": "IVA indetraibile"},
            {"conto": "1.2.01", "dare": 0, "avere": "importo_totale", "descrizione": "Cassa"},
        ]
    },
    
    "autoconsumo": {
        "descrizione": "Autoconsumo titolare",
        "righe": [
            {"conto": "prelievo_titolare", "dare": "importo_totale", "avere": 0, "descrizione": "Prelievi titolare"},
            {"conto": "3.1.01", "dare": 0, "avere": "importo_netto", "descrizione": "Ricavi (autoconsumo)"},
            {"conto": "iva_debito", "dare": 0, "avere": "importo_iva", "descrizione": "IVA a debito"},
        ]
    },
}

# ============================================================================
# FUNZIONI HELPER PER RICONOSCIMENTO E CATEGORIZZAZIONE
# ============================================================================

def riconosci_f24(descrizione: str, importo: float) -> Dict:
    """
    Riconosce se un movimento bancario è un F24 e ne determina la tipologia
    
    Returns:
        dict con chiavi: tipo ('erario' o 'inps'), codice_tributo, conto, descrizione
    """
    descrizione_lower = descrizione.lower()
    
    # Cerca pattern F24
    if any(kw in descrizione_lower for kw in ["f24", "f 24", "tributi"]):
        # Cerca codice tributo nella descrizione
        import re
        
        # Pattern per codici erario (4 cifre)
        match_erario = re.search(r'\b([2-6]\d{3})\b', descrizione)
        if match_erario:
            codice = match_erario.group(1)
            if codice in F24_ERARIO_CODES:
                return {
                    "tipo": "erario",
                    "codice_tributo": codice,
                    "conto": F24_ERARIO_CODES[codice]["conto"],
                    "descrizione_tributo": F24_ERARIO_CODES[codice]["descrizione"],
                    "categoria": F24_ERARIO_CODES[codice]["tipo"]
                }
        
        # Pattern per codici INPS (DM seguito da 2 cifre)
        match_inps = re.search(r'\b(DM\d{2})\b', descrizione.upper())
        if match_inps:
            codice = match_inps.group(1).upper()
            if codice in F24_INPS_CODES:
                return {
                    "tipo": "inps",
                    "codice_tributo": codice,
                    "conto": F24_INPS_CODES[codice]["conto"],
                    "descrizione_tributo": F24_INPS_CODES[codice]["descrizione"],
                    "categoria": F24_INPS_CODES[codice]["tipo"]
                }
        
        # Se contiene INPS ma no codice specifico
        if "inps" in descrizione_lower or "contributi" in descrizione_lower:
            return {
                "tipo": "inps",
                "codice_tributo": None,
                "conto": "4.2.01",
                "descrizione_tributo": "Contributi INPS (generico)",
                "categoria": "costo_personale"
            }
        
        # Altrimenti erario generico
        return {
            "tipo": "erario",
            "codice_tributo": None,
            "conto": "4.3.02",
            "descrizione_tributo": "Imposte (generico)",
            "categoria": "imposte"
        }
    
    return None


def categorizza_movimento_bancario(descrizione: str, importo: float, tipo_movimento: str) -> Dict:
    """
    Categorizza un movimento bancario basandosi sulla descrizione
    
    Args:
        descrizione: Causale del movimento
        importo: Importo del movimento
        tipo_movimento: 'addebito' o 'accredito'
    
    Returns:
        dict con chiavi: conto, tipo, dare, descrizione_categoria
    """
    descrizione_lower = descrizione.lower()
    
    # Prima verifica se è un F24
    f24_info = riconosci_f24(descrizione, importo)
    if f24_info:
        return {
            "conto": f24_info["conto"],
            "tipo": f24_info["categoria"],
            "dare": True,
            "descrizione_categoria": f24_info["descrizione_tributo"],
            "f24_dettagli": f24_info
        }
    
    # Cerca pattern nei movimenti standard
    for pattern_key, pattern_data in BANK_MOVEMENT_PATTERNS.items():
        if any(kw in descrizione_lower for kw in pattern_data["keywords"]):
            return {
                "conto": pattern_data["conto"],
                "tipo": pattern_data["tipo"],
                "dare": pattern_data["dare"],
                "descrizione_categoria": pattern_key.replace("_", " ").title()
            }
    
    # Default: movimento non categorizzato
    return {
        "conto": None,
        "tipo": "non_categorizzato",
        "dare": tipo_movimento == "addebito",
        "descrizione_categoria": "Movimento non categorizzato"
    }


def determina_conto_omaggio(valore_unitario: float, destinatario: str) -> Dict:
    """
    Determina il trattamento contabile di un omaggio
    
    Args:
        valore_unitario: Valore unitario dell'omaggio (IVA esclusa)
        destinatario: 'cliente' o 'dipendente'
    
    Returns:
        dict con regole di deducibilità e conto contabile
    """
    if destinatario == "dipendente":
        return OMAGGI_RULES["dipendente"]
    
    if valore_unitario <= 50:
        rule = OMAGGI_RULES["cliente_sotto_50"].copy()
        # IVA detraibile solo se <= 25,82€
        rule["iva_detraibile"] = valore_unitario <= 25.82
        return rule
    else:
        return OMAGGI_RULES["cliente_sopra_50"]


def genera_scrittura_partita_doppia(template_key: str, dati: Dict) -> List[Dict]:
    """
    Genera una scrittura contabile in partita doppia da un template
    
    Args:
        template_key: Chiave del template (es. 'acquisto_merce_contanti')
        dati: Dizionario con i valori (es. {'importo_netto': 1000, 'importo_iva': 220})
    
    Returns:
        Lista di righe contabili con dare e avere
    """
    if template_key not in DOUBLE_ENTRY_TEMPLATES:
        raise ValueError(f"Template '{template_key}' non trovato")
    
    template = DOUBLE_ENTRY_TEMPLATES[template_key]
    righe_output = []
    
    for riga in template["righe"]:
        riga_output = {
            "conto": riga["conto"],
            "descrizione": riga["descrizione"],
            "dare": 0,
            "avere": 0
        }
        
        # Calcola dare
        if riga["dare"] != 0:
            if isinstance(riga["dare"], str):
                # È una chiave da sostituire (es. 'importo_netto')
                if riga["dare"] in dati:
                    riga_output["dare"] = dati[riga["dare"]]
                else:
                    riga_output["dare"] = 0
            else:
                riga_output["dare"] = riga["dare"]
        
        # Calcola avere
        if riga["avere"] != 0:
            if isinstance(riga["avere"], str):
                # È una chiave da sostituire
                if riga["avere"] in dati:
                    riga_output["avere"] = dati[riga["avere"]]
                else:
                    riga_output["avere"] = 0
            else:
                riga_output["avere"] = riga["avere"]
        
        righe_output.append(riga_output)
    
    return righe_output


def verifica_quadratura(righe: List[Dict]) -> Tuple[bool, float, float]:
    """
    Verifica che una scrittura contabile sia in quadratura (Dare = Avere)
    
    Returns:
        tuple (quadra: bool, totale_dare: float, totale_avere: float)
    """
    totale_dare = sum(r["dare"] for r in righe)
    totale_avere = sum(r["avere"] for r in righe)
    
    # Tolleranza per errori di arrotondamento
    quadra = abs(totale_dare - totale_avere) < 0.01
    
    return quadra, totale_dare, totale_avere
