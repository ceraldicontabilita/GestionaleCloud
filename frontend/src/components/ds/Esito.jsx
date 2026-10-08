import React from 'react';
import { Badge } from './Badge';

/**
 * Esito — la regola unica del colore (documento di design del titolare,
 * passo 4). Il colore sta su UNA cella per riga, quella che porta il
 * giudizio; le altre celle restano nere. Il testo c'è sempre: il colore non è
 * mai l'unica informazione.
 *
 * - `intervento`  rosso:  serve un intervento;
 * - `verificare`  giallo: da verificare, non urgente;
 * - `chiuso`      verde:  verificato, chiuso;
 * - `nessun_dato` grigio: nessun dato (non è un problema).
 */
export const ESITI = {
  intervento: { variant: 'danger', testo: 'Da sistemare' },
  verificare: { variant: 'warning', testo: 'Da verificare' },
  chiuso: { variant: 'success', testo: 'Chiuso' },
  nessun_dato: { variant: 'neutral', testo: 'Nessun dato' },
};

export function Esito({ esito = 'nessun_dato', children, ...props }) {
  const voce = ESITI[esito] || ESITI.nessun_dato;
  return (
    <Badge variant={voce.variant} data-esito={esito} {...props}>
      {children || voce.testo}
    </Badge>
  );
}

export default Esito;
