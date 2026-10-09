"""Regressioni contabili: data del pagamento distinta dalla competenza."""
import unittest
import sys
from pathlib import Path
from types import ModuleType

# Il saldo è un motore puro: caricare il package non deve avviare auth/email.
ROOT = Path(__file__).resolve().parents[1]
for package in ("app", "app.services", "app.hr", "app.hr.services"):
    if package not in sys.modules:
        module = ModuleType(package)
        module.__path__ = [str(ROOT / package.replace(".", "/"))]
        sys.modules[package] = module

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


class ComponentiDocumentaliTests(unittest.TestCase):
    def cedolino(self, tipo="ordinario", **extra):
        return dict(id="c", codice_fiscale="CF", anno=2026, mese=8, tipo_cedolino=tipo,
                    netto=1000, dati_chiave={"componenti_busta": [
                        {"tipo": "14", "importo": 234.49, "pagina": 1, "bbox": [1, 2, 3, 4]},
                        {"tipo": "tfr_quota_anno", "importo": 450, "pagina": 1, "bbox": [1, 8, 3, 9]},
                    ], "componenti_versione": 1}, **extra)

    def test_quote_lorde_non_creano_secondo_debito(self):
        from app.services.mensilita_aggiuntive import componenti_documentate
        c = self.cedolino()
        voci = componenti_documentate([c], 2026, {"14"})
        self.assertEqual(voci[0]["importo"], 234.49)
        m = componi_movimenti(paghe=[{"anno": 2026, "mese": 8, "importo_busta": 1000}],
                              cedolini=[c], esiti=[], acconti=[], conciliazioni=[])
        self.assertEqual(prima_nota_mensile(m)["saldo_finale"], 1000)

    def test_mensilita_autonoma_e_versioni_superate_non_sono_quote_ordinarie(self):
        from app.services.mensilita_aggiuntive import componenti_documentate
        cs = [self.cedolino("quattordicesima"), self.cedolino(status="sostituito", sostituito_da="nuova"),
              self.cedolino(varianti_da_decidere=True)]
        self.assertEqual(componenti_documentate(cs, 2026, {"14"}), [])

    def test_rilettura_non_modifica_netto_o_acconti(self):
        from app.services.cedolini_hr_riverifica import componenti_della_riga
        c = self.cedolino()
        originale = self.cedolino() | {"netto": 990}
        patch = componenti_della_riga(c, [originale])
        self.assertEqual(set(patch), {"dati_chiave.componenti_busta", "dati_chiave.componenti_versione"})
        self.assertEqual(c["netto"], 1000)

    def test_pdf_di_altro_dipendente_o_periodo_non_aggiorna_componenti(self):
        from app.services.cedolini_hr_riverifica import componenti_della_riga
        c = self.cedolino()
        for modifica in ({"codice_fiscale": "ALTRO"}, {"mese": 7}, {"anno": 2025}):
            with self.assertRaises(ValueError):
                componenti_della_riga(c, [c | modifica])


class CoperturaMensilitaTests(unittest.TestCase):
    def test_un_bonifico_chiude_tre_mesi_senza_triplicare_il_pagamento(self):
        from app.services.pagamenti_mensilita import indice_coperture, stato_copertura
        e = {'id': 'e', 'dipendente_id': 'd', 'data': '2022-06-10', 'importo': 3249,
             'confermato_manuale': True, 'periodi_saldati': [{'anno': 2022, 'mese': m} for m in (3, 4, 5)]}
        coperture = indice_coperture([e])
        self.assertEqual(set(coperture), {('d', 2022, m) for m in (3, 4, 5)})
        for prove in coperture.values():
            self.assertEqual(stato_copertura(prove)['saldo'], 0)
            self.assertEqual(prove[0]['nota'], 'Stipendio pagato con bonifico del 10/06/2022')
        mov = componi_movimenti(paghe=[], esiti=[e], cedolini=[], acconti=[], conciliazioni=[])
        self.assertEqual(prima_nota_mensile(mov)['saldo_finale'], -3249)
        self.assertEqual(indice_coperture([e | {'confermato_manuale': False}]), {})

    def test_totali_zucchetti_dalle_celle_non_dalla_prima_coppia_del_testo(self):
        from app.parsers.busta_paga_multi_template import _parse_zucchetti_totals_layout
        words = [(423, 698, 480, 705, 'TOTALEsCOMPETENZE'), (546, 700, 578, 707, '2.006,29'),
                 (423, 711, 478, 718, 'TOTALEsTRATTENUTE'), (553, 713, 578, 720, '500,41'),
                 (423, 560, 478, 568, 'IRPEF'), (553, 560, 578, 568, '89,76')]
        self.assertEqual(_parse_zucchetti_totals_layout([words]), {'lordo': 2006.29, 'trattenute': 500.41})
        self.assertEqual(_parse_zucchetti_totals_layout([words[1:2]]), {})
        ambiguous = words + [(540, 713, 560, 720, '999,99')]
        self.assertNotIn('trattenute', _parse_zucchetti_totals_layout([ambiguous]))
