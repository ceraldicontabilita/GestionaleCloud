"""Scheda Markdown dei cedolini: la copia della lettura, fonte della ricarica."""
import asyncio
import base64

from mongomock_motor import AsyncMongoMockClient

from app.services import cedolini_manager, cedolini_motore
from app.services import schede_markdown as sm

CF = "RSSMRA80A01H501U"
PDF_A = base64.b64encode(b"%PDF-1.4 busta A").decode()


def run(coro):
    return asyncio.run(coro)


def _busta(mese=4, anno=2026, netto=941.0, **kw):
    return {
        "codice_fiscale": CF, "nome_dipendente": "ROSSI MARIO", "anno": anno, "mese": mese,
        "tipo_cedolino": "mensile", "netto": netto, "netto_mese": netto,
        "stato_netto": "NETTO_VERIFICATO_DA_CEDOLINO" if netto is not None else "NETTO_NON_PRESENTE_O_NON_LEGGIBILE",
        "lordo": 1157.32, "totale_trattenute": 217.18, "livello": "5", "formato_rilevato": "zucchetti_new",
        "ferie_permessi": {"ferie_residuo": 2.5, "permessi_goduti": None},
        "dati_extra": {"tfr_mese": 293.65, "ferie_residue": 2},
        "dati_chiave": {"rateo_13ma_presente": True, "rateo_13ma_importo": "63,62", "indennita_l207_24": None},
        "voci": [{"codice": "C00001", "descrizione": "Retribuzione | base", "valori": ["9,54850", "763,48"]}],
        "impronta_busta": "d09c1a089ff4aba3e78077246bcac6fd", **kw,
    }


def _lettura(*buste, esito="buste", presenze=()):
    return {"esito": esito, "motivo": "prova", "buste": list(buste), "presenze": list(presenze), "fuori_periodo": []}


def test_la_scheda_si_rilegge_uguale_a_cio_che_e_stato_letto():
    busta = _busta()
    md = sm.scheda_cedolino(_lettura(busta), sha256="a" * 64, filename="Rossi | aprile.pdf", drive_file_id="d1")
    assert "| netto | 941.00 |" in md and "| livello | 5 |" in md
    riletta = sm.leggi_scheda(md)
    assert riletta["intestazione"]["sha256"] == "a" * 64 and riletta["intestazione"]["drive_file_id"] == "d1"
    b = riletta["buste"][0]
    for campo in ("codice_fiscale", "anno", "mese", "netto", "lordo", "stato_netto", "livello",
                  "ferie_permessi", "dati_extra", "dati_chiave", "voci", "impronta_busta"):
        assert b[campo] == busta[campo], campo
    # Cella vuota -> nullo, mai zero.
    assert sm.leggi_scheda(sm.scheda_cedolino(_lettura(_busta(netto=None)), sha256="b" * 64))["buste"][0]["netto"] is None


def test_il_registro_aggiunge_le_buste_nuove_e_perde_quelle_eliminate():
    db = AsyncMongoMockClient()["t"]
    run(sm.salva_scheda_cedolino(db, _lettura(_busta(mese=3)), sha256="a" * 64, filename="marzo.pdf"))
    run(sm.salva_scheda_cedolino(db, _lettura(_busta(mese=4)), sha256="b" * 64, filename="aprile.pdf"))
    run(sm.salva_scheda_cedolino(db, _lettura(_busta(mese=4)), sha256="b" * 64, filename="aprile.pdf"))  # rilettura
    registro = run(db[sm.REGISTRI].find_one({"id": "cedolino:2026"}))
    assert registro["buste"] == 2
    righe = [r for r in registro["markdown"].splitlines() if r.startswith("| aprile") or r.startswith("| marzo")]
    assert [r.split(" |")[0] for r in righe] == ["| aprile", "| marzo"]     # il piu' recente in alto

    assert run(sm.togli_scheda(db, "a" * 64, motivo="busta sbagliata"))["esito"] == "eliminata"
    registro = run(db[sm.REGISTRI].find_one({"id": "cedolino:2026"}))
    assert registro["buste"] == 1 and "marzo" not in registro["markdown"]
    scheda = run(db[sm.SCHEDE].find_one({"id": "cedolino:" + "a" * 64}))
    assert scheda["stato"] == sm.STATO_ELIMINATA and scheda["markdown"]       # la scheda resta


def test_ogni_lettura_dello_scrittore_unico_scrive_la_scheda(monkeypatch):
    db = AsyncMongoMockClient()["t"]
    lettura = _lettura({**_busta(), "_pdf_data": PDF_A, "_raw_text": ""})
    monkeypatch.setattr(cedolini_motore, "leggi_pdf", lambda _c: lettura)

    async def registra(db, ced, **_):
        return None

    monkeypatch.setattr(cedolini_manager, "registra_busta", registra)
    esito = run(cedolini_manager.processa_tutti_cedolini_pdf(db, PDF_A, "aprile.pdf", drive_file_id="d1"))
    scheda = run(db[sm.SCHEDE].find_one({"id": esito["scheda_markdown"]}))
    assert scheda["drive_file_id"] == "d1" and scheda["anni"] == [2026] and "ROSSI MARIO" in scheda["markdown"]


def test_la_ricarica_ritrova_la_stessa_busta_senza_rileggere_il_pdf(monkeypatch):
    from app.services.salari_unificati_v2 import _cedolino_document_key

    db = AsyncMongoMockClient()["t"]
    letta = _busta(impronta_busta=None)
    chiave_prima = _cedolino_document_key(letta, PDF_A)
    import hashlib
    letta["impronta_busta"] = hashlib.md5(base64.b64decode(PDF_A)).hexdigest()
    run(sm.salva_scheda_cedolino(db, _lettura(letta, _busta(mese=5, netto=None)), sha256="c" * 64,
                                 filename="fascicolo.pdf", drive_file_id="d9"))

    prova = run(sm.ricarica_cedolini(db, dry_run=True))
    assert prova["buste"] == 2 and prova["cedolini_processati"] == 0

    ricevute = []

    async def registra(db, ced, *, filename, pdf_data, pdf_text, results):
        ricevute.append((ced, pdf_data))

    monkeypatch.setattr(cedolini_manager, "registra_busta", registra)
    run(sm.ricarica_cedolini(db, anno=2026, dry_run=False))
    assert [c["mese"] for c, _ in ricevute] == [4, 5]
    ced, pdf = ricevute[0]
    assert pdf is None and ced["drive_file_id"] == "d9" and ced["dati_extra"]["tfr_mese"] == 293.65
    assert _cedolino_document_key(ced, None) == chiave_prima            # nessun doppione


def test_le_schede_sono_riservate_all_admin():
    from app.routers.schede_markdown import router
    from app.utils.ruoli import richiedi_admin

    assert richiedi_admin in [d.dependency for d in router.dependencies]
