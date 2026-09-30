import fitz


def test_rateo_13ma_in_un_mese_di_fis_e_una_mensile_non_una_tredicesima():
    from app.parsers.busta_paga_multi_template import _detect_tipo_cedolino

    fis_con_rateo = (
        "PERIODO DI RETRIBUZIONE\nMarzo 2025\n* * Z00250 Ferie godute\n"
        "* * Z50000 13ma Mensilita'\nZ00054 FIS D.Lgs.148/2015 fino 15 dip"
    )
    vera_tredicesima = (
        "PERIODO DI RETRIBUZIONE\nDicembre 2025 AGG.\n"
        "* * Z50000 13ma Mensilita' 8,60913 172,00000 ORE 1.480,77"
    )

    assert _detect_tipo_cedolino(fis_con_rateo) == "mensile"
    assert _detect_tipo_cedolino(vera_tredicesima) == "tredicesima"


def test_voce_con_asterischi_davanti_si_legge():
    from app.parsers.cedolino_voci import leggi_corpo_cedolino

    corpo = leggi_corpo_cedolino("* * Z50000 13ma Mensilita' 126,21\nZ00000 Contributo IVS 10,00")

    assert corpo["dati_chiave"]["rateo_13ma_presente"] is True
    assert corpo["dati_chiave"]["rateo_13ma_importo"] == "126,21"


def test_rateo_13ma_si_legge_per_riga_anche_se_il_testo_la_spezza():
    from app.parsers.cedolino_voci import importi_ratei_da_coordinate

    pdf = fitz.open()
    pagina = pdf.new_page()
    for x, testo in ((38, "Z50000"), (68, "13ma"), (285, "8,41117"), (372, "7,16500"), (548, "60,27")):
        pagina.insert_text((x, 300), testo, fontsize=8)
    for x, testo in ((38, "Z50022"), (68, "14ma"), (285, "8,00000"), (548, "1.234,56")):
        pagina.insert_text((x, 330), testo, fontsize=8)
    contenuto = pdf.tobytes()
    pdf.close()

    assert importi_ratei_da_coordinate(contenuto) == {"13": "60,27", "14": "1.234,56"}
