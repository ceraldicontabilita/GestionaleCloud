import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../api';
import { formatEuro } from '../lib/utils';
import DocumentViewerModal from './DocumentViewerModal';

/**
 * Interroga avviso bonario (PR 11 dell'audit del commercialista).
 *
 * Il commercialista inserisce le righe dell'avviso (codice tributo, periodo,
 * importo) e ottiene, riga per riga, il controllo incrociato con: righe F24
 * dei modelli in archivio, quietanze, addebiti bancari I24 e ritenute dei
 * cedolini HR. Sola lettura: POST /api/f24/avviso-bonario/controllo.
 * Palette salvia/sabbia (niente blu); date gg/mm/aaaa gia' formattate dal
 * backend (`*_it`).
 */
const PALETTE = {
  salvia: '#5b7a6b',
  salviaScura: '#3f5a4e',
  crema: '#faf7f0',
  card: '#fffefb',
  bordo: '#e6e0d4',
  inchiostro: '#2a3329',
  sabbia: '#8a6f47',
  sabbiaScura: '#6f583a',
  terracotta: '#d35f4e',
  ocra: '#c4894a',
  bosco: '#3d8168',
  grigio: '#6b7268',
};

export const ESITI_AVVISO = {
  COPERTO: { label: 'Coperto', bg: '#e3efe8', color: PALETTE.bosco, spiegazione: 'F24 pagato con quietanza o addebito bancario' },
  PAGATO_SENZA_QUIETANZA: { label: 'Pagato senza quietanza', bg: '#fbf1e3', color: PALETTE.sabbiaScura, spiegazione: 'Addebito bancario presente, quietanza assente' },
  DA_PAGARE: { label: 'Da pagare', bg: '#fdf3e7', color: PALETTE.ocra, spiegazione: 'Modello presente, nessuna prova di pagamento' },
  NON_TROVATO: { label: 'Non trovato', bg: '#f7e4e0', color: PALETTE.terracotta, spiegazione: 'Nessuna riga F24 per tributo e periodo' },
  IMPORTO_DIVERSO: { label: 'Importo diverso', bg: '#f7e4e0', color: PALETTE.terracotta, spiegazione: 'Riga trovata ma con importo differente' },
};

const rigaVuota = () => ({ codice_tributo: '', periodo: '', importo: '', anno_imposta: '' });

const stileInput = {
  minHeight: 38, padding: '6px 10px', border: `1px solid ${PALETTE.bordo}`, borderRadius: 6,
  background: PALETTE.card, color: PALETTE.inchiostro, fontSize: 13,
};
const stileTh = {
  padding: '8px', textAlign: 'left', fontWeight: 600, fontSize: 11, color: PALETTE.grigio,
  textTransform: 'uppercase', whiteSpace: 'nowrap', borderBottom: `2px solid ${PALETTE.bordo}`,
};
const stileTd = { padding: '8px', fontSize: 12.5, verticalAlign: 'top', borderBottom: `1px solid ${PALETTE.bordo}` };
const stileBottone = (primario = true) => ({
  padding: '8px 14px', minHeight: 38, borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 12.5,
  background: primario ? PALETTE.salvia : PALETTE.card,
  color: primario ? 'white' : PALETTE.salviaScura,
  border: primario ? 'none' : `1px solid ${PALETTE.salvia}`,
});

function BadgeEsito({ esito }) {
  const stile = ESITI_AVVISO[esito] || { label: esito, bg: PALETTE.crema, color: PALETTE.grigio };
  return (
    <span title={stile.spiegazione} style={{ padding: '3px 8px', borderRadius: 6, fontSize: 11, fontWeight: 700, background: stile.bg, color: stile.color, whiteSpace: 'nowrap' }}>
      {stile.label}
    </span>
  );
}

function ListaProve({ riga, onApriPdf }) {
  const modelli = riga.righe_f24 || [];
  const quietanze = riga.quietanze || [];
  const addebiti = riga.addebiti_banca || [];
  const ced = riga.cedolini_hr;
  return (
    <div style={{ display: 'grid', gap: 6 }}>
      {modelli.length === 0 && <span style={{ color: PALETTE.grigio }}>Nessun modello F24</span>}
      {modelli.map((m) => (
        <div key={m.f24_id} data-testid={`avviso-f24-${m.f24_id}`}>
          <strong>F24</strong> del {m.data_versamento_it || '—'} · saldo {formatEuro(m.saldo_modello)} · riga {formatEuro(m.importo_righe)}
          {' · '}
          <button type="button" onClick={() => onApriPdf(m)} style={{ ...stileBottone(false), padding: '2px 8px', minHeight: 26, fontSize: 11 }}>
            Apri PDF
          </button>
          <div style={{ fontSize: 11, color: PALETTE.grigio }}>{m.file_name} · stato {m.stato_evidenza}</div>
        </div>
      ))}
      {quietanze.map((q) => (
        <div key={`${q.fonte}-${q.quietanza_id}`} data-testid={`avviso-quietanza-${q.quietanza_id}`}>
          <strong>Quietanza</strong> {q.data_it || '—'} · prot. {q.protocollo || '—'}
          {q.importo != null && <> · {formatEuro(q.importo)}</>}
          {' '}<span style={{ fontSize: 11, color: q.agganciata ? PALETTE.bosco : PALETTE.ocra }}>{q.agganciata ? 'agganciata' : 'compatibile, non agganciata'}</span>
          <div style={{ fontSize: 11, color: PALETTE.grigio }}>{q.filename}</div>
        </div>
      ))}
      {addebiti.map((a) => (
        <div key={a.movimento_id} data-testid={`avviso-banca-${a.movimento_id}`}>
          <strong>Banca</strong> {a.data_it || '—'} · {formatEuro(a.importo)}
          {' '}<span style={{ fontSize: 11, color: a.agganciato ? PALETTE.bosco : PALETTE.ocra }}>{a.agganciato ? 'agganciato' : 'compatibile, non agganciato'}</span>
          {' · '}<Link to={a.link} style={{ color: PALETTE.salviaScura }}>apri movimento</Link>
          <div style={{ fontSize: 11, color: PALETTE.grigio }}>{a.descrizione}</div>
        </div>
      ))}
      {ced && (
        <div data-testid="avviso-cedolini-hr">
          <strong>Cedolini HR</strong> {ced.periodo}: {ced.n_cedolini} buste
          {ced.totale != null
            ? <> · {ced.natura} {formatEuro(ced.totale)} (campo {ced.campo_usato}) · differenza {formatEuro(ced.differenza_vs_avviso)}</>
            : <> · trattenute totali {formatEuro(ced.trattenute_totali)}</>}
          {!ced.attendibile && (
            <div style={{ fontSize: 11, color: PALETTE.terracotta }}>
              Confronto non attendibile: {ced.motivo || ced.errore || 'dati non disponibili'}
            </div>
          )}
          {' '}<a href={ced.link || '/hr/'} style={{ color: PALETTE.salviaScura, fontSize: 11 }}>apri HR</a>
        </div>
      )}
    </div>
  );
}

export default function AvvisoBonarioF24() {
  const [righe, setRighe] = useState([rigaVuota()]);
  const [numeroAvviso, setNumeroAvviso] = useState('');
  const [dataAvviso, setDataAvviso] = useState('');
  const [esito, setEsito] = useState(null);
  const [errore, setErrore] = useState(null);
  const [loading, setLoading] = useState(false);
  const [pdfViewer, setPdfViewer] = useState(null);

  const aggiornaRiga = (indice, campo, valore) => {
    setRighe((prev) => prev.map((r, i) => (i === indice ? { ...r, [campo]: valore } : r)));
  };

  const interroga = async (evento) => {
    evento?.preventDefault?.();
    setErrore(null);
    const valide = righe.filter((r) => r.codice_tributo.trim() && r.periodo.trim() && r.importo !== '');
    if (valide.length === 0) {
      setErrore('Inserisci almeno una riga con codice tributo, periodo e importo.');
      return;
    }
    setLoading(true);
    try {
      const res = await api.post('/api/f24/avviso-bonario/controllo', {
        righe: valide.map((r) => ({
          codice_tributo: r.codice_tributo.trim(),
          periodo: r.periodo.trim(),
          importo: parseFloat(String(r.importo).replace(',', '.')),
          anno_imposta: r.anno_imposta ? parseInt(r.anno_imposta, 10) : null,
        })),
        numero_avviso: numeroAvviso || null,
        data_avviso: dataAvviso || null,
        includi_cedolini_hr: true,
      });
      setEsito(res.data);
    } catch (e) {
      setEsito(null);
      setErrore(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  const riepilogo = esito?.riepilogo;

  return (
    <section
      data-testid="avviso-bonario-f24"
      style={{ padding: 16, borderBottom: `1px solid ${PALETTE.bordo}`, background: PALETTE.crema }}
      aria-labelledby="avviso-bonario-titolo"
    >
      <h3 id="avviso-bonario-titolo" style={{ margin: '0 0 4px', fontSize: 15, color: PALETTE.salviaScura }}>
        Interroga avviso bonario
      </h3>
      <p style={{ margin: '0 0 12px', fontSize: 12.5, color: PALETTE.grigio }}>
        Inserisci le righe dell'avviso (codice tributo, periodo MM/AAAA o AAAA, importo): per ogni riga il
        gestionale cerca la riga F24, la quietanza, l'addebito bancario e le ritenute dei cedolini HR.
        Nessun dato viene modificato.
      </p>

      <form onSubmit={interroga} style={{ display: 'grid', gap: 8 }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <input aria-label="Numero avviso" placeholder="Numero avviso (facoltativo)" value={numeroAvviso} onChange={(e) => setNumeroAvviso(e.target.value)} style={{ ...stileInput, minWidth: 220 }} />
          <input aria-label="Data avviso" type="date" value={dataAvviso} onChange={(e) => setDataAvviso(e.target.value)} style={stileInput} />
        </div>
        {righe.map((r, i) => (
          <div key={i} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }} data-testid={`avviso-riga-${i}`}>
            <input aria-label={`Codice tributo riga ${i + 1}`} placeholder="Codice tributo (es. 1001)" value={r.codice_tributo} onChange={(e) => aggiornaRiga(i, 'codice_tributo', e.target.value)} style={{ ...stileInput, width: 170 }} />
            <input aria-label={`Periodo riga ${i + 1}`} placeholder="Periodo (es. 10/2019)" value={r.periodo} onChange={(e) => aggiornaRiga(i, 'periodo', e.target.value)} style={{ ...stileInput, width: 150 }} />
            <input aria-label={`Importo riga ${i + 1}`} placeholder="Importo €" inputMode="decimal" value={r.importo} onChange={(e) => aggiornaRiga(i, 'importo', e.target.value)} style={{ ...stileInput, width: 130 }} />
            <input aria-label={`Anno imposta riga ${i + 1}`} placeholder="Anno imposta" inputMode="numeric" value={r.anno_imposta} onChange={(e) => aggiornaRiga(i, 'anno_imposta', e.target.value)} style={{ ...stileInput, width: 120 }} />
            {righe.length > 1 && (
              <button type="button" aria-label={`Rimuovi riga ${i + 1}`} onClick={() => setRighe((prev) => prev.filter((_, j) => j !== i))} style={stileBottone(false)}>
                Rimuovi
              </button>
            )}
          </div>
        ))}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button type="button" onClick={() => setRighe((prev) => [...prev, rigaVuota()])} style={stileBottone(false)}>
            + Aggiungi riga
          </button>
          <button type="submit" data-testid="btn-interroga-avviso" disabled={loading} style={{ ...stileBottone(true), cursor: loading ? 'wait' : 'pointer' }}>
            {loading ? 'Controllo in corso…' : 'Interroga avviso'}
          </button>
        </div>
      </form>

      {errore && (
        <div role="alert" style={{ marginTop: 10, fontSize: 13, color: PALETTE.terracotta, fontWeight: 600 }}>
          {errore}
        </div>
      )}

      {riepilogo && (
        <div data-testid="avviso-riepilogo" style={{ marginTop: 14, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <div style={{ padding: '8px 12px', background: PALETTE.card, border: `1px solid ${PALETTE.bordo}`, borderRadius: 8 }}>
            <div style={{ fontSize: 11, color: PALETTE.grigio }}>Totale avviso</div>
            <strong>{formatEuro(riepilogo.totale_avviso)}</strong>
          </div>
          <div style={{ padding: '8px 12px', background: PALETTE.card, border: `1px solid ${PALETTE.bordo}`, borderRadius: 8 }}>
            <div style={{ fontSize: 11, color: PALETTE.grigio }}>Coperto</div>
            <strong style={{ color: PALETTE.bosco }}>{formatEuro(riepilogo.totale_coperto)}</strong>
          </div>
          <div style={{ padding: '8px 12px', background: PALETTE.card, border: `1px solid ${PALETTE.bordo}`, borderRadius: 8 }}>
            <div style={{ fontSize: 11, color: PALETTE.grigio }}>Pagato senza quietanza</div>
            <strong style={{ color: PALETTE.sabbiaScura }}>{formatEuro(riepilogo.totale_pagato_senza_quietanza)}</strong>
          </div>
          <div style={{ padding: '8px 12px', background: PALETTE.card, border: `1px solid ${PALETTE.bordo}`, borderRadius: 8 }}>
            <div style={{ fontSize: 11, color: PALETTE.grigio }}>Scoperto</div>
            <strong style={{ color: PALETTE.terracotta }}>{formatEuro(riepilogo.totale_scoperto)}</strong>
          </div>
          {esito.fonti && (
            <div style={{ alignSelf: 'center', fontSize: 11, color: PALETTE.grigio }}>
              Archivio letto: {esito.fonti.f24} F24 · {esito.fonti.quietanze} quietanze · {esito.fonti.movimenti_f24_banca} addebiti banca
            </div>
          )}
        </div>
      )}

      {esito?.righe?.length > 0 && (
        <div style={{ overflowX: 'auto', marginTop: 12 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900, background: PALETTE.card }} data-testid="avviso-tabella-esiti">
            <thead>
              <tr>
                <th style={stileTh}>Tributo</th>
                <th style={stileTh}>Periodo</th>
                <th style={{ ...stileTh, textAlign: 'right' }}>Importo avviso</th>
                <th style={stileTh}>Esito</th>
                <th style={{ ...stileTh, textAlign: 'right' }}>Differenza</th>
                <th style={stileTh}>Contropartite (F24 · quietanza · banca · cedolini)</th>
                <th style={stileTh}>Motivazione</th>
              </tr>
            </thead>
            <tbody>
              {esito.righe.map((r, idx) => (
                <tr key={`${r.codice_tributo}-${r.periodo}-${idx}`} data-testid={`avviso-esito-${r.codice_tributo}-${idx}`}>
                  <td style={{ ...stileTd, fontFamily: 'monospace', fontWeight: 700 }}>
                    {r.codice_tributo}
                    {r.descrizione_tributo && <div style={{ fontSize: 10.5, color: PALETTE.grigio, fontFamily: 'inherit', fontWeight: 400 }}>{r.descrizione_tributo}</div>}
                  </td>
                  <td style={{ ...stileTd, whiteSpace: 'nowrap' }}>{r.periodo}</td>
                  <td style={{ ...stileTd, textAlign: 'right', fontFamily: 'monospace' }}>{formatEuro(r.importo)}</td>
                  <td style={stileTd}><BadgeEsito esito={r.esito} /></td>
                  <td style={{ ...stileTd, textAlign: 'right', fontFamily: 'monospace', color: r.differenza ? PALETTE.terracotta : PALETTE.inchiostro }}>
                    {r.differenza == null ? '—' : formatEuro(r.differenza)}
                  </td>
                  <td style={{ ...stileTd, minWidth: 320 }}>
                    <ListaProve riga={r} onApriPdf={(m) => setPdfViewer({ title: `F24 ${m.file_name || m.f24_id}`, src: m.pdf_url })} />
                  </td>
                  <td style={{ ...stileTd, minWidth: 220, color: PALETTE.grigio }}>{r.motivazione}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pdfViewer && (
        <DocumentViewerModal
          title={pdfViewer.title}
          src={pdfViewer.src}
          documentType="f24"
          onClose={() => setPdfViewer(null)}
        />
      )}
    </section>
  );
}
