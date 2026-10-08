#!/usr/bin/env python3
"""Ottimizza in-place le immagini del bucket Supabase usato da Menu e Lotti."""

from __future__ import annotations

import os
import sys
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.menu.image_optimizer import ottimizza_immagine_web


BUCKET = "menu-images"


def _request(url: str, *, headers: dict[str, str], data: bytes | None = None, timeout: int = 120) -> tuple[bytes, dict]:
    richiesta = Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    with urlopen(richiesta, timeout=timeout) as risposta:
        return risposta.read(), dict(risposta.headers.items())


def _config() -> tuple[str, dict[str, str]]:
    url = (os.environ.get("MENU_SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("MENU_SUPABASE_KEY") or ""
    if not url or not key:
        raise SystemExit("Servono MENU_SUPABASE_URL e MENU_SUPABASE_KEY")
    return url, {"apikey": key, "Authorization": f"Bearer {key}"}


def _lista(url: str, headers: dict[str, str], prefix: str = "") -> list[dict]:
    risultati = []
    offset = 0
    while True:
        corpo, _ = _request(
            f"{url}/storage/v1/object/list/{BUCKET}",
            headers={**headers, "Content-Type": "application/json"},
            data=json.dumps({"prefix": prefix, "limit": 100, "offset": offset, "sortBy": {"column": "name", "order": "asc"}}).encode(),
            timeout=60,
        )
        pagina = json.loads(corpo)
        risultati.extend(pagina)
        if len(pagina) < 100:
            return risultati
        offset += len(pagina)


def _file_ricorsivi(url: str, headers: dict[str, str], prefix: str = "") -> list[str]:
    file = []
    for voce in _lista(url, headers, prefix):
        nome = voce.get("name")
        if not nome:
            continue
        percorso = f"{prefix}/{nome}" if prefix else nome
        if voce.get("id") is None:
            file.extend(_file_ricorsivi(url, headers, percorso))
        elif (
            str((voce.get("metadata") or {}).get("mimetype", "")).startswith("image/")
            and (voce.get("metadata") or {}).get("mimetype") != "image/webp"
        ):
            file.append(percorso)
    return file


def _ottimizza(url: str, headers: dict[str, str], percorso: str) -> tuple[int, int]:
    encoded = quote(percorso, safe="/")
    prima, response_headers = _request(f"{url}/storage/v1/object/{BUCKET}/{encoded}", headers=headers)
    if response_headers.get("Content-Type", "").startswith("image/webp"):
        return len(prima), len(prima)
    dopo = ottimizza_immagine_web(prima)
    if len(dopo) >= len(prima) and response_headers.get("Content-Type", "").startswith("image/webp"):
        return len(prima), len(prima)
    _request(
        f"{url}/storage/v1/object/{BUCKET}/{encoded}",
        headers={
            **headers,
            "Content-Type": "image/webp",
            "Cache-Control": "max-age=31536000",
            "x-upsert": "true",
        },
        data=dopo,
        timeout=120,
    )
    return len(prima), len(dopo)


def main() -> None:
    url, headers = _config()
    percorsi = _file_ricorsivi(url, headers)
    if not percorsi:
        print("Tutte le immagini sono gia' WebP ottimizzati.")
        return
    prima = dopo = completati = 0
    errori = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        lavori = {pool.submit(_ottimizza, url, headers, p): p for p in percorsi}
        for lavoro in as_completed(lavori):
            try:
                a, b = lavoro.result()
            except Exception as exc:
                errori.append(f"{lavori[lavoro]}: {exc}")
                continue
            prima += a
            dopo += b
            completati += 1
            if completati % 25 == 0 or completati == len(percorsi):
                print(f"{completati}/{len(percorsi)}: {prima / 1024**2:.1f} -> {dopo / 1024**2:.1f} MiB", flush=True)
    if errori:
        print(f"NON OTTIMIZZATI: {len(errori)}", flush=True)
        for errore in errori:
            print(errore, flush=True)


if __name__ == "__main__":
    main()
