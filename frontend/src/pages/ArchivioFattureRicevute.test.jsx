import { describe, expect, it } from 'vitest';

import { descriviPagamento } from './ArchivioFattureRicevute';

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
