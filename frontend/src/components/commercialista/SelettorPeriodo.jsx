import React from 'react';
import { CalendarRange } from 'lucide-react';

import { COLORS, BORDER_RADIUS, FONT } from '../../lib/utils';
import { Input, Select } from '../ds';
import {
  MESI, MODI_PERIODO, TRIMESTRI, calcolaPeriodo, mascheraDataIT,
} from '../../lib/periodoCommercialista';

/**
 * Il periodo dell'Area Commercialista: chip «Mese | Trimestre | Anno | Personalizzato».
 * Mese e trimestre si scelgono da tendine, l'anno anche; solo «Personalizzato» chiede due date
 * (gg/mm/aaaa). Il periodo scelto e' sempre riassunto per esteso sotto i controlli.
 *
 * `stato` = { modo, mese, trimestre, dalIT, alIT }; `anno` viene dal selettore globale.
 */
export default function SelettorPeriodo({ stato, anno, onChange, onAnno }) {
  const periodo = calcolaPeriodo({ ...stato, anno });
  const annoCorrente = new Date().getFullYear();
  const anni = Array.from({ length: 8 }, (_, i) => annoCorrente + 1 - i);
  const cambia = campi => onChange({ ...stato, ...campi });

  const chip = attivo => ({
    minHeight: 44,
    padding: '0 16px',
    borderRadius: BORDER_RADIUS.full,
    border: `1px solid ${attivo ? COLORS.primary : COLORS.border}`,
    background: attivo ? COLORS.primary : COLORS.card,
    color: attivo ? '#fff' : COLORS.text,
    fontWeight: 700,
    fontSize: 13,
    fontFamily: FONT.family,
    cursor: 'pointer',
  });
  const campo = { minHeight: 44, minWidth: 0, flex: '1 1 140px' };

  return (
    <div data-testid="selettore-periodo">
      <div role="radiogroup" aria-label="Tipo di periodo" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {MODI_PERIODO.map(m => (
          <button
            key={m.id}
            type="button"
            role="radio"
            aria-checked={stato.modo === m.id}
            data-testid={`periodo-${m.id}`}
            onClick={() => cambia({ modo: m.id })}
            style={chip(stato.modo === m.id)}
          >
            {m.label}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 12 }}>
        {stato.modo === 'mese' && (
          <Select
            aria-label="Mese"
            value={stato.mese}
            onChange={e => cambia({ mese: Number(e.target.value) })}
            style={campo}
          >
            {MESI.slice(1).map((nome, i) => (
              <option key={nome} value={i + 1}>{nome}</option>
            ))}
          </Select>
        )}
        {stato.modo === 'trimestre' && (
          <Select
            aria-label="Trimestre"
            value={stato.trimestre}
            onChange={e => cambia({ trimestre: Number(e.target.value) })}
            style={campo}
          >
            {TRIMESTRI.map(t => (
              <option key={t.id} value={t.id}>{t.label}</option>
            ))}
          </Select>
        )}
        {stato.modo !== 'personalizzato' && (
          <Select
            aria-label="Anno"
            value={anno}
            onChange={e => onAnno(Number(e.target.value))}
            style={{ ...campo, flex: '0 1 120px' }}
          >
            {anni.map(a => (
              <option key={a} value={a}>{a}</option>
            ))}
          </Select>
        )}
        {stato.modo === 'personalizzato' && (
          <>
            <label style={{ ...campo, display: 'block', fontSize: 12, color: COLORS.textMuted }}>
              Dal (gg/mm/aaaa)
              <Input
                aria-label="Dal"
                inputMode="numeric"
                placeholder="gg/mm/aaaa"
                value={stato.dalIT}
                onChange={e => cambia({ dalIT: mascheraDataIT(e.target.value) })}
                error={!!stato.dalIT && !periodo.valido}
                style={{ minHeight: 44, marginTop: 4 }}
              />
            </label>
            <label style={{ ...campo, display: 'block', fontSize: 12, color: COLORS.textMuted }}>
              Al (gg/mm/aaaa)
              <Input
                aria-label="Al"
                inputMode="numeric"
                placeholder="gg/mm/aaaa"
                value={stato.alIT}
                onChange={e => cambia({ alIT: mascheraDataIT(e.target.value) })}
                error={!!stato.alIT && !periodo.valido}
                style={{ minHeight: 44, marginTop: 4 }}
              />
            </label>
          </>
        )}
      </div>

      <p
        data-testid="periodo-riepilogo"
        role={periodo.valido ? undefined : 'alert'}
        style={{
          margin: '12px 0 0', display: 'flex', alignItems: 'center', gap: 8, fontSize: 13,
          color: periodo.valido ? COLORS.textMuted : COLORS.danger,
        }}
      >
        <CalendarRange size={16} aria-hidden="true" />
        {periodo.valido
          ? `${periodo.etichetta}: dal ${periodo.dal.split('-').reverse().join('/')} al ${periodo.al.split('-').reverse().join('/')}`
          : periodo.errore}
      </p>
    </div>
  );
}
