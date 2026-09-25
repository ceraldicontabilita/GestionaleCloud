export function primoSegmentoDopo(pathname, prefisso, ids, fallback) {
  const escaped = String(prefisso).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const resto = String(pathname).replace(new RegExp(`^${escaped}/?`), '');
  const segmento = resto.split(/[/?#]/)[0] || '';
  if (ids.includes(segmento)) return segmento;
  return fallback;
}

export function sezioneDocumenti(pathname = '') {
  const p = String(pathname);
  if (p === '/import-documenti' || p.startsWith('/import-documenti/')) return 'import';
  return primoSegmentoDopo(p, '/documenti', ['atti', 'drive', 'archivio', 'import'], 'import');
}

export function sezioneStrumenti(pathname = '') {
  return primoSegmentoDopo(pathname, '/strumenti', ['verifica', 'commercialista', 'pianificazione', 'visure'], 'verifica');
}

export function sezioneFatture(pathname = '') {
  return primoSegmentoDopo(pathname, '/fatture', ['corrispettivi'], 'archivio');
}

export function sezionePrimaNota(pathname = '') {
  return primoSegmentoDopo(pathname, '/prima-nota', ['pulizia'], 'prima-nota');
}

export function tabUnificataDaPath(pathname = '') {
  return primoSegmentoDopo(pathname, '/riconciliazione', [
    'dashboard',
    'banca',
    'assegni',
    'f24',
    'stipendi',
    'documenti',
    'paypal',
  ], 'dashboard');
}
