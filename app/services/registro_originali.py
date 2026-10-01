"""Dall'impronta SHA-256 di un file all'originale su Drive, col registro della cartella unica.

Il registro (``drive_cartella_unica``, scritto dallo smistatore) ha per ogni file
passato di li' ``sha256`` e ``drive_file_id``; l'originale e' la copia in
``ELABORATE`` (``drive_cartella_unica.originale``). Qui solo la lettura e la
scelta della copia, mai per nome:

* un solo file con quello SHA-256 in ``ELABORATE``: e' lui, certo;
* piu' file identici: l'originale e' quello che ha *creato* il documento, cioe'
  l'unico con ``gia_presente`` falso (le copie arrivate dopo sono ``gia_presente``);
  se non e' uno solo, **nessuna scelta** e si dichiarano tutti i candidati.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

REGISTRO = "drive_cartella_unica"
CARTELLA_ORIGINALI = "ELABORATE"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PROIEZIONE = {"_id": 0, "id": 1, "drive_file_id": 1, "cartella": 1, "sha256": 1, "md5": 1, "gia_presente": 1}


@dataclass(frozen=True)
class Originale:
    drive_id: Optional[str]          # None se non si puo' scegliere
    candidati: tuple = field(default_factory=tuple)
    certo: bool = False


def sha256_valido(valore: Any) -> Optional[str]:
    testo = str(valore or "").strip().lower()
    return testo if _SHA256_RE.match(testo) else None


class RegistroOriginali:
    """Indice sha256 -> file in ``ELABORATE``. Costruito una volta (un prefetch, regola 4)."""

    def __init__(self, righe: Iterable[Dict[str, Any]] = ()):
        self._per_sha: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.righe = 0
        for r in righe:
            if str(r.get("cartella") or "") != CARTELLA_ORIGINALI:
                continue
            sha = sha256_valido(r.get("sha256"))
            drive_id = str(r.get("drive_file_id") or r.get("id") or "").strip()
            if not (sha and drive_id):
                continue
            self.righe += 1
            self._per_sha[sha].append({"drive_id": drive_id, "gia_presente": r.get("gia_presente")})

    def __len__(self) -> int:
        return len(self._per_sha)

    def trova(self, sha: Any) -> Optional[Originale]:
        """``None`` se il file non e' nel registro; altrimenti l'originale (certo o no)."""
        chiave = sha256_valido(sha)
        copie = self._per_sha.get(chiave) if chiave else None
        if not copie:
            return None
        ids = tuple(sorted({c["drive_id"] for c in copie}))
        if len(ids) == 1:
            return Originale(ids[0], ids, True)
        creatori = sorted({c["drive_id"] for c in copie if c["gia_presente"] is not True})
        if len(creatori) == 1:
            return Originale(creatori[0], ids, True)
        return Originale(None, ids, False)


async def leggi_registro(db) -> RegistroOriginali:
    righe = await db[REGISTRO].find({"cartella": CARTELLA_ORIGINALI}, PROIEZIONE).to_list(length=None)
    return RegistroOriginali(righe)


__all__ = ["Originale", "RegistroOriginali", "leggi_registro", "sha256_valido"]
