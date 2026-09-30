"""MINI-07: protocollo personale e familiare. Solo dati sintetici.

Import idempotente e per intestazione, numero immutabile, ricerca AND con
snippet, stato «rimosso» (mai cancellato), ponte informativo senza scritture.
"""
import asyncio
import hashlib
import io
from datetime import date

import pytest
from fastapi import FastAPI
from openpyxl import Workbook

from app.router_registry import register_all_routers
from app.services import protocollo_personale as pp
from app.services.archivio_documenti_memoria import ArchivioDocumenti
from app.utils.dependencies import get_current_admin_user
from tests.route_table import elenco_route

INTESTAZIONE = ["N_PROTOCOLLO", "DATA_PROTOCOLLO", "TIPO_CORRISPONDENZA", "TIPO_DOCUMENTO", "DATA_DOCUMENTO",
                "ENTRATA_USCITA", "OGGETTO", "MITTENTE_DESTINATARIO", "PRATICA", "IMPORTO", "NOTE",
                "NOME_FILE", "IMPRONTA_SHA256", "LINK"]


def sha(testo: str) -> str:
    return hashlib.sha256(testo.encode()).hexdigest()


def riga(numero, oggetto, *, data="2023-05-10", tipo="Comunicazione", nome="doc.pdf", impronta=None,
         importo="N/A", pratica="N/A", controparte="N/D", note=None, link="Apri"):
    return [numero, data, "Cartaceo / Scansione", tipo, data, "Entrata", oggetto, controparte, pratica, importo,
            note, nome, impronta or sha(nome + numero), link]


RIGHE = [
    riga("2023/000001", "TARI 2023 avviso di pagamento intestato a Enzo Rossi", nome="tari_enzo.pdf", tipo="Tributi",
         importo="123,45"),
    riga("2023/000002", "TARI 2023 avviso intestato a Maria Bianchi", nome="tari_maria.pdf", tipo="Tributi"),
    riga("2019/000007", "Canone COSAP occupazione suolo pubblico anno 2019", data="2019-03-01", nome="cosap.pdf",
         tipo="Tributi"),
    riga("2021/000003", "Verbale codice della strada, veicolo targa AB123CD, città di Napoli", data="2021-07-20",
         nome="verbale.pdf", tipo="Verbale"),
    riga("2022/000004", "Cartella di pagamento esattoriale n. 071 2022 0001234", data="2022-11-02",
         nome="cartella.pdf", tipo="Cartella"),
]


def xlsx(righe=RIGHE, intestazione=INTESTAZIONE, foglio="REGISTRO_PROTOCOLLO") -> bytes:
    cartella = Workbook()
    ws = cartella.active
    ws.title = foglio
    ws.append(intestazione)
    for r in righe:
        ws.append(r)
    buffer = io.BytesIO()
    cartella.save(buffer)
    return buffer.getvalue()


def run(coro):
    return asyncio.run(coro)


def caricato(righe=RIGHE):
    db = ArchivioDocumenti()
    run(pp.importa_registro(db, xlsx(righe), dry_run=False))
    return db


def numeri(esito):
    return [r["numero"] for r in esito["righe"]]


# ── import ───────────────────────────────────────────────────────────────────

def test_dry_run_e_il_predefinito_e_non_scrive():
    db = ArchivioDocumenti()
    esito = run(pp.importa_registro(db, xlsx()))
    assert esito["dry_run"] is True and esito["nuovi"] == 5
    assert run(db[pp.COLL].find({}).to_list(None)) == []


def test_import_idempotente_secondo_giro_nuovi_zero():
    db = ArchivioDocumenti()
    primo = run(pp.importa_registro(db, xlsx(), dry_run=False))
    secondo = run(pp.importa_registro(db, xlsx(), dry_run=False))
    assert primo["nuovi"] == 5
    assert (secondo["nuovi"], secondo["aggiornati"], secondo["invariati"]) == (0, 0, 5)
    assert len(run(db[pp.COLL].find({}).to_list(None))) == 5


def test_lettura_per_intestazione_non_per_posizione():
    ordine = list(reversed(range(len(INTESTAZIONE))))
    invertita = [INTESTAZIONE[i] for i in ordine]
    righe = [[r[i] for i in ordine] for r in RIGHE]
    letto = pp.leggi_registro_xlsx(xlsx(righe, invertita))
    assert {r["numero"] for r in letto["righe"]} == {r[0] for r in RIGHE}
    tari = next(r for r in letto["righe"] if r["numero"] == "2023/000001")
    assert tari["importo"] == "123.45" and tari["valuta"] == "EUR" and tari["data_protocollo"] == "2023-05-10"


def test_colonna_obbligatoria_assente_e_errore_col_nome():
    senza = [c for c in INTESTAZIONE if c != "NOME_FILE"]
    righe = [[v for c, v in zip(INTESTAZIONE, r) if c != "NOME_FILE"] for r in RIGHE]
    with pytest.raises(pp.RegistroNonValido) as errore:
        pp.leggi_registro_xlsx(xlsx(righe, senza))
    assert errore.value.codice == "COLONNE_ASSENTI" and errore.value.dettagli["mancanti"] == ["nome_file"]
    with pytest.raises(pp.RegistroNonValido) as errore:
        pp.leggi_registro_xlsx(xlsx(foglio="ALTRO"))
    assert errore.value.codice == "FOGLIO_ASSENTE"


def test_importo_decimal_e_date_gg_mm_aaaa():
    assert str(pp.importo_decimal("1.234,50")) == "1234.50"
    assert pp.importo_decimal("N/A") is None and pp.importo_decimal("boh") is None
    assert str(pp.importo_decimal(0.1)) == "0.10"
    assert pp.data_iso("31/12/2023") == "2023-12-31" and pp.data_iso(date(2020, 2, 3)) == "2020-02-03"
    assert pp.data_iso("31/02/2023") is None  # mai una data inventata


def test_righe_non_valide_e_ripetute_sono_scartate_senza_contenuto():
    righe = [riga("2023/000001", "uno"), riga("2023/1", "uno", nome="x.pdf"), riga("boh", "due"),
             riga("2024/000009", "tre", impronta="zz")]
    letto = pp.leggi_registro_xlsx(xlsx(righe))
    motivi = sorted(s["motivo"] for s in letto["scartate"])
    assert motivi == ["numero_non_valido", "numero_ripetuto_diverso", "sha256_non_valido"]
    assert all(set(s) <= {"riga_excel", "motivo", "numero"} for s in letto["scartate"])
    assert [r["numero"] for r in letto["righe"]] == ["2023/000001"]


def test_numero_immutabile_altro_sha_va_in_conflitto_e_non_si_tocca():
    db = caricato()
    cambiata = [list(r) for r in RIGHE]
    cambiata[0][12] = sha("altro file")
    cambiata[0][6] = "oggetto riscritto"
    esito = run(pp.importa_registro(db, xlsx(cambiata), dry_run=False))
    assert esito["in_conflitto"] == 1 and esito["elenco_in_conflitto"] == ["2023/000001"]
    attuale = run(db[pp.COLL].find_one({"id": "2023/000001"}))
    assert attuale["sha256"] == sha("tari_enzo.pdf2023/000001") and "riscritto" not in attuale["oggetto"]


def test_stesso_numero_stessa_impronta_con_note_nuove_si_aggiorna():
    db = caricato()
    cambiata = [list(r) for r in RIGHE]
    cambiata[2][10] = "nota nuova"
    esito = run(pp.importa_registro(db, xlsx(cambiata), dry_run=False))
    assert (esito["nuovi"], esito["aggiornati"]) == (0, 1)
    assert run(db[pp.COLL].find_one({"id": "2019/000007"}))["note"] == "nota nuova"


def test_riga_sparita_dal_foglio_non_si_rimuove_solo_si_segnala():
    db = caricato()
    esito = run(pp.importa_registro(db, xlsx(RIGHE[:3]), dry_run=False))
    assert esito["assenti_nel_file"] == 2
    assert len(run(db[pp.COLL].find({"stato": "attivo"}).to_list(None))) == 5


# ── ricerca ──────────────────────────────────────────────────────────────────

def test_ricerca_tari_enzo_2023_e_and():
    db = caricato()
    esito = run(pp.cerca(db, q="tari enzo 2023"))
    assert numeri(esito) == ["2023/000001"]
    assert numeri(run(pp.cerca(db, q="tari 2023")))  # le due TARI
    assert sorted(numeri(run(pp.cerca(db, q="tari 2023")))) == ["2023/000001", "2023/000002"]
    assert numeri(run(pp.cerca(db, q="tari enzo 2019"))) == []


def test_ricerca_cosap_2019_verbale_targa_cartella():
    db = caricato()
    assert numeri(run(pp.cerca(db, q="cosap 2019"))) == ["2019/000007"]
    assert numeri(run(pp.cerca(db, q="verbale"))) == ["2021/000003"]
    assert numeri(run(pp.cerca(db, q="ab123cd"))) == ["2021/000003"]
    assert numeri(run(pp.cerca(db, q="AB 123 CD"))) == ["2021/000003"]  # targa con spazi
    assert numeri(run(pp.cerca(db, q="cartella pagamento"))) == ["2022/000004"]


def test_ricerca_senza_accenti_e_maiuscole_e_data_gg_mm_aaaa():
    db = caricato()
    assert numeri(run(pp.cerca(db, q="CITTA napoli"))) == ["2021/000003"]  # «città»
    assert numeri(run(pp.cerca(db, q="città"))) == ["2021/000003"]
    assert numeri(run(pp.cerca(db, q="20/07/2021"))) == ["2021/000003"]


def test_filtro_anno_e_piu_recenti_per_primi():
    db = caricato()
    assert numeri(run(pp.cerca(db, anno=2019))) == ["2019/000007"]
    assert numeri(run(pp.cerca(db)))[0] == "2023/000002"  # numero piu' alto a parita' di data
    assert numeri(run(pp.cerca(db)))[-1] == "2019/000007"


def test_snippet_a_segmenti_con_parole_evidenziate_senza_html():
    db = caricato()
    riga_ = run(pp.cerca(db, q="cosap suolo"))["righe"][0]
    assert riga_["snippet"]
    evidenziate = [s["t"].lower() for s in riga_["snippet"] if s["hit"]]
    assert evidenziate == ["cosap", "suolo"]
    assert "".join(s["t"] for s in riga_["snippet"]).startswith("Canone")
    # l'accento non sposta l'evidenziazione: lunghezza invariata dalla normalizzazione
    accento = run(pp.cerca(db, q="citta"))["righe"][0]["snippet"]
    assert [s["t"] for s in accento if s["hit"]] == ["città"]
    assert run(pp.cerca(db))["righe"][0]["snippet"] is None


def test_paginazione_con_tetto_200_e_niente_payload_nell_elenco():
    db = caricato()
    run(db[pp.COLL].update_one({"id": "2019/000007"}, {"$set": {"testo_ocr": "testo lungo riservato"}}))
    esito = run(pp.cerca(db, limit=2, offset=1))
    assert esito["totale"] == 5 and len(esito["righe"]) == 2
    assert run(pp.cerca(db, limit=9999))["limit"] == 200
    assert all("testo_ocr" not in r and "testo_indice" not in r for r in run(pp.cerca(db))["righe"])


# ── rimozione (mai cancellazione) ────────────────────────────────────────────

def test_stato_rimosso_resta_in_archivio_fuori_dalla_ricerca_e_l_import_non_lo_riattiva():
    db = caricato()
    assert run(pp.segna_rimosso(db, "2019/7", "duplicato di carta", attore="admin"))["success"]
    assert numeri(run(pp.cerca(db, q="cosap"))) == []
    assert numeri(run(pp.cerca(db, q="cosap", includi_rimossi=True))) == ["2019/000007"]
    riga_ = run(db[pp.COLL].find_one({"id": "2019/000007"}))
    assert riga_["stato"] == "rimosso" and riga_["rimosso_motivo"] == "duplicato di carta" and riga_["rimosso_da"] == "admin"
    esito = run(pp.importa_registro(db, xlsx(), dry_run=False))
    assert (esito["nuovi"], esito["rimossi_saltati"]) == (0, 1)
    assert run(db[pp.COLL].find_one({"id": "2019/000007"}))["stato"] == "rimosso"
    assert run(pp.segna_rimosso(db, "2019/7", "ancora", attore="admin"))["code"] == "NON_TROVATO"
    assert run(pp.segna_rimosso(db, "2019/7", "", attore="admin"))["code"] == "DATI_NON_VALIDI"
    assert run(pp.ripristina(db, "2019/000007", attore="admin"))["success"]
    assert numeri(run(pp.cerca(db, q="cosap"))) == ["2019/000007"]
    assert len(run(db[pp.COLL].find({}).to_list(None))) == 5  # niente cancellato


# ── ponte informativo ────────────────────────────────────────────────────────

class _DbSoloLettura(ArchivioDocumenti):
    """Archivio che fallisce a qualunque scrittura durante il ponte."""

    bloccato = False

    def __getitem__(self, nome):
        collezione = super().__getitem__(nome)
        if not self.bloccato:
            return collezione
        db = self

        class Guardia:
            def __getattr__(self, attributo):
                if attributo in ("insert_one", "insert_many", "update_one", "update_many", "delete_one",
                                 "delete_many", "replace_one", "bulk_write", "find_one_and_update"):
                    raise AssertionError(f"scrittura vietata su {nome}.{attributo}")
                return getattr(collezione, attributo)

        return Guardia()


def test_ponte_mostra_i_documenti_collegati_e_non_scrive_niente():
    db = _DbSoloLettura()
    impronta = sha("cartella.pdf2022/000004")
    run(pp.importa_registro(db, xlsx(), dry_run=False))
    run(db["cartelle_pagamento"].insert_one({"id": "cart-1", "sha256": impronta}))
    run(db["ricevute_pagopa"].insert_one({"id": "rec-1", "pdf_hash": impronta}))
    run(db["invoices"].insert_one({"id": "fatt-1", "invoice_number": "1", "total_amount": 10}))
    prima = {c: run(db[c].find({}).to_list(None)) for c in ("cartelle_pagamento", "ricevute_pagopa", "invoices",
                                                           "prima_nota", "movimenti_contabili", "entity_relations")}
    db.bloccato = True
    dettaglio = run(pp.dettaglio(db, "2022/000004"))
    db.bloccato = False
    collegati = dettaglio["collegati"]
    assert collegati["sola_lettura"] is True
    assert {(d["tipo"], d["id"]) for d in collegati["documenti"]} == {
        ("cartella_pagamento", "cart-1"), ("ricevuta_pagopa", "rec-1")}
    dopo = {c: run(db[c].find({}).to_list(None)) for c in prima}
    assert dopo == prima  # nessuna relazione, scrittura contabile o pagamento nato dal ponte
    # rimanda alla sezione che esiste gia', senza riportare i dati del documento
    assert {d["rotta"] for d in collegati["documenti"]} == {"/riconciliazione/pagopa"}
    assert all(set(d) <= {"tipo", "collezione", "id", "rotta", "via", "stato"} for d in collegati["documenti"])


def test_ponte_rimanda_a_tributi_verbali_atti_archivio_esistenti():
    db = ArchivioDocumenti()
    righe = [riga(f"2024/00000{i}", "doc", impronta=sha(f"f{i}"), nome=f"f{i}.pdf") for i in range(1, 5)]
    run(pp.importa_registro(db, xlsx(righe), dry_run=False))
    run(db["quietanze_f24"].insert_one({"id": "q-1", "pdf_hash": sha("f1")}))
    run(db["verbali_noleggio"].insert_one({"id": "v-1", "numero_verbale": "AB/123", "source_sha256": sha("f2")}))
    run(db["atti_giudiziari"].insert_one({"id": sha("f3")}))
    run(db["documents_inbox"].insert_one({"id": "d-1", "sha256": sha("f4")}))
    rotte = {}
    for n in range(1, 5):
        for d in run(pp.dettaglio(db, f"2024/{n}"))["collegati"]["documenti"]:
            rotte[d["tipo"]] = d["rotta"]
    assert rotte == {"tributo_pagato": "/tributi", "verbale": "/verbali-noleggio/AB/123",
                     "atto_giudiziario": "/prima-nota", "documento_archivio": "/documenti/archivio"}


def test_riga_familiare_resta_fuori_dalla_contabilita_end_to_end():
    from app.services.personal_family_registry import FAMILY_PROFILES

    nome = next(iter(FAMILY_PROFILES.values()))["display_name"]
    db = ArchivioDocumenti()
    righe = [riga("2023/000001", f"TARI 2023 intestata a {nome}", nome="tari.pdf", importo="88,00")]
    run(pp.importa_registro(db, xlsx(righe), dry_run=False))
    salvata = run(db[pp.COLL].find_one({"id": "2023/000001"}))
    assert salvata["ambito"] == "personale_familiare" and salvata["accounting_excluded"] is True
    run(pp.cerca(db, q="tari"))
    run(pp.dettaglio(db, "2023/1"))
    contabili = ("prima_nota", "prima_nota_banca", "prima_nota_cassa", "movimenti_contabili", "scritture_contabili",
                 "invoices", "alerts", "scadenziario_fornitori", "partite_aperte", "attese", "entity_relations",
                 "estratto_conto_movimenti", "pagamenti")
    for collezione in contabili:
        assert run(db[collezione].find({}).to_list(None)) == [], collezione


def test_nessun_modulo_contabile_legge_il_protocollo_personale():
    from pathlib import Path

    radice = Path(__file__).resolve().parents[2] / "app"
    lettori = {p.relative_to(radice).as_posix() for p in radice.rglob("*.py")
               if "protocollo_personale" in p.read_text(encoding="utf-8", errors="ignore")}
    assert lettori == {"services/protocollo_personale.py", "routers/protocollo_personale.py",
                       "document_repository.py", "router_registry.py"}


def test_ponte_legge_le_relazioni_documentali_senza_crearne():
    from app.services.entity_relations import upsert_entity_relation

    db = _DbSoloLettura()
    link = "https://drive.google.com/file/d/FILEID1234567890/view"
    righe = [list(r) for r in RIGHE]
    righe[4][13] = link
    run(pp.importa_registro(db, xlsx(righe), dry_run=False))
    assert run(db[pp.COLL].find_one({"id": "2022/000004"}))["drive_file_id"] == "FILEID1234567890"
    run(upsert_entity_relation(db, source_type="invoice", source_id="fatt-9", relation_type="has_source_document",
                               target_type="documento", target_id="FILEID1234567890", status="confirmed",
                               rule="test"))
    db.bloccato = True
    collegati = run(pp.dettaglio(db, "2022/000004"))["collegati"]
    db.bloccato = False
    assert [(d["tipo"], d["id"], d["via"]) for d in collegati["documenti"]] == [("invoice", "fatt-9", "entity_relations")]
    assert len(run(db["entity_relations"].find({}).to_list(None))) == 1


def test_riga_senza_impronta_ne_link_non_ha_collegati():
    db = caricato()
    riga_ = run(db[pp.COLL].find_one({"id": "2023/000002"}))
    riga_["sha256"] = None
    assert run(pp.documenti_collegati(db, riga_))["documenti"] == []


# ── testo del PDF ────────────────────────────────────────────────────────────

def test_testo_pdf_si_aggancia_solo_se_l_impronta_e_quella_registrata():
    db = ArchivioDocumenti()
    pdf = b"%PDF-1.4 non e' un pdf vero"
    righe = [riga("2020/000001", "atto", impronta=hashlib.sha256(pdf).hexdigest())]
    run(pp.importa_registro(db, xlsx(righe), dry_run=False))
    assert run(pp.allega_testo_pdf(db, "2020/1", b"altro"))["code"] == "IMPRONTA_DIVERSA"
    assert run(pp.allega_testo_pdf(db, "2020/1", pdf))["code"] == "TESTO_ASSENTE"
    assert run(pp.allega_testo_pdf(db, "2099/1", pdf))["code"] == "NON_TROVATO"


# ── router ───────────────────────────────────────────────────────────────────

def test_endpoint_solo_admin():
    app = FastAPI()
    register_all_routers(app)
    route = [r for r in elenco_route(app) if "/api/protocollo-personale" in r.path]
    assert len(route) >= 8

    def dipendenze(dependant):
        trovate = set()
        for d in dependant.dependencies:
            if d.call:
                trovate.add(d.call)
            trovate |= dipendenze(d)
        return trovate

    assert all(get_current_admin_user in dipendenze(r.dependant) for r in route)
    assert not [r for r in route if "DELETE" in r.methods]
