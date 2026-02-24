"""
Configurazione azienda centralizzata.
USARE SEMPRE QUESTE COSTANTI, MAI VALORI HARDCODED.
"""
import os
from typing import Dict, List


class AziendaConfig:
    """Configurazione dati azienda."""
    
    # === DATI AZIENDA ===
    RAGIONE_SOCIALE: str = os.environ.get("AZIENDA_RAGIONE_SOCIALE", "Ceraldi Group S.r.l.")
    PARTITA_IVA: str = os.environ.get("AZIENDA_PIVA", "04523831214")
    CODICE_FISCALE: str = os.environ.get("AZIENDA_CF", "04523831214")
    
    # === CONTATTI ===
    EMAIL: str = os.environ.get("AZIENDA_EMAIL", "ceraldigroupsrl@gmail.com")
    PEC: str = os.environ.get("AZIENDA_PEC", "")
    TELEFONO: str = os.environ.get("AZIENDA_TEL", "")
    
    # === INDIRIZZO ===
    INDIRIZZO: str = os.environ.get("AZIENDA_INDIRIZZO", "")
    CAP: str = os.environ.get("AZIENDA_CAP", "")
    CITTA: str = os.environ.get("AZIENDA_CITTA", "")
    PROVINCIA: str = os.environ.get("AZIENDA_PROVINCIA", "")
    
    # === COORDINATE BANCARIE ===
    IBAN_PRINCIPALE: str = os.environ.get("AZIENDA_IBAN", "")
    BIC: str = os.environ.get("AZIENDA_BIC", "")
    BANCA: str = os.environ.get("AZIENDA_BANCA", "")


class AliquoteIVA:
    """Aliquote IVA standard Italia."""
    
    ORDINARIA: float = 0.22      # 22%
    RIDOTTA_10: float = 0.10    # 10%
    RIDOTTA_5: float = 0.05     # 5%
    MINIMA: float = 0.04        # 4%
    ESENTE: float = 0.00        # Esente
    
    # Mapping codici natura IVA
    NATURE_IVA: Dict[str, str] = {
        "N1": "Escluse ex art. 15",
        "N2": "Non soggette",
        "N2.1": "Non soggette - altri casi",
        "N2.2": "Non soggette - altri casi",
        "N3": "Non imponibili",
        "N3.1": "Non imponibili - esportazioni",
        "N3.2": "Non imponibili - cessioni intraUE",
        "N3.3": "Non imponibili - San Marino",
        "N3.4": "Non imponibili - lettera d) art. 8-bis",
        "N3.5": "Non imponibili - a seguito di dichiarazioni",
        "N3.6": "Non imponibili - altre operazioni",
        "N4": "Esenti",
        "N5": "Regime del margine",
        "N6": "Inversione contabile",
        "N6.1": "Inversione contabile - cessione rottami",
        "N6.2": "Inversione contabile - cessione oro/argento",
        "N6.3": "Inversione contabile - subappalto edilizia",
        "N6.4": "Inversione contabile - cessione fabbricati",
        "N6.5": "Inversione contabile - cellulari",
        "N6.6": "Inversione contabile - prodotti elettronici",
        "N6.7": "Inversione contabile - prestazioni comparto edile",
        "N6.8": "Inversione contabile - operazioni settore energetico",
        "N6.9": "Inversione contabile - altri casi",
        "N7": "IVA assolta in altro stato UE",
    }
    
    @classmethod
    def get_aliquota(cls, codice: str) -> float:
        """Ottiene aliquota da codice."""
        mapping = {
            "22": cls.ORDINARIA,
            "10": cls.RIDOTTA_10,
            "5": cls.RIDOTTA_5,
            "4": cls.MINIMA,
            "0": cls.ESENTE,
        }
        return mapping.get(str(codice), cls.ORDINARIA)


class ConfigContabilita:
    """Configurazione contabilità."""
    
    # === CALENDARIO ===
    ANNO_FISCALE_INIZIO_MESE: int = 1  # Gennaio
    GIORNO_CHIUSURA_STIPENDI: int = 27
    GIORNI_SCADENZA_DEFAULT: int = 30
    GIORNI_PREAVVISO_SCADENZA: int = 7
    
    # === LIMITI ===
    LIMITE_CONTANTI: float = 4999.99  # Limite pagamento contanti
    LIMITE_RITENUTA_ACCONTO: float = 77.47  # Soglia ritenuta
    
    # === PERCENTUALI ===
    RITENUTA_ACCONTO_PROFESSIONISTI: float = 0.20  # 20%
    RITENUTA_ACCONTO_AGENTI: float = 0.23  # 23% sul 50%
    CONTRIBUTO_INPS_GESTIONE_SEPARATA: float = 0.2672  # 26.72%
    
    # === CODICI TRIBUTO F24 COMUNI ===
    CODICI_TRIBUTO_F24: Dict[str, str] = {
        "1001": "Ritenute su redditi di lavoro dipendente",
        "1040": "Ritenute su redditi di lavoro autonomo",
        "1712": "Acconto imposta sostitutiva TFR",
        "1713": "Saldo imposta sostitutiva TFR",
        "3800": "IRAP - Acconto prima rata",
        "3801": "Addizionale regionale IRPEF",
        "3844": "Addizionale comunale IRPEF - Acconto",
        "3848": "Addizionale comunale IRPEF - Saldo",
        "6099": "Versamento IVA sulla base della dichiarazione annuale",
        "6001": "Versamento IVA mensile gennaio",
        "6002": "Versamento IVA mensile febbraio",
        "6003": "Versamento IVA mensile marzo",
        # ... altri mesi
        "6031": "Versamento IVA trimestrale 1° trimestre",
        "6032": "Versamento IVA trimestrale 2° trimestre",
        "6033": "Versamento IVA trimestrale 3° trimestre",
        "6034": "Versamento IVA trimestrale 4° trimestre",
        "6035": "Versamento IVA trimestrale - acconto",
    }


class TipiDocumentoSDI:
    """Tipi documento SDI (Fattura elettronica)."""
    
    TIPI: Dict[str, str] = {
        "TD01": "Fattura",
        "TD02": "Acconto/Anticipo su fattura",
        "TD03": "Acconto/Anticipo su parcella",
        "TD04": "Nota di Credito",
        "TD05": "Nota di Debito",
        "TD06": "Parcella",
        "TD07": "Fattura semplificata",
        "TD08": "Nota di credito semplificata",
        "TD09": "Nota di debito semplificata",
        "TD10": "Fattura acquisto intra beni",
        "TD11": "Fattura acquisto intra servizi",
        "TD12": "Doc riepilogativo acquisti Iva non imponibile",
        "TD16": "Integrazione fattura reverse charge interno",
        "TD17": "Integrazione/autofattura acquisto servizi estero",
        "TD18": "Integrazione acquisto beni intra",
        "TD19": "Integrazione/autofattura acquisto beni ex art.17",
        "TD20": "Autofattura regolarizzazione/denuncia",
        "TD21": "Autofattura splafonamento",
        "TD22": "Estrazione beni da Deposito IVA",
        "TD23": "Estrazione beni da Deposito IVA con versamento",
        "TD24": "Fattura differita art.21 c.4 lett.a",
        "TD25": "Fattura differita art.21 c.4 terzo periodo lett.b",
        "TD26": "Cessione beni ammortizzabili/passaggi interni",
        "TD27": "Fattura autoconsumo/cessioni gratuite",
    }
    
    # Tipi che sono note di credito
    NOTE_CREDITO: List[str] = ["TD04", "TD08"]
    
    # Tipi che sono note di debito
    NOTE_DEBITO: List[str] = ["TD05", "TD09"]
    
    @classmethod
    def is_nota_credito(cls, tipo: str) -> bool:
        return tipo in cls.NOTE_CREDITO
    
    @classmethod
    def is_nota_debito(cls, tipo: str) -> bool:
        return tipo in cls.NOTE_DEBITO
    
    @classmethod
    def get_descrizione(cls, tipo: str) -> str:
        return cls.TIPI.get(tipo, tipo)


# === SINGLETON INSTANCES ===
azienda = AziendaConfig()
aliquote_iva = AliquoteIVA()
config_contabilita = ConfigContabilita()
tipi_documento = TipiDocumentoSDI()

# === SHORTCUT PER ACCESSO VELOCE ===
PIVA_AZIENDA = azienda.PARTITA_IVA
CF_AZIENDA = azienda.CODICE_FISCALE
EMAIL_AZIENDA = azienda.EMAIL
RAGIONE_SOCIALE_AZIENDA = azienda.RAGIONE_SOCIALE

IVA_22 = aliquote_iva.ORDINARIA
IVA_10 = aliquote_iva.RIDOTTA_10
IVA_4 = aliquote_iva.MINIMA
