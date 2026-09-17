from app.services.enel_bolletta_parser import parse_bolletta_enel_testo


def test_parser_enel_annuale_e_mensile_con_quadratura():
    mesi = list(range(1, 13))
    f1 = [100 + m for m in mesi]
    f2 = [50 + m for m in mesi]
    f3 = [75 + m for m in mesi]
    tot = [a + b + c for a, b, c in zip(f1, f2, f3)]
    testo = f"""
Consumo annuo (dal 01.01.2025 al 31.12.2025)
F1 F2 F3 Tot. consumo
{sum(f1):,} kWh {sum(f2):,} kWh {sum(f3):,} kWh {sum(tot):,}
Informazioni storiche
F1 {' '.join(map(str, f1))}
F2 {' '.join(map(str, f2))}
F3 {' '.join(map(str, f3))}
Tot {' '.join(map(str, tot))}
kW max {' '.join('40.0' for _ in mesi)}
Consumo rilevato (dal 01.12.2025 al 31.12.2025)
F1 F2 F3 Totale energia
112 kWh 62 kWh 87 kWh 261 kWh
""".replace(",", ".")
    parsed = parse_bolletta_enel_testo(testo)
    assert parsed["anno"] == 2025
    assert len(parsed["mensili"]) == 12
    assert parsed["mensili"][-1]["totale_kwh"] == 261
    assert parsed["periodo_fatturato"]["f1_kwh"] == 112


def test_parser_non_espone_pod_o_dati_del_cliente():
    parsed = parse_bolletta_enel_testo("Codice POD IT000SECRET")
    assert parsed == {"fornitore": "Enel Energia", "mensili": []}
