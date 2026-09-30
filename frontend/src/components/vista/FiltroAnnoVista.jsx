import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import { annoDelFiltro } from '../../lib/vista';
import { COLORS, FONT } from '../../lib/utils';

/**
 * Filtro anno delle viste. Un solo anno globale (selettore in alto, `ANNO`)
 * alimenta tutte le viste; qui si puo' solo restringere a quell'anno o
 * allargare a «Tutti gli anni», e la scelta resta nell'indirizzo
 * (`?anno=tutti`), quindi il link si condivide identico.
 *
 * Hook `useAnnoVista()` per le pagine, componente per la riga di filtri.
 */
export function useAnnoVista() {
  const { anno: annoGlobale } = useAnnoGlobale();
  const [params, setParams] = useSearchParams();
  const parametro = params.get('anno');
  const anno = annoDelFiltro(annoGlobale, parametro);
  const imposta = tutti => {
    const nuovi = new URLSearchParams(params);
    if (tutti) nuovi.set('anno', 'tutti'); else nuovi.delete('anno');
    setParams(nuovi, { replace: true });
  };
  return { anno, annoGlobale, tutti: anno === null, imposta };
}

const chip = attivo => ({
  minHeight: 44, minWidth: 44, padding: '0 14px', borderRadius: 999, cursor: 'pointer',
  border: `1px solid ${attivo ? COLORS.primary : COLORS.border}`,
  background: attivo ? COLORS.primarySoft : COLORS.card,
  color: attivo ? COLORS.primaryDark : COLORS.text,
  fontWeight: attivo ? 700 : 500, fontSize: 13.5, fontFamily: FONT.family,
});

export default function FiltroAnnoVista({ stato }) {
  const { annoGlobale, tutti, imposta } = stato;
  return (
    <div role="group" aria-label="Anno" data-testid="filtro-anno-vista"
      style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
      <button type="button" style={chip(!tutti)} aria-pressed={!tutti} onClick={() => imposta(false)}>
        Anno {annoGlobale}
      </button>
      <button type="button" style={chip(tutti)} aria-pressed={tutti} onClick={() => imposta(true)}>
        Tutti gli anni
      </button>
      <span style={{ fontSize: 12.5, color: COLORS.textMuted }}>
        L'anno si cambia dal selettore in alto.
      </span>
    </div>
  );
}
