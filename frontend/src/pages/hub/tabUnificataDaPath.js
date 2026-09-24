const TAB_UNIFICATA = new Set([
  'dashboard', 'banca', 'assegni', 'f24', 'stipendi', 'documenti', 'paypal',
]);

/** Stesso taglio dell'hub. Niente (?:-unificata), niente (\\w+). */
export function tabUnificataDaPath(pathname = '') {
  const resto = String(pathname).replace(/^\/riconciliazione\/?/, '');
  const segmento = resto.split(/[/?#]/)[0] || '';
  if (TAB_UNIFICATA.has(segmento)) return segmento;
  return 'dashboard';
}
