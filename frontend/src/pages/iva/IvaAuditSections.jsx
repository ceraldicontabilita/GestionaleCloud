import React from 'react';
import { CalendarDays, FileCheck2 } from 'lucide-react';
import { Badge } from '../../components/ds';
import { COLORS, formatDateIT, formatEuro } from '../../lib/utils';

const cardStyle = {
  background: COLORS.card,
  border: `1px solid ${COLORS.border}`,
  borderRadius: 10,
  padding: 14,
  marginTop: 16,
};

const titleStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  margin: '0 0 6px',
  color: COLORS.text,
  fontSize: 16,
  fontWeight: 700,
};

const metricStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: 3,
  minWidth: 150,
  padding: '10px 12px',
  border: `1px solid ${COLORS.border}`,
  borderRadius: 8,
  background: COLORS.bgAlt,
};

function EsitoF24({ mese }) {
  const daVersare = mese.da_versare ?? Math.max(Number(mese.saldo || 0), 0);
  const aCredito = mese.a_credito ?? Math.max(-Number(mese.saldo || 0), 0);
  if (mese.stato_periodo === 'NON_ANCORA_DOVUTO') return <Badge variant="neutral">Non ancora dovuto</Badge>;
  if (mese.stato_periodo === 'IN_FORMAZIONE') return <Badge variant="info">In formazione</Badge>;
  if (mese.stato_periodo === 'IN_ATTESA') return <Badge variant="info">In attesa</Badge>;
  if (mese.stato_periodo === 'DA_COMPLETARE') return <Badge variant="danger">Da completare</Badge>;
  if (mese.periodo_calcolato === false || mese.stato_calcolo === 'NON_CALCOLATO') {
    return <Badge variant="neutral">Non calcolato</Badge>;
  }
  if (mese.lipe?.stato === 'LIPE_AMBIGUA' || mese.lipe?.stato === 'LIPE_DA_VERIFICARE') {
    return <Badge variant="warning">LIPE da verificare</Badge>;
  }
  if (mese.lipe?.stato === 'LIPE_ESTRATTA' && mese.lipe?.coerente_gestionale === false) {
    return <Badge variant="warning">Dati da verificare</Badge>;
  }
  if (daVersare <= 0) {
    return <Badge variant="info">Credito {formatEuro(aCredito)}</Badge>;
  }
  if (mese.stato_f24 === 'in_attesa_f24' || mese.importo_f24_commercialista == null) {
    return <Badge variant="warning">In attesa F24</Badge>;
  }
  if (mese.stato_f24 === 'f24_ambiguo' || mese.stato_f24 === 'periodo_f24_da_verificare') {
    return <Badge variant="warning">Verificare documento</Badge>;
  }
  if (mese.coerente_f24) return <Badge variant="success">Conforme</Badge>;
  return <Badge variant="danger">Importo diverso</Badge>;
}

export function ConfrontoIvaCommercialista({ anno, dati, loading, error }) {
  const mesi = dati?.mensile || [];

  return (
    <section id="iva-confronto-f24" style={cardStyle} data-testid="iva-confronto-commercialista">
      <h3 style={titleStyle}>
        <FileCheck2 size={18} style={{ color: COLORS.primary }} />
        Confronto con F24 del commercialista
      </h3>
      <p style={{ margin: '0 0 12px', color: COLORS.textMuted, fontSize: 13 }}>
        Tre fonti distinte, senza sommarle tra loro: il gestionale calcola vendite meno acquisti
        detraibili; la LIPE comunica VP4 (IVA esigibile) e VP5 (IVA detratta); l’F24 mostra quanto
        richiesto dalla commercialista con il codice IVA 6001–6012. Quietanza e banca provano il
        pagamento, non modificano il calcolo.
      </p>

      {loading && <div style={{ padding: 20, color: COLORS.textMuted }}>Caricamento confronto F24…</div>}
      {!loading && error && (
        <div role="alert" style={{ padding: 12, borderRadius: 8, color: COLORS.danger, background: COLORS.dangerLight }}>
          {error}
        </div>
      )}
      {!loading && !error && mesi.length === 0 && (
        <div style={{ padding: 20, color: COLORS.textMuted }}>Nessun dato IVA disponibile per il {anno}.</div>
      )}
      {!loading && !error && mesi.length > 0 && (
        <>
          <div style={{ overflowX: 'auto' }}>
            <table className="iva-responsive-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
              <thead>
                <tr>
                  {['Mese', 'Calcolo gestionale', 'LIPE comunicata', 'F24 commercialista', 'Pagamento', 'Esito'].map((label) => (
                    <th key={label} style={{ padding: '10px 9px', textAlign: label === 'Mese' ? 'left' : 'right', color: COLORS.textMuted, background: COLORS.bgAlt, whiteSpace: 'nowrap' }}>
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {mesi.map((m) => {
                  const nonCalcolato = m.periodo_calcolato === false || m.stato_calcolo === 'NON_CALCOLATO';
                  return (
                  <tr key={m.mese} style={{ borderTop: `1px solid ${COLORS.border}` }}>
                    <td data-label="Mese" style={{ padding: '10px 9px', fontWeight: 700 }}>{m.mese_nome}</td>
                    <td data-label="Calcolo gestionale" style={{ padding: '10px 9px', textAlign: 'right' }}>
                      {nonCalcolato ? '—' : (
                        <span>
                          Vendite {formatEuro(m.iva_debito_corrispettivi)}<br />
                          Acquisti − {formatEuro(m.iva_credito_fatture)}<br />
                          <strong style={{ color: m.saldo > 0 ? COLORS.danger : COLORS.success }}>
                            Saldo {m.saldo > 0 ? '+' : ''}{formatEuro(m.saldo)}
                          </strong>
                          <small style={{ display: 'block', color: COLORS.textMuted }}>
                            {m.num_fatture || 0} fatture · {m.fatture_con_iva_competenza || 0} con IVA
                            {m.fatture_gia_liquidate ? ` · ${m.fatture_gia_liquidate} già liquidate` : ''}
                            {m.fatture_da_classificare ? ` · ${m.fatture_da_classificare} da verificare` : ''}
                          </small>
                        </span>
                      )}
                    </td>
                    <td data-label="LIPE comunicata" style={{ padding: '10px 9px', textAlign: 'right' }}>
                      {['LIPE_ESTRATTA', 'LIPE_DA_VERIFICARE'].includes(m.lipe?.stato) ? (
                        <span>
                          Esigibile VP4 {formatEuro(m.lipe.vp4)}<br />
                          Detraibile VP5 {formatEuro(m.lipe.vp5)}
                          <small style={{ display: 'block', color: m.lipe.stato === 'LIPE_DA_VERIFICARE' ? COLORS.warning : m.lipe.coerente_gestionale ? COLORS.success : COLORS.danger }}>
                            {m.lipe.stato === 'LIPE_DA_VERIFICARE' ? 'OCR da verificare' : m.lipe.coerente_gestionale ? 'uguale al gestionale' : 'diversa dal gestionale'} · pag. {m.lipe.page_number || '—'}
                          </small>
                        </span>
                      ) : <span style={{ color: COLORS.textMuted }}>{m.lipe?.stato === 'LIPE_AMBIGUA' ? 'Più LIPE candidate' : '—'}</span>}
                    </td>
                    <td data-label="F24 commercialista" style={{ padding: '10px 9px', textAlign: 'right' }}>
                      {m.importo_f24_commercialista == null ? '—' : (
                        <span>
                          {formatEuro(m.importo_f24_commercialista)}
                          <small style={{ display: 'block', color: COLORS.textMuted }}>
                            codice {m.codice_tributo_iva || '—'}{m.f24_multi_tributo ? ' · multi-tributo' : ''}
                          </small>
                        </span>
                      )}
                    </td>
                    <td data-label="Pagamento" style={{ padding: '10px 9px', textAlign: 'right' }}>
                      <small style={{ display: 'block' }}>Quietanza: {m.quietanza_presente ? 'presente' : 'assente'}</small>
                      <small style={{ display: 'block' }}>Banca: {m.verificato_banca ? 'verificata' : 'non verificata'}</small>
                    </td>
                    <td data-label="Esito" style={{ padding: '10px 9px', textAlign: 'right' }}><EsitoF24 mese={m} /></td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 12 }}>
            <div style={metricStyle}><span style={{ color: COLORS.textMuted, fontSize: 11 }}>IVA debito {anno}</span><strong>{formatEuro(dati.totali?.iva_debito_totale || 0)}</strong></div>
            <div style={metricStyle}><span style={{ color: COLORS.textMuted, fontSize: 11 }}>IVA credito {anno}</span><strong>{formatEuro(dati.totali?.iva_credito_totale || 0)}</strong></div>
            <div style={metricStyle}><span style={{ color: COLORS.textMuted, fontSize: 11 }}>Saldo gestionale {anno}</span><strong style={{ color: (dati.totali?.saldo_annuale || 0) > 0 ? COLORS.danger : COLORS.success }}>{formatEuro(dati.totali?.saldo_annuale || 0)}</strong></div>
          </div>
        </>
      )}
    </section>
  );
}

export function ScadenzeIvaMensili({ anno, dati, loading, error }) {
  const scadenze = dati?.scadenze || [];

  return (
    <section id="iva-scadenze" style={cardStyle} data-testid="iva-scadenze-mensili">
      <h3 style={titleStyle}>
        <CalendarDays size={18} style={{ color: COLORS.primary }} />
        Scadenze IVA mensili {anno}
      </h3>
      <p style={{ margin: '0 0 12px', color: COLORS.textMuted, fontSize: 13 }}>
        Prospetto mensile con riporto del credito. Le cifre marcate come stima non sostituiscono
        la liquidazione confermata né il modello F24 ricevuto dal commercialista.
      </p>

      {loading && <div style={{ padding: 20, color: COLORS.textMuted }}>Caricamento scadenze IVA…</div>}
      {!loading && error && (
        <div role="alert" style={{ padding: 12, borderRadius: 8, color: COLORS.danger, background: COLORS.dangerLight }}>
          {error}
        </div>
      )}
      {!loading && !error && scadenze.length === 0 && (
        <div style={{ padding: 20, color: COLORS.textMuted }}>Nessuna scadenza IVA disponibile per il {anno}.</div>
      )}
      {!loading && !error && scadenze.length > 0 && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 10 }}>
            {scadenze.map((s) => {
              const nonCalcolato = s.stato === 'NON_CALCOLATO' || s.saldo_cents == null;
              const aDebito = Boolean(s.da_versare_effettivo ?? s.da_versare);
              return (
                <article key={s.mese} style={{ padding: 12, border: `1px solid ${COLORS.border}`, borderLeft: `4px solid ${nonCalcolato ? COLORS.textMuted : aDebito ? COLORS.warning : COLORS.success}`, borderRadius: 8, background: COLORS.bgAlt }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                    <strong>{s.mese_nome}</strong>
                    {s.fonte === 'stima' && <Badge variant="neutral">Stima</Badge>}
                  </div>
                  <div style={{ marginTop: 7, fontSize: 11, color: COLORS.textMuted }}>Scadenza {formatDateIT(s.data_scadenza)}</div>
                  <div style={{ marginTop: 8, display: 'grid', gap: 3, fontSize: 12 }}>
                    <span>Debito: <strong>{nonCalcolato ? '—' : formatEuro(s.iva_debito)}</strong></span>
                    <span>Credito: <strong>{nonCalcolato ? '—' : formatEuro(s.iva_credito)}</strong></span>
                    <span>Saldo progressivo: <strong>{nonCalcolato ? '—' : formatEuro(s.saldo_progressivo ?? s.saldo)}</strong></span>
                  </div>
                  <div style={{ marginTop: 9 }}>
                    <Badge variant={nonCalcolato ? 'neutral' : aDebito ? 'warning' : 'success'}>
                      {nonCalcolato ? 'Non calcolato' : aDebito ? 'Da verificare con F24' : 'Credito riportato'}
                    </Badge>
                  </div>
                </article>
              );
            })}
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 12 }}>
            <div style={metricStyle}><span style={{ color: COLORS.textMuted, fontSize: 11 }}>Totale a credito</span><strong style={{ color: COLORS.success }}>{formatEuro(dati.totale_a_credito || 0)}</strong></div>
            <div style={metricStyle}><span style={{ color: COLORS.textMuted, fontSize: 11 }}>Totale teorico a debito</span><strong style={{ color: COLORS.warning }}>{formatEuro(dati.totale_da_versare || 0)}</strong></div>
            <div style={metricStyle}><span style={{ color: COLORS.textMuted, fontSize: 11 }}>Saldo progressivo</span><strong>{formatEuro(dati.saldo_progressivo ?? dati.saldo_annuale ?? 0)}</strong></div>
          </div>
        </>
      )}
    </section>
  );
}
