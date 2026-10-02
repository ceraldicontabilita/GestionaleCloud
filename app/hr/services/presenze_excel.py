"""Lettura conservativa del foglio presenze mensile Ceraldi.

Il parser non conosce il database e non decide l'identita' dei dipendenti:
ricava il codice fiscale dal riepilogo dello stesso file e restituisce record
giornalieri normalizzati. L'associazione al record HR avviene nel router.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Tuple


def testo_norm(value: Any) -> str:
    testo = unicodedata.normalize("NFKD", str(value or ""))
    testo = "".join(c for c in testo if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", testo).split())


def nome_norm(value: Any) -> str:
    return " ".join(testo_norm(value).upper().split())


def data_iso(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    testo = str(value or "").strip()[:10]
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(testo, formato).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise ValueError(f"data non valida: {value!r}")


def _foglio(wb, titolo: str):
    cercato = testo_norm(titolo)
    for ws in wb.worksheets:
        if testo_norm(ws.title) == cercato:
            return ws
    raise ValueError(f"foglio '{titolo}' non trovato")


def _header(ws, richiesti: Iterable[str]) -> Tuple[int, Dict[str, int]]:
    richiesti_norm = {testo_norm(x) for x in richiesti}
    for numero, row in enumerate(ws.iter_rows(min_row=1, max_row=12, values_only=True), 1):
        mappa = {testo_norm(v): i for i, v in enumerate(row) if v not in (None, "")}
        if richiesti_norm.issubset(mappa):
            return numero, mappa
    raise ValueError(f"intestazioni mancanti nel foglio '{ws.title}'")


def _val(row: tuple, mappa: Dict[str, int], nome: str):
    indice = mappa.get(testo_norm(nome))
    return row[indice] if indice is not None and indice < len(row) else None


def _unisci_note(*parti: Any) -> str:
    viste = []
    for parte in parti:
        testo = str(parte or "").strip()
        if testo and testo not in viste:
            viste.append(testo)
    return " · ".join(viste)


def analizza_presenze_workbook(wb) -> Dict[str, Any]:
    """Restituisce celle P/M/F/PE/R/AS, senza inventare festivita' o riposi.

    Le assenze certificate prevalgono sulle timbrature fisiche. In particolare,
    se una persona ha timbrato durante una malattia, l'entrata resta tracciata
    ma la cella destinata al foglio paga e' M.
    """
    riepilogo = _foglio(wb, "Riepilogo Consulente")
    riga_r, map_r = _header(riepilogo, ("Dipendente", "Codice fiscale"))
    cf_per_nome: Dict[str, str] = {}
    errori: List[Dict[str, Any]] = []
    for numero, row in enumerate(
        riepilogo.iter_rows(min_row=riga_r + 1, values_only=True), riga_r + 1
    ):
        nome = str(_val(row, map_r, "Dipendente") or "").strip()
        cf = re.sub(r"\s+", "", str(_val(row, map_r, "Codice fiscale") or "")).upper()
        if not nome or nome_norm(nome) == "TOTALE MESE":
            continue
        if re.fullmatch(r"[A-Z0-9]{16}", cf):
            cf_per_nome[nome_norm(nome)] = cf
        else:
            errori.append({"foglio": riepilogo.title, "riga": numero, "nome": nome,
                           "motivo": "codice fiscale mancante o non valido"})

    giornaliere = _foglio(wb, "Presenze Giornaliere")
    riga_g, map_g = _header(giornaliere, ("Dipendente", "Data", "Entrata"))
    celle: Dict[Tuple[str, str], Dict[str, Any]] = {}
    nomi_senza_cf = set()
    for numero, row in enumerate(
        giornaliere.iter_rows(min_row=riga_g + 1, values_only=True), riga_g + 1
    ):
        nome = str(_val(row, map_g, "Dipendente") or "").strip()
        if not nome:
            continue
        try:
            giorno = data_iso(_val(row, map_g, "Data"))
        except ValueError as exc:
            errori.append({"foglio": giornaliere.title, "riga": numero, "nome": nome,
                           "motivo": str(exc)})
            continue
        n_norm = nome_norm(nome)
        cf = cf_per_nome.get(n_norm)
        if not cf:
            if n_norm not in nomi_senza_cf:
                errori.append({"foglio": giornaliere.title, "riga": numero, "nome": nome,
                               "nome_norm": n_norm,
                               "motivo": "nominativo giornaliero assente dal riepilogo: richiede associazione esplicita"})
                nomi_senza_cf.add(n_norm)
        key = (cf or f"nome:{n_norm}", giorno)
        if key in celle:
            errori.append({"foglio": giornaliere.title, "riga": numero, "nome": nome,
                           "motivo": "presenza duplicata per la stessa data"})
            continue
        celle[key] = {
            "codice_fiscale": cf,
            "nome_norm": n_norm,
            "nome_file": nome,
            "data": giorno,
            "stato": "presente",
            "giustificativo": "P",
            "entrata": str(_val(row, map_g, "Entrata") or "").strip() or None,
            "note": _unisci_note(_val(row, map_g, "Tipo timbratura"), _val(row, map_g, "Note")),
            "fonti": [{"foglio": giornaliere.title, "riga": numero}],
        }

    assenze = _foglio(wb, "Assenze, Ferie, Malattie")
    riga_a, map_a = _header(assenze, ("Dipendente", "Tipo", "Dal", "Al"))
    codici = {
        "malattia": "M", "ferie": "F", "permesso": "PE", "rol": "R",
        "assenza": "AS", "assente": "AS",
    }
    for numero, row in enumerate(
        assenze.iter_rows(min_row=riga_a + 1, values_only=True), riga_a + 1
    ):
        nome = str(_val(row, map_a, "Dipendente") or "").strip()
        if not nome:
            continue
        tipo = testo_norm(_val(row, map_a, "Tipo"))
        codice = codici.get(tipo)
        if not codice:
            errori.append({"foglio": assenze.title, "riga": numero, "nome": nome,
                           "motivo": f"tipo assenza non riconosciuto: {tipo or '-'}"})
            continue
        cf = cf_per_nome.get(nome_norm(nome))
        if not cf:
            errori.append({"foglio": assenze.title, "riga": numero, "nome": nome,
                           "motivo": "nominativo senza codice fiscale nel riepilogo"})
            continue
        try:
            dal = datetime.strptime(data_iso(_val(row, map_a, "Dal")), "%Y-%m-%d").date()
            al = datetime.strptime(data_iso(_val(row, map_a, "Al") or _val(row, map_a, "Dal")), "%Y-%m-%d").date()
        except ValueError as exc:
            errori.append({"foglio": assenze.title, "riga": numero, "nome": nome,
                           "motivo": str(exc)})
            continue
        if al < dal or (al - dal).days > 366:
            errori.append({"foglio": assenze.title, "riga": numero, "nome": nome,
                           "motivo": "intervallo assenza non valido"})
            continue
        protocollo = _val(row, map_a, "Protocollo INPS")
        nota = _unisci_note(
            f"{str(_val(row, map_a, 'Tipo') or '').strip()} da Excel",
            f"Protocollo INPS: {protocollo}" if protocollo else None,
            _val(row, map_a, "Note"),
        )
        corrente = dal
        while corrente <= al:
            giorno = corrente.isoformat()
            key = (cf, giorno)
            precedente = celle.get(key, {})
            celle[key] = {
                "codice_fiscale": cf,
                "nome_file": nome,
                "data": giorno,
                "stato": "assente" if codice == "AS" else "giustificato",
                "giustificativo": codice,
                "entrata": precedente.get("entrata"),
                "note": _unisci_note(precedente.get("note"), nota),
                "fonti": precedente.get("fonti", []) + [{"foglio": assenze.title, "riga": numero}],
            }
            corrente += timedelta(days=1)

    record = sorted(celle.values(), key=lambda x: (x["nome_file"], x["data"]))
    periodi = sorted({r["data"][:7] for r in record})
    if len(periodi) != 1:
        raise ValueError("il file deve contenere un solo mese di presenze")
    conteggi: Dict[str, int] = {}
    for r in record:
        codice = r["giustificativo"]
        conteggi[codice] = conteggi.get(codice, 0) + 1
    return {
        "periodo": periodi[0],
        "record": record,
        "conteggi": conteggi,
        "errori": errori,
        "dipendenti_file": sorted({r["codice_fiscale"] for r in record if r["codice_fiscale"]}),
        "nominativi_da_associare": sorted({r["nome_file"] for r in record if not r["codice_fiscale"]}),
    }
