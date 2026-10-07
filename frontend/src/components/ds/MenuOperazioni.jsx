import React, { useEffect, useId, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown, ChevronUp, Workflow } from 'lucide-react';
import { COLORS, SHADOWS, BORDER_RADIUS } from '../../lib/utils';
import { Button } from './Button';

/**
 * MenuOperazioni — l'unico menu' delle operazioni automatiche di una pagina.
 *
 * Decisione del titolare (07/10/2026): «molte pagine con molti bottoni, mi
 * creano solo confusione: fondi i bottoni che fanno operazioni automatiche».
 * In barra restano l'azione principale (crea, registra) e i filtri; tutto
 * cio' che il gestionale fa da solo (riprocessa, rilegge, analizza, impara,
 * stampa, svuota) sta qui, in un solo posto con lo stesso nome ovunque.
 *
 * API: voci [{ id, label, Icon, onClick, to, disabled, title, pericolosa,
 * separatore }]. `separatore: true` disegna una riga; `pericolosa` colora di
 * rosso (cancella, svuota); `to` rende la voce un link interno. Ogni voce ha
 * `data-testid={id}`; il bottone e' `menu-operazioni-btn`, il pannello
 * `menu-operazioni`. Si chiude con un clic fuori, con Esc e dopo ogni voce.
 * Senza voci non si disegna niente.
 */
export function MenuOperazioni({ voci = [], label = 'Operazioni', size = 'lg', style = {}, testId = 'menu-operazioni' }) {
  const [aperto, setAperto] = useState(false);
  const contenitore = useRef(null);
  const idPannello = useId();

  useEffect(() => {
    if (!aperto) return undefined;
    const fuori = e => {
      if (contenitore.current && !contenitore.current.contains(e.target)) setAperto(false);
    };
    const tasto = e => { if (e.key === 'Escape') setAperto(false); };
    document.addEventListener('mousedown', fuori);
    document.addEventListener('keydown', tasto);
    return () => {
      document.removeEventListener('mousedown', fuori);
      document.removeEventListener('keydown', tasto);
    };
  }, [aperto]);

  const visibili = voci.filter(Boolean);
  if (visibili.length === 0) return null;

  const stileVoce = disabilitata => ({
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'flex-start',
    gap: 9,
    width: '100%',
    minHeight: 44,
    padding: '11px 16px',
    background: 'transparent',
    border: 'none',
    borderRadius: 0,
    textAlign: 'left',
    fontSize: 13,
    fontWeight: 500,
    color: disabilitata ? COLORS.textSubtle : COLORS.gray[700],
    textDecoration: 'none',
    cursor: disabilitata ? 'not-allowed' : 'pointer',
  });

  return (
    <div ref={contenitore} style={{ position: 'relative', ...style }}>
      <Button
        type="button"
        variant={aperto ? 'primary' : 'secondary'}
        size={size}
        onClick={() => setAperto(v => !v)}
        aria-haspopup="menu"
        aria-expanded={aperto}
        aria-controls={idPannello}
        data-testid={`${testId}-btn`}
      >
        <Workflow size={14} aria-hidden="true" style={{ flexShrink: 0 }} /> {label}{' '}
        {aperto ? <ChevronUp size={14} aria-hidden="true" /> : <ChevronDown size={14} aria-hidden="true" />}
      </Button>
      {aperto && (
        <div
          id={idPannello}
          role="menu"
          aria-label={label}
          data-testid={testId}
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            left: 0,
            background: COLORS.card,
            borderRadius: BORDER_RADIUS.lg,
            boxShadow: SHADOWS.xl,
            border: `1px solid ${COLORS.border}`,
            minWidth: 260,
            maxWidth: 'min(360px, calc(100vw - 32px))',
            padding: '6px 0',
            zIndex: 1500,
            maxHeight: '70vh',
            overflowY: 'auto',
          }}
        >
          {visibili.map((voce, i) => {
            if (voce.separatore) {
              return <div key={voce.id || `sep-${i}`} role="separator" style={{ height: 1, background: COLORS.border, margin: '6px 0' }} />;
            }
            const { id, label: testo, Icon, onClick, to, disabled, title, pericolosa } = voce;
            const contenuto = (
              <>
                {Icon && <Icon size={14} aria-hidden="true" style={{ flexShrink: 0 }} />}
                <span>{testo}</span>
              </>
            );
            const stile = { ...stileVoce(disabled), ...(pericolosa && !disabled ? { color: COLORS.danger } : {}) };
            if (to) {
              return (
                <Link key={id} to={to} role="menuitem" title={title} data-testid={id} style={stile} onClick={() => setAperto(false)}>
                  {contenuto}
                </Link>
              );
            }
            return (
              <button
                key={id}
                type="button"
                role="menuitem"
                title={title}
                disabled={disabled}
                data-testid={id}
                style={stile}
                onMouseEnter={e => { if (!disabled) e.currentTarget.style.background = COLORS.bgAlt; }}
                onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
                onClick={() => { setAperto(false); onClick?.(); }}
              >
                {contenuto}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default MenuOperazioni;
