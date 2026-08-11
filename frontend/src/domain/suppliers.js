/** Regola unica per il badge, filtro e contatore fornitori incompleti. */
export const supplierIncompleteFields = (supplier = {}, { includeContacts = true } = {}) => {
  const value = (...keys) => keys.some(key => String(supplier[key] ?? '').trim() !== '');
  const fiscali = [];
  if (!value('ragione_sociale', 'denominazione', 'nome', 'name')) fiscali.push('ragione_sociale');
  if (!value('partita_iva', 'piva', 'vat_number', 'vat')) fiscali.push('partita_iva');
  if (!value('comune', 'city')) fiscali.push('comune');
  const contatti = [];
  if (includeContacts && !value('email', 'pec')) contatti.push('email');
  if (includeContacts && !value('telefono', 'phone', 'telephone')) contatti.push('telefono');
  return { fiscali, contatti };
};

export const isSupplierIncomplete = (supplier, options) => {
  const fields = supplierIncompleteFields(supplier, options);
  return fields.fiscali.length > 0 || fields.contatti.length > 0;
};

export const isSupplierFiscalIncomplete = supplier =>
  supplierIncompleteFields(supplier, { includeContacts: false }).fiscali.length > 0;
