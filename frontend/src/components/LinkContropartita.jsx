import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight } from 'lucide-react';

/**
 * LinkContropartita — "cliccando un dato ti aspetti di trovare i dati in una
 * contropartita" (titolare, audit del commercialista 03/09/2026 §6, PR 16).
 *
 * UN solo componente e UNA sola tabella di rotte per tutti i collegamenti tra
 * registri: Prima Nota ↔ estratto conto, riconciliazione → fattura / prima
 * nota, scadenza → movimento pagante, bilancio → verifica → giornale →
 * documento, F24 → quietanza / movimento. Ogni pagina di destinazione legge
 * il parametro e porta in evidenza il record (scroll + evidenziazione).
 *
 * Palette salvia/sabbia del gruppo (mai blu).
 */
export const PALETTE_CONTROPARTITA = {
  salvia: '#5b7a6b',
  salviaScura: '#3f5a4e',
  salviaChiara: '#eef3ef',
  bordo: '#c9d6cd',
  sabbia: '#8a6f47',
  sabbiaChiara: '#f6f1e7',
  evidenza: '#fdf3d7',
};

const enc = v => encodeURIComponent(String(v));

/** Rotte canoniche di destinazione: un solo posto in cui sono scritte. */
export const ROTTE_CONTROPARTITA = {
  // Archivio fatture legge `?invoice_id=` (ArchivioFattureRicevute.jsx).
  fattura: id => `/fatture?invoice_id=${enc(id)}`,
  // Riconciliazione banca legge `?movimento=` (RiconciliazioneUnificata.jsx).
  movimentoBanca: id => `/riconciliazione/banca?movimento=${enc(id)}`,
  // Prima Nota legge l'hash `sezione`/`selected` (useHashState in PrimaNota.jsx):
  // `selected` filtra il registro per id riga o per id del movimento di estratto conto.
  primaNotaBanca: id => `/prima-nota#sezione=banca&selected=${enc(id)}`,
  // Bilancio di verifica legge `?conto=` (codice operativo o CEE).
  verificaConto: conto => `/contabilita/verifica?conto=${enc(conto)}`,
  // Libro giornale legge `?conto=&data_da=&data_a=` e `?scrittura=`.
  giornaleConto: (conto, anno) =>
    `/contabilita/giornale?conto=${enc(conto)}&data_da=${enc(anno)}-01-01&data_a=${enc(anno)}-12-31`,
  giornaleScrittura: id => `/contabilita/giornale?scrittura=${enc(id)}`,
  // XML del corrispettivo (endpoint esistente, si apre in una nuova scheda).
  corrispettivoXml: id => `/api/corrispettivi/${enc(id)}/view`,
};

/**
 * Rotta del documento d'origine di una scrittura del libro giornale
 * (`fonte_documento: {tipo, id}` del motore registrazione_contabile).
 * Ritorna `{ to, esterno, etichetta }` oppure null se non c'è documento.
 */
export function rottaDocumentoOrigine(fonte) {
  if (!fonte || !fonte.id) return null;
  if (fonte.tipo === 'fattura') {
    return { to: ROTTE_CONTROPARTITA.fattura(fonte.id), esterno: false, etichetta: 'Vai alla fattura' };
  }
  if (fonte.tipo === 'corrispettivo') {
    return { to: ROTTE_CONTROPARTITA.corrispettivoXml(fonte.id), esterno: true, etichetta: 'Apri il corrispettivo' };
  }
  return null;
}

/**
 * Id del movimento di estratto conto collegato a una riga di Prima Nota
 * Banca. Nomi verificati sui dati reali (prima_nota_banca, 03/09/2026):
 * estratto_conto_id (120 righe), movimento_estratto_conto_id (120),
 * movimento_bancario_id (72), estratto_conto_ids (29), movimento_banca_id.
 */
export function movimentoEstrattoContoDi(mov = {}) {
  return (
    mov.estratto_conto_id ||
    mov.movimento_estratto_conto_id ||
    mov.movimento_bancario_id ||
    mov.movimento_banca_id ||
    (Array.isArray(mov.estratto_conto_ids) ? mov.estratto_conto_ids[0] : null) ||
    null
  );
}

const stileBase = compatto => ({
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
  minHeight: compatto ? 26 : 32,
  padding: compatto ? '2px 8px' : '5px 10px',
  borderRadius: 8,
  border: `1px solid ${PALETTE_CONTROPARTITA.bordo}`,
  background: PALETTE_CONTROPARTITA.salviaChiara,
  color: PALETTE_CONTROPARTITA.salviaScura,
  fontSize: compatto ? 11 : 12,
  fontWeight: 700,
  textDecoration: 'none',
  whiteSpace: 'nowrap',
  cursor: 'pointer',
});

/**
 * @param {string} to        rotta interna (react-router) o URL (`esterno`)
 * @param {boolean} esterno  apre in nuova scheda (PDF/XML serviti dal backend)
 * @param {string} title     tooltip: tipo, id, data, importo, origine (regola §12)
 */
export default function LinkContropartita({
  to, children, esterno = false, title, testId, compatto = false, style = {}, onClick,
}) {
  if (!to) return null;
  const stile = { ...stileBase(compatto), ...style };
  const contenuto = (
    <>
      {children}
      <ArrowUpRight size={compatto ? 12 : 14} aria-hidden="true" />
    </>
  );
  if (esterno) {
    return (
      <a href={to} target="_blank" rel="noreferrer" title={title} data-testid={testId}
        style={stile} onClick={onClick}>
        {contenuto}
      </a>
    );
  }
  return (
    <Link to={to} title={title} data-testid={testId} style={stile} onClick={onClick}>
      {contenuto}
    </Link>
  );
}
