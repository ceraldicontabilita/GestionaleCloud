import React, { useState, useEffect, useCallback } from 'react';
import api from '../api';
import { COLORS } from '../lib/utils.js';
import { toast } from 'sonner';

const RUOLI = [
  { value: 'operatore', label: 'Operatore', desc: 'Usa e inserisce, ma non cancella in blocco né tocca le impostazioni' },
  { value: 'sola_lettura', label: 'Sola lettura', desc: 'Può solo guardare, nessuna modifica' },
  { value: 'admin', label: 'Admin', desc: 'Può tutto, incluse cancellazioni e impostazioni' },
];

function labelRuolo(r) {
  return (RUOLI.find(x => x.value === r) || {}).label || r;
}

export default function Utenti() {
  const [utenti, setUtenti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [errore, setErrore] = useState(null);
  const [form, setForm] = useState({ nome: '', ruolo: 'operatore', pin: '' });
  const [salvando, setSalvando] = useState(false);

  const carica = useCallback(async () => {
    setLoading(true);
    setErrore(null);
    try {
      const res = await api.get('/api/utenti');
      setUtenti(res.data.utenti || []);
    } catch (e) {
      setErrore(e.response?.data?.detail || 'Errore nel caricamento utenti');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  const creaUtente = async e => {
    e.preventDefault();
    if (!form.nome.trim() || !/^\d{4,12}$/.test(form.pin)) {
      toast.error('Inserisci nome e un PIN di 4-12 cifre');
      return;
    }
    setSalvando(true);
    try {
      await api.post('/api/utenti', form);
      toast.success(`Utente "${form.nome}" creato`);
      setForm({ nome: '', ruolo: 'operatore', pin: '' });
      carica();
    } catch (e2) {
      toast.error(e2.response?.data?.detail || 'Errore nella creazione');
    } finally {
      setSalvando(false);
    }
  };

  const cambiaRuolo = async (u, ruolo) => {
    try {
      await api.put(`/api/utenti/${u.id}`, { ruolo });
      toast.success(`Ruolo di ${u.nome} aggiornato`);
      carica();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Errore aggiornamento ruolo');
    }
  };

  const toggleAttivo = async u => {
    try {
      await api.put(`/api/utenti/${u.id}`, { attivo: !u.attivo });
      carica();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Errore aggiornamento');
    }
  };

  const cambiaPin = async u => {
    const nuovo = window.prompt(`Nuovo PIN per ${u.nome} (4-12 cifre):`);
    if (nuovo == null) return;
    if (!/^\d{4,12}$/.test(nuovo)) { toast.error('PIN non valido'); return; }
    try {
      await api.put(`/api/utenti/${u.id}`, { pin: nuovo });
      toast.success('PIN aggiornato');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Errore cambio PIN');
    }
  };

  const elimina = async u => {
    if (!window.confirm(`Eliminare l'utente "${u.nome}"?`)) return;
    try {
      await api.delete(`/api/utenti/${u.id}`);
      toast.success('Utente eliminato');
      carica();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Errore eliminazione');
    }
  };

  return (
    <div style={{ minHeight: '100vh', background: COLORS.bg, padding: 16 }}>
      <div style={{ maxWidth: 900, margin: '0 auto' }}>
        <h1 style={{ color: COLORS.primary, fontSize: 22, marginBottom: 4 }}>Utenti e accessi</h1>
        <p style={{ color: COLORS.textMuted, fontSize: 13, marginBottom: 20 }}>
          Crea account con PIN personale e ruolo. L'amministratore principale entra
          col PIN configurato sul server e non compare in questa lista.
        </p>

        {/* Nuovo utente */}
        <form onSubmit={creaUtente} style={{
          background: COLORS.card, border: `1px solid ${COLORS.border}`,
          borderRadius: 10, padding: 16, marginBottom: 24,
          display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end',
        }}>
          <div style={{ flex: '1 1 200px' }}>
            <label style={lbl}>Nome</label>
            <input style={inp} value={form.nome}
              onChange={e => setForm(f => ({ ...f, nome: e.target.value }))}
              placeholder="Es. Maria Rossi" />
          </div>
          <div style={{ flex: '1 1 160px' }}>
            <label style={lbl}>Ruolo</label>
            <select style={inp} value={form.ruolo}
              onChange={e => setForm(f => ({ ...f, ruolo: e.target.value }))}>
              {RUOLI.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
          </div>
          <div style={{ flex: '1 1 140px' }}>
            <label style={lbl}>PIN (4-12 cifre)</label>
            <input style={inp} value={form.pin} inputMode="numeric"
              onChange={e => setForm(f => ({ ...f, pin: e.target.value.replace(/\D/g, '') }))}
              placeholder="Es. 246810" />
          </div>
          <button type="submit" disabled={salvando} style={{
            background: COLORS.primary, color: '#fff', border: 'none',
            borderRadius: 8, padding: '10px 18px', fontWeight: 700, cursor: 'pointer',
            height: 40,
          }}>
            {salvando ? 'Creo…' : '+ Aggiungi utente'}
          </button>
          <div style={{ flexBasis: '100%', color: COLORS.textMuted, fontSize: 12 }}>
            {(RUOLI.find(r => r.value === form.ruolo) || {}).desc}
          </div>
        </form>

        {/* Elenco */}
        {loading ? (
          <div style={{ color: COLORS.textMuted }}>Caricamento…</div>
        ) : errore ? (
          <div style={{ color: COLORS.danger }}>{errore}</div>
        ) : utenti.length === 0 ? (
          <div style={{ color: COLORS.textMuted }}>Nessun utente aggiuntivo. Solo l'amministratore.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {utenti.map(u => (
              <div key={u.id} style={{
                background: COLORS.card, border: `1px solid ${COLORS.border}`,
                borderRadius: 10, padding: 12, display: 'flex', gap: 12,
                alignItems: 'center', flexWrap: 'wrap',
                opacity: u.attivo ? 1 : 0.55,
              }}>
                <div style={{ flex: '1 1 180px' }}>
                  <div style={{ color: COLORS.text, fontWeight: 700 }}>{u.nome}</div>
                  <div style={{ color: COLORS.textMuted, fontSize: 12 }}>
                    {labelRuolo(u.ruolo)} · {u.attivo ? 'attivo' : 'disattivato'}
                  </div>
                </div>
                <select value={u.ruolo} onChange={e => cambiaRuolo(u, e.target.value)}
                  style={{ ...inp, width: 'auto' }}>
                  {RUOLI.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                </select>
                <button onClick={() => cambiaPin(u)} style={btnGhost}>Cambia PIN</button>
                <button onClick={() => toggleAttivo(u)} style={btnGhost}>
                  {u.attivo ? 'Disattiva' : 'Riattiva'}
                </button>
                <button onClick={() => elimina(u)} style={{ ...btnGhost, color: COLORS.danger }}>
                  Elimina
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

const lbl = { display: 'block', color: COLORS.textMuted, fontSize: 12, marginBottom: 4 };
const inp = {
  width: '100%', boxSizing: 'border-box', padding: '9px 10px',
  borderRadius: 8, border: `1px solid ${COLORS.border}`,
  background: COLORS.bg, color: COLORS.text, fontSize: 14, height: 40,
};
const btnGhost = {
  background: 'transparent', border: `1px solid ${COLORS.border}`,
  color: COLORS.text, borderRadius: 8, padding: '8px 12px',
  cursor: 'pointer', fontSize: 13,
};
