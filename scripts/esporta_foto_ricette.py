"""Copia delle foto delle ricette Lotti nella cartella Drive Desktop del titolare.

Il gestionale su Render non puo' creare file nel «Il mio Drive» del titolare:
il suo account di servizio non ha spazio (``storageQuotaExceeded``). Questo
programma gira sul PC, legge le ricette dal Lotti di produzione e deposita le
foto nella cartella sincronizzata da Google Drive Desktop, che le carica con
l'account del titolare. L'archivio canonico resta Supabase Storage: questa e'
una copia di consultazione, non una seconda fonte da cui il gestionale legga.

Idempotente: un file gia' presente con lo stesso SHA-256 non si riscrive; una
foto cambiata sostituisce la copia con scrittura atomica. Una ricetta la cui
foto non e' piu' leggibile e' elencata nell'indice come ``mancante``, mai
riempita con un'immagine presa per nome.

Il PIN personale arriva da ``LOTTI_OPERATOR_PIN`` o si digita al prompt: non
si scrive su disco.
"""
from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Callable, Iterable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_URL = "https://gestionalecloud.onrender.com/lotti"
CARTELLA_PREDEFINITA = r"C:\Users\ceral\Il mio Drive\GESTIONALE\FOTO E IMMAGINI\RICETTE"
INDICE = "indice_foto_ricette.csv"
ESTENSIONI = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

Scarica = Callable[[str], tuple[bytes, str]]


def nome_file(ricetta: dict, mime: str) -> str:
    """Nome leggibile e stabile: il nome della ricetta piu' l'inizio del suo ID.

    L'ID distingue due ricette omonime e tiene fermo il file quando la foto
    cambia; i caratteri vietati da Windows diventano spazi.
    """
    nome = unicodedata.normalize("NFC", str(ricetta.get("nome") or "").strip())
    nome = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", nome)
    nome = re.sub(r"\s+", " ", nome).strip(" .") or "ricetta"
    ident = re.sub(r"[^A-Za-z0-9]+", "", str(ricetta.get("id") or ""))[:8] or "senzaid"
    estensione = ESTENSIONI.get(str(mime or "").split(";", 1)[0].strip().casefold(), ".img")
    return f"{nome[:120]} [{ident}]{estensione}"


def _sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def _scrivi_atomico(cartella: Path, target: Path, contenuto: bytes) -> None:
    with tempfile.NamedTemporaryFile(dir=cartella, delete=False, suffix=".tmp") as handle:
        handle.write(contenuto)
        temp = Path(handle.name)
    temp.replace(target)


def esporta(ricette: Iterable[dict], scarica: Scarica, cartella: Path, preview: bool = False) -> dict:
    esito = {"ricette": 0, "con_foto": 0, "nuove": 0, "aggiornate": 0,
             "invariate": 0, "mancanti": 0, "errori": 0, "senza_foto": 0}
    righe: list[dict] = []
    if not preview:
        cartella.mkdir(parents=True, exist_ok=True)
    for ricetta in ricette:
        esito["ricette"] += 1
        foto_url = str(ricetta.get("foto_url") or "").strip()
        riga = {"ricetta_id": ricetta.get("id"), "nome": ricetta.get("nome"),
                "file": "", "sha256": "", "esito": ""}
        if not foto_url:
            esito["senza_foto"] += 1
            riga["esito"] = "senza_foto"
            righe.append(riga)
            continue
        esito["con_foto"] += 1
        try:
            contenuto, mime = scarica(foto_url)
        except HTTPError as exc:
            # Una foto illeggibile non ferma le altre: resta scritta nell'indice.
            chiave = "mancanti" if exc.code == 404 else "errori"
            esito[chiave] += 1
            riga["esito"] = "mancante" if exc.code == 404 else f"errore_http_{exc.code}"
            righe.append(riga)
            continue
        digest = hashlib.sha256(contenuto).hexdigest()
        target = cartella / nome_file(ricetta, mime)
        precedente = _sha256_file(target)
        if precedente == digest:
            stato = "invariate"
        elif precedente is None:
            stato = "nuove"
        else:
            stato = "aggiornate"
        if stato != "invariate" and not preview:
            _scrivi_atomico(cartella, target, contenuto)
        esito[stato] += 1
        riga.update(file=target.name, sha256=digest, esito=stato)
        righe.append(riga)
    if not preview:
        with tempfile.NamedTemporaryFile("w", dir=cartella, delete=False, suffix=".tmp",
                                         newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(righe[0]) if righe else
                                    ["ricetta_id", "nome", "file", "sha256", "esito"], delimiter=";")
            writer.writeheader()
            writer.writerows(righe)
            temp = Path(handle.name)
        temp.replace(cartella / INDICE)
    return esito


class ClientLotti:
    def __init__(self, base_url: str, pin: str):
        self.base_url = base_url.rstrip("/")
        login = self._richiesta("POST", "/api/tablet-operatori/login", {"pin": pin})
        self.token = json.loads(login[0])["token"]

    def _richiesta(self, metodo: str, percorso: str, corpo: dict | None = None,
                   token: str | None = None) -> tuple[bytes, str]:
        headers = {"Accept": "*/*"}
        data = None
        if corpo is not None:
            data = json.dumps(corpo).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = Request(self.base_url + percorso, data=data, headers=headers, method=metodo)
        with urlopen(req, timeout=120) as response:
            return response.read(), response.headers.get("Content-Type", "")

    def ricette(self) -> list[dict]:
        return json.loads(self._richiesta("GET", "/api/ricette", token=self.token)[0])

    def foto(self, foto_url: str) -> tuple[bytes, str]:
        return self._richiesta("GET", foto_url, token=self.token)


def main() -> int:
    parser = argparse.ArgumentParser(description="Copia le foto delle ricette Lotti nella cartella Drive")
    parser.add_argument("--dest", default=os.getenv("FOTO_RICETTE_DIR", CARTELLA_PREDEFINITA))
    parser.add_argument("--preview", action="store_true", help="Non scrive file")
    args = parser.parse_args()
    pin = os.getenv("LOTTI_OPERATOR_PIN") or getpass.getpass("PIN personale Lotti: ")
    client = ClientLotti(os.getenv("LOTTI_BASE_URL", BASE_URL), pin)
    esito = esporta(client.ricette(), client.foto, Path(args.dest), preview=args.preview)
    print(json.dumps(esito, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
