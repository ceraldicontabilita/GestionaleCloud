import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Plus, X } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, formatDateIT, COLORS, BORDER_RADIUS } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import ApriOriginale from '../components/ApriOriginale';
import ModalFattura from '../components/ModalFattura';
import LinkContropartita, { ROTTE_CONTROPARTITA } from '../components/LinkContropartita';
import { useConfirm } from '../components/ui/ConfirmDialog';
import { Button, Badge, StatCard, Input, Select, ListaAdattiva } from '../components/ds';

const emptyForm = () => ({ data_scadenza: '', descrizione: '', tipo: 'CUSTOM', importo: '', priorita: 'media', note: '' });
const chiusa = s => Boolean(s.completata || s.pagata);
const euroCents = n => n == null ? 'Non disponibile' : formatEuro(n / 100);
const errorText = e => {
  const detail = e.response?.data?.detail;
  return Array.isArray(detail) ? detail.map(x => x.msg).join('; ') : detail || e.message || 'Errore di caricamento';
};
const box = { background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.lg, padding: 16, marginBottom: 16, minWidth: 0 };
const flex = { display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' };
const nomiMesi = ['Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno', 'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre'];

export default function Scadenze() {
  const { anno } = useAnnoGlobale();
  const confirm = useConfirm();
  const navigate = useNavigate();
  const [tipo, setTipo] = useState('');
  const [stato, setStato] = useState('aperte');
  const [mese, setMese] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [viewingInvoice, setViewingInvoice] = useState(null);
  const request = useRef(0);
  const filters = `${anno}|${tipo}|${stato}|${mese}`;
  const visible = result?.filters === filters ? result : null;
  const rows = visible?.scadenze || [];

  const load = useCallback(async (offset = 0) => {
    const version = ++request.current;
    if (offset) setLoadingMore(true);
    else { setLoading(true); setError(''); setResult(null); setLoadingMore(false); }
    const params = new URLSearchParams({ anno, stato, limit: '50', offset: String(offset) });
    if (tipo) params.set('tipo', tipo);
    if (mese) params.set('mese', mese);
    try {
      const { data } = await api.get(`/api/scadenze/tutte?${params}`);
      if (request.current !== version) return;
      setResult(previous => ({ ...data, filters,
        scadenze: offset && previous?.filters === filters ? [...previous.scadenze, ...data.scadenze] : data.scadenze || [],
      }));
    } catch (e) {
      if (request.current !== version) return;
      if (offset) toast.error(`Altre scadenze non disponibili: ${errorText(e)}`);
      else { setResult(null); setError(errorText(e)); }
    } finally {
      if (request.current === version) { setLoading(false); setLoadingMore(false); }
    }
  }, [anno, tipo, stato, mese, filters]);

  useEffect(() => {
    load();
    return () => { request.current += 1; };
  }, [load]);

  const completa = async s => {
    if (chiusa(s)) return;
    try { await api.put(`/api/scadenze/completa/${encodeURIComponent(s.id)}`); load(); }
    catch (e) { toast.error(errorText(e)); }
  };
  const elimina = async s => {
    if (!await confirm({ title: 'Elimina promemoria', message: s.descrizione, confirmText: 'Elimina', cancelText: 'Annulla', variant: 'danger' })) return;
    try { await api.delete(`/api/scadenze/${encodeURIComponent(s.id)}`); load(); }
    catch (e) { toast.error(errorText(e)); }
  };
  const crea = async e => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post('/api/scadenze/crea', { ...form, importo: form.importo === '' ? null : Number(form.importo) });
      setShowModal(false); setForm(emptyForm()); load();
    } catch (err) { toast.error(errorText(err)); }
    finally { setSaving(false); }
  };
  const paga = async s => {
    // Il tipo del promemoria non è l'identità di una fattura.
    if (!s.fattura_id || chiusa(s)) return;
    navigate(ROTTE_CONTROPARTITA.fattura(s.fattura_id));
  };
  const azioni = s => <div style={flex}>
    {(s.documenti || []).map(d => <ApriOriginale key={d.url} url={d.url} titolo={d.titolo}>{d.titolo}</ApriOriginale>)}
    {s.dettaglio_url && (s.dettaglio_url.startsWith('/hr/') ? <a href={s.dettaglio_url}>Apri dipendente</a> : <Link to={s.dettaglio_url}>Apri dettaglio</Link>)}
    {s.fattura_id && <>
      <Button size="sm" onClick={() => setViewingInvoice({ id: s.fattura_id, numero: s.numero_fattura || s.descrizione })}>Apri fattura</Button>
      {!chiusa(s) && <Button size="sm" onClick={() => paga(s)}>Paga</Button>}
    </>}
    {s.pagamento?.movimento_bancario_id && <LinkContropartita
      to={ROTTE_CONTROPARTITA.movimentoBanca(s.pagamento.movimento_bancario_id)} compatto
      testId={`link-movimento-pagante-${s.id}`} title={`Movimento del ${formatDateIT(s.pagamento.data_pagamento || '')}`}>
      Movimento che l'ha pagata
    </LinkContropartita>}
    {s.source === 'custom' && <>
      {!chiusa(s) && <Button size="sm" onClick={() => completa(s)}>Segna come completata</Button>}
      <Button variant="danger" size="sm" onClick={() => elimina(s)}>Elimina promemoria</Button>
    </>}
  </div>;

  const stats = visible?.statistiche;
  return <PageLayout title="Scadenze" subtitle={`Scadenze dell'anno ${anno}: tributi, rate e adempimenti`} actions={
    <Button iconLeft={<Plus size={16} />} onClick={() => setShowModal(true)}>Nuova scadenza</Button>
  }>
    <div style={{ ...box, ...flex }}>
      <label>Tipo <Select aria-label="Tipo" value={tipo} onChange={e => setTipo(e.target.value)}>
        <option value="">Tutti i tipi</option>
        {[...new Set([...(visible?.tipi || []), tipo, 'CUSTOM', 'F24', 'IVA', 'INPS', 'ADER', 'ADEMPIMENTO'])].filter(Boolean).sort().map(t =>
          <option key={t} value={t}>{t === 'CUSTOM' ? 'Tutti i promemoria' : t}</option>)}
      </Select></label>
      <label>Stato <Select aria-label="Stato" value={stato} onChange={e => setStato(e.target.value)}>
        <option value="aperte">Aperte, comprese le scadute</option><option value="scadute">Scadute aperte</option>
        <option value="da_verificare">Da verificare</option><option value="chiuse">Pagate o completate</option><option value="tutte">Tutti gli stati</option>
      </Select></label>
      <label>Mese di scadenza <Select aria-label="Mese di scadenza" value={mese} onChange={e => setMese(e.target.value)}>
        <option value="">Tutto l'anno</option>{nomiMesi.map((n, i) => <option key={n} value={i + 1}>{n}</option>)}
      </Select></label>
      <Button onClick={() => load()} disabled={loading}>Aggiorna</Button>
    </div>
    {loading || (!visible && !error) ? <p role="status">Caricamento delle scadenze e delle prove…</p> : error ?
      <div role="alert" style={box}><p>Scadenze non disponibili. I dati non sono stati caricati.</p><p>{error}</p><Button onClick={() => load()}>Riprova</Button></div> : <>
      {stats && <div style={{ ...box }}>
        <p style={{ marginTop: 0 }}>Riepilogo dell'anno {anno}, con i filtri selezionati</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 185px), 1fr))', gap: 12 }}>
          <StatCard label="Residuo documentato" value={formatEuro(stats.totale_importo)} accent="warning" />
          <StatCard label="Aperte" value={stats.aperte} />
          <StatCard label="Scadute o entro 3 giorni" value={stats.urgenti} accent="danger" />
          <StatCard label="Da verificare" value={stats.da_verificare} accent="warning" />
        </div>
        <p style={{ marginBottom: 0 }}>Il residuo esclude importi non disponibili e voci con incongruenze. {stats.importi_non_disponibili || 0} importi non disponibili. Le chiusure dei promemoria non certificano un pagamento.</p>
      </div>}
      <section aria-label="Scadenze dell'anno" style={box}>
        <p>{visible.totale || 0} scadenze · ordinate per data</p>
        {rows.length ? <ListaAdattiva testId="scadenze-table" dati={rows} chiave={s => s.id} pageSize={rows.length || 50} cardBreakpoint={1100} resetKey={filters}
          colonne={[
            { key: 'descrizione', label: 'Obbligo e periodo', ruoloCard: 'titolo', render: s => <div style={{ overflowWrap: 'anywhere' }}>
              <strong>{s.descrizione}</strong><div>{s.tipo}{s.codici?.length ? ` · ${s.codici.join(', ')}` : ''}{s.periodo ? ` · ${s.periodo}` : ''}</div>
              {s.atteso_da_buste && <p>Prospetto paghe: {euroCents(s.atteso_da_buste.importo_cents)}{s.atteso_da_buste.differenza_cents ? ` · differenza con F24: ${euroCents(s.atteso_da_buste.differenza_cents)}` : ''}</p>}
              {s.note && <details style={{ marginTop: 8 }}><summary>Note</summary><p style={{ whiteSpace: 'pre-wrap' }}>{s.note}</p></details>}
            </div> },
            { key: 'data', label: 'Scadenza', ruoloCard: 'dettaglio', render: s => s.data ? formatDateIT(s.data) : 'Data da verificare' },
            { key: 'stato', label: 'Stato', ruoloCard: 'dettaglio', render: s => <Badge variant={chiusa(s) ? 'success' : s.da_verificare ? 'warning' : s.urgente ? 'danger' : 'info'}>
              {s.pagata && s.pagamento?.data_pagamento ? `Pagata il ${formatDateIT(s.pagamento.data_pagamento)}` : s.stato_label || (chiusa(s) ? 'Completata' : 'Aperta')}
            </Badge> },
            { key: 'importo_cents', label: 'Dovuto', ruoloCard: 'dettaglio', render: s => s.monetaria === false ? 'Adempimento' : euroCents(s.importo_cents ?? (s.importo != null ? Math.round(s.importo * 100) : null)) },
            { key: 'pagato_cents', label: 'Pagato', ruoloCard: 'dettaglio', render: s => s.monetaria === false ? '—' : euroCents(s.pagato_cents) },
            { key: 'residuo_cents', label: 'Residuo', ruoloCard: 'importo', render: s => s.monetaria === false ? '—' : <span>{euroCents(s.residuo_cents)}{s.conteggiabile === false && !chiusa(s) && <small style={{ display: 'block' }}>Escluso dal totale: da verificare</small>}</span> },
            { key: 'azioni', label: 'Documenti e azioni', ruoloCard: 'azioni', render: azioni },
          ]} /> : <p>Nessuna scadenza per i filtri selezionati.</p>}
        {rows.length < visible.totale && <Button onClick={() => load(rows.length)} disabled={loadingMore}>{loadingMore ? 'Caricamento…' : 'Carica altre scadenze'}</Button>}
      </section>
      <section aria-label="Documenti da verificare" style={box}>
        <h3 style={{ marginTop: 0 }}>Documenti da verificare</h3><p>{visible.documenti_periodo || 'Archivio completo, tutti gli anni'}</p>
        <div style={flex}>{(visible.documenti_da_verificare || []).map(p => <Link key={p.id} to={p.url}>{p.titolo}: {p.conteggio}</Link>)}</div>
        {visible.segnalazioni?.length > 0 && <details style={{ marginTop: 12 }}><summary>Segnalazioni sui piani ({visible.segnalazioni.length})</summary>
          <ul>{visible.segnalazioni.map(s => <li key={s.id}>{s.messaggio} · <Link to={s.url}>Apri piano</Link></li>)}</ul>
        </details>}
      </section>
    </>}
    {showModal && <div role="dialog" aria-modal="true" aria-label="Nuova scadenza" style={{ position: 'fixed', inset: 0, zIndex: 200, background: '#0008', display: 'grid', placeItems: 'center', padding: 12 }}>
      <form onSubmit={crea} style={{ ...box, width: 'min(100%, 520px)', maxHeight: '90dvh', overflowY: 'auto', margin: 0 }}>
        <div style={{ ...flex, justifyContent: 'space-between' }}><h3>Nuovo promemoria</h3><Button type="button" aria-label="Chiudi" onClick={() => setShowModal(false)}><X size={18} /></Button></div>
        <label>Data di scadenza<Input type="date" required min="2000-01-01" max="2100-12-31" value={form.data_scadenza} onChange={e => setForm({ ...form, data_scadenza: e.target.value })} /></label>
        <label>Descrizione<Input required maxLength={2000} value={form.descrizione} onChange={e => setForm({ ...form, descrizione: e.target.value })} /></label>
        <label>Tipo<Select value={form.tipo} onChange={e => setForm({ ...form, tipo: e.target.value })}>{['CUSTOM', 'IVA', 'F24', 'INPS', 'INAIL', 'IMU', 'IRES', 'IRAP', 'FATTURA', 'ALTRO'].map(t => <option key={t} value={t}>{t === 'CUSTOM' ? 'Personalizzata' : t}</option>)}</Select></label>
        <label>Importo, se noto<Input type="number" min="0" step="0.01" value={form.importo} onChange={e => setForm({ ...form, importo: e.target.value })} /></label>
        <label>Note<Input maxLength={10000} value={form.note} onChange={e => setForm({ ...form, note: e.target.value })} /></label>
        <p>Questo promemoria non crea fatture o versamenti.</p>
        <Button type="submit" disabled={saving}>{saving ? 'Salvataggio…' : 'Salva promemoria'}</Button>
      </form>
    </div>}
    {viewingInvoice && <ModalFattura fatturaId={viewingInvoice.id} numero={viewingInvoice.numero} onClose={() => setViewingInvoice(null)} />}
  </PageLayout>;
}
