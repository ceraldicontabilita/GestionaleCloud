"""Verifica lo stato reale delle migrazioni nei registri Sheets configurati.

Sola lettura: chiama ogni script di migrazione nella sua modalità dry-run
(`migra(esegui=False)`), che conta soltanto — non scrive nulla. Aggrega i
risultati in memoria/VERIFICA_MIGRAZIONI_PRODUZIONE.md.

NON esegue nessuna migrazione. Per eseguirle, lanciare singolarmente ogni
script con --esegui dopo aver rivisto questo report (uno alla volta, non a
blocco — note di migrazione nella cronologia git (PIANO_MIGRAZIONE_COLLECTION.md) di
attenzione specifiche di ciascuna).

Uso: python scripts/verifica_migrazioni_produzione.py
Richiede le credenziali Google Drive/Sheets previste da ``app/config.py``.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.getcwd())

from app.database import Database  # noqa: E402

# (nome_modulo, etichetta, collection_canonica)
MIGRAZIONI = [
    ("app.scripts.migra_fatture_passive_a_invoices", "fatture_passive -> invoices", "invoices"),
    ("app.scripts.migra_staff_a_dipendenti", "staff -> dipendenti", "dipendenti"),
    ("app.scripts.migra_employees_a_dipendenti", "employees -> dipendenti", "dipendenti"),
    ("app.scripts.migra_payslips_a_cedolini", "payslips -> cedolini", "cedolini"),
    ("app.scripts.migra_f24_unificato", "f24_models/f24_commercialista/f24_uploaded/f24 -> f24_unificato", "f24_unificato"),
    ("app.scripts.migra_documents_classified", "documents_classified -> documenti_classificati", "documenti_classificati"),
    ("app.scripts.migra_invoices_emesse_a_fatture", "invoices_emesse -> fatture_emesse", "fatture_emesse"),
]

OUT = "memoria/VERIFICA_MIGRAZIONI_PRODUZIONE.md"


async def main():
    await Database.connect_db()
    db = Database.get_db()

    righe = ["# VERIFICA MIGRAZIONI PRODUZIONE — piano residuo op.13", ""]
    righe.append("> Generato da `scripts/verifica_migrazioni_produzione.py` (sola lettura, "
                  "dry-run di ogni script di migrazione). NON modifica dati.")
    righe.append("")

    for modulo, etichetta, coll_canonica in MIGRAZIONI:
        mod = __import__(modulo, fromlist=["migra"])
        report = await mod.migra(esegui=False)
        conteggio_canonica = await db[coll_canonica].count_documents({})
        righe.append(f"## {etichetta}")
        righe.append(f"- Documenti oggi in `{coll_canonica}`: **{conteggio_canonica}**")
        righe.append(f"- Da migrare secondo il dry-run: **{report.get('migrati', '?')}** "
                      f"(già presenti: {report.get('gia_presenti', '?')})")
        if report.get("per_sorgente"):
            for sorgente, dettaglio in report["per_sorgente"].items():
                righe.append(f"  - `{sorgente}`: trovati={dettaglio.get('trovati')} "
                              f"da_migrare={dettaglio.get('da_migrare')}")
        stato = "✅ ALLINEATA (nulla da migrare)" if report.get("migrati", 1) == 0 else "⚠️ RESIDUO DA MIGRARE"
        righe.append(f"- **Stato: {stato}**")
        righe.append("")
        print(f"{etichetta}: migrati_da_fare={report.get('migrati')} "
              f"gia_presenti={report.get('gia_presenti')}")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(righe) + "\n")
    print(f"\nScritto {OUT}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"ERRORE: impossibile aprire i registri Sheets: {e}", file=sys.stderr)
        print("Servono le credenziali Drive/Sheets previste da app/config.py.", file=sys.stderr)
        sys.exit(1)
