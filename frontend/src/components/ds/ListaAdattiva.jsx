import React, { useEffect, useState } from 'react';
import { COLORS, SHADOWS, BORDER_RADIUS, useIsMobile } from '../../lib/utils';
import { TableWrap, Table, Th, Td } from './Table';

/**
 * ListaAdattiva — la "ricetta Fatture" come componente unico.
 *
 * Descrivi le COLONNE una volta sola e lui disegna:
 *  - su monitor: la tabella standard del design system (Th/Td);
 *  - su telefono/tablet: una card per riga con lo schema fisso
 *    titolo in grassetto + importo grande a destra + riga di dettagli
 *    piccoli + azioni in fondo (identico alla pagina Fatture).
 *
 * Paginazione integrata: mostra `pageSize` righe e mette la barra
 * "Carica altre" SIA SOPRA che SOTTO la lista (così non devi risalire
 * tutta la pagina per caricare il blocco successivo).
 *
 * Spec colonna:
 *  { key, label, render?(item), align?, mono?, tdStyle?|fn(item),
 *    ruoloCard: 'titolo'|'sottotitolo'|'importo'|'dettaglio'|'azioni'|'omesso',
 *    iconaCard?, hideMobile? }
 */
export function ListaAdattiva({
  colonne = [],
  dati = [],
  pageSize = 50,
  chiave = (item, i) => item.id || i,
  testId,
}) {
  const isMobile = useIsMobile();
  const [visibili, setVisibili] = useState(pageSize);

  // Nuovi dati (cambio filtro/anno) → riparte dal primo blocco
  useEffect(() => {
    setVisibili(pageSize);
  }, [dati, pageSize]);

  const mostrate = dati.slice(0, visibili);
  const rimanenti = dati.length - mostrate.length;

  const valore = (col, item) => (col.render ? col.render(item) : item[col.key]);

  const BarraCaricaAltre = ({ posizione }) =>
    rimanenti > 0 ? (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          gap: 10,
          padding: '10px 0',
        }}
      >
        <button
          onClick={() => setVisibili(v => v + pageSize)}
          data-testid={testId ? `${testId}-carica-altre-${posizione}` : undefined}
          style={{
            padding: '8px 16px',
            background: '#0f2744',
            color: 'white',
            border: '1px solid #0f2744',
            borderRadius: 6,
            fontWeight: 700,
            fontSize: 12.5,
            cursor: 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          ▼ Carica altre {Math.min(pageSize, rimanenti)}
        </button>
        <button
          onClick={() => setVisibili(dati.length)}
          style={{
            padding: '8px 14px',
            background: 'white',
            color: '#0f2744',
            border: `1px solid ${COLORS.border}`,
            borderRadius: 6,
            fontWeight: 600,
            fontSize: 12.5,
            cursor: 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          Tutte ({dati.length})
        </button>
        <span style={{ fontSize: 11.5, color: COLORS.textSubtle }}>
          {mostrate.length} di {dati.length}
        </span>
      </div>
    ) : null;

  // ── VISTA MOBILE: card per riga ──────────────────────────────────────────
  if (isMobile) {
    const colTitolo = colonne.find(c => c.ruoloCard === 'titolo');
    const colSottotitolo = colonne.find(c => c.ruoloCard === 'sottotitolo');
    const colImporto = colonne.find(c => c.ruoloCard === 'importo');
    const colAzioni = colonne.find(c => c.ruoloCard === 'azioni');
    const colDettagli = colonne.filter(
      c => c.ruoloCard === 'dettaglio' && !c.hideMobile
    );

    return (
      <div data-testid={testId} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <BarraCaricaAltre posizione="sopra" />
        {mostrate.map((item, i) => (
          <div
            key={chiave(item, i)}
            style={{
              background: COLORS.card,
              borderRadius: BORDER_RADIUS.lg,
              padding: '12px 14px',
              border: `1px solid ${COLORS.border}`,
              boxShadow: SHADOWS.sm,
              minWidth: 0,
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
                gap: 8,
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                {colTitolo && (
                  <div
                    style={{
                      fontWeight: 700,
                      color: COLORS.primary,
                      fontSize: 14,
                      overflowWrap: 'anywhere',
                    }}
                  >
                    {valore(colTitolo, item)}
                  </div>
                )}
                {colSottotitolo && (
                  <div style={{ fontSize: 11, color: COLORS.textSubtle, marginTop: 2 }}>
                    {valore(colSottotitolo, item)}
                  </div>
                )}
              </div>
              {colImporto && (
                <div
                  style={{
                    fontWeight: 700,
                    fontSize: 15,
                    color: COLORS.primary,
                    whiteSpace: 'nowrap',
                    flexShrink: 0,
                  }}
                >
                  {valore(colImporto, item)}
                </div>
              )}
            </div>
            {(colDettagli.length > 0 || colAzioni) && (
              // Dettagli e azioni sulla STESSA riga: card più bassa,
              // entrano più righe per schermata
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: 8,
                  marginTop: 6,
                  minWidth: 0,
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    gap: 10,
                    rowGap: 4,
                    fontSize: 12,
                    color: COLORS.textMuted,
                    flexWrap: 'wrap',
                    minWidth: 0,
                    flex: 1,
                  }}
                >
                  {colDettagli.map(c => (
                    <span key={c.key} style={{ whiteSpace: 'nowrap' }}>
                      {c.iconaCard ? `${c.iconaCard} ` : `${c.label}: `}
                      {valore(c, item)}
                    </span>
                  ))}
                </div>
                {colAzioni && <div style={{ flexShrink: 0 }}>{valore(colAzioni, item)}</div>}
              </div>
            )}
          </div>
        ))}
        <BarraCaricaAltre posizione="sotto" />
      </div>
    );
  }

  // ── VISTA DESKTOP: tabella standard ──────────────────────────────────────
  return (
    <div data-testid={testId}>
      <BarraCaricaAltre posizione="sopra" />
      <TableWrap style={{ border: 'none', borderRadius: 0 }}>
        <Table style={{ background: 'transparent' }}>
          <thead>
            <tr>
              {colonne
                .filter(c => c.ruoloCard !== 'omesso' || c.label)
                .map(c => (
                  <Th key={c.key} align={c.align || 'left'}>
                    {c.label}
                  </Th>
                ))}
            </tr>
          </thead>
          <tbody>
            {mostrate.map((item, i) => (
              <tr
                key={chiave(item, i)}
                style={{ transition: 'background 0.15s' }}
                onMouseEnter={e => (e.currentTarget.style.background = COLORS.bgAlt)}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                {colonne
                  .filter(c => c.ruoloCard !== 'omesso' || c.label)
                  .map(c => (
                    <Td
                      key={c.key}
                      align={c.align || 'left'}
                      mono={c.mono}
                      style={typeof c.tdStyle === 'function' ? c.tdStyle(item) : c.tdStyle}
                    >
                      {valore(c, item)}
                    </Td>
                  ))}
              </tr>
            ))}
          </tbody>
        </Table>
      </TableWrap>
      <BarraCaricaAltre posizione="sotto" />
    </div>
  );
}

export default ListaAdattiva;
