"""
Classificazione costi unificata — punto d'ingresso unico.

Storicamente esistono TRE classificatori distinti, ciascuno con un proprio
scopo e propri chiamanti (P2-4 della verifica Contabilità):

  1. learning_machine_cdc      → CENTRO DI COSTO analitico (bar/pasticceria),
                                  con learning sui fornitori.
  2. classificazione_costi     → voce di CONTO ECONOMICO (schema civilistico
                                  art. 2425 c.c.) + deducibilità/detraibilità.
  3. categorizzazione_contabile → conto del PIANO DEI CONTI + deducibilità
                                  IRES/IRAP + categoria merceologica.

Non sono ridondanti: classificano tre ASSI diversi della stessa fattura. Per
questo non vengono fusi in un unico output, ma orchestrati da un solo punto:
`classifica_costo_completo` restituisce, con una sola chiamata, le tre
classificazioni coerenti tra loro (stesso input, stessa normalizzazione).

I motori esistenti restano la fonte di verità di ciascun asse: qui si delega
soltanto, senza duplicarne la logica. I chiamanti che hanno bisogno di un
solo asse continuano a usare direttamente il motore relativo; chi vuole la
classificazione completa (es. import fattura) usa questo façade.
"""
from typing import Any, Dict, List, Optional

from app.services import learning_machine_cdc as _cdc
from app.services import classificazione_costi as _ce
from app.services import categorizzazione_contabile as _pc


def _testo_linee(linee_fattura: Optional[List[Dict]]) -> str:
    """Concatena le descrizioni delle linee per i classificatori che
    lavorano su una singola stringa descrittiva."""
    if not linee_fattura:
        return ""
    parti = []
    for linea in linee_fattura:
        if isinstance(linea, dict):
            parti.append(str(linea.get("descrizione") or linea.get("description") or ""))
    return " ".join(p for p in parti if p)


def classifica_costo_completo(
    supplier_name: str,
    descrizione: str = "",
    linee_fattura: Optional[List[Dict]] = None,
    importo: Optional[float] = None,
) -> Dict[str, Any]:
    """Classifica una fattura di costo sui tre assi con una sola chiamata.

    Ritorna:
      {
        "centro_costo": {"id", "config", "confidence"},
        "conto_economico": {"categoria", "deducibilita": {...}},
        "piano_conti": {"conto_codice", "conto_nome", "categoria_merceologica",
                        "categoria_fiscale", "deducibilita_ires",
                        "deducibilita_irap", "confidenza"},
      }
    I singoli motori restano invariati: qui si delega e si normalizza l'output.
    """
    desc_completa = (descrizione or "").strip()
    if not desc_completa:
        desc_completa = _testo_linee(linee_fattura)

    # --- Asse 1: centro di costo analitico ---
    cdc_id, cdc_config, cdc_conf = _cdc.classifica_fattura_per_centro_costo(
        supplier_name, descrizione or "", linee_fattura
    )

    # --- Asse 2: conto economico civilistico + deducibilità ---
    categoria_ce = _ce.classifica_fornitore(supplier_name, desc_completa)
    deducibilita_ce: Dict[str, Any] = {}
    if importo is not None:
        deducibilita_ce = _ce.calcola_deducibilita(categoria_ce, float(importo))

    # --- Asse 3: piano dei conti + deducibilità IRES/IRAP ---
    if linee_fattura:
        pc_raw = _pc.categorizza_fattura_completa(linee_fattura, supplier_name or "")
        piano_conti = pc_raw
    else:
        res = _pc.categorizza_descrizione(desc_completa, supplier_name or "")
        piano_conti = {
            "categoria_merceologica": res.categoria_merceologica,
            "conto_codice": res.conto_codice,
            "conto_nome": res.conto_nome,
            "categoria_fiscale": getattr(res.categoria_fiscale, "value", str(res.categoria_fiscale)),
            "deducibilita_ires": res.percentuale_deducibilita_ires,
            "deducibilita_irap": res.percentuale_deducibilita_irap,
            "note_fiscali": res.note_fiscali,
            "confidenza": res.confidenza,
        }

    return {
        "centro_costo": {
            "id": cdc_id,
            "config": cdc_config,
            "confidence": cdc_conf,
        },
        "conto_economico": {
            "categoria": categoria_ce,
            "deducibilita": deducibilita_ce,
        },
        "piano_conti": piano_conti,
    }
