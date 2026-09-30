"""Esegue pytest senza credenziali cloud o URL dei collaudi live ereditati.

Uso: python scripts/collaudo_isolato.py [argomenti pytest]
I test HTTP esterni restano disabilitati: usare gli E2E con marker fixture
per collaudare le scritture. Non avvia servizi né connessioni al database.
"""
from pathlib import Path
import os
import subprocess
import sys


def ambiente_isolato(sorgente):
    """Esclude anche alias legacy e URL che aprono client fuori dal deposito ERP."""
    ambiente = dict(sorgente)
    for nome in tuple(ambiente):
        if any(parola in nome for parola in (
            "SUPABASE", "SECRET", "TOKEN", "API_KEY", "GMAIL", "PAYPAL",
            "SUMUP", "PIN_HASH", "SMTP", "GOOGLE", "DATABASE", "MONGO",
            "URL", "PASSWORD", "CREDENTIAL",
        )) or nome.startswith(("VITE_", "REACT_APP_", "MENU_", "LOTTI_",
                              "HR_", "APPDIPENDENTI_")):
            ambiente.pop(nome, None)
    ambiente.update(
        ENVIRONMENT="test", ENABLE_SCHEDULER="false", PROCESS_ROLE="web",
        SECRET_KEY="collaudo-isolato-solo-fixture-32-bytes",
        FAIL_FAST_SECRETS="false",
        RUN_STARTUP_DATA_REPAIRS="false",
        RUN_STARTUP_INDEX_MIGRATIONS="false", RUN_STARTUP_SEED_DATA="false",
    )
    return ambiente


def main():
    ambiente = ambiente_isolato(os.environ)
    return subprocess.call([sys.executable, "-m", "pytest", *sys.argv[1:]],
                           cwd=Path(__file__).resolve().parents[1], env=ambiente)


if __name__ == "__main__":
    raise SystemExit(main())
