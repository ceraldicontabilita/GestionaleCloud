import { describe, expect, it } from 'vitest';

import { descriviPagamento, puoAssociareAssegno } from './ArchivioFattureRicevute';

describe('descriviPagamento', () => {
  it('non trasforma lo stato storico pagata in una prova di pagamento', () => {
    expect(descriviPagamento({ pagato: true })).toMatchObject({
      label: 'Pagamento da verificare',
      verified: false,
      variant: 'warning',
    });
  });

  it('presenta il metodo del fornitore solo come previsione', () => {
    expect(descriviPagamento({ fornitore_metodo_pagamento: 'contanti' })).toMatchObject({
      label: 'Previsto: Cassa',
      verified: false,
      variant: 'neutral',
    });
  });

  it('mostra riferimento e conferma di un assegno riscontrato', () => {
    expect(descriviPagamento({
      payment_evidence: [{
        type: 'assegno',
        status: 'confirmed',
        reference: '0208769328-01',
        bank_movement_id: 'mov-1',
      }],
    })).toMatchObject({
      label: 'Assegno n. 0208769328-01',
      verified: true,
      variant: 'success',
    });
  });

  it('distingue una registrazione bancaria non ancora riscontrata', () => {
    expect(descriviPagamento({ prima_nota_banca_id: 'pn-1' })).toMatchObject({
      label: 'Banca · da riscontrare',
      verified: false,
      variant: 'warning',
    });
  });

  it('blocca la presentazione positiva in presenza di conflitto', () => {
    expect(descriviPagamento({
      payment_allocation_status: 'conflicting',
      allocation_conflict_reason: 'quota_supera_totale_fattura',
    })).toMatchObject({
      label: 'Conflitto da verificare',
      verified: false,
      variant: 'danger',
    });
  });
});

describe('puoAssociareAssegno', () => {
  it('consente l azione soltanto su una fattura con debito positivo', () => {
    expect(puoAssociareAssegno({ tipo_documento: 'TD01', total_amount: 100 })).toBe(true);
    expect(puoAssociareAssegno({ tipo_documento: 'TD01', total_amount: 0 })).toBe(false);
  });

  it.each(['TD04', 'TD08'])('non mostra Abbina sulle note di credito %s', tipo => {
    expect(puoAssociareAssegno({ tipo_documento: tipo, total_amount: 100 })).toBe(false);
  });
});
