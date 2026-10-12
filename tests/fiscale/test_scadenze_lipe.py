from datetime import date
from app.services.scadenze_lipe import scadenza_lipe, attesa_lipe


def test_scadenze_2026_ufficiali_e_festivi():
    assert scadenza_lipe(2026,1)[1] == date(2026,6,1)
    assert scadenza_lipe(2026,2)[1] == date(2026,9,30)
    assert scadenza_lipe(2026,3)[1] == date(2026,11,30)
    assert scadenza_lipe(2026,4)[1] == date(2027,3,1)
    assert scadenza_lipe(2023,4)[1] == date(2024,2,29)


def test_il_giorno_di_scadenza_non_e_documento_mancante():
    assert not attesa_lipe(2026,6,date(2026,9,30))['puoi_scaricare']
    assert attesa_lipe(2026,6,date(2026,10,1))['puoi_scaricare']
    assert attesa_lipe(2026,8,date(2026,10,12))['stato']=='in_attesa_scadenza'
    assert attesa_lipe(2026,8,date(2026,12,1))['puoi_scaricare']
    assert not attesa_lipe(2026,8,date(2026,10,12),presente=True)['confronto_abilitato']
    assert attesa_lipe(2026,8,date(2026,12,1),presente=True)['confronto_abilitato']
