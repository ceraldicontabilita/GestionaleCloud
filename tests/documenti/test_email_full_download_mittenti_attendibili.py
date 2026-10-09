"""REGOLA UTENTE 18/07/2026: "la lista è il vangelo per scaricare la
posta" — la scansione email generica ("Scarica Documenti da Email")
scarica SOLO dai mittenti configurati in Mittenti Email (collezione
mittenti_email, qualunque tipo documento, attivi). Lista vuota = ZERO
download: nessun fallback permissivo. (Prima: lista vuota = nessuna
restrizione, ed entravano saveris2.net, pec.kimbo.it, legalmail mai
autorizzati dall'utente.)"""
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
        # la whitelist carica find({"attivo": True}) su TUTTI i tipi
        return _FakeCursor([
            d for d in self.docs
            if all(d.get(k2) == v for k2, v in query.items())
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


def test_lista_vuota_zero_download(monkeypatch):
    """La lista è il vangelo: senza mittenti configurati NON si scarica
    nulla (niente fallback permissivo)."""
    downloader = EmailFullDownloader(db=_FakeDb(mittenti_docs=[]))
    monkeypatch.setattr(downloader, "save_pdf_to_db", _stub_save)

    salvati = _run(downloader.process_email(
        b"1", _msg_con_pdf("Testo Saveris <no-reply-eu.saveris2@saveris2.net>")))

    assert salvati == 0


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


def test_whitelist_copre_tutti_i_tipi_documento(monkeypatch):
    """Un mittente configurato per i cedolini (tipo diverso da 'generico')
    è comunque attendibile per la scansione generica: la lista è unica."""
    downloader = EmailFullDownloader(db=_FakeDb(mittenti_docs=[
        {"pattern": "paghe@consulente.it", "indirizzo_email": "paghe@consulente.it",
         "canale": "gmail", "tipo_documento": "cedolino", "attivo": True},
        {"pattern": "vecchio@dismesso.it", "indirizzo_email": "vecchio@dismesso.it",
         "canale": "gmail", "tipo_documento": "generico", "attivo": False},
    ]))
    monkeypatch.setattr(downloader, "save_pdf_to_db", _stub_save)

    da_cedolini = _run(downloader.process_email(
        b"1", _msg_con_pdf("Paghe <paghe@consulente.it>")))
    assert da_cedolini == 1

    disattivato = _run(downloader.process_email(
        b"2", _msg_con_pdf("Vecchio <vecchio@dismesso.it>")))
    assert disattivato == 0


async def _stub_save(**kwargs):
    return "doc-fake-id"
