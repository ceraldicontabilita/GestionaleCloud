"""Importa i JSON recuperati da Mongo nel document store Supabase di Lotti.

L'importazione e' idempotente: la chiave e' (collezione, _id). Non cancella
mai dati gia' presenti e puo' essere rilanciata dopo un'interruzione.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

from bson import json_util

# Script offline (una tantum): va lanciato dalla radice di GestionaleCloud
# (`python -m app.lotti.scripts.migrate_recovered_json_to_supabase <cartella>`)
# oppure con la radice del repo nel PYTHONPATH. Aggiunge la radice del repo
# (parents[3] = .../gestionalecloud) e NON piu' la vecchia radice di backend/.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.lotti.supabase_document_store import SupabaseRpcStore  # noqa: E402


def _load_documents(path: Path) -> list[dict]:
    raw = path.read_bytes()
    data = json_util.loads(raw.decode("utf-8"))
    if not isinstance(data, list) or not all(isinstance(x, dict) for x in data):
        raise ValueError(f"Formato non valido: {path}")
    return data


async def run(source: Path) -> dict:
    store = SupabaseRpcStore(
        os.environ["LOTTI_SUPABASE_URL"],
        os.environ["LOTTI_SUPABASE_ANON_KEY"],
        os.environ["LOTTI_DB_SECRET"],
    )
    result = {"source": str(source), "collections": {}, "total": 0}
    try:
        for path in sorted(source.glob("*.json")):
            docs = _load_documents(path)
            imported = await store.upsert_docs(path.stem, docs)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            result["collections"][path.stem] = {
                "documents": len(docs),
                "upserted": imported,
                "sha256": digest,
            }
            result["total"] += len(docs)
        return result
    finally:
        await store.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Cartella contenente i JSON Mongo")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not args.source.is_dir():
        parser.error(f"Cartella non trovata: {args.source}")
    missing = [k for k in ("LOTTI_SUPABASE_URL", "LOTTI_SUPABASE_ANON_KEY", "LOTTI_DB_SECRET") if not os.getenv(k)]
    if missing:
        parser.error("Variabili mancanti: " + ", ".join(missing))
    result = asyncio.run(run(args.source))
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

