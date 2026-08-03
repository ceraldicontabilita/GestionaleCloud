"""Raccoglitore locale RT -> Google Drive Desktop.

Questo programma gira sul PC collegato alla LAN del registratore. Render non
puo' raggiungere 192.168.x.x: il collector conserva i byte originali e li
deposita in ``Corrispettivi/Da elaborare``; il gestionale su Render esegue poi
parsing, deduplica e registrazione con la pipeline Drive canonica.
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


def sync(base_url: str, inbox: Path, preview: bool = False) -> dict:
    base_url = _private_base_url(base_url)
    days = _daily_directories(base_url)
    source = days[-1] if days else base_url
    urls = _rt_xmls(source)
    state_path = _state_path()
    state = _load_state(state_path)
    known = state.setdefault("hashes", {})
    result = {"cartella": source, "trovati": len(urls), "copiati": 0, "duplicati": 0}

    if not preview:
        inbox.mkdir(parents=True, exist_ok=True)
    day = unquote(urlparse(source).path.rstrip("/").split("/")[-1])
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

    if not preview:
        _save_state(state_path, state)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Importa l'ultima giornata RT in Drive")
    parser.add_argument("--preview", action="store_true", help="Non scrive file o stato")
    args = parser.parse_args()
    base_url = os.getenv("RT_LOCAL_BASE_URL", "http://192.168.1.19/www/dati-rt/")
    inbox_raw = os.getenv("RT_DRIVE_INBOX")
    if not inbox_raw:
        raise SystemExit("Impostare RT_DRIVE_INBOX sulla cartella Corrispettivi\\Da elaborare")
    result = sync(base_url, Path(inbox_raw), preview=args.preview)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
