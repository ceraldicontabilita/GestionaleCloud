"""
Parser Fornitore da XML FatturaPA — Ceraldi ERP
================================================
Estrae automaticamente dalla fattura elettronica SDI:
  - Anagrafica fornitore (Tab 1)
  - Lista prodotti acquistati (Tab 3)
  - Storico prezzi (Tab 4)
  - Termini di pagamento (Tab 5)

Standard: FatturaPA v1.2 / v1.3 (DPR 633/1972, DM 3/4/2013)
Compatibile con tutti i file XML ricevuti da @pec.fatturapa.it
"""

import xml.etree.ElementTree as ET
from datetime import datetime, date
from typing import Optional


NS = {
    "p": "http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2",
    "p13": "http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.3",
}


def _text(el, path: str, default: str = "") -> str:
    """Estrae testo da un elemento XML con fallback."""
    if el is None:
        return default
    found = el.find(path)
    return (found.text or "").strip() if found is not None else default


def _float(el, path: str, default: float = 0.0) -> float:
    """Estrae float da XML."""
    val = _text(el, path)
    try:
        return float(val.replace(",", "."))
    except (ValueError, AttributeError):
        return default


def parse_fornitore_da_xml(xml_content: bytes) -> Optional[dict]:
    """
    Parsea una fattura XML SDI ed estrae:
      - Anagrafica fornitore
      - Lista linee prodotto con prezzi
      - Dati pagamento
    """
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        return None

    # Rimuovi namespace per semplificare i path
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]

    header = root.find(".//FatturaElettronicaHeader")
    body = root.find(".//FatturaElettronicaBody")
    if header is None or body is None:
        return None

    # ── Anagrafica cedente (fornitore) ────────────────────
    cedente = header.find("CedentePrestatore")
    if cedente is None:
        return None

    dati_anag = cedente.find(".//DatiAnagrafici")
    sede = cedente.find("Sede")

    piva_el = dati_anag.find("IdFiscaleIVA") if dati_anag else None
    piva = _text(piva_el, "IdCodice") if piva_el else ""
    cf = _text(dati_anag, "CodiceFiscale") if dati_anag else ""
    ragione = _text(dati_anag, ".//Denominazione") or _text(dati_anag, ".//Nome")
    regime = _text(dati_anag, "RegimeFiscale")

    # Contatti e SDI
    contatti = cedente.find("Contatti")
    pec = _text(contatti, "Email") if contatti else ""

    cessionario = header.find("CessionarioCommittente")
    sdi = _text(header, ".//DatiTrasmissione/CodiceDestinatario")

    anagrafica = {
        "ragione_sociale": ragione,
        "piva": piva,
        "codice_fiscale": cf or piva,
        "codice_sdi": sdi,
        "pec": pec,
        "regime_fiscale": regime,
        "sede": {
            "indirizzo": _text(sede, "Indirizzo"),
            "numero_civico": _text(sede, "NumeroCivico"),
            "cap": _text(sede, "CAP"),
            "comune": _text(sede, "Comune"),
            "provincia": _text(sede, "Provincia"),
            "nazione": _text(sede, "Nazione"),
        },
        "estratto_da_xml": True,
        "updated_at": datetime.utcnow(),
    }

    # ── Dati fattura ──────────────────────────────────────
    dati_gen = body.find(".//DatiGeneraliDocumento")
    numero_fattura = _text(dati_gen, "Numero")
    data_fattura_str = _text(dati_gen, "Data")
    try:
        data_fattura = datetime.strptime(data_fattura_str, "%Y-%m-%d").date()
    except ValueError:
        data_fattura = date.today()

    totale = _float(dati_gen, "ImportoTotaleDocumento")
    valuta = _text(dati_gen, "Divisa") or "EUR"

    # ── Prodotti (linee dettaglio) ────────────────────────
    prodotti = []
    for linea in body.findall(".//DettaglioLinee"):
        desc = _text(linea, "Descrizione")
        qty = _float(linea, "Quantita", 1.0)
        um = _text(linea, "UnitaMisura", "PZ")
        prezzo = _float(linea, "PrezzoUnitario")
        sconto_pct = 0.0
        sconto_el = linea.find(".//ScontoMaggiorazione")
        if sconto_el is not None:
            tipo = _text(sconto_el, "Tipo")
            perc = _float(sconto_el, "Percentuale")
            if tipo == "SC":  # sconto
                sconto_pct = perc
        prezzo_netto = prezzo * (1 - sconto_pct / 100)

        # Codice articolo fornitore
        codice_art = ""
        for cod in linea.findall(".//CodiceArticolo"):
            if _text(cod, "CodiceTipo") in ("ART", "COD", "EAN", "FORNITORE"):
                codice_art = _text(cod, "CodiceValore")
                break
        if not codice_art:
            codice_art = _text(linea, ".//CodiceArticolo/CodiceValore")

        prodotti.append({
            "numero_linea": int(_text(linea, "NumeroLinea", "0")),
            "codice_articolo": codice_art,
            "descrizione": desc,
            "quantita": qty,
            "unita_misura": um,
            "prezzo_unitario": prezzo,
            "sconto_pct": sconto_pct,
            "prezzo_netto": round(prezzo_netto, 4),
            "aliquota_iva": _float(linea, "AliquotaIVA"),
            "data_fattura": data_fattura.isoformat(),
            "numero_fattura": numero_fattura,
            "valuta": valuta,
        })

    # ── Dati pagamento ────────────────────────────────────
    pagamento_el = body.find(".//DatiPagamento")
    pagamento = {}
    if pagamento_el is not None:
        modalita = _text(pagamento_el, ".//ModalitaPagamento")
        termini = _text(pagamento_el, ".//GiorniTerminiPagamento")
        iban = _text(pagamento_el, ".//IBAN")
        pagamento = {
            "modalita_xml": modalita,      # MP02=Assegno, MP05=Bonifico, ecc.
            "termini_pagamento_gg": termini,
            "iban_fornitore": iban,
        }

    return {
        "anagrafica": anagrafica,
        "prodotti_fattura": prodotti,
        "fattura": {
            "numero": numero_fattura,
            "data": data_fattura.isoformat(),
            "totale": totale,
            "valuta": valuta,
            "piva_fornitore": piva,
        },
        "pagamento_xml": pagamento,
    }


def aggiorna_fornitore_da_fatture(fornitore: dict, nuova_fattura: dict) -> dict:
    """
    Aggiorna il documento fornitore con i dati di una nuova fattura XML.
    Aggiorna: prodotti (Tab 3) e storico_prezzi (Tab 4).
    """
    data_fattura = nuova_fattura["fattura"]["data"]
    numero_fattura = nuova_fattura["fattura"]["numero"]

    # Aggiorna anagrafica (ultima data fattura)
    if not fornitore.get("anagrafica", {}).get("prima_fattura_data"):
        fornitore.setdefault("anagrafica", {})["prima_fattura_data"] = data_fattura
    fornitore.setdefault("anagrafica", {})["ultima_fattura_data"] = data_fattura
    fornitore["anagrafica"]["n_fatture_totali"] =         fornitore["anagrafica"].get("n_fatture_totali", 0) + 1

    # Costruisci indici veloci
    prodotti_idx = {p["codice_articolo"] or p["descrizione"]: i
                    for i, p in enumerate(fornitore.get("prodotti", []))}
    storico_idx = {s["codice_articolo"] or s["descrizione"]: i
                   for i, s in enumerate(fornitore.get("storico_prezzi", []))}

    for linea in nuova_fattura.get("prodotti_fattura", []):
        chiave = linea.get("codice_articolo") or linea.get("descrizione", "")
        if not chiave:
            continue

        # ── Tab 3: aggiorna lista prodotti ──────────────
        if chiave in prodotti_idx:
            p = fornitore["prodotti"][prodotti_idx[chiave]]
            p["ultimo_acquisto"] = max(p.get("ultimo_acquisto", ""), data_fattura)
            p["n_acquisti"] = p.get("n_acquisti", 0) + 1
            p["quantita_totale_acquistata"] = round(
                p.get("quantita_totale_acquistata", 0) + linea["quantita"], 3
            )
        else:
            fornitore.setdefault("prodotti", []).append({
                "codice_articolo": linea.get("codice_articolo", ""),
                "descrizione": linea.get("descrizione", ""),
                "unita_misura": linea.get("unita_misura", "PZ"),
                "prima_acquisto": data_fattura,
                "ultimo_acquisto": data_fattura,
                "n_acquisti": 1,
                "quantita_totale_acquistata": linea["quantita"],
                "url_scheda": None,
                "immagine": None,
            })

        # ── Tab 4: aggiorna storico prezzi ──────────────
        entry_prezzo = {
            "data": data_fattura,
            "numero_fattura": numero_fattura,
            "prezzo_unitario": linea["prezzo_unitario"],
            "quantita": linea["quantita"],
            "sconto_pct": linea.get("sconto_pct", 0),
            "prezzo_netto": linea["prezzo_netto"],
        }

        if chiave in storico_idx:
            s = fornitore["storico_prezzi"][storico_idx[chiave]]
            s["storico"].append(entry_prezzo)
            s["storico"].sort(key=lambda x: x["data"])
            # Ricalcola trend
            prezzi = [e["prezzo_netto"] for e in s["storico"] if e["prezzo_netto"] > 0]
            if len(prezzi) >= 2:
                var = (prezzi[-1] - prezzi[0]) / prezzi[0] * 100
                s["variazione_pct"] = round(var, 2)
                s["trend"] = "crescita" if var > 2 else "calo" if var < -2 else "stabile"
            s["prezzo_attuale"] = prezzi[-1] if prezzi else 0
        else:
            fornitore.setdefault("storico_prezzi", []).append({
                "codice_articolo": linea.get("codice_articolo", ""),
                "descrizione": linea.get("descrizione", ""),
                "storico": [entry_prezzo],
                "prezzo_attuale": linea["prezzo_netto"],
                "variazione_pct": 0.0,
                "trend": "stabile",
            })

    fornitore["updated_at"] = datetime.utcnow()
    return fornitore
