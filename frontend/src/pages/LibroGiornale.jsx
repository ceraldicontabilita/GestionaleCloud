import React, { useState, useEffect, useCallback, useRef } from 'react';
import api from '../api';
import { toast } from 'sonner';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { COLORS } from '../lib/utils.js';

/**
 * Libro Giornale e Libro Mastro (art. 2216 c.c.) — registro UNICO
 * `movimenti_contabili` in partita doppia (motore §6.1).
 *
 * - Giornale: elenco CRONOLOGICO delle scritture definitive, ognuna col suo
 *   numero di protocollo (numero_registrazione) immutabile.
 * - Mastro: le stesse righe riclassificate per conto (mastrini).
 * - Esporta/Reimporta: il registro è ricostruibile "pari pari" — anche dopo
 *   una cancellazione totale, reimportando l'export si ricreano le scritture
 *   con protocollo, date e righe originali (reimport riservato all'Admin).
 * - Le operazioni PROVVISORIE vivono in Prima Nota Provvisoria (registro
 *   protocollo provvisorio) e NON compaiono qui finché non diventano definitive.
 */
export default function LibroGiornale() {
  const { anno } = useAnnoGlobale();
  const [vista, setVista] = useState('giornale'); // giornale | mastro
  const [giornale, setGiornale] = useState(null);
  const [mastro, setMastro] = useState(null);
  const [loading, setLoading] = useState(true);
  const [espansa, setEspansa] = useState(null); // id scrittura espansa
  const [controllo60, setControllo60] = useState(null);
  const fileInputRef = useRef(null);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const range = `data_da=${anno}-01-01&data_a=${anno}-12-31`;
      const [g, m, c60] = await Promise.all([
        api.get(`/api/contabilita-gestionale/libro-giornale?${range}&limit=2000`),
        api.get(`/api/contabilita-gestionale/libro-mastro?${range}`),
        api.get('/api/contabilita-gestionale/libro-giornale/controllo-60-giorni'),
      ]);
      setGiornale(g.data);
      setMastro(m.data);
      setControllo60(c60.data);
    } catch (e) {
      toast.error('Errore caricamento registro', {
        description: e.response?.data?.detail || e.message,
      });
    } finally {
      setLoading(false);
    }
  }, [anno]);

  useEffect(() => { carica(); }, [carica]);

  const esporta = async () => {
    try {
      const res = await api.get(`/api/contabilita-gestionale/libro-giornale/export?anno=${anno}`);
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `libro_giornale_${anno}.json`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      toast.success(`Registro ${anno} esportato`, {
        description: `${res.data.numero_scritture} scritture nel file`,
      });
    } catch (e) {
      toast.error('Errore export', { description: e.response?.data?.detail || e.message });
    }
  };

  const importa = async file => {
    try {
      const testo = await file.text();
      const dump = JSON.parse(testo);
      const res = await api.post('/api/contabilita-gestionale/libro-giornale/import', dump);
      toast.success('Registro reimportato', {
        description: `${res.data.ricreate} scritture ricreate, ${res.data.gia_presenti} già presenti`,
      });
      carica();
    } catch (e) {
      toast.error('Errore reimport', {
        description: e.response?.data?.detail || e.message,
      });
    }
  };

  const eur = v =>
    (v || 0).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const Badge = ({ ok, children }) => (
    <span style={{
      padding: '3px 10px', borderRadius: 12, fontSize: 12, fontWeight: 700,
      background: ok ? '#dcfce7' : '#fee2e2', color: ok ? '#166534' : '#991b1b',
    }}>{children}</span>
  );

  return (
    <div>
      {/* Header azioni */}
      <div style={{
        display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 14,
      }}>
        {['giornale', 'mastro'].map(v => (
          <button key={v} onClick={() => setVista(v)} data-testid={`vista-${v}`}
            style={{
              padding: '8px 16px', borderRadius: 8, cursor: 'pointer', fontWeight: 700,
              border: `1px solid ${COLORS.border}`,
              background: vista === v ? COLORS.primary : 'transparent',
              color: vista === v ? '#fff' : COLORS.text,
            }}>
            {v === 'giornale' ? '📖 Libro Giornale' : '📚 Libro Mastro'}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <button onClick={esporta} data-testid="export-giornale" style={btnGhost}>
          📥 Esporta registro {anno}
        </button>
        <button onClick={() => fileInputRef.current?.click()} data-testid="import-giornale"
          style={btnGhost} title="Ricostruzione da export precedente (solo Admin)">
          ♻️ Reimporta
        </button>
        <input ref={fileInputRef} type="file" accept="application/json" hidden
          onChange={e => { if (e.target.files?.[0]) importa(e.target.files[0]); e.target.value = ''; }} />
      </div>

      <p style={{ color: COLORS.textMuted, fontSize: 12, margin: '0 0 14px' }}>
        Registro definitivo in partita doppia: ogni scrittura ha il suo numero di
        protocollo immutabile. Le operazioni provvisorie restano in Prima Nota
        Provvisoria finché non vengono confermate. L'export permette di ricostruire
        la contabilità pari pari, come registrata all'epoca dei fatti.
      </p>

      {/* Controllo 60 giorni (DPR 600/73 art. 22) */}
      {controllo60 && !controllo60.conforme && (
        <div data-testid="alert-60-giorni" style={{
          padding: '10px 14px', background: '#fffbeb', border: '1px solid #fcd34d',
          borderRadius: 8, color: '#92400e', fontSize: 13, marginBottom: 14,
        }}>
          ⏰ <strong>{controllo60.totale_in_ritardo} documenti oltre i 60 giorni</strong> non
          ancora registrati in contabilità ({controllo60.fatture_non_registrate_oltre_60gg} fatture,{' '}
          {controllo60.corrispettivi_non_registrati_oltre_60gg} corrispettivi).
          Le registrazioni cronologiche vanno eseguite entro 60 giorni: {controllo60.azione}
        </div>
      )}

      {loading ? (
        <div style={{ color: COLORS.textMuted, padding: 24 }}>Caricamento registro…</div>
      ) : vista === 'giornale' ? (
        <>
          <div style={{ display: 'flex', gap: 16, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            <strong style={{ color: COLORS.text }}>{giornale?.totale ?? 0} scritture</strong>
            <span style={{ color: COLORS.textMuted, fontSize: 13 }}>
              DARE € {eur(giornale?.totale_dare)} · AVERE € {eur(giornale?.totale_avere)}
            </span>
            <Badge ok={giornale?.quadratura}>
              {giornale?.quadratura ? '✓ Quadra' : '✗ Non quadra'}
            </Badge>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: COLORS.bgAlt, textAlign: 'left' }}>
                  <th style={th}>Prot. n.</th>
                  <th style={th}>Data</th>
                  <th style={th}>Tipo</th>
                  <th style={th}>Descrizione</th>
                  <th style={{ ...th, textAlign: 'right' }}>DARE</th>
                  <th style={{ ...th, textAlign: 'right' }}>AVERE</th>
                  <th style={th}></th>
                </tr>
              </thead>
              <tbody>
                {(giornale?.scritture || []).map(s => (
                  <React.Fragment key={s.id}>
                    <tr style={{ borderBottom: `1px solid ${COLORS.border}`, cursor: 'pointer' }}
                      onClick={() => setEspansa(espansa === s.id ? null : s.id)}
                      data-testid={`scrittura-${s.numero_registrazione}`}>
                      <td style={{ ...td, fontWeight: 700 }}>{s.numero_registrazione}</td>
                      <td style={td}>{s.data_documento || s.data}</td>
                      <td style={td}>{s.tipo}</td>
                      <td style={td}>{s.descrizione}</td>
                      <td style={{ ...td, textAlign: 'right' }}>€ {eur(s.totale_dare)}</td>
                      <td style={{ ...td, textAlign: 'right' }}>€ {eur(s.totale_avere)}</td>
                      <td style={{ ...td, color: COLORS.textMuted }}>
                        {espansa === s.id ? '▲' : '▼'}
                      </td>
                    </tr>
                    {espansa === s.id && (s.righe || []).map((r, i) => (
                      <tr key={i} style={{ background: COLORS.bgAlt, fontSize: 12 }}>
                        <td style={td}></td>
                        <td style={td} colSpan={2}>{r.conto_codice || r.conto} — {r.conto_nome}</td>
                        <td style={td}>{r.descrizione}</td>
                        <td style={{ ...td, textAlign: 'right' }}>{r.dare ? `€ ${eur(r.dare)}` : ''}</td>
                        <td style={{ ...td, textAlign: 'right' }}>{r.avere ? `€ ${eur(r.avere)}` : ''}</td>
                        <td style={td}></td>
                      </tr>
                    ))}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
          {(giornale?.scritture || []).length === 0 && (
            <div style={{ color: COLORS.textMuted, padding: 24, textAlign: 'center' }}>
              Nessuna scrittura definitiva per il {anno}. Le scritture nascono dalla
              registrazione contabile (Piano dei Conti → Registra fatture) e dalle
              operazioni di TFR e ammortamenti.
            </div>
          )}
        </>
      ) : (
        <>
          <div style={{ display: 'flex', gap: 16, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            <strong style={{ color: COLORS.text }}>{mastro?.totale_conti ?? 0} mastrini</strong>
            <span style={{ color: COLORS.textMuted, fontSize: 13 }}>
              DARE € {eur(mastro?.totale_dare)} · AVERE € {eur(mastro?.totale_avere)}
            </span>
            <Badge ok={mastro?.quadratura}>
              {mastro?.quadratura ? '✓ Quadra' : '✗ Non quadra'}
            </Badge>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: COLORS.bgAlt, textAlign: 'left' }}>
                  <th style={th}>Conto</th>
                  <th style={th}>Nome</th>
                  <th style={th}>Conto CEE ufficiale</th>
                  <th style={{ ...th, textAlign: 'right' }}>DARE</th>
                  <th style={{ ...th, textAlign: 'right' }}>AVERE</th>
                  <th style={{ ...th, textAlign: 'right' }}>Saldo</th>
                  <th style={{ ...th, textAlign: 'right' }}>Righe</th>
                </tr>
              </thead>
              <tbody>
                {(mastro?.mastrini || []).map(m => (
                  <tr key={m.conto} style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                    <td style={{ ...td, fontWeight: 700 }}>{m.conto}</td>
                    <td style={td}>{m.conto_nome}</td>
                    <td style={td}>
                      {m.conto_ufficiale
                        ? `${m.conto_ufficiale} — ${m.conto_ufficiale_nome || ''}`
                        : <span style={{ color: COLORS.textMuted }}>—</span>}
                    </td>
                    <td style={{ ...td, textAlign: 'right' }}>€ {eur(m.dare)}</td>
                    <td style={{ ...td, textAlign: 'right' }}>€ {eur(m.avere)}</td>
                    <td style={{
                      ...td, textAlign: 'right', fontWeight: 700,
                      color: m.saldo >= 0 ? COLORS.text : COLORS.danger,
                    }}>€ {eur(m.saldo)}</td>
                    <td style={{ ...td, textAlign: 'right' }}>{m.movimenti}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

const th = { padding: '10px 12px', color: '#475569', fontWeight: 700, whiteSpace: 'nowrap' };
const td = { padding: '9px 12px', color: '#0f172a' };
const btnGhost = {
  background: 'transparent', border: '1px solid #e2e8f0', color: '#0f2744',
  borderRadius: 8, padding: '8px 14px', cursor: 'pointer', fontSize: 13, fontWeight: 600,
};
