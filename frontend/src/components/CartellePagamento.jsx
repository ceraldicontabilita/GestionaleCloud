import React, { useCallback, useEffect, useState } from 'react';
import api from '../api';
import { COLORS, BORDER_RADIUS, formatEuroD } from '../lib/utils';
import { toast } from './ui/sonner';

/**
 * Cartelle di pagamento dell'Agente della riscossione: ogni cartella e' un
 * obbligo «da pagare» (attesa). La chiude solo la ricevuta con lo stesso IUV e
 * lo stesso importo. Il termine (60 giorni) parte dalla notifica, che non sta
 * nel PDF: la dice il titolare, mai inventata.
 */
const STATO = {
  ATTESO: { testo: 'Da pagare', colore: COLORS.warning },
  DA_VERIFICARE: { testo: 'Da verificare', colore: COLORS.danger },
  SODDISFATTO: { testo: 'Pagata', colore: COLORS.success },
};

const dataIt = iso => {
  const [a, m, g] = String(iso || '').slice(0, 10).split('-');
  return a && m && g ? `${g}/${m}/${a}` : '—';
};

export default function CartellePagamento() {
  const [cartelle, setCartelle] = useState([]);

  const carica = useCallback(async () => {
    try {
      const { data } = await api.get('/api/pagopa/cartelle');
      setCartelle(Array.isArray(data?.cartelle) ? data.cartelle : []);
    } catch {
      setCartelle([]);
    }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  const impostaNotifica = async (cartella, valore) => {
    if (!valore) return;
    try {
      await api.put(`/api/pagopa/cartelle/${encodeURIComponent(cartella.id)}/notifica`, { data_notifica: valore });
      toast.success('Data di notifica salvata');
      carica();
    } catch (e) {
      toast.error(e.response?.data?.detail?.message || 'Data di notifica non salvata');
    }
  };

  if (cartelle.length === 0) return null;

  return (
    <section
      aria-label="Cartelle di pagamento"
      data-testid="cartelle-pagamento"
      style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.md, padding: 14, marginBottom: 16 }}
    >
      <h2 style={{ margin: '0 0 10px', fontSize: 15, fontWeight: 800 }}>Cartelle di pagamento</h2>
      <div style={{ display: 'grid', gap: 10 }}>
        {cartelle.map(c => {
          const stato = STATO[c.expectation_status] || STATO.DA_VERIFICARE;
          return (
            <div key={c.id} data-testid={`cartella-${c.id}`}
              style={{ border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.md, padding: '10px 12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                <strong>Cartella {c.numero_cartella}</strong>
                <span style={{ fontWeight: 800, color: stato.colore }}>{stato.testo}</span>
              </div>
              <div style={{ fontSize: 13, color: COLORS.textMuted, marginTop: 2 }}>
                {c.ente_creditore || 'Ente non letto'} · {formatEuroD(Number(c.totale || 0))}
                {c.diritti_notifica ? ` (di cui diritti di notifica ${formatEuroD(Number(c.diritti_notifica))})` : ''}
                {c.iuv ? ` · IUV ${c.iuv}` : ''}
              </div>
              {(c.verbali_collegati || []).map(v => (
                <div key={v.id} style={{ fontSize: 13 }}>Verbale {v.numero_verbale} · targa {v.targa}</div>
              ))}
              {(c.verbali || []).length > 0 && (c.verbali_collegati || []).length === 0 && (
                <div style={{ fontSize: 13, color: COLORS.textMuted }}>
                  Verbale {c.verbali.map(v => `${v.numero_verbale} (${v.targa})`).join(', ')}: non ancora in archivio
                </div>
              )}
              {c.importi_quadrano === false && (
                <div role="alert" style={{ fontSize: 13, color: COLORS.danger }}>
                  Le somme della cartella non tornano: da verificare sul documento.
                </div>
              )}
              <label style={{ display: 'block', marginTop: 8, fontSize: 12.5, fontWeight: 700, color: COLORS.textMuted }}>
                Data di notifica
                <input
                  type="date" value={c.data_notifica || ''} onChange={e => impostaNotifica(c, e.target.value)}
                  aria-label={`Data di notifica della cartella ${c.numero_cartella}`}
                  style={{ display: 'block', marginTop: 4, minHeight: 44, padding: '6px 10px', border: `1px solid ${COLORS.border}`, borderRadius: 8 }}
                />
              </label>
              <div style={{ fontSize: 13, marginTop: 6 }}>
                {c.scadenza
                  ? <>Da pagare entro <strong>{dataIt(c.scadenza)}</strong> (60 giorni dalla notifica, salvo festività)</>
                  : 'Scadenza: dipende dalla data di notifica, ancora da indicare.'}
              </div>
              {c.expectation_status === 'SODDISFATTO' && (
                <div style={{ fontSize: 13, color: COLORS.success }}>Pagata il {dataIt(c.data_pagamento)} · ricevuta agganciata per IUV</div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
