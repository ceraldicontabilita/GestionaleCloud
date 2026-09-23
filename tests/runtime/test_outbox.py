import asyncio

from app.services import event_bus, outbox


class _MemCursor:
    def __init__(self, rows):
        self._rows = list(rows)

    def __aiter__(self):
        self._i = 0
        return self

    async def __anext__(self):
        if self._i >= len(self._rows):
            raise StopAsyncIteration
        row = self._rows[self._i]
        self._i += 1
        return row


class _Collezione:
    def __init__(self):
        self.rows = []

    async def find_one(self, filtro):
        for row in self.rows:
            if all(row.get(k) == v for k, v in filtro.items()):
                return dict(row)
        return None

    async def insert_one(self, doc):
        self.rows.append(dict(doc))

    async def update_one(self, filtro, update, upsert=False):
        for i, row in enumerate(self.rows):
            if all(row.get(k) == v for k, v in filtro.items()):
                nuovo = dict(row)
                nuovo.update(update.get("$set") or {})
                self.rows[i] = nuovo
                return
        if upsert:
            base = dict(filtro)
            base.update(update.get("$setOnInsert") or {})
            base.update(update.get("$set") or {})
            self.rows.append(base)

    def find(self, filtro):
        def ok(row):
            for k, v in filtro.items():
                if isinstance(v, dict) and "$in" in v:
                    if row.get(k) not in v["$in"]:
                        return False
                elif row.get(k) != v:
                    return False
            return True

        return _MemCursor([r for r in self.rows if ok(r)])


class _Db(dict):
    def __init__(self):
        super().__init__()
        self["outbox_events"] = _Collezione()
        self["outbox_deliveries"] = _Collezione()
        self["agenti_segnalazioni"] = _Collezione()


def test_enqueue_idempotente_e_retry_per_consumer():
    async def scenario():
        event_bus._handlers.clear()
        chiamate = []

        async def ok(ctx, db):
            chiamate.append(("ok", ctx["id"]))
            return {"ok": True}

        async def ko(ctx, db):
            chiamate.append(("ko", ctx["id"]))
            raise RuntimeError("lotti giu")

        event_bus.register_handler("fattura.created", ok)
        event_bus.register_handler("fattura.created", ko)
        db = _Db()
        payload = {"id": "fat-1", "totale": "10.00"}

        prima = await outbox.registra(db, "fattura.created", payload)
        seconda = await outbox.registra(db, "fattura.created", payload)
        assert prima["duplicato"] is False
        assert seconda["duplicato"] is True
        assert seconda["id"] == prima["id"]
        assert len(db["outbox_events"].rows) == 1
        assert {r["consumer"] for r in db["outbox_deliveries"].rows} == {"ok", "ko"}

        stats = await outbox.riprocessa_pendenti(db)
        assert stats["ok"] == 1
        assert stats["errori"] == 1
        stati = {r["consumer"]: r["stato"] for r in db["outbox_deliveries"].rows}
        assert stati["ok"] == "done"
        assert stati["ko"] == "error"

        stats2 = await outbox.riprocessa_pendenti(db)
        assert stats2["ok"] == 0
        assert stats2["errori"] == 1
        assert [c for c, _ in chiamate].count("ok") == 1
        assert [c for c, _ in chiamate].count("ko") == 2

        event_bus._handlers.clear()

    asyncio.run(scenario())


def test_propagate_event_persiste_prima_di_eseguire():
    async def scenario():
        event_bus._handlers.clear()
        visto = []

        async def handler(ctx, db):
            visto.append(ctx["event_id"])
            return True

        event_bus.register_handler("cedolino.importato", handler)
        db = _Db()
        risultati = await event_bus.propagate_event(
            "cedolino.importato",
            {"cedolino_id": "c-9"},
            db,
            source_module="test",
        )
        assert visto
        assert db["outbox_events"].rows
        assert risultati and risultati[0]["success"] is True
        consegna = db["outbox_deliveries"].rows[0]
        assert consegna["stato"] == "done"
        event_bus._handlers.clear()

    asyncio.run(scenario())
