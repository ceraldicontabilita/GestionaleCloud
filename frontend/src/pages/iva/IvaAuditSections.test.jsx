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
              stato_periodo: 'NON_ANCORA_DOVUTO',
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
    expect(within(confronto).getByText('Non ancora dovuto')).toBeInTheDocument();
    expect(within(confronto).getAllByText('—').length).toBeGreaterThanOrEqual(3);

    const scadenze = screen.getByTestId('iva-scadenze-mensili');
    expect(within(scadenze).getByText('Non calcolato')).toBeInTheDocument();
    expect(within(scadenze).getByText((_, element) => element.textContent === 'Debito: —')).toBeInTheDocument();
    expect(within(scadenze).queryByText('Credito riportato')).not.toBeInTheDocument();
  });
});

describe('Confronto IVA: base completa del mese', () => {
  it('distingue tutte le fatture, quelle con IVA e quelle già liquidate', () => {
    render(
      <ConfrontoIvaCommercialista
        anno={2026}
        loading={false}
        error={null}
        dati={{
          mensile: [{
            mese: 7,
            mese_nome: 'Luglio',
            stato_calcolo: 'CALCOLATA',
            periodo_calcolato: true,
            iva_debito_corrispettivi: 6211.86,
            iva_credito_fatture: 3241.46,
            saldo: 2970.40,
            num_fatture: 108,
            fatture_con_iva_competenza: 97,
            fatture_gia_liquidate: 84,
            fatture_da_classificare: 11,
            importo_f24_commercialista: null,
            quietanza_presente: false,
            verificato_banca: false,
            lipe: { stato: 'LIPE_ESTRATTA', vp4: 6211.86, vp5: 3241.46, coerente_gestionale: true, page_number: 2 },
          }],
          totali: {},
        }}
      />,
    );

    const confronto = screen.getByTestId('iva-confronto-commercialista');
    expect(within(confronto).getByText(/108 fatture · 97 con IVA · 84 già liquidate · 11 da verificare/)).toBeInTheDocument();
    expect(within(confronto).getByText(/Esigibile VP4 € 6.211,86/)).toBeInTheDocument();
    expect(within(confronto).getByText(/Detraibile VP5 € 3.241,46/)).toBeInTheDocument();
    expect(within(confronto).getByText(/uguale al gestionale · pag. 2/)).toBeInTheDocument();
    expect(within(confronto).getByText(/Quietanza e banca provano il pagamento/)).toBeInTheDocument();
  });

  it('mostra i valori OCR ma richiede verifica', () => {
    render(<ConfrontoIvaCommercialista anno={2026} loading={false} error={null} dati={{
      mensile: [{
        mese: 7, mese_nome: 'Luglio', stato_calcolo: 'CALCOLATA', periodo_calcolato: true,
        iva_debito_corrispettivi: 100, iva_credito_fatture: 20, saldo: 80,
        lipe: { stato: 'LIPE_DA_VERIFICARE', vp4: 100, vp5: 20, page_number: 1 },
      }],
      totali: {},
    }} />);

    const confronto = screen.getByTestId('iva-confronto-commercialista');
    expect(within(confronto).getByText(/Esigibile VP4 € 100,00/)).toBeInTheDocument();
    expect(within(confronto).getByText(/Detraibile VP5 € 20,00/)).toBeInTheDocument();
    expect(within(confronto).getByText(/OCR da verificare · pag. 1/)).toBeInTheDocument();
    expect(within(confronto).getByText('LIPE da verificare')).toBeInTheDocument();
  });

  it('mostra il modello del periodo ma non attribuisce quietanza e banca a un codice IVA assente', () => {
    render(<ConfrontoIvaCommercialista anno={2026} loading={false} error={null} dati={{
      mensile: [{
        mese: 1, mese_nome: 'Gennaio', stato_calcolo: 'NON_CALCOLATO',
        periodo_calcolato: false, stato_f24: 'f24_periodo_senza_codice_iva',
        codice_tributo_iva: '6001', importo_f24_commercialista: null,
        quietanza_presente: false, verificato_banca: false,
        modelli_f24_periodo: [{ file: '2026-01 Gennaio - F24.pdf' }],
        lipe: {
          stato: 'LIPE_COPIE_COERENTI', vp4: 5047.43, vp5: 12779.61,
          numero_copie: 3, page_number: 1,
        },
      }],
      totali: {},
    }} />);

    const confronto = screen.getByTestId('iva-confronto-commercialista');
    expect(within(confronto).getByText('Modello del periodo presente')).toBeInTheDocument();
    expect(within(confronto).getByText('codice 6001 assente')).toBeInTheDocument();
    expect(within(confronto).getByText(/Non attribuibile all’IVA/)).toBeInTheDocument();
    expect(within(confronto).getByText(/3 copie coerenti, provenienze conservate/)).toBeInTheDocument();
    expect(within(confronto).queryByText('Banca: verificata')).not.toBeInTheDocument();
  });
});
