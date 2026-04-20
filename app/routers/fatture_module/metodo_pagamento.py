"""
Normalizzazione metodo di pagamento e auto-routing fatture
in prima_nota_cassa / prima_nota_banca sulla base dell'anagrafica fornitore.
"""
from typing import Optional, Tuple


# Metodo fornitore (o FE MP code) → destinazione
METODI_CASSA = {
    "contanti", "contante", "cassa", "cash",
    "mp01",              # FE: contanti
}

METODI_BANCA = {
    "banca", "bancario", "bancaria",
    "bonifico", "bonif", "bonifico bancario", "bonif.",
    "sepa", "sepa diretto", "rid", "rid sepa",
    "carta", "carta di credito", "carta credito",
    "credit card", "credit", "creditcard",
    "bancomat", "debit", "carta di debito", "carta debito",
    "domiciliazione", "domiciliato",
    "paypal",            # paypal → banca
    "stripe",
    "mp02",              # FE: assegno bancario → ATTENZIONE (non è banca puro) ma lo consideriamo banca auto
    "mp03",              # FE: assegno circolare → idem
    "mp05",              # FE: bonifico
    "mp08",              # FE: carta di pagamento
    "mp17",              # FE: finanziamento
    "mp19",              # FE: SEPA Direct Debit
    "mp20",              # FE: SEPA Direct Debit CORE
    "mp21",              # FE: SEPA Direct Debit B2B
}

# Metodi che NON vogliamo auto-routare (richiedono logica dedicata o manuale)
METODI_ASSEGNO = {
    "assegno", "assegno bancario", "assegno circolare",
    "assegni",
}

METODI_AMBIGUI = {
    "", "misto", "da_configurare", "da configurare",
    "altro", "n/a", "na", "none", "null",
}


def normalizza_metodo_pagamento(metodo_raw: Optional[str]) -> Optional[str]:
    """
    Normalizza un metodo di pagamento (fornitore o FE) in una destinazione:
      - 'cassa'  → va in prima_nota_cassa
      - 'banca'  → va in prima_nota_banca (include bonifico, carta, SEPA, paypal)
      - 'assegno'→ va gestito come assegno (NON auto-routato)
      - None     → ambiguo / da configurare, NON auto-routare

    Il confronto è case-insensitive e accetta sia label italiane (contanti,
    bonifico, carta di credito…) sia codici MP FE (MP01, MP05, MP08…).
    """
    if not metodo_raw:
        return None
    m = str(metodo_raw).strip().lower()
    if not m or m in METODI_AMBIGUI:
        return None

    # Priorità: assegno prima di banca (MP02/MP03 sono assegni nell'FE, ma
    # chi li riceve in genere li incassa poi in banca; qui li teniamo separati).
    if any(a in m for a in METODI_ASSEGNO):
        # MP02/MP03 vengono considerati ASSEGNI, non banca
        if m in {"mp02", "mp03"}:
            return "assegno"
        return "assegno"

    # Cassa (controllo esatto o substring "contant"/"cash")
    if m in METODI_CASSA or "contant" in m or "cash" in m:
        return "cassa"

    # Banca (controllo esatto o substring)
    if m in METODI_BANCA:
        return "banca"
    for kw in ("bonifico", "banca", "bancar", "sepa", "rid", "carta", "credit", "debit", "paypal", "stripe", "bancomat", "domicili"):
        if kw in m:
            return "banca"

    # Codici MP non mappati → ambiguo
    return None


def destinazione_auto(metodo_fornitore: Optional[str]) -> Tuple[Optional[str], str]:
    """
    Ritorna (destinazione, descrizione) per log/UX:
      destinazione ∈ {'cassa','banca','assegno',None}
    """
    dest = normalizza_metodo_pagamento(metodo_fornitore)
    if dest == "cassa":
        return "cassa", "contanti → prima_nota_cassa"
    if dest == "banca":
        return "banca", "banca/carta/bonifico → prima_nota_banca"
    if dest == "assegno":
        return "assegno", "assegno → gestito in area assegni"
    return None, f"metodo ambiguo/non configurato: {metodo_fornitore!r}"
