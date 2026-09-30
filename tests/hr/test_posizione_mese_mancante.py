from datetime import date

from app.services.posizione_dipendente import componi_movimenti, mesi_mancanti, posizione


def _ced(mese, netto="1000,00"):
    return {"id": f"c{mese}", "anno": 2025, "mese": mese, "tipo_cedolino": "mensile",
            "netto": netto, "stato_netto": "NETTO_VERIFICATO_DA_CEDOLINO"}


def _mov(mesi):
    return componi_movimenti(paghe=[], esiti=[], cedolini=[_ced(m) for m in mesi],
                             acconti=[], conciliazioni=[])


def test_gennaio_senza_busta_e_dichiarato_mancante():
    mov = _mov([2, 3, 4])
    rapporto = {"data_assunzione": "2025-01-10"}
    assert mesi_mancanti(mov["registro"], 2025, rapporto, date(2026, 1, 15)) == [(2025, 1)] + [
        (2025, m) for m in range(5, 13)]


def test_riga_nella_posizione_senza_importi_e_dopo_la_cessazione_niente():
    mov = _mov([1, 2, 4])
    rapporto = {"data_assunzione": "2025-01-01", "data_cessazione": "2025-04-30"}
    out = posizione(mov, 2025, rapporto)
    righe = [r for r in out["righe"] if r["tipo"] == "mese_mancante"]
    assert [r["descrizione"].endswith("mese mancante") for r in righe] == [True]
    assert righe[0]["dare"] is None and righe[0]["avere"] is None
    assert out["mesi_mancanti"] == [{"anno": 2025, "mese": 3}]


def test_senza_assunzione_parte_dalla_prima_busta():
    mov = _mov([3, 5])
    assert mesi_mancanti(mov["registro"], 2025, {}, date(2025, 7, 1)) == [(2025, 4), (2025, 6)]
