"""
Motore UNICO tributi F24 — classificazione, scadenze, ravvedimenti,
associazione F24↔cedolini e anti-duplicazione DM10↔RC01.

Implementa la "Specifica definitiva F24/Cedolini/IRES/IRAP/Chat"
(memoria/SPECIFICA_F24_CEDOLINI_IRES_IRAP_CHAT.md), in particolare:
  - §6-10: tabella normativa dei codici tributo e causali per ente;
  - §11:  classificazione automatica di ogni riga (natura, ente,
          deducibilità, motivazione);
  - §3/12: le ritenute e le quote trattenute al lavoratore NON sono un
          nuovo costo se la retribuzione lorda è già contabilizzata —
          il saldo F24 non è mai automaticamente il costo deducibile;
  - §15:  regole di associazione F24 ↔ cedolini con motivazione leggibile;
  - §20:  scadenza naturale, giorni di ritardo, stato pagamento e tipo
          versamento (ordinario / ravvedimento / regolarizzazione);
  - §21/23: collegamento DM10 ↔ RC01 e rilevazione possibile doppio
          pagamento.

Tutte le funzioni sono PURE (nessun accesso al DB): lavorano sui
documenti F24 così come sono salvati (sezione_erario, sezione_inps,
sezione_regioni, sezione_tributi_locali, sezione_inail, dati_generali)
e sono riusate da router, chat intelligente e pipeline quietanze.
"""
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

# ── Nature possibili di una riga (§11) ─────────────────────────────────────
NATURE = ("costo", "ritenuta", "credito", "sanzione", "regolarizzazione", "pagamento")

# ── Tabella normativa Erario (§6) ──────────────────────────────────────────
# deducibilita: 'si' | 'no' | 'parziale' | 'da_verificare'
TABELLA_ERARIO: Dict[str, Dict[str, str]] = {
    "1001": {"descrizione": "Ritenute su retribuzioni", "natura": "ritenuta",
             "ente": "Erario", "deducibilita": "no",
             "nota": "Debito verso Erario: trattenuta al lavoratore, non nuovo costo"},
    "1002": {"descrizione": "Ritenute su arretrati", "natura": "ritenuta",
             "ente": "Erario", "deducibilita": "no",
             "nota": "Debito verso Erario"},
    "1012": {"descrizione": "Ritenute su cessazione/TFR", "natura": "ritenuta",
             "ente": "Erario", "deducibilita": "no",
             "nota": "Debito verso Erario"},
    "1701": {"descrizione": "Credito trattamento integrativo", "natura": "credito",
             "ente": "Erario", "deducibilita": "no",
             "nota": "Credito compensabile, non costo"},
    "8906": {"descrizione": "Sanzioni sostituto d'imposta", "natura": "sanzione",
             "ente": "Erario", "deducibilita": "no",
             "nota": "Sanzione: non è costo del personale"},
    "6869": {"descrizione": "Credito investimenti Mezzogiorno", "natura": "credito",
             "ente": "Erario", "deducibilita": "no",
             "nota": "Credito fiscale compensato, non costo"},
    # Addizionali (§7-8): ritenute del lavoratore, mai nuovo costo
    "3802": {"descrizione": "Addizionale regionale IRPEF", "natura": "ritenuta",
             "ente": "Regione", "deducibilita": "no",
             "nota": "Trattenuta al lavoratore, debito verso la Regione"},
    "3847": {"descrizione": "Addizionale comunale IRPEF — acconto", "natura": "ritenuta",
             "ente": "Comune", "deducibilita": "no",
             "nota": "Trattenuta al lavoratore, debito verso il Comune"},
    "3848": {"descrizione": "Addizionale comunale IRPEF — saldo", "natura": "ritenuta",
             "ente": "Comune", "deducibilita": "no",
             "nota": "Trattenuta al lavoratore, debito verso il Comune"},
}

# Codici sanzioni/interessi da ravvedimento (coerenti col motore quietanze)
CODICI_RAVVEDIMENTO = {
    "8901", "8902", "8903", "8904", "8906", "8907", "8911",
    "1989", "1990", "1991", "1992", "1993", "1994",
    "1507", "1508", "1509", "1510", "1511", "1512",
}

# ── Causali INPS (§9) ──────────────────────────────────────────────────────
CAUSALI_INPS: Dict[str, Dict[str, str]] = {
    "DM10": {"descrizione": "Contributi correnti lavoratori dipendenti",
             "natura": "costo", "ente": "INPS", "deducibilita": "parziale",
             "nota": "Comprende quota datoriale (costo) E quota lavoratore "
                     "(trattenuta): la quota di costo è quella datoriale dal "
                     "prospetto paghe, mai l'intero totale F24"},
    "CXX":  {"descrizione": "Gestione separata collaboratori",
             "natura": "costo", "ente": "INPS", "deducibilita": "parziale",
             "nota": "Quota committente = costo; quota collaboratore = trattenuta"},
    "RC01": {"descrizione": "Regolarizzazione contributiva (ravvedimento)",
             "natura": "regolarizzazione", "ente": "INPS", "deducibilita": "da_verificare",
             "nota": "Riferita a un periodo PRECEDENTE: mai imputata come nuovo "
                     "costo del mese di pagamento; collegare all'F24 originario"},
}

# ── Causali INAIL (§10) ────────────────────────────────────────────────────
CAUSALI_INAIL: Dict[str, Dict[str, str]] = {
    "P": {"descrizione": "Pagamento premi e accessori INAIL",
          "natura": "costo", "ente": "INAIL", "deducibilita": "si",
          "nota": "Premio a carico dell'impresa: deducibile per competenza"},
}

# Codici Regione noti (§7) e Comuni catastali rilevati (§8)
CODICI_REGIONE = {"05": "Campania"}
CODICI_COMUNE = {"F839": "Napoli", "B990": "Casoria"}


def classifica_riga(sezione: str, codice: str) -> Dict[str, str]:
    """Classificazione normativa di una riga F24 (§11).

    Ritorna sempre un dict con natura/ente/deducibilita/descrizione/nota;
    i codici non in tabella escono come 'da_verificare' con motivazione
    esplicita (mai indovinare).
    """
    sez = (sezione or "").lower()
    cod = (codice or "").strip().upper()

    if sez in ("inps", "sezione_inps"):
        info = CAUSALI_INPS.get(cod)
        if info:
            return dict(info, codice=cod, sezione="INPS")
        return {"codice": cod, "sezione": "INPS", "descrizione": f"Causale INPS {cod}",
                "natura": "pagamento", "ente": "INPS", "deducibilita": "da_verificare",
                "nota": "Causale non in tabella normativa: verificare col consulente"}

    if sez in ("inail", "sezione_inail"):
        info = CAUSALI_INAIL.get(cod)
        if info:
            return dict(info, codice=cod, sezione="INAIL")
        return {"codice": cod, "sezione": "INAIL", "descrizione": f"Causale INAIL {cod}",
                "natura": "pagamento", "ente": "INAIL", "deducibilita": "da_verificare",
                "nota": "Causale non in tabella normativa: verificare col consulente"}

    # Erario / Regioni / Tributi locali: tabella unica dei codici tributo
    info = TABELLA_ERARIO.get(cod)
    if info:
        return dict(info, codice=cod, sezione=sez or "erario")
    if cod in CODICI_RAVVEDIMENTO:
        return {"codice": cod, "sezione": sez or "erario",
                "descrizione": f"Sanzioni/interessi da ravvedimento ({cod})",
                "natura": "sanzione", "ente": "Erario", "deducibilita": "no",
                "nota": "Accessorio da ravvedimento: non è costo del personale"}
    return {"codice": cod, "sezione": sez or "erario",
            "descrizione": f"Codice tributo {cod}",
            "natura": "pagamento", "ente": "Erario", "deducibilita": "da_verificare",
            "nota": "Codice non in tabella normativa: verificare col consulente"}


# ── Periodi e scadenze (§20) ───────────────────────────────────────────────

def _parse_periodo(valore: Any) -> Optional[tuple]:
    """(mese, anno) da 'MM/YYYY', 'MM-YYYY', 'YYYY-MM' o simili. None se ignoto."""
    if not valore:
        return None
    s = str(valore).strip()
    m = re.match(r"^(\d{1,2})[/-](\d{4})$", s)
    if m:
        mese, anno = int(m.group(1)), int(m.group(2))
        return (mese, anno) if 1 <= mese <= 12 else None
    m = re.match(r"^(\d{4})[/-](\d{1,2})$", s)
    if m:
        anno, mese = int(m.group(1)), int(m.group(2))
        return (mese, anno) if 1 <= mese <= 12 else None
    return None


def _parse_data(valore: Any) -> Optional[date]:
    if not valore:
        return None
    if isinstance(valore, datetime):
        return valore.date()
    if isinstance(valore, date):
        return valore
    s = str(valore).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def scadenza_naturale(mese: int, anno: int) -> date:
    """Scadenza ordinaria di ritenute/contributi del periodo: il 16 del
    mese successivo (§20 — es. novembre 2022 → 16 dicembre 2022)."""
    if mese == 12:
        return date(anno + 1, 1, 16)
    return date(anno, mese + 1, 16)


def valuta_pagamento(mese: int, anno: int, data_pagamento: Any) -> Dict[str, Any]:
    """Scadenza naturale, giorni di ritardo e stato pagamento (§20)."""
    scadenza = scadenza_naturale(mese, anno)
    pagato_il = _parse_data(data_pagamento)
    if pagato_il is None:
        stato = "in_scadenza" if date.today() <= scadenza else "non_pagato"
        return {"scadenza_naturale": scadenza.isoformat(), "data_pagamento": None,
                "giorni_ritardo": None, "stato": stato}
    ritardo = (pagato_il - scadenza).days
    return {
        "scadenza_naturale": scadenza.isoformat(),
        "data_pagamento": pagato_il.isoformat(),
        "giorni_ritardo": max(0, ritardo),
        "stato": "pagato_in_ritardo" if ritardo > 0 else "pagato_nei_termini",
    }


def _righe_f24(f24: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Tutte le righe del modello con sezione esplicita."""
    righe = []
    for sezione in ("sezione_erario", "sezione_regioni", "sezione_tributi_locali"):
        for r in f24.get(sezione, []) or []:
            righe.append({**r, "_sezione": sezione, "_codice": r.get("codice_tributo", "")})
    for r in f24.get("sezione_inps", []) or []:
        righe.append({**r, "_sezione": "sezione_inps", "_codice": r.get("causale", "")})
    for r in f24.get("sezione_inail", []) or []:
        righe.append({**r, "_sezione": "sezione_inail", "_codice": r.get("causale", "")})
    return righe


def causali_inps(f24: Dict[str, Any]) -> List[str]:
    return sorted({(r.get("causale") or "").strip().upper()
                   for r in f24.get("sezione_inps", []) or [] if r.get("causale")})


def tipo_versamento(f24: Dict[str, Any]) -> str:
    """'regolarizzazione' se compare RC01; 'ravvedimento' se ci sono codici
    sanzioni/interessi; altrimenti 'ordinario' (§20)."""
    if "RC01" in causali_inps(f24):
        return "regolarizzazione"
    for r in _righe_f24(f24):
        if r["_codice"].upper() in CODICI_RAVVEDIMENTO:
            return "ravvedimento"
    return "ordinario"


def periodo_prevalente(f24: Dict[str, Any]) -> Optional[tuple]:
    """(mese, anno) più frequente tra le righe del modello."""
    conteggio: Dict[tuple, int] = {}
    for r in _righe_f24(f24):
        p = _parse_periodo(r.get("periodo_riferimento") or r.get("periodo"))
        if p:
            conteggio[p] = conteggio.get(p, 0) + 1
    if not conteggio:
        # fallback dai dati generali
        dg = f24.get("dati_generali", {}) or {}
        return _parse_periodo(dg.get("periodo_riferimento") or dg.get("periodo"))
    return max(conteggio, key=conteggio.get)


def classifica_f24(f24: Dict[str, Any]) -> Dict[str, Any]:
    """Analisi completa del modello: righe classificate, totali per natura,
    tipo versamento, periodo prevalente, scadenza/stato pagamento (§11+§20).

    NB (§3): il saldo finale è un'uscita finanziaria ('pagamento'), MAI
    automaticamente un costo deducibile.
    """
    righe_out: List[Dict[str, Any]] = []
    totali: Dict[str, float] = {}
    for r in _righe_f24(f24):
        cls = classifica_riga(r["_sezione"], r["_codice"])
        debito = float(r.get("importo_debito", 0) or r.get("importo", 0) or 0)
        credito = float(r.get("importo_credito", 0) or 0)
        cls_riga = {
            **cls,
            "periodo": r.get("periodo_riferimento") or r.get("periodo") or "",
            "importo_debito": debito,
            "importo_credito": credito,
        }
        righe_out.append(cls_riga)
        natura = "credito" if credito and not debito else cls["natura"]
        totali[natura] = round(totali.get(natura, 0) + (debito or credito), 2)

    periodo = periodo_prevalente(f24)
    dg = f24.get("dati_generali", {}) or {}
    data_pag = (dg.get("data_pagamento") or f24.get("data_pagamento")
                or f24.get("data_pagamento_quietanza"))
    pagamento = (valuta_pagamento(periodo[0], periodo[1], data_pag)
                 if periodo else {"scadenza_naturale": None, "data_pagamento": None,
                                  "giorni_ritardo": None, "stato": "periodo_ignoto"})

    saldo = dg.get("saldo_delega") or (f24.get("totali", {}) or {}).get("saldo_netto", 0)
    return {
        "righe": righe_out,
        "totali_per_natura": totali,
        "tipo_versamento": tipo_versamento(f24),
        "causali_inps": causali_inps(f24),
        "periodo_prevalente": f"{periodo[0]:02d}/{periodo[1]}" if periodo else None,
        "saldo_finale": float(saldo or 0),
        "nota_saldo": "Il saldo finale è l'uscita finanziaria netta: NON coincide "
                      "col costo deducibile (ritenute e crediti compensati non sono costi)",
        **pagamento,
    }


# ── Associazione F24 ↔ cedolini (§15) ──────────────────────────────────────

def valuta_associazione_cedolini(
    f24: Dict[str, Any], mese_cedolini: int, anno_cedolini: int,
    codice_fiscale_azienda: Optional[str] = None,
) -> Dict[str, Any]:
    """Verifica le condizioni della §15 e produce una motivazione leggibile
    (usata anche dalla Chat intelligente per spiegare l'esito)."""
    motivi: List[str] = []
    ok = True

    # 1. stesso soggetto fiscale (se noto)
    cf_f24 = ((f24.get("dati_generali", {}) or {}).get("codice_fiscale")
              or f24.get("codice_fiscale") or "").strip().upper()
    if codice_fiscale_azienda and cf_f24 and cf_f24 != codice_fiscale_azienda.strip().upper():
        ok = False
        motivi.append(f"soggetto fiscale diverso ({cf_f24} ≠ {codice_fiscale_azienda})")

    # 2/6. periodo di riferimento coincidente col mese/anno dei cedolini
    periodo = periodo_prevalente(f24)
    if periodo is None:
        ok = False
        motivi.append("periodo di riferimento non determinabile dal modello")
    elif periodo != (mese_cedolini, anno_cedolini):
        ok = False
        motivi.append(
            f"periodo F24 {periodo[0]:02d}/{periodo[1]} diverso dal periodo "
            f"cedolini {mese_cedolini:02d}/{anno_cedolini}"
        )
    else:
        motivi.append(f"periodo coincidente ({mese_cedolini:02d}/{anno_cedolini})")

    # 5. regolarizzazioni per periodi precedenti → gestione separata
    if "RC01" in causali_inps(f24):
        ok = False
        motivi.append("presente causale RC01 (regolarizzazione di periodo "
                      "precedente): associazione ai cedolini correnti vietata")

    # 7. tolleranza SOLO sulla data di pagamento (di norma il mese successivo)
    esito = valuta_pagamento(mese_cedolini, anno_cedolini,
                             (f24.get("dati_generali", {}) or {}).get("data_pagamento")
                             or f24.get("data_pagamento"))
    if esito["data_pagamento"]:
        motivi.append(
            f"pagato il {esito['data_pagamento']} (scadenza naturale "
            f"{esito['scadenza_naturale']}, "
            + ("nei termini)" if esito["stato"] == "pagato_nei_termini"
               else f"{esito['giorni_ritardo']} giorni di ritardo)")
        )

    spiegazione = (
        ("Associazione consentita: " if ok else "Associazione NON consentita: ")
        + "; ".join(motivi) + "."
    )
    return {"associabile": ok, "motivi": motivi, "spiegazione": spiegazione,
            "periodo_f24": f"{periodo[0]:02d}/{periodo[1]}" if periodo else None,
            "periodo_cedolini": f"{mese_cedolini:02d}/{anno_cedolini}"}


# ── DM10 ↔ RC01 e doppio pagamento (§21 + §23) ────────────────────────────

def _codici_principali(f24: Dict[str, Any]) -> set:
    """Codici tributo del modello, esclusi sanzioni/interessi da ravvedimento."""
    return {r["_codice"].upper() for r in _righe_f24(f24)
            if r["_codice"] and r["_codice"].upper() not in CODICI_RAVVEDIMENTO}


def confronta_dm10_rc01(f24_ordinario: Dict[str, Any], f24_rc01: Dict[str, Any]) -> Dict[str, Any]:
    """Collegamento tra F24 ordinario (DM10) e F24 di regolarizzazione (RC01):
    stesso soggetto + stesso periodo + tributi corrispondenti → NON sommare
    due volte (§21). Il solo stesso mese NON basta: si confrontano i campi.
    """
    controlli: List[Dict[str, Any]] = []

    def check(nome, a, b, obbligatorio=True):
        uguali = bool(a) and bool(b) and str(a).strip().upper() == str(b).strip().upper()
        controlli.append({"campo": nome, "ordinario": a, "rc01": b,
                          "coincide": uguali, "obbligatorio": obbligatorio})
        return uguali or not obbligatorio

    dg_a = f24_ordinario.get("dati_generali", {}) or {}
    dg_b = f24_rc01.get("dati_generali", {}) or {}
    cf_ok = check("codice_fiscale", dg_a.get("codice_fiscale") or f24_ordinario.get("codice_fiscale"),
                  dg_b.get("codice_fiscale") or f24_rc01.get("codice_fiscale"))

    pa, pb = periodo_prevalente(f24_ordinario), periodo_prevalente(f24_rc01)
    periodo_ok = pa is not None and pa == pb
    controlli.append({"campo": "periodo", "ordinario": pa, "rc01": pb,
                      "coincide": periodo_ok, "obbligatorio": True})

    codici_a, codici_b = _codici_principali(f24_ordinario), _codici_principali(f24_rc01)
    comuni = codici_a & codici_b - {"DM10", "RC01"}
    tributi_ok = len(comuni) > 0
    controlli.append({"campo": "codici_tributo_comuni", "ordinario": sorted(codici_a),
                      "rc01": sorted(codici_b), "coincide": tributi_ok,
                      "obbligatorio": True, "comuni": sorted(comuni)})

    collegati = cf_ok and periodo_ok and tributi_ok
    return {
        "collegati": collegati,
        "controlli": controlli,
        "tributi_comuni": sorted(comuni),
        "spiegazione": (
            "RC01 riconosciuto come regolarizzazione del debito originario: le "
            "righe comuni NON vanno registrate due volte in costi/debiti/pagamenti."
            if collegati else
            "Confronto insufficiente: lo stesso mese da solo non basta per "
            "dichiarare il collegamento; verificare campo per campo."
        ),
    }


def _risulta_pagato(f24: Dict[str, Any]) -> bool:
    return bool(
        f24.get("status") == "pagato" or f24.get("pagato")
        or f24.get("quietanza_id") or f24.get("riconciliato_quietanza")
        or (f24.get("dati_generali", {}) or {}).get("data_pagamento")
        or f24.get("data_pagamento_quietanza")
    )


def rileva_doppio_pagamento(f24_ordinario: Dict[str, Any], f24_rc01: Dict[str, Any]) -> Dict[str, Any]:
    """POSSIBILE DOPPIO PAGAMENTO (§23): entrambi pagati, stesso debito,
    e il secondo non è chiaramente fatto di sole sanzioni/interessi."""
    legame = confronta_dm10_rc01(f24_ordinario, f24_rc01)
    if not legame["collegati"]:
        return {"possibile_doppio_pagamento": False, "stato": "non_duplicato",
                "dettaglio": legame}

    entrambi_pagati = _risulta_pagato(f24_ordinario) and _risulta_pagato(f24_rc01)
    if not entrambi_pagati:
        return {"possibile_doppio_pagamento": False, "stato": "non_duplicato",
                "motivo": "non risultano entrambi pagati", "dettaglio": legame}

    # Quota del secondo modello riferibile ai tributi comuni (capitale) vs accessori
    quota_capitale = 0.0
    quota_accessori = 0.0
    for r in _righe_f24(f24_rc01):
        importo = float(r.get("importo_debito", 0) or r.get("importo", 0) or 0)
        if r["_codice"].upper() in CODICI_RAVVEDIMENTO:
            quota_accessori += importo
        elif r["_codice"].upper() in legame["tributi_comuni"]:
            quota_capitale += importo

    solo_accessori = quota_capitale <= 0.01
    return {
        "possibile_doppio_pagamento": not solo_accessori,
        "stato": "da_verificare" if not solo_accessori else "non_duplicato",
        "quota_potenzialmente_duplicata": round(quota_capitale, 2),
        "quota_sanzioni_interessi": round(quota_accessori, 2),
        "messaggio": ("POSSIBILE DOPPIO PAGAMENTO: entrambi i modelli risultano "
                      "pagati per lo stesso debito — verificare col consulente se "
                      "il secondo versamento comprende solo sanzioni e interessi "
                      "oppure se il capitale è stato versato due volte."
                      if not solo_accessori else
                      "Secondo versamento composto da soli accessori "
                      "(sanzioni/interessi): nessuna duplicazione di capitale."),
        "dettaglio": legame,
    }


# Stati ammessi per l'anomalia doppio pagamento (§23)
STATI_ANOMALIA_DOPPIO_PAGAMENTO = (
    "da_verificare", "confermato_doppio_pagamento",
    "non_duplicato", "rimborsato_compensato", "chiuso_dal_consulente",
)
