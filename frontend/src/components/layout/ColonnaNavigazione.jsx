import React, { memo, useEffect, useRef } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ExternalLink } from 'lucide-react';
import { COLORS } from '../../lib/utils';
import { gruppiVisibili, voceDi } from '../../navigation.config';
import { useAuth } from '../../contexts/AuthContext.jsx';

/**
 * Colonna di navigazione a sinistra, sempre visibile su desktop: tutte le
 * sezioni in vista, raggruppate per momento del lavoro, senza menù a tendina.
 * Se non ci stanno, la colonna scorre per conto suo.
 *
 * La voce attiva e' una sola, quella col prefisso d'indirizzo piu' lungo
 * (`voceDi`): su /riconciliazione/f24 e' accesa F24, non Riconciliazione.
 * Lo stato attivo e' `aria-current="page"`, e la grafica lo legge da li'.
 */
const ColonnaNavigazione = memo(function ColonnaNavigazione() {
  const { pathname } = useLocation();
  const { isAdmin } = useAuth();
  const attiva = voceDi(pathname)?.voce;
  const colonna = useRef(null);

  // La voce accesa resta in vista anche quando sta in fondo alla colonna.
  useEffect(() => {
    colonna.current?.querySelector('[aria-current="page"]')?.scrollIntoView?.({ block: 'nearest' });
  }, [attiva?.to]);

  return (
    <nav ref={colonna} className="colonna-nav" aria-label="Sezioni del gestionale" data-testid="colonna-navigazione">
      {gruppiVisibili(isAdmin).map(gruppo => (
        <section
          key={gruppo.id}
          className="colonna-nav-gruppo"
          data-testid={`nav-gruppo-${gruppo.id}`}
          style={{ '--banda': gruppo.colore }}
        >
          <h2 className="colonna-nav-titolo">
            <span className="colonna-nav-punto" style={{ background: gruppo.colore }} aria-hidden="true" />
            {gruppo.titolo}
          </h2>
          <ul>
            {gruppo.voci.map(({ to, href, label, Icon, external }) => (
              <li key={to || href}>
                {external ? (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="colonna-nav-voce"
                    data-testid={`nav-${label.toLowerCase().replace(/\s+/g, '-')}`}
                  >
                    <Icon size={15} style={{ color: gruppo.colore }} />
                    <span>{label}</span>
                    <ExternalLink size={12} className="colonna-nav-esterno" aria-label="si apre in una scheda nuova" />
                  </a>
                ) : (
                  <Link
                    to={to}
                    className="colonna-nav-voce"
                    aria-current={attiva?.to === to ? 'page' : undefined}
                    data-testid={`nav-${label.toLowerCase().replace(/\s+/g, '-')}`}
                  >
                    <Icon size={15} style={{ color: gruppo.colore }} />
                    <span>{label}</span>
                  </Link>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}
      <style>{`
        .colonna-nav {
          position: fixed;
          top: var(--topnav-height);
          bottom: 0;
          left: 0;
          width: var(--colonna-nav-larghezza);
          overflow-y: auto;
          background: ${COLORS.card};
          border-right: 1px solid ${COLORS.border};
          padding: 12px 10px 90px;
          box-sizing: border-box;
          z-index: 900;
        }
        .colonna-nav-gruppo + .colonna-nav-gruppo { margin-top: 14px; }
        .colonna-nav-titolo {
          display: flex;
          align-items: center;
          gap: 7px;
          margin: 0 0 4px;
          padding: 0 8px;
          font-size: 10.5px;
          font-weight: 800;
          letter-spacing: 0.06em;
          color: ${COLORS.textMuted};
        }
        .colonna-nav-punto { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
        .colonna-nav ul { list-style: none; margin: 0; padding: 0; }
        .colonna-nav-voce {
          display: flex;
          align-items: center;
          gap: 8px;
          min-height: 32px;
          padding: 5px 8px;
          border-left: 2px solid color-mix(in srgb, var(--banda) 26%, transparent);
          border-radius: 0 6px 6px 0;
          color: ${COLORS.gray[700]};
          font-size: 13.5px;
          font-weight: 500;
          text-decoration: none;
        }
        .colonna-nav-voce:hover { background: ${COLORS.bg}; border-left-color: var(--banda); }
        .colonna-nav-voce:focus-visible { outline: 2px solid ${COLORS.primaryLight}; outline-offset: -2px; }
        /* Come nell'artefatto: la voce accesa prende il colore della sua famiglia. */
        .colonna-nav-voce[aria-current="page"] {
          background: color-mix(in srgb, var(--banda) 13%, transparent);
          color: var(--banda);
          border-left-color: var(--banda);
          font-weight: 700;
        }
        .colonna-nav-esterno { margin-left: auto; color: ${COLORS.textSubtle}; }
        @media (max-width: 768px) { .colonna-nav { display: none; } }
      `}</style>
    </nav>
  );
});

export default ColonnaNavigazione;
