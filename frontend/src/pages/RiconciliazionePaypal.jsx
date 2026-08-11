import React, { useCallback, useEffect, useMemo, useState } from 'react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { toast } from 'sonner';
import { PageLayout } from '../components/PageLayout';

const euro = valore => new Intl.NumberFormat('it-IT', {
  style: 'currency',
  currency: 'EUR',
}).format(Number(valore || 0));

const dataIT = valore => {
  if (!valore) return '-';
  const data = new Date(valore);
  return Number.isNaN(data.getTime()) ? String(valore) : data.toLocaleDateString('it-IT');
};

export default function RiconciliazionePaypal() {
  const { anno } = useAnnoGlobale();
  const [loading, setLoading] = useState(true);
  const [errore, setErrore] = useState('');
  const [statoApi, setStatoApi] = useState(null);
  const [transazioni, setTransazioni] = useState([]);
  const [movimentiBanca, setMovimentiBanca] = useState([]);
  const [ricerca, setRicerca] = useState('');

  const caricaDati = useCallback(async () => {
    const paramsAnno = anno ? `?anno=${anno}` : '';
    const paramsTx = new URLSearchParams({ limit: '1000', solo_pagamenti: 'true' });
    if (anno) paramsTx.append('anno', anno);
    const paramsBanca = new URLSearchParams({ limit: '5000' });
    if (anno) paramsBanca.append('anno', anno);

    const [apiStatus, tx, banca] = await Promise.all([
      api.get('/api/paypal-api/status'),
      api.get(`/api/paypal-statements/transactions?${paramsTx}`),
      api.get(`/api/paypal-statements/bank-movements?${paramsBanca}`),
    ]);

    setStatoApi(apiStatus.data || null);
    setTransazioni(tx.data?.transactions || []);
    setMovimentiBanca(banca.data?.movimenti || []);
    return { apiStatus: apiStatus.data || null, paramsAnno };
  }, [anno]);

  const sincronizzaAutomaticamente = useCallback(async () => {
    try {
      const stato = await api.get('/api/paypal-api/status');
      setStatoApi(stato.data || null);
      if (!stato.data?.api_configurata) return;

      const oggi = new Date();
      const inizio = new Date(oggi.getFullYear(), oggi.getMonth() - 2, 1);
      await api.post('/api/paypal-api/sync', {
        start_date: inizio.toISOString().slice(0, 10),
        end_date: oggi.toISOString().slice(0, 10),
      });
    } catch (e) {
      console.error('Sincronizzazione PayPal non riuscita', e);
    }
  }, []);

  useEffect(() => {
    let attivo = true;
    (async () => {
      setLoading(true);
      setErrore('');
      try {
        await sincronizzaAutomaticamente();
        if (attivo) await caricaDati();
      } catch (e) {
        if (attivo) setErrore(e.response?.data?.detail || e.message || 'Errore caricamento PayPal');
      } finally {
        if (attivo) setLoading(false);
      }
    })();
    return () => { attivo = false; };
  }, [caricaDati, sincronizzaAutomaticamente]);

  const riconciliaBanca = async () => {
    try {
      await api.post(`/api/paypal-statements/riprocessa?anno=${anno}`);
      await caricaDati();
      toast.success('Riconciliazione PayPal aggiornata');
    } catch (e) {
      toast.error(e.response?.data?.detail || e.message || 'Riconciliazione non riuscita');
    }
  };

  const righe = useMemo(() => {
    const termine = ricerca.trim().toLowerCase();
    if (!termine) return transazioni;
    return transazioni.filter(tx => `${tx.nome_controparte || ''} ${tx.descrizione || ''} ${tx.email_controparte || ''}`
      .toLowerCase().includes(termine));
  }, [transazioni, ricerca]);

  const riconciliati = movimentiBanca.filter(m => m.riconciliato_paypal).length;
  const daVerificare = movimentiBanca.length - riconciliati;

  return (
    <PageLayout>
      <main style={{ maxWidth: 1400, margin: '0 auto', padding: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
          <div>
            <h1 style={{ margin: 0 }}>PayPal</h1>
            <p style={{ margin: '6px 0 0', color: '#64748b' }}>
              Sincronizzazione automatica all'apertura. I documenti si acquisiscono solo da Documenti.
            </p>
          </div>
          <button type="button" onClick={riconciliaBanca} style={{ minHeight: 40, padding: '8px 14px', borderRadius: 8, border: '1px solid #cbd5e1', background: '#fff', cursor: 'pointer', fontWeight: 700 }}>
            Rielabora collegamenti
          </button>
        </div>

        {errore && <div role="alert" style={{ padding: 12, background: '#fef2f2', color: '#991b1b', borderRadius: 8, marginBottom: 12 }}>{errore}</div>}
        {statoApi && !statoApi.api_configurata && (
          <div style={{ padding: 12, background: '#eff6ff', color: '#1d4ed8', borderRadius: 8, marginBottom: 12 }}>
            API PayPal non configurata. Le transazioni gia presenti restano consultabili e riconciliabili.
          </div>
        )}

        <section style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(150px, 1fr))', gap: 10, marginBottom: 16 }}>
          <div style={card}><small>Transazioni</small><strong style={value}>{transazioni.length}</strong></div>
          <div style={card}><small>Movimenti banca</small><strong style={value}>{movimentiBanca.length}</strong></div>
          <div style={card}><small>Riconciliati</small><strong style={value}>{riconciliati}</strong></div>
          <div style={card}><small>Da verificare</small><strong style={value}>{daVerificare}</strong></div>
        </section>

        <input
          value={ricerca}
          onChange={e => setRicerca(e.target.value)}
          placeholder="Cerca controparte, descrizione o email"
          style={{ width: '100%', minHeight: 40, padding: '8px 10px', border: '1px solid #cbd5e1', borderRadius: 8, marginBottom: 12 }}
        />

        {loading ? (
          <div style={{ padding: 30, color: '#64748b' }}>Caricamento…</div>
        ) : (
          <div style={{ overflowX: 'auto', background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900 }}>
              <thead style={{ background: '#f8fafc' }}>
                <tr>
                  {['Data', 'Controparte', 'Descrizione', 'Importo', 'Fattura', 'Stato'].map(t => <th key={t} style={th}>{t}</th>)}
                </tr>
              </thead>
              <tbody>
                {righe.map(tx => (
                  <tr key={tx.transaction_id || tx.id} style={{ borderTop: '1px solid #e2e8f0' }}>
                    <td style={td}>{dataIT(tx.data || tx.date)}</td>
                    <td style={td}>{tx.nome_controparte || '-'}</td>
                    <td style={td}>{tx.descrizione || '-'}</td>
                    <td style={{ ...td, textAlign: 'right', fontWeight: 700 }}>{euro(tx.importo)}</td>
                    <td style={td}>{tx.fattura_numero || tx.stato_collegamento_fattura || '-'}</td>
                    <td style={td}>{tx.riconciliato_banca ? 'Riconciliato' : 'Da verificare'}</td>
                  </tr>
                ))}
                {righe.length === 0 && (
                  <tr><td colSpan={6} style={{ ...td, textAlign: 'center', color: '#64748b' }}>Nessuna transazione</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </PageLayout>
  );
}

const card = { background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, padding: 14 };
const value = { display: 'block', marginTop: 6, fontSize: 24, color: '#0f2744' };
const th = { padding: '10px 12px', textAlign: 'left', fontSize: 12, color: '#475569' };
const td = { padding: '10px 12px', fontSize: 13, color: '#1e293b' };
