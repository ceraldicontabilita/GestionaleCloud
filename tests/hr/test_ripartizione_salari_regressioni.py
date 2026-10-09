import unittest
from app.services.posizione_dipendente import componi_movimenti, posizione, prima_nota_mensile

class SaldoDipendenteTests(unittest.TestCase):
    def movimenti(self, **campi):
        return componi_movimenti(**dict(paghe=[], esiti=[], cedolini=[], acconti=[], conciliazioni=[], **campi))

    def test_pagamento_non_riconciliato_senza_mese_riduce_saldo_alla_data(self):
        m = self.movimenti(pagamenti_senza_competenza=[{
            "id": "q", "dipendente_id": "d", "data": "2025-12-20", "importo": 400,
            "associazione_certa": True, "stato": "da_associare"}])
        self.assertEqual(posizione(m, 2025)["chiusura"], -400)
        self.assertEqual(posizione(m, 2026)["apertura"], -400)
        self.assertIsNone(m["registro"][0]["competenza"])

    def test_pagamento_con_competenza_futura_non_si_sposta_nel_progressivo(self):
        m = componi_movimenti(paghe=[{"anno": 2026, "mese": 1, "importo_busta": 1000}],
                              esiti=[{"data": "2025-12-20", "importo": 400, "anno": 2026, "mese": 1}],
                              cedolini=[], acconti=[], conciliazioni=[])
        righe = prima_nota_mensile(m)["movimenti"]
        self.assertEqual([(r["data"], r["saldo"]) for r in righe], [("2025-12-20", -400), ("2026-01-31", 600)])

    def test_cedolino_e_pagamento_successivo_sulla_stessa_riga(self):
        m = componi_movimenti(paghe=[{"anno": 2021, "mese": 11, "importo_busta": 878}],
                              esiti=[{"data": "2021-12-03", "importo": 863, "anno": 2021, "mese": 11}],
                              cedolini=[], acconti=[], conciliazioni=[])
        vista = prima_nota_mensile(m)
        self.assertEqual(len(vista["competenze"]), 1)
        r = vista["competenze"][0]
        self.assertEqual((r["dovuto"], r["pagato"], r["differenza"]), (878, 863, 15))
        self.assertEqual(r["pagamenti"][0]["data"], "2021-12-03")
        self.assertEqual([x["saldo"] for x in vista["movimenti"]], [878, 15])

    def test_pagamenti_multipli_chiudono_busta_e_lasciano_acconto(self):
        m = componi_movimenti(paghe=[{"anno": 2021, "mese": 11, "importo_busta": 878}],
                              esiti=[{"data": d, "importo": i, "anno": 2021, "mese": 11}
                                     for d, i in [("2021-12-03", 863), ("2021-12-16", 1878), ("2021-12-21", 1000)]]
                                    + [{"data": "2021-12-22", "importo": 400}],
                              cedolini=[], acconti=[], conciliazioni=[])
        vista = prima_nota_mensile(m)
        r, *liberi = vista["competenze"]
        self.assertEqual(len(r["pagamenti"]), 2)
        self.assertEqual((r["pagato"], r["differenza"]), (878, 0))
        self.assertTrue(all(libero["mese"] is None for libero in liberi))
        self.assertEqual(sum(libero["pagato"] for libero in liberi), 3263)
        self.assertEqual(vista["saldo_finale"], -3263)

    def test_esito_senza_mese_ha_valore_economico(self):
        m = componi_movimenti(paghe=[], esiti=[{"data": "2025-12-20", "importo": 400}],
                              cedolini=[], acconti=[], conciliazioni=[])
        self.assertEqual(prima_nota_mensile(m)["saldo_finale"], -400)

    def test_candidato_non_confermato_non_diventa_pagamento(self):
        m = self.movimenti(pagamenti_senza_competenza=[{
            "id": "q", "dipendente_id": "d", "data": "2025-12-20", "importo": 400,
            "associazione_certa": False, "stato": "da_associare"}])
        self.assertEqual(prima_nota_mensile(m)["saldo_finale"], 0)

    def test_stessa_operazione_in_coda_ed_esiti_si_conta_una_volta(self):
        q = {"id": "q", "dipendente_id": "d", "data": "2025-12-20", "importo": 400,
             "associazione_certa": True, "stato": "da_associare", "hash": "same-document"}
        m = componi_movimenti(paghe=[], esiti=[q | {"anno": 2025, "mese": 12}],
                              cedolini=[], acconti=[], conciliazioni=[], pagamenti_senza_competenza=[q])
        self.assertEqual(prima_nota_mensile(m)["saldo_finale"], -400)

    def test_ricevuta_uguale_a_elenco_resta_da_confrontare_senza_doppia_sottrazione(self):
        q = {"id": "q", "dipendente_id": "d", "data": "2025-12-20", "importo": 400,
             "associazione_certa": True, "stato": "da_associare", "hash": "receipt"}
        m = componi_movimenti(paghe=[], esiti=[q | {"hash": None, "origine": "elenco-pagamenti-titolare"}],
                              cedolini=[], acconti=[], conciliazioni=[], pagamenti_senza_competenza=[q])
        self.assertEqual(prima_nota_mensile(m)["saldo_finale"], -400)
        self.assertEqual(m["registro"][1]["tipo"], "verifica_bonifico")


class RipartizioneSalariTests(unittest.TestCase):
    def vista(self, paghe, esiti):
        return prima_nota_mensile(componi_movimenti(paghe=paghe, esiti=esiti,
            cedolini=[], acconti=[], conciliazioni=[]))

    def test_prima_competenza_poi_residuo_vecchio_e_acconto(self):
        paghe = [{"anno": 2025, "mese": 11, "importo_busta": 800},
                 {"anno": 2025, "mese": 12, "importo_busta": 1000}]
        vista = self.vista(paghe, [{"key": "p1", "data": "2026-01-10", "anno": 2025, "mese": 12, "importo": 1950}])
        mesi = {r["mese"]: r for r in vista["competenze"]}
        self.assertEqual([mesi[m]["pagato"] for m in (11, 12, None)], [800, 1000, 150])
        self.assertEqual(sum(r["pagato"] for r in vista["competenze"]), 1950)
        self.assertEqual(vista["saldo_finale"], -150)

    def test_due_pagamenti_consumano_soltanto_il_residuo(self):
        paghe = [{"anno": 2025, "mese": m, "importo_busta": 1000} for m in (11, 12)]
        esiti = [{"key": "p1", "data": "2025-12-10", "importo": 700},
                 {"key": "p2", "data": "2026-01-07", "importo": 600}]
        vista = self.vista(paghe, esiti)
        self.assertEqual([(r["pagato"], r["differenza"]) for r in vista["competenze"]], [(1000, 0), (300, 700)])
        self.assertEqual(vista["saldo_finale"], 700)
        self.assertEqual([r["data"] for r in vista["movimenti"] if r["avere"]], ["2025-12-10", "2026-01-07"])

    def test_cedolino_scelto_vince_sulla_causale_senza_dividere_il_fatto_banca(self):
        paghe = [{"anno": 2025, "mese": m, "importo_busta": 1000} for m in (10, 11, 12)]
        e = {"key": "p", "data": "2026-01-01", "anno": 2025, "mese": 11, "importo": 1200,
             "destinazioni_salari": [{"anno": 2025, "mese": 12, "importo": 1000}]}
        vista = self.vista(paghe, [e])
        self.assertEqual([(r["mese"], r["pagato"]) for r in vista["competenze"]], [(10, 200), (11, 0), (12, 1000)])
        self.assertEqual(len([r for r in vista["movimenti"] if r["avere"]]), 1)

    def test_netto_assente_non_si_inventa_ed_eccedenza_si_applica_al_prossimo_cedolino(self):
        e = {"key": "p", "data": "2025-12-10", "importo": 400}
        senza = self.vista([], [e])
        con = self.vista([{"anno": 2026, "mese": 1, "importo_busta": 500}], [e])
        self.assertIsNone(senza["competenze"][0]["dovuto"])
        self.assertEqual((con["competenze"][0]["pagato"], con["competenze"][0]["differenza"]), (400, 100))
        self.assertEqual(con["movimenti"][0]["saldo"], -400)
