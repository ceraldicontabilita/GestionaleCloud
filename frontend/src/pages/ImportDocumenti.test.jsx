import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import ImportDocumenti, { classificaEsitoUpload, descriviProvaFiscale } from './ImportDocumenti';

vi.mock('../api', () => ({ default: { post: vi.fn() } }));

function mockPreviewThenImport(tipo, importData, parsed = {}) {
  api.post.mockImplementation(url => Promise.resolve({
    data: url.endsWith('/preview')
      ? {
          success: true,
          preview_only: true,
          tipo_rilevato: tipo,
          confirmation_token: `token-${tipo}`,
          blocking_errors: [],
          duplicate: false,
          file: { sha256: 'a'.repeat(64) },
          parsed,
          validation: parsed.validazione || {},
        }
      : importData,
  }));
}

describe('Import documenti - corrispettivo duplicato', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('non presenta come importato un duplicato restituito con HTTP 200', async () => {
    mockPreviewThenImport('corrispettivo', {
        success: false,
        duplicate: true,
        action: 'duplicate',
        imported: 0,
        tipo_rilevato: 'corrispettivo',
        message: 'Corrispettivo duplicato ignorato: 2026-07-06 — totale 2006.30€',
    });

    render(<ImportDocumenti />);

    const xml = new File(['<Corrispettivi/>'], 'corrispettivo-test.xml', {
      type: 'application/xml',
    });
    fireEvent.change(screen.getByTestId('file-input'), { target: { files: [xml] } });
    fireEvent.click(await screen.findByTestId('upload-btn'));

    expect(await screen.findByTestId('preview-summary')).toHaveTextContent('nessun dato salvato');
    expect(api.post).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId('upload-btn'));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('Nessun nuovo documento: duplicati ignorati')).toBeInTheDocument();
    expect(screen.getByText(/Corrispettivo duplicato ignorato: 2026-07-06/)).toBeInTheDocument();
    expect(screen.queryByText('Import completato!')).not.toBeInTheDocument();
  });

  it('mostra come errore un workflow fallito restituito con HTTP 200', () => {
    expect(classificaEsitoUpload({
      success: false,
      message: 'Errore parsing F24',
    })).toEqual({
      status: 'error',
      message: 'Errore parsing F24',
    });
  });

  it('mostra la prova del parsing F24 canonico senza confonderla con la banca', async () => {
    mockPreviewThenImport('f24', {
        success: true,
        tipo_rilevato: 'f24',
        workflow: 'F24_CANONICO',
        imported: 1,
        message: 'F24 importato nel registro canonico',
        data: {
          righe_tributo: 2,
          righe_credito: 1,
          validazione: { saldo_quadrato: true },
        },
    }, { righe_tributo: 2, validazione: { saldo_quadrato: true } });
    render(<ImportDocumenti />);

    const pdf = new File(['%PDF-test'], 'f24-test.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByTestId('file-input'), { target: { files: [pdf] } });
    fireEvent.click(await screen.findByTestId('upload-btn'));
    await screen.findByTestId('preview-summary');
    fireEvent.click(screen.getByTestId('upload-btn'));

    expect(await screen.findByText('Righe tributo: 2 • Crediti: 1 • Quadratura verificata')).toBeInTheDocument();
    expect(descriviProvaFiscale({ workflow: 'ALTRO' })).toBe('');
  });

  it('mostra il collegamento CBILL a rata e cartelle distinguendo la banca', () => {
    expect(descriviProvaFiscale({
      workflow: 'PAGOPA_CBILL_CANONICO',
      data: { riconciliazione_fiscale: {
        matched: true,
        linked_claim_ids: ['claim-1', 'claim-2'],
        bank_verified: false,
      } },
    })).toBe('Rata collegata â€¢ Cartelle collegate: 2 â€¢ Banca da verificare');
  });

  it('separa importo, commissione e addebito per MAV RAV e bollettini', () => {
    const description = descriviProvaFiscale({
      workflow: 'PAGAMENTO_DOCUMENTALE_CANONICO',
      data: {
        receipt: { operation_amount: 34.9, fee_amount: 2.85, bank_debit_total: 37.75 },
        riconciliazione_fiscale: { matched: false, bank_verified: false },
      },
    });
    expect(description).toContain('Operazione: € 34.90');
    expect(description).toContain('Commissione: € 2.85');
    expect(description).toContain('Addebito: € 37.75');
    expect(description).toContain('Banca da verificare');
  });

  it('mostra anche il collegamento AdeR prodotto da una quietanza F24', () => {
    expect(descriviProvaFiscale({
      workflow: 'F24_CANONICO',
      data: { riconciliazione_ader: { matched: true, linked_claim_ids: ['claim-1'] } },
    })).toBe('Rata AdeR collegata • Cartelle collegate: 1');
  });

  it('mantiene lo ZIP intero e lo affida ai controlli del backend', async () => {
    mockPreviewThenImport('archivio_zip', {
        success: true,
        tipo_rilevato: 'archivio_zip',
        imported: 2,
        message: 'ZIP elaborato: 2 importati, 0 duplicati, 0 errori, 0 ignorati',
    });
    render(<ImportDocumenti />);

    const zip = new File(['PK-test'], 'documenti.zip', { type: 'application/zip' });
    fireEvent.change(screen.getByTestId('zip-file-input'), { target: { files: [zip] } });

    expect(await screen.findByText('1 file in coda')).toBeInTheDocument();
    expect(screen.getByText('documenti.zip')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('upload-btn'));

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const [url, formData] = api.post.mock.calls[0];
    expect(url).toBe('/api/documenti/upload-auto/preview');
    expect(formData.get('file').name).toBe('documenti.zip');
    fireEvent.click(screen.getByTestId('upload-btn'));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    const [importUrl, , config] = api.post.mock.calls[1];
    expect(importUrl).toBe('/api/documenti/upload-auto');
    expect(config.headers['X-Document-Preview-Token']).toBe('token-archivio_zip');
    expect((await screen.findAllByText('Archivio ZIP')).length).toBeGreaterThan(0);
  });

  it('esegue prima la simulazione delle classificazioni massive', async () => {
    api.post
      .mockResolvedValueOnce({ data: {
        dry_run: true, totali: 12, classificati: { f24: 4 }, nessuna_categoria: 8,
      } })
      .mockResolvedValueOnce({ data: {
        dry_run: false, totali: 12, classificati: { f24: 4 },
        nessuna_categoria: 8, cedolini_associati: 0, f24_creati: 4,
      } });
    render(<ImportDocumenti />);

    fireEvent.click(screen.getByTestId('auto-classify-btn'));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    expect(api.post.mock.calls[0][0]).toContain('dry_run=true');
    expect(api.post.mock.calls[1][0]).toContain('dry_run=false');
  });
});
