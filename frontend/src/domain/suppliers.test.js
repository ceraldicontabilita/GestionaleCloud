import { describe, expect, it } from 'vitest';
import { isSupplierIncomplete, supplierIncompleteFields } from './suppliers';

describe('regola unica qualità fornitori', () => {
  it('usa la stessa definizione per badge e filtro', () => {
    const incomplete = { partita_iva: '01234567890', comune: 'Napoli', email: '' };
    const complete = { ragione_sociale: 'Acme Srl', partita_iva: '01234567890', comune: 'Napoli', email: 'a@acme.it', telefono: '081' };
    expect(isSupplierIncomplete(incomplete)).toBe(true);
    expect(supplierIncompleteFields(incomplete).contatti).toEqual(['email', 'telefono']);
    expect(isSupplierIncomplete(complete)).toBe(false);
  });

  it('può distinguere mancanze fiscali e di contatto', () => {
    const fields = supplierIncompleteFields({ ragione_sociale: 'Acme', partita_iva: '01234567890', comune: 'Napoli' }, { includeContacts: false });
    expect(fields.fiscali).toEqual([]);
    expect(fields.contatti).toEqual([]);
  });
});
