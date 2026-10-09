"""Coda Drive equa e scarti documentali riprodotti senza servizi esterni."""
import ast
from pathlib import Path
import sys
from types import ModuleType
import unittest

ROOT = Path(__file__).resolve().parents[1]
for package in ('app', 'app.services'):
    if package not in sys.modules:
        module = ModuleType(package)
        module.__path__ = [str(ROOT / package.replace('.', '/'))]
        sys.modules[package] = module

from app.services.drive_cartella_unica import seleziona_lotto
from app.services.classificazione_estratti import route_da_testo, BANCA, MUTUO
from app.services.estratto_conto_bnl_parser import leggi_parole_bnl, EstrattoBNLNonValido


class DriveParserTests(unittest.TestCase):
    def test_pdf_non_attendono_la_fine_di_migliaia_di_xml(self):
        xml = [{'id': f'x{i}', 'name': f'{i}.xml', 'modifiedTime': str(i)} for i in range(3529)]
        pdf = [{'id': f'p{i}', 'name': f'documento {i}.pdf'} for i in range(7822)]
        coda = xml + pdf
        lotto = seleziona_lotto(coda, 50)
        self.assertEqual(sum(f['name'].endswith('.pdf') for f in lotto), 25)
        self.assertEqual([f['id'] for f in lotto if f['name'].endswith('.pdf')], [f'p{i}' for i in range(25)])
        self.assertEqual(len(seleziona_lotto(xml, 50)), 50)
        self.assertEqual(len(seleziona_lotto(pdf[:3] * 2, 50)), 3)

    def test_precedenze_e_nessun_file_perso_nella_coda(self):
        files = [dict(id='a', name='1.xml'), dict(id='b', name='Busta paga.pdf'),
                 dict(id='c', name='Estratto conto.pdf'), dict(id='d', name='quadro.pdf')]
        self.assertEqual([f['id'] for f in seleziona_lotto(files, 4)], ['c', 'b', 'a', 'd'])

    def test_estratto_con_rata_mutuo_non_diventa_documento_mutuo(self):
        self.assertEqual(route_da_testo('ESTRATTO CONTO\n05034\nSALDO INIZIALE\nAddebito rata mutuo'), BANCA)
        self.assertEqual(route_da_testo('Banco\nBPM\nData contabile\nData valuta\nMutuo'), BANCA)
        self.assertEqual(route_da_testo('Mutuo\nPIANO DI\nAMMORTAMENTO'), MUTUO)
        self.assertEqual(route_da_testo('Mutui: quietanza pagamento rata n. 3'), MUTUO)
        self.assertIsNone(route_da_testo('Comunicazione pubblicitaria sul mutuo'))

    def test_bnl_codice_zi_allineato_a_destra_e_saldi_verificati(self):
        def w(text, x0, x1, top):
            return dict(text=text, x0=x0, x1=x1, top=top)
        header = [w('(DATA', 50, 75, 100), w('CONTABILE)', 75, 110, 100),
                  w('(DATA', 120, 145, 100), w('ABI', 190, 201.4, 90),
                  w('USCITA', 440, 470, 88), w('DI', 472, 479, 88),
                  w('ENTRATA', 510, 545, 88), w('DI', 547, 554, 88)]
        row = [w('26/07/2019', 50, 90, 130), w('26/07/2019', 120, 160, 130),
               w('ZI', 199.7, 205.5, 130), w('Bonifico', 216, 250, 130),
               w('1.400,00', 525, 554, 130)]
        text = ('Banca Nazionale del Lavoro ESTRATTO CONTO N. 3/2019 DATA CONTABILE '
                'saldo iniziale al 01/07/2019? 0,00 € '
                'entrate complessive di questo periodo? 1.400,00 € '
                'uscite complessive di questo periodo? 0,00 € '
                'saldo finale al 30/09/2019? 1.400,00 €')
        parsed = leggi_parole_bnl([header + row], testo=text)
        self.assertEqual(len(parsed.righe), 1)
        self.assertEqual((parsed.righe[0].causale_abi, parsed.righe[0].tipo), ('ZI', 'entrata'))
        with self.assertRaises(EstrattoBNLNonValido):
            leggi_parole_bnl([header + row], testo=text.replace('30/09/2019? 1.400,00', '30/09/2019? 1.401,00'))


class EmptyReconciliationTests(unittest.IsolatedAsyncioTestCase):
    async def test_lista_vuota_non_rilegge_ne_modifica_lo_storico(self):
        # Esegue la funzione di produzione; gli altri motori sono irraggiungibili
        # se il chiamante ha gia' riconciliato tutti i movimenti del proprio lotto.
        path = ROOT / 'app/services/bank_payment_allocations.py'
        tree = ast.parse(path.read_text())
        node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)
                    and n.name == 'reconcile_deterministic_invoice_allocations')
        future = ast.parse('from __future__ import annotations').body
        namespace = {}
        exec(compile(ast.Module(body=future + [node], type_ignores=[]), str(path), 'exec'), namespace)
        class NoDatabaseRead:
            def __getitem__(self, key):
                raise AssertionError('Nessuna lettura del database per un lotto vuoto')
        result = await namespace[node.name](NoDatabaseRead(), movement_ids=[])
        self.assertEqual((result['esaminati'], result['allocati']), (0, 0))


if __name__ == '__main__':
    unittest.main()
