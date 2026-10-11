import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import DeclarationDossier from './DeclarationDossier';

describe('Fascicolo dichiarazione annuale', () => {
  it('riunisce invii e allegati e apre ogni originale e la quietanza senza F24', () => {
    const onOpen = vi.fn();
    render(<DeclarationDossier onOpen={onOpen} dossier={{
      document_type: 'MODELLO_770', tax_year: 2023, model_years: [2024], taxpayer_id: '04523831214',
      original_count: 3, receipt_count: 1,
      originals: [
        { id: 'front', filename: 'Frontespizio.pdf', role: 'Frontespizio', declaration_identifier: 'INVIO-1', pdf_url: '/api/originale/documento/front' },
        { id: 'st', filename: 'ST.pdf', role: 'Quadro ST', declaration_identifier: 'INVIO-1', pdf_url: '/api/originale/documento/st' },
        { id: 'integrativa', filename: 'Integrativa.pdf', declaration_identifier: 'INVIO-2', pdf_url: '/api/originale/documento_fiscale/integrativa' },
      ],
      quietanze: [{ chiave: 'q', data: '2024-01-16', importo_cents: 12500, senza_modello: true,
        tax_rows: [{ codice: '1001', mese: 12, anno: 2023, importo_debito_cents: 12500 }],
        quietanze: [{ id: 'q', filename: 'Quietanza.pdf', pdf_url: '/api/originale/quietanza/q' }],
      }],
    }} />);
    expect(screen.getByText('770 · Anno d’imposta 2023')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Apri fascicolo'));
    for (const [filename, url] of [['Frontespizio.pdf', '/api/originale/documento/front'], ['ST.pdf', '/api/originale/documento/st'],
      ['Integrativa.pdf', '/api/originale/documento_fiscale/integrativa'], ['Quietanza.pdf', '/api/originale/quietanza/q']]) {
      fireEvent.click(screen.getByRole('button', { name: `Apri PDF ${filename}` }));
      expect(onOpen).toHaveBeenLastCalledWith({ url, titolo: filename });
    }
    expect(screen.getByText('Invio INVIO-1')).toBeInTheDocument();
    expect(screen.getByText('Invio INVIO-2')).toBeInTheDocument();
    expect(screen.getByText(/12\/2023/)).toBeInTheDocument();
  });
});
