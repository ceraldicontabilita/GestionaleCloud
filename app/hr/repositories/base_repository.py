"""Repository CRUD di base — re-export del modulo unico.

La logica vive in `app/repositories/base_repository.py`. Fino al 19/09/2026
qui c'era una copia rimasta a MongoDB: importava `AsyncIOMotorCollection` e
`bson.ObjectId`, e costruiva il filtro per identificativo con
`ObjectId(doc_id)`.

L'app HR non gira su MongoDB: gira sull'adattatore Postgres
`app/hr/db_supabase.py`, dove gli identificativi sono testo. `ObjectId()` su
un UUID solleva `InvalidId`, che l'`except` della funzione inghiottiva — cosi'
`update`, `find_by_id` e `delete` tornavano False/None **in silenzio**.

Misurato in produzione il 19/09/2026: l'unico utente di `hr.app_users`
(`ceraldi`, id `08d4732b-…`, un UUID) non aveva **mai** ricevuto un
`last_login`, perche' `routers/pin_login.py` chiama `update_last_login` a ogni
accesso col PIN e quella catena finiva sempre nell'`InvalidId`.

Il modulo unico costruisce ora un filtro valido su entrambi gli archivi
(`_id` per il runtime dell'ERP, `id` per quello HR).
"""
from app.repositories.base_repository import BaseRepository  # noqa: F401

__all__ = ["BaseRepository"]
