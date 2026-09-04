"""Sincronizzazione ``prima_nota_salari`` <- archivio HR (PR 15).

Decisione del titolare 03/09/2026 (``CLAUDE.md`` "Cedolini: un solo sistema
(HR)"): l'archivio cedolini che gli utenti vedono e' SOLO l'app HR
(``public.app_cedolini`` del Postgres HR). Il deposito gestionale -> HR e'
gia' fatto (``services/hr_cedolini_deposito.py``); questo modulo e' il verso
opposto, HR -> ``prima_nota_salari``: legge i cedolini dall'archivio HR (in
sola lettura, non scrive mai in HR) e verifica/crea le righe di Prima Nota
corrispondenti, sulla stessa chiave logica ``(codice_fiscale, anno, mese,
tipo_cedolino)`` di ``services/prima_nota_salari_chiave.py`` — per non creare
un terzo sistema oltre a ``services/salari_sync.py`` (che sincronizza dal
registro interno ``cedolini``, non dall'HR) e all'import da Excel.

Regole (CLAUDE.md "Identita', duplicati e relazioni" — nessuna associazione
automatica ambigua):

- cedolino HR senza riga di prima nota corrispondente -> la riga viene
  CREATA (netto dal cedolino HR, dipendente risolto per CF sull'anagrafica
  del gestionale) SOLO se nessuna riga con quella chiave esiste gia' — se
  ne esiste una con un CF non risolvibile che potrebbe essere la stessa
  identita', non si indovina: resta segnalata a parte;
- riga di prima nota gia' presente per la stessa chiave ma con un netto
  diverso da quello del cedolino HR -> MAI sovrascritta automaticamente:
  entra nel report ``discrepanze`` (netto gestionale vs netto HR), da
  risolvere a mano;
- riga di prima nota senza alcun cedolino HR corrispondente -> report
  ``prima_nota_senza_cedolino_hr`` (non e' compito di questo modulo deciderne
  la sorte: puo' essere un'anomalia da bonificare con
  ``bonifica_prima_nota_salari_doppioni`` o un cedolino non ancora arrivato
  in HR);
- il periodo ammesso e' lo stesso di tutta la Prima Nota salari
  (``salari_periodo.periodo_ammesso_in_prima_nota``, da dicembre 2025): i
  cedolini HR precedenti restano fuori, come per gli altri canali.

Dopo aver creato righe mancanti, i bonifici lasciati "senza destinazione" da
``stipendi_bonifici.riallinea_competenza_bonifici_stipendi`` (PR 13) possono
ora trovare una riga su cui posarsi: questo modulo puo' richiamare quella
funzione (mai duplicarne la logica) quando ha effettivamente creato righe.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.hr_cedolini_deposito import connetti_hr, dsn_hr
from app.services.prima_nota_salari_chiave import (
    IndiceDipendenti,
    carica_indice_dipendenti,
    chiave_logica_riga,
    importo_atteso_riga,
    tipo_cedolino_canonico,
)
from app.services.salari_periodo import periodo_ammesso_in_prima_nota
from app.services.scritture_contabili import FILTRO_MOVIMENTO_ATTIVO

logger = logging.getLogger(__name__)

MOTIVO_SYNC = "sync_prima_nota_salari_da_hr_2026-09-04"
COLLECTION = "prima_nota_salari"
TOLLERANZA_NETTO = 0.01

_SQL_CEDOLINI_ANNO = (
    "SELECT id, doc FROM public.app_cedolini"
    " WHERE (doc->>'anno') ~ '^[0-9]+$' AND (doc->>'anno')::int = $1"
)
_SQL_CEDOLINI_TUTTI = "SELECT id, doc FROM public.app_cedolini"


def _json(valore: Any) -> Dict[str, Any]:
    return json.loads(valore) if isinstance(valore, str) else dict(valore or {})


async def _leggi_cedolini_hr(dsn: str, anno: Optional[int]) -> List[Dict[str, Any]]:
    con = await connetti_hr(dsn)
    try:
        if anno:
            righe = await con.fetch(_SQL_CEDOLINI_ANNO, int(anno))
        else:
            righe = await con.fetch(_SQL_CEDOLINI_TUTTI)
    finally:
        await con.close()
    cedolini = []
    for riga in righe:
        doc = _json(riga["doc"])
        doc.setdefault("id", riga["id"])
        cedolini.append(doc)
    return cedolini


def _numero(valore: Any) -> Optional[float]:
    if valore is None or valore == "":
        return None
    try:
        return round(float(valore), 2)
    except (TypeError, ValueError):
        return None


def _sintesi_cedolino(cedolino: Dict[str, Any], cf: str, anno: int, mese: int, tipo: str) -> Dict[str, Any]:
    return {
        "hr_cedolino_id": cedolino.get("id"),
        "codice_fiscale": cf,
        "anno": anno,
        "mese": mese,
        "tipo_cedolino": tipo,
        "dipendente": str(cedolino.get("nome_dipendente") or cedolino.get("dipendente_nome") or "").strip(),
        "netto_hr": _numero(cedolino.get("netto")),
    }


async def sincronizza_da_hr(
    db,
    *,
    dry_run: bool = True,
    anno: Optional[int] = None,
    actor: Optional[str] = None,
    riallinea_bonifici: bool = True,
) -> Dict[str, Any]:
    """Confronta ``prima_nota_salari`` con l'archivio HR e crea le righe
    mancanti. Non scrive mai in HR (sola lettura). ``dry_run=True`` (default)
    non scrive nulla nel gestionale: ritorna solo i due elenchi di verifica.
    """
    dsn = dsn_hr()
    if not dsn:
        return {
            "hr_configurato": False,
            "errore": "Nessuna DSN HR configurata (HR_SUPABASE_DB_URL / "
                      "APPDIPENDENTI_DB_URL / SUPABASE_DB_URL)",
        }

    try:
        cedolini_hr = await _leggi_cedolini_hr(dsn, anno)
    except Exception as exc:
        logger.exception("[sync HR salari] lettura archivio HR fallita")
        return {"hr_configurato": True, "errore": f"lettura HR fallita: {exc}"}

    indice = await carica_indice_dipendenti(db)

    filtro_pn: Dict[str, Any] = dict(FILTRO_MOVIMENTO_ATTIVO)
    if anno:
        filtro_pn["anno"] = int(anno)
    righe_pn = await db[COLLECTION].find(filtro_pn, {"_id": 0}).to_list(20000)

    per_chiave_pn: Dict[Any, List[Dict[str, Any]]] = {}
    for riga in righe_pn:
        chiave = chiave_logica_riga(riga, indice)
        if chiave:
            per_chiave_pn.setdefault(chiave, []).append(riga)

    chiavi_hr_viste: set = set()
    cedolini_senza_prima_nota: List[Dict[str, Any]] = []
    discrepanze: List[Dict[str, Any]] = []
    coerenti = 0
    fuori_periodo = 0
    senza_identita_hr = 0
    nuove_righe: List[Dict[str, Any]] = []

    now = datetime.now(timezone.utc).isoformat()
    for cedolino in cedolini_hr:
        cf = str(cedolino.get("codice_fiscale") or "").strip().upper()
        try:
            anno_c = int(cedolino.get("anno"))
            mese_c = int(cedolino.get("mese"))
        except (TypeError, ValueError):
            senza_identita_hr += 1
            continue
        if not cf or not 1 <= mese_c <= 12:
            senza_identita_hr += 1
            continue
        if not periodo_ammesso_in_prima_nota(anno_c, mese_c):
            fuori_periodo += 1
            continue
        tipo_c = tipo_cedolino_canonico(cedolino.get("tipo_cedolino"))
        chiave = (cf, anno_c, mese_c, tipo_c)
        chiavi_hr_viste.add(chiave)
        netto_hr = _numero(cedolino.get("netto"))
        if netto_hr is None or netto_hr <= 0:
            senza_identita_hr += 1
            continue

        righe_corrispondenti = per_chiave_pn.get(chiave) or []
        if not righe_corrispondenti:
            sintesi = _sintesi_cedolino(cedolino, cf, anno_c, mese_c, tipo_c)
            cedolini_senza_prima_nota.append(sintesi)
            dip = indice.dipendente_per_cf(cf)
            nuove_righe.append({
                "id": str(uuid.uuid4()),
                "dipendente": sintesi["dipendente"].upper(),
                "dipendente_nome": sintesi["dipendente"],
                "dipendente_id": (dip or {}).get("id"),
                "codice_fiscale": cf,
                "anno": anno_c,
                "mese": mese_c,
                "tipo_cedolino": tipo_c,
                "tipo": "stipendio",
                "importo_busta": netto_hr,
                "importo_bonifico": 0,
                "saldo": round(-netto_hr, 2),
                "progressivo": 0,
                "riconciliato": False,
                "source": "hr_cedolini_sync",
                "hr_cedolino_id": cedolino.get("id"),
                "descrizione": f"Stipendio {sintesi['dipendente']} - {mese_c:02d}/{anno_c} (da archivio HR)",
                "created_at": now,
                "updated_at": now,
            })
            continue

        # Puo' esserci piu' di una riga viva con la stessa chiave se la
        # bonifica dei doppioni (PR 14) non e' ancora stata applicata: il
        # confronto usa quella con l'importo piu' vicino al netto HR, cosi'
        # da non segnalare una falsa discrepanza sulla riga sbagliata.
        riga_confronto = min(
            righe_corrispondenti,
            key=lambda r: abs(importo_atteso_riga(r) - netto_hr),
        )
        importo_pn = importo_atteso_riga(riga_confronto)
        if abs(importo_pn - netto_hr) <= TOLLERANZA_NETTO:
            coerenti += 1
        else:
            discrepanze.append({
                **_sintesi_cedolino(cedolino, cf, anno_c, mese_c, tipo_c),
                "prima_nota_id": riga_confronto.get("id"),
                "importo_busta_gestionale": importo_pn,
            })

    prima_nota_senza_cedolino_hr = [
        {
            "id": riga.get("id"),
            "dipendente": (
                riga.get("dipendente_nome") or riga.get("dipendente")
                or riga.get("nome_dipendente")
            ),
            "codice_fiscale": chiave[0], "anno": chiave[1], "mese": chiave[2],
            "tipo_cedolino": chiave[3], "importo_busta": importo_atteso_riga(riga),
        }
        for chiave, righe_chiave in per_chiave_pn.items()
        if chiave not in chiavi_hr_viste
        for riga in righe_chiave
    ]
    prima_nota_senza_cedolino_hr.sort(key=lambda r: (r["anno"], r["mese"], r["codice_fiscale"]))
    cedolini_senza_prima_nota.sort(key=lambda r: (r["anno"], r["mese"], r["codice_fiscale"]))
    discrepanze.sort(key=lambda r: (r["anno"], r["mese"], r["codice_fiscale"]))

    esito: Dict[str, Any] = {
        "hr_configurato": True,
        "dry_run": dry_run,
        "motivo": MOTIVO_SYNC,
        "anno_filtro": anno,
        "cedolini_hr_esaminati": len(cedolini_hr),
        "cedolini_fuori_periodo_ammesso": fuori_periodo,
        "cedolini_senza_identita": senza_identita_hr,
        "righe_prima_nota_esaminate": len(righe_pn),
        "coerenti": coerenti,
        "totale_cedolini_senza_prima_nota": len(cedolini_senza_prima_nota),
        "totale_prima_nota_senza_cedolino_hr": len(prima_nota_senza_cedolino_hr),
        "totale_discrepanze_netto": len(discrepanze),
        "cedolini_senza_prima_nota": cedolini_senza_prima_nota,
        "prima_nota_senza_cedolino_hr": prima_nota_senza_cedolino_hr,
        "discrepanze": discrepanze,
    }

    if dry_run:
        return esito

    if nuove_righe:
        await db[COLLECTION].insert_many([r.copy() for r in nuove_righe])
    esito["righe_create"] = len(nuove_righe)
    esito["eseguita_at"] = now

    if nuove_righe:
        try:
            await db["prima_nota_migrazioni_audit"].insert_one({
                "id": str(uuid.uuid4()),
                "migrazione": MOTIVO_SYNC,
                "actor": actor or "sistema",
                "created_at": now,
                "righe_create": [
                    {"id": r["id"], "codice_fiscale": r["codice_fiscale"],
                     "anno": r["anno"], "mese": r["mese"], "tipo_cedolino": r["tipo_cedolino"],
                     "importo_busta": r["importo_busta"]}
                    for r in nuove_righe
                ],
            })
        except Exception:  # pragma: no cover - l'audit non deve bloccare il sync
            logger.exception("Audit del sync HR salari non scritto")

        if riallinea_bonifici:
            try:
                from app.services.stipendi_bonifici import (
                    riallinea_competenza_bonifici_stipendi,
                )

                anni_toccati = {int(r["anno"]) for r in nuove_righe}
                riallinei = []
                for anno_toccato in sorted(anni_toccati):
                    riallinei.append(await riallinea_competenza_bonifici_stipendi(
                        db, dry_run=False, anno=anno_toccato,
                        actor=actor or "sync_prima_nota_salari_da_hr",
                    ))
                esito["riallineo_bonifici"] = riallinei
            except Exception:
                logger.exception(
                    "[sync HR salari] riallineo bonifici dopo la creazione delle righe non completato"
                )
                esito["riallineo_bonifici"] = {"errore": True}

    logger.warning(
        "[sync HR salari] cedolini esaminati %s, righe create %s, discrepanze %s, "
        "prima nota senza cedolino HR %s",
        len(cedolini_hr), esito.get("righe_create", 0), len(discrepanze),
        len(prima_nota_senza_cedolino_hr),
    )
    return esito


# ── CLI ──────────────────────────────────────────────────────────────────────

async def _main_async(dry_run: bool, anno: Optional[int]) -> Dict[str, Any]:
    from app.database import Database

    await Database.connect_db()
    try:
        return await sincronizza_da_hr(
            Database.get_db(), dry_run=dry_run, anno=anno, actor="cli",
        )
    finally:
        await Database.close_db()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Confronta prima_nota_salari con l'archivio cedolini HR e crea le "
            "righe mancanti (PR 15). Default: solo analisi."
        ),
    )
    parser.add_argument("--applica", action="store_true", help="scrive davvero le righe mancanti")
    parser.add_argument("--anno", type=int, default=None, help="limita a un anno contabile")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    risultato = asyncio.run(_main_async(dry_run=not args.applica, anno=args.anno))
    print(json.dumps(risultato, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
