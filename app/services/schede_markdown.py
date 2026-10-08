"""Schede Markdown delle letture: la copia di cio' che il motore ha letto.

Ogni PDF letto diventa una **scheda** in Markdown (collezione
``schede_markdown``, chiave ``<tipo>:<sha256 del PDF>``): un'intestazione con
tipo, impronta, file, versione del lettore e data, poi una sezione per ogni
busta con i suoi campi. E' la fonte per ricaricare i dati senza rileggere i
PDF: ``leggi_scheda`` la riporta ai campi che lo scrittore unico si aspetta.

Accanto alle schede c'e' il **registro** per tipo e anno (collezione
``registri_markdown``, chiave ``<tipo>:<anno>``): una tabella con una riga per
busta, la piu' recente in alto. Si riscrive ogni volta che una scheda di
quell'anno nasce o viene tolta, quindi aggiunge le righe dei PDF nuovi e perde
quelle dei cedolini eliminati.

Gli importi sono testo con due decimali (``1018.00``), il codice fiscale e i
codici delle voci restano testo; una cella vuota e' un valore assente, mai
zero.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional

SCHEDE = "schede_markdown"
REGISTRI = "registri_markdown"
TIPO_CEDOLINO = "cedolino"
VERSIONE_LETTORE_CEDOLINI = "cedolini_motore/2"

STATO_ATTIVA = "attiva"
STATO_ELIMINATA = "eliminata"

# Campi della busta nell'ordine in cui si scrivono. Il tipo decide come si
# rilegge la cella: gli importi tornano numeri, gli interi interi, il resto
# resta testo (un «5» di livello non e' un importo).
_CAMPI_BUSTA = (
    ("codice_fiscale", "testo"), ("nome_dipendente", "testo"),
    ("anno", "intero"), ("mese", "intero"), ("tipo_cedolino", "testo"),
    ("netto", "importo"), ("stato_netto", "testo"),
    ("netto_letto", "importo"), ("netto_calcolato", "importo"),
    ("lordo", "importo"), ("totale_trattenute", "importo"),
    ("tfr_quota", "importo"), ("ore_lavorate", "numero"), ("giorni_lavorati", "numero"),
    ("livello", "testo"), ("formato_rilevato", "testo"),
    ("cessato", "sino"), ("data_cessazione_rilevata", "testo"),
    ("source_page_start", "intero"), ("source_page_end", "intero"),
    ("source_document_pages", "intero"), ("impronta_busta", "testo"),
)
_TIPI = dict(_CAMPI_BUSTA)
# Gruppi annidati: ``gruppo.chiave`` nella tabella.
_GRUPPI = ("ferie_permessi", "dati_extra", "dati_chiave")
_GRUPPI_NUMERICI = ("ferie_permessi", "dati_extra")

_NUMERO = re.compile(r"^-?\d+(?:\.\d+)?$")
_MESI = ("", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
         "agosto", "settembre", "ottobre", "novembre", "dicembre")


def _ora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _importo(valore: Any) -> str:
    if valore is None or valore == "":
        return ""
    try:
        return str(Decimal(str(valore)).quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError):
        return str(valore)


def _numero(valore: Any) -> str:
    if valore is None or valore == "":
        return ""
    try:
        return format(Decimal(str(valore)).normalize(), "f")
    except (InvalidOperation, ValueError):
        return str(valore)


def _cella(testo: Any) -> str:
    return str(testo).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _scrivi_valore(tipo: str, valore: Any) -> str:
    if valore is None:
        return ""
    if tipo == "importo":
        return _importo(valore)
    if tipo in ("numero", "intero"):
        return _numero(valore)
    if tipo == "sino":
        return "si" if valore else "no"
    return _cella(valore)


def _leggi_valore(tipo: str, testo: str) -> Any:
    if testo == "":
        return None
    if tipo == "intero":
        return int(Decimal(testo))
    if tipo in ("importo", "numero"):
        return float(Decimal(testo))
    if tipo == "sino":
        return testo == "si"
    return testo


def _tabella(righe: Iterable[tuple]) -> List[str]:
    out = ["| campo | valore |", "| --- | --- |"]
    out += [f"| {k} | {v} |" for k, v in righe]
    return out


def _sezione_busta(numero: int, busta: Dict[str, Any]) -> List[str]:
    periodo = f"{int(busta['mese']):02d}/{busta['anno']}" if busta.get("mese") and busta.get("anno") else "periodo non letto"
    righe = [(campo, _scrivi_valore(tipo, busta.get(campo))) for campo, tipo in _CAMPI_BUSTA]
    for gruppo in _GRUPPI:
        valori = busta.get(gruppo) or {}
        for chiave in sorted(valori):
            v = valori[chiave]
            if gruppo in _GRUPPI_NUMERICI and isinstance(v, (int, float)) and not isinstance(v, bool):
                testo = _numero(v)
            elif isinstance(v, bool):
                testo = "si" if v else "no"
            else:
                testo = "" if v is None else _cella(v)
            righe.append((f"{gruppo}.{chiave}", testo))
    out = [f"## Busta {numero} — {busta.get('nome_dipendente') or busta.get('codice_fiscale') or 'N/D'} — {periodo}", ""]
    out += _tabella(righe)
    voci = busta.get("voci") or []
    if voci:
        out += ["", "### Voci", "", "| codice | descrizione | valori |", "| --- | --- | --- |"]
        out += [f"| {_cella(v.get('codice', ''))} | {_cella(v.get('descrizione', ''))} | "
                f"{_cella(' ; '.join(v.get('valori') or []))} |" for v in voci]
    return out + [""]


def _sezione_presenze(numero: int, foglio: Dict[str, Any]) -> List[str]:
    periodo = f"{int(foglio['mese']):02d}/{foglio['anno']}" if foglio.get("mese") and foglio.get("anno") else "periodo non letto"
    righe = [
        ("codice_fiscale", _cella(foglio.get("codice_fiscale") or "")),
        ("nome_dipendente", _cella(foglio.get("nome_dipendente") or "")),
        ("anno", _numero(foglio.get("anno"))), ("mese", _numero(foglio.get("mese"))),
        ("pagina", _numero(foglio.get("pagina"))),
        ("giorni_lavorati", _numero(foglio.get("giorni_lavorati"))),
        ("giorni_con_giustificativo", _numero(foglio.get("giorni_con_giustificativo"))),
    ]
    out = [f"## Presenze {numero} — {foglio.get('nome_dipendente') or foglio.get('codice_fiscale') or 'N/D'} — {periodo}", ""]
    out += _tabella(righe)
    giorni = foglio.get("presenze") or []
    if giorni:
        out += ["", "### Giorni", "", "| giorno | settimana | ore | giustificativo |", "| --- | --- | --- | --- |"]
        out += [f"| {g.get('giorno', '')} | {g.get('giorno_settimana', '')} | {g.get('ore_ordinarie') or ''} | "
                f"{g.get('giustificativo') or ''} |" for g in giorni]
    return out + [""]


def scheda_cedolino(lettura: Dict[str, Any], *, sha256: str, filename: str = "",
                    drive_file_id: str = "", source_path: str = "", letto_il: str = "") -> str:
    """Il Markdown di una lettura del motore unico dei cedolini."""
    testa = [
        "---",
        f"tipo: {TIPO_CEDOLINO}",
        f"sha256: {sha256}",
        f"file: {_cella(filename)}",
        f"drive_file_id: {drive_file_id or ''}",
        f"percorso: {_cella(source_path)}",
        f"lettore: {VERSIONE_LETTORE_CEDOLINI}",
        f"letto_il: {letto_il or _ora()}",
        f"esito: {lettura.get('esito')}",
        f"motivo: {_cella(lettura.get('motivo') or '')}",
        "---",
        "",
        f"# Cedolino — {_cella(filename or sha256)}",
        "",
    ]
    corpo: List[str] = []
    buste = list(lettura.get("buste") or []) + list(lettura.get("fuori_periodo") or [])
    for i, busta in enumerate(buste, start=1):
        corpo += _sezione_busta(i, busta)
    for i, foglio in enumerate(lettura.get("presenze") or [], start=1):
        corpo += _sezione_presenze(i, foglio)
    return "\n".join(testa + corpo).rstrip() + "\n"


def _celle(riga: str) -> List[str]:
    interno = riga.strip()[1:-1]
    celle, corrente, i = [], "", 0
    while i < len(interno):
        c = interno[i]
        if c == "\\" and i + 1 < len(interno):
            corrente += interno[i + 1]
            i += 2
            continue
        if c == "|":
            celle.append(corrente.strip())
            corrente = ""
        else:
            corrente += c
        i += 1
    celle.append(corrente.strip())
    return celle


def leggi_scheda(markdown: str) -> Dict[str, Any]:
    """Dal Markdown ai dati: intestazione, buste (con voci) e fogli presenze."""
    testa: Dict[str, str] = {}
    righe = markdown.splitlines()
    if righe and righe[0].strip() == "---":
        fine = righe.index("---", 1)
        for riga in righe[1:fine]:
            chiave, _, valore = riga.partition(":")
            testa[chiave.strip()] = valore.strip()
        righe = righe[fine + 1:]

    buste: List[Dict[str, Any]] = []
    presenze: List[Dict[str, Any]] = []
    corrente: Optional[Dict[str, Any]] = None
    tabella = None
    for riga in righe:
        if riga.startswith("## Busta "):
            corrente = {"voci": []}
            buste.append(corrente)
            tabella = "campi"
            continue
        if riga.startswith("## Presenze "):
            corrente = {"presenze": []}
            presenze.append(corrente)
            tabella = "presenze_campi"
            continue
        if riga.startswith("### Voci"):
            tabella = "voci"
            continue
        if riga.startswith("### Giorni"):
            tabella = "giorni"
            continue
        if corrente is None or not riga.startswith("|") or set(riga.replace("|", "").strip()) <= {"-", " "}:
            continue
        celle = _celle(riga)
        if celle[0] in ("campo", "codice", "giorno"):
            continue
        if tabella == "campi":
            chiave, testo = celle[0], celle[1] if len(celle) > 1 else ""
            gruppo, _, sotto = chiave.partition(".")
            if sotto and gruppo in _GRUPPI:
                if gruppo in _GRUPPI_NUMERICI and _NUMERO.match(testo):
                    valore: Any = float(Decimal(testo))
                elif testo in ("si", "no"):
                    valore = testo == "si"
                else:
                    valore = testo or None
                corrente.setdefault(gruppo, {})[sotto] = valore
            else:
                corrente[chiave] = _leggi_valore(_TIPI.get(chiave, "testo"), testo)
        elif tabella == "voci":
            corrente["voci"].append({
                "codice": celle[0], "descrizione": celle[1],
                "valori": [v.strip() for v in celle[2].split(";") if v.strip()] if len(celle) > 2 else [],
            })
        elif tabella == "presenze_campi":
            chiave, testo = celle[0], celle[1] if len(celle) > 1 else ""
            tipo = "testo" if chiave in ("codice_fiscale", "nome_dipendente") else "intero"
            corrente[chiave] = _leggi_valore(tipo, testo)
        elif tabella == "giorni":
            corrente["presenze"].append({
                "giorno": int(celle[0]) if celle[0].isdigit() else celle[0],
                "giorno_settimana": celle[1], "ore_ordinarie": celle[2] or None,
                "giustificativo": celle[3] or None,
            })
    return {"intestazione": testa, "buste": buste, "presenze": presenze}


def _righe_registro(buste: Iterable[Dict[str, Any]], sha256: str, filename: str) -> List[Dict[str, Any]]:
    return [{
        "anno": b.get("anno"), "mese": b.get("mese"),
        "codice_fiscale": b.get("codice_fiscale"), "nome_dipendente": b.get("nome_dipendente"),
        "tipo_cedolino": b.get("tipo_cedolino"), "netto": _importo(b.get("netto")),
        "stato_netto": b.get("stato_netto"), "lordo": _importo(b.get("lordo")),
        "totale_trattenute": _importo(b.get("totale_trattenute")),
        "sha256": sha256, "file": filename,
    } for b in buste if b.get("anno")]


def registro_markdown(tipo: str, anno: int, righe: List[Dict[str, Any]]) -> str:
    """Il registro di un anno: una riga per busta, la piu' recente in alto."""
    ordinate = sorted(righe, key=lambda r: (int(r.get("mese") or 0), str(r.get("nome_dipendente") or "")),
                      reverse=True)
    out = [
        "---", f"tipo: {tipo}", f"anno: {anno}", f"buste: {len(ordinate)}", f"aggiornato_il: {_ora()}", "---", "",
        f"# Cedolini {anno}", "",
        "| mese | dipendente | codice fiscale | tipo | netto | stato netto | lordo | trattenute | file | sha256 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in ordinate:
        mese = int(r.get("mese") or 0)
        out.append(
            f"| {_MESI[mese] if 0 < mese <= 12 else ''} | {_cella(r.get('nome_dipendente') or '')} | "
            f"{r.get('codice_fiscale') or ''} | {r.get('tipo_cedolino') or ''} | {r.get('netto') or ''} | "
            f"{r.get('stato_netto') or ''} | {r.get('lordo') or ''} | {r.get('totale_trattenute') or ''} | "
            f"{_cella(r.get('file') or '')} | {r.get('sha256') or ''} |"
        )
    return "\n".join(out) + "\n"


async def riscrivi_registro(db, tipo: str, anno: int) -> Dict[str, Any]:
    """Rifa il registro dell'anno dalle righe delle schede attive (senza leggere i Markdown)."""
    schede = await db[SCHEDE].find(
        {"tipo": tipo, "stato": STATO_ATTIVA},
        {"_id": 0, "righe": 1, "anni": 1},
    ).to_list(None)
    righe = [r for s in schede if anno in (s.get("anni") or []) for r in (s.get("righe") or [])
             if r.get("anno") == anno]
    markdown = registro_markdown(tipo, anno, righe)
    await db[REGISTRI].update_one(
        {"id": f"{tipo}:{anno}"},
        {"$set": {"id": f"{tipo}:{anno}", "tipo": tipo, "anno": anno, "buste": len(righe),
                  "markdown": markdown, "aggiornato_il": _ora()}},
        upsert=True,
    )
    return {"anno": anno, "buste": len(righe)}


async def salva_scheda_cedolino(db, lettura: Dict[str, Any], *, sha256: str, filename: str = "",
                                drive_file_id: str = "", source_path: str = "") -> Dict[str, Any]:
    """Scrive (o riscrive) la scheda di un PDF e aggiorna i registri degli anni toccati."""
    buste = list(lettura.get("buste") or []) + list(lettura.get("fuori_periodo") or [])
    righe = _righe_registro(lettura.get("buste") or [], sha256, filename)
    anni_prima = set()
    esistente = await db[SCHEDE].find_one({"id": f"{TIPO_CEDOLINO}:{sha256}"}, {"_id": 0, "anni": 1})
    if esistente:
        anni_prima = set(esistente.get("anni") or [])
    anni = sorted({r["anno"] for r in righe})
    ora = _ora()
    markdown = scheda_cedolino(lettura, sha256=sha256, filename=filename, drive_file_id=drive_file_id,
                               source_path=source_path, letto_il=ora)
    await db[SCHEDE].update_one(
        {"id": f"{TIPO_CEDOLINO}:{sha256}"},
        {"$set": {
            "id": f"{TIPO_CEDOLINO}:{sha256}", "tipo": TIPO_CEDOLINO, "sha256": sha256,
            "stato": STATO_ATTIVA, "esito": lettura.get("esito"), "file": filename,
            "drive_file_id": drive_file_id or None, "lettore": VERSIONE_LETTORE_CEDOLINI,
            "letto_il": ora, "anni": anni, "buste": len(buste), "righe": righe, "markdown": markdown,
        }},
        upsert=True,
    )
    for anno in sorted(set(anni) | anni_prima):
        await riscrivi_registro(db, TIPO_CEDOLINO, anno)
    return {"id": f"{TIPO_CEDOLINO}:{sha256}", "anni": anni, "buste": len(buste)}


async def togli_scheda(db, sha256: str, *, motivo: str, tipo: str = TIPO_CEDOLINO) -> Dict[str, Any]:
    """Il cedolino e' stato eliminato: la scheda resta, marcata, e il registro perde le sue righe."""
    scheda = await db[SCHEDE].find_one({"id": f"{tipo}:{sha256}"}, {"_id": 0, "anni": 1, "stato": 1})
    if not scheda:
        return {"esito": "non_trovata"}
    await db[SCHEDE].update_one({"id": f"{tipo}:{sha256}"}, {"$set": {
        "stato": STATO_ELIMINATA, "motivo_eliminazione": motivo, "eliminata_il": _ora(),
    }})
    for anno in scheda.get("anni") or []:
        await riscrivi_registro(db, tipo, anno)
    return {"esito": "eliminata", "anni": scheda.get("anni") or []}


def buste_da_ricaricare(markdown: str) -> List[Dict[str, Any]]:
    """Le buste della scheda nella forma che lo scrittore unico accetta, senza PDF."""
    scheda = leggi_scheda(markdown)
    testa = scheda["intestazione"]
    buste = []
    for busta in scheda["buste"]:
        dati = dict(busta)
        impronta = dati.pop("impronta_busta", None)
        if impronta:
            dati["file_hash"] = impronta      # stessa chiave documentale della prima lettura
        dati["netto_mese"] = dati.get("netto")
        dati["source_path"] = testa.get("percorso") or testa.get("file")
        dati["source_file_hash"] = testa.get("sha256")
        if testa.get("drive_file_id"):
            dati["drive_file_id"] = testa["drive_file_id"]
        buste.append(dati)
    return buste


CHIAVE_RICARICA = "ricarica_cedolini_da_schede"


async def ricarica_cedolini(db, *, anno: Optional[int] = None, dry_run: bool = True) -> Dict[str, Any]:
    """Riscrive i cedolini dalle schede Markdown, senza rileggere un solo PDF.

    Passa ogni busta allo scrittore unico (``cedolini_manager.registra_busta``)
    con la stessa chiave documentale della prima lettura: le buste gia' in
    archivio si aggiornano, non si duplicano. ``dry_run`` conta soltanto.
    """
    from app.services.cedolini_manager import registra_busta
    from app.services.cedolini_motore import PAYROLL_MIN_YEAR

    schede = await db[SCHEDE].find(
        {"tipo": TIPO_CEDOLINO, "stato": STATO_ATTIVA}, {"_id": 0, "id": 1, "anni": 1, "file": 1},
    ).to_list(None)
    if anno is not None:
        schede = [s for s in schede if anno in (s.get("anni") or [])]
    esito: Dict[str, Any] = {
        "dry_run": dry_run, "anno": anno, "schede": len(schede), "buste": 0,
        "cedolini_processati": 0, "buste_senza_netto": 0, "anagrafiche_create": 0,
        "prima_nota_create": 0, "riconciliati": 0, "errori": [],
    }
    for scheda in schede:
        completa = await db[SCHEDE].find_one({"id": scheda["id"]}, {"_id": 0, "markdown": 1})
        for busta in buste_da_ricaricare((completa or {}).get("markdown") or ""):
            anno_busta = busta.get("anno") or 0
            if anno_busta < PAYROLL_MIN_YEAR or (anno is not None and anno_busta != anno):
                continue
            esito["buste"] += 1
            if dry_run:
                continue
            await registra_busta(db, busta, filename=scheda.get("file") or "", pdf_data=None,
                                 pdf_text="", results=esito)
    return esito
