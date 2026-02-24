"""
Costanti e configurazioni per il modulo Noleggio Auto.

FORNITORI SUPPORTATI:
- ALD Automotive (01924961004): Targa e contratto in descrizione linea
- ARVAL (04911190488): Targa in descrizione, codice cliente in causali
- Leasys (06714021000): Targa e modello in descrizione
- LeasePlan (02615080963): NO targa in fattura - richiede associazione manuale

CATEGORIE SPESE:
- Canoni: Canone locazione, servizi, rifatturazione, conguaglio km
- Pedaggio: Gestione pedaggi, telepass
- Verbali: Verbali, multe, sanzioni
- Bollo: Tasse automobilistiche
- Costi Extra: Penalità, addebiti extra
- Riparazioni: Sinistri, danni, carrozzeria, meccanica
"""

# Collection MongoDB per veicoli noleggio
COLLECTION = "veicoli_noleggio"

# Fornitori noleggio con P.IVA
FORNITORI_NOLEGGIO = {
    "ALD": "01924961004",
    "ARVAL": "04911190488", 
    "Leasys": "06714021000",
    "LeasePlan": "02615080963"
}

# Pattern per targhe italiane (formato: XX000XX)
TARGA_PATTERN = r'\b([A-Z]{2}\d{3}[A-Z]{2})\b'

# Keywords per categorizzazione spese
KEYWORDS_VERBALI = [
    "verbale", "sanzione", "infrazione", "violazione",
    "notifica", "multa", "divieto sosta", "ztl"
]

KEYWORDS_BOLLO = [
    "bollo", "tassa di propriet", "tassa propriet",
    "addebito bollo", "tasse automobilist"
]

KEYWORDS_PEDAGGIO = [
    "telepass", "pedaggio", "autostrad", "gestione pedagg"
]

KEYWORDS_RIPARAZIONI = [
    "sinistro", "danno", "carrozzeria", "riparazione",
    "meccanica", "manutenzione straordinaria"
]

KEYWORDS_COSTI_EXTRA = [
    "penale", "penalità", "addebito extra",
    "sostituzione pneumatici", "chilometr"
]

# Pattern per marca/modello veicoli
MARCA_PATTERNS = [
    (r'STELVIO[^,\n]{0,50}', "Alfa Romeo"),
    (r'GIULIA[^,\n]{0,50}', "Alfa Romeo"),
    (r'TONALE[^,\n]{0,50}', "Alfa Romeo"),
    (r'BMW\s+(X[1-7][^,\n]{0,40})', "BMW"),
    (r'(X[1-7]\s*[xXsS]?[Dd]rive[^,\n]{0,40})', "BMW"),
    (r'MAZDA\s+(CX-?\d+[^,\n]{0,50})', "Mazda"),
    (r'(CX-?\d+[^,\n]{0,50})', "Mazda"),
]
