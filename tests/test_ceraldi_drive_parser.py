"""Coda Drive equa e scarti documentali riprodotti senza servizi esterni."""
import ast
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
for package in ('app', 'app.services'):
    if package not in sys.modules:
        module = ModuleType(package)
        module.__path__ = [str(ROOT / package.replace('.', '/'))]
        sys.modules[package] = module

from app.services.drive_cartella_unica import seleziona_lotto
from app.services.classificazione_estratti import route_da_testo, BANCA, MUTUO
from app.services.estratto_conto_bnl_parser import leggi_parole_bnl, EstrattoBNLNonValido
from app.services import drive_cartella_unica as drive


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


class DeferredYearTests(unittest.IsolatedAsyncioTestCase):
    def test_anno_diverso_non_e_errore_anche_se_xml_parzialmente_importato(self):
        for success, imported in [(False, 0), (True, 1)]:
            destination, message = drive.esito_del_risultato(dict(
                success=success, imported=imported, skipped_altro_anno=1,
                anni_in_attesa=[2026], anno_import_attivo=2025))
            self.assertEqual(destination, drive.ARRETRATO)
            self.assertIn('2026', message)
        self.assertEqual(drive.esito_del_risultato(dict(success=False, message='XML corrotto')),
                         (drive.ERRORI, 'XML corrotto'))

    async def test_vecchio_scarto_rinviato_e_ripreso_solo_per_anno_selezionato(self):
        row = dict(id='originale', cartella=drive.ERRORI, tipo='fattura',
                   motivo="Fattura del 2026: l'anno attivo e' il 2025, non entra nel gestionale e l'originale resta su Drive")
        db = Mock()
        collection = db.__getitem__ = Mock(return_value=Mock())
        collection.return_value.find.return_value.to_list = AsyncMock(return_value=[row])
        folders = {key: key for key in (drive.ERRORI, drive.ARRETRATO, drive.INBOX)}
        with patch.object(drive, '_sposta') as move, patch.object(drive, '_registra', new_callable=AsyncMock) as record:
            self.assertEqual(await drive.rimetti_in_coda_buste_gia_presenti(
                db, None, folders, anno_attivo=2025), 1)
            fields = record.await_args.kwargs
            self.assertEqual((fields['esito'], fields['cartella'], fields['anni_in_attesa']),
                             ('arretrato', drive.ARRETRATO, [2026]))
            row.update(fields)
            move.reset_mock(); record.reset_mock()
            self.assertEqual(await drive.rimetti_in_coda_buste_gia_presenti(
                db, None, folders, anno_attivo=2025), 0)
            move.assert_not_called(); record.assert_not_awaited()
            self.assertEqual(await drive.rimetti_in_coda_buste_gia_presenti(
                db, None, folders, anno_attivo=2026), 1)
            self.assertEqual(record.await_args.kwargs['cartella'], drive.INBOX)
            self.assertEqual(record.await_args.kwargs['esito'], 'rimesso_in_coda')

    async def test_recupero_storico_limitato_per_non_bloccare_i_pdf_nuovi(self):
        rows = [dict(id=str(i), cartella=drive.ARRETRATO, anni_in_attesa=[2026]) for i in range(100)]
        db = Mock()
        db.__getitem__ = Mock(return_value=Mock())
        db.__getitem__.return_value.find.return_value.to_list = AsyncMock(return_value=rows)
        folders = {key: key for key in (drive.ERRORI, drive.ARRETRATO, drive.INBOX)}
        with patch.object(drive, '_sposta') as move, patch.object(drive, '_registra', new_callable=AsyncMock):
            self.assertEqual(await drive.rimetti_in_coda_buste_gia_presenti(
                db, None, folders, limite=25, anno_attivo=2026), 25)
            self.assertEqual(move.call_count, 25)


if __name__ == '__main__':
    unittest.main()
