export function calcolaProduzione(totaleG, recuperoRichiestoG, disponibileG) {
  const totale = Math.max(0, Number(totaleG) || 0);
  const recuperato = Math.min(
    totale,
    Math.max(0, Number(recuperoRichiestoG) || 0),
    Math.max(0, Number(disponibileG) || 0),
  );
  return { totale, recuperato, nuovo: totale - recuperato };
}

export function scalaIngredienti(ingredienti, pesoBaseG, pesoNuovoG) {
  return Object.entries(ingredienti).map(([nome, quantita]) =>
    typeof quantita === "number"
      ? { n: nome, q: (quantita / pesoBaseG) * pesoNuovoG }
      : { n: nome, qb: true },
  );
}
