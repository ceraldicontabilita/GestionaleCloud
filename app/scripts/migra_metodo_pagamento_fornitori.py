"""
Migrazione metodo di pagamento fornitori -> {cassa, banca, misto}.

Contesto: prima del motore unico app.engines.prima_nota_engine i fornitori
potevano avere metodo_pagamento impostato a valori come "riba", "assegno",
"bonifico", "rid", "carta", "bancario", "sepa", ecc. Per decisione esplicita
(2026-07) queste sono tutte varianti di un unico concetto: "banca" (transita
dal conto corrente). Questo script NORMALIZZA il campo salvato senza
cancellare nulla: nessun fornitore viene eliminato, nessuna fattura viene
toccata, solo il valore testuale del metodo pagamento viene riscritto usando
la stessa regola del motore di instradamento.

Uso:
    python -m app.scripts.migra_metodo_pagamento_fornitori           # dry-run, stampa il report
    python -m app.scripts.migra_metodo_pagamento_fornitori --apply   # applica davvero le modifiche

Di default esegue un DRY RUN: mostra quanti fornitori verrebbero
modificati e con quale nuovo valore, senza scrivere nulla sul database.
Va eseguito con --apply solo dopo aver verificato il report.
"""
import argparse
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from app.database import Database, Collections
from app.engines.prima_nota_engine import normalizza_metodo_pagamento, CASSA, BANCA, MISTO

logger = logging.getLogger(__name__)

# Campi che nel tempo hanno ospitato il metodo di pagamento fornitore.
CAMPI_METODO = ("metodo_pagamento", "metodo_pagamento_predefinito")


async def migra_metodo_pagamento_fornitori(apply: bool = False) -> Dict[str, Any]:
    """Normalizza il metodo di pagamento di tutti i fornitori a {cassa, banca, misto}.

    Non tocca fornitori il cui metodo e' gia' uno dei tre valori canonici, o
    vuoto/non impostato (restano "non definito", segnalati altrove con alert,
    non e' compito di questa migrazione deciderne uno).
    """
    db = Database.get_db()
    coll = db[Collections.SUPPLIERS]

    report: Dict[str, Any] = {
        "dry_run": not apply,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "analizzati": 0,
        "gia_canonici": 0,
        "non_definiti_saltati": 0,
        "non_riconosciuti_saltati": 0,
        "da_modificare": 0,
        "modificati": 0,
        "dettaglio_modifiche": [],   # prime 200, per revisione
        "dettaglio_non_riconosciuti": [],  # prime 50, richiedono decisione manuale
    }

    canonici = {CASSA, BANCA, MISTO}

    async for fornitore in coll.find({}, {"_id": 0, "id": 1, "partita_iva": 1, "ragione_sociale": 1,
                                            "denominazione": 1, **{c: 1 for c in CAMPI_METODO}}):
        report["analizzati"] += 1
        nome = fornitore.get("ragione_sociale") or fornitore.get("denominazione") or fornitore.get("partita_iva") or fornitore.get("id")

        update: Dict[str, str] = {}
        for campo in CAMPI_METODO:
            valore_attuale = fornitore.get(campo)
            if not valore_attuale:
                continue
            if valore_attuale in canonici:
                continue
            canonico = normalizza_metodo_pagamento(valore_attuale)
            if canonico is None:
                if len(report["dettaglio_non_riconosciuti"]) < 50:
                    report["dettaglio_non_riconosciuti"].append({
                        "fornitore": nome, "campo": campo, "valore": valore_attuale,
                    })
                report["non_riconosciuti_saltati"] += 1
                continue
            update[campo] = canonico

        if not update:
            report["gia_canonici"] += 1
            continue

        report["da_modificare"] += 1
        if len(report["dettaglio_modifiche"]) < 200:
            report["dettaglio_modifiche"].append({
                "fornitore": nome,
                "id": fornitore.get("id"),
                "modifiche": update,
            })

        if apply:
            update["updated_at"] = datetime.now(timezone.utc).isoformat()
            update["metodo_pagamento_migrato_da"] = {
                campo: fornitore.get(campo) for campo in update if campo in CAMPI_METODO
            }
            await coll.update_one({"id": fornitore.get("id")}, {"$set": update})
            report["modificati"] += 1

    return report


def _print_report(report: Dict[str, Any]) -> None:
    modo = "APPLICATO" if not report["dry_run"] else "DRY RUN (nessuna modifica scritta)"
    print(f"\n=== Migrazione metodo pagamento fornitori — {modo} ===")
    print(f"Fornitori analizzati:        {report['analizzati']}")
    print(f"Gia' su valore canonico:     {report['gia_canonici']}")
    print(f"Da modificare:               {report['da_modificare']}")
    if not report["dry_run"]:
        print(f"Modificati:                  {report['modificati']}")
    print(f"Non riconosciuti (manuale):  {report['non_riconosciuti_saltati']}")
    if report["dettaglio_non_riconosciuti"]:
        print("\nValori non riconosciuti (richiedono decisione manuale):")
        for d in report["dettaglio_non_riconosciuti"]:
            print(f"  - {d['fornitore']}: {d['campo']}={d['valore']!r}")
    if report["dettaglio_modifiche"]:
        print(f"\nEsempio modifiche (prime {min(20, len(report['dettaglio_modifiche']))} di {report['da_modificare']}):")
        for d in report["dettaglio_modifiche"][:20]:
            print(f"  - {d['fornitore']}: {d['modifiche']}")
    if report["dry_run"] and report["da_modificare"] > 0:
        print("\nPer applicare davvero: python -m app.scripts.migra_metodo_pagamento_fornitori --apply")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Applica le modifiche (default: dry-run)")
    args = parser.parse_args()

    risultato = asyncio.run(migra_metodo_pagamento_fornitori(apply=args.apply))
    _print_report(risultato)
