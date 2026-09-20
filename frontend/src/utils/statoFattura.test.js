/**
 * «È pagata?» deve dare la stessa risposta su ogni schermo.
 *
 * Il 20/09/2026 non la dava: 639 fatture (311.838,20 €) hanno solo
 * `stato = "pagata"`, e nessuna pagina guardava quel campo. Qui si prova che
 * ogni scrittura presente in archivio viene riconosciuta, e soprattutto il
 * caso da 311 mila euro.
 */
import { describe, expect, it } from 'vitest';
import {
  ePagata, eAnnullata, eParziale, statoPagamento, ASPETTO_STATO,
} from './statoFattura';

describe('stato di pagamento di una fattura', () => {
  it.each([
    ['stato = pagata (639 fatture)', { stato: 'pagata' }],
    ['stato_pagamento = pagata (46)', { stato_pagamento: 'pagata' }],
    ['stato_pagamento = pagato (3)', { stato_pagamento: 'pagato' }],
    ['pagato = true (46)', { pagato: true }],
    ['paid = true (46)', { paid: true }],
    ['payment_status = paid (29)', { payment_status: 'paid' }],
  ])('riconosce %s', (_nome, fattura) => {
    expect(ePagata(fattura)).toBe(true);
    expect(statoPagamento(fattura)).toBe('pagata');
  });

  it('il caso da 311.838,20 €: solo `stato`, nessun `pagato`', () => {
    const fattura = { stato: 'pagata', total_amount: 488.01 };
    expect('pagato' in fattura).toBe(false);
    expect(ePagata(fattura)).toBe(true);
  });

  it('una fattura senza nessuno stato è «da verificare», non un debito', () => {
    const fattura = { invoice_number: '1/2026', total_amount: 100 };
    expect(ePagata(fattura)).toBe(false);
    expect(statoPagamento(fattura)).toBe('da_verificare');
  });

  it('da_pagare resta da_pagare', () => {
    expect(statoPagamento({ stato: 'da_pagare' })).toBe('da_pagare');
    expect(ePagata({ stato: 'da_pagare' })).toBe(false);
  });

  it('parziale non è pagata', () => {
    expect(eParziale({ stato: 'parziale' })).toBe(true);
    expect(ePagata({ stato: 'parziale' })).toBe(false);
  });

  it('annullata batte pagata: una stornata non entra negli incassi', () => {
    const f = { stato: 'annullata', pagato: true };
    expect(eAnnullata(f)).toBe(true);
    expect(ePagata(f)).toBe(false);
    expect(statoPagamento(f)).toBe('annullata');
  });

  it('basta un campo solo: pretendere l\'accordo perderebbe le 639', () => {
    expect(ePagata({ stato: 'pagata', stato_pagamento: 'da_verificare' })).toBe(true);
  });

  it('maiuscole e spazi non cambiano la risposta', () => {
    expect(ePagata({ stato: '  PAGATA ' })).toBe(true);
  });

  it('`status` è lo stato del documento, non del pagamento', () => {
    // 1.127 archiviata + 555 archived + 624 imported, zero «paid»
    expect(ePagata({ status: 'archiviata' })).toBe(false);
    expect(ePagata({ status: 'imported' })).toBe(false);
  });

  it('`stato_finanziario = riconciliato` non vuol dire pagata', () => {
    expect(ePagata({ stato_finanziario: 'riconciliato' })).toBe(false);
  });

  it('ogni stato possibile ha un aspetto: nessun badge vuoto', () => {
    const stati = ['pagata', 'parziale', 'da_pagare', 'annullata', 'da_verificare'];
    stati.forEach((s) => {
      expect(ASPETTO_STATO[s]).toBeDefined();
      expect(ASPETTO_STATO[s].testo).toBeTruthy();
    });
  });

  it('niente esplode su input mancante', () => {
    expect(ePagata(null)).toBe(false);
    expect(ePagata(undefined)).toBe(false);
    expect(statoPagamento({})).toBe('da_verificare');
  });
});
