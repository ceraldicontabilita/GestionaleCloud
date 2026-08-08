import asyncio
import base64

from app.services import cedolini_manager as manager


def _matches(doc, query):
    if "$or" in query:
        return any(_matches(doc, branch) for branch in query["$or"])
    for key, value in query.items():
        if isinstance(value, dict) and "$exists" in value:
            if (key in doc) != value["$exists"]:
                return False
        elif doc.get(key) != value:
            return False
    return True


class _Collection:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, *args, **kwargs):
        return next((dict(doc) for doc in self.docs if _matches(doc, query)), None)

    async def insert_one(self, doc):
        row = dict(doc)
        row.setdefault("_id", f"mongo-{len(self.docs) + 1}")
        self.docs.append(row)

    async def update_one(self, query, update, *args, **kwargs):
        for doc in self.docs:
            if _matches(doc, query):
                doc.update(update.get("$set", {}))
                return


class _Db:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _Collection())


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _data(netto, tipo="mensile"):
    return {
        "codice_fiscale": "RSSMRA80A01H501U",
        "nome_dipendente": "Rossi Mario",
        # Usa un mese gia' maturato nel periodo contabile operativo. Dicembre
        # 2026 e' futuro rispetto alla data del collaudo e deve correttamente
        # restare fuori dalla Prima Nota Salari.
        "mese": 6,
        "anno": 2026,
        "netto_mese": netto,
        "lordo": netto + 500,
        "tipo_cedolino": tipo,
    }


def _disable_side_effects(monkeypatch):
    async def no_match(*args, **kwargs):
        return False

    async def no_event(*args, **kwargs):
        return None

    monkeypatch.setattr(manager, "riconcilia_stipendio_automatico", no_match)
    import app.services.event_bus as event_bus
    monkeypatch.setattr(event_bus, "propagate_event", no_event)


def test_documenti_distinti_stesso_mese_restano_distinti(monkeypatch):
    _disable_side_effects(monkeypatch)
    db = _Db()
    pdf_mensile = base64.b64encode(b"%PDF-1.4 mensile").decode()
    pdf_tredicesima = base64.b64encode(b"%PDF-1.4 tredicesima").decode()

    first = _run(manager.processa_cedolino_completo(db, _data(1500), "mensile.pdf", pdf_mensile))
    second = _run(manager.processa_cedolino_completo(
        db, _data(900, "tredicesima"), "tredicesima.pdf", pdf_tredicesima
    ))

    assert first["success"] and second["success"]
    assert len(db["riepilogo_cedolini"].docs) == 2
    assert len(db["prima_nota_salari"].docs) == 2
    assert len({d["cedolino_dedup_key"] for d in db["prima_nota_salari"].docs}) == 2


def test_stesso_pdf_riprocessato_e_idempotente(monkeypatch):
    _disable_side_effects(monkeypatch)
    db = _Db()
    pdf = base64.b64encode(b"%PDF-1.4 stesso documento").decode()
    _run(manager.processa_cedolino_completo(db, _data(1500), "mensile.pdf", pdf))
    _run(manager.processa_cedolino_completo(db, _data(1500), "mensile.pdf", pdf))

    assert len(db["riepilogo_cedolini"].docs) == 1
    assert len(db["prima_nota_salari"].docs) == 1


def test_v2_usa_hash_pdf_e_fallback_legacy_esatto():
    from app.services.salari_unificati_v2 import (
        _cedolino_document_key,
        _cedolino_identity_filter,
    )

    data = _data(1500)
    pdf_a = base64.b64encode(b"%PDF-1.4 A").decode()
    pdf_b = base64.b64encode(b"%PDF-1.4 B").decode()
    key_a = _cedolino_document_key(data, pdf_a)
    key_b = _cedolino_document_key(data, pdf_b)
    assert key_a != key_b

    filtro = _cedolino_identity_filter(
        data["codice_fiscale"], 12, 2026, "mensile",
        key_a, "mensile.pdf", 1500, 2000,
    )
    assert filtro["$or"][0] == {"cedolino_dedup_key": key_a}
    legacy = filtro["$or"][1]
    assert legacy["cedolino_dedup_key"] == {"$exists": False}
    assert legacy["filename"] == "mensile.pdf"
    assert legacy["netto"] == 1500
