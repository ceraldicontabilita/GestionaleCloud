import React, { useEffect, useMemo, useState } from 'react';
import {
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  Download,
  FileText,
  Landmark,
  Loader2,
  Paperclip,
  Search,
  TriangleAlert,
} from 'lucide-react';
import { toast } from 'sonner';
import api from '../api';
import { formatEuroD } from '../lib/utils';

const MESI = [
  '', 'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
  'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre',
  'Tredicesima', 'Quattordicesima',
];

const numero = valore => Number(valore || 0);
const nomeRiga = riga => String(
  riga.dipendente_nome || riga.dipendente || riga.nome_dipendente || '',
).trim();
const importoAccontoRiga = riga => Math.max(
  numero(riga.importo_bonifico),
  numero(riga.importo_bonifico_documentato),
);

function saldoStyle(saldo) {
  if (Math.abs(saldo) < 0.01) return { color: '#15803d', background: '#dcfce7' };
  if (saldo > 0) return { color: '#9a6700', background: '#fef3c7' };
  return { color: '#b91c1c', background: '#fee2e2' };
}

function aggregaRighe(righe) {
  const mensilita = new Map();
  for (const riga of righe) {
    const dipendente = nomeRiga(riga) || 'Dipendente da identificare';
    const identita = String(riga.dipendente_id || riga.codice_fiscale || dipendente.toUpperCase());
    const anno = Number(riga.anno) || 0;
    const tipoCedolino = String(riga.tipo_cedolino || 'mensile').toLowerCase();
    const meseOriginale = Number(riga.mese) || 0;
    const mese = tipoCedolino === 'tredicesima' ? 13 : tipoCedolino === 'quattordicesima' ? 14 : meseOriginale;
    const chiave = `${identita}|${anno}|${meseOriginale}|${tipoCedolino}`;
    if (!mensilita.has(chiave)) mensilita.set(chiave, { identita, dipendente, anno, mese, meseOriginale, tipoCedolino, righe: [] });
    mensilita.get(chiave).righe.push(riga);
  }

  const dipendenti = new Map();
  for (const gruppo of mensilita.values()) {
    const valoriBusta = gruppo.righe.map(r => numero(r.importo_busta)).filter(v => v > 0);
    gruppo.importoBusta = valoriBusta.length ? Math.max(...valoriBusta) : 0;
    gruppo.importoAcconti = gruppo.righe.reduce((totale, r) => totale + importoAccontoRiga(r), 0);
    gruppo.saldo = gruppo.importoBusta - gruppo.importoAcconti;
    gruppo.rigaCedolino = gruppo.righe.find(r => r.cedolino_disponibile);
    gruppo.rigaBonifico = gruppo.righe.find(r => r.bonifico_documento_disponibile);
    gruppo.cedolinoDisponibile = Boolean(gruppo.rigaCedolino);
    gruppo.bonificoDisponibile = Boolean(gruppo.rigaBonifico);
    const righeConPagamento = gruppo.righe.filter(r => importoAccontoRiga(r) > 0);
    gruppo.riconciliato = righeConPagamento.length > 0 && righeConPagamento.every(r => r.riconciliato === true);
    gruppo.daRivedere = gruppo.righe.some(r => r.riconciliazione_precedente_da_rivedere);

    if (!dipendenti.has(gruppo.identita)) dipendenti.set(gruppo.identita, { id: gruppo.identita, nome: gruppo.dipendente, anni: new Map() });
    const dipendente = dipendenti.get(gruppo.identita);
    if (!dipendente.anni.has(gruppo.anno)) dipendente.anni.set(gruppo.anno, []);
    dipendente.anni.get(gruppo.anno).push(gruppo);
  }

  return [...dipendenti.values()].map(dipendente => {
    dipendente.anni = [...dipendente.anni.entries()].map(([anno, mesi]) => {
      mesi.sort((a, b) => a.mese - b.mese);
      return {
        anno,
        mesi,
        busta: mesi.reduce((totale, mese) => totale + mese.importoBusta, 0),
        acconti: mesi.reduce((totale, mese) => totale + mese.importoAcconti, 0),
        saldo: mesi.reduce((totale, mese) => totale + mese.saldo, 0),
      };
    }).sort((a, b) => b.anno - a.anno);
    return dipendente;
  }).sort((a, b) => a.nome.localeCompare(b.nome, 'it'));
}

export default function CedoliniSalari() {
  const [righe, setRighe] = useState([]);
  const [loading, setLoading] = useState(true);
  const [ricerca, setRicerca] = useState('');
  const [annoFiltro, setAnnoFiltro] = useState('tutti');
  const [documentoInApertura, setDocumentoInApertura] = useState(null);
  const [exportInCorso, setExportInCorso] = useState(false);

  useEffect(() => {
    let attivo = true;
    setLoading(true);
    api.get('/api/prima-nota-salari/salari')
      .then(r => { if (attivo) setRighe(Array.isArray(r.data) ? r.data : []); })
      .catch(() => { if (attivo) toast.error('Impossibile caricare i cedolini'); })
      .finally(() => { if (attivo) setLoading(false); });
    return () => { attivo = false; };
  }, []);

  const esportaAppDipendenti = async () => {
    setExportInCorso(true);
    try {
      const params = annoFiltro !== 'tutti' ? { anno: annoFiltro } : {};
      const risposta = await api.get('/api/prima-nota-salari/export-appdipendenti/download', { params, responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([risposta.data], { type: 'application/zip' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = 'export_appdipendenti.zip';
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 60000);
      toast.success('Export AppDipendenti creato con PDF originali e fogli Excel');
    } catch (errore) {
      toast.error(errore.response?.data?.detail || 'Export AppDipendenti non riuscito');
    } finally {
      setExportInCorso(false);
    }
  };

  const apriDocumento = async (tipo, riga) => {
    const chiave = `${tipo}-${riga.id}`;
    setDocumentoInApertura(chiave);
    try {
      const risposta = await api.get(`/api/prima-nota-salari/salari/${encodeURIComponent(riga.id)}/${tipo}-pdf`, { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([risposta.data], { type: 'application/pdf' }));
      const finestra = window.open(url, '_blank', 'noopener,noreferrer');
      if (!finestra) {
        const link = document.createElement('a');
        link.href = url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.click();
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (errore) {
      toast.error(errore.response?.data?.detail || `PDF ${tipo} non disponibile`);
    } finally {
      setDocumentoInApertura(null);
    }
  };

  const datiDipendenti = useMemo(() => aggregaRighe(righe), [righe]);
  const anniDisponibili = [...new Set(righe.map(r => Number(r.anno)).filter(Number.isFinite))].sort((a, b) => b - a);
  const termine = ricerca.trim().toLowerCase();
  const dipendentiVisibili = datiDipendenti
    .filter(d => !termine || d.nome.toLowerCase().includes(termine))
    .map(d => ({ ...d, anni: d.anni.filter(a => annoFiltro === 'tutti' || Number(a.anno) === Number(annoFiltro)) }))
    .filter(d => d.anni.length > 0);
  const totali = dipendentiVisibili.reduce((acc, d) => {
    for (const anno of d.anni) {
      acc.busta += anno.busta;
      acc.acconti += anno.acconti;
      acc.saldo += anno.saldo;
    }
    return acc;
  }, { busta: 0, acconti: 0, saldo: 0 });

  return (
    <main style={{ maxWidth: 1680, margin: '0 auto', padding: '22px 20px 60px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'end', gap: 16, flexWrap: 'wrap', marginBottom: 18 }}>
        <div>
          <h1 style={{ margin: 0, color: '#0f2744', fontSize: 27 }}>Cedolini, acconti e bonifici per dipendente</h1>
          <p style={{ margin: '6px 0 0', color: '#64748b' }}>
            I documenti vengono acquisiti esclusivamente da Documenti. Qui controlli importi, allegati gia acquisiti e riscontro bancario reale.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'end', flexWrap: 'wrap' }}>
          <button type="button" onClick={esportaAppDipendenti} disabled={exportInCorso} title="Esporta i PDF originali e i registri per AppDipendenti" style={{ minHeight: 42, borderRadius: 9, padding: '10px 14px', border: '1px solid #cbd5e1', background: '#fff', color: '#0f2744', fontWeight: 750, cursor: exportInCorso ? 'wait' : 'pointer', display: 'inline-flex', alignItems: 'center', gap: 7 }}>
            {exportInCorso ? <Loader2 size={18} className="spin" /> : <Download size={18} />}
            {exportInCorso ? 'Esportazione...' : 'Export AppDipendenti'}
          </button>
          <label style={{ display: 'grid', gap: 5, color: '#475569', fontSize: 12, fontWeight: 700 }}>
            Anno
            <select value={annoFiltro} onChange={e => setAnnoFiltro(e.target.value)} aria-label="Anno cedolini" style={{ minWidth: 150, minHeight: 42, padding: '8px 10px', border: '1px solid #cbd5e1', borderRadius: 9, background: '#fff' }}>
              <option value="tutti">Tutti gli anni</option>
              {anniDisponibili.map(valore => <option key={valore} value={valore}>{valore}</option>)}
            </select>
          </label>
          <label style={{ position: 'relative', minWidth: 285 }}>
            <Search size={18} style={{ position: 'absolute', left: 12, top: 12, color: '#64748b' }} />
            <input value={ricerca} onChange={e => setRicerca(e.target.value)} placeholder="Cerca dipendente" aria-label="Cerca dipendente" style={{ width: '100%', minHeight: 42, padding: '8px 12px 8px 40px', border: '1px solid #cbd5e1', borderRadius: 9 }} />
          </label>
        </div>
      </div>

      <section aria-label="Totali del periodo" style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(190px, 1fr))', gap: 12, marginBottom: 18 }}>
        {[
          ['Importo buste', totali.busta, '#2563eb', <FileText size={20} key="b" />],
          ['Acconti / bonifici', totali.acconti, '#7c3aed', <Landmark size={20} key="a" />],
          ['Saldo busta − acconti', totali.saldo, saldoStyle(totali.saldo).color, <CalendarDays size={20} key="s" />],
        ].map(([titolo, valore, colore, icona]) => (
          <div key={titolo} style={{ background: '#fff', border: '1px solid #e2e8f0', borderLeft: `5px solid ${colore}`, borderRadius: 12, padding: '16px 18px' }}>
            <div style={{ color: '#64748b', fontWeight: 750, fontSize: 12, display: 'flex', alignItems: 'center', gap: 7 }}>{icona}{titolo}</div>
            <strong style={{ display: 'block', color: colore, fontSize: 25, marginTop: 7 }}>{formatEuroD(valore)}</strong>
          </div>
        ))}
      </section>

      {loading && <div style={{ padding: 45, textAlign: 'center', color: '#64748b' }}><Loader2 size={23} className="spin" /> Caricamento...</div>}
      {!loading && dipendentiVisibili.length === 0 && <div style={{ padding: 45, textAlign: 'center', color: '#64748b', background: '#fff', borderRadius: 12 }}>Nessun dato trovato.</div>}

      <section style={{ display: 'grid', gap: 14 }}>
        {!loading && dipendentiVisibili.map(dipendente => (
          <details key={dipendente.id} open={Boolean(termine)} style={{ background: '#fff', border: '1px solid #dbe4ee', borderRadius: 13, overflow: 'hidden', boxShadow: '0 2px 7px rgba(15,39,68,.05)' }}>
            <summary style={{ listStyle: 'none', cursor: 'pointer', padding: '15px 18px', display: 'grid', gridTemplateColumns: 'minmax(220px, 1.4fr) repeat(3, minmax(135px, .7fr)) 28px', gap: 12, alignItems: 'center', background: '#f8fafc' }}>
              <strong style={{ color: '#0f2744', fontSize: 17 }}>{dipendente.nome}</strong>
              <span><small style={{ display: 'block', color: '#64748b' }}>BUSTE</small><b>{formatEuroD(dipendente.anni.reduce((t, a) => t + a.busta, 0))}</b></span>
              <span><small style={{ display: 'block', color: '#64748b' }}>ACCONTI / BONIFICI</small><b>{formatEuroD(dipendente.anni.reduce((t, a) => t + a.acconti, 0))}</b></span>
              <span><small style={{ display: 'block', color: '#64748b' }}>SALDO</small><b style={{ color: saldoStyle(dipendente.anni.reduce((t, a) => t + a.saldo, 0)).color }}>{formatEuroD(dipendente.anni.reduce((t, a) => t + a.saldo, 0))}</b></span>
              <ChevronDown size={21} color="#64748b" />
            </summary>

            <div style={{ padding: 15, display: 'grid', gap: 14 }}>
              {dipendente.anni.map(anno => (
                <section key={anno.anno} style={{ border: '1px solid #e2e8f0', borderRadius: 11, overflow: 'hidden' }}>
                  <header style={{ display: 'grid', gridTemplateColumns: '110px repeat(3, minmax(130px, 1fr))', gap: 10, alignItems: 'center', padding: '12px 14px', background: '#0f2744', color: '#fff' }}>
                    <strong style={{ fontSize: 18 }}>{anno.anno}</strong>
                    <span><small style={{ opacity: .75 }}>Busta</small><b style={{ display: 'block' }}>{formatEuroD(anno.busta)}</b></span>
                    <span><small style={{ opacity: .75 }}>Acconti / bonifici</small><b style={{ display: 'block' }}>{formatEuroD(anno.acconti)}</b></span>
                    <span><small style={{ opacity: .75 }}>Saldo</small><b style={{ display: 'block' }}>{formatEuroD(anno.saldo)}</b></span>
                  </header>
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1040 }}>
                      <thead style={{ background: '#eef2f7', color: '#475569' }}>
                        <tr>
                          {['Mese', 'Importo busta', 'Acconti / bonifici', 'Saldo', 'Cedolino', 'Bonifico', 'Stato banca'].map(titolo => (
                            <th key={titolo} style={{ padding: '10px 12px', textAlign: ['Mese', 'Cedolino', 'Bonifico', 'Stato banca'].includes(titolo) ? 'left' : 'right', fontSize: 11 }}>{titolo}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {anno.mesi.map(mese => {
                          const stileSaldo = saldoStyle(mese.saldo);
                          return (
                            <tr key={`${anno.anno}-${mese.meseOriginale}-${mese.tipoCedolino}`} style={{ borderTop: '1px solid #e2e8f0' }}>
                              <td style={{ padding: '11px 12px', fontWeight: 800, color: '#0f2744' }}>{MESI[mese.mese] || `Mese ${mese.mese}`}</td>
                              <td style={{ padding: '11px 12px', textAlign: 'right', fontWeight: 800 }}>{formatEuroD(mese.importoBusta)}</td>
                              <td style={{ padding: '11px 12px', textAlign: 'right', fontWeight: 800 }}>{formatEuroD(mese.importoAcconti)}</td>
                              <td style={{ padding: '11px 12px', textAlign: 'right' }}><span style={{ ...stileSaldo, borderRadius: 999, padding: '5px 9px', fontWeight: 850 }}>{formatEuroD(mese.saldo)}</span></td>
                              <td style={{ padding: '8px 12px' }}>
                                {mese.cedolinoDisponibile ? (
                                  <button type="button" onClick={() => apriDocumento('cedolino', mese.rigaCedolino)} disabled={documentoInApertura === `cedolino-${mese.rigaCedolino.id}`} style={{ minHeight: 38, border: 0, borderRadius: 8, padding: '8px 10px', background: '#2563eb', color: '#fff', fontWeight: 750, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                                    <FileText size={16} /> Vedi
                                  </button>
                                ) : <span style={{ color: '#64748b' }}>Non acquisito</span>}
                              </td>
                              <td style={{ padding: '8px 12px' }}>
                                {mese.bonificoDisponibile ? (
                                  <button type="button" onClick={() => apriDocumento('bonifico', mese.rigaBonifico)} disabled={documentoInApertura === `bonifico-${mese.rigaBonifico.id}`} style={{ minHeight: 38, border: 0, borderRadius: 8, padding: '8px 10px', background: '#7c3aed', color: '#fff', fontWeight: 750, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                                    <Paperclip size={16} /> Vedi
                                  </button>
                                ) : <span style={{ color: '#64748b' }}>Non acquisito</span>}
                              </td>
                              <td style={{ padding: '11px 12px' }}>
                                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: mese.riconciliato ? '#15803d' : '#b45309', fontWeight: 750 }}>
                                  {mese.riconciliato ? <CheckCircle2 size={17} /> : <TriangleAlert size={17} />}
                                  {mese.riconciliato ? 'Riconciliato con estratto conto' : mese.daRivedere ? 'Associazione da rivedere' : 'Da verificare in banca'}
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </section>
              ))}
            </div>
          </details>
        ))}
      </section>
    </main>
  );
}
