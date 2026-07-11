import React, { useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Compass } from 'lucide-react';
import { NAV_TUTTE } from '../navigation.config';

/**
 * Pagina 404 reale. Prima qualunque route sconosciuta veniva reindirizzata
 * in silenzio alla Dashboard: un link sbagliato sembrava "un bottone che
 * non funziona" e il difetto restava invisibile. Ora l'URL errato si VEDE
 * (e finisce in console), con i link alle sezioni vere per riprendersi.
 */
export default function PaginaNonTrovata() {
  const location = useLocation();
  const url = location.pathname + location.search + location.hash;

  useEffect(() => {
    console.warn(`[404] Route non trovata: ${url}`);
  }, [url]);

  return (
    <div style={{ maxWidth: 720, margin: '40px auto', padding: '0 16px' }}>
      <div
        data-testid="pagina-non-trovata"
        style={{
          background: 'white',
          border: '1px solid #e2e8f0',
          borderRadius: 12,
          padding: 24,
          textAlign: 'center',
        }}
      >
        <Compass size={40} style={{ color: '#0f2744', marginBottom: 8 }} />
        <h1 style={{ margin: '0 0 6px', fontSize: 22, color: '#0f2744' }}>Pagina non trovata</h1>
        <p style={{ margin: '0 0 4px', color: '#475569', fontSize: 14 }}>
          L'indirizzo richiesto non esiste nel gestionale:
        </p>
        <code
          style={{
            display: 'inline-block',
            background: '#f1f5f9',
            borderRadius: 6,
            padding: '4px 10px',
            fontSize: 13,
            color: '#b91c1c',
            marginBottom: 16,
            maxWidth: '100%',
            overflowWrap: 'anywhere',
          }}
        >
          {url}
        </code>
        <p style={{ margin: '0 0 14px', color: '#64748b', fontSize: 13 }}>
          Se ci sei arrivato da un bottone o un link interno, segnalalo: è un
          collegamento da correggere, non un tuo errore.
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center' }}>
          {NAV_TUTTE.filter(i => i.to).map(i => (
            <Link
              key={i.to}
              to={i.to}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                padding: '7px 12px',
                borderRadius: 8,
                border: '1px solid #e2e8f0',
                color: '#0f2744',
                textDecoration: 'none',
                fontSize: 13,
                fontWeight: 600,
                background: '#f8fafc',
              }}
            >
              <i.Icon size={14} />
              {i.label}
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
