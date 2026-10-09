"""DRV-03 (resto) e bonifica del solo ``canale`` (MINI-09.5 e MINI-09.6).

Si prova che: il canale si ricava dai campi storici con il normalizzatore unico e
non si inventa; una busta con `canale` non si tocca; il netto e `netto_fonte` non
si toccano; il `drive_file_id` del cedolino si scrive solo con un originale
univoco; un file con piu' buste e' un documento combinato (confermato); un'impronta
su piu' file identici senza un solo creatore resta DA_VERIFICARE; i collegamenti
del protocollo verso entita' sparite si riagganciano solo con una prova di
identita' del file. Tutto sintetico: nessun nome, codice fiscale o IBAN.
"""
import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.constants.canale_documento import canale_ricavabile
from app.services import canale_bonifica, indice_relazionale as indice
from app.services import protocollo_collegamenti as coll
from app.services import relazioni_documentali as doc
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

SHA_A, SHA_B, SHA_C, SHA_D = ("a" * 64, "b" * 64, "c" * 64, "d" * 64)
MD5_1, MD5_2, MD5_3 = ("1" * 32, "2" * 32, "3" * 32)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _db(nome):
    return ClientArchivioMemoria()[nome]


def _ins(db, coll_nome, **campi):
    _run(db[coll_nome].insert_one(campi))


def _rel(db):
    return _run(db["entity_relations"].find({}, {"_id": 0}).to_list(length=None))


def _reg(db, drive_id, sha, *, gia_presente=False, cartella="ELABORATE"):
    _ins(db, "drive_cartella_unica", id=drive_id, drive_file_id=drive_id, cartella=cartella, sha256=sha,
         md5=drive_id[:1] * 32, gia_presente=gia_presente, esito="elaborato")


# ── canale: il normalizzatore ────────────────────────────────────────────────

def test_canale_esistente_vince_su_ogni_altra_prova():
    assert canale_ricavabile({"canale": "posta", "drive_file_id": "X", "source": "gmail"}) == ("posta", "canale_esistente")


def test_etichetta_del_motore_non_e_un_canale():
    # `cedolino_v2` e `gestionale_cloud` dicono chi ha scritto la riga, non da dove e' arrivato il file
    assert canale_ricavabile({"source": "cedolino_v2"}) == (None, None)
    assert canale_ricavabile({"fonte": "gestionale_cloud", "gestionale_source": "cedolino_v2"}) == (None, None)


def test_percorso_di_posta_e_percorso_drive():
    assert canale_ricavabile({"source": "cedolino_v2", "source_path": "2023-04-12_mittente@esempio.it_busta.pdf"}) == ("posta", "percorso")
    assert canale_ricavabile({"source": "cedolino_v2", "source_path": "PERSONA UNO/DA ELABORARE/busta.pdf"}) == ("drive", "percorso")
    # il solo nome del file non dice niente: non si inventa
    assert canale_ricavabile({"source": "cedolino_v2", "source_path": "busta.pdf"}) == (None, None)
    assert canale_ricavabile({"source_path": "una/cartella/qualunque/busta.pdf"}) == (None, None)


def test_etichetta_di_posta_batte_id_drive_come_alla_creazione():
    # un allegato di posta archiviato su Drive resta «posta» (`canale_obbligatorio`)
    assert canale_ricavabile({"fonte": "gmail_scan", "drive_file_id": "D1"}) == ("posta", "etichetta:fonte")
    assert canale_ricavabile({"drive_file_id": "D1"}) == ("drive", "drive_file_id")
    assert canale_ricavabile({"source_occurrences": [{"drive_file_id": "D2"}]}) == ("drive", "drive_file_id")
    assert canale_ricavabile({"source_occurrences": [{"drive_file_id": ""}]}) == (None, None)


def test_etichetta_sconosciuta_e_altro_solo_se_nient_altro_parla():
    assert canale_ricavabile({"fonte": "import dipendenti-main.zip"}) == ("altro", "etichetta:fonte")
    assert canale_ricavabile({"fonte": "import dipendenti-main.zip", "source_path": "A/DA ELABORARE/x.pdf"}) == ("drive", "percorso")
    assert canale_ricavabile({"fonte": "import Drive/GESTIONALE/Cedolini Paga/Elaborate"}) == ("drive", "etichetta:fonte")


# ── canale: la bonifica ──────────────────────────────────────────────────────

def _buste():
    db = _db("canale-erp")
    _ins(db, "cedolini", _id="c-drive", id="c-drive", source="cedolino_v2", source_path="X/DA ELABORARE/a.pdf", netto=100.5)
    _ins(db, "cedolini", _id="c-posta", id="c-posta", source="cedolino_v2", source_path="2023-01-02_m@esempio.it_a.pdf")
    _ins(db, "cedolini", _id="c-niente", id="c-niente", source="cedolino_v2", source_path="a.pdf",
         netto_fonte="cella", netto=7)
    _ins(db, "cedolini", _id="c-gia", id="c-gia", canale="caricato", source_path="X/DA ELABORARE/b.pdf")
    return db


def test_anteprima_conta_per_canale_e_non_ricavabile_senza_scrivere():
    db = _buste()
    esito = _run(canale_bonifica.esegui(db))
    g = esito["gestionale"]
    assert esito["dry_run"] is True and esito["scritte_gestionale"] == 0
    assert g["per_canale"] == {"posta": 1, "drive": 1, "caricato": 0, "altro": 0}
    assert g["non_ricavabile"] == 1 and g["gia_con_canale"] == 1 and g["da_scrivere"] == 2
    assert esito["hr"] == {"stato": "non_raggiungibile"}          # si dichiara, non e' uno zero
    assert all("canale" not in r for r in _run(db["cedolini"].find({"id": {"$in": ["c-drive", "c-posta", "c-niente"]}}).to_list(length=None)))
    # nessun nome di file negli esempi
    assert all(set(e) == {"archivio", "id", "canale", "regola"} for e in g["esempi_non_ricavabili"])


def test_scrittura_idempotente_non_sovrascrive_e_non_tocca_netto():
    db = _buste()
    primo = _run(canale_bonifica.esegui(db, dry_run=False))
    assert primo["scritte_gestionale"] == 2 and primo["restanti"] == 0
    per_id = {r["id"]: r for r in _run(db["cedolini"].find({}).to_list(length=None))}
    assert per_id["c-drive"]["canale"] == "drive" and per_id["c-posta"]["canale"] == "posta"
    assert "canale" not in per_id["c-niente"]                      # non ricavabile: resta vuoto
    assert per_id["c-gia"]["canale"] == "caricato"                 # la prima copia fissa il canale
    assert per_id["c-drive"]["netto"] == 100.5 and "netto_fonte" not in per_id["c-drive"]
    assert per_id["c-niente"]["netto_fonte"] == "cella" and per_id["c-niente"]["netto"] == 7
    secondo = _run(canale_bonifica.esegui(db, dry_run=False))
    assert secondo["scritte_gestionale"] == 0 and secondo["gestionale"]["da_scrivere"] == 0
    assert secondo["gestionale"]["gia_con_canale"] == 3 and secondo["gestionale"]["non_ricavabile"] == 1


def test_il_limite_spezza_il_giro_e_si_riprende():
    db = _buste()
    uno = _run(canale_bonifica.esegui(db, dry_run=False, limite=1))
    assert uno["scritte_gestionale"] == 1 and uno["restanti"] == 1
    due = _run(canale_bonifica.esegui(db, dry_run=False, limite=1))
    assert due["scritte_gestionale"] == 1 and due["restanti"] == 0


class _ConHr:
    """Connessione HR finta: ``fetch`` restituisce le righe, ``execute`` registra le scritture."""

    def __init__(self, righe, guasto=False):
        self.righe, self.guasto, self.scritture = righe, guasto, []

    async def fetch(self, sql):
        if self.guasto:
            raise RuntimeError("")
        return self.righe

    async def execute(self, sql, *args):
        self.scritture.append((sql, args))
        return "UPDATE 1"


def test_hr_canale_proprio_poi_gemella_del_gestionale_mai_su_chi_ce_l_ha():
    db = _db("canale-hr")
    _ins(db, "cedolini", _id="e1", id="e1", source="cedolino_v2", cedolino_dedup_key="K1", canale="posta")
    _ins(db, "cedolini", _id="e2", id="e2", source="cedolino_v2", cedolino_dedup_key="K2", source_path="a.pdf")
    righe = [
        {"id": "h1", "fonte": "import Drive/GESTIONALE/Cedolini Paga/Elaborate"},      # etichetta
        {"id": "h2", "fonte": "gestionale_cloud", "cedolino_dedup_key": "K1"},           # gemella: posta
        {"id": "h3", "fonte": "gestionale_cloud", "cedolino_dedup_key": "K2"},           # gemella senza canale
        {"id": "h4", "fonte": "gestionale_cloud"},                                        # niente
        {"id": "h5", "fonte": "gestionale_cloud", "canale": "caricato"},                  # gia' fissato
    ]
    con = _ConHr(righe)
    esito = _run(canale_bonifica.esegui(db, dry_run=False, hr_con=con, tabella_hr='"hr"."app_cedolini"'))
    h = esito["hr"]
    assert h["stato"] == "letto" and h["per_canale"] == {"posta": 1, "drive": 1, "caricato": 0, "altro": 0}
    assert h["non_ricavabile"] == 2 and h["gia_con_canale"] == 1
    assert sorted(a[0] for _, a in con.scritture) == ["h1", "h2"]
    # la scrittura HR non puo' sovrascrivere e non tocca altri campi
    assert all("coalesce(doc->>'canale', '') = ''" in sql and "netto" not in sql for sql, _ in con.scritture)
    assert esito["scritte_hr"] == 2


def test_hr_in_errore_si_dichiara_e_il_gestionale_prosegue():
    db = _buste()
    esito = _run(canale_bonifica.esegui(db, dry_run=False, hr_con=_ConHr([], guasto=True), tabella_hr='"hr"."app_cedolini"'))
    assert esito["hr"]["stato"] == "errore" and esito["hr"]["errore"].startswith("RuntimeError")
    assert esito["scritte_gestionale"] == 2


def _client_canale(monkeypatch, db):
    from app.database import Database
    from app.routers import cedolini_canale as router
    from app.utils.dependencies import get_current_admin_user

    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(router, "_job_task", None)
    app = FastAPI()
    app.include_router(router.router, prefix="/api/cedolini")
    app.dependency_overrides[get_current_admin_user] = lambda: {"sub": "a", "role": "admin"}
    return TestClient(app), router


def test_endpoint_canale_dry_run_per_difetto_e_solo_admin(monkeypatch):
    db = _buste()
    client, router = _client_canale(monkeypatch, db)
    with client:
        assert client.post("/api/cedolini/canale/bonifica").json()["dry_run"] is True
        for _ in range(200):
            stato = client.get("/api/cedolini/canale/stato").json()
            if stato.get("stato") == "completato" and stato.get("esito"):
                break
        assert stato["esito"]["dry_run"] is True and stato["esito"]["scritte_gestionale"] == 0
    from app.utils.dependencies import get_current_admin_user
    for rotta in router.router.routes:
        assert any(d.call is get_current_admin_user for d in rotta.dependant.dependencies), rotta.path


# ── relazioni: cedolini col registro della cartella unica ────────────────────

def _busta(db, ident, **campi):
    _ins(db, "cedolini", _id=ident, id=ident, **campi)


def _occ(*hash_):
    return [{"filename": "f.pdf", "drive_file_id": "", "source_file_hash": h} for h in hash_]


def test_cedolino_con_impronta_propria_sha256_scrive_il_drive_file_id_solo_dopo_il_giro_vero():
    db = _db("drv-ced-sha")
    _reg(db, "D-SINGOLO", SHA_A)
    _busta(db, "c1", source_file_hash=SHA_A, source_occurrences=_occ(SHA_A))
    esito = _run(doc.esegui(db, protocollo=[]))
    assert esito["dry_run"] is True and esito["cedolini_scritti"] == 0 and esito["drive_file_id_da_scrivere"] == 1
    assert "drive_file_id" not in _run(db["cedolini"].find_one({"id": "c1"}))
    vero = _run(doc.esegui(db, dry_run=False, protocollo=[]))
    assert vero["cedolini_scritti"] == 1 and vero["scritte"] == 1
    assert _run(db["cedolini"].find_one({"id": "c1"}))["drive_file_id"] == "D-SINGOLO"
    r = _rel(db)
    assert [(x["source"]["type"], x["target"]["id"], x["status"], x["rule"]) for x in r] == [
        ("payslip", "D-SINGOLO", "confirmed", "impronta_sha256")]
    secondo = _run(doc.esegui(db, dry_run=False, protocollo=[]))
    assert secondo["nuove"] == 0 and secondo["scritte"] == 0 and secondo["cedolini_scritti"] == 0
    assert secondo["restanti"] == 0


def test_busta_in_piu_file_senza_impronta_propria_non_riceve_drive_file_id_ma_le_copie_restano_relazioni():
    db = _db("drv-ced-copie")
    _reg(db, "D-UNO", SHA_A)
    _reg(db, "D-COMBINATO", SHA_B)
    _busta(db, "c1", source_occurrences=_occ(SHA_A, SHA_B))                  # nessuna impronta propria
    _busta(db, "c2", source_occurrences=_occ(SHA_B))                         # stessa file combinato
    esito = _run(doc.esegui(db, dry_run=False, protocollo=[]))
    stati = {(x["source"]["id"], x["target"]["id"]): x["status"] for x in _rel(db)}
    assert stati == {("c1", "D-UNO"): "confirmed", ("c1", "D-COMBINATO"): "confirmed",
                     ("c2", "D-COMBINATO"): "confirmed"}                       # un file con piu' buste non e' ambiguita'
    assert esito["drive_file_id_da_verificare"] == 1                          # c1: piu' file, nessun originale deciso
    assert esito["drive_file_id_da_scrivere"] == 1                            # c2: un solo file
    assert "drive_file_id" not in _run(db["cedolini"].find_one({"id": "c1"}))
    assert _run(db["cedolini"].find_one({"id": "c2"}))["drive_file_id"] == "D-COMBINATO"


def test_drive_file_id_gia_scritto_non_si_sovrascrive():
    db = _db("drv-ced-gia")
    _reg(db, "D-NUOVO", SHA_A)
    _busta(db, "c1", drive_file_id="D-VECCHIO", source_file_hash=SHA_A)
    esito = _run(doc.esegui(db, dry_run=False, protocollo=[]))
    assert _run(db["cedolini"].find_one({"id": "c1"}))["drive_file_id"] == "D-VECCHIO"
    assert esito["cedolini_scritti"] == 0 and esito["drive_file_id_gia_scritto"] == 1
    # il campo vale e l'impronta non lo contraddice ne' lo affianca
    assert {x["target"]["id"] for x in _rel(db)} == {"D-VECCHIO"}


def test_copie_identiche_in_elaborate_il_creatore_e_quello_non_gia_presente():
    db = _db("drv-ced-creatore")
    _reg(db, "D-PRIMO", SHA_A, gia_presente=False)
    _reg(db, "D-COPIA", SHA_A, gia_presente=True)
    _busta(db, "c1", source_file_hash=SHA_A)
    _run(doc.esegui(db, dry_run=False, protocollo=[]))
    assert [(x["target"]["id"], x["status"]) for x in _rel(db)] == [("D-PRIMO", "confirmed")]
    assert _run(db["cedolini"].find_one({"id": "c1"}))["drive_file_id"] == "D-PRIMO"


def test_copie_identiche_senza_un_solo_creatore_sono_da_verificare_e_non_si_scrive():
    db = _db("drv-ced-ambiguo")
    _reg(db, "D-X", SHA_A, gia_presente=True)
    _reg(db, "D-Y", SHA_A, gia_presente=True)
    _busta(db, "c1", source_file_hash=SHA_A)
    esito = _run(doc.esegui(db, dry_run=False, protocollo=[]))
    r = _rel(db)
    assert {(x["target"]["id"], x["status"], x["provenance"]["motivo"]) for x in r} == {
        ("D-X", "pending", doc.MOTIVO_COPIE_IDENTICHE), ("D-Y", "pending", doc.MOTIVO_COPIE_IDENTICHE)}
    assert esito["cedolini_scritti"] == 0 and esito["impronte_su_piu_file_identici"] == 1
    assert "drive_file_id" not in _run(db["cedolini"].find_one({"id": "c1"}))


def test_solo_elaborate_e_originale_e_mai_per_nome():
    db = _db("drv-ced-cartelle")
    _reg(db, "D-ERRORE", SHA_A, cartella="ERRORI")
    _reg(db, "D-DOPPIONE", SHA_A, cartella="DOPPIONI")
    _busta(db, "c1", source_file_hash=SHA_A, filename="D-ERRORE.pdf")
    esito = _run(doc.esegui(db, dry_run=False, protocollo=[]))
    assert _rel(db) == [] and esito["per_fonte_dati"]["payslip"]["impronta_senza_file"] == 1


def test_md5_del_protocollo_resta_la_via_per_le_impronte_a_32_caratteri():
    db = _db("drv-ced-md5")
    _busta(db, "c1", source_file_hash=MD5_1)
    _busta(db, "c2", source_file_hash=MD5_2)
    protocollo = [{"drive_id": "D-P1", "md5": MD5_1, "collegamento_tipo": None, "collegamento_id": None}]
    esito = _run(doc.esegui(db, dry_run=False, protocollo=protocollo))
    assert [(x["source"]["id"], x["target"]["id"], x["rule"]) for x in _rel(db)] == [("c1", "D-P1", "impronta_md5")]
    assert esito["cedolini_scritti"] == 1
    assert _run(db["cedolini"].find_one({"id": "c1"}))["drive_file_id"] == "D-P1"


# ── relazioni: estratti, inbox, ricevute ─────────────────────────────────────

def test_bonifici_ricevute_estratti_per_impronta_e_la_chiave_deve_esistere():
    db = _db("drv-altri")
    for d, sha in (("D-BON", SHA_A), ("D-PAGOPA", SHA_B), ("D-EC", SHA_C), ("D-NEXI", SHA_D)):
        _reg(db, d, sha)
    _ins(db, "bonifici_transfers", _id="b1", id="b1", document_hash=SHA_A)
    _ins(db, "bonifici_transfers", _id="b2", id="b2")                                   # senza impronta: niente
    _ins(db, "ricevute_pagopa", _id="p1", id="p1", pdf_hash=SHA_B)
    _ins(db, "estratti_conto_originali", _id="e1", id="e1", blob_key="estratto-originale:" + SHA_C)
    _ins(db, "estratto_conto_nexi", _id="n1", id="n1", content_sha256=SHA_D)
    _ins(db, "estratto_conto_nexi", _id="n2", id="n2", content_sha256="e" * 64)         # file non nel registro
    esito = _run(doc.esegui(db, dry_run=False, protocollo=[]))
    attese = {("bonifico_pdf", "b1", "D-BON"), ("pagopa_receipt", "p1", "D-PAGOPA"),
              ("estratto_conto_originale", "e1", "D-EC"), ("estratto_conto_nexi", "n1", "D-NEXI")}
    assert {(x["source"]["type"], x["source"]["id"], x["target"]["id"]) for x in _rel(db)} == attese
    assert all(x["status"] == "confirmed" and x["rule"] == "impronta_sha256" for x in _rel(db))
    assert esito["per_fonte_dati"]["estratto_conto_nexi"]["impronta_senza_file"] == 1
    assert _run(doc.esegui(db, dry_run=False, protocollo=[]))["nuove"] == 0


def test_inbox_con_drive_file_id_vale_quello_e_l_impronta_non_lo_affianca():
    db = _db("drv-inbox")
    _reg(db, "D-REG", SHA_A)
    _ins(db, "documents_inbox", _id="i1", id="i1", drive_file_id="D-SUO", sha256=SHA_A)     # il campo vince
    _ins(db, "documents_inbox", _id="i2", id="i2", sha256=SHA_A)                               # solo impronta
    _ins(db, "documents_inbox", _id="i3", id="i3", file_hash=MD5_3)                            # MD5 non nel protocollo
    _run(doc.esegui(db, dry_run=False, protocollo=[]))
    assert {(x["source"]["id"], x["target"]["id"]) for x in _rel(db)} == {("i1", "D-SUO"), ("i2", "D-REG")}
    assert all(x["source"]["type"] == "inbox_document" for x in _rel(db))


def test_impronta_su_file_condiviso_fra_ricevute_non_e_ambiguita():
    db = _db("drv-combinato")
    _reg(db, "D-DISTINTA", SHA_A)
    _ins(db, "bonifici_transfers", _id="b1", id="b1", document_hash=SHA_A)
    _ins(db, "bonifici_transfers", _id="b2", id="b2", document_hash=SHA_A)
    _run(doc.esegui(db, dry_run=False, protocollo=[]))
    assert {x["status"] for x in _rel(db)} == {"confirmed"} and len(_rel(db)) == 2


# ── relazioni: quietanze, copie attestate e HR ───────────────────────────────

def test_quietanza_con_copia_attestata_dalle_occorrenze_non_e_ambigua():
    db = _db("drv-quietanza")
    _ins(db, "quietanze_f24", _id="q1", id="q1", drive_file_id="D-Q1", pdf_hash=MD5_1,
         source_occurrences=[{"md5": MD5_1, "source": "drive"}, {"md5": MD5_2, "source": "posta"}])
    protocollo = [{"drive_id": "D-Q1", "md5": MD5_1, "collegamento_tipo": "quietanze_f24", "collegamento_id": "q1"},
                  {"drive_id": "D-Q1-COPIA", "md5": MD5_2, "collegamento_tipo": None, "collegamento_id": None}]
    esito = _run(doc.esegui(db, dry_run=False, protocollo=protocollo))
    stati = {(x["source"]["id"], x["target"]["id"]): (x["status"], x["rule"]) for x in _rel(db)}
    assert stati == {("q1", "D-Q1"): ("confirmed", "drive_file_id"), ("q1", "D-Q1-COPIA"): ("confirmed", "occorrenza")}
    assert esito["da_verificare"] == 0


def test_quietanza_senza_drive_file_id_si_aggancia_con_la_sua_impronta_md5():
    db = _db("drv-quietanza-md5")
    _ins(db, "quietanze_f24", _id="q1", id="q1", pdf_hash=MD5_1)
    protocollo = [{"drive_id": "D-Q", "md5": MD5_1, "collegamento_tipo": None, "collegamento_id": None}]
    _run(doc.esegui(db, dry_run=False, protocollo=protocollo))
    assert [(x["source"]["id"], x["target"]["id"], x["rule"]) for x in _rel(db)] == [("q1", "D-Q", "impronta_md5")]


def test_hr_verificata_contro_l_archivio_hr_e_le_orfane_si_contano():
    db = _db("drv-hr")
    protocollo = [
        {"drive_id": "D1", "md5": MD5_1, "collegamento_tipo": "hr_cedolino", "collegamento_id": "uuid-vivo"},
        {"drive_id": "D2", "md5": MD5_2, "collegamento_tipo": "hr_cedolino", "collegamento_id": "uuid-orfano"},
        {"drive_id": "D3", "md5": MD5_3, "collegamento_tipo": "hr_bonifico", "collegamento_id": "uuid-bon-orfano"},
    ]

    async def _hr():
        return {"hr_payslip": {"uuid-vivo"}, "hr_bonifico": set()}

    esito = _run(doc.esegui(db, protocollo=protocollo, leggi_hr=_hr))
    assert esito["hr"] == "verificato" and esito["previste"] == 1
    assert esito["collegamenti_non_mappati"] == {"hr_cedolino:entita_assente": 1, "hr_bonifico:entita_assente": 1}

    async def _hr_giu():
        return None

    senza = _run(doc.esegui(db, protocollo=protocollo, leggi_hr=_hr_giu))
    assert senza["hr"] == "non_verificato" and senza["previste"] == 3      # non si scarta cio' che non si e' potuto verificare


# ── i collegamenti del protocollo verso entita' sparite ──────────────────────

class _Conn:
    def __init__(self, righe):
        self.righe, self.chiamate = righe, []

    async def execute(self, sql, drive_id, tipo, nuovo, vecchio):
        self.chiamate.append((drive_id, tipo, nuovo, vecchio))
        n = 0
        for r in self.righe:
            if r["drive_id"] == drive_id and r["collegamento_tipo"] == tipo and r["collegamento_id"] == vecchio:
                r["collegamento_id"] = nuovo
                n += 1
        return f"UPDATE {n}"

    async def close(self):
        pass


def _scenario_orfani():
    db = _db("drv-orfani")
    _ins(db, "quietanze_f24", _id="q-vivo", id="q-vivo", drive_file_id="D-Q", pdf_hash=MD5_3,
         source_occurrences=[{"md5": MD5_1, "source": "drive"}])                      # ha assorbito la copia MD5_1
    _ins(db, "quietanze_f24", _id="q-a", id="q-a", source_occurrences=[{"md5": MD5_2, "source": "drive"}])
    _ins(db, "quietanze_f24", _id="q-b", id="q-b", source_occurrences=[{"md5": MD5_2, "source": "posta"}])
    _ins(db, "quietanze_f24", _id="q-quarantena", id="q-quarantena", status="eliminato", doppione_di="q-vivo")
    righe = [
        {"drive_id": "D-ORF1", "md5": MD5_1, "collegamento_tipo": "quietanze_f24", "collegamento_id": "q-sparita"},
        {"drive_id": "D-ORF2", "md5": MD5_2, "collegamento_tipo": "quietanze_f24", "collegamento_id": "q-sparita-2"},
        {"drive_id": "D-ORF3", "md5": "9" * 32, "collegamento_tipo": "quietanze_f24", "collegamento_id": "q-sparita-3"},
        {"drive_id": "D-ORF4", "md5": "8" * 32, "collegamento_tipo": "quietanze_f24", "collegamento_id": "q-quarantena"},
        {"drive_id": "D-OK", "md5": MD5_3, "collegamento_tipo": "quietanze_f24", "collegamento_id": "q-vivo"},
    ]
    return db, righe


def test_orfani_anteprima_motivo_e_nessuna_scrittura():
    db, righe = _scenario_orfani()
    conn = _Conn(righe)
    esito = _run(coll.esegui(db, protocollo=righe, conn=conn))
    assert esito["dry_run"] is True and esito["applicati"] == 0 and conn.chiamate == []
    assert esito["collegamenti_controllati"] == 5 and esito["vivi"] == 1 and esito["orfani"] == 4
    assert esito["id_scomparso"] == 3 and esito["id_ancora_presente_ma_fuori"] == 1
    assert esito["riagganciabili"] == 2 and esito["riagganciabili_md5_occorrenza"] == 1 and esito["riagganciabili_doppione_di"] == 1
    assert esito["ambigui"] == 1 and esito["senza_entita"] == 1
    assert esito["ambigui_elenco"][0]["candidati"] == ["q-a", "q-b"]       # due entita' con lo stesso file: nessuna scelta
    assert esito["senza_entita_elenco"][0]["drive_id"] == "D-ORF3"
    assert {(v["drive_id"], v["id_nuovo"]) for v in esito["esempi_riagganci"]} == {("D-ORF1", "q-vivo"), ("D-ORF4", "q-vivo")}


def test_orfani_riaggancio_per_id_solo_dove_certo_e_secondo_giro_zero():
    db, righe = _scenario_orfani()
    conn = _Conn(righe)
    primo = _run(coll.esegui(db, dry_run=False, protocollo=righe, conn=conn))
    assert primo["applicati"] == 2
    assert sorted(conn.chiamate) == [("D-ORF1", "quietanze_f24", "q-vivo", "q-sparita"),
                                     ("D-ORF4", "quietanze_f24", "q-vivo", "q-quarantena")]
    assert {r["drive_id"]: r["collegamento_id"] for r in righe}["D-ORF2"] == "q-sparita-2"   # ambiguo: intatto
    secondo = _run(coll.esegui(db, dry_run=False, protocollo=righe, conn=conn))
    assert secondo["applicati"] == 0 and secondo["riagganciabili"] == 0 and len(conn.chiamate) == 2


def test_riaggancio_non_scrive_se_il_collegamento_nel_frattempo_e_cambiato():
    db, righe = _scenario_orfani()
    conn = _Conn(righe)
    righe[0]["collegamento_id"] = "q-altro"                 # un altro processo l'ha gia' cambiato dopo la lettura

    letti = [dict(r) for r in righe]
    letti[0]["collegamento_id"] = "q-sparita"
    esito = _run(coll.esegui(db, dry_run=False, protocollo=letti, conn=conn))
    assert esito["applicati"] == 1                           # solo D-ORF4: la guardia sul vecchio id ha fermato D-ORF1
    assert righe[0]["collegamento_id"] == "q-altro"


def test_protocollo_non_raggiungibile_si_dichiara():
    db = _db("drv-orfani-vuoto")

    async def _nessuno():
        return None

    from app.services import relazioni_documentali as rd
    orig = rd.leggi_protocollo
    rd.leggi_protocollo = _nessuno
    try:
        assert _run(coll.esegui(db)) == {"dry_run": True, "protocollo": "non_disponibile"}
    finally:
        rd.leggi_protocollo = orig


# ── indice: filtro per documento ─────────────────────────────────────────────

def test_indice_filtra_per_documento_e_mostra_regola_e_motivo():
    db = _db("drv-indice")
    _reg(db, "D-A", SHA_A)
    _reg(db, "D-B", SHA_B, gia_presente=True)
    _reg(db, "D-B2", SHA_B, gia_presente=True)
    _ins(db, "bonifici_transfers", _id="b1", id="b1", document_hash=SHA_A)
    _ins(db, "bonifici_transfers", _id="b2", id="b2", document_hash=SHA_B)
    _run(doc.esegui(db, dry_run=False, protocollo=[]))
    righe = _run(indice.leggi_righe(db, indice.costruisci_filtro(documento="D-A")))["righe"]
    assert [(r["origine_id"], r["destinazione_id"], r["stato"], r["regola"]) for r in righe] == [
        ("b1", "D-A", "CONFERMATA", "impronta_sha256")]
    tutte = _run(indice.leggi_righe(db))["righe"]
    riep = indice.riepilogo(tutte)
    assert riep["per_regola"] == {"impronta_sha256": 3}
    assert riep["per_motivo"] == {doc.MOTIVO_COPIE_IDENTICHE: 2}
    da_ver = _run(indice.leggi_righe(db, indice.costruisci_filtro(documento="D-B2", stato="DA_VERIFICARE")))["righe"]
    assert [r["motivo"] for r in da_ver] == [doc.MOTIVO_COPIE_IDENTICHE]


def test_endpoint_indice_documento_e_bonifica_collegamenti_solo_admin(monkeypatch):
    from app.database import Database
    from app.routers import indice_relazionale as router
    from app.utils.dependencies import get_current_admin_user

    db = _db("drv-endpoint")
    _reg(db, "D-A", SHA_A)
    _ins(db, "bonifici_transfers", _id="b1", id="b1", document_hash=SHA_A)
    _run(doc.esegui(db, dry_run=False, protocollo=[]))
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(router, "_job_task", None)
    monkeypatch.setattr(router, "_job_collegamenti", None)

    async def _protocollo():
        return []

    monkeypatch.setattr(doc, "leggi_protocollo", _protocollo)
    app = FastAPI()
    app.include_router(router.router, prefix="/api/indice-relazionale")
    app.dependency_overrides[get_current_admin_user] = lambda: {"sub": "a", "role": "admin"}
    with TestClient(app) as client:
        elenco = client.get("/api/indice-relazionale", params={"documento": "D-A"}).json()
        assert [r["origine_id"] for r in elenco["righe"]] == ["b1"]
        assert client.get("/api/indice-relazionale/export", params={"documento": "D-A", "formato": "json"}).status_code == 200
        assert client.post("/api/indice-relazionale/protocollo-collegamenti/bonifica").json()["dry_run"] is True
        for _ in range(200):
            stato = client.get("/api/indice-relazionale/protocollo-collegamenti/stato").json()
            if stato.get("stato") == "completato" and stato.get("esito"):
                break
        assert stato["esito"]["dry_run"] is True and stato["esito"]["applicati"] == 0
    for rotta in router.router.routes:
        assert any(d.call is get_current_admin_user for d in rotta.dependant.dependencies), rotta.path
