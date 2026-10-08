"""Stampe di controllo delle buste paga: la bozza non resta accanto alla busta.

Il consulente produce prima una «STAMPA DI CONTROLLO» (Zucchetti:
«Elaborazione Versione … di controllo»), poi la busta definitiva: stesso
dipendente, stesso periodo, stesso netto. Su Drive finivano tutte e due e il
gestionale le leggeva come due buste. Regola del titolare (27/09/2026): se
esiste la busta definitiva identica (codice fiscale, periodo, netto), la
stampa di controllo si toglie da Drive — nel Cestino, o in ``DOPPIONI`` quando
il file e' del titolare e Drive nega il Cestino al service account.

La applica ``pulisci_archivio`` sulle buste in ``ELABORATE``, a gruppi di
file con lo stesso nome (``… - 2025-12`` e ``… - 2025-12 (dup2)``), dopo ogni
giro dello smistatore: una bozza sparisce solo se nel gruppo c'e' la
definitiva identica. Senza la definitiva la bozza resta. All'arrivo non si
decide: il registro ``cedolini`` non dice da quale file e' nata una busta, e
un doppione di dati non prova che la definitiva sia su Drive.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

REGISTRO = "cedolini_stampe_controllo"
MOTIVO = "stampa di controllo: c'e' la busta definitiva identica"
GRUPPI_PER_GIRO = 25

_CONTROLLO = re.compile(
    r"ELABORAZIONE\s+VERSIONE[\s\d.]*DI\s+CONTROLLO|STAMPA\s+(?:\S+\s+){0,3}DI\s+CONTROLLO"
)
_DUP = re.compile(r"\s*\(dup\d+\)|\s*\(\d+\)", re.IGNORECASE)
_BUSTA = re.compile(r"LUL|CEDOLIN", re.IGNORECASE)

Identita = Tuple[str, int, int, str]


def _testo(contenuto: bytes) -> str:
    import fitz

    documento = fitz.open(stream=contenuto, filetype="pdf")
    try:
        testo = "\n".join(pagina.get_text() for pagina in documento)
    finally:
        documento.close()
    return re.sub(r"\s+", " ", testo.upper())


def e_stampa_di_controllo(testo_alto: str) -> bool:
    return bool(_CONTROLLO.search(testo_alto or ""))


def _netto(valore: Any) -> str:
    try:
        return f"{float(valore):.2f}"
    except (TypeError, ValueError):
        return ""


def leggi(contenuto: bytes) -> Tuple[bool, Set[Identita]]:
    """(e' una stampa di controllo, identita' delle buste: CF, anno, mese, netto)."""
    from app.services.cedolini_motore import leggi_pdf

    controllo = e_stampa_di_controllo(_testo(contenuto))
    identita: Set[Identita] = set()
    for busta in leggi_pdf(contenuto).get("buste") or []:
        cf = str(busta.get("codice_fiscale") or "").upper()
        netto = _netto(busta.get("netto"))
        try:
            anno, mese = int(busta.get("anno") or 0), int(busta.get("mese") or 0)
        except (TypeError, ValueError):
            continue
        if cf and anno and mese and netto:
            identita.add((cf, anno, mese, netto))
    return controllo, identita


def raggruppa(files: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Buste con lo stesso nome a meno di «(dupN)»: le sole che possono essere copie."""
    gruppi: Dict[str, List[Dict[str, Any]]] = {}
    for f in files:
        nome = str(f.get("name") or "")
        if not nome.lower().endswith(".pdf") or not _BUSTA.search(nome):
            continue
        chiave = _DUP.sub("", nome[:-4]).strip().lower()
        gruppi.setdefault(chiave, []).append(f)
    return {k: v for k, v in gruppi.items() if len(v) > 1}


def bozze_superate(letti: List[Tuple[Dict[str, Any], bool, Set[Identita]]]
                   ) -> List[Tuple[Dict[str, Any], Dict[Identita, str]]]:
    """Le stampe di controllo del gruppo con una definitiva identica.

    Per ogni bozza anche, busta per busta, l'id del file definitivo che la
    contiene: le buste registrate dalla bozza vi si riagganciano.
    """
    definitive: Dict[Identita, str] = {}
    for f, controllo, identita in letti:
        if not controllo:
            for chiave in identita:
                definitive.setdefault(chiave, f["id"])
    return [(f, {chiave: definitive[chiave] for chiave in identita}) for f, controllo, identita in letti
            if controllo and identita and identita <= definitive.keys()]


async def pulisci_archivio(db, *, gruppi_per_giro: Optional[int] = GRUPPI_PER_GIRO) -> Dict[str, Any]:
    """Toglie da ELABORATE le stampe di controllo superate, qualche gruppo per giro."""
    from app.services import drive_cartella_unica as cu
    from app.services.drive_download import scarica_bytes

    esito: Dict[str, Any] = {"gruppi": 0, "controllati": 0, "tolte": 0, "errori": 0}
    if not cu.radice():
        return esito
    service = await asyncio.to_thread(cu._service)
    cartelle = await asyncio.to_thread(cu._cartelle, service, cu.radice())
    archivio = cartelle[cu.ARCHIVIO]
    files = await asyncio.to_thread(cu._elenca, service, archivio, "id, name, md5Checksum")
    gruppi = raggruppa(files)
    esito["gruppi"] = len(gruppi)
    fatti = {
        g["id"]: g.get("firma") for g in await db[REGISTRO].find(
            {}, {"_id": 0, "id": 1, "firma": 1}).to_list(None)
    }
    adesso = datetime.now(timezone.utc).isoformat()
    for chiave, membri in sorted(gruppi.items()):
        if gruppi_per_giro is not None and esito["controllati"] >= gruppi_per_giro:
            break
        firma = ",".join(sorted(m["id"] for m in membri))
        if fatti.get(chiave) == firma:
            continue
        esito["controllati"] += 1
        try:
            letti = []
            for membro in membri:
                contenuto = await asyncio.to_thread(scarica_bytes, service, membro["id"])
                controllo, identita = await asyncio.to_thread(leggi, contenuto)
                letti.append((membro, controllo, identita))
            tolte = []
            for bozza, definitive in bozze_superate(letti):
                # Prima si riaggancia, poi si toglie: «vedi documento» di una
                # busta nata dalla bozza deve aprire la definitiva.
                for (cf, anno, mese, _netto_busta), definitiva in definitive.items():
                    await db["cedolini"].update_many(
                        {"drive_file_id": bozza["id"], "codice_fiscale": cf,
                         "anno": anno, "mese": mese},
                        {"$set": {"drive_file_id": definitiva}},
                    )
                copia_di = sorted(set(definitive.values()))[0]
                cartella = "CESTINO"
                if not await asyncio.to_thread(cu._cestina, service, bozza["id"],
                                              f"{copia_di} (stampa di controllo superata)"):
                    cartella = cu.DOPPIONI
                    await asyncio.to_thread(cu._sposta, service, bozza["id"], archivio,
                                            cartelle[cu.DOPPIONI], MOTIVO)
                await cu._registra(db, bozza["id"], nome=bozza.get("name"), cartella=cartella,
                                   esito="stampa_controllo_tolta", duplicato_di=copia_di,
                                   motivo=MOTIVO)
                tolte.append({"id": bozza["id"], "nome": bozza.get("name"), "definitiva": copia_di,
                              "cartella": cartella})
            esito["tolte"] += len(tolte)
            restanti = ",".join(sorted(m["id"] for m in membri if m["id"] not in {t["id"] for t in tolte}))
            await db[REGISTRO].update_one(
                {"id": chiave},
                {"$set": {"id": chiave, "firma": restanti, "tolte": tolte, "controllato_at": adesso}},
                upsert=True,
            )
        except Exception as exc:  # noqa: BLE001 - un gruppo non ferma gli altri
            esito["errori"] += 1
            logger.warning("Stampe di controllo di %s non controllate: %s: %s",
                           chiave, type(exc).__name__, exc)
    return esito


__all__ = ["e_stampa_di_controllo", "raggruppa", "bozze_superate", "pulisci_archivio", "leggi"]

