"""Bug segnalato dall'utente 15/07/2026: la scansione email generica
("Scarica Documenti da Email") dichiarava nel docstring di filtrare per
"parole chiave amministrative e mittenti attendibili", ma il filtro
mittenti non era mai stato implementato — scaricava allegati da
QUALSIASI mittente il cui testo contenesse una parola chiave molto
generica (es. "enel", "bolletta"), incluse fonti mai autorizzate
dall'utente. La collezione mittenti_email (già usata da cedolini/verbali)
viene ora consultata anche qui per il tipo_documento "generico"."""
import asyncio
from email.message import EmailMessage

from app.services.email_full_download import EmailFullDownloader


class _FakeConfigColl:
    async def find_one(self, *a, **k):
        return None  # nessuna keyword configurata -> usa i default


class _FakeMittentiColl:
    def __init__(self, docs):
        self.docs = docs

    def find(self, query, *a, **k):
        return _FakeCursor([
            d for d in self.docs
            if d.get("tipo_documento") == query.get("tipo_documento")
            and d.get("canale") == query.get("canale")
            and d.get("attivo", True)
        ])


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        return _AsyncIter(self._docs)


class _AsyncIter:
    def __init__(self, docs):
        self._docs = list(docs)
        self._i = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._i >= len(self._docs):
            raise StopAsyncIteration
        d = self._docs[self._i]
        self._i += 1
        return d


class _FakeDb:
    def __init__(self, mittenti_docs=None):
        self._mittenti = _FakeMittentiColl(mittenti_docs or [])

    def __getitem__(self, name):
        if name == "config":
            return _FakeConfigColl()
        if name == "mittenti_email":
            return self._mittenti
        if name == "mittenti_attendibili":
            return _FakeMittentiColl([])  # legacy, vuota
        raise AssertionError(f"collection non attesa nel test: {name}")


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _msg_con_pdf(mittente: str, oggetto: str = "Bolletta ENEL energia elettrica") -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = mittente
    msg["Subject"] = oggetto
    msg["Date"] = "Tue, 15 Jul 2026 08:00:00 +0000"
    msg.set_content("corpo email")
    # >500 byte: extract_pdfs_from_email scarta gli allegati più piccoli
    # (soglia anti file-vuoti/corrotti).
    msg.add_attachment(b"%PDF-1.4 fake" + b"0" * 600, maintype="application", subtype="pdf",
                        filename="documento.pdf")
    return msg


def test_senza_mittenti_configurati_nessuna_restrizione(monkeypatch):
    """Lista vuota per tipo 'generico' = comportamento attuale (nessun blocco),
    per non spegnere di colpo il canale finché l'utente non la popola."""
    downloader = EmailFullDownloader(db=_FakeDb(mittenti_docs=[]))
    monkeypatch.setattr(downloader, "save_pdf_to_db", _stub_save)

    salvati = _run(downloader.process_email(
        b"1", _msg_con_pdf("Raffaele Mangiacapra <raffaele@saveris2.net>")))

    assert salvati == 1


def test_con_mittenti_configurati_blocca_non_attendibili(monkeypatch):
    downloader = EmailFullDownloader(db=_FakeDb(mittenti_docs=[
        {"pattern": "commercialista@studioceraldi.it", "indirizzo_email": "commercialista@studioceraldi.it",
         "canale": "gmail", "tipo_documento": "generico", "attivo": True},
    ]))
    monkeypatch.setattr(downloader, "save_pdf_to_db", _stub_save)

    non_attendibile = _run(downloader.process_email(
        b"1", _msg_con_pdf("Raffaele Mangiacapra <raffaele@saveris2.net>")))
    assert non_attendibile == 0

    attendibile = _run(downloader.process_email(
        b"2", _msg_con_pdf("Studio Ceraldi <commercialista@studioceraldi.it>")))
    assert attendibile == 1


async def _stub_save(**kwargs):
    return "doc-fake-id"
