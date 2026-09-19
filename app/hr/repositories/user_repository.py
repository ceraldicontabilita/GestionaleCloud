"""Repository utenti — re-export del modulo unico.

La logica vive in `app/repositories/user_repository.py`. La copia che stava
qui differiva in due punti, entrambi risolti a favore del lato ERP:

- ereditava dal `base_repository` rimasto a MongoDB (vedi la nota li');
- il ruolo predefinito di un utente nuovo era `"user"` invece di
  `"operatore"`. Verificato che non cambia nulla per i permessi: in
  `app/hr/utils/dependencies.py` `require_admin` vuole esattamente `"admin"` e
  `require_staff` vuole `"admin"` o `"responsabile_turni"`, e i ruoli validi
  dell'app HR sono `{dipendente, responsabile_turni, admin}` — `"user"` non
  compare da nessuna parte, quindi non concedeva niente che `"operatore"` non
  conceda. In produzione la differenza non si e' mai vista: `hr.app_users`
  contiene un solo utente, con ruolo `admin`.
"""
from app.repositories.user_repository import UserRepository  # noqa: F401

__all__ = ["UserRepository"]
