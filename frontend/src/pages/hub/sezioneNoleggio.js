const TAB_IDS = ['flotta', 'posizione', 'verbali', 'costi'];

export function sezioneNoleggio(pathname = '') {
  const resto = String(pathname).replace(/^\/noleggio\/?/, '');
  const segmento = resto.split(/[/?#]/)[0] || '';
  if (TAB_IDS.includes(segmento)) return segmento;
  return 'flotta';
}
