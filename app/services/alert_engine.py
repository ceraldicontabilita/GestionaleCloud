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
import asyncio
import hashlib
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from app.constants.canale_documento import (
    STATO_ALERT_APERTO, STATO_ALERT_IGNORATO, STATO_ALERT_RISOLTO,
)

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
    "POSTA_NON_RAGGIUNGIBILE": {
        "modulo": "email",
        "severita": "critical",
        "titolo": "Il gestionale non entra nella casella di posta",
        "condizione_chiusura": "Login IMAP riuscito al giro successivo"
    },
    "RITENUTA_DA_VERSARE": {
        "modulo": "f24",
        "severita": "warning",
        "titolo": "Parcella con ritenuta d'acconto da versare (F24 1040)",
        "condizione_chiusura": "F24 con il codice 1040 del periodo versato"
    },
    "POSSIBILE_DOPPIO_PAGAMENTO_F24": {
        "modulo": "f24",
        "severita": "warning",
        "titolo": "Possibile doppio pagamento: F24 ordinario e regolarizzazione RC01 per lo stesso debito",
        "condizione_chiusura": "Il titolare cambia lo stato dell'anomalia (non duplicato, confermato, "
                               "rimborsato/compensato, chiuso dal consulente)"
    },
    "F24_CONTROLLO_DA_VERIFICARE": {
        "modulo": "f24",
        "severita": "warning",
        "titolo": "F24 con righe da verificare (codice Regione/Comune, riga INAIL, causale INPS)",
        "condizione_chiusura": "Il modello non ha piu' righe da verificare al controllo successivo"
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
    "F24_QUIETANZA_SENZA_ADDEBITO": {
        "modulo": "f24",
        "severita": "warning",
        "titolo": "Quietanza F24 senza addebito in banca",
        "condizione_chiusura": "Addebito I24 di pari importo e data d'incasso trovato",
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

    # --- Incroci fiscali del minisito (incroci_fiscali.py) ---
    "IVA_PAGAMENTO_MANCANTE_O_PARZIALE": {
        "modulo": "fiscale",
        "severita": "critical",
        "titolo": "IVA mensile dovuta da LIPE non versata (o versata in parte)",
        "condizione_chiusura": "Versato con il codice 60MM del mese entro 1,00 EUR dal VP14, o LIPE sostituita"
    },
    "IRAP_SALDO_MANCANTE_O_PARZIALE": {
        "modulo": "fiscale",
        "severita": "critical",
        "titolo": "Saldo IRAP (rigo IR26) non versato con il codice 3800",
        "condizione_chiusura": "Codice 3800 dell'anno d'imposta versato entro 1,00 EUR dal rigo IR26"
    },
    "IVA_ANNUALE_SALDO_DA_VERIFICARE": {
        "modulo": "fiscale",
        "severita": "warning",
        "titolo": "Saldo IVA annuale (rigo VX1) senza versamento 6099",
        "condizione_chiusura": "Codice 6099 dell'anno d'imposta versato entro 1,00 EUR dal rigo VX1"
    },
    "COMUNICAZIONE_54BIS_NON_PAGATA": {
        "modulo": "fiscale",
        "severita": "critical",
        "titolo": "Comunicazione di irregolarita' (art. 54-bis) non pagata",
        "condizione_chiusura": "Codici della comunicazione versati per il suo totale entro 1,00 EUR"
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
    # Definizioni arrivate dalla copia `app/hr` il 19/09/2026: erano solo di
    # la', e un codice fuori catalogo fa tornare `genera_alert` None con una
    # semplice riga di log — l'alert sparisce in silenzio.
    "CED_CONTESTATA": {
        "modulo": "cedolini",
        "severita": "warning",
        "titolo": "Busta paga contestata dal dipendente",
        "condizione_chiusura": "Contestazione gestita"
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
    "DIP_DIMISSIONI_RICEVUTE": {
        "modulo": "dipendenti",
        "severita": "critical",
        "titolo": "Dimissioni ricevute: UNILAV di cessazione entro 5 giorni",
        "condizione_chiusura": "Dipendente cessato in HR o alert risolto dopo la comunicazione al consulente"
    },
    "DIP_CONTRATTO_IN_SCADENZA": {
        "modulo": "dipendenti",
        "severita": "warning",
        "titolo": "Contratto a termine in scadenza",
        "condizione_chiusura": "Rinnovo o cessazione registrati"
    },
    "DIP_PERIODO_PROVA_IN_SCADENZA": {
        "modulo": "dipendenti",
        "severita": "warning",
        "titolo": "Periodo di prova in scadenza",
        "condizione_chiusura": "Esito prova registrato"
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
    "F24_TRIBUTO_VERSATO_DUE_VOLTE": {
        "modulo": "f24",
        "severita": "warning",
        "titolo": "Stesso tributo in due deleghe F24 dello stesso giorno",
        "condizione_chiusura": "Verificato col commercialista (rimborso, compensazione o delega annullata)",
    },
    "DILAZIONE_INPS_RATA_NON_PAGATA": {
        "modulo": "f24",
        "severita": "warning",
        "titolo": "Rata della dilazione INPS non versata per intero",
        "condizione_chiusura": "Quietanza F24 della rata (sede, causale, matricola, periodo, importo)",
    },
    "BNK_F24_SENZA_QUIETANZA": {
        "modulo": "banca",
        "severita": "warning",
        "titolo": "Addebito F24 senza quietanza: da riscaricare dal Cassetto Fiscale",
        "condizione_chiusura": "Quietanza di pari importo e data d'incasso caricata",
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
    "FONTE_CONTABILE_FERMA": {
        "modulo": "banca",
        "severita": "critical",
        "titolo": "Fonte contabile ferma: non arrivano piu' documenti",
        "condizione_chiusura": "La fonte torna ad aggiornarsi"
    },
    "ESTRATTO_MESE_MANCANTE": {
        "modulo": "banca",
        "severita": "warning",
        "titolo": "Estratto del mese mancante",
        "condizione_chiusura": "Estratto del mese caricato"
    },
    "BNK_BENEFICIARIO_DIVERSO": {
        "modulo": "banca",
        "severita": "warning",
        "titolo": "Bonifico collegato a una fattura di un altro fornitore",
        "condizione_chiusura": "Collegamento corretto o beneficiario confermato"
    },
    "FAT_PAGATA_DUE_VOLTE": {
        "modulo": "fatture",
        "severita": "critical",
        "titolo": "Fattura con due uscite per l'importo intero",
        "condizione_chiusura": "Uscita in piu' scollegata o rimborso trovato"
    },
    "FAT_IMPORTO_ANOMALO": {
        "modulo": "fatture",
        "severita": "info",
        "titolo": "Fattura molto piu' alta del solito per il fornitore",
        "condizione_chiusura": "Importo confermato dal titolare"
    },
    "RT_GIORNO_SENZA_CHIUSURA": {
        "modulo": "cassa",
        "severita": "warning",
        "titolo": "Giorno con incassi POS e senza chiusura RT",
        "condizione_chiusura": "Chiusura RT del giorno importata"
    },
    "ESTRATTO_NEXI_MANCANTE": {
        "modulo": "banca",
        "severita": "warning",
        "titolo": "Estratto conto Nexi mancante",
        "condizione_chiusura": "Estratto Nexi del periodo caricato"
    },
    "NEXI_ADDEBITO_NON_QUADRA": {
        "modulo": "banca",
        "severita": "warning",
        "titolo": "Addebito Nexi non quadra con l'estratto carta",
        "condizione_chiusura": "Differenza spiegata o estratto corretto"
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
    "MAG_SOTTO_SCORTA": {
        "modulo": "magazzino",
        "severita": "warning",
        "titolo": "Prodotto sotto scorta",
        "condizione_chiusura": "Giacenza ripristinata"
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
    "FATTURA_IDENTITA_DA_VERIFICARE": {
        "modulo": "fatture",
        "severita": "warning",
        "titolo": "Fatture con stessa chiave ma originali diversi",
        "condizione_chiusura": "Originali confrontati e collisione confermata o annullata"
    },
    "FATTURA_CASSA_PAGATA_BANCA": {
        "modulo": "prima_nota",
        "severita": "warning",
        "titolo": "Fattura pagata per BANCA nonostante metodo cassa",
        "condizione_chiusura": "Presa visione (registrazione già corretta in banca)"
    },
    "COLLAUDO_INVARIANTE": {
        "modulo": "collaudo",
        "severita": "warning",
        "titolo": "Collaudo automatico: invariante violata",
        "condizione_chiusura": "Il check torna a zero violazioni al giro successivo"
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

#: Una sola creazione per volta nel processo: fra il controllo «esiste gia'
#: aperto?» e l'inserimento ci sono degli await, e il giro dei 30 minuti e
#: l'import di un estratto conto che girano insieme aprivano due alert gemelli
#: per lo stesso movimento (15 doppioni RIC_* in produzione).
_creazione_lock = asyncio.Lock()


def id_alert_deterministico(codice: str, entita_id: str, generazione: int) -> str:
    """Identificativo stabile dell'alert (codice, entita', n-esima apertura).

    Due processi (deploy sovrapposto, web + scheduler) che aprono lo stesso
    alert nello stesso momento calcolano lo stesso id: l'upsert per id di
    Supabase ne tiene uno solo, invece di due righe gemelle. La generazione
    (quanti alert di quel codice l'entita' ha gia' avuto) conserva lo storico:
    un alert chiuso non viene sovrascritto da quello che si riapre dopo.
    """
    chiave = f"{codice}|{entita_id}|{int(generazione)}"
    return "alert_" + hashlib.sha256(chiave.encode("utf-8")).hexdigest()[:24]


async def _generazione_alert(db, codice: str, entita_id: str) -> int:
    contatore = getattr(db[COLL_ALERTS], "count_documents", None)
    if contatore is None:
        return 0
    try:
        return int(await contatore({"codice": codice, "entita_id": entita_id}))
    except Exception as exc:  # noqa: BLE001 - resta l'id della generazione 0
        logger.warning("Conteggio alert %s/%s non riuscito: %s: %s",
                       codice, entita_id, type(exc).__name__, exc)
        return 0


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
    Idempotente: se l'alert esiste già aperto, non lo duplica — neanche con
    due chiamate concorrenti nello stesso processo (lock) o in due processi
    (id deterministico, vedi ``id_alert_deterministico``).

    Returns: il documento alert creato, o None se già esistente.
    """
    if codice not in ALERT_CATALOG:
        logger.warning(f"Codice alert sconosciuto: {codice}")
        return None

    cat = ALERT_CATALOG[codice]

    async with _creazione_lock:
        # Idempotenza: controlla se esiste già aperto
        existing = await db[COLL_ALERTS].find_one({
            "codice": codice,
            "entita_id": entita_id,
            "stato": STATO_ALERT_APERTO
        })

        if existing:
            logger.debug(f"Alert {codice} già aperto per {entita_id}, skip")
            return None

        alert_id = id_alert_deterministico(
            codice, entita_id, await _generazione_alert(db, codice, entita_id),
        )
        alert = {
            "_id": alert_id,
            "id": alert_id,
            "codice": codice,
            "modulo": cat["modulo"],
            "severita": cat["severita"],
            "titolo": cat["titolo"],
            "dettaglio": dettaglio,
            "condizione_chiusura": cat["condizione_chiusura"],
            "entita_id": entita_id,
            "entita_collection": entita_collection,
            "stato": STATO_ALERT_APERTO,
            "letto": False,
            "risolto": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "resolved_at": None,
            "resolved_by": None,
        }

        if extra:
            alert["extra"] = extra

        await db[COLL_ALERTS].insert_one(alert)
    alert.pop("_id", None)
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
            "stato": STATO_ALERT_APERTO
        },
        {
            "$set": {
                "stato": STATO_ALERT_RISOLTO,
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


async def risolvi_alert_per_id(
    alert_id: str,
    db,
    motivo: str,
    resolved_by: str = "sistema",
) -> bool:
    """Chiude UN alert aperto per id, scrivendo il motivo.

    E' lo stesso gesto di ``risolvi_alert``, pensato per le bonifiche: si
    chiude solo la riga nominata, mai per filtro, e resta scritto perche'.
    """
    if not alert_id:
        return False
    result = await db[COLL_ALERTS].update_one(
        {"id": alert_id, "stato": STATO_ALERT_APERTO},
        {"$set": {
            "stato": STATO_ALERT_RISOLTO,
            "risolto": True,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
            "resolved_by": resolved_by,
            "motivo_chiusura": motivo,
        }},
    )
    return result.modified_count > 0


#: Gli alert che un movimento bancario tiene aperti finche' non e'
#: riconciliato. Nessuno li chiudeva: il movimento abbinato restava «senza
#: match» per sempre.
CODICI_ALERT_MOVIMENTO_DA_RICONCILIARE = (
    "RIC_NON_RICONCILIATO",
    "RIC_MATCH_AMBIGUO",
    "RIC_PAGAMENTO_MULTIPLO",
)


async def chiudi_alert_movimento_riconciliato(
    db, movimento_id: Any, resolved_by: str = "riconciliazione",
) -> int:
    """Il movimento e' diventato ``riconciliato: True``: i suoi alert di
    riconciliazione non hanno piu' ragione di stare aperti. Non blocca mai
    chi riconcilia: un errore qui si scrive nel log e basta."""
    if not movimento_id:
        return 0
    try:
        return await risolvi_alert_multi(
            list(CODICI_ALERT_MOVIMENTO_DA_RICONCILIARE), str(movimento_id), db, resolved_by,
        )
    except Exception as exc:  # noqa: BLE001 - la riconciliazione e' gia' scritta
        logger.warning(
            "Alert del movimento %s non chiusi: %s: %s",
            movimento_id, type(exc).__name__, exc,
        )
        return 0


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
        {"entita_id": entita_id, "stato": STATO_ALERT_APERTO},
        {"_id": 0}
    ).to_list(100)
    return alerts


async def conta_alert_per_modulo(db) -> Dict[str, Dict[str, int]]:
    """Ritorna conteggio alert aperti raggruppati per modulo e severità."""
    pipeline = [
        {"$match": {"stato": STATO_ALERT_APERTO}},
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
        {"id": alert_id, "stato": STATO_ALERT_APERTO},
        {
            "$set": {
                "stato": STATO_ALERT_IGNORATO,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "resolved_by": ignored_by
            }
        }
    )
    return result.modified_count > 0


# ============================================================
# SEED: inserire definizioni alert in Drive/Supabase
# ============================================================
async def seed_alert_definitions(db):
    """Inserisce/aggiorna il catalogo alert_definitions in Drive/Supabase."""
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
