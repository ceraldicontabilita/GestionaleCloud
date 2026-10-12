import React, { useEffect, useState } from 'react';
import api from '../api';
import { useAuth } from '../contexts/AuthContext';

const inputStyle = { width: '100%', minHeight: 40, padding: '7px 9px', border: '1px solid #d9d6cd', borderRadius: 7, boxSizing: 'border-box', background: 'white' };
const labelStyle = { display: 'grid', gap: 5, fontSize: 13 };
const percentuale = value => {
  if (value == null || !Number.isFinite(Number(value))) return '';
  const quota = Number(value);
  // Il campo canonico è 0..1; vecchi documenti possono avere 0..100.
  return String(Math.round((quota >= 0 && quota <= 1 ? quota * 100 : quota) * 100) / 100);
};

export default function FiscalitaFattura({ fatturaId }) {
  const { isAdmin } = useAuth();
  const [fattura, setFattura] = useState(null);
  const [form, setForm] = useState({});
  const [errore, setErrore] = useState('');
  const [saving, setSaving] = useState(false);
  const [esito, setEsito] = useState('');

  useEffect(() => {
    let attivo = true;
    setFattura(null);
    setErrore('');
    setEsito('');
    api.get(`/api/fatture/${encodeURIComponent(fatturaId)}`).then(({ data }) => {
      if (!attivo) return;
      const documento = data.fattura || data;
      const contesto = documento.contesto_fiscale_iva || {};
      const anno = String(documento.invoice_date || documento.data_documento || '').slice(0, 4);
      setFattura(documento);
      setForm({
        inerente: typeof contesto.inerente === 'boolean' ? String(contesto.inerente) : '',
        fonte_documento: contesto.fonte_documento || '',
        dal: contesto.validita_fiscale?.dal || (anno ? `${anno}-01-01` : ''),
        al: contesto.validita_fiscale?.al || (anno ? `${anno}-12-31` : ''),
        uso_veicolo: contesto.uso_veicolo || '',
        percentuale_utilizzo_aziendale: percentuale(contesto.percentuale_utilizzo_aziendale),
        pro_rata_applicabile: typeof contesto.pro_rata_applicabile === 'boolean' ? String(contesto.pro_rata_applicabile) : '',
        pro_rata: percentuale(contesto.pro_rata ?? documento.pro_rata),
      });
    }).catch(error => {
      if (attivo) setErrore(error.response?.data?.detail || 'Impossibile leggere la fiscalità della fattura');
    });
    return () => { attivo = false; };
  }, [fatturaId]);

  const cambia = (campo, value) => { setForm(prev => ({ ...prev, [campo]: value })); setEsito(''); };
  const salvare = async event => {
    event.preventDefault();
    setSaving(true);
    setErrore('');
    setEsito('');
    try {
      if (!['true', 'false'].includes(form.inerente)) throw new Error('Confermare l’inerenza dell’acquisto');
      const dati = { inerente: form.inerente === 'true', fonte_documento: form.fonte_documento.trim(),
        validita_fiscale: { dal: form.dal, al: form.al } };
      if (form.uso_veicolo) Object.assign(dati, { tipo_veicolo: 'autovettura', uso_veicolo: form.uso_veicolo });
      if (form.percentuale_utilizzo_aziendale !== '') dati.percentuale_utilizzo_aziendale = Number(form.percentuale_utilizzo_aziendale) / 100;
      if (form.pro_rata_applicabile !== '') dati.pro_rata_applicabile = form.pro_rata_applicabile === 'true';
      if (form.pro_rata_applicabile === 'true') dati.pro_rata = Number(form.pro_rata) / 100;
      const { data } = await api.put(`/api/fatture/${encodeURIComponent(fatturaId)}/contesto-fiscale-iva`, dati);
      setFattura(data.fattura);
      setEsito(data.iva_da_verificare ? `Condizioni salvate. IVA ancora da verificare: ${data.motivo}` : 'Condizioni salvate e IVA ricalcolata.');
    } catch (error) {
      setErrore(error.response?.data?.detail || error.message || 'Conferma fiscale non riuscita');
    } finally { setSaving(false); }
  };
  const bloccata = fattura?.iva_utilizzata === true || ['INSERITA_IN_LIQUIDAZIONE', 'RECUPERATA_IN_DICHIARAZIONE_ANNUALE'].includes(fattura?.stato_detrazione_iva);

  return <details style={{ background: '#f6f4ee', borderBottom: '1px solid #dedbd3', flexShrink: 0 }}>
    <summary style={{ padding: '11px 16px', cursor: 'pointer', fontWeight: 700 }}>Fiscalità della fattura</summary>
    <div style={{ padding: '0 16px 14px', maxHeight: '45vh', overflowY: 'auto', color: '#353b35' }}>
      {errore && <p role="alert" style={{ color: '#a33527' }}>{errore}</p>}
      {!fattura && !errore && <p>Caricamento fiscalità...</p>}
      {fattura && <>
        <p style={{ fontSize: 13 }}>IVA detraibile: <strong>{fattura.percentuale_detraibilita_iva == null ? 'Da verificare' : `${percentuale(fattura.percentuale_detraibilita_iva)}%`}</strong>
          {fattura.iva_detraibile != null && ` · € ${Number(fattura.iva_detraibile).toLocaleString('it-IT', { minimumFractionDigits: 2 })}`}</p>
        {fattura.motivo_detraibilita_da_verificare && <p style={{ fontSize: 13 }}>{fattura.motivo_detraibilita_da_verificare}</p>}
        <p style={{ fontSize: 12 }}>Conferma solo condizioni sostenute da un documento. Per le auto il 70% riguarda il costo deducibile, non l’IVA; l’ammortamento del bene è distinto dalla detrazione IVA.</p>
        {!isAdmin ? <p>La conferma delle condizioni fiscali richiede un amministratore.</p> : bloccata ? <p>L’IVA è già utilizzata: occorre la riapertura della liquidazione prima di cambiarla.</p> :
          <form onSubmit={salvare} style={{ display: 'grid', gap: 12 }}>
            <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
              <label style={labelStyle}>Acquisto inerente all’attività
                <select required value={form.inerente || ''} onChange={e => cambia('inerente', e.target.value)} style={inputStyle}>
                  <option value="">Da confermare</option><option value="true">Sì, documentato</option><option value="false">No</option>
                </select>
              </label>
              <label style={labelStyle}>Documento che prova l’uso
                <input required maxLength={500} value={form.fonte_documento || ''} onChange={e => cambia('fonte_documento', e.target.value)} placeholder="Es. contratto, assegnazione, fattura e destinazione" style={inputStyle} />
              </label>
              <label style={labelStyle}>Validità dal<input type="date" required value={form.dal || ''} onChange={e => cambia('dal', e.target.value)} style={inputStyle} /></label>
              <label style={labelStyle}>Validità al<input type="date" required value={form.al || ''} onChange={e => cambia('al', e.target.value)} style={inputStyle} /></label>
              <label style={labelStyle}>Uso dell’autovettura, se pertinente
                <select value={form.uso_veicolo || ''} onChange={e => cambia('uso_veicolo', e.target.value)} style={inputStyle}>
                  <option value="">Non indicato / non pertinente</option><option value="promiscuo">Promiscuo, documentato</option><option value="esclusivo">Esclusivamente aziendale, documentato</option>
                </select>
              </label>
              <label style={labelStyle}>Utilizzo aziendale telefonia (%)
                <input type="number" min="0" max="100" step="0.01" value={form.percentuale_utilizzo_aziendale ?? ''} onChange={e => cambia('percentuale_utilizzo_aziendale', e.target.value)} placeholder="Solo se pertinente" style={inputStyle} />
              </label>
              <label style={labelStyle}>Pro rata IVA
                <select value={form.pro_rata_applicabile || ''} onChange={e => cambia('pro_rata_applicabile', e.target.value)} style={inputStyle}>
                  <option value="">Non indicato</option><option value="false">Non applicabile, verificato</option><option value="true">Applicabile, verificato</option>
                </select>
              </label>
              {form.pro_rata_applicabile === 'true' && <label style={labelStyle}>Quota pro rata (%)
                <input type="number" required min="0" max="100" step="0.01" value={form.pro_rata ?? ''} onChange={e => cambia('pro_rata', e.target.value)} style={inputStyle} />
              </label>}
            </div>
            <p style={{ fontSize: 12, margin: 0 }}>Salvando confermi la documentazione e ricalcoli l’IVA di questa fattura. Il periodo chiuso resta protetto.</p>
            <button type="submit" disabled={saving} style={{ ...inputStyle, background: '#c15f3c', color: 'white', fontWeight: 700, cursor: 'pointer' }}>{saving ? 'Salvataggio...' : 'Conferma condizioni e ricalcola IVA'}</button>
            {esito && <p role="status" style={{ fontSize: 13, margin: 0 }}>{esito}</p>}
          </form>}
      </>}
    </div>
  </details>;
}
