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
 * Paginazione integrata A PAGINE NUMERATE (1 · 2 · 3 …): ogni pagina
 * mostra `pageSize` righe e la barra dei numeri sta SIA SOPRA che SOTTO
 * la lista (così non devi risalire tutta la pagina per cambiare blocco).
 * La pagina corrente NON si resetta quando una singola riga viene
 * aggiornata sul posto (toggle magazzino, cambio metodo, modifica):
 * si torna a pagina 1 solo se cambia il numero di righe (filtri/anno).
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
  const [pagina, setPagina] = useState(1);

  // Torna a pagina 1 SOLO quando cambia il numero di righe (cambio
  // filtro/anno). Un aggiornamento sul posto di una riga (toggle magazzino,
  // cambio metodo, modifica) produce un nuovo array della STESSA lunghezza:
  // la pagina corrente non deve resettarsi (richiesta utente 10/07: "dalla
  // seconda pagina in poi quando cambio da in magazzino a escludi mi
  // restituisce il ricaricamento della pagina").
  useEffect(() => {
    setPagina(1);
  }, [dati.length, pageSize]);

  const totPagine = Math.max(1, Math.ceil(dati.length / pageSize));
  const paginaCorrente = Math.min(pagina, totPagine);
  const inizio = (paginaCorrente - 1) * pageSize;
  const mostrate = dati.slice(inizio, inizio + pageSize);

  const valore = (col, item) => (col.render ? col.render(item) : item[col.key]);

  // Numeri di pagina da mostrare: tutti fino a 7 pagine, altrimenti
  // finestra attorno alla corrente con puntini (1 … 4 5 6 … 12).
  const numeriPagina = () => {
    if (totPagine <= 7) return Array.from({ length: totPagine }, (_, i) => i + 1);
    const set = new Set(
      [1, 2, paginaCorrente - 1, paginaCorrente, paginaCorrente + 1, totPagine - 1, totPagine].filter(
        n => n >= 1 && n <= totPagine
      )
    );
    const nums = [...set].sort((a, b) => a - b);
    const out = [];
    let prev = 0;
    for (const n of nums) {
      if (n - prev > 1) out.push('…');
      out.push(n);
      prev = n;
    }
    return out;
  };

  const stileBottone = attivo => ({
    minWidth: 34,
    padding: '7px 10px',
    background: attivo ? '#0f2744' : 'white',
    color: attivo ? 'white' : '#0f2744',
    border: attivo ? '1px solid #0f2744' : `1px solid ${COLORS.border}`,
    borderRadius: 6,
    fontWeight: 700,
    fontSize: 12.5,
    cursor: attivo ? 'default' : 'pointer',
    whiteSpace: 'nowrap',
  });

  const BarraPagine = ({ posizione }) =>
    totPagine > 1 ? (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 6,
          padding: '10px 0',
        }}
      >
        <button
          onClick={() => setPagina(p => Math.max(1, p - 1))}
          disabled={paginaCorrente === 1}
          data-testid={testId ? `${testId}-pagina-prec-${posizione}` : undefined}
          style={{ ...stileBottone(false), opacity: paginaCorrente === 1 ? 0.4 : 1 }}
        >
          ‹
        </button>
        {numeriPagina().map((n, i) =>
          n === '…' ? (
            <span key={`dots-${i}`} style={{ fontSize: 12.5, color: COLORS.textSubtle, padding: '0 2px' }}>
              …
            </span>
          ) : (
            <button
              key={n}
              onClick={() => setPagina(n)}
              data-testid={testId ? `${testId}-pagina-${n}-${posizione}` : undefined}
              style={stileBottone(n === paginaCorrente)}
            >
              {n}
            </button>
          )
        )}
        <button
          onClick={() => setPagina(p => Math.min(totPagine, p + 1))}
          disabled={paginaCorrente === totPagine}
          data-testid={testId ? `${testId}-pagina-succ-${posizione}` : undefined}
          style={{ ...stileBottone(false), opacity: paginaCorrente === totPagine ? 0.4 : 1 }}
        >
          ›
        </button>
        <span style={{ fontSize: 11.5, color: COLORS.textSubtle, marginLeft: 4 }}>
          {inizio + 1}–{inizio + mostrate.length} di {dati.length}
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
        <BarraPagine posizione="sopra" />
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
        <BarraPagine posizione="sotto" />
      </div>
    );
  }

  // ── VISTA DESKTOP: tabella standard ──────────────────────────────────────
  return (
    <div data-testid={testId}>
      <BarraPagine posizione="sopra" />
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
      <BarraPagine posizione="sotto" />
    </div>
  );
}

export default ListaAdattiva;
