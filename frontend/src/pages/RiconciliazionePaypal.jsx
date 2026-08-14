import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';

import api from '../api';
import { PageLayout } from '../components/PageLayout';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { useIsMobile } from '../hooks/useData';

const denaro = (valore, valuta = 'EUR') => {
  const currency = String(valuta || 'EUR').toUpperCase();
  try {
    return new Intl.NumberFormat('it-IT', { style: 'currency', currency })
      .format(Number(valore || 0));
  } catch {
    return `${Number(valore || 0).toFixed(2)} ${currency}`;
  }
};

const dataIT = valore => {
  if (!valore) return '-';
  const data = new Date(valore);
  return Number.isNaN(data.getTime()) ? String(valore) : data.toLocaleDateString('it-IT');
};

const statoFatturaLabel = stato => ({
  associata_validata: 'Associata validata',
  da_rivalidare: 'Da rivalidare',
  non_associata: 'Non associata',
}[stato] || 'Da verificare');

const fonteLabel = fonte => (
  String(fonte.source_type || '').toLowerCase() === 'api'
    ? 'PayPal API'
    : (fonte.nome_file || fonte.tipo_documento || 'Fonte PayPal')
);

const compactId = valore => {
  const text = String(valore || '');
  return text.length > 10 ? `…${text.slice(-8)}` : (text || '-');
};

export default function RiconciliazionePaypal() {
  const { anno } = useAnnoGlobale();
  const isMobile = useIsMobile();
  const location = useLocation();
  const tabIniziale = new URLSearchParams(location.search).get('tab') || 'transazioni';
  const [tab, setTab] = useState(tabIniziale);
  const [loading, setLoading] = useState(true);
  const [errore, setErrore] = useState('');
  const [statoApi, setStatoApi] = useState(null);
  const [dashboard, setDashboard] = useState({});
  const [transazioni, setTransazioni] = useState([]);
  const [movimentiBanca, setMovimentiBanca] = useState([]);
  const [riepilogoBanca, setRiepilogoBanca] = useState({});
  const [fonti, setFonti] = useState([]);
  const transactionIdIniziale = new URLSearchParams(location.search).get('transaction_id') || '';
  const [ricerca, setRicerca] = useState(transactionIdIniziale);
  const [statoCollegamento, setStatoCollegamento] = useState('tutti');
  const [sincronizzazione, setSincronizzazione] = useState('in_attesa');
  const [riprocessamento, setRiprocessamento] = useState('');

  const caricaDati = useCallback(async () => {
    const paramsTx = new URLSearchParams({ limit: '1000', solo_pagamenti: 'true' });
    const paramsBanca = new URLSearchParams({ limit: '5000' });
    if (anno) {
      paramsTx.append('anno', anno);
      paramsBanca.append('anno', anno);
    }

    const risultati = await Promise.allSettled([
      api.get(`/api/paypal-statements/dashboard?anno=${anno}`),
      api.get(`/api/paypal-statements/transactions?${paramsTx}`),
      api.get(`/api/paypal-statements/report?anno=${anno}`),
      api.get(`/api/paypal-statements/statements?anno=${anno}`),
      api.get(`/api/paypal-statements/bank-movements?${paramsBanca}`),
      api.get('/api/paypal-api/status'),
    ]);

    const valore = (indice, fallback = {}) => (
      risultati[indice].status === 'fulfilled' ? (risultati[indice].value.data || fallback) : fallback
    );
    const datiDashboard = valore(0);
    const datiTransazioni = valore(1);
    const datiFonti = valore(3);
    const datiBanca = valore(4);

    setDashboard(datiDashboard);
    setTransazioni(Array.isArray(datiTransazioni.transactions) ? datiTransazioni.transactions : []);
    setFonti(Array.isArray(datiFonti.fonti) ? datiFonti.fonti : (Array.isArray(datiFonti.statements) ? datiFonti.statements : []));
    setMovimentiBanca(Array.isArray(datiBanca.movimenti) ? datiBanca.movimenti : []);
    setRiepilogoBanca(datiBanca);
    setStatoApi(valore(5, null));
    setErrore(risultati.some(risultato => risultato.status === 'rejected')
      ? 'Alcuni dati PayPal non sono stati caricati. Riprova senza considerare certi i valori mancanti.'
      : '');
  }, [anno]);

  useEffect(() => {
    let attivo = true;
    setLoading(true);
    const avvia = async () => {
      const status = await api.get('/api/paypal-api/status');
      if (status.data?.api_configurata) {
        setSincronizzazione('in_corso');
        await api.post('/api/paypal-api/sync/incremental');
        setSincronizzazione('completata');
      } else {
        setSincronizzazione('non_configurata');
      }
      // Applica sempre il motore end-to-end anche allo storico gia' presente:
      // la sincronizzazione API da sola non associa fattura e prova bancaria.
      const riprocessato = await api.post(`/api/paypal-statements/riprocessa?anno=${anno}`);
      const dopo = riprocessato.data?.collegamenti_dopo || {};
      setRiprocessamento(`Associate ${dopo.associate || 0} · finalizzate ${dopo.finalizzate || 0} · ambigue ${dopo.ambigue || 0}`);
      await caricaDati();
    };
    avvia()
      .catch(() => {
        if (attivo) {
          setSincronizzazione('errore');
          setErrore('Sincronizzazione PayPal non completata. I dati mostrati possono non essere aggiornati.');
          caricaDati().catch(() => {});
        }
      })
      .finally(() => { if (attivo) setLoading(false); });
    return () => { attivo = false; };
  }, [caricaDati]);

  const riprocessaStorico = async () => {
    setLoading(true);
    setRiprocessamento('Riprocessamento in corso…');
    try {
      const risposta = await api.post(`/api/paypal-statements/riprocessa?anno=${anno}`);
      const dopo = risposta.data?.collegamenti_dopo || {};
      setRiprocessamento(`Associate ${dopo.associate || 0} · finalizzate ${dopo.finalizzate || 0} · ambigue ${dopo.ambigue || 0}`);
      await caricaDati();
    } catch (e) {
      setRiprocessamento('Riprocessamento non riuscito');
      setErrore(e.response?.data?.detail || 'Riprocessamento PayPal non riuscito.');
    } finally {
      setLoading(false);
    }
  };

  const transazioniConBanca = useMemo(() => {
    const perId = new Map();
    movimentiBanca.forEach(movimento => {
      const id = String(movimento.paypal_transaction_id || '');
      if (id) perId.set(id, movimento);
    });
    return transazioni.map(tx => ({
      ...tx,
      bank_movement: perId.get(String(tx.transaction_id || tx.id || '')) || null,
    }));
  }, [transazioni, movimentiBanca]);

  const righe = useMemo(() => {
    const termine = ricerca.trim().toLowerCase();
    return transazioniConBanca.filter(tx => {
      const compatibileTesto = !termine || `${tx.transaction_id || tx.id || ''} ${tx.nome_controparte || ''} ${tx.descrizione || ''} ${tx.email_controparte || ''}`
        .toLowerCase().includes(termine);
      const compatibileStato = statoCollegamento === 'tutti' || tx.stato_collegamento_fattura === statoCollegamento;
      return compatibileTesto && compatibileStato;
    });
  }, [transazioniConBanca, ricerca, statoCollegamento]);

  const riconciliati = Number(riepilogoBanca.riconciliati ?? movimentiBanca.filter(m => m.riconciliato_paypal).length);
  const daVerificare = Number(riepilogoBanca.da_associare ?? Math.max(0, movimentiBanca.length - riconciliati));

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
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <span data-testid="paypal-sync-status" style={{ color: '#475569', fontSize: 13 }}>
            {sincronizzazione === 'in_corso' ? 'Sincronizzazione incrementale…' :
              sincronizzazione === 'completata' ? `Aggiornato${statoApi?.ultimo_sync ? ` alle ${new Date(statoApi.ultimo_sync).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })}` : ''}` :
                sincronizzazione === 'non_configurata' ? 'API non configurata' :
                  sincronizzazione === 'errore' ? 'Sincronizzazione da verificare' : 'Verifica aggiornamenti…'}
          </span>
          <button type="button" onClick={riprocessaStorico} disabled={loading} style={buttonStyle}>
            Riprocessa {anno}
          </button>
          </div>
        </div>

        {riprocessamento && <div data-testid="paypal-reprocess-result" style={{ ...messageStyle, background: '#ecfdf5', color: '#166534' }}>{riprocessamento}</div>}

        {loading && <div role="status" style={messageStyle}>Caricamento dati PayPal...</div>}
        {errore && <div role="alert" style={{ ...messageStyle, background: '#fef2f2', color: '#991b1b' }}>{errore}</div>}
        {statoApi && !statoApi.api_configurata && (
          <div style={{ ...messageStyle, background: '#eff6ff', color: '#1d4ed8' }}>
            API PayPal non configurata. Le transazioni già presenti restano consultabili e riconciliabili.
          </div>
        )}

        <section style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(150px, 1fr))', gap: 10, marginBottom: 16 }}>
          <div style={card}><small>Transazioni</small><strong style={value}>{dashboard.total_transactions ?? transazioni.length}</strong></div>
          <div style={card}><small>Movimenti banca</small><strong style={value}>{dashboard.movimenti_banca_paypal ?? movimentiBanca.length}</strong></div>
          <div style={card}><small>Riconciliati</small><strong style={value}>{riconciliati}</strong></div>
          <div style={card}><small>Da verificare</small><strong style={value}>{daVerificare}</strong></div>
        </section>

        <section data-testid="paypal-relation-flow" aria-label="Stato collegamenti PayPal" style={{ ...card, gridTemplateColumns: 'repeat(5, minmax(120px, 1fr))', marginBottom: 16, overflowX: 'auto' }}>
          {[
            ['Transazioni', transazioni.length],
            ['Controparte identificata', transazioni.filter(tx => tx.nome_controparte).length],
            ['Fattura validata', transazioni.filter(tx => tx.stato_collegamento_fattura === 'associata_validata').length],
            ['Banca verificata', riconciliati],
            ['Eccezioni', transazioni.filter(tx => tx.stato_collegamento_fattura !== 'associata_validata').length + daVerificare],
          ].map(([label, count], index) => (
            <div key={label} style={{ minWidth: 120 }}>
              <small>{index ? '→ ' : ''}{label}</small>
              <strong style={value}>{count}</strong>
            </div>
          ))}
        </section>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
          {[
            ['transazioni', 'Transazioni'],
            ['estratti', 'Movimenti banca'],
            ['documenti', 'Fonti'],
          ].map(([id, label]) => (
            <button key={id} type="button" onClick={() => setTab(id)} style={{ ...buttonStyle, background: tab === id ? '#0f2744' : '#fff', color: tab === id ? '#fff' : '#0f2744' }}>{label}</button>
          ))}
        </div>

        {!loading && tab === 'transazioni' && (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(240px, 1fr) minmax(190px, 260px)', gap: 10, marginBottom: 12 }}>
              <input value={ricerca} onChange={e => setRicerca(e.target.value)} placeholder="Cerca ID, controparte, descrizione o email" style={inputStyle} />
              <select aria-label="Stato collegamento fattura" value={statoCollegamento} onChange={e => setStatoCollegamento(e.target.value)} style={inputStyle}>
                <option value="tutti">Tutti gli stati</option>
                <option value="associata_validata">Associata validata</option>
                <option value="da_rivalidare">Da rivalidare</option>
                <option value="non_associata">Non associata</option>
              </select>
            </div>
            {isMobile ? <TransactionCards righe={righe} /> : <TransactionTable righe={righe} />}
          </>
        )}

        {!loading && tab === 'estratti' && (
          <>
            <p style={{ color: '#64748b' }}>Fonti duplicate unificate: <strong>{riepilogoBanca.duplicati_unificati || 0}</strong></p>
            {isMobile ? <BankCards righe={movimentiBanca} /> : <BankTable righe={movimentiBanca} />}
          </>
        )}

        {!loading && tab === 'documenti' && (
          isMobile ? <SourceCards fonti={fonti} /> : <SourceTable fonti={fonti} />
        )}
      </main>
    </PageLayout>
  );
}

function TransactionId({ value: id }) {
  if (!id) return <span>-</span>;
  return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><code title={id}>{compactId(id)}</code><button type="button" aria-label={`Copia ID transazione ${id}`} title="Copia ID" onClick={() => navigator.clipboard?.writeText(String(id))} style={copyButton}>Copia</button></span>;
}

function TransactionAmount({ tx }) {
  const gross = denaro(tx.gross_amount ?? tx.importo ?? tx.lordo, tx.gross_currency || tx.currency);
  if (tx.settlement_amount != null && tx.settlement_currency) {
    return <span>{gross} → {denaro(tx.settlement_amount, tx.settlement_currency)}</span>;
  }
  return <span>{gross}</span>;
}

function TransactionCards({ righe }) {
  return <div data-testid="paypal-transaction-cards" style={cards}>{righe.map(tx => <article key={tx.transaction_id || tx.id} style={card}><strong>{tx.descrizione || '-'}</strong><TransactionId value={tx.transaction_id || tx.id} /><span>{tx.nome_controparte || '-'}</span><span>{dataIT(tx.data || tx.date)} - <TransactionAmount tx={tx} /></span><span>{statoFatturaLabel(tx.stato_collegamento_fattura)}</span>{tx.bank_movement ? <a href={`/prima-nota?section=banca&selected=${encodeURIComponent(tx.bank_movement.id)}`}>Vedi prova bancaria {compactId(tx.bank_movement.id)}</a> : <span>Banca da verificare</span>}</article>)}</div>;
}

function TransactionTable({ righe }) {
  return <div data-testid="paypal-transactions-table" style={tableWrap}><table style={table}><thead><tr>{['Data', 'ID', 'Controparte', 'Descrizione', 'Importo/valuta', 'Fattura', 'Banca', 'Stato'].map(t => <th key={t} style={th}>{t}</th>)}</tr></thead><tbody>{righe.map(tx => <tr key={tx.transaction_id || tx.id}><td style={td}>{dataIT(tx.data || tx.date)}</td><td style={td}><TransactionId value={tx.transaction_id || tx.id} /></td><td style={td}>{tx.nome_controparte || '-'}</td><td style={td}>{tx.descrizione || '-'}</td><td style={td}><TransactionAmount tx={tx} /></td><td style={td}>{tx.fattura_associata?.numero || tx.fattura_numero || '-'}</td><td style={td}>{tx.bank_movement ? <a href={`/prima-nota?section=banca&selected=${encodeURIComponent(tx.bank_movement.id)}`}>Prova {compactId(tx.bank_movement.id)}</a> : 'Da verificare'}</td><td style={td}>{statoFatturaLabel(tx.stato_collegamento_fattura)}</td></tr>)}</tbody></table></div>;
}

function BankCards({ righe }) {
  return <div data-testid="paypal-bank-cards" style={cards}>{righe.map(riga => <article key={riga.id} style={card}><strong>{riga.descrizione || '-'}</strong><span>{dataIT(riga.data)} - {denaro(riga.importo, riga.valuta || 'EUR')}</span><span>{riga.riconciliato_paypal ? 'Riconciliato' : 'Da associare'}</span>{riga.paypal_transaction_id && <a href={`/riconciliazione/paypal?tab=transazioni&transaction_id=${encodeURIComponent(riga.paypal_transaction_id)}`}>Apri transazione {compactId(riga.paypal_transaction_id)}</a>}</article>)}</div>;
}

function BankTable({ righe }) {
  return <div data-testid="paypal-bank-table" style={tableWrap}><table style={table}><thead><tr>{['Data', 'Descrizione', 'Importo', 'Transazione', 'Stato'].map(t => <th key={t} style={th}>{t}</th>)}</tr></thead><tbody>{righe.map(riga => <tr key={riga.id}><td style={td}>{dataIT(riga.data)}</td><td style={td}>{riga.descrizione || '-'}</td><td style={td}>{denaro(riga.importo, riga.valuta || 'EUR')}</td><td style={td}>{riga.paypal_transaction_id ? <a href={`/riconciliazione/paypal?tab=transazioni&transaction_id=${encodeURIComponent(riga.paypal_transaction_id)}`}>{compactId(riga.paypal_transaction_id)}</a> : '-'}</td><td style={td}>{riga.riconciliato_paypal ? 'Riconciliato' : 'Da associare'}</td></tr>)}</tbody></table></div>;
}

function SourceDetails({ fonte }) {
  return <><strong>{fonteLabel(fonte)}</strong><span>{fonte.periodo_inizio || '-'} - {fonte.periodo_fine || '-'}</span><span>{fonte.totale_transazioni || 0} transazioni</span><span>{fonte.totale_pagamenti || 0} pagamenti</span>{fonte.documento_presente === false && <span>Nessun file: fonte API</span>}</>;
}

function SourceCards({ fonti }) {
  return <div data-testid="paypal-source-cards" style={cards}>{fonti.map(fonte => <article key={fonte.id} style={card}><SourceDetails fonte={fonte} /></article>)}</div>;
}

function SourceTable({ fonti }) {
  return <div data-testid="paypal-source-table" style={tableWrap}><table style={table}><thead><tr>{['Fonte', 'Periodo', 'Transazioni', 'Pagamenti', 'Documento'].map(t => <th key={t} style={th}>{t}</th>)}</tr></thead><tbody>{fonti.map(fonte => <tr key={fonte.id}><td style={td}>{fonteLabel(fonte)}</td><td style={td}>{fonte.periodo_inizio || '-'} - {fonte.periodo_fine || '-'}</td><td style={td}>{fonte.totale_transazioni || 0}</td><td style={td}>{fonte.totale_pagamenti || 0}</td><td style={td}>{fonte.documento_presente === false ? 'Nessun file: fonte API' : 'Documento acquisito'}</td></tr>)}</tbody></table></div>;
}

const card = { background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, padding: 14, display: 'grid', gap: 6 };
const cards = { display: 'grid', gap: 10 };
const value = { display: 'block', marginTop: 6, fontSize: 24, color: '#0f2744' };
const buttonStyle = { minHeight: 40, padding: '8px 14px', borderRadius: 8, border: '1px solid #cbd5e1', background: '#fff', cursor: 'pointer', fontWeight: 700 };
const inputStyle = { width: '100%', minHeight: 40, padding: '8px 10px', border: '1px solid #cbd5e1', borderRadius: 8 };
const messageStyle = { padding: 12, color: '#64748b', borderRadius: 8, marginBottom: 12 };
const tableWrap = { overflowX: 'auto', background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10 };
const table = { width: '100%', borderCollapse: 'collapse', minWidth: 760 };
const th = { padding: '10px 12px', textAlign: 'left', fontSize: 12, color: '#475569', background: '#f8fafc' };
const td = { padding: '10px 12px', fontSize: 13, color: '#1e293b', borderTop: '1px solid #e2e8f0' };
const copyButton = { minHeight: 28, padding: '2px 6px', border: '1px solid #cbd5e1', borderRadius: 5, background: '#fff', cursor: 'pointer', fontSize: 11 };
