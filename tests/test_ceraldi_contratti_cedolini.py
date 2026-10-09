"""Rapporti distinti, copie e saldo mensile: nessuna chiamata esterna."""
import sys
import unittest
from pathlib import Path
from types import ModuleType
for package in ('app', 'app.services', 'app.utils'):
    if package not in sys.modules:
        module = ModuleType(package)
        module.__path__ = [str(Path(__file__).resolve().parents[1] / package.replace('.', '/'))]
        sys.modules[package] = module
from app.services.cedolini_rapporti import raggruppa_cedolini, stessa_busta, rapporto_da_coordinate
from app.services.posizione_dipendente import dovuto_busta, componi_movimenti, prima_nota_mensile
from app.constants.stati_associazione_bonifico import esiti_confermati, esiti_riconciliati


class ContrattiCedoliniTests(unittest.TestCase):
    def busta(self, ident='a', netto=345.17, **extra):
        return dict(id=ident, dipendente_id='d', codice_fiscale='CF', anno=2025, mese=11,
                    tipo_cedolino='ordinario', netto=netto, rapporto_id=ident,
                    impronta_contenuto=ident, **extra)

    def test_due_contratti_e_copia_sommati_una_volta(self):
        a,b=self.busta(),self.busta('b',121)
        grouped=list(raggruppa_cedolini([a,b,dict(b,id='copia')]).values())
        self.assertEqual(len(grouped),1)
        self.assertEqual(len(grouped[0]['cedolini_componenti']),2)
        self.assertEqual(float(dovuto_busta({},grouped[0])['dovuto']),466.17)
        m=componi_movimenti(paghe=[],cedolini=[a,b],esiti=[{
            'data':'2025-12-05','anno':2025,'mese':11,'importo':466.17}],acconti=[],conciliazioni=[])
        self.assertEqual(prima_nota_mensile(m)['saldo_finale'],0)

    def test_importi_uguali_non_sono_prova_di_duplicato(self):
        a,b=self.busta(),self.busta('b')
        self.assertFalse(stessa_busta(a,b))
        self.assertEqual(list(raggruppa_cedolini([a,b]).values())[0]['netto'],690.34)

    def test_netto_ignoto_non_completa_il_mese(self):
        a,b=self.busta(),self.busta('b',None)
        total=list(raggruppa_cedolini([a,b]).values())[0]
        self.assertIsNone(dovuto_busta({'importo_busta':345.17},total)['dovuto'])

    def test_revisioni_da_decidere_non_sommate_e_sostituiti_esclusi(self):
        total=list(raggruppa_cedolini([self.busta(varianti_da_decidere=True),self.busta('b',121)]).values())[0]
        self.assertIsNone(dovuto_busta({},total)['dovuto'])
        self.assertEqual(list(raggruppa_cedolini([self.busta(),self.busta('b',121,status='sostituito')]).values())[0]['netto'],345.17)

    def test_data_scadenza_non_diventa_cessazione(self):
        words=[(77,158,117,165,'DatasAssunzione'),(123,158,163,165,'DatasCessazione'),
               (77,168,117,175,'26-11-2025'),(200,168,260,175,'T.Deter.'),(270,168,300,175,'25/11/2027')]
        r=rapporto_da_coordinate(words)['rapporto_lavoro']
        self.assertEqual(r['data_assunzione'],'2025-11-26')
        self.assertNotIn('data_cessazione',r)

    def test_conferma_titolare_vale_senza_inventare_prova_banca(self):
        e={'dipendente_id':'d','origine':'elenco-pagamenti-titolare','associazione_certa':True,'competenza_confermata':True}
        self.assertTrue(esiti_confermati([e]))
        self.assertFalse(esiti_riconciliati([e]))
        self.assertFalse(esiti_confermati([dict(e,competenza_confermata=False)]))

    def test_competenza_esplicita_non_data_del_bonifico(self):
        from app.services.pagamenti_mensilita import competenza_in_causale
        self.assertEqual(competenza_in_causale('Bonifico 07/07/2026 stipendio 06/2026'), (6, 2026))
        self.assertEqual(competenza_in_causale('Stipendio Giugno 2026'), (6, 2026))
        self.assertIsNone(competenza_in_causale('Bonifico del 07/07/2026'))
        self.assertIsNone(competenza_in_causale('Parisi stipendi 3-4-5 2022'))
        self.assertIsNone(competenza_in_causale('stipendi 06/2026 e 07/2026'))
