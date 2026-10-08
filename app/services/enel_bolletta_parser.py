"""Parser deterministico delle bollette Enel Energia.

Salva soltanto misure aggregate e provenienza; anagrafica, POD e coordinate di
pagamento restano nel documento originale protetto.
"""
from __future__ import annotations

import base64
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

import fitz


def _intero_italiano(value: str) -> int:
    return int(re.sub(r"[^0-9]", "", value or "") or 0)


def estrai_testo_pdf(pdf: bytes) -> str:
    doc = fitz.open(stream=pdf, filetype="pdf")
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def _serie_storica(testo: str, nome: str) -> List[float]:
    match = re.search(rf"(?m)^\s*{re.escape(nome)}\s+([0-9][0-9.\s,]+)$", testo)
    if not match:
        return []
    valori = []
    for token in match.group(1).split():
        token = token.strip()
        if re.fullmatch(r"\d+(?:[.,]\d+)?", token):
            if nome == "kW max":
                valori.append(float(token.replace(",", ".")))
            else:
                valori.append(float(token.replace(".", "").replace(",", ".")))
    return valori


def parse_bolletta_enel_testo(testo: str) -> Dict[str, Any]:
    testo = str(testo or "").replace("\xa0", " ")
    annuo = re.search(
        r"Consumo annuo\s*\(dal\s*\d{2}\.\d{2}\.(20\d{2})\s*al\s*\d{2}\.\d{2}\.20\d{2}\)"
        r"\s*F1\s*F2\s*F3\s*Tot\.?\s*consumo\s*"
        r"([\d.]+)\s*kWh\s*([\d.]+)\s*kWh\s*([\d.]+)\s*kWh\s*([\d.]+)",
        testo, re.IGNORECASE | re.DOTALL,
    )
    risultato: Dict[str, Any] = {"fornitore": "Enel Energia", "mensili": []}
    if annuo:
        anno = int(annuo.group(1))
        totali = {
            "f1_kwh": _intero_italiano(annuo.group(2)),
            "f2_kwh": _intero_italiano(annuo.group(3)),
            "f3_kwh": _intero_italiano(annuo.group(4)),
            "totale_kwh": _intero_italiano(annuo.group(5)),
        }
        risultato.update({"anno": anno, "annuale": totali})

        f1, f2, f3, tot = (_serie_storica(testo, n) for n in ("F1", "F2", "F3", "Tot"))
        potenze = _serie_storica(testo, "kW max")
        if all(len(s) >= 12 for s in (f1, f2, f3, tot)):
            f1, f2, f3, tot = (s[-12:] for s in (f1, f2, f3, tot))
            potenze = potenze[-12:] if len(potenze) >= 12 else []
            mensili = []
            for indice in range(12):
                riga = {
                    "anno": anno, "mese": indice + 1,
                    "f1_kwh": int(f1[indice]), "f2_kwh": int(f2[indice]),
                    "f3_kwh": int(f3[indice]), "totale_kwh": int(tot[indice]),
                }
                if potenze:
                    riga["potenza_massima_kw"] = potenze[indice]
                if abs(riga["f1_kwh"] + riga["f2_kwh"] + riga["f3_kwh"] - riga["totale_kwh"]) <= 1:
                    mensili.append(riga)
            if len(mensili) == 12 and sum(r["totale_kwh"] for r in mensili) == totali["totale_kwh"]:
                risultato["mensili"] = mensili

    periodo = re.search(
        r"Consumo (?:rilevato|fatturato)\s*\(dal\s*(\d{2})\.(\d{2})\.(20\d{2})\s*al\s*"
        r"\d{2}\.\d{2}\.20\d{2}\)\s*F1\s*F2\s*F3\s*Totale energia\s*"
        r"([\d.]+)\s*kWh\s*([\d.]+)\s*kWh\s*([\d.]+)\s*kWh\s*([\d.]+)\s*kWh",
        testo, re.IGNORECASE | re.DOTALL,
    )
    if periodo:
        risultato["periodo_fatturato"] = {
            "anno": int(periodo.group(3)), "mese": int(periodo.group(2)),
            "f1_kwh": _intero_italiano(periodo.group(4)),
            "f2_kwh": _intero_italiano(periodo.group(5)),
            "f3_kwh": _intero_italiano(periodo.group(6)),
            "totale_kwh": _intero_italiano(periodo.group(7)),
        }
    return risultato


def parse_bolletta_enel(pdf: bytes | str) -> Dict[str, Any]:
    if isinstance(pdf, str):
        pdf = base64.b64decode(pdf)
    return parse_bolletta_enel_testo(estrai_testo_pdf(pdf))


async def salva_consumi_enel(db, parsed: Dict[str, Any], source_hash: str, documento_id: str) -> int:
    righe = parsed.get("mensili") or ([parsed["periodo_fatturato"]] if parsed.get("periodo_fatturato") else [])
    aggiornati = 0
    for riga in righe:
        if not riga.get("anno") or not riga.get("mese"):
            continue
        await db["consumi_energia"].update_one(
            {"fornitore": "Enel Energia", "anno": riga["anno"], "mese": riga["mese"]},
            {"$set": {
                **riga,
                "fornitore": "Enel Energia",
                "fonte": "bolletta_email",
                "source_hash": source_hash,
                "documento_id": documento_id,
                "aggiornato_il": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )
        aggiornati += 1
    return aggiornati
