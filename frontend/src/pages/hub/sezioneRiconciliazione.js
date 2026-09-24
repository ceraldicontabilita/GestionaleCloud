/** Primo pezzo dopo /riconciliazione. Uguaglianza, non sottostringa. */
export function sezioneRiconciliazione(pathname = '') {
  const resto = String(pathname).replace(/^\/riconciliazione\/?/, '');
  const segmento = resto.split(/[/?#]/)[0] || '';
  if (segmento === 'gestione-assegni') return 'assegni';
  if (segmento === 'archivio-bonifici') return 'bonifici';
  return segmento;
}
