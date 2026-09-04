"""Mapping CANONICO verso il piano dei conti UFFICIALE CEE (§6.2/§6.3).

Regola utente (vincolante): **il piano dei conti è solo CEE** — quando si incontra un
altro schema, si usa SOLO quello ufficiale CEE (`app/services/piano_conti_ufficiale.py`,
estratto dal bilancio ufficiale Ceraldi).

Nel codice esistono due schemi INTERNI che NON sono il piano ufficiale:
  - operativo puntato (es. `05.01.01` = "Acquisto merci"): era la collezione
    `piano_conti` (31 conti, dismessa con l'audit del 03/09/2026, PR 7) ed e'
    ancora il codice usato dal motore di registrazione §6.1 e dal dizionario
    articoli. Da qui in poi e' soltanto un ALIAS del conto CEE;
  - numerico di `contabilita_italiana` (es. `400100`).
Attenzione: i codici INTERNI collidono con quelli ufficiali (nel piano ufficiale
`05` = Immobilizzazioni materiali, `55` = Acquisti). Per il bilancio/reportistica si
converte SEMPRE verso i codici ufficiali con questa tabella.

`OPERATIVO_A_UFFICIALE`: codice operativo interno → codice ufficiale CEE.

Audit del commercialista 03/09/2026 (PR 7):
- `piano_conti_cee()` e' l'UNICA lista di conti esposta dalle API (router
  `piano_conti.py`, pagina Piano dei Conti): conti CEE con il codice operativo
  come alias, saldi convertiti;
- `completa_conti_prima_nota()` assegna a ogni riga di Prima Nota il conto
  di tesoreria CEE (`conto_contabile`: 19.01.01 Banca c/c, 19.03.03 Cassa,
  19.01.05 Mastercard SumUp, 15.07.xx crediti POS) e la contropartita CEE
  per categoria (`conto_contropartita`: 33.03.01 Fornitori per Fatture/
  Assegni/PayPal, 39.07.01 Personale c/retribuzioni per Stipendi, 75.01.07.xx
  per le commissioni, ...). Un conto non presente nel piano ufficiale viene
  rifiutato, mai scritto.

  Nota sulla semantica di `conto_contabile` nelle righe di Prima Nota: le
  letture di tesoreria (`prima_nota_module/common.py::saldi_finanziari`,
  `stats.py`, `banca.py`) lo usano per capire SU QUALE CONTO REALE si muove
  il denaro (BPM, Mastercard SumUp, credito verso un gestore). Per questo la
  contropartita economica/patrimoniale sta in un campo separato: scrivere
  33.03.01 in `conto_contabile` avrebbe tolto i pagamenti fornitori dal
  saldo di Banco BPM.
"""
from typing import Any, Dict, List, Optional

from app.services import conti_pos
from app.services.piano_conti_ufficiale import CONTI_UFFICIALI, MACRO_UFFICIALE, sezione_di

# codice operativo interno (piano_conti.STRUTTURA_BASE) → codice ufficiale CEE
OPERATIVO_A_UFFICIALE: Dict[str, str] = {
    # ATTIVO
    "01.01.01": "19.03.03",   # Cassa → Cassa contanti
    "01.01.02": "19.01.01",   # Banca c/c → Banca c/c
    "01.02.01": "15.05",      # Crediti v/clienti → Crediti vari v/terzi (macro; no leaf clienti nel bilancio)
    "01.03.01": "51.01.03",   # Magazzino merci → Rimanenze di merci
    "01.04.01": "35.01",      # IVA a credito → Erario c/IVA
    "01.05.01": "41",         # Fondo ammortamento → B.II Fondi ammortamento (A7, scelta utente)
    # PASSIVO
    "02.01.01": "33.03.01",   # Debiti v/fornitori → Fornitori terzi Italia
    "02.02.01": "35.07",      # Debiti tributari → Erario c/imposte
    "02.02.02": "37.01.01",   # Debiti v/INPS → INPS dipendenti
    "02.03.01": "35.01.11",   # IVA a debito → Erario c/liquidazione IVA
    "02.04.01": "29.01.01",   # TFR → Fondo TFR
    # PATRIMONIO NETTO
    "03.01.01": "23.01.01",   # Capitale sociale
    "03.02.01": "23.01.05",   # Riserva legale
    "03.03.01": "25.01.05",   # Utile d'esercizio → Avanzo utili
    "03.03.02": "25",         # Perdita d'esercizio → Risultati dell'esercizio (macro)
    # RICAVI
    "04.01.01": "47.01.03",   # Ricavi vendite prodotti → Vendita merci
    "04.01.02": "47.01.03",   # Ricavi vendite bar → Vendita merci
    "04.01.03": "47.01.03",   # Ricavi vendite cucina → Vendita merci
    "04.02.01": "47",         # Ricavi prestazioni servizi → Vendite (macro)
    "04.03.01": "53.01",      # Proventi finanziari → Altri ricavi/proventi diversi
    # COSTI
    "05.01.01": "55.01.07",   # Acquisto merci → Acquisti merci
    "05.01.02": "55.01.01",   # Acquisto materie prime → Acquisti di materie prime
    "05.02.01": "57",         # Costi per servizi → Acquisti di servizi (macro)
    "05.02.02": "57.09",      # Utenze → Costi per utenze
    "05.02.03": "65",         # Canoni di locazione → Godimento beni di terzi (macro)
    "05.03.01": "67.01.01",   # Salari e stipendi → Retribuzioni lorde
    "05.03.02": "67.01.03",   # Contributi previdenziali → Contributi INPS
    "05.03.03": "67.01.07",   # TFR → Quote TFR dipendenti
    "05.04.01": "41",         # Ammortamento immobilizzazioni → Fondi ammortamento (macro) VERIFICARE
    "05.05.01": "75",         # Oneri finanziari → Oneri finanziari (macro)
    "05.06.01": "84",         # Imposte e tasse → Imposte dell'esercizio (macro)

    # ── Piano operativo ESTESO (categorizzazione_contabile.PIANO_CONTI_ESTESO,
    # usato dal dizionario articoli e dalle regole di categorizzazione). Ogni
    # codice operativo che il gestionale puo' produrre ha un conto CEE: nessun
    # secondo piano dei conti (audit 03/09/2026, PR 7). Le corrispondenze
    # merceologiche (bevande = merci, caffe'/farine = materie prime) vanno
    # confermate dal commercialista: sono alias, non conti nuovi.
    "01.02.02": "15.05",      # Crediti v/fornitori (anticipi) → Crediti vari v/terzi
    "01.03.02": "51.01.13",   # Magazzino materie prime → Rimanenze materie prime
    "01.04.02": "15.05",      # Ritenute subite → Crediti vari v/terzi
    "01.04.03": "35.07",      # Acconti imposte → Erario c/imposte
    "01.05.02": "15",         # Risconti attivi → Crediti vari (macro)
    "01.06.01": "05.03.51",   # Impianti e macchinari → Altri impianti e macchinari
    "01.06.02": "05.05.51",   # Attrezzature → Attrezzatura varia e minuta
    "01.06.03": "05.07.51",   # Automezzi → Altri beni materiali
    "01.06.04": "05.07.01",   # Mobili e arredi
    "01.06.05": "05.07.05",   # Macchine ufficio elettroniche
    "02.01.02": "39.07.01",   # Debiti v/dipendenti → Personale c/retribuzioni
    "02.02.03": "37.01.05",   # Debiti v/INAIL → INAIL dipendenti/collaboratori
    "02.02.04": "35.03.01",   # Debiti per ritenute → Erario c/riten. lav. dipendente
    "02.03.02": "35.01.11",   # IVA da versare → Erario c/liquidazione IVA
    "02.04.02": "27",         # Fondo rischi → Fondi rischi e oneri (macro)
    "02.05.01": "39.05",      # Ratei passivi → Debiti vari
    "02.05.02": "39.05",      # Risconti passivi → Debiti vari
    "02.06.01": "31.03.05",   # Mutui passivi → Finanz. a medio/lungo termine bancari
    "02.06.02": "31.03.05",   # Finanziamenti bancari → Finanz. a medio/lungo termine bancari
    "03.02.02": "23.01.17",   # Riserva straordinaria
    "03.04.01": "25.01.05",   # Utili portati a nuovo → Avanzo utili
    "03.04.02": "25",         # Perdite portate a nuovo → Risultati dell'esercizio (macro)
    "04.01.04": "47.01.03",   # Ricavi vendite alcolici → Vendita merci
    "04.01.05": "47.01.03",   # Ricavi vendite tabacchi → Vendita merci
    "04.03.02": "53.01",      # Interessi attivi bancari → Proventi diversi
    "04.04.01": "53.01",      # Proventi straordinari → Proventi diversi
    "04.04.02": "53.01",      # Plusvalenze → Proventi diversi
    "04.04.03": "53.01",      # Sopravvenienze attive → Proventi diversi
    "05.01.03": "55.01.07",   # Bevande alcoliche → Acquisti merci
    "05.01.04": "55.01.07",   # Bevande analcoliche → Acquisti merci
    "05.01.05": "55.01.01",   # Prodotti alimentari → Acquisti di materie prime
    "05.01.06": "55.07.51",   # Piccola utensileria → Materiale vario di consumo
    "05.01.07": "55.01.09",   # Materiali di consumo e imballaggio → Confezioni e imballi
    "05.01.08": "55.01.05",   # Pulizia e igiene → Acquisti materiali di consumo
    "05.01.09": "55.01.01",   # Caffe' e affini → Acquisti di materie prime
    "05.01.10": "55.01.01",   # Surgelati → Acquisti di materie prime
    "05.01.11": "55.01.07",   # Prodotti da forno → Acquisti merci
    "05.01.12": "55.07.13",   # Materiale edile → Materiali manutenzioni diverse
    "05.01.13": "55.01.01",   # Additivi e ingredienti → Acquisti di materie prime
    "05.02.04": "57.09.17",   # Utenze - Acqua → Acqua potabile
    "05.02.05": "57.09.13",   # Utenze - Energia elettrica
    "05.02.06": "57.09.19",   # Utenze - Gas
    "05.02.07": "57.09.01",   # Telefonia → Spese telefoniche ordinarie
    "05.02.08": "65.07.01",   # Software e cloud → Canoni licenze software
    "05.02.09": "65.05",      # Noleggi e locazioni operative → Locazioni impianti e attrezz.
    "05.02.10": "57.11.01",   # Manutenzioni → Spese manut. impianti e macchinari propri
    "05.02.11": "59.03.01",   # Carburanti e lubrificanti veicoli
    "05.02.12": "61.01.01",   # Consulenze → Consulenze amministrative e fiscali
    "05.02.13": "63.05.91",   # Assicurazioni
    "05.02.14": "63.01.01",   # Pubblicita' e marketing → Pubblicita', inserzioni e affissioni
    "05.02.15": "63.03.03",   # Omaggi e spese promozionali → Omaggi
    "05.02.16": "57.05.01",   # Trasporti su acquisti
    "05.02.17": "63.01.09",   # Spese viaggio e trasferte → Spese per alberghi e ristoranti
    "05.02.18": "63.03",      # Spese di rappresentanza (macro)
    "05.02.19": "63.05.51",   # Spese postali → Spese generali varie
    "05.02.20": "63.05.51",   # Spese condominiali → Spese generali varie
    "05.02.21": "65.07",      # Diritti SIAE e licenze → Canoni e licenze (macro)
    "05.02.22": "65.03.07",   # Noleggio automezzi → Canoni leasing automezzi
    "05.02.23": "71.03.11",   # Canoni e abbonamenti → Abbonamenti, libri e pubblicazioni
    "05.02.24": "55.07.51",   # Arredi e tappezzeria → Materiale vario di consumo
    "05.03.04": "67.03.51",   # Altri costi del personale
    "05.03.05": "67.03.51",   # Buoni pasto dipendenti → Altri costi per il personale
    "05.04.02": "41",         # Ammortamento immateriali → Fondi ammortamento (macro)
    "05.04.03": "41",         # Svalutazioni → Fondi ammortamento (macro) VERIFICARE
    "05.05.02": "75.01.07",   # Spese e commissioni bancarie
    "05.05.03": "75.03.05",   # Interessi passivi su mutui
    "05.05.04": "75.03",      # Interessi passivi su leasing → Oneri finanziari diversi
    "05.06.02": "71.01.51",   # Accise e imposte indirette → Altre imposte e tasse indirette
    "05.06.03": "84.01",      # IRES → Imposte dell'esercizio
    "05.06.04": "84.01",      # IRAP → Imposte dell'esercizio
    "05.06.05": "71.01.04",   # IMU
    "05.07.01": "71.03",      # Oneri straordinari → Altri costi di esercizio
    "05.07.02": "71.03",      # Minusvalenze → Altri costi di esercizio
    "05.07.03": "71.03",      # Sopravvenienze passive → Altri costi di esercizio
    "05.07.04": "71.03",      # Perdite su crediti → Altri costi di esercizio
}

# Gruppo del bilancio (MACRO_UFFICIALE) → categoria usata dalle pagine
# (attivo / passivo / patrimonio_netto / ricavi / costi).
_CATEGORIA_PER_GRUPPO = {
    "attivo": "attivo",
    "passivo": "passivo",
    "patrimonio_netto": "patrimonio_netto",
    "ricavi": "ricavi",
    "costi": "costi",
}

# Conti di tesoreria CEE: dove il denaro sta davvero. Su una riga di Prima
# Nota `conto_contabile` e' SEMPRE uno di questi (o un credito POS 15.07.xx).
CONTO_BANCA = conti_pos.CONTO_BPM            # 19.01.01
CONTO_CASSA = "19.03.03"
CONTO_FORNITORI = "33.03.01"
CONTO_PERSONALE_RETRIBUZIONI = "39.07.01"
CONTO_PERSONALE_LIQUIDAZIONE = "39.07.05"
CONTO_SOCI_FINANZIAMENTO = "31.03.15"
CONTO_MUTUI = "31.03.05"
CONTO_ERARIO_IMPOSTE = "35.07"
CONTO_VENDITA_MERCI = "47.01.03"
CONTO_UTENZE = "57.09"
CONTO_PROVENTI_DIVERSI = "53.01"
CONTO_CREDITI_VARI = "15.05"
CONTO_SPESE_GENERALI = "63.05.51"

_TESORERIA_PER_REGISTRO = {"banca": CONTO_BANCA, "cassa": CONTO_CASSA}

# Categoria di Prima Nota → contropartita CEE. Le chiavi sono normalizzate
# (minuscolo, spazi singoli). Un valore callable riceve (registro, tipo,
# gestore) e restituisce il codice: serve alle categorie POS, dove il conto
# dipende dal circuito, e ai trasferimenti cassa<->banca, dove dipende dal
# registro. `None` = contropartita non determinabile dalla sola categoria
# (resta da classificare, mai inventata).
_CONTROPARTITE: Dict[str, Any] = {
    # pagamenti/incassi documentali
    "fatture": CONTO_FORNITORI,
    "pagamento fornitore": CONTO_FORNITORI,
    "fornitori": CONTO_FORNITORI,
    "pagamenti fatture": CONTO_FORNITORI,
    "nota credito fornitore": CONTO_FORNITORI,
    "assegni": CONTO_FORNITORI,
    "pagamento paypal": CONTO_FORNITORI,
    "incasso cliente": CONTO_CREDITI_VARI,
    "rimborso": CONTO_PROVENTI_DIVERSI,
    "utenze": CONTO_UTENZE,
    # personale
    "stipendi": CONTO_PERSONALE_RETRIBUZIONI,
    "acconti dipendenti": CONTO_PERSONALE_RETRIBUZIONI,
    "tfr": CONTO_PERSONALE_LIQUIDAZIONE,
    # banca
    "commissioni bancarie": conti_pos.COMMISSIONI_ALTRO,
    "competenze bancarie": conti_pos.COMMISSIONI_ALTRO,
    "spese carnet assegni": conti_pos.COMMISSIONI_ALTRO,
    "finanziamento soci": CONTO_SOCI_FINANZIAMENTO,
    "rata mutuo": CONTO_MUTUI,
    "f24": CONTO_ERARIO_IMPOSTE,
    "pagamento f24": CONTO_ERARIO_IMPOSTE,
    # vendite e cassa
    "corrispettivi": CONTO_VENDITA_MERCI,
    "spese": CONTO_SPESE_GENERALI,
    # trasferimenti cassa <-> banca: la contropartita e' l'altro conto reale
    "versamento banca": lambda registro, tipo, gestore: (
        CONTO_CASSA if registro == "banca" else CONTO_BANCA),
    "storno versamento": lambda registro, tipo, gestore: (
        CONTO_CASSA if registro == "banca" else CONTO_BANCA),
    "prelevamento banca": lambda registro, tipo, gestore: (
        CONTO_CASSA if registro == "banca" else CONTO_BANCA),
    # circuiti POS (conti_pos e' il punto unico dei codici per circuito)
    "corrispettivi pos": CONTO_CASSA,
    "pos verso banca": lambda registro, tipo, gestore: conti_pos.conto_credito(gestore),
    "accrediti pos": lambda registro, tipo, gestore: conti_pos.conto_credito(gestore),
    "crediti verso gestori incassi": lambda registro, tipo, gestore: (
        conti_pos.conto_accredito(gestore) or CONTO_BANCA),
    "commissioni e spese bancarie": lambda registro, tipo, gestore: conti_pos.conto_credito(gestore),
    "rettifiche pos": lambda registro, tipo, gestore: conti_pos.conto_credito(gestore),
}


def _normalizza_categoria(categoria: Any) -> str:
    return " ".join(str(categoria or "").strip().lower().split())


def operativo_a_ufficiale(codice_operativo: str) -> Optional[str]:
    """Codice interno operativo → codice ufficiale CEE (None se ignoto)."""
    return OPERATIVO_A_UFFICIALE.get(str(codice_operativo))


def descrizione_ufficiale(codice_ufficiale: str) -> Optional[str]:
    """Descrizione del conto ufficiale (o del macro-gruppo se è un codice a 2 cifre)."""
    return CONTI_UFFICIALI.get(str(codice_ufficiale))


def conto_cee_valido(codice: Any) -> bool:
    """True se `codice` esiste nel piano ufficiale (conto o macro-gruppo)."""
    testo = str(codice or "").strip()
    return bool(testo) and (testo in CONTI_UFFICIALI or testo in MACRO_UFFICIALE)


def alias_operativi(codice_ufficiale: str) -> List[str]:
    """Codici operativi (storici) che confluiscono nel conto CEE, ordinati."""
    codice = str(codice_ufficiale or "")
    return sorted(op for op, uff in OPERATIVO_A_UFFICIALE.items() if uff == codice)


def risolvi_codice_cee(codice: Any, preferisci_operativo: bool = True) -> Optional[str]:
    """Accetta un codice CEE o un alias operativo e restituisce il CEE.

    Otto codici operativi collidono con codici CEE veri (es. operativo
    ``05.01.09`` "Acquisto caffe'" vs CEE ``05.01.09`` "Costruzioni leggere").
    Con ``preferisci_operativo`` (default: i saldi, il dizionario articoli e
    le regole sono scritti nello schema operativo) vince l'alias; la pagina
    Piano dei Conti, che ragiona gia' in CEE, passa ``False``.
    """
    testo = str(codice or "").strip()
    if not testo:
        return None
    if preferisci_operativo and testo in OPERATIVO_A_UFFICIALE:
        return OPERATIVO_A_UFFICIALE[testo]
    if conto_cee_valido(testo):
        return testo
    return OPERATIVO_A_UFFICIALE.get(testo)


# Codici esposti dal piano: tutti i conti ufficiali piu' i macro-gruppi che
# sono destinazione di un alias operativo (es. 41 Fondi ammortamento, 47
# Vendite) e che il bilancio elenca solo come intestazione.
CODICI_PIANO: List[str] = sorted(
    set(CONTI_UFFICIALI) | {t for t in OPERATIVO_A_UFFICIALE.values() if t in MACRO_UFFICIALE}
)


def categoria_cee(codice_ufficiale: str) -> Optional[str]:
    """attivo / passivo / patrimonio_netto / ricavi / costi del conto CEE."""
    sez = sezione_di(codice_ufficiale)
    if not sez:
        return None
    return _CATEGORIA_PER_GRUPPO.get(sez[1])


def saldi_in_cee(saldi: Dict[str, float]) -> Dict[str, float]:
    """Somma i saldi per conto CEE: chiavi operative convertite, chiavi gia'
    CEE lasciate passare, chiavi ignote scartate."""
    out: Dict[str, float] = {}
    for codice, saldo in (saldi or {}).items():
        cee = risolvi_codice_cee(codice)
        if not cee:
            continue
        out[cee] = round(out.get(cee, 0.0) + float(saldo or 0), 2)
    return out


def conto_cee(codice_ufficiale: str, saldo: float = 0.0) -> Dict[str, Any]:
    """Rappresentazione API di un conto CEE (con alias operativo)."""
    codice = str(codice_ufficiale)
    sez = sezione_di(codice)
    alias = alias_operativi(codice)
    return {
        "id": f"cee:{codice}",
        "codice": codice,
        "nome": CONTI_UFFICIALI.get(codice) or (MACRO_UFFICIALE.get(codice, (None, None, codice))[2]),
        "categoria": categoria_cee(codice),
        "sezione": sez[0] if sez else None,
        "gruppo": sez[1] if sez else None,
        "voce_cee": sez[2] if sez else None,
        "livello": len(codice.split(".")),
        "natura": "finanziario" if (sez and sez[0] == "SP") else "economico",
        "schema": "CEE",
        "alias_operativi": alias,
        "alias_operativo": alias[0] if alias else None,
        "attivo": True,
        "saldo": round(float(saldo or 0), 2),
    }


def piano_conti_cee(saldi_operativi: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
    """L'UNICO piano dei conti esposto dalle API: tutti i conti ufficiali CEE
    (231 + conti POS aggiunti in codice) con alias operativo e saldo.

    I saldi arrivano per codice operativo (`_calcola_saldi_piano_conti`) o
    gia' CEE (dizionario articoli aggiornato dalla pagina): vengono sommati
    sul conto ufficiale con `saldi_in_cee`. Funzione PURA: nessun DB.
    """
    saldi = saldi_in_cee(saldi_operativi or {})
    return [conto_cee(codice, saldi.get(codice, 0.0)) for codice in CODICI_PIANO]


def raggruppa_per_categoria(conti: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {
        "attivo": [], "passivo": [], "patrimonio_netto": [], "ricavi": [], "costi": [],
    }
    for conto in conti:
        categoria = conto.get("categoria")
        if categoria in grouped:
            grouped[categoria].append(conto)
    return grouped


def converti_conto_operativo(documento: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Lettura di compatibilita' di un vecchio documento `piano_conti`:
    torna il conto CEE corrispondente (None se il codice non ha mapping)."""
    cee = risolvi_codice_cee((documento or {}).get("codice"))
    if not cee:
        return None
    conto = conto_cee(cee, (documento or {}).get("saldo") or 0.0)
    conto["conto_operativo"] = {
        "codice": documento.get("codice"), "nome": documento.get("nome"),
        "categoria": documento.get("categoria"),
    }
    return conto


def classifica_saldi_ufficiale(saldi_operativi: Dict[str, float]) -> Dict[str, Dict]:
    """VISTA DERIVATA del bilancio in forma UFFICIALE CEE (§6.2): converte i saldi dei
    conti operativi interni nei conti ufficiali e li raggruppa per macro-gruppo di
    bilancio (SP/CE). Funzione PURA: nessun accesso al DB.

    Ritorna {codice_ufficiale: {"descrizione", "sezione", "gruppo", "voce_cee",
             "saldo", "conti_operativi": [...]}}.
    """
    out: Dict[str, Dict] = {}
    for cod_op, saldo in saldi_operativi.items():
        cod_uff = OPERATIVO_A_UFFICIALE.get(str(cod_op))
        if not cod_uff:
            continue
        sez = sezione_di(cod_uff)
        voce = out.setdefault(cod_uff, {
            "descrizione": CONTI_UFFICIALI.get(cod_uff, cod_uff),
            "sezione": sez[0] if sez else None,
            "gruppo": sez[1] if sez else None,
            "voce_cee": sez[2] if sez else None,
            "saldo": 0.0, "conti_operativi": [],
        })
        voce["saldo"] = round(voce["saldo"] + float(saldo or 0), 2)
        voce["conti_operativi"].append(cod_op)
    return out


# ── Conti delle righe di Prima Nota ───────────────────────────────────────────

def _gestore_riga(doc: Dict[str, Any]) -> str:
    gestore = doc.get("gestore") or doc.get("circuito")
    if gestore:
        return conti_pos.normalizza(gestore)
    categoria = str(doc.get("categoria") or doc.get("category") or "").upper()
    for circuito, sigla in conti_pos.SIGLE.items():
        if sigla in categoria.split():
            return circuito
    return conti_pos.normalizza(None)


def _e_categoria_pos_uscita(categoria: str) -> bool:
    return categoria in {_normalizza_categoria(c) for c in conti_pos.CATEGORIE_USCITA_POS}


def contropartita_per_categoria(
    registro: str, tipo: str, categoria: Any, gestore: Any = None,
) -> Optional[str]:
    """Contropartita CEE della riga dalla sola categoria (None se ignota)."""
    chiave = _normalizza_categoria(categoria)
    if not chiave:
        return None
    if _e_categoria_pos_uscita(chiave):
        chiave = "pos verso banca"
    regola = _CONTROPARTITE.get(chiave)
    if regola is None:
        return None
    codice = regola(registro, tipo, gestore) if callable(regola) else regola
    return codice or None


def conto_tesoreria(registro: str) -> Optional[str]:
    return _TESORERIA_PER_REGISTRO.get(str(registro or ""))


def completa_conti_prima_nota(registro: str, doc: Dict[str, Any]) -> Dict[str, Any]:
    """Campi conto da aggiungere a una riga di Prima Nota (solo quelli mancanti).

    - `conto_contabile`: se presente deve essere CEE (altrimenti ValueError);
      se manca e' il conto di tesoreria del registro (19.01.01 / 19.03.03);
    - `conto_contropartita`: se presente deve essere CEE; se manca viene
      dedotto dalla categoria; se la categoria non e' nota resta assente e la
      riga porta `contropartita_da_classificare = True` (mai inventata);
    - `conto_nome` / `conto_contropartita_nome`: descrizioni ufficiali.
    Nessun importo viene toccato. Funzione pura.
    """
    aggiornamenti: Dict[str, Any] = {}
    conto = str(doc.get("conto_contabile") or "").strip()
    if conto and not conto_cee_valido(conto):
        raise ValueError(f"conto_contabile {conto!r} non esiste nel piano dei conti CEE")
    if not conto:
        conto = conto_tesoreria(registro) or ""
        if not conto:
            raise ValueError(f"registro sconosciuto: {registro!r}")
        aggiornamenti["conto_contabile"] = conto
    if not doc.get("conto_nome"):
        aggiornamenti["conto_nome"] = CONTI_UFFICIALI.get(conto, "")

    contropartita = str(doc.get("conto_contropartita") or "").strip()
    if contropartita and not conto_cee_valido(contropartita):
        raise ValueError(
            f"conto_contropartita {contropartita!r} non esiste nel piano dei conti CEE"
        )
    if not contropartita:
        contropartita = contropartita_per_categoria(
            registro, str(doc.get("tipo") or doc.get("type") or ""),
            doc.get("categoria") or doc.get("category"), _gestore_riga(doc),
        ) or ""
        if contropartita and contropartita == conto:
            # es. riga POS con conto credito esplicito e categoria che
            # rimanda allo stesso credito: non e' una contropartita.
            contropartita = ""
        if contropartita:
            aggiornamenti["conto_contropartita"] = contropartita
        elif not doc.get("contropartita_da_classificare"):
            aggiornamenti["contropartita_da_classificare"] = True
    if contropartita and not doc.get("conto_contropartita_nome"):
        aggiornamenti["conto_contropartita_nome"] = CONTI_UFFICIALI.get(contropartita, "")
    return aggiornamenti
