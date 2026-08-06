import React, { useEffect, useMemo, useState } from 'react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuroD, formatDateIT } from '../lib/utils';
import { useConfirm } from '../components/ui/ConfirmDialog';

/**
 * FINANZIAMENTO SOCI (richiesta utente 18/07/2026) — prima nota dei
 * finanziamenti con la scheda personale dei quattro soci. I bonifici in
 * entrata dal socio diventano APPORTI; le uscite con causale di
 * rimborso/restituzione diventano RIMBORSI. Il dato si estrae in
 * automatico dall'estratto conto (idempotente) leggendo la causale.
 */

const BLU = '#0f2744';
const VERDE = '#16a34a';
const ROSSO = '#dc2626';
const eur = v => formatEuroD(v || 0);

function parseImportoIT(input) {
  const v = parseFloat(String(input ?? '').replace(/\./g, '').replace(',', '.'));
  return isNaN(v) ? null : v;
}

export default function FinanziamentoSoci() {
  const { anno } = useAnnoGlobale();
  const confirm = useConfirm();
  const [dati, setDati] = useState(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [aperta, setAperta] = useState(null);
  const [manuale, setManuale] = useState(null); // {socio_id, nome}
  const [form, setForm] = useState({ tipo: 'apporto', importo: '', data: '', descrizione: '' });
  const [errore, setErrore] = useState('');
  const [busy, setBusy] = useState(null);

  const carica = async (conScan = false) => {
    if (conScan) setScanning(true); else setLoading(true);
    try {
      const r = await api.get(`/api/finanziamenti-soci/schede?anno=${anno}&scan=${conScan}`);
      setDati(r.data);
    } catch (e) {
      console.error('Finanziamenti soci:', e);
    } finally {
      setLoading(false);
      setScanning(false);
    }
  };
  useEffect(() => { carica(true); }, [anno]);

  const scan = dati?.scan;
  const schede = dati?.schede || [];

  const salvaManuale = async () => {
    const importo = parseImportoIT(form.importo);
    if (!importo || !form.data) {
      setErrore('Servono importo e data.');
      return;
    }
    setErrore('');
    try {
      await api.post('/api/finanziamenti-soci/movimento', {
        socio_id: manuale.socio_id, tipo: form.tipo, importo,
        data: form.data, descrizione: form.descrizione,
      });
      setManuale(null);
      setForm({ tipo: 'apporto', importo: '', data: '', descrizione: '' });
      carica(false);
    } catch (e) {
      setErrore(e.response?.data?.detail || e.response?.data?.message || e.message);
    }
  };

  const elimina = async mov => {
    const ok = await confirm({
      title: 'Eliminare il movimento dalla scheda?',
      message: `${formatDateIT(mov.data)} — ${mov.tipo} ${eur(mov.importo)}`,
      confirmText: 'Elimina', danger: true,
    });
    if (!ok) return;
    setBusy(mov.id);
    try {
      await api.delete(`/api/finanziamenti-soci/movimento/${mov.id}`);
      carica(false);
    } finally {
      setBusy(null);
    }
  };

  const campo = { width: '100%', padding: '9px 10px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 14, boxSizing: 'border-box' };

  const totale = dati?.totale || { apporti: 0, rimborsi: 0, saldo: 0 };

  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
        <div style={{ fontSize: 13, color: '#475569' }}>
          👥 Prima nota finanziamenti: apporti e rimborsi dei soci letti
          dall'estratto conto (causale per causale).
        </div>
        <button
          onClick={() => carica(true)} disabled={scanning}
          data-testid="scan-finanziamenti-soci"
          style={{ background: BLU, color: 'white', border: 'none', borderRadius: 8, padding: '8px 14px', fontSize: 13, fontWeight: 700, cursor: 'pointer', opacity: scanning ? 0.6 : 1 }}
        >
          {scanning ? '⏳ Scansione…' : '🔄 Aggiorna da estratto conto'}
        </button>
      </div>

      {scan && (
        <div style={{ fontSize: 12.5, color: '#475569', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 9, padding: '7px 11px', marginBottom: 10 }}>
          Scansione: {scan.righe_esaminate} righe EC esaminate — {scan.apporti_nuovi} apporti
          e {scan.rimborsi_nuovi} rimborsi nuovi, {scan.uscite_ignorate_causale} uscite ignorate
          (causale non di rimborso, es. stipendi)
          {scan.duplicati_semantici_ignorati > 0 ? ` — ${scan.duplicati_semantici_ignorati} copie bancarie ignorate` : ''}.
        </div>
      )}

      {dati?.duplicati_accorpati > 0 && (
        <div style={{ fontSize: 12.5, color: '#7c2d12', background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: 9, padding: '7px 11px', marginBottom: 10 }}>
          {dati.duplicati_accorpati} copie dello stesso movimento bancario sono state accorpate nel totale. Le prove sorgente restano conservate per l'audit.
        </div>
      )}

      {loading && <div style={{ padding: 30, textAlign: 'center', color: '#6b7280' }}>⏳ Caricamento…</div>}

      {!loading && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 10 }}>
            {schede.map(s => (
              <div
                key={s.socio_id}
                data-testid={`scheda-socio-${s.socio_id}`}
                style={{ background: 'white', borderRadius: 12, border: '1px solid #e2e8f0', borderLeft: `4px solid ${s.saldo >= 0 ? BLU : ROSSO}`, padding: '11px 14px' }}
              >
                <div style={{ fontWeight: 800, color: BLU, fontSize: 14.5 }}>👤 {s.nome}</div>
                <div style={{ display: 'grid', gap: 3, margin: '8px 0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5 }}>
                    <span style={{ color: '#64748b' }}>Apporti</span>
                    <b style={{ color: VERDE, fontFamily: 'ui-monospace, Menlo, monospace' }}>{eur(s.apporti)}</b>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5 }}>
                    <span style={{ color: '#64748b' }}>Rimborsi</span>
                    <b style={{ color: ROSSO, fontFamily: 'ui-monospace, Menlo, monospace' }}>{eur(s.rimborsi)}</b>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, borderTop: '1px dashed #e2e8f0', paddingTop: 4 }}>
                    <span style={{ fontWeight: 700, color: '#334155' }}>Credito residuo</span>
                    <b style={{ color: s.saldo >= 0 ? BLU : ROSSO, fontFamily: 'ui-monospace, Menlo, monospace' }}>{eur(s.saldo)}</b>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    onClick={() => setAperta(aperta === s.socio_id ? null : s.socio_id)}
                    style={{ flex: 1, background: '#f1f5f9', border: '1px solid #e2e8f0', borderRadius: 7, padding: '6px 8px', fontSize: 12, cursor: 'pointer', fontWeight: 600 }}
                  >
                    {aperta === s.socio_id ? '▲ Chiudi' : `▼ Movimenti (${s.movimenti.length})`}
                  </button>
                  <button
                    onClick={() => { setManuale({ socio_id: s.socio_id, nome: s.nome }); setErrore(''); }}
                    title="Aggiungi movimento manuale"
                    style={{ background: BLU, color: 'white', border: 'none', borderRadius: 7, padding: '6px 10px', fontSize: 12, cursor: 'pointer', fontWeight: 700 }}
                  >
                    ➕
                  </button>
                </div>
                {aperta === s.socio_id && (
                  <div style={{ marginTop: 8, display: 'grid', gap: 5 }}>
                    {s.movimenti.length === 0 && (
                      <div style={{ fontSize: 12, color: '#6b7280' }}>Nessun movimento{dati?.anno ? ` nel ${dati.anno}` : ''}.</div>
                    )}
                    {s.movimenti.map(m => (
                      <div key={m.id} style={{ border: '1px solid #f1f5f9', borderRadius: 8, padding: '6px 9px', fontSize: 12 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 6 }}>
                          <span style={{ fontWeight: 700, color: m.tipo === 'apporto' ? VERDE : ROSSO }}>
                            {m.tipo === 'apporto' ? '↧ Apporto' : '↥ Rimborso'} · {formatDateIT(m.data)}
                          </span>
                          <span style={{ display: 'inline-flex', gap: 5, alignItems: 'center' }}>
                            <b style={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>{eur(m.importo)}</b>
                            <button
                              onClick={() => elimina(m)} disabled={busy === m.id}
                              title="Elimina (es. associazione errata)"
                              style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 6, padding: '2px 6px', fontSize: 11, cursor: 'pointer' }}
                            >
                              🗑️
                            </button>
                          </span>
                        </div>
                        <div style={{ color: '#64748b', marginTop: 2, wordBreak: 'break-word' }}>
                          {m.descrizione || '—'}{m.source === 'manuale' ? ' · (manuale)' : ''}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          <div style={{ marginTop: 10, background: 'white', borderRadius: 11, border: '1px solid #e2e8f0', padding: '9px 13px', display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', fontSize: 13 }}>
            <span style={{ color: '#334155', fontWeight: 700 }}>Totale finanziamento soci</span>
            <span style={{ display: 'flex', gap: 14, fontFamily: 'ui-monospace, Menlo, monospace' }}>
              <span style={{ color: VERDE }}>+{eur(totale.apporti)}</span>
              <span style={{ color: ROSSO }}>−{eur(totale.rimborsi)}</span>
              <b style={{ color: totale.saldo >= 0 ? BLU : ROSSO }}>= {eur(totale.saldo)}</b>
            </span>
          </div>
        </>
      )}

      {manuale && (
        <div
          onClick={() => setManuale(null)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(15,39,68,0.55)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 14 }}
        >
          <div onClick={e => e.stopPropagation()} style={{ background: 'white', borderRadius: 14, padding: 18, width: '100%', maxWidth: 400 }}>
            <h3 style={{ margin: '0 0 10px', fontSize: 15, color: BLU }}>➕ Movimento — {manuale.nome}</h3>
            <div style={{ display: 'grid', gap: 9 }}>
              <select value={form.tipo} onChange={e => setForm({ ...form, tipo: e.target.value })} style={campo}>
                <option value="apporto">Apporto (il socio finanzia)</option>
                <option value="rimborso">Rimborso (la società restituisce)</option>
              </select>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 9 }}>
                <input type="date" value={form.data} onChange={e => setForm({ ...form, data: e.target.value })} style={campo} />
                <input
                  placeholder="Importo (es. 1.000,00)" inputMode="decimal" value={form.importo}
                  onChange={e => setForm({ ...form, importo: e.target.value })} style={campo}
                />
              </div>
              <input
                placeholder="Descrizione / causale" value={form.descrizione}
                onChange={e => setForm({ ...form, descrizione: e.target.value })} style={campo}
              />
              {errore && <div style={{ color: ROSSO, fontSize: 13 }}>{errore}</div>}
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button onClick={() => setManuale(null)} style={{ padding: '8px 14px', borderRadius: 8, border: '1px solid #d1d5db', background: 'white', cursor: 'pointer' }}>
                  Annulla
                </button>
                <button onClick={salvaManuale} style={{ padding: '8px 16px', borderRadius: 8, border: 'none', background: BLU, color: 'white', fontWeight: 700, cursor: 'pointer' }}>
                  💾 Salva
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
