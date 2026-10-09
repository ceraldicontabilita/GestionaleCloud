import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';

const API = '/hr/api/dipendenti-cloud';
const vuota = () => ({ dipendente_id: '', destinazione: '', data_inizio: '', data_fine: '', scopo: '', rimborso: '0' });
const nome = d => d?.nome_completo || [d?.cognome, d?.nome].filter(Boolean).join(' ');
const messaggio = e => typeof e.response?.data?.detail === 'string' ? e.response.data.detail : 'Operazione non riuscita. Riprova.';
const dataIT = v => v ? v.slice(0, 10).split('-').reverse().join('/') : '—';

export default function MissioniPage({ dipendenti = [] }) {
  const [righe, setRighe] = useState([]);
  const [loading, setLoading] = useState(true);
  const [errore, setErrore] = useState('');
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState(null);
  const [azione, setAzione] = useState(null);
  const [stato, setStato] = useState('');
  const carica = useCallback(async () => {
    setLoading(true); setErrore('');
    try { setRighe((await axios.get(`${API}/missioni`)).data || []); }
    catch (e) { setErrore(messaggio(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { carica(); }, [carica]);
  const salva = async e => {
    e.preventDefault(); setBusy(true); setErrore('');
    try {
      const payload = { ...form, rimborso: Number(form.rimborso), stato: 'in_attesa' };
      if (form.id) await axios.put(`${API}/missioni/${encodeURIComponent(form.id)}`, payload);
      else await axios.post(`${API}/missioni`, payload);
      setForm(null); await carica();
    } catch (err) { setErrore(messaggio(err)); }
    finally { setBusy(false); }
  };
  const esegui = async () => {
    setBusy(true); setErrore('');
    try {
      const url = `${API}/missioni/${encodeURIComponent(azione.riga.id)}`;
      if (azione.tipo === 'approva') await axios.put(`${url}/approva`);
      else await axios.delete(url);
      setAzione(null); await carica();
    } catch (e) { setErrore(messaggio(e)); }
    finally { setBusy(false); }
  };
  const campo = (key, value) => setForm(s => ({ ...s, [key]: value }));
  const visibili = righe.filter(r => !stato || r.stato === stato);
  return <div className="dc-page">
    <div className="dc-page-header"><h1>Missioni</h1><p>Trasferte dei dipendenti e rimborsi richiesti.</p></div>
    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 16 }}>
      <button className="dc-btn dc-btn-primary" onClick={() => setForm(vuota())}>Nuova missione</button>
      <select className="dc-select" aria-label="Stato missioni" value={stato} onChange={e => setStato(e.target.value)}><option value="">Tutti gli stati</option><option value="in_attesa">In attesa</option><option value="approvata">Approvate</option></select>
      <button className="dc-btn" onClick={carica} disabled={loading}>Aggiorna</button>
    </div>
    {errore && <div role="alert" className="dc-card" style={{ color: '#a13e30' }}>{errore}</div>}
    {form && <form className="dc-card" onSubmit={salva} aria-label={form.id ? 'Modifica missione' : 'Nuova missione'}>
      <h2>{form.id ? 'Modifica missione' : 'Nuova missione'}</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
        <label>Dipendente<select className="dc-select" aria-label="Dipendente" required value={form.dipendente_id} onChange={e => campo('dipendente_id', e.target.value)}><option value="">Seleziona dipendente</option>{dipendenti.map(d => <option key={d.id} value={d.id}>{nome(d)}</option>)}</select></label>
        <label>Destinazione<input className="dc-select" required value={form.destinazione} onChange={e => campo('destinazione', e.target.value)} /></label>
        <label>Data inizio<input className="dc-select" type="date" required value={form.data_inizio} onChange={e => campo('data_inizio', e.target.value)} /></label>
        <label>Data fine<input className="dc-select" type="date" required min={form.data_inizio} value={form.data_fine} onChange={e => campo('data_fine', e.target.value)} /></label>
        <label>Scopo<input className="dc-select" required value={form.scopo} onChange={e => campo('scopo', e.target.value)} /></label>
        <label>Rimborso richiesto (€)<input className="dc-select" type="number" min="0" step="0.01" required value={form.rimborso} onChange={e => campo('rimborso', e.target.value)} /></label>
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 16 }}><button className="dc-btn dc-btn-primary" disabled={busy} type="submit">{busy ? 'Salvataggio…' : 'Salva missione'}</button><button className="dc-btn" type="button" disabled={busy} onClick={() => setForm(null)}>Annulla</button></div>
    </form>}
    {azione && <div className="dc-card" role="alertdialog" aria-label="Conferma missione">
      <p>{azione.tipo === 'approva' ? 'Approvare la missione e il rimborso richiesto?' : 'Eliminare questa missione ancora in attesa?'}</p>
      <button className="dc-btn" disabled={busy} onClick={esegui}>Conferma</button> <button className="dc-btn" disabled={busy} onClick={() => setAzione(null)}>Annulla</button>
    </div>}
    {loading ? <p role="status">Caricamento missioni…</p> : !errore && !visibili.length ? <div className="dc-empty">Nessuna missione con questi filtri.</div> : <div className="dc-card" style={{ overflowX: 'auto' }}>
      <table className="dc-table dc-table--cards"><thead><tr><th>Dipendente</th><th>Destinazione</th><th>Periodo</th><th>Scopo</th><th>Rimborso</th><th>Stato</th><th>Azioni</th></tr></thead>
        <tbody>{visibili.map(r => <tr key={r.id}>
          <td data-label="Dipendente">{nome(dipendenti.find(d => d.id === r.dipendente_id)) || 'Dipendente da verificare'}</td><td data-label="Destinazione">{r.destinazione}</td>
          <td data-label="Periodo">{dataIT(r.data_inizio)} – {dataIT(r.data_fine)}</td><td data-label="Scopo">{r.scopo}</td><td data-label="Rimborso">{Number(r.rimborso || 0).toLocaleString('it-IT', { style: 'currency', currency: 'EUR' })}</td>
          <td data-label="Stato">{r.stato === 'approvata' ? 'Approvata' : r.stato === 'in_attesa' ? 'In attesa' : r.stato}</td>
          <td data-label="Azioni">{r.stato === 'in_attesa' && <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <button className="dc-btn" onClick={() => setForm({ ...r })}>Modifica</button><button className="dc-btn" onClick={() => setAzione({ tipo: 'approva', riga: r })}>Approva</button><button className="dc-btn" onClick={() => setAzione({ tipo: 'elimina', riga: r })}>Elimina</button>
          </div>}</td>
        </tr>)}</tbody>
      </table>
    </div>}
  </div>;
}
