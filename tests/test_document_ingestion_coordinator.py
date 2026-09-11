import asyncio
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.services.document_ingestion_coordinator import (
    MAX_SLOTS,
    QUEUE_COLLECTION,
    SCHEDULE_COLLECTION,
    WORKER_COLLECTION,
    ensure_folder_schedule,
    enqueue_due_slots,
    run_one,
)


def _match(doc, selector):
    for key, expected in selector.items():
        if key == "$or":
            if not any(_match(doc, item) for item in expected):
                return False
            continue
        value = doc.get(key)
        if isinstance(expected, dict) and "$in" in expected:
            if value not in expected["$in"]:
                return False
        elif value != expected:
            return False
    return True


class _Result:
    def __init__(self, modified_count=1):
        self.modified_count = modified_count


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return deepcopy(self.rows)


class _Collection:
    def __init__(self):
        self.rows = []
        self._lock = asyncio.Lock()

    def find(self, selector=None, projection=None):
        selector = selector or {}
        return _Cursor([row for row in self.rows if _match(row, selector)])

    async def find_one(self, selector, projection=None, sort=None):
        for row in self.rows:
            if _match(row, selector):
                return deepcopy(row)
        return None

    async def insert_one(self, doc):
        self.rows.append(deepcopy(doc))
        return _Result()

    async def update_one(self, selector, update, upsert=False):
        for row in self.rows:
            if not _match(row, selector):
                continue
            for key, value in update.get("$set", {}).items():
                row[key] = deepcopy(value)
            for key, value in update.get("$inc", {}).items():
                row[key] = row.get(key, 0) + value
            return _Result(1)
        if upsert:
            row = {k: v for k, v in selector.items() if not k.startswith("$")}
            row.update(deepcopy(update.get("$set", {})))
            for key, value in update.get("$inc", {}).items():
                row[key] = row.get(key, 0) + value
            self.rows.append(row)
            return _Result(1)
        return _Result(0)

    async def find_one_and_update(self, selector, update, upsert=False, return_document=None, **_kwargs):
        async with self._lock:
            for row in self.rows:
                if not _match(row, selector):
                    continue
                for key, value in update.get("$set", {}).items():
                    row[key] = deepcopy(value)
                for key, value in update.get("$inc", {}).items():
                    row[key] = row.get(key, 0) + value
                return deepcopy(row)
            if not upsert:
                return None
            row = {k: v for k, v in selector.items() if not k.startswith("$")}
            row.update(deepcopy(update.get("$set", {})))
            for key, value in update.get("$inc", {}).items():
                row[key] = row.get(key, 0) + value
            self.rows.append(row)
            return deepcopy(row)


class _DB:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        self.collections.setdefault(name, _Collection())
        return self.collections[name]


@pytest.mark.asyncio
async def test_48_cartelle_ricevono_48_slot_distinti_da_30_minuti():
    db = _DB()
    folders = [{"area": f"area_{idx:02d}", "folder_id": f"f{idx}"} for idx in range(MAX_SLOTS)]
    slots = await ensure_folder_schedule(db, folders)

    assert len(slots) == MAX_SLOTS
    assert [slot.slot_index for slot in slots] == list(range(MAX_SLOTS))
    assert slots[0].hour == 0 and slots[0].minute == 0
    assert slots[-1].hour == 23 and slots[-1].minute == 30


@pytest.mark.asyncio
async def test_slot_scaduto_viene_accodato_una_sola_volta():
    db = _DB()
    await ensure_folder_schedule(db, [{"area": "f24", "folder_id": "folder-f24"}])
    now = datetime(2026, 9, 11, 0, 5, tzinfo=timezone.utc)

    first = await enqueue_due_slots(db, now=now, grace_minutes=45)
    second = await enqueue_due_slots(db, now=now, grace_minutes=45)

    assert first["queued"] == 1
    assert second["queued"] == 0
    assert second["already_queued"] == 1
    assert len(db[QUEUE_COLLECTION].rows) == 1


@pytest.mark.asyncio
async def test_un_solo_worker_esegue_una_cartella_per_volta():
    db = _DB()
    now = datetime(2026, 9, 11, 0, 5, tzinfo=timezone.utc)
    await ensure_folder_schedule(
        db,
        [
            {"area": "a", "folder_id": "fa"},
            {"area": "b", "folder_id": "fb"},
        ],
    )
    # Inseriamo direttamente due job maturi, indipendentemente dallo slot della seconda area.
    for area in ("a", "b"):
        await db[QUEUE_COLLECTION].insert_one({
            "id": f"job-{area}",
            "run_key": f"{area}:test",
            "area": area,
            "status": "PENDING",
            "attempt": 0,
            "scheduled_for": now.isoformat(),
            "created_at": now.isoformat(),
            "checkpoint": None,
        })

    active = 0
    max_active = 0

    async def runner():
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.03)
        active -= 1
        return {"processed": 1}

    results = await asyncio.gather(
        run_one(db, {"a": runner, "b": runner}),
        run_one(db, {"a": runner, "b": runner}),
    )

    assert max_active == 1
    assert {result["status"] for result in results} <= {"done", "busy_local", "busy_global"}
    done = [row for row in db[QUEUE_COLLECTION].rows if row.get("status") == "DONE"]
    assert len(done) == 1


@pytest.mark.asyncio
async def test_job_parziale_torna_in_coda_senza_bloccare_gli_altri():
    db = _DB()
    now = datetime(2026, 9, 11, 0, 5, tzinfo=timezone.utc)
    for area in ("grande", "piccola"):
        await db[QUEUE_COLLECTION].insert_one({
            "id": f"job-{area}",
            "run_key": f"{area}:test",
            "area": area,
            "status": "PENDING",
            "attempt": 0,
            "scheduled_for": now.isoformat(),
            "created_at": now.isoformat(),
            "checkpoint": None,
        })

    first = await run_one(db, {
        "grande": lambda: {"processed": 50, "partial": True, "checkpoint": "50"},
        "piccola": lambda: {"processed": 1},
    })
    second = await run_one(db, {
        "grande": lambda: {"processed": 50, "partial": True, "checkpoint": "100"},
        "piccola": lambda: {"processed": 1},
    })

    assert first["area"] == "grande"
    assert first["status"] == "partial"
    assert second["area"] == "piccola"
    assert second["status"] == "done"
    grande = next(row for row in db[QUEUE_COLLECTION].rows if row["area"] == "grande")
    assert grande["checkpoint"] == "50"
    assert grande["status"] == "PARTIAL"


def test_collections_are_separate_operational_state():
    assert len({QUEUE_COLLECTION, SCHEDULE_COLLECTION, WORKER_COLLECTION}) == 3
