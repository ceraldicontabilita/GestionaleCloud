"""Lettura conservativa del foglio presenze mensile Ceraldi.

Il parser non conosce il database e non decide l'identita' dei dipendenti:
ricava il codice fiscale dal riepilogo dello stesso file e restituisce record
giornalieri normalizzati. L'associazione al record HR avviene nel router.
"""

from __future__ import annotations

import re
import unicodedata
import calendar
import csv
import io
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


_CODICI_GRIGLIA = {"P", "AS", "F", "PE", "M", "R", "RS", "CH", "FNL", "X"}
_MESI = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}


def _periodo_griglia(righe: List[tuple], nome_file: str = "") -> Tuple[int, int]:
    primi = " ".join(str(v or "") for row in righe[:3] for v in row)
    testo = testo_norm(primi)
    anno_match = re.search(r"\b(20\d{2})\b", testo)
    mese = next((numero for nome, numero in _MESI.items() if nome in testo), None)
    if anno_match and mese:
        return int(anno_match.group(1)), mese
    file_match = re.search(r"(20\d{2})[_-](0?[1-9]|1[0-2])", nome_file or "")
    if file_match:
        return int(file_match.group(1)), int(file_match.group(2))
    raise ValueError("mese e anno non riconoscibili dal titolo o dal nome del file")


def analizza_presenze_griglia(righe: Iterable[Iterable[Any]], nome_file: str = "") -> Dict[str, Any]:
    """Legge la griglia giorno-per-giorno esportata dalla pagina Presenze."""
    righe = [tuple(row) for row in righe]
    anno, mese = _periodo_griglia(righe, nome_file)
    giorni_mese = calendar.monthrange(anno, mese)[1]
    header_idx = None
    colonne_giorni: Dict[int, int] = {}
    for idx, row in enumerate(righe[:12]):
        if not row or testo_norm(row[0]) != "dipendente":
            continue
        for colonna, valore in enumerate(row[1:], 1):
            try:
                giorno = int(str(valore).strip())
            except (TypeError, ValueError):
                continue
            if 1 <= giorno <= giorni_mese:
                colonne_giorni[giorno] = colonna
        if set(colonne_giorni) == set(range(1, giorni_mese + 1)):
            header_idx = idx
            break
    if header_idx is None:
        raise ValueError("griglia non valida: servono Dipendente e tutti i giorni del mese")

    record: List[Dict[str, Any]] = []
    errori: List[Dict[str, Any]] = []
    nominativi = set()
    for numero, row in enumerate(righe[header_idx + 1:], header_idx + 2):
        nome = str(row[0] if row else "").strip()
        if not nome:
            continue
        if testo_norm(nome).startswith("legenda"):
            break
        nominativi.add(nome)
        for giorno, colonna in colonne_giorni.items():
            valore = row[colonna] if colonna < len(row) else None
            codice = str(valore or "").strip().upper()
            if not codice:
                continue
            if codice not in _CODICI_GRIGLIA:
                errori.append({"foglio": nome_file or "Griglia presenze", "riga": numero,
                               "nome": nome, "motivo": f"codice non riconosciuto al giorno {giorno}: {codice}"})
                continue
            record.append({
                "codice_fiscale": None,
                "nome_norm": nome_norm(nome),
                "nome_file": nome,
                "data": f"{anno:04d}-{mese:02d}-{giorno:02d}",
                "stato": "presente" if codice == "P" else "assente" if codice == "AS" else "giustificato",
                "giustificativo": codice,
                "entrata": None,
                "note": "Importato dalla griglia mensile Presenze",
                "fonti": [{"foglio": nome_file or "Griglia presenze", "riga": numero}],
            })
    if not record:
        raise ValueError("la griglia non contiene alcun codice presenza")
    conteggi: Dict[str, int] = {}
    for voce in record:
        codice = voce["giustificativo"]
        conteggi[codice] = conteggi.get(codice, 0) + 1
    return {
        "periodo": f"{anno:04d}-{mese:02d}",
        "record": sorted(record, key=lambda x: (x["nome_file"], x["data"])),
        "conteggi": conteggi,
        "errori": errori,
        "dipendenti_file": [],
        "nominativi_da_associare": sorted(nominativi),
        "formato": "griglia",
    }


def analizza_presenze_csv(raw: bytes, nome_file: str = "") -> Dict[str, Any]:
    try:
        testo = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        testo = raw.decode("cp1252")
    try:
        dialetto = csv.Sniffer().sniff(testo[:4096], delimiters=";,\t")
        righe = csv.reader(io.StringIO(testo), dialect=dialetto)
    except csv.Error:
        righe = csv.reader(io.StringIO(testo), delimiter=";")
    return analizza_presenze_griglia(righe, nome_file)


def indicizza_dipendenti_per_nome(dipendenti: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    indice: Dict[str, List[Dict[str, Any]]] = {}
    for dip in dipendenti:
        varianti = {
            nome_norm(dip.get("nome_completo")),
            nome_norm(f"{dip.get('cognome', '')} {dip.get('nome', '')}"),
            nome_norm(f"{dip.get('nome', '')} {dip.get('cognome', '')}"),
        }
        for variante in varianti - {""}:
            if dip not in indice.setdefault(variante, []):
                indice[variante].append(dip)
    return indice


def analizza_presenze_workbook(wb, nome_file: str = "") -> Dict[str, Any]:
    titoli = {testo_norm(ws.title) for ws in wb.worksheets}
    richiesti = {testo_norm(x) for x in ("Riepilogo Consulente", "Presenze Giornaliere", "Assenze, Ferie, Malattie")}
    if not richiesti.issubset(titoli):
        ultimo_errore = None
        for ws in wb.worksheets:
            try:
                return analizza_presenze_griglia(ws.iter_rows(values_only=True), nome_file or ws.title)
            except ValueError as exc:
                ultimo_errore = exc
        raise ValueError(str(ultimo_errore or "griglia presenze non riconosciuta"))
    return _analizza_presenze_consulente(wb)


def _analizza_presenze_consulente(wb) -> Dict[str, Any]:
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

    # Il foglio elenca le sole giornate lavorate e le assenze certificate.
    # Per ogni persona effettivamente presente nel dettaglio, i giorni residui
    # del mese sono quindi riposi. Non estendiamo la regola ai nominativi che
    # compaiono soltanto nel riepilogo (es. una persona senza alcuna giornata).
    periodi = sorted({r["data"][:7] for r in celle.values()})
    if len(periodi) != 1:
        raise ValueError("il file deve contenere un solo mese di presenze")
    anno, mese = (int(x) for x in periodi[0].split("-"))
    giorni_mese = calendar.monthrange(anno, mese)[1]
    identita = {}
    for key, voce in celle.items():
        identita[key[0]] = {
            "codice_fiscale": voce.get("codice_fiscale"),
            "nome_file": voce["nome_file"],
            "nome_norm": voce.get("nome_norm") or nome_norm(voce["nome_file"]),
        }
    for ident, persona in identita.items():
        for giorno in range(1, giorni_mese + 1):
            data_giorno = f"{anno:04d}-{mese:02d}-{giorno:02d}"
            key = (ident, data_giorno)
            if key in celle:
                continue
            celle[key] = {
                **persona, "data": data_giorno, "stato": "giustificato",
                "giustificativo": "RS", "entrata": None,
                "note": "Riposo — nessuna presenza nel dettaglio giornaliero Excel",
                "fonti": [{"foglio": giornaliere.title, "riga": None}],
            }

    record = sorted(celle.values(), key=lambda x: (x["nome_file"], x["data"]))
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
