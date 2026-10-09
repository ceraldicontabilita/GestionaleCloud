// Una proposta di persona non e' una prova del mese pagato.
export function sceltaIniziale(bonifico) {
  const p = bonifico.proposta || {};
  const periodo = p.anno && p.mese;
  return {
    dipendente_id: p.dipendente_id || '',
    tipo: periodo ? (p.tipo || 'stipendio') : 'acconto',
    conciliazione_id: '', anno: periodo ? p.anno : '', mese: periodo ? p.mese : '',
  };
}

export function sceltaCandidato(bonifico, corrente, candidato) {
  // Il candidato cambia la persona; non sovrascrive tipo e periodo scelti.
  return { ...(corrente || sceltaIniziale(bonifico)), dipendente_id: candidato.dipendente_id };
}

export function propostaIntatta(bonifico, scelta) {
  const iniziale = sceltaIniziale(bonifico);
  return Boolean(iniziale.dipendente_id) && ['dipendente_id', 'tipo', 'anno', 'mese']
    .every(campo => scelta?.[campo] === iniziale[campo]);
}
