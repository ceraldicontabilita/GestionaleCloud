export const SEZIONI_CONTABILITA = [
  'piano-conti', 'bilancio', 'verifica', 'giornale', 'controllo', 'calendario',
  'cespiti', 'finanziaria', 'chiusura', 'budget', 'mutui', 'avanzata', 'utile',
  'previsioni-acquisti', 'dati-isa',
];

const ALIAS = {
  'piano-dei-conti': 'piano-conti',
  'bilancio-verifica': 'verifica',
  'controllo-mensile': 'controllo',
  'calendario-fiscale': 'calendario',
  'contabilita-avanzata': 'avanzata',
  'utile-obiettivo': 'utile',
};

function foglia(pathname = '') {
  const sotto = String(pathname).match(/\/contabilita\/([^/?#]+)/);
  if (sotto) return sotto[1];
  const pezzi = String(pathname).replace(/\/$/, '').split(/[/?#]/).filter(Boolean);
  return pezzi.pop() || '';
}

export function sezioneContabilita(pathname = '') {
  const raw = foglia(pathname);
  if (!raw || raw === 'contabilita') return 'piano-conti';
  const tab = ALIAS[raw] || raw;
  return SEZIONI_CONTABILITA.includes(tab) ? tab : 'piano-conti';
}

export function sezioneContabilitaSconosciuta(pathname = '') {
  const raw = foglia(pathname);
  if (!raw || raw === 'contabilita') return false;
  const tab = ALIAS[raw] || raw;
  return !SEZIONI_CONTABILITA.includes(tab);
}
