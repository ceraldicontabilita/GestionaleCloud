/**
 * Coda operativa dei movimenti bancari realmente privi di documento.
 *
 * Le righe gia' collegate ma con uno stato storico non allineato non vengono
 * contate. I casi con piu' documenti compatibili restano sospesi e mostrano
 * tutti i candidati: nessuna scelta silenziosa sul solo importo.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import api from '../api';
import { useConfirm } from './ui/ConfirmDialog';

const euro = (v) =>
  new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' })
    .format(Number(v || 0));

const dataIt = (v) => String(v || '').slice(0, 10).split('-').reverse().join('/');

export default function InAttesaDocumento({ anno, onRicarica }) {
  const [dati, setDati] = useState(null);
  const [aperto, setAperto] = useState(false);
  const [busy, setBusy] = useState('');
  const [limiteVisibile, setLimiteVisibile] = useState(100);
  const [messaggio, setMessaggio] = useState('');
  const [errore, setErrore] = useState('');
  const codaRef = useRef(null);
  const confirm = useConfirm();

  const carica = useCallback(async () => {
    try {
      const { data } = await api.get(`/api/prima-nota/banca/in-attesa-documento?anno=${anno}`);
      setDati(data);
    } catch {
      setDati(null);
    }
  }, [anno]);

  useEffect(() => {
    setLimiteVisibile(100);
    let vivo = true;
    api.get(`/api/prima-nota/banca/in-attesa-documento?anno=${anno}`)
      .then(({ data }) => { if (vivo) setDati(data); })
      .catch(() => { if (vivo) setDati(null); });
    return () => { vivo = false; };
  }, [anno]);

  const apriCoda = () => {
    setAperto(true);
    setMessaggio('');
    setErrore('');
    setTimeout(() => {
      codaRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
      codaRef.current?.focus?.();
    }, 0);
  };

  const collegaFattura = async (movimento, fattura) => {
    const ok = await confirm({
      title: 'Collega movimento e fattura',
      message: `${dataIt(movimento.data)} - ${euro(movimento.importo)}\n${fattura.fornitore || ''} - fattura ${fattura.numero || ''}`,
      confirmText: 'Collega',
      variant: 'warning',
    });
    if (!ok) return;
    setBusy(`${movimento.id}:${fattura.id}`);
    setErrore('');
    setMessaggio('');
    try {
      await api.post('/api/operazioni-da-confermare/smart/riconcilia-manuale', {
        movimento_id: movimento.id,
        tipo: 'fattura',
        associazioni: [{ id: fattura.id }],
        note: 'Collegamento dalla coda Prima Nota Banca',
      });
      setMessaggio(`Collegata fattura ${fattura.numero || fattura.id} al movimento ${dataIt(movimento.data)}.`);
      await carica();
      await onRicarica?.({ silent: true });
    } catch (e) {
      setErrore(e.response?.data?.detail || e.response?.data?.message || e.message || 'Collegamento non riuscito');
    } finally {
      setBusy('');
    }
  };

  if (!dati) return null;

  const quanti = dati.totale || 0;
  const tuttoAPosto = quanti === 0;

  return (
    <div
      data-testid="banca-in-attesa-documento"
      style={{
        margin: '12px 0', padding: '12px 14px', borderRadius: 10,
        border: `1px solid ${tuttoAPosto ? '#bbf7d0' : '#fde68a'}`,
        background: tuttoAPosto ? '#f0fdf4' : '#fffbeb',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <strong style={{ color: tuttoAPosto ? '#15803d' : '#92400e' }}>
          {tuttoAPosto
            ? 'Nessun movimento presente nella coda documenti da collegare.'
            : `${quanti} movimenti dell'estratto conto aspettano il documento`}
        </strong>
        {!tuttoAPosto && (
          <>
            <span style={{ color: '#92400e', fontSize: 13 }}>
              effetto sul saldo {euro(dati.effetto_sul_saldo)}
            </span>
            <button
              type="button"
              onClick={() => setAperto(v => !v)}
              style={{
                marginLeft: 'auto', padding: '6px 10px', borderRadius: 7,
                border: '1px solid #fcd34d', background: '#fff', color: '#92400e',
                fontSize: 12.5, fontWeight: 700, cursor: 'pointer',
              }}
            >
              {aperto ? 'Nascondi' : 'Vedi quali'}
            </button>
            <button
              type="button"
              onClick={apriCoda}
              style={{
                padding: '6px 10px', borderRadius: 7, border: 0,
                background: '#92400e', color: '#fff', fontSize: 12.5,
                fontWeight: 700, cursor: 'pointer',
              }}
            >
              Agganciali
            </button>
          </>
        )}
      </div>

      {(dati.gia_collegati_da_allineare || 0) > 0 && (
        <p style={{ margin: '7px 0 0', color: '#475569', fontSize: 12.5 }}>
          {dati.gia_collegati_da_allineare} movimenti hanno gia' un documento collegato e non sono conteggiati tra i sospesi.
        </p>
      )}

      {!tuttoAPosto && (
        <p style={{ margin: '8px 0 0', fontSize: 12.5, color: '#78350f' }}>
          Restano qui solo i casi senza identita univoca o con piu' documenti dello stesso importo al centesimo.
        </p>
      )}

      {messaggio && <div role="status" style={{ marginTop: 9, color: '#166534', fontWeight: 700 }}>{messaggio}</div>}
      {errore && <div role="alert" style={{ marginTop: 9, color: '#991b1b', fontWeight: 700 }}>{errore}</div>}

      {aperto && (
        <div ref={codaRef} tabIndex={-1} aria-label="Operazioni da agganciare" style={{ marginTop: 12, outline: 'none' }}>
          {(dati.movimenti || []).slice(0, limiteVisibile).map((m) => (
            <article
              key={m.id}
              style={{
                padding: 11, marginTop: 8, background: '#fff', border: '1px solid #fde68a',
                borderRadius: 9, display: 'grid', gap: 7,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                <span>
                  <b>{dataIt(m.data)}</b> · {m.strumento_bancario?.label || m.categoria || 'Altro'}
                </span>
                <b style={{ color: m.tipo === 'entrata' ? '#15803d' : '#b91c1c' }}>
                  {m.tipo === 'entrata' ? '+' : '-'} {euro(m.importo)}
                </b>
              </div>
              <div style={{ color: '#334155', fontSize: 12.5 }}>
                {m.descrizione_originale || m.descrizione || 'Descrizione non disponibile'}
              </div>
              <div style={{ color: '#92400e', fontSize: 12.5, fontWeight: 700 }}>
                {m.motivo_sospensione}
              </div>
              {(m.candidati || []).map((fattura) => (
                <div
                  key={`${m.id}:${fattura.id}`}
                  style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    gap: 10, flexWrap: 'wrap', padding: '8px 9px', borderRadius: 8,
                    background: '#f8fafc', border: '1px solid #e2e8f0',
                  }}
                >
                  <span style={{ fontSize: 12.5 }}>
                    <b>{fattura.fornitore || 'Fornitore non indicato'}</b>
                    {' '}· fattura {fattura.numero || 'senza numero'}
                    {fattura.data ? ` · ${dataIt(fattura.data)}` : ''}
                    {fattura.importo != null ? ` · ${euro(fattura.importo)}` : ''}
                  </span>
                  <button
                    type="button"
                    onClick={() => collegaFattura(m, fattura)}
                    disabled={Boolean(busy)}
                    style={{
                      padding: '6px 10px', border: 0, borderRadius: 7,
                      background: '#0f2744', color: '#fff', fontWeight: 700,
                      cursor: busy ? 'wait' : 'pointer',
                    }}
                  >
                    {busy === `${m.id}:${fattura.id}` ? 'Collegamento...' : 'Collega questa fattura'}
                  </button>
                </div>
              ))}
            </article>
          ))}
          {(dati.movimenti || []).length > limiteVisibile && (
            <button
              type="button"
              onClick={() => setLimiteVisibile((valore) => valore + 100)}
              style={{
                marginTop: 9, padding: '7px 11px', borderRadius: 7,
                border: '1px solid #fcd34d', background: '#fff', color: '#92400e',
                fontSize: 12.5, fontWeight: 700, cursor: 'pointer',
              }}
            >
              Mostra altri {Math.min(100, (dati.movimenti || []).length - limiteVisibile)} movimenti
            </button>
          )}
        </div>
      )}
    </div>
  );
}
