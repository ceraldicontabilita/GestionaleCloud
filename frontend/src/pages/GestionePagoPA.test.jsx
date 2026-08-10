import { describe, expect, it } from 'vitest';

import { paymentAmountParts, paymentKindLabel } from './GestionePagoPA';

describe('GestionePagoPA - semantica documentale', () => {
  it('distingue le famiglie CBILL, MAV, RAV e bollettino postale', () => {
    expect(paymentKindLabel('RICEVUTA_CBILL')).toBe('CBILL');
    expect(paymentKindLabel('RICEVUTA_MAV')).toBe('MAV');
    expect(paymentKindLabel('RICEVUTA_RAV')).toBe('RAV');
    expect(paymentKindLabel('RICEVUTA_BOLLETTINO_POSTALE')).toBe('Bollettino postale');
  });

  it('mostra separati importo obbligo, commissione e totale banca', () => {
    expect(paymentAmountParts({
      operation_amount: 126.68, fee_amount: 2.85, bank_debit_total: 129.53,
    })).toEqual({ operation: 126.68, fee: 2.85, bankTotal: 129.53 });
  });
});
