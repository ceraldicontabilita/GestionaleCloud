"""Gli originali Drive restano riapribili senza ricerca/download duplicati."""
import ast
import asyncio
import base64
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, Mock, patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
for package in ('app', 'app.services'):
    if package not in sys.modules:
        module = ModuleType(package)
        module.__path__ = [str(ROOT / package.replace('.', '/'))]
        sys.modules[package] = module

from app.document_repository import metadata_projection
from app.services.pdf_drive_only import externalize_documents, hydrate_document, reference_from_download

PDF = b'%PDF-1.7\noriginal receipt\n%%EOF'
SOURCE = dict(channel='drive_cartella_unica', drive_file_id='original',
              source_sha256=hashlib.sha256(PDF).hexdigest())


class BonificoDriveTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.archive = ModuleType('app.services.email_drive_archive')
        self.archive.archive_binary_copy = Mock(return_value={
            'status': 'archived', 'drive_file_id': 'new-verified-copy'})
        self.download = ModuleType('app.services.drive_download')
        self.download.scarica_originale = AsyncMock(return_value=PDF)
        self.modules = patch.dict(sys.modules, {
            self.archive.__name__: self.archive, self.download.__name__: self.download})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    async def test_transfer_e_inbox_riusano_originale_e_lo_riaprono_identico(self):
        for collection in ('bonifici_transfers', 'documents_inbox'):
            doc = dict(pdf_data=base64.b64encode(PDF).decode(),
                       **reference_from_download(PDF, SOURCE))
            await externalize_documents(collection, [doc])
            self.assertNotIn('pdf_data', doc)
            self.assertEqual(doc['_drive_payloads']['pdf_data']['drive_file_id'], 'original')
            await hydrate_document(collection, doc)
            self.assertEqual(base64.b64decode(doc['pdf_data']), PDF)
        self.archive.archive_binary_copy.assert_not_called()
        self.assertEqual(self.download.scarica_originale.await_count, 2)

    async def test_zip_header_e_contenuto_diverso_passano_da_archivio_verificato(self):
        sources = [{}, {**SOURCE, 'archive_member': 'receipt.pdf'},
                   {**SOURCE, 'archive_filename': 'archive.zip'},
                   {**SOURCE, 'source_sha256': 'different'},
                   {**SOURCE, 'channel': 'render_calderone'}]
        for source in sources:
            with self.subTest(source=source):
                doc = dict(pdf_data=base64.b64encode(PDF).decode(),
                           **reference_from_download(PDF, source))
                await externalize_documents('bonifici_transfers', [doc])
                self.assertEqual(doc['drive_file_id'], 'new-verified-copy')
        self.assertEqual(self.archive.archive_binary_copy.call_count, len(sources))

    async def test_originale_modificato_non_viene_servito_silenziosamente(self):
        doc = reference_from_download(PDF, SOURCE)
        self.download.scarica_originale.return_value = PDF.replace(b'original', b'altered')
        with self.assertRaisesRegex(RuntimeError, 'non corrispondente'):
            await hydrate_document('bonifici_transfers', doc)

    async def test_ingest_legge_pdf_una_volta_e_cerca_duplicati_senza_originali(self):
        # Esegue il writer reale; sostituisce soltanto parser e servizi esterni.
        path = ROOT / 'app/services/bonifici_pdf_ingest.py'
        node = next(n for n in ast.parse(path.read_text()).body
                    if isinstance(n, ast.AsyncFunctionDef) and n.name == 'importa_pdf_bonifico')
        parser = Mock(return_value='receipt text')
        collection = Mock()
        collection.find_one = AsyncMock(return_value=None)
        documents = []
        async def insert(doc):
            await externalize_documents('bonifici_transfers', [doc])
            documents.append(doc)
        collection.insert_one = insert
        hr = ModuleType('app.services.hr_pagamenti_deposito')
        hr.deposita_bonifico_transfer_in_hr = AsyncMock(return_value={'esito': 'in_coda'})
        namespace = dict(asyncio=asyncio, base64=base64, hashlib=hashlib,
                         datetime=datetime, timezone=timezone, uuid=uuid,
                         read_pdf_bytes=parser, e_stampa_fattura=lambda _: False,
                         metadata_projection=metadata_projection, reference_from_download=reference_from_download,
                         extract_transfers_from_text=lambda *a, **kw: [{'importo': 100, 'data': '2026-01-01',
                                                                       'beneficiario': {'nome': 'Test Person'}}],
                         accredito_non_registrabile=lambda _: False,
                         extract_filename_metadata=lambda _: {}, canale_obbligatorio=lambda _: 'drive',
                         build_dedup_key=lambda _: 'key', STATO_BONIFICO_DOCUMENTATO='documentato',
                         logger=logging.getLogger(__name__))
        future = ast.parse('from __future__ import annotations').body
        exec(compile(ast.Module(body=future + [node], type_ignores=[]), str(path), 'exec'), namespace)
        with patch.dict(sys.modules, {hr.__name__: hr}):
            result = await namespace[node.name]({'bonifici_transfers': collection}, PDF, 'receipt.pdf',
                                                source='drive_cartella_unica', auto_associa=False,
                                                source_context=SOURCE)
        self.assertEqual(result['status'], 'saved')
        self.assertEqual(documents[0]['drive_file_id'], 'original')
        self.assertEqual(hr.deposita_bonifico_transfer_in_hr.await_args.args[1]['drive_file_id'], 'original')
        self.assertEqual(collection.find_one.await_args.args[1]['pdf_data'], 0)
        parser.assert_called_once_with(PDF)
        self.archive.archive_binary_copy.assert_not_called()


if __name__ == '__main__':
    unittest.main()
