import React, { Suspense, lazy, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { X } from 'lucide-react';
import { PageLoader } from '../ds';
import { ScadenzaF24 } from './Scadenzario';
import { COLORS, FONT } from '../../lib/utils';

const F24Dettaglio = lazy(() => import('../../pages/F24Scheda.jsx').then(m => ({ default: m.F24Dettaglio })));

/**
 * Pannello laterale di un F24: lo stesso dettaglio della vista `/fiscale/f24/:id`
 * (righe tributo, originale, riscontro con la banca), aperto sopra la pagina
 * Tributi da qualunque riga che porti un protocollo. Non ha dati propri.
 */
export default function PannelloF24({ id, titolo = 'Dettaglio F24', onClose }) {
  const chiudi = useRef(null);
  useEffect(() => {
    const tasto = e => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', tasto);
    chiudi.current?.focus();
    return () => document.removeEventListener('keydown', tasto);
  }, [onClose]);

  return (
    <div
      style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(20,20,19,.35)' }}
      onClick={onClose} data-testid="pannello-f24-sfondo"
    >
      <aside
        role="dialog" aria-modal="true" aria-label={titolo} data-testid="pannello-f24"
        onClick={e => e.stopPropagation()}
        style={{
          position: 'absolute', top: 0, right: 0, bottom: 0, width: 'min(760px, 100vw)', overflowY: 'auto',
          background: COLORS.bg || '#faf9f5', boxShadow: '-8px 0 24px rgba(20,20,19,.15)', fontFamily: FONT.family,
        }}
      >
        <div style={{
          position: 'sticky', top: 0, zIndex: 1, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          gap: 8, padding: '8px 16px', background: COLORS.card, borderBottom: `1px solid ${COLORS.border}`,
        }}>
          <strong>{titolo}</strong>
          <span style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Link to={`/fiscale/f24/${encodeURIComponent(id)}`} style={{ fontSize: 13 }}>Apri come pagina</Link>
            <button
              type="button" ref={chiudi} onClick={onClose} aria-label="Chiudi il pannello"
              style={{ minWidth: 44, minHeight: 44, border: 'none', background: 'transparent', cursor: 'pointer' }}
            ><X size={20} aria-hidden="true" /></button>
          </span>
        </div>
        <div style={{ padding: 16 }}>
          <Suspense fallback={<PageLoader />}><F24Dettaglio id={id} incorporato /></Suspense>
          <section style={{ marginTop: 14 }} aria-label="Scadenza e ravvedimento">
            <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>Scadenza e ravvedimento</h3>
            <ScadenzaF24 id={id} />
          </section>
        </div>
      </aside>
    </div>
  );
}
