// Proiezione dei soli dati già restituiti dal server; nessun matching o stato
// pagamento viene inventato nel browser. I totali sommano le righe visibili.
export function filtraPaghe(archivio, anno, mese, stato) {
  const righe = archivio.filter(r => (!anno || Number(r.anno) === Number(anno))
    && (!mese || Number(r.mese) === Number(mese)) && (!stato || r.stato === stato));
  const totali = { buste: 0, bonifici: 0, acconti: 0, saldo: 0,
    pagati: 0, parziali: 0, da_pagare: 0, senza_busta: 0, associati: 0, da_verificare: 0 };
  const countKey = { pagato: 'pagati', parziale: 'parziali', da_pagare: 'da_pagare', bonifico_senza_busta: 'senza_busta' };
  for (const r of righe) {
    for (const [total, field] of [['buste', 'busta'], ['bonifici', 'bonifico'], ['acconti', 'acconti'], ['saldo', 'saldo']]) {
      totali[total] += Math.round((Number(r[field]) || 0) * 100);
    }
    if (countKey[r.stato]) totali[countKey[r.stato]] += 1;
    if (['pagato', 'parziale', 'bonifico_senza_busta'].includes(r.stato)) {
      totali[r.associato ? 'associati' : 'da_verificare'] += 1;
    }
  }
  for (const key of ['buste', 'bonifici', 'acconti', 'saldo']) totali[key] /= 100;
  return { righe, totali, count: righe.length };
}
