import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { ConfrontoIvaCommercialista, ScadenzeIvaMensili } from './IvaAuditSections';

describe('Prospetti IVA: periodi non conclusi', () => {
  it('non trasforma un mese futuro in credito zero', () => {
    render(
      <>
        <ConfrontoIvaCommercialista
          anno={2026}
          loading={false}
          error={null}
          dati={{
            mensile: [{
              mese: 8,
              mese_nome: 'Agosto',
              stato_calcolo: 'NON_CALCOLATO',
              periodo_calcolato: false,
              iva_debito_corrispettivi: null,
              iva_credito_fatture: null,
              saldo: null,
              num_fatture: 0,
              importo_f24_commercialista: null,
            }],
            totali: {},
          }}
        />
        <ScadenzeIvaMensili
          anno={2026}
          loading={false}
          error={null}
          dati={{
            scadenze: [{
              mese: 8,
              mese_nome: 'Agosto',
              data_scadenza: '2026-09-16',
              stato: 'NON_CALCOLATO',
              saldo_cents: null,
              iva_debito: null,
              iva_credito: null,
              saldo_progressivo: null,
            }],
          }}
        />
      </>,
    );

    const confronto = screen.getByTestId('iva-confronto-commercialista');
    expect(within(confronto).getByText('Non calcolato')).toBeInTheDocument();
    expect(within(confronto).getAllByText('—').length).toBeGreaterThanOrEqual(5);

    const scadenze = screen.getByTestId('iva-scadenze-mensili');
    expect(within(scadenze).getByText('Non calcolato')).toBeInTheDocument();
    expect(within(scadenze).getByText((_, element) => element.textContent === 'Debito: —')).toBeInTheDocument();
    expect(within(scadenze).queryByText('Credito riportato')).not.toBeInTheDocument();
  });
});
