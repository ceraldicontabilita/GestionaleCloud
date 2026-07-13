"""Mapping CANONICO dei piani dei conti (PROMPT_DEFINITIVO §6.2/§6.3).

Schema canonico scelto dall'utente: **CEE puntato** (es. `05.01.01`), quello usato dal
motore di registrazione §6.1 (`registrazione_contabile`) e dal bilancio di `piano_conti`.

Questo modulo fornisce l'UNICA tabella di corrispondenza tra i due piani dei conti che
oggi convivono senza mapping:
  - `piano_conti` (CEE puntato, 30 conti, OPERATIVO/semplificato) — CANONICO;
  - `contabilita_italiana` (numerico 6 cifre, 96 conti, CIVILISTICO dettagliato).

Due direzioni:
  1. `PUNTATO_A_CEE`  — ogni conto puntato → voce di bilancio CEE (per presentare il
     bilancio dei saldi `piano_conti` in forma CEE: è la "vista derivata" del §6.2).
  2. `NUMERICO_A_PUNTATO` — ogni conto numerico → conto puntato corrispondente, quando
     esiste un equivalente OPERATIVO. Molti-a-uno. I conti puramente CIVILISTICI
     (immobilizzazioni, riserve dettagliate, ratei/risconti, fondi) NON hanno equivalente
     puntato e valgono `None` (marcati SOLO_CIVILISTICO): il piano puntato, essendo
     semplificato, non li rappresenta → la conversione numerico→puntato è LOSSY in quella
     direzione. Vanno confermati/estesi con l'utente prima di dismettere il piano numerico.

NB: nessuna scrittura/migrazione dati qui: è solo la tabella di verità del mapping,
da usare per rendere il bilancio unico (§6.2) e per convertire i codici tra i due schemi.
"""
from typing import Dict, Optional

# ── 1. Piano CEE puntato → voce di bilancio CEE ─────────────────────────────
# sezione: "SP" (stato patrimoniale) o "CE" (conto economico); `cee` = voce civilistica.
PUNTATO_A_CEE: Dict[str, Dict[str, str]] = {
    # ATTIVO (SP)
    "01.01.01": {"sezione": "SP", "gruppo": "attivo", "cee": "C.IV.3", "voce": "Disponibilità liquide - cassa"},
    "01.01.02": {"sezione": "SP", "gruppo": "attivo", "cee": "C.IV.1", "voce": "Disponibilità liquide - banca"},
    "01.02.01": {"sezione": "SP", "gruppo": "attivo", "cee": "C.II.1", "voce": "Crediti verso clienti"},
    "01.03.01": {"sezione": "SP", "gruppo": "attivo", "cee": "C.I.4", "voce": "Rimanenze - merci"},
    "01.04.01": {"sezione": "SP", "gruppo": "attivo", "cee": "C.II.5", "voce": "Crediti tributari - IVA a credito"},
    # PASSIVO (SP)
    "02.01.01": {"sezione": "SP", "gruppo": "passivo", "cee": "D.7", "voce": "Debiti verso fornitori"},
    "02.02.01": {"sezione": "SP", "gruppo": "passivo", "cee": "D.12", "voce": "Debiti tributari"},
    "02.02.02": {"sezione": "SP", "gruppo": "passivo", "cee": "D.13", "voce": "Debiti verso istituti previdenza"},
    "02.03.01": {"sezione": "SP", "gruppo": "passivo", "cee": "D.12", "voce": "Debiti tributari - IVA a debito"},
    "02.04.01": {"sezione": "SP", "gruppo": "passivo", "cee": "C", "voce": "Trattamento di fine rapporto"},
    # PATRIMONIO NETTO (SP)
    "03.01.01": {"sezione": "SP", "gruppo": "patrimonio_netto", "cee": "A.I", "voce": "Capitale sociale"},
    "03.02.01": {"sezione": "SP", "gruppo": "patrimonio_netto", "cee": "A.IV", "voce": "Riserva legale"},
    "03.03.01": {"sezione": "SP", "gruppo": "patrimonio_netto", "cee": "A.IX", "voce": "Utile d'esercizio"},
    "03.03.02": {"sezione": "SP", "gruppo": "patrimonio_netto", "cee": "A.IX", "voce": "Perdita d'esercizio"},
    # RICAVI (CE)
    "04.01.01": {"sezione": "CE", "gruppo": "ricavi", "cee": "A.1", "voce": "Ricavi vendite e prestazioni"},
    "04.01.02": {"sezione": "CE", "gruppo": "ricavi", "cee": "A.1", "voce": "Ricavi vendite e prestazioni"},
    "04.01.03": {"sezione": "CE", "gruppo": "ricavi", "cee": "A.1", "voce": "Ricavi vendite e prestazioni"},
    "04.02.01": {"sezione": "CE", "gruppo": "ricavi", "cee": "A.1", "voce": "Ricavi vendite e prestazioni"},
    "04.03.01": {"sezione": "CE", "gruppo": "ricavi", "cee": "C.16", "voce": "Altri proventi finanziari"},
    # COSTI (CE)
    "05.01.01": {"sezione": "CE", "gruppo": "costi", "cee": "B.6", "voce": "Materie prime, sussidiarie, consumo"},
    "05.01.02": {"sezione": "CE", "gruppo": "costi", "cee": "B.6", "voce": "Materie prime, sussidiarie, consumo"},
    "05.02.01": {"sezione": "CE", "gruppo": "costi", "cee": "B.7", "voce": "Costi per servizi"},
    "05.02.02": {"sezione": "CE", "gruppo": "costi", "cee": "B.7", "voce": "Costi per servizi - utenze"},
    "05.02.03": {"sezione": "CE", "gruppo": "costi", "cee": "B.8", "voce": "Costi per godimento beni di terzi"},
    "05.03.01": {"sezione": "CE", "gruppo": "costi", "cee": "B.9.a", "voce": "Salari e stipendi"},
    "05.03.02": {"sezione": "CE", "gruppo": "costi", "cee": "B.9.b", "voce": "Oneri sociali"},
    "05.03.03": {"sezione": "CE", "gruppo": "costi", "cee": "B.9.c", "voce": "Trattamento di fine rapporto"},
    "05.04.01": {"sezione": "CE", "gruppo": "costi", "cee": "B.10", "voce": "Ammortamenti e svalutazioni"},
    "05.05.01": {"sezione": "CE", "gruppo": "costi", "cee": "C.17", "voce": "Interessi e altri oneri finanziari"},
    "05.06.01": {"sezione": "CE", "gruppo": "costi", "cee": "20", "voce": "Imposte sul reddito"},
}

# ── 2. Piano numerico (contabilita_italiana) → piano puntato canonico ───────
# `None` = SOLO_CIVILISTICO: nessun equivalente nel piano puntato semplificato.
NUMERICO_A_PUNTATO: Dict[str, Optional[str]] = {
    # A) Crediti verso soci — solo civilistico
    "100000": None,
    # B.I) Immobilizzazioni immateriali — solo civilistico
    "110100": None, "110200": None, "110300": None, "110400": None,
    "110500": None, "110600": None, "110700": None,
    # B.II) Immobilizzazioni materiali e fondi amm.to — solo civilistico
    "120100": None, "120200": None, "120300": None, "120400": None, "120500": None,
    "125100": None, "125200": None, "125300": None, "125400": None,
    # C.I) Rimanenze → Magazzino merci (01.03.01)
    "130100": "01.03.01", "130200": "01.03.01", "130300": "01.03.01",
    "130400": "01.03.01", "130500": "01.03.01",
    # C.II) Crediti → Crediti v/clienti / crediti tributari (IVA a credito)
    "140100": "01.02.01", "140200": "01.02.01", "140300": "01.02.01", "140400": "01.02.01",
    "140500": "01.04.01",  # crediti tributari ≈ IVA a credito (operativo)
    "140510": "01.04.01", "140520": "01.02.01",
    # C.III) Attività finanziarie — solo civilistico
    "150000": None,
    # C.IV) Disponibilità liquide
    "160100": "01.01.02", "160200": "01.01.02", "160300": "01.01.01",
    # D) Ratei/risconti attivi — solo civilistico
    "170100": None, "170200": None,
    # A) Patrimonio netto
    "200100": "03.01.01",  # capitale sociale
    "200200": None, "200300": None,  # riserve dettagliate — solo civilistico
    "200400": "03.02.01",  # riserva legale
    "200500": None, "200600": None, "200700": None,
    "200800": "03.03.01",  # utili/perdite a nuovo ≈ utile d'esercizio (macro)
    # B) Fondi rischi/oneri — solo civilistico
    "210100": None, "210200": None, "210300": None, "210400": None,
    # C) TFR
    "220000": "02.04.01",
    # D) Debiti
    "230100": None, "230200": None, "230300": None,
    "230400": "01.01.02",  # debiti v/banche (segno passivo, macro banca) — VERIFICARE
    "230500": None, "230600": None,
    "230700": "02.01.01",  # debiti v/fornitori
    "230800": None, "230900": "02.01.01", "231000": "02.01.01", "231100": "02.01.01",
    "231200": "02.02.01",  # debiti tributari
    "231300": "02.02.02",  # debiti previdenziali (INPS)
    "231400": "02.02.01",  # altri debiti ≈ debiti tributari (macro) — VERIFICARE
    # E) Ratei/risconti passivi — solo civilistico
    "240100": None, "240200": None,
    # CE - A) Valore della produzione (ricavi)
    "300100": "04.01.01", "300200": "04.01.01", "300300": "04.01.01",
    "300400": "04.01.01", "300500": "04.03.01",
    # CE - B) Costi della produzione
    "400100": "05.01.01",  # materie prime
    "400200": "05.02.01",  # servizi
    "400300": "05.02.03",  # godimento beni di terzi ≈ canoni locazione
    "400400": "05.03.01",  # personale (macro)
    "400410": "05.03.01",  # salari
    "400420": "05.03.02",  # oneri sociali
    "400430": "05.03.03",  # TFR
    "400440": "05.03.03",  # quiescenza ≈ TFR (macro) — VERIFICARE
    "400450": "05.03.01",  # altri costi personale (macro)
    "400500": "05.04.01",  # ammortamenti
    "400510": "05.04.01", "400520": "05.04.01", "400530": "05.04.01", "400540": "05.04.01",
    "400600": "05.01.01",  # variazione rimanenze materie (macro costi merci) — VERIFICARE
    "400700": None, "400800": None,  # accantonamenti — solo civilistico
    "400900": "05.02.01",  # oneri diversi di gestione ≈ servizi (macro) — VERIFICARE
    # CE - C) Proventi e oneri finanziari
    "500100": "04.03.01", "500200": "04.03.01",  # proventi finanziari
    "500300": "05.05.01",  # interessi e oneri finanziari
    "500400": "05.05.01",  # utili/perdite su cambi ≈ oneri finanziari (macro) — VERIFICARE
    # CE - D) Rettifiche valore att. finanziarie — solo civilistico
    "600100": None, "600200": None,
    # CE - 20) Imposte
    "700100": "05.06.01", "700200": "05.06.01",
}


def to_puntato(codice_numerico: str) -> Optional[str]:
    """Conto numerico → conto puntato canonico (None se SOLO_CIVILISTICO/ignoto)."""
    return NUMERICO_A_PUNTATO.get(str(codice_numerico))


def voce_cee(codice_puntato: str) -> Optional[Dict[str, str]]:
    """Conto puntato → voce di bilancio CEE (per la vista bilancio unica §6.2)."""
    return PUNTATO_A_CEE.get(str(codice_puntato))


def numerico_solo_civilistici() -> list:
    """Codici numerici senza equivalente puntato (mapping lossy da confermare)."""
    return [k for k, v in NUMERICO_A_PUNTATO.items() if v is None]


def classifica_saldi_cee(saldi_puntati: Dict[str, float]) -> Dict[str, Dict]:
    """VISTA DERIVATA del bilancio in forma CEE (§6.2), a partire dai saldi dei conti
    PUNTATI (fonte unica). Raggruppa i saldi per voce CEE, così bilancio/mastro/giornale
    presentano UN solo dato contabile in classificazione civilistica, senza motori
    paralleli. Funzione PURA: nessun accesso al DB.

    Ritorna: {voce_cee: {"sezione", "gruppo", "descrizione", "saldo", "conti": [...]}}.
    """
    out: Dict[str, Dict] = {}
    for codice, saldo in saldi_puntati.items():
        info = PUNTATO_A_CEE.get(str(codice))
        if not info:
            continue
        key = info["cee"]
        voce = out.setdefault(key, {
            "sezione": info["sezione"], "gruppo": info["gruppo"],
            "descrizione": info["voce"], "saldo": 0.0, "conti": [],
        })
        voce["saldo"] = round(voce["saldo"] + float(saldo or 0), 2)
        voce["conti"].append(codice)
    return out
