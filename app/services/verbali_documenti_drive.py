"""Documenti Drive collegati a un verbale, letti dal foglio dei collegamenti.

Il foglio (foglio «Collegamenti» di un xlsx, letto **per intestazione**) dice, per ogni
riga, quale file Drive appartiene a quale verbale: ``numero_verbale``, ``drive_id``,
``tipo``, ``nome_file`` e, se noto, ``sha256``. Il servizio non scarica e non sposta
niente: scrive sul verbale l'elenco ``documenti_drive`` e il dettaglio lo apre con
l'endpoint unico degli originali (``/api/originale?drive_id=``), che accetta solo i file
della cartella unica o dell'inventario Drive.

Una riga con ``azione`` = «rimuovi» scollega il file dal verbale (il file su Drive non si tocca; il collegamento
togliere resta in ``documenti_drive_rimossi`` con data e motivo).

Regole: ``dry_run`` per difetto; un verbale si trova solo per numero (mai per targa o
importo); lo stesso ``drive_id`` non si aggiunge due volte; se il foglio dice un altro tipo o nome per un file
gia' collegato, li corregge (il tipo si legge dal contenuto, il tipo precedente resta in ``tipo_precedente``); un verbale senza riga nel gestionale resta nell'elenco «non trovati».
"""
from __future__ import annotations

import io
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

COLLEZIONI_VERBALI = ("verbali_noleggio", "verbali_noleggio_completi")
FOGLIO = "Collegamenti"
TIPI = ("verbale", "notifica", "quietanza", "bonifico", "avviso_pagopa", "ricevuta", "presa_in_carico", "altro")
_COLONNE = {"numero_verbale": ("numero_verbale", "verbale", "numero"),
            "drive_id": ("drive_id", "id_drive"),
            "tipo": ("tipo", "tipo_documento"),
            "nome_file": ("nome_file", "nome", "file"),
            "sha256": ("sha256", "impronta"),
            "azione": ("azione",)}
_DRIVE_ID = re.compile(r"^[A-Za-z0-9_-]{15,80}$")


def _chiave(testo: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(testo or "").strip().lower()).strip("_")


def _numero(valore: Any) -> str:
    return re.sub(r"\s+", "", str(valore or "")).upper()


def righe_da_xlsx(contenuto: bytes) -> List[Dict[str, Any]]:
    """Le righe del foglio «Collegamenti», lette per intestazione (mai per posizione)."""
    from openpyxl import load_workbook

    cartella = load_workbook(io.BytesIO(contenuto), read_only=True, data_only=True)
    if FOGLIO not in cartella.sheetnames:
        raise ValueError(f"Manca il foglio «{FOGLIO}»")
    righe = cartella[FOGLIO].iter_rows(values_only=True)
    intestazione = next(righe, None)
    if not intestazione:
        return []
    posizione: Dict[str, int] = {}
    for indice, nome in enumerate(intestazione):
        for campo, alias in _COLONNE.items():
            if _chiave(nome) in alias and campo not in posizione:
                posizione[campo] = indice
    if "numero_verbale" not in posizione or "drive_id" not in posizione:
        raise ValueError("Il foglio deve avere le colonne numero_verbale e drive_id")
    risultato = []
    for riga in righe:
        if not riga or all(c in (None, "") for c in riga):
            continue
        risultato.append({campo: (riga[i] if i < len(riga) else None) for campo, i in posizione.items()})
    return risultato


async def _verbali_per_numero(db, numero: str) -> List[tuple]:
    trovati = []
    for collezione in COLLEZIONI_VERBALI:
        try:
            doc = await db[collezione].find_one(
                {"$or": [{"numero_verbale": numero}, {"numero_verbale_old": numero}]}, {"_id": 0})
        except Exception as exc:
            logger.warning("Collegamenti Drive: lettura %s non riuscita (%s)", collezione, type(exc).__name__)
            continue
        if doc:
            trovati.append((collezione, doc))
    return trovati


async def collega_documenti_drive(db, righe: Iterable[Dict[str, Any]], *, dry_run: bool = True,
                                  autore: Optional[str] = None) -> Dict[str, Any]:
    """Aggiunge ``documenti_drive`` ai verbali nominati dalle righe; idempotente."""
    adesso = datetime.now(timezone.utc).isoformat()
    esito: Dict[str, Any] = {"dry_run": dry_run, "righe": 0, "collegati": 0, "corretti": 0, "rimossi": 0, "gia_collegati": 0,
                             "non_trovati": [], "non_validi": [], "verbali_toccati": 0}
    per_verbale: Dict[str, List[Dict[str, Any]]] = {}
    for riga in righe:
        esito["righe"] += 1
        numero = _numero(riga.get("numero_verbale"))
        drive_id = str(riga.get("drive_id") or "").strip()
        tipo = _chiave(riga.get("tipo")) or "altro"
        if not numero or not _DRIVE_ID.match(drive_id):
            esito["non_validi"].append({"numero_verbale": numero or None, "drive_id": drive_id or None,
                                        "motivo": "numero_o_drive_id_mancante"})
            continue
        if tipo not in TIPI:
            tipo = "altro"
        azione = _chiave(riga.get("azione"))
        voce = {"azione": "rimuovi" if azione == "rimuovi" else "collega", "drive_id": drive_id, "tipo": tipo, "nome": str(riga.get("nome_file") or "").strip() or None,
                "sha256": (str(riga.get("sha256") or "").strip().lower() or None),
                "fonte": "foglio_collegamenti"}
        per_verbale.setdefault(numero, []).append(voce)

    for numero, voci in sorted(per_verbale.items()):
        trovati = await _verbali_per_numero(db, numero)
        if not trovati:
            esito["non_trovati"].append({"numero_verbale": numero, "documenti": len(voci)})
            continue
        toccato = False
        for collezione, doc in trovati:
            attuali = [dict(d) for d in (doc.get("documenti_drive") or []) if isinstance(d, dict)]
            per_id = {str(d.get("drive_id")): d for d in attuali}
            nuovi, corretti, rimossi_ora = [], 0, []
            for voce in voci:
                esistente = per_id.get(voce["drive_id"])
                if voce["azione"] == "rimuovi":
                    # Si scollega il collegamento (il file su Drive non si tocca); resta traccia in documenti_drive_rimossi.
                    if esistente is not None:
                        per_id.pop(voce["drive_id"])
                        rimossi_ora.append({**esistente, "rimosso_il": adesso, "rimosso_da": autore,
                                            "motivo_rimozione": "duplicato (scelta del titolare)"})
                    continue
                if esistente is None:
                    nuovo = {**voce, "collegato_il": adesso, "collegato_da": autore}
                    per_id[voce["drive_id"]] = nuovo
                    nuovi.append(nuovo)
                elif (esistente.get("tipo"), esistente.get("nome")) != (voce["tipo"], voce["nome"]):
                    # Il foglio e' la fonte: una riga con lo stesso file corregge tipo e nome (il tipo si legge dal contenuto).
                    esistente["tipo_precedente"] = esistente.get("tipo")
                    esistente.update(tipo=voce["tipo"], nome=voce["nome"], corretto_il=adesso)
                    corretti += 1
            da_collegare = [v for v in voci if v["azione"] != "rimuovi"]
            if collezione == trovati[0][0]:
                esito["gia_collegati"] += len(da_collegare) - len(nuovi) - corretti
                esito["collegati"] += len(nuovi)
                esito["corretti"] += corretti
                esito["rimossi"] += len(rimossi_ora)
            if not nuovi and not corretti and not rimossi_ora:
                continue
            toccato = True
            if dry_run:
                continue
            filtro = {"id": doc["id"]} if doc.get("id") else {"numero_verbale": doc.get("numero_verbale")}
            aggiorna = {"documenti_drive": [per_id[k] for k in per_id], "updated_at": adesso}
            if rimossi_ora:
                aggiorna["documenti_drive_rimossi"] = (doc.get("documenti_drive_rimossi") or []) + rimossi_ora
            await db[collezione].update_one(filtro, {"$set": aggiorna})
        if toccato:
            esito["verbali_toccati"] += 1
    if not dry_run and (esito["collegati"] or esito["corretti"] or esito["rimossi"]):
        try:
            await db["audit_log"].insert_one({
                "id": f"verbali_documenti_drive_{adesso}", "modulo": "verbali_noleggio",
                "azione": "collega_documenti_drive", "utente": autore, "created_at": adesso,
                "collegati": esito["collegati"], "corretti": esito["corretti"], "rimossi": esito["rimossi"], "verbali_toccati": esito["verbali_toccati"]})
        except Exception as exc:
            logger.warning("Collegamenti Drive: audit non scritto (%s)", type(exc).__name__)
    return esito
