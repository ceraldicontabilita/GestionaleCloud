"""Regressioni contabili: data del pagamento distinta dalla competenza."""
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


if __name__ == "__main__":
    unittest.main()
