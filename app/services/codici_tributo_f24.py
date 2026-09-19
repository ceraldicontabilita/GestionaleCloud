"""
Dizionario completo dei codici tributo F24
Fonte: Agenzia delle Entrate + INPS + Ricerca web 2025

LOGICA CORRETTA:
- Se importo è in colonna DEBITO → è un VERSAMENTO (si paga)
- Se importo è in colonna CREDITO → è una COMPENSAZIONE (si scala)
- Il saldo può essere:
  * + (positivo) = DEBITO da versare
  * - (negativo) = CREDITO che riduce il totale
"""
from typing import Dict, Any, List

CODICI_TRIBUTO_F24 = {
    # ==================== ERARIO - IRPEF ====================
    "1001": {
        "descrizione": "Ritenute su retribuzioni, pensioni, trasferte, mensilità aggiuntive",
        "tipo": "misto",
        "sezione": "ERARIO",
        "scadenza": "16 del mese successivo"
    },
    "1002": {
        "descrizione": "Ritenute su emolumenti arretrati",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1012": {
        "descrizione": "Ritenute su indennità per cessazione di rapporto di lavoro",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1040": {
        "descrizione": "Ritenute su redditi di lavoro autonomo: compensi per l'esercizio di arti e professioni",
        "tipo": "misto",
        "sezione": "ERARIO",
        "scadenza": "16 del mese successivo"
    },
    # 1627/1631/1704: descrizioni ripristinate al testo in uso in produzione
    # (dizionario locale di parser_f24 prima della delega al registro unico).
    "1627": {
        "descrizione": "Eccedenza versamenti ritenute lavoro dipendente",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1631": {
        "descrizione": "Somme rimborsate sostituto assistenza fiscale",
        "tipo": "credito",
        "sezione": "ERARIO"
    },
    # 1704 è un CREDITO, non IVA né costo (CLAUDE.md, "F24, tributi, dichiarazioni").
    "1704": {
        "descrizione": "Credito somma art.1 c.4 L. 207/2024",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1713": {
        "descrizione": "Saldo imposte sostitutive su TFR",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1714": {
        "descrizione": "Acconto imposte sostitutive su TFR",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    
    # ==================== ERARIO - IVA ====================
    "6001": {
        "descrizione": "IVA - Versamento mensile gennaio",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 febbraio"
    },
    "6002": {
        "descrizione": "IVA - Versamento mensile febbraio",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 marzo"
    },
    "6003": {
        "descrizione": "IVA - Versamento mensile marzo",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 aprile"
    },
    "6004": {
        "descrizione": "IVA - Versamento mensile aprile",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 maggio"
    },
    "6005": {
        "descrizione": "IVA - Versamento mensile maggio",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 giugno"
    },
    "6006": {
        "descrizione": "IVA - Versamento mensile giugno",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 luglio"
    },
    "6007": {
        "descrizione": "IVA - Versamento mensile luglio",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 agosto"
    },
    "6008": {
        "descrizione": "IVA - Versamento mensile agosto",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 settembre"
    },
    "6009": {
        "descrizione": "IVA - Versamento mensile settembre",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 ottobre"
    },
    "6010": {
        "descrizione": "IVA - Versamento mensile ottobre",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 novembre"
    },
    "6011": {
        "descrizione": "IVA - Versamento mensile novembre",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 dicembre"
    },
    "6012": {
        "descrizione": "IVA - Versamento mensile dicembre",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 gennaio anno successivo"
    },
    "6099": {
        "descrizione": "IVA - Versamento annuale",
        "tipo": "debito",
        "sezione": "ERARIO"
    },
    
    # ==================== INPS ====================
    "5100": {
        "descrizione": "Contributi previdenziali INPS lavoratori dipendenti",
        "tipo": "misto",
        "sezione": "INPS",
        "causali": ["DM10", "CXX", "M100"],
        "scadenza": "16 del mese successivo"
    },
    "RC01": {
        "descrizione": "Contributi INPS artigiani",
        "tipo": "debito",
        "sezione": "INPS"
    },
    "CP01": {
        "descrizione": "Contributi INPS commercianti",
        "tipo": "debito",
        "sezione": "INPS"
    },
    "PXX": {
        "descrizione": "Contributi INPS gestione separata",
        "tipo": "debito",
        "sezione": "INPS"
    },
    
    # ==================== REGIONI ====================
    "3800": {
        "descrizione": "Imposta regionale sulle attività produttive - saldo",
        "tipo": "misto",
        "sezione": "REGIONI"
    },
    # 3801/3802: testi ripristinati a quelli in uso in produzione. L'abbinamento
    # (quale dei due è il sostituto d'imposta e quale l'autotassazione) è
    # da verificare con la fonte ufficiale AE: qui non si riformula nulla di
    # propria iniziativa, si tiene il valore che l'utente già vedeva.
    "3801": {
        "descrizione": "Addizionale regionale IRPEF - sostituto d'imposta",
        "tipo": "debito",
        "sezione": "REGIONI"
    },
    "3802": {
        "descrizione": "Addizionale regionale IRPEF - autotassazione",
        "tipo": "misto",
        "sezione": "REGIONI",
        "scadenza": "16 del mese successivo"
    },
    "3796": {
        "descrizione": "Addizionale regionale IRPEF rimborsata",
        "tipo": "credito",
        "sezione": "REGIONI"
    },
    # 3800 = saldo, 3812 = acconto prima rata, 3813 = acconto seconda rata:
    # descrizioni ripristinate al testo in uso in produzione (il registro
    # duplicava "IRAP saldo" su 3800 e 3813).
    "3812": {
        "descrizione": "IRAP acconto prima rata",
        "tipo": "debito",
        "sezione": "REGIONI"
    },
    "3813": {
        "descrizione": "IRAP acconto seconda rata o unica soluzione",
        "tipo": "misto",
        "sezione": "REGIONI"
    },
    
    # ==================== IMU / TASI / ADDIZIONALE COMUNALE ====================
    "3847": {
        "descrizione": "Addizionale comunale IRPEF - acconto",
        "tipo": "misto",
        "sezione": "IMU",
        "scadenza": "16 del mese successivo"
    },
    "3848": {
        "descrizione": "Addizionale comunale IRPEF - saldo",
        "tipo": "misto",
        "sezione": "IMU",
        "scadenza": "16 del mese successivo"
    },
    "3797": {
        "descrizione": "Addizionale comunale IRPEF rimborsata",
        "tipo": "credito",
        "sezione": "IMU"
    },
    # 3916 = aree fabbricabili quota COMUNE: il registro duplicava il significato
    # di 3925 (fabbricati gruppo D - STATO). Testo ripristinato a quello in uso
    # in produzione.
    "3916": {
        "descrizione": "IMU aree fabbricabili - comune",
        "tipo": "debito",
        "sezione": "IMU"
    },
    "3918": {
        "descrizione": "IMU - imposta municipale propria per altri fabbricati - COMUNE",
        "tipo": "debito",
        "sezione": "IMU"
    },
    "3914": {
        "descrizione": "IMU - imposta municipale propria per terreni - COMUNE",
        "tipo": "debito",
        "sezione": "IMU"
    },
    "3925": {
        "descrizione": "IMU - imposta municipale propria per immobili ad uso produttivo classificati D - STATO",
        "tipo": "debito",
        "sezione": "IMU"
    },
    "3930": {
        "descrizione": "IMU - imposta municipale propria per immobili ad uso produttivo classificati D - COMUNE",
        "tipo": "debito",
        "sezione": "IMU"
    },
    
    # ==================== INAIL ====================
    "8001": {
        "descrizione": "Regolarizzazione premio INAIL",
        "tipo": "debito",
        "sezione": "INAIL"
    },
    "8002": {
        "descrizione": "Prima rata premio INAIL",
        "tipo": "debito",
        "sezione": "INAIL"
    },
    "8003": {
        "descrizione": "Seconda rata premio INAIL",
        "tipo": "debito",
        "sezione": "INAIL"
    },
    "8004": {
        "descrizione": "Terza rata premio INAIL",
        "tipo": "debito",
        "sezione": "INAIL"
    },

    # ==================== ERARIO - migrati da parser_f24.py (fix duplicazione 19/09/2026) ====================
    "1004": {
        "descrizione": "Ritenute su conguaglio TFR",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1018": {
        "descrizione": "Ritenute su prestazioni pensionistiche complementari (D.Lgs. 252/2005)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1019": {
        "descrizione": "Ritenute 4% condominio sostituto d'imposta - acconto IRPEF",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1020": {
        "descrizione": "Ritenute 4% condominio - IRES",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1036": {
        "descrizione": "Ritenute su utili distribuiti a persone fisiche non residenti",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1039": {
        "descrizione": "Ritenuta bonifici oneri deducibili/detrazioni (art.25 DL 78/2010)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1045": {
        "descrizione": "Ritenute su contributi da regioni, province, comuni",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1049": {
        "descrizione": "Ritenuta creditore pignoratizio (art.21 c.15 L.449/97)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1050": {
        "descrizione": "Ritenute su premi riscatto assicurazioni vita",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1052": {
        "descrizione": "Indennità di esproprio/occupazione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1058": {
        "descrizione": "Ritenute su plusvalenze cessioni a termine valute estere",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1065": {
        "descrizione": "Ritenuta 5% rendite AVS e LLP (art.76 L.413/1991)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1066": {
        "descrizione": "Ritenute su trattamenti pensionistici dopo conguaglio fine anno",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1120": {
        "descrizione": "Imposta sostitutiva IRES/IRAP SIIQ e SIINQ",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1121": {
        "descrizione": "Imposta sostitutiva conferimenti SIIQ/SIINQ/fondi immobiliari",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1132": {
        "descrizione": "IRES rideterminata plusvalenza cessione partecipazioni",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1301": {
        "descrizione": "Ritenute retribuzioni Valle d'Aosta impianti fuori regione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1302": {
        "descrizione": "Ritenute emolumenti arretrati Valle d'Aosta",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1304": {
        "descrizione": "Eccedenza ritenute Valle d'Aosta effettuate in regione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1312": {
        "descrizione": "Ritenute TFR Valle d'Aosta impianti fuori regione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1628": {
        "descrizione": "Eccedenza versamenti ritenute lavoro autonomo",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1630": {
        "descrizione": "Interessi dilazione IRPEF assistenza fiscale",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1633": {
        "descrizione": "Credito canoni locazione (art.16 TUIR)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1634": {
        "descrizione": "Credito ritenute IRPEF personale (art.4 DL 457/97)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1655": {
        "descrizione": "Recupero somme art.1 DL 66/2014",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1668": {
        "descrizione": "Interessi pagamento dilazionato importi rateizzabili",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1678": {
        "descrizione": "Eccedenza versamenti ritenute erariali compensazione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1680": {
        "descrizione": "Ritenute capitali assicurazione vita",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1684": {
        "descrizione": "Addizionale bonus/stock options (art.33 DL 78/2010)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1699": {
        "descrizione": "Recupero premio dipendenti art.63 DL 18/2020",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1701": {
        "descrizione": "Credito trattamento integrativo (DL 3/2020)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1702": {
        "descrizione": "Credito trattamento integrativo lavoro notturno/festivo turistico",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1703": {
        "descrizione": "Credito bonus lavoratori dipendenti (DL 113/2024)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1851": {
        "descrizione": "IVAFE attività finanziarie estero - Conv. Santa Sede",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1852": {
        "descrizione": "IVAFE attività finanziarie estero - acconto Conv. Santa Sede",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1854": {
        "descrizione": "Imposta sostitutiva lezioni private - acconto (L. 145/2018)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1868": {
        "descrizione": "IRAP riallineamento principi contabili (D.Lgs. 192/2024)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1909": {
        "descrizione": "Interessi ravvedimento quota IRES Sicilia",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1914": {
        "descrizione": "Ritenute TFR impianti Valle d'Aosta",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1919": {
        "descrizione": "Ritenuta locazioni brevi (art.4 DL 50/2017)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1920": {
        "descrizione": "Ritenute retribuzioni impianti Valle d'Aosta",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1921": {
        "descrizione": "Ritenute emolumenti arretrati impianti Valle d'Aosta",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1928": {
        "descrizione": "Ritenute interessi banche Valle d'Aosta",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1941": {
        "descrizione": "Interessi ravvedimento acconto tassazione separata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1962": {
        "descrizione": "Eccedenza ritenute Valle d'Aosta effettuate fuori regione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1984": {
        "descrizione": "Ravvedimento importi rateizzati erariali - interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1987": {
        "descrizione": "Ravvedimento importi rateizzati IRAP - interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1988": {
        "descrizione": "Interessi ravvedimento quota IRPEF Sicilia",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1989": {
        "descrizione": "Interessi ravvedimento IRPEF (art.13 D.Lgs. 472/97)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1990": {
        "descrizione": "Interessi ravvedimento IRES (art.13 D.Lgs. 472/97)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1991": {
        "descrizione": "Interessi ravvedimento IVA (art.13 D.Lgs. 472/97)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1993": {
        "descrizione": "Interessi ravvedimento IRAP (art.13 D.Lgs. 472/97)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    # Corretti il 19/09/2026: erano ruotati di uno. Il saldo e' il 2001, non
    # il 2003 — cosi' com'era, ogni F24 IRES letto dal parser mostrava un
    # acconto al posto di un saldo e viceversa. Fonte: Agenzia delle Entrate.
    "2001": {
        "descrizione": "IRES saldo",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2002": {
        "descrizione": "IRES acconto prima rata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2003": {
        "descrizione": "IRES acconto seconda rata o unica soluzione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2004": {
        "descrizione": "Addizionale IRES art.31 DL 185/2008 - acconto prima rata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2005": {
        "descrizione": "Addizionale IRES art.31 DL 185/2008 - acconto seconda rata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2006": {
        "descrizione": "Addizionale IRES art.31 DL 185/2008 - saldo",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2007": {
        "descrizione": "Maggior acconto I rata IRES (L. 207/2024)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2008": {
        "descrizione": "Maggior acconto II rata IRES (L. 207/2024)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2010": {
        "descrizione": "Addizionale IRES settore petrolifero/gas - acconto prima rata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2011": {
        "descrizione": "Addizionale IRES settore petrolifero/gas - acconto seconda rata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2012": {
        "descrizione": "Addizionale IRES settore petrolifero/gas - saldo",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2013": {
        "descrizione": "Addizionale IRES 4% petrolifero/gas - acconto prima rata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2014": {
        "descrizione": "Addizionale IRES 4% petrolifero/gas - acconto seconda rata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2015": {
        "descrizione": "Addizionale IRES 4% petrolifero/gas - saldo",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2016": {
        "descrizione": "Recupero IRES decadenza agevolazioni start-up innovative",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2017": {
        "descrizione": "Recupero addizionale IRES petrolifero decadenza start-up",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2018": {
        "descrizione": "Maggiorazione IRES - acconto prima rata (DL 138/2011)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2019": {
        "descrizione": "Maggiorazione IRES - acconto seconda rata (DL 138/2011)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2020": {
        "descrizione": "Maggiorazione IRES - saldo (DL 138/2011)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2022": {
        "descrizione": "Recupero IRES decadenza agevolazioni ZES (L. 178/2020)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2025": {
        "descrizione": "Addizionale IRES intermediari finanziari - saldo (L. 208/2015)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2026": {
        "descrizione": "Imposta rateizzata exit-tax IRES (art.166 TUIR)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2027": {
        "descrizione": "Exit-tax maggiorazione IRES società di comodo",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2028": {
        "descrizione": "Exit-tax addizionale IRES settore petrolifero/gas",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2030": {
        "descrizione": "Exit-tax addizionale IRES enti creditizi/finanziari/assicurativi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2031": {
        "descrizione": "Quota IRES impianti Sicilia - acconto prima rata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2032": {
        "descrizione": "Quota IRES impianti Sicilia - acconto seconda rata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2033": {
        "descrizione": "Quota IRES impianti Sicilia - saldo",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2041": {
        "descrizione": "Addizionale IRES intermediari finanziari - acconto prima rata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2042": {
        "descrizione": "Addizionale IRES intermediari finanziari - acconto seconda rata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2043": {
        "descrizione": "Maggior acconto I rata addizionale IRES intermediari (L. 207/2024)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2044": {
        "descrizione": "Maggior acconto II rata addizionale IRES intermediari (L. 207/2024)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2045": {
        "descrizione": "Addizionale IRES redditi concessione - acconto prima rata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2046": {
        "descrizione": "Addizionale IRES redditi concessione - acconto seconda rata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2047": {
        "descrizione": "Addizionale IRES redditi concessione - saldo",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2048": {
        "descrizione": "IRES L. 207/2024 - acconto seconda rata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2049": {
        "descrizione": "IRES L. 207/2024 - saldo",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2501": {
        "descrizione": "Imposta sostitutiva rivalutazione TFR 17% - acconto",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2502": {
        "descrizione": "Imposta sostitutiva rivalutazione TFR 17% - saldo",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2503": {
        "descrizione": "Imposta sostitutiva TFR forme pensionistiche",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "2691": {
        "descrizione": "Tributo straordinario soggetti IRPEG",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3805": {
        "descrizione": "Interessi pagamento dilazionato tributi regionali",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3850": {
        "descrizione": "Diritto camerale annuale",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3851": {
        "descrizione": "Interessi diritto camerale",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3852": {
        "descrizione": "Sanzioni diritto camerale",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3858": {
        "descrizione": "IRAP versamento mensile (art.10-bis D.Lgs. 446/97)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3881": {
        "descrizione": "Maggior acconto I rata IRAP (L. 207/2024)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3882": {
        "descrizione": "Maggior acconto II rata IRAP (L. 207/2024)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3883": {
        "descrizione": "IRAP compensazione credito (L. 190/2014)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3912": {
        "descrizione": "IMU abitazione principale",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3913": {
        "descrizione": "IMU fabbricati rurali strumentali - comune",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3915": {
        "descrizione": "IMU terreni - Stato",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3917": {
        "descrizione": "IMU aree fabbricabili - Stato",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3919": {
        "descrizione": "IMU interessi accertamento - comune",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3920": {
        "descrizione": "IMU sanzioni accertamento - comune",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3923": {
        "descrizione": "IMU imposta - comune",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3924": {
        "descrizione": "IMU imposta - Stato",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3944": {
        "descrizione": "TARES",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3950": {
        "descrizione": "TARI",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3958": {
        "descrizione": "TASI abitazione principale",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3959": {
        "descrizione": "TASI fabbricati rurali strumentali",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3960": {
        "descrizione": "TASI aree fabbricabili",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3961": {
        "descrizione": "TASI altri fabbricati",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3962": {
        "descrizione": "TASI interessi accertamento",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "3963": {
        "descrizione": "TASI sanzioni accertamento",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4001": {
        "descrizione": "IRPEF saldo",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4002": {
        "descrizione": "Maggiore imposta IRPEF rideterminazione reddito agevolato",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4003": {
        "descrizione": "Addizionale IRPEF art.31 DL 185/2008 - acconto prima rata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4004": {
        "descrizione": "Addizionale IRPEF art.31 DL 185/2008 - acconto seconda rata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4005": {
        "descrizione": "Addizionale IRPEF art.31 DL 185/2008 - saldo",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4033": {
        "descrizione": "IRPEF acconto prima rata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4034": {
        "descrizione": "IRPEF acconto seconda rata o unica soluzione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4036": {
        "descrizione": "Quota IRPEF impianti Sicilia - acconto prima rata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4037": {
        "descrizione": "Quota IRPEF impianti Sicilia - acconto seconda rata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4038": {
        "descrizione": "Quota IRPEF impianti Sicilia - saldo",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4040": {
        "descrizione": "Imposta redditi tassazione separata da pignoramento/sequestro",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4049": {
        "descrizione": "Imposta rateizzata plusvalenza exit-tax IRPEF",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4050": {
        "descrizione": "Ritenute d'acconto non operate - lavoratori autonomi (DL 23/2020)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4068": {
        "descrizione": "CPB soggetti ISA - maggiorazione acconto IRPEF (D.Lgs. 13/2024)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4069": {
        "descrizione": "CPB soggetti ISA non PF - maggiorazione acconto (D.Lgs. 13/2024)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4070": {
        "descrizione": "CPB maggiorazione acconto IRAP (D.Lgs. 13/2024)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4072": {
        "descrizione": "CPB forfetari - maggiorazione acconto (D.Lgs. 13/2024)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4200": {
        "descrizione": "Acconto imposte redditi tassazione separata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4201": {
        "descrizione": "Acconto tassazione separata trattenuta sostituto",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4330": {
        "descrizione": "IRPEF acconto sostituto Valle d'Aosta fuori regione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4331": {
        "descrizione": "IRPEF saldo sostituto Valle d'Aosta fuori regione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4332": {
        "descrizione": "Rimborso erariali sostituto Valle d'Aosta fuori regione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4700": {
        "descrizione": "Restituzione bonus incapienti non spettante (art.44 DL 159/2007)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4711": {
        "descrizione": "Restituzione bonus straordinario famiglie non spettante (DL 185/2008)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4722": {
        "descrizione": "Imposta CFC - IRPEF saldo (art.127-bis TUIR)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4723": {
        "descrizione": "Imposta CFC - IRPEF primo acconto",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4724": {
        "descrizione": "Imposta CFC - IRPEF secondo acconto",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4725": {
        "descrizione": "Adeguamento IRPEF parametri/studi settore (art.33 DL 269/2003)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4726": {
        "descrizione": "Maggiorazione 3% adeguamento studi settore persone fisiche",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4730": {
        "descrizione": "IRPEF acconto trattenuta sostituto",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4731": {
        "descrizione": "IRPEF saldo trattenuta sostituto",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4932": {
        "descrizione": "IRPEF saldo sostituto impianti Valle d'Aosta",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4933": {
        "descrizione": "IRPEF acconto sostituto impianti Valle d'Aosta",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4934": {
        "descrizione": "Ritenute post-conguaglio Valle d'Aosta versate fuori",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4935": {
        "descrizione": "Ritenute post-conguaglio versate Valle d'Aosta maturate fuori",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "4936": {
        "descrizione": "Rimborso erariali sostituto Valle d'Aosta",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "5063": {
        "descrizione": "Recupero aiuto Stato esonero IRAP saldo - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "5064": {
        "descrizione": "Recupero aiuto Stato esonero IRAP saldo - sanzione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "5065": {
        "descrizione": "Recupero aiuto Stato esonero IRAP acconto - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "5066": {
        "descrizione": "Recupero aiuto Stato esonero IRAP acconto - sanzione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6013": {
        "descrizione": "IVA acconto mensile",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6031": {
        "descrizione": "IVA I trimestre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6032": {
        "descrizione": "IVA II trimestre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6033": {
        "descrizione": "IVA III trimestre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6034": {
        "descrizione": "IVA IV trimestre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6035": {
        "descrizione": "IVA acconto",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6036": {
        "descrizione": "Credito IVA I trimestre (art.38-bis DPR 633/72)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6037": {
        "descrizione": "Credito IVA II trimestre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6038": {
        "descrizione": "Credito IVA III trimestre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6040": {
        "descrizione": "IVA PA scissione pagamenti (art.17-ter DPR 633/72)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6041": {
        "descrizione": "IVA PA/società scissione pagamenti attività commerciali",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6043": {
        "descrizione": "IVA acquisti modello INTRA 12 (art.49 DL 331/93)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6044": {
        "descrizione": "IVA immissione consumo deposito fiscale (L. 205/2017)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6045": {
        "descrizione": "IVA inversione contabile settore logistica (L. 207/2024)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6201": {
        "descrizione": "IVA immatricolazione auto UE - gennaio",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6202": {
        "descrizione": "IVA immatricolazione auto UE - febbraio",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6203": {
        "descrizione": "IVA immatricolazione auto UE - marzo",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6204": {
        "descrizione": "IVA immatricolazione auto UE - aprile",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6205": {
        "descrizione": "IVA immatricolazione auto UE - maggio",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6206": {
        "descrizione": "IVA immatricolazione auto UE - giugno",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6207": {
        "descrizione": "IVA immatricolazione auto UE - luglio",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6208": {
        "descrizione": "IVA immatricolazione auto UE - agosto",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6209": {
        "descrizione": "IVA immatricolazione auto UE - settembre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6210": {
        "descrizione": "IVA immatricolazione auto UE - ottobre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6211": {
        "descrizione": "IVA immatricolazione auto UE - novembre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6212": {
        "descrizione": "IVA immatricolazione auto UE - dicembre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6231": {
        "descrizione": "IVA immatricolazione auto UE - I trimestre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6232": {
        "descrizione": "IVA immatricolazione auto UE - II trimestre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6233": {
        "descrizione": "IVA immatricolazione auto UE - III trimestre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6234": {
        "descrizione": "IVA immatricolazione auto UE - IV trimestre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6301": {
        "descrizione": "IVA estrazione deposito - gennaio",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6302": {
        "descrizione": "IVA estrazione deposito - febbraio",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6303": {
        "descrizione": "IVA estrazione deposito - marzo",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6304": {
        "descrizione": "IVA estrazione deposito - aprile",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6305": {
        "descrizione": "IVA estrazione deposito - maggio",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6306": {
        "descrizione": "IVA estrazione deposito - giugno",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6307": {
        "descrizione": "IVA estrazione deposito - luglio",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6308": {
        "descrizione": "IVA estrazione deposito - agosto",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6309": {
        "descrizione": "IVA estrazione deposito - settembre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6310": {
        "descrizione": "IVA estrazione deposito - ottobre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6311": {
        "descrizione": "IVA estrazione deposito - novembre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6312": {
        "descrizione": "IVA estrazione deposito - dicembre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6492": {
        "descrizione": "IVA rettifica contribuenti minimi franchigia",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6493": {
        "descrizione": "Integrazione IVA",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6494": {
        "descrizione": "ISA integrazione IVA",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6495": {
        "descrizione": "IVA regolarizzazione magazzino",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6496": {
        "descrizione": "IVA adeguamento concordato preventivo",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6497": {
        "descrizione": "IVA rettifica contribuenti minimi (L. 244/2007)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6501": {
        "descrizione": "IVA vendita immobili espropriazione forzata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6720": {
        "descrizione": "Subfornitura IVA mensile - I trimestre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6721": {
        "descrizione": "Subfornitura IVA mensile - II trimestre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6722": {
        "descrizione": "Subfornitura IVA mensile - III trimestre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6723": {
        "descrizione": "Subfornitura IVA mensile - IV trimestre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6724": {
        "descrizione": "Subfornitura IVA trimestrale - I trimestre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6725": {
        "descrizione": "Subfornitura IVA trimestrale - II trimestre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6726": {
        "descrizione": "Subfornitura IVA trimestrale - III trimestre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6727": {
        "descrizione": "Subfornitura IVA trimestrale - IV trimestre",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6728": {
        "descrizione": "Imposta sugli intrattenimenti",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6729": {
        "descrizione": "IVA forfettaria intrattenimenti",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6781": {
        "descrizione": "Eccedenza ritenute lavoro dipendente mod. 770",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6782": {
        "descrizione": "Eccedenza ritenute lavoro autonomo mod. 770",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6783": {
        "descrizione": "Eccedenza ritenute redditi capitale mod. 770",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6790": {
        "descrizione": "Credito ritenute risparmio pagamenti interessi UE",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "6830": {
        "descrizione": "Credito IRPEF ritenute riattribuite soci art.5 TUIR",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "7452": {
        "descrizione": "IRAP recupero credito compensazione - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "7453": {
        "descrizione": "IRAP recupero credito compensazione - sanzione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "8083": {
        "descrizione": "Sanzione ravvedimento quota IRES Sicilia",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "8084": {
        "descrizione": "Restituzione somme Agenzia Entrate - imposta",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "8085": {
        "descrizione": "Restituzione somme Agenzia Entrate - interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "8086": {
        "descrizione": "Restituzione somme Agenzia Entrate - sanzioni",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "8901": {
        "descrizione": "Sanzione pecuniaria IRPEF",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "8902": {
        "descrizione": "Interessi ravvedimento IRPEF",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "8903": {
        "descrizione": "Sanzione pecuniaria addizionale regionale IRPEF",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "8904": {
        "descrizione": "Sanzione pecuniaria IVA",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "8906": {
        "descrizione": "Sanzione pecuniaria sostituti d'imposta",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "8907": {
        "descrizione": "Sanzione pecuniaria IRAP",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "8911": {
        "descrizione": "Sanzione pecuniaria IRAP",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "8913": {
        "descrizione": "Interessi ravvedimento IRAP",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "8915": {
        "descrizione": "Sanzione pecuniaria IRPEF rettifica 730",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "8918": {
        "descrizione": "Sanzione pecuniaria IRES",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "8919": {
        "descrizione": "Sanzione IRPEF art.33 DL 269/2003",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "8920": {
        "descrizione": "Sanzione IRES art.33 DL 269/2003",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "8921": {
        "descrizione": "Sanzione IVA art.33 DL 269/2003",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "8938": {
        "descrizione": "Sanzione ravvedimento quota IRPEF Sicilia",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "8941": {
        "descrizione": "Sanzione ravvedimento acconto tassazione separata",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "8947": {
        "descrizione": "Sanzione ravvedimento ritenute lavoro dipendente",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "8948": {
        "descrizione": "Sanzione ravvedimento ritenute lavoro autonomo",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "8949": {
        "descrizione": "Sanzione ravvedimento ritenute redditi capitale",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9399": {
        "descrizione": "Regolarizzazione operazioni IVA mancata fatturazione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9400": {
        "descrizione": "Spese di notifica atti impositivi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9401": {
        "descrizione": "IRPEF accertamento adesione - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9402": {
        "descrizione": "Sanzione tributi erariali accertamento adesione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9405": {
        "descrizione": "IRPEG/IRES accertamento adesione - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9409": {
        "descrizione": "Ritenute accertamento adesione - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9413": {
        "descrizione": "IVA accertamento adesione - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9415": {
        "descrizione": "IRAP accertamento con adesione - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9416": {
        "descrizione": "IRAP accertamento con adesione - sanzione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9424": {
        "descrizione": "Sanzione anagrafe tributaria codice fiscale",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9451": {
        "descrizione": "IRPEF omessa impugnazione - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9452": {
        "descrizione": "Sanzione tributi erariali omessa impugnazione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9455": {
        "descrizione": "IRPEG/IRES omessa impugnazione - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9459": {
        "descrizione": "Ritenute omessa impugnazione - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9463": {
        "descrizione": "IVA omessa impugnazione - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9466": {
        "descrizione": "IRAP omessa impugnazione - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9467": {
        "descrizione": "IRAP omessa impugnazione - sanzione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9475": {
        "descrizione": "Sanzione decadenza rateazione erariali (art.29 DL 78/2010)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9478": {
        "descrizione": "Sanzione decadenza rateazione IRAP (art.29 DL 78/2010)",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9501": {
        "descrizione": "IRPEF conciliazione giudiziale - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9502": {
        "descrizione": "Sanzione tributi erariali conciliazione giudiziale",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9507": {
        "descrizione": "Ritenute conciliazione giudiziale - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9509": {
        "descrizione": "IVA conciliazione giudiziale - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9512": {
        "descrizione": "IRAP conciliazione giudiziale - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9513": {
        "descrizione": "IRAP conciliazione giudiziale - sanzione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9601": {
        "descrizione": "Sanzione pecuniaria erariali definizione sanzioni",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9607": {
        "descrizione": "Sanzione pecuniaria IRAP definizione sanzioni",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9695": {
        "descrizione": "Sanzione componenti reddituali negativi non scambiati",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9701": {
        "descrizione": "IVA e interessi - altri tipi definizione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9711": {
        "descrizione": "Recupero IVA forfettaria intrattenimenti - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9712": {
        "descrizione": "Recupero IVA forfettaria intrattenimenti - sanzioni",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9713": {
        "descrizione": "Interessi rateazione recupero IVA intrattenimenti",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9900": {
        "descrizione": "IRPEF adesione verbale constatazione - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9901": {
        "descrizione": "IRPEG/IRES adesione verbale constatazione - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9903": {
        "descrizione": "Ritenute adesione verbale constatazione - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9904": {
        "descrizione": "IVA adesione verbale constatazione - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9905": {
        "descrizione": "Sanzione erariali adesione verbale constatazione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9908": {
        "descrizione": "IRAP adesione verbale constatazione - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9909": {
        "descrizione": "IRAP adesione verbale constatazione - sanzione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9912": {
        "descrizione": "IRPEF adesione invito comparire - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9913": {
        "descrizione": "IRPEG/IRES adesione invito comparire - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9915": {
        "descrizione": "Ritenute adesione invito comparire - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9916": {
        "descrizione": "IVA adesione invito comparire - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9917": {
        "descrizione": "Sanzione erariali adesione invito comparire",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9920": {
        "descrizione": "IRAP adesione invito comparire - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9921": {
        "descrizione": "IRAP adesione invito comparire - sanzione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9930": {
        "descrizione": "IRPEF contenzioso art.29 DL 78/2010 - imposta",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9931": {
        "descrizione": "IRPEF contenzioso art.29 DL 78/2010 - interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9932": {
        "descrizione": "IRES contenzioso art.29 DL 78/2010 - imposta",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9933": {
        "descrizione": "IRES contenzioso art.29 DL 78/2010 - interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9934": {
        "descrizione": "IRAP contenzioso art.29 DL 78/2010 - imposta",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9935": {
        "descrizione": "IRAP contenzioso art.29 DL 78/2010 - interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9938": {
        "descrizione": "Ritenute contenzioso art.29 DL 78/2010 - imposta",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9939": {
        "descrizione": "Ritenute contenzioso art.29 DL 78/2010 - interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9944": {
        "descrizione": "IVA contenzioso art.29 DL 78/2010 - imposta",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9945": {
        "descrizione": "IVA contenzioso art.29 DL 78/2010 - interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9946": {
        "descrizione": "Ravvedimento importi rateizzati erariali - sanzione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9949": {
        "descrizione": "Ravvedimento importi rateizzati IRAP - sanzione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9950": {
        "descrizione": "IRPEF reclamo/mediazione - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9951": {
        "descrizione": "IRES reclamo/mediazione - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9953": {
        "descrizione": "IVA reclamo/mediazione - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9954": {
        "descrizione": "Sanzioni erariali reclamo/mediazione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9955": {
        "descrizione": "IRAP reclamo/mediazione art.17-bis - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9956": {
        "descrizione": "IRAP reclamo/mediazione - sanzioni",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9970": {
        "descrizione": "Sanzioni erariali contenzioso art.29 DL 78/2010",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9971": {
        "descrizione": "Sanzioni IRAP contenzioso art.29 DL 78/2010",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9974": {
        "descrizione": "Estrazione deposito IVA recupero - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9975": {
        "descrizione": "Estrazione deposito IVA - sanzione omesso versamento",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9976": {
        "descrizione": "IRPEF definizione agevolata PVC - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9977": {
        "descrizione": "IRES definizione agevolata PVC - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9978": {
        "descrizione": "IVA definizione agevolata PVC - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9979": {
        "descrizione": "Ritenute definizione agevolata PVC - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9986": {
        "descrizione": "Sanzione erariali definizione agevolata PVC",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9988": {
        "descrizione": "IRAP definizione agevolata PVC - imposta/interessi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "9990": {
        "descrizione": "IRAP definizione agevolata PVC - sanzione",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
}


def get_codice_info(codice: str) -> Dict[str, Any]:
    """
    Restituisce le informazioni complete di un codice tributo.
    
    Args:
        codice: Il codice tributo da cercare
        
    Returns:
        Dict con descrizione, tipo, sezione e altre info
    """
    return CODICI_TRIBUTO_F24.get(codice.upper(), {
        "descrizione": f"Codice tributo {codice}",
        "tipo": "unknown",
        "sezione": "UNKNOWN"
    })


def get_descrizione_tributo(codice: str) -> str:
    """
    Restituisce la descrizione di un codice tributo.
    
    Args:
        codice: Il codice tributo
        
    Returns:
        Descrizione del codice tributo
    """
    info = get_codice_info(codice)
    return info.get("descrizione", f"Codice {codice}")


def get_tipo_tributo(codice: str) -> str:
    """
    Restituisce il tipo di un codice tributo (debito/credito/misto).
    
    Args:
        codice: Il codice tributo
        
    Returns:
        Tipo del tributo
    """
    info = get_codice_info(codice)
    return info.get("tipo", "unknown")


def get_sezione_tributo(codice: str) -> str:
    """
    Restituisce la sezione F24 di un codice tributo.
    
    Args:
        codice: Il codice tributo
        
    Returns:
        Sezione F24 (ERARIO, INPS, REGIONI, IMU, INAIL)
    """
    info = get_codice_info(codice)
    return info.get("sezione", "UNKNOWN")


def get_codici_by_sezione(sezione: str) -> List[str]:
    """
    Restituisce tutti i codici tributo di una sezione.
    
    Args:
        sezione: Nome sezione (ERARIO, INPS, REGIONI, IMU, INAIL)
        
    Returns:
        Lista di codici tributo
    """
    return [
        codice for codice, info in CODICI_TRIBUTO_F24.items()
        if info.get("sezione", "").upper() == sezione.upper()
    ]


def cerca_codice_tributo(query: str) -> List[Dict[str, Any]]:
    """
    Cerca codici tributo per descrizione o codice.
    
    Args:
        query: Stringa di ricerca
        
    Returns:
        Lista di codici tributo che corrispondono
    """
    query_lower = query.lower()
    results = []
    
    for codice, info in CODICI_TRIBUTO_F24.items():
        if (query_lower in codice.lower() or 
            query_lower in info.get("descrizione", "").lower()):
            results.append({
                "codice": codice,
                **info
            })
    
    return results


def get_all_codici() -> List[Dict[str, Any]]:
    """
    Restituisce tutti i codici tributo.
    
    Returns:
        Lista di tutti i codici tributo con info
    """
    return [
        {"codice": codice, **info}
        for codice, info in CODICI_TRIBUTO_F24.items()
    ]
