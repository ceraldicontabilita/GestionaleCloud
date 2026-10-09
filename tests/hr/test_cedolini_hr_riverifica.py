"""Netti HR riletti dal PDF: si corregge solo con il netto verificato dalla cella.

Caso reale (28/09/2026): Dias, quattordicesima 2022, in HR 0,45 € dal vecchio
import; il lettore unico legge 675,00 € dal PDF salvato nella stessa riga.
"""
import asyncio
import base64
import json

from app.constants.stati_netto import NETTO_VERIFICATO_DA_CEDOLINO
from app.services import cedolini_hr_riverifica as rv

BUSTA_14 = {"codice_fiscale": "DSIMTH82R04Z209K", "anno": 2022, "mese": 7,
            "tipo_cedolino": "quattordicesima", "netto": 675.0,
            "stato_netto": NETTO_VERIFICATO_DA_CEDOLINO}
RIGA_14 = {"id": "r1", "cf": "dsimth82r04z209k", "anno": "2022", "mese": "14",
           "tipo": "quattordicesima", "netto": "0.45"}


def test_la_quattordicesima_si_ritrova_per_tipo_anche_col_mese_diverso():
    esito = rv.busta_della_riga(RIGA_14, [BUSTA_14])
    assert esito == {"esito": "ritrovata", "netto": rv._cent(675.0), "ratei": {},
                      "netto_calcolato": None}


def test_la_mensile_vuole_lo_stesso_mese():
    riga = {**RIGA_14, "tipo": "ordinario", "mese": "8"}
    busta = {**BUSTA_14, "tipo_cedolino": "mensile", "mese": 7}
    assert rv.busta_della_riga(riga, [busta])["esito"] == "non_ritrovata"
    assert rv.busta_della_riga({**riga, "mese": "7"}, [busta])["esito"] == "ritrovata"


def test_un_netto_non_verificato_non_corregge_niente():
    busta = {**BUSTA_14, "stato_netto": "MULTIPLE_NETS_DA_VERIFICARE"}
    esito = rv.busta_della_riga(RIGA_14, [busta])
    patch = rv.correzione(RIGA_14, esito, "2026-09-28")
    assert "netto" not in patch and patch["netto_riverifica_esito"] == "netto_non_verificato"


def test_due_buste_con_netti_diversi_restano_ambigue():
    esito = rv.busta_della_riga(RIGA_14, [BUSTA_14, {**BUSTA_14, "netto": 600.0}])
    assert esito["esito"] == "ambigua"


def test_la_correzione_lascia_il_valore_di_prima():
    patch = rv.correzione(RIGA_14, rv.busta_della_riga(RIGA_14, [BUSTA_14]), "2026-09-28T03:00")
    assert patch["netto"] == 675.0 and patch["netto_riverifica_esito"] == "corretto"
    assert patch["storico_netto_ultimo"]["prima"] == 0.45
    assert patch["netto_riverificato_versione"] == rv.VERSIONE


def test_un_netto_gia_giusto_si_conferma_senza_riscriverlo():
    riga = {**RIGA_14, "netto": "675"}
    patch = rv.correzione(riga, rv.busta_della_riga(riga, [BUSTA_14]), "x")
    assert patch["netto_riverifica_esito"] == "confermato" and "netto" not in patch


class _Con:
    """Connessione finta: una riga, il suo PDF e gli UPDATE registrati."""

    def __init__(self):
        self.doc = {"storico_netto": [{"prima": 1, "dopo": 2}]}
        self.aggiornamenti = []

    async def fetch(self, _sql, versione, lotto):
        return [] if self.aggiornamenti else [RIGA_14]

    async def fetchval(self, sql, _id):
        if "storico_netto" in sql:
            return json.dumps(self.doc["storico_netto"])
        return base64.b64encode(b"%PDF finto").decode()

    async def execute(self, _sql, riga_id, patch):
        self.aggiornamenti.append((riga_id, json.loads(patch)))


def test_il_lotto_corregge_accoda_lo_storico_e_poi_si_ferma(monkeypatch):
    from app.services import cedolini_motore

    monkeypatch.setattr(cedolini_motore, "leggi_pdf", lambda _pdf: {"buste": [BUSTA_14]})
    con = _Con()
    esito = asyncio.run(rv.riverifica_lotto(con))
    assert esito["conteggi"] == {"corretto": 1}
    [(riga_id, patch)] = con.aggiornamenti
    assert riga_id == "r1" and patch["netto"] == 675.0
    assert len(patch["storico_netto"]) == 2 and patch["storico_netto"][-1]["prima"] == 0.45
    assert asyncio.run(rv.riverifica_lotto(con))["lette"] == 0


def test_in_simulazione_non_si_scrive(monkeypatch):
    from app.services import cedolini_motore

    monkeypatch.setattr(cedolini_motore, "leggi_pdf", lambda _pdf: {"buste": [BUSTA_14]})
    con = _Con()
    assert asyncio.run(rv.riverifica_lotto(con, dry_run=True))["correzioni"][0]["dopo"] == 675.0
    assert con.aggiornamenti == []


# ── acconto recuperato: in HR il netto e' busta + acconto (titolare, 28/09/2026) ──

BUSTA_08 = {"codice_fiscale": "MSCMNL80A01F839X", "anno": 2025, "mese": 8,
            "tipo_cedolino": "mensile", "netto": 598.0, "stato_netto": NETTO_VERIFICATO_DA_CEDOLINO}
RIGA_08 = {"id": "r8", "cf": "MSCMNL80A01F839X", "anno": "2025", "mese": "8",
           "tipo": "ordinario", "netto": "1597.06", "acconto": "1000"}


def test_con_l_acconto_recuperato_il_netto_hr_non_si_riscrive_con_la_cella():
    patch = rv.correzione(RIGA_08, rv.busta_della_riga(RIGA_08, [BUSTA_08]), "x")
    assert patch["netto_riverifica_esito"] == "confermato_con_acconto"
    assert "netto" not in patch and patch["netto_busta"] == 598.0


def test_con_l_acconto_un_netto_sbagliato_diventa_busta_piu_acconto():
    riga = {**RIGA_08, "netto": "0.23"}
    patch = rv.correzione(riga, rv.busta_della_riga(riga, [BUSTA_08]), "x")
    assert patch["netto_riverifica_esito"] == "corretto" and patch["netto"] == 1598.0
    assert patch["netto_busta"] == 598.0 and patch["storico_netto_ultimo"]["prima"] == 0.23


# Caso di prova (dati inventati): cella del netto 1.500,00, competenze meno
# trattenute 2.500,00 (acconto di 1.000,00 recuperato), in HR 2.499,95. La riga
# HR non annota l'acconto: la v1 l'aveva «corretta» a 1.500,00.
BUSTA_ACCONTO = {"codice_fiscale": "RSSMRA80A01F839X", "anno": 2023, "mese": 1,
                 "tipo_cedolino": "mensile", "netto": 1500.0, "netto_calcolato": 2500.0,
                 "stato_netto": NETTO_VERIFICATO_DA_CEDOLINO}
RIGA_ACCONTO = {"id": "r2", "cf": "RSSMRA80A01F839X", "anno": "2023", "mese": "1",
                "tipo": "ordinario", "netto": "2499.95"}


def _patch(riga, busta):
    return rv.correzione(riga, rv.busta_della_riga(riga, [busta]), "2026-09-28T07:00")


def test_l_acconto_letto_dal_pdf_conferma_busta_piu_acconto():
    patch = _patch(RIGA_ACCONTO, BUSTA_ACCONTO)
    assert patch["netto_riverifica_esito"] == "confermato_con_acconto"
    assert "netto" not in patch and patch["netto_busta"] == 1500.0


def test_la_correzione_sbagliata_della_v1_si_ripristina():
    riga = {**RIGA_ACCONTO, "netto": "1500.0", "prima_v1": "2499.95", "fonte_ultima": rv.VERSIONE_V1}
    patch = _patch(riga, BUSTA_ACCONTO)
    assert patch["netto_riverifica_esito"] == "ripristinato" and patch["netto"] == 2499.95
    assert patch["storico_netto_ultimo"]["prima"] == 1500.0


def test_la_correzione_giusta_della_v1_resta_senza_riscrivere():
    riga = {**RIGA_14, "netto": "675.0", "prima_v1": "0.45", "fonte_ultima": rv.VERSIONE_V1}
    patch = _patch(riga, BUSTA_14)
    assert patch["netto_riverifica_esito"] == "corretto" and "netto" not in patch


def test_il_rateo_letto_dalla_busta_si_fonde_nei_dati_chiave_senza_perdere_il_resto():
    busta = {**BUSTA_14, "dati_chiave": {"rateo_13ma_presente": True, "rateo_13ma_importo": "60,27"}}
    riga = {**RIGA_14, "dati_chiave": {"acconto_recuperato_busta": "100,00"}}
    patch = rv.correzione(riga, rv.busta_della_riga(riga, [busta]), "x")
    assert patch["dati_chiave"] == {"acconto_recuperato_busta": "100,00",
                                    "rateo_13ma_presente": True, "rateo_13ma_importo": "60,27"}


def test_il_rateo_si_scrive_anche_se_il_netto_non_e_verificato():
    busta = {**BUSTA_14, "stato_netto": "MULTIPLE_NETS_DA_VERIFICARE",
             "dati_chiave": {"rateo_14ma_importo": "1.234,56", "rateo_14ma_presente": True}}
    patch = rv.correzione(RIGA_14, rv.busta_della_riga(RIGA_14, [busta]), "x")
    assert patch["dati_chiave"]["rateo_14ma_importo"] == "1.234,56" and "netto" not in patch
