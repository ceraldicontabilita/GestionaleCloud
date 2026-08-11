import { describe, expect, it } from 'vitest';
import { isRentalReconciliationMovement } from './RiconciliazioneUnificata';

describe('ambito riconciliazione noleggio', () => {
  it('riconosce soltanto le controparti di noleggio note', () => {
    expect(isRentalReconciliationMovement({ causale: 'BONIFICO LEASYS fatture luglio' })).toBe(true);
    expect(isRentalReconciliationMovement({ beneficiario: 'ARVAL SERVICE LEASE ITALIA SPA' })).toBe(true);
    expect(isRentalReconciliationMovement({ descrizione: 'Pagamento fornitore generico' })).toBe(false);
  });
});
