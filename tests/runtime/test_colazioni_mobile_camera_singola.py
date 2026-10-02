from pathlib import Path


HTML = (
    Path(__file__).resolve().parents[2] / "frontend_colazioni" / "index.html"
).read_text(encoding="utf-8")


def test_menu_albergatore_mobile_non_richiede_scroll_orizzontale():
    assert 'pre==="albergatore"?"hotel-tabs":""' in HTML
    assert "grid-template-columns:repeat(4,minmax(0,1fr))" in HTML
    assert ".hotel-tabs button{width:100%;min-width:0" in HTML


def test_prenotazione_gestisce_una_sola_camera_senza_date_nella_card():
    assert "let NR=[],DEF={},NRSEL=-1" in HTML
    assert "Seleziona e salva una camera alla volta" in HTML
    assert 'id="n_cam"' in HTML
    assert 'class="booking-room"' in HTML
    assert "Salva questa camera e crea il QR" in HTML
    assert "Continua con una nuova camera" in HTML
    assert "selTutte(" not in HTML
    assert "<th>Dal</th><th>Al</th>" not in HTML


def test_periodo_rimane_unico_nella_card_superiore():
    assert 'id="n_dal" type="date"' in HTML
    assert 'id="n_al" type="date"' in HTML
    assert "Periodo scelto sopra" in HTML
