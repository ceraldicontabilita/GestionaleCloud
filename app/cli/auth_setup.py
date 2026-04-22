"""
CLI di emergenza per gestione utenti admin.

Utilizzo sul server (shell del container Emergent):
    python -m app.cli.auth_setup

Funzioni:
- Se non ci sono utenti nel DB: crea il primo utente admin (interattivo)
- Se ci sono utenti: elenca gli account esistenti e offre reset password

Questo tool NON espone endpoint web. Funziona solo con accesso shell al server.
Mai passare la password come argomento di comando (finirebbe nella history shell):
la si inserisce sempre tramite prompt mascherato.
"""
import asyncio
import sys
import getpass
from datetime import datetime, timezone
from typing import Optional

import bcrypt

from app.database import Database
from app.database import Collections


def _hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def _chiedi_password(label: str = "Password") -> str:
    """Chiede password due volte via prompt mascherato, valida lunghezza minima."""
    while True:
        pw1 = getpass.getpass(f"{label} (min 8 caratteri): ")
        if len(pw1) < 8:
            print("❌ La password deve essere di almeno 8 caratteri. Riprova.")
            continue
        pw2 = getpass.getpass(f"{label} (conferma): ")
        if pw1 != pw2:
            print("❌ Le password non coincidono. Riprova.")
            continue
        return pw1


def _chiedi_email() -> str:
    while True:
        email = input("Email: ").strip().lower()
        if "@" not in email or "." not in email.split("@")[-1]:
            print("❌ Email non valida. Riprova.")
            continue
        return email


async def _crea_primo_admin(db) -> None:
    """Crea il primo utente admin nel DB vuoto."""
    print("\n=== CREAZIONE PRIMO ADMIN ===")
    print("Nessun utente esiste nel database. Creo il primo admin.\n")

    email = _chiedi_email()

    # Double-check: qualcuno potrebbe averlo creato in una corsa
    if await db[Collections.USERS].find_one({"email": email}):
        print(f"❌ Email {email} già registrata. Annullo.")
        return

    nome = input("Nome (opzionale): ").strip() or None
    password = _chiedi_password("Password admin")

    doc = {
        "email": email,
        "password_hash": _hash_password(password),
        "name": nome,
        "role": "admin",
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    result = await db[Collections.USERS].insert_one(doc)
    print(f"\n✅ Admin creato con successo")
    print(f"   Email: {email}")
    print(f"   Nome: {nome or '(nessuno)'}")
    print(f"   Ruolo: admin")
    print(f"   _id MongoDB: {result.inserted_id}")
    print(f"\nOra puoi loggarti da /login con queste credenziali.")


async def _gestione_utenti_esistenti(db) -> None:
    """Mostra utenti esistenti e permette reset password."""
    cursor = db[Collections.USERS].find(
        {}, {"_id": 0, "email": 1, "name": 1, "role": 1, "is_active": 1,
             "created_at": 1, "last_login": 1}
    )
    utenti = await cursor.to_list(1000)

    print(f"\n=== UTENTI ESISTENTI ({len(utenti)}) ===\n")
    for idx, u in enumerate(utenti, 1):
        attivo = "✓" if u.get("is_active", True) else "✗"
        ruolo = u.get("role", "user")
        nome = u.get("name") or "(senza nome)"
        last_login = u.get("last_login")
        last_str = last_login.isoformat() if hasattr(last_login, "isoformat") else str(last_login or "mai")
        print(f"  [{idx}] {attivo} {u['email']} — {nome} — ruolo: {ruolo} — ultimo login: {last_str}")

    print("\nOpzioni:")
    print("  [r] Reset password di un utente")
    print("  [c] Crea nuovo utente aggiuntivo")
    print("  [a] Abilita/disabilita utente")
    print("  [q] Esci senza modifiche")

    scelta = input("\nScelta: ").strip().lower()

    if scelta == "q" or not scelta:
        print("Uscita senza modifiche.")
        return

    if scelta == "r":
        await _reset_password(db, utenti)
    elif scelta == "c":
        await _crea_utente_aggiuntivo(db)
    elif scelta == "a":
        await _toggle_attivo(db, utenti)
    else:
        print("Scelta non valida. Uscita.")


async def _reset_password(db, utenti) -> None:
    email = input("Email dell'utente di cui resettare la password: ").strip().lower()
    if not any(u["email"] == email for u in utenti):
        print(f"❌ Email {email} non trovata nella lista.")
        return
    password = _chiedi_password("Nuova password")
    result = await db[Collections.USERS].update_one(
        {"email": email},
        {"$set": {
            "password_hash": _hash_password(password),
            "updated_at": datetime.now(timezone.utc),
        }}
    )
    if result.modified_count:
        print(f"✅ Password aggiornata per {email}")
    else:
        print(f"⚠️  Nessuna modifica effettuata.")


async def _crea_utente_aggiuntivo(db) -> None:
    email = _chiedi_email()
    if await db[Collections.USERS].find_one({"email": email}):
        print(f"❌ Email {email} già registrata.")
        return
    nome = input("Nome (opzionale): ").strip() or None
    ruolo = input("Ruolo (admin/user) [default: user]: ").strip().lower() or "user"
    if ruolo not in ("admin", "user"):
        print(f"⚠️  Ruolo '{ruolo}' non standard, imposto 'user'.")
        ruolo = "user"
    password = _chiedi_password("Password")
    doc = {
        "email": email,
        "password_hash": _hash_password(password),
        "name": nome,
        "role": ruolo,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    result = await db[Collections.USERS].insert_one(doc)
    print(f"✅ Utente creato: {email} ({ruolo})")


async def _toggle_attivo(db, utenti) -> None:
    email = input("Email dell'utente da abilitare/disabilitare: ").strip().lower()
    utente = next((u for u in utenti if u["email"] == email), None)
    if not utente:
        print(f"❌ Email {email} non trovata.")
        return
    attuale = utente.get("is_active", True)
    nuovo = not attuale
    conferma = input(f"Stato attuale: {'attivo' if attuale else 'disattivo'}. "
                     f"Imposto a {'attivo' if nuovo else 'disattivo'}? [s/N]: ").strip().lower()
    if conferma != "s":
        print("Annullato.")
        return
    await db[Collections.USERS].update_one(
        {"email": email},
        {"$set": {"is_active": nuovo, "updated_at": datetime.now(timezone.utc)}}
    )
    print(f"✅ Utente {email} → {'attivo' if nuovo else 'disattivo'}")


async def main() -> None:
    print("=" * 60)
    print("  CERALDI ERP — CLI Gestione Utenti Admin")
    print("=" * 60)

    # Connetti al DB
    await Database.connect_db()
    db = Database.get_db()

    try:
        count = await db[Collections.USERS].count_documents({})
        print(f"\nUtenti presenti nel database: {count}")

        if count == 0:
            await _crea_primo_admin(db)
        else:
            await _gestione_utenti_esistenti(db)

    finally:
        await Database.close_db()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrotto dall'utente.")
        sys.exit(130)
