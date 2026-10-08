"""Raccoglitore locale RT -> Google Drive Desktop.

Via **supplementare** dei corrispettivi: la primaria resta l'import degli XML
(Documenti > Import o la cartella unica). Gira sul PC del titolare, collegato
alla LAN del registratore (Render non raggiunge 192.168.x.x): copia i byte
originali in ``DATI SOCIETA CERALDI/DA ELABORARE`` via Drive Desktop, e lo
smistatore del gestionale fa parsing, deduplica e registrazione.

Ogni giro riprende dal giorno dell'ultima copia (compreso, perche' l'RT
aggiunge file durante la giornata) fino a oggi: un PC rimasto spento recupera
da solo le giornate perse. Alla prima esecuzione legge tutte le giornate che
l'RT conserva; ``--dal AAAAMMGG`` limita il recupero. Installazione come
attivita' pianificata di Windows: ``scripts/installa_sync_rt.ps1``.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def _private_base_url(raw: str) -> str:
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("RT_LOCAL_BASE_URL deve essere un URL http/https")
    try:
        ip = ipaddress.ip_address(parsed.hostname)
    except ValueError as exc:
        raise ValueError("Usare l'indirizzo IP privato del registratore") from exc
    if not (ip.is_private or ip.is_loopback):
        raise ValueError("RT_LOCAL_BASE_URL deve puntare a una rete privata")
    return raw.rstrip("/") + "/"


def _get(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "CeraldiERP-RT-Collector/1.0"})
    with urlopen(req, timeout=30) as response:
        return response.read()


def _links(url: str) -> list[str]:
    parser = _Links()
    parser.feed(_get(url).decode("utf-8", errors="replace"))
    out = []
    for href in parser.hrefs:
        if href.startswith(("?", "#")) or href in {"../", "/"}:
            continue
        target = urljoin(url, href)
        if target.startswith(url):
            out.append(target)
    return out


def _daily_directories(base_url: str) -> list[str]:
    dirs = []
    for url in _links(base_url):
        name = unquote(urlparse(url).path.rstrip("/").split("/")[-1])
        if re.fullmatch(r"20\d{6}", name) and url.endswith("/"):
            dirs.append(url)
    return sorted(set(dirs))


def _rt_xmls(directory_url: str) -> list[str]:
    result = []
    for url in _links(directory_url):
        name = unquote(urlparse(url).path.split("/")[-1])
        upper = name.upper()
        if upper.endswith(".XML") and "ESITO" not in upper:
            result.append(url)
    # I rapporti/chiusure CORRISP vengono prima degli XML accessori.
    return sorted(set(result), key=lambda u: ("CORRISP" not in u.upper(), u))


def _state_path() -> Path:
    configured = os.getenv("RT_SYNC_STATE_FILE")
    if configured:
        return Path(configured)
    base = Path(os.getenv("LOCALAPPDATA") or tempfile.gettempdir()) / "CeraldiERP"
    return base / "rt-sync-state.json"


def _load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"hashes": {}}


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _giorno(url: str) -> str:
    return unquote(urlparse(url).path.rstrip("/").split("/")[-1])


def giornate_da_leggere(days: list[str], ultimo: str | None, dal: str | None = None) -> list[str]:
    """Le cartelle giornaliere dal giorno dell'ultima copia (compreso) in poi."""
    soglia = max(filter(None, [ultimo, dal]), default="")
    return [d for d in days if _giorno(d) >= soglia]


def sync(base_url: str, inbox: Path, preview: bool = False, dal: str | None = None) -> dict:
    base_url = _private_base_url(base_url)
    state_path = _state_path()
    state = _load_state(state_path)
    known = state.setdefault("hashes", {})
    days = _daily_directories(base_url)
    sorgenti = giornate_da_leggere(days, state.get("ultimo_giorno"), dal) if days else [base_url]
    result = {"giornate": [_giorno(d) for d in sorgenti], "trovati": 0, "copiati": 0, "duplicati": 0}

    if not preview:
        inbox.mkdir(parents=True, exist_ok=True)
    for source in sorgenti:
        day = _giorno(source)
        urls = _rt_xmls(source)
        result["trovati"] += len(urls)
        for url in urls:
            content = _get(url)
            digest = hashlib.sha256(content).hexdigest()
            if digest in known:
                result["duplicati"] += 1
                continue
            original = unquote(urlparse(url).path.split("/")[-1])
            safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{day}_{original}")
            target = inbox / safe_name
            if not preview:
                with tempfile.NamedTemporaryFile(dir=inbox, delete=False) as handle:
                    handle.write(content)
                    temp_name = Path(handle.name)
                temp_name.replace(target)
                known[digest] = {"source": url, "file": safe_name}
            result["copiati"] += 1
        if not preview and re.fullmatch(r"20\d{6}", day):
            # Salvato a ogni giornata: un giro interrotto riparte da qui.
            state["ultimo_giorno"] = max(day, state.get("ultimo_giorno") or "")
            _save_state(state_path, state)

    if not preview:
        _save_state(state_path, state)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Copia in Drive le giornate RT non ancora copiate")
    parser.add_argument("--preview", action="store_true", help="Non scrive file o stato")
    parser.add_argument("--dal", help="Primo giorno da recuperare, AAAAMMGG")
    args = parser.parse_args()
    if args.dal and not re.fullmatch(r"20\d{6}", args.dal):
        raise SystemExit("--dal vuole una data AAAAMMGG")
    base_url = os.getenv("RT_LOCAL_BASE_URL", "http://192.168.1.19/www/dati-rt/")
    inbox_raw = os.getenv("RT_DRIVE_INBOX")
    if not inbox_raw:
        raise SystemExit("Impostare RT_DRIVE_INBOX sulla cartella DATI SOCIETA CERALDI\\DA ELABORARE")
    result = sync(base_url, Path(inbox_raw), preview=args.preview, dal=args.dal)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
