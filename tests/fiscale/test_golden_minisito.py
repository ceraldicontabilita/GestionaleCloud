"""MINI-00: i dati di riferimento del Minisito fiscale (pacchetto del titolare su
Drive, cartella `MINISITO`, rigenerazione del 16/09/2026) vivono qui come golden
di regressione per i lettori (MINI-02), gli incroci (MINI-04) e i cedolini
(MINI-03/05).

- `manifest_final.json`: lato fiscale (212 quietanze F24 dedotte da 265, 23 LIPE,
  5 IVA annuali, 31 dichiarazioni, incroci mensili e alert), dati societari.
- `cedolini_canonici.json`: 1.378 periodi di 50 dipendenti con pseudonimi
  `DIP-nn`; tolti nomi, IBAN, causali, beneficiari e nomi file.

`protocollo_data` non è nel pacchetto: il protocollo personale (MINI-07) ha solo
il registro Excel su Drive.
"""
import json
import re
from pathlib import Path

CARTELLA = Path(__file__).parent / "golden_minisito"


def _carica(nome):
    return json.loads((CARTELLA / nome).read_text(encoding="utf-8"))


def test_manifest_finale_ha_le_sezioni_e_i_conteggi_del_pacchetto():
    m = _carica("manifest_final.json")
    raw = m["raw"]
    assert len(raw["f24"]) == 212 and len(raw["f24_duplicati_rimossi"]) == 53
    assert len(raw["lipe"]) == 23 and len(raw["iva"]) == 5 and len(raw["generic"]) == 31
    assert len(m["confronti_iva_mensile"]) == 63 and len(m["alerts"]) == 16
    assert len(m["codice_tributo_index"]) == 84 and m["file_corrotti"] == []
    # ogni quietanza ha righe tributo quadrate al centesimo; il protocollo manca
    # su due PDF del 2022 riparati (resta solo nel nome del file)
    senza_protocollo = []
    for q in raw["f24"]:
        assert q["tributi"], q["filename"]
        assert round(sum(t["debito"] for t in q["tributi"]), 2) == q["totale_debito"]
        if not q.get("protocollo"):
            senza_protocollo.append(q["filename"])
    assert len(senza_protocollo) == 2 and all("2022" in f for f in senza_protocollo)
    # la regola del minisito: un solo periodo per mese, dalla LIPE canonica
    periodi = [(c["anno"], c["mese"]) for c in m["confronti_iva_mensile"]]
    assert len(periodi) == len(set(periodi))
    assert {a["tipo"] for a in m["alerts"]} <= {
        "PAGAMENTO_MANCANTE_O_PARZIALE", "POSSIBILE_ERRORE_PERIODO_IMPUTAZIONE",
        "POSSIBILE_COMPENSAZIONE_6099", "IRAP_SALDO_MANCANTE_O_PARZIALE",
        "IVA_ANNUALE_SALDO_DA_VERIFICARE", "COMUNICAZIONE_54BIS_NON_PAGATA",
    }


def test_cedolini_golden_sono_anonimi():
    testo = (CARTELLA / "cedolini_canonici.json").read_text(encoding="utf-8")
    assert not re.search(r"IT\d{2}[A-Z]\d{22}", testo), "IBAN in chiaro"
    assert not re.search(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b", testo), "codice fiscale in chiaro"
    righe = _carica("cedolini_canonici.json")
    assert len(righe) == 1378
    dipendenti = {r["dipendente"] for r in righe}
    assert len(dipendenti) == 50 and all(re.fullmatch(r"DIP-\d{2}", d) for d in dipendenti)
    for chiave in ("descrizione", "beneficiario", "causale", "iban_beneficiario", "filename"):
        assert f'"{chiave}"' not in testo, chiave


def test_cedolini_golden_portano_gli_stati_del_minisito():
    righe = _carica("cedolini_canonici.json")
    assert {r["tipo"] for r in righe} == {"Ordinario", "Tredicesima", "Quattordicesima", "TFR"}
    assert {r["netto_fonte"] for r in righe} == {None, "diretto", "calcolato_da_totali", "non_letto_da_lul"}
    stati = {(r.get("riscontro") or {}).get("stato") for r in righe}
    assert stati == {None, "confermato", "da_verificare", "differenza", "nessun_bonifico_trovato", "non_riscontrabile"}
    # un netto non letto resta nullo, mai zero: sono i 97 cedolini estratti dai LUL
    da_lul = [r for r in righe if r["netto_fonte"] == "non_letto_da_lul"]
    assert da_lul and all(r["netto_val"] is None for r in da_lul)
