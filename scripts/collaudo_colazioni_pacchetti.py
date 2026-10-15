"""Tre test di contesa nativa su un database locale usa e getta.

Predisporre un cluster PostgreSQL locale di collaudo, già in esecuzione.
Esempio: python scripts/collaudo_colazioni_pacchetti.py \
    --socket-dir /tmp/pg-collaudo --pg-bin /usr/lib/postgresql/16/bin --user postgres

Il runner crea e rimuove esclusivamente un database qa_colazioni_<uuid>.
Non installa dipendenze, non avvia server e non accetta host remoti.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import uuid


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket-dir", type=Path, required=True)
    parser.add_argument("--pg-bin", type=Path)
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user", default="postgres")
    args = parser.parse_args()
    host = args.socket_dir.resolve()
    if not host.is_dir():
        parser.error("La cartella del socket PostgreSQL locale non esiste")
    if args.port not in range(1, 65536):
        parser.error("Porta non valida")
    psql = (args.pg_bin / "psql") if args.pg_bin else Path(shutil.which("psql") or "/non-disponibile")
    createdb, dropdb = psql.with_name("createdb"), psql.with_name("dropdb")
    if not all(path.is_file() for path in (psql, createdb, dropdb)):
        parser.error("Servono i client PostgreSQL psql, createdb e dropdb; indicarli con --pg-bin")
    name = "qa_colazioni_" + uuid.uuid4().hex
    connection = ["-h", str(host), "-p", str(args.port), "-U", args.user]
    environment = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    environment.update(BB_QA_PG_READY="1", BB_QA_PSQL=str(psql), BB_QA_HOST=str(host),
                       BB_QA_PORT=str(args.port), BB_QA_USER=args.user, BB_QA_NAME=name,
                       BB_QA_MIGRATIONS_DIR=str(ROOT / "supabase/migrations"))
    create = subprocess.run([str(createdb), *connection, "--template=template0", name],
                            env=environment, text=True, capture_output=True, timeout=25)
    if create.returncode:
        parser.exit(create.returncode, create.stderr)
    try:
        module_file = ROOT / "tests/colazioni/test_pacchetti_concorrenza_postgres.py"
        result = subprocess.run([os.sys.executable, str(module_file)], env=environment, cwd=ROOT, timeout=120)
        return result.returncode
    finally:
        cleanup = subprocess.run([str(dropdb), *connection, "--if-exists", name],
                                 env=environment, text=True, capture_output=True, timeout=25)
        if cleanup.returncode:
            print("Impossibile rimuovere il database di collaudo " + name + ": " + cleanup.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
