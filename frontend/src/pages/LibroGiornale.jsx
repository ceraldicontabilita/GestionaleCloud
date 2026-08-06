import React, { useState, useEffect, useCallback, useRef } from 'react';
import api from '../api';
import { toast } from 'sonner';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { COLORS, useIsMobile } from '../lib/utils.js';

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
  // Su telefono le scritture/mastrini diventano card (16/07/2026, stessa
  // ricetta di Fatture/Prima Nota); su monitor resta la tabella.
  const isMobile = useIsMobile();
  const [vista, setVista] = useState('giornale'); // giornale | mastro
  const [giornale, setGiornale] = useState(null);
  const [mastro, setMastro] = useState(null);
  const [loading, setLoading] = useState(true);
  const [registerError, setRegisterError] = useState(null);
  const [espansa, setEspansa] = useState(null); // id scrittura espansa
  const [controllo60, setControllo60] = useState(null);
  const fileInputRef = useRef(null);

  const carica = useCallback(async () => {
    setLoading(true);
    setRegisterError(null);
    setGiornale(null);
    setMastro(null);
    try {
      const range = `data_da=${anno}-01-01&data_a=${anno}-12-31`;
      const controlloPromise = api
        .get('/api/contabilita-gestionale/libro-giornale/controllo-60-giorni')
        .catch(e => {
          setControllo60(null);
          toast.warning('Controllo 60 giorni non disponibile', {
            description: e.response?.data?.detail || e.message,
          });
          return null;
        });
      const [g, m, c60] = await Promise.all([
        api.get(`/api/contabilita-gestionale/libro-giornale?${range}&limit=2000`),
        api.get(`/api/contabilita-gestionale/libro-mastro?${range}`),
        controlloPromise,
      ]);
      setGiornale(g.data);
      setMastro(m.data);
      if (c60) setControllo60(c60.data);
    } catch (e) {
      setRegisterError(e.response?.data?.detail || e.message || 'Servizio non disponibile');
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
      if (file.size > 25 * 1024 * 1024) {
        throw new Error('File troppo grande: limite 25 MB');
      }
      const testo = await file.text();
      const dump = JSON.parse(testo);
      if (
        dump?.tipo !== 'libro_giornale_gestionalecloud' ||
        dump?.versione !== 1 ||
        !Array.isArray(dump?.scritture)
      ) {
        throw new Error('File non riconosciuto: selezionare un export del Libro Giornale');
      }
      const conferma = window.confirm(
        `Reimportare ${dump.scritture.length} scritture dal file ${file.name}?\n\n` +
        'Saranno aggiunte soltanto quelle mancanti. Il server annullerà tutto se trova ' +
        'scritture sbilanciate, protocolli duplicati o righe invalide.'
      );
      if (!conferma) return;
      const res = await api.post('/api/contabilita-gestionale/libro-giornale/import', dump);
      toast.success('Registro reimportato', {
        description: `${res.data.ricreate} scritture ricreate, ${res.data.gia_presenti} già presenti`,
      });
      carica();
    } catch (e) {
      toast.error('Errore reimport', {
        description:
          e.response?.data?.detail?.messaggio || e.response?.data?.detail || e.message,
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
        <button onClick={esporta} data-testid="export-giornale" style={btnGhost}
          disabled={loading || !giornale}>
          📥 Esporta registro {anno}
        </button>
        <button onClick={() => fileInputRef.current?.click()} data-testid="import-giornale"
          style={btnGhost} title="Ricostruzione da export precedente (solo Admin)"
          disabled={loading}>
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

      {!loading && giornale?.troncato && (
        <div role="alert" style={{
          padding: '10px 14px', background: '#fffbeb', border: '1px solid #fcd34d',
          borderRadius: 8, color: '#92400e', fontSize: 13, marginBottom: 14,
        }}>
          <strong>Vista parziale:</strong> mostrate {giornale.totale} scritture su{' '}
          {giornale.totale_disponibile}. Totali e quadratura non rappresentano l'intero periodo.
        </div>
      )}

      {!loading && giornale?.qualita_registro && !giornale.qualita_registro.registro_valido && (
        <div role="alert" data-testid="alert-qualita-giornale" style={{
          padding: '10px 14px', background: '#fef2f2', border: '1px solid #fecaca',
          borderRadius: 8, color: '#991b1b', fontSize: 13, marginBottom: 14,
        }}>
          <strong>Registro non valido:</strong>{' '}
          {giornale.qualita_registro.scritture_sbilanciate || 0} scritture sbilanciate,{' '}
          {giornale.qualita_registro.protocolli_duplicati || 0} protocolli duplicati,{' '}
          {giornale.qualita_registro.scritture_senza_protocollo || 0} senza protocollo,{' '}
          {giornale.qualita_registro.righe_non_numeriche || 0} righe non numeriche e{' '}
          {giornale.qualita_registro.righe_senza_conto || 0} righe senza conto. Nessuna
          correzione automatica è stata eseguita.
        </div>
      )}

      {loading ? (
        <div style={{ color: COLORS.textMuted, padding: 24 }}>Caricamento registro…</div>
      ) : registerError ? (
        <div role="alert" style={{
          color: '#991b1b', background: '#fef2f2', border: '1px solid #fecaca',
          borderRadius: 8, padding: 18,
        }}>
          <strong>Impossibile caricare Libro Giornale e Libro Mastro.</strong>
          <div style={{ marginTop: 4, fontSize: 13 }}>{String(registerError)}</div>
          <button type="button" onClick={carica} style={{ ...btnGhost, marginTop: 12 }}>
            Riprova
          </button>
        </div>
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
          {isMobile ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {(giornale?.scritture || []).map(s => (
                <div
                  key={s.id}
                  onClick={() => setEspansa(espansa === s.id ? null : s.id)}
                  data-testid={`scrittura-${s.numero_registrazione}`}
                  style={{
                    background: 'white', borderRadius: 12, border: `1px solid ${COLORS.border}`,
                    borderLeft: '4px solid #0f2744', boxShadow: '0 1px 2px rgba(15,39,68,0.06)',
                    padding: '10px 12px', cursor: 'pointer', minWidth: 0,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                    <div style={{ minWidth: 0 }}>
                      <span style={{ fontWeight: 800, color: '#0f2744', fontSize: 13 }}>
                        n. {s.numero_registrazione}
                      </span>
                      <span style={{ marginLeft: 8, fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 11.5, color: '#475569' }}>
                        {s.data_documento || s.data}
                      </span>
                      <span style={{ marginLeft: 8, background: '#f1f5f9', color: '#475569', padding: '2px 7px', borderRadius: 999, fontSize: 10.5, fontWeight: 600 }}>
                        {s.tipo}
                      </span>
                    </div>
                    <span style={{ color: COLORS.textMuted, flexShrink: 0 }}>{espansa === s.id ? '▲' : '▼'}</span>
                  </div>
                  <div style={{ marginTop: 4, fontSize: 12.5, color: '#1e293b', overflowWrap: 'anywhere' }}>
                    {s.descrizione}
                  </div>
                  <div style={{ marginTop: 6, display: 'flex', gap: 14, fontSize: 12, fontFamily: 'ui-monospace, Menlo, monospace' }}>
                    <span style={{ color: '#16a34a', fontWeight: 700 }}>DARE € {eur(s.totale_dare)}</span>
                    <span style={{ color: '#dc2626', fontWeight: 700 }}>AVERE € {eur(s.totale_avere)}</span>
                  </div>
                  {espansa === s.id && (
                    <div style={{ marginTop: 8, borderTop: `1px solid ${COLORS.border}`, paddingTop: 6 }}>
                      {(s.righe || []).map((r, i) => (
                        <div key={i} style={{ fontSize: 11.5, color: '#475569', padding: '3px 0', display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                          <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
                            {r.conto_codice || r.conto} — {r.conto_nome}
                          </span>
                          <span style={{ whiteSpace: 'nowrap', fontFamily: 'ui-monospace, Menlo, monospace' }}>
                            {r.dare ? `D € ${eur(r.dare)}` : `A € ${eur(r.avere)}`}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
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
          )}
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
          {isMobile ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {(mastro?.mastrini || []).map(m => (
                <div
                  key={m.conto}
                  style={{
                    background: 'white', borderRadius: 12, border: `1px solid ${COLORS.border}`,
                    borderLeft: `4px solid ${m.saldo >= 0 ? '#0f2744' : '#dc2626'}`,
                    boxShadow: '0 1px 2px rgba(15,39,68,0.06)', padding: '10px 12px', minWidth: 0,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                    <div style={{ minWidth: 0 }}>
                      <span style={{ fontWeight: 800, color: '#0f2744', fontSize: 13, fontFamily: 'ui-monospace, Menlo, monospace' }}>
                        {m.conto}
                      </span>
                      <div style={{ fontSize: 12.5, color: '#1e293b', overflowWrap: 'anywhere' }}>{m.conto_nome}</div>
                      {m.conto_ufficiale && (
                        <div style={{ fontSize: 11, color: COLORS.textMuted, overflowWrap: 'anywhere' }}>
                          CEE {m.conto_ufficiale} — {m.conto_ufficiale_nome || ''}
                        </div>
                      )}
                    </div>
                    <div style={{ textAlign: 'right', flexShrink: 0 }}>
                      <div style={{
                        fontWeight: 800, fontSize: 14.5, fontFamily: 'ui-monospace, Menlo, monospace',
                        color: m.saldo >= 0 ? '#0f2744' : '#dc2626',
                      }}>
                        € {eur(m.saldo)}
                      </div>
                      <div style={{ fontSize: 10.5, color: COLORS.textMuted }}>{m.movimenti} righe</div>
                    </div>
                  </div>
                  <div style={{ marginTop: 6, display: 'flex', gap: 14, fontSize: 11.5, fontFamily: 'ui-monospace, Menlo, monospace' }}>
                    <span style={{ color: '#16a34a' }}>DARE € {eur(m.dare)}</span>
                    <span style={{ color: '#dc2626' }}>AVERE € {eur(m.avere)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
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
          )}
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
