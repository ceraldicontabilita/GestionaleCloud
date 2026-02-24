import React, { useState, useEffect, useCallback } from 'react';
import api from '../../api';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import { formatEuro, formatDateIT, COLORS } from '../../lib/utils';
import { PageLayout } from '../../components/PageLayout';
import { 
  Wallet, RefreshCw, CheckCircle, Clock, AlertCircle, 
  FileText, Users, Calendar, ChevronDown, ChevronUp 
} from 'lucide-react';

/**
 * PagheHub - Pagina SEMPLIFICATA
 * 
 * Mostra in modo chiaro:
 * 1. Riepilogo Buste Paga (DA_PAGARE / PAGATO)
 * 2. Riepilogo F24 (DA_PAGARE / PAGATO)
 * 
 * I dati vengono importati automaticamente dalla pagina Import Documenti.
 */

const MESI = ['', 'Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic'];

function StatBox({ label, value, sub, color, icon: Icon }) {
  return (
    <div style={{
      background: 'white',
      border: `1px solid ${COLORS.grayLight}`,
      borderRadius: 12,
      padding: '16px 20px',
      flex: '1 1 160px',
      minWidth: 140
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        {Icon && <Icon size={14} color={color || COLORS.gray} />}
        <span style={{ fontSize: 11, color: COLORS.gray, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</span>
      </div>
      <div style={{ fontSize: 24, fontWeight: 800, color: color || COLORS.dark }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: COLORS.gray, marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

function BadgeStato({ stato }) {
  const isOk = stato === 'PAGATO';
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      padding: '4px 12px',
      borderRadius: 20,
      fontSize: 11,
      fontWeight: 700,
      background: isOk ? '#d1fae5' : '#fef3c7',
      color: isOk ? '#065f46' : '#92400e',
      border: `1px solid ${isOk ? '#6ee7b7' : '#fcd34d'}`
    }}>
      {isOk ? <CheckCircle size={12} /> : <Clock size={12} />}
      {stato || 'N/D'}
    </span>
  );
}

// ====== SEZIONE BUSTE PAGA ======
function SezioneBustePaga({ anno }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/paghe/buste-paga', { params: { anno } });
      setData(res.data?.data || []);
    } catch (e) {
      console.error('Errore caricamento buste paga:', e);
    }
    setLoading(false);
  }, [anno]);

  useEffect(() => { load(); }, [load]);

  const totPagato = data.filter(b => b.stato_pagamento === 'PAGATO').reduce((s, b) => s + (b.netto_mese || 0), 0);
  const totDaPagare = data.filter(b => b.stato_pagamento === 'DA_PAGARE').reduce((s, b) => s + (b.netto_mese || 0), 0);

  return (
    <div style={{ background: 'white', borderRadius: 12, border: '1px solid #e5e7eb', overflow: 'hidden' }}>
      <div style={{ padding: 16, borderBottom: '1px solid #e5e7eb', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 36, height: 36, borderRadius: 8, background: '#ede9fe', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Users size={18} color="#7c3aed" />
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15, color: '#374151' }}>Buste Paga</div>
            <div style={{ fontSize: 12, color: '#6b7280' }}>{data.length} dipendenti</div>
          </div>
        </div>
        <button onClick={load} disabled={loading} style={{ padding: '6px 12px', background: '#f3f4f6', border: 'none', borderRadius: 6, cursor: 'pointer' }}>
          <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
        </button>
      </div>

      {/* Stats */}
      <div style={{ padding: 16, display: 'flex', gap: 12, flexWrap: 'wrap', borderBottom: '1px solid #e5e7eb', background: '#fafafa' }}>
        <StatBox label="Da Pagare" value={formatEuro(totDaPagare)} color="#f59e0b" icon={Clock} />
        <StatBox label="Pagati" value={formatEuro(totPagato)} color="#10b981" icon={CheckCircle} />
        <StatBox label="Totale" value={formatEuro(totPagato + totDaPagare)} icon={Wallet} />
      </div>

      {/* Table */}
      {data.length === 0 ? (
        <div style={{ padding: 40, textAlign: 'center', color: '#9ca3af' }}>
          <FileText size={32} style={{ marginBottom: 8, opacity: 0.4 }} />
          <div style={{ fontWeight: 600 }}>Nessuna busta paga</div>
          <div style={{ fontSize: 13, marginTop: 4 }}>Carica un Libro Unico (LUL) dalla pagina Import</div>
        </div>
      ) : (
        <div style={{ maxHeight: 400, overflow: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#f9fafb' }}>
                {['Dipendente', 'Periodo', 'Netto', 'Stato', ''].map(h => (
                  <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: 11, color: '#6b7280', borderBottom: '1px solid #e5e7eb' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((b, i) => (
                <React.Fragment key={i}>
                  <tr 
                    onClick={() => setExpanded(expanded === i ? null : i)}
                    style={{ borderBottom: '1px solid #f3f4f6', cursor: 'pointer', background: expanded === i ? '#f8fafc' : 'white' }}
                  >
                    <td style={{ padding: '12px 14px', fontWeight: 600 }}>{b.dipendente_nome || b.codice_fiscale}</td>
                    <td style={{ padding: '12px 14px', color: '#6b7280' }}>
                      {b.periodo ? `${MESI[parseInt(b.periodo.split('-')[1])]} ${b.periodo.split('-')[0]}` : '—'}
                    </td>
                    <td style={{ padding: '12px 14px', fontWeight: 700 }}>{formatEuro(b.netto_mese)}</td>
                    <td style={{ padding: '12px 14px' }}><BadgeStato stato={b.stato_pagamento} /></td>
                    <td style={{ padding: '12px 14px', width: 30 }}>
                      {expanded === i ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </td>
                  </tr>
                  {expanded === i && (
                    <tr>
                      <td colSpan={5} style={{ padding: '0 14px 14px', background: '#f8fafc' }}>
                        <div style={{ padding: 12, background: 'white', borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12 }}>
                          <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
                            <div><span style={{ color: '#6b7280' }}>CF:</span> <strong>{b.codice_fiscale}</strong></div>
                            {b.data_pagamento && <div><span style={{ color: '#6b7280' }}>Pagato il:</span> <strong>{formatDateIT(b.data_pagamento)}</strong></div>}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ====== SEZIONE F24 ======
function SezioneF24({ anno }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/paghe/distinte-f24', { params: { anno } });
      setData(res.data?.data || []);
    } catch (e) {
      console.error('Errore caricamento F24:', e);
    }
    setLoading(false);
  }, [anno]);

  useEffect(() => { load(); }, [load]);

  const totPagato = data.filter(f => f.stato_pagamento === 'PAGATO').reduce((s, f) => s + (f.totale || 0), 0);
  const totDaPagare = data.filter(f => f.stato_pagamento === 'DA_PAGARE').reduce((s, f) => s + (f.totale || 0), 0);

  return (
    <div style={{ background: 'white', borderRadius: 12, border: '1px solid #e5e7eb', overflow: 'hidden' }}>
      <div style={{ padding: 16, borderBottom: '1px solid #e5e7eb', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 36, height: 36, borderRadius: 8, background: '#fee2e2', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <FileText size={18} color="#dc2626" />
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15, color: '#374151' }}>F24</div>
            <div style={{ fontSize: 12, color: '#6b7280' }}>{data.length} modelli</div>
          </div>
        </div>
        <button onClick={load} disabled={loading} style={{ padding: '6px 12px', background: '#f3f4f6', border: 'none', borderRadius: 6, cursor: 'pointer' }}>
          <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
        </button>
      </div>

      {/* Stats */}
      <div style={{ padding: 16, display: 'flex', gap: 12, flexWrap: 'wrap', borderBottom: '1px solid #e5e7eb', background: '#fafafa' }}>
        <StatBox label="Da Pagare" value={formatEuro(totDaPagare)} color="#f59e0b" icon={Clock} />
        <StatBox label="Pagati" value={formatEuro(totPagato)} color="#10b981" icon={CheckCircle} />
        <StatBox label="Totale" value={formatEuro(totPagato + totDaPagare)} icon={FileText} />
      </div>

      {/* Table */}
      {data.length === 0 ? (
        <div style={{ padding: 40, textAlign: 'center', color: '#9ca3af' }}>
          <FileText size={32} style={{ marginBottom: 8, opacity: 0.4 }} />
          <div style={{ fontWeight: 600 }}>Nessun F24</div>
          <div style={{ fontSize: 13, marginTop: 4 }}>Carica un modello F24 dalla pagina Import</div>
        </div>
      ) : (
        <div style={{ maxHeight: 400, overflow: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#f9fafb' }}>
                {['Periodo', 'Scadenza', 'Totale', 'Stato', ''].map(h => (
                  <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: 11, color: '#6b7280', borderBottom: '1px solid #e5e7eb' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((f, i) => (
                <React.Fragment key={i}>
                  <tr 
                    onClick={() => setExpanded(expanded === i ? null : i)}
                    style={{ borderBottom: '1px solid #f3f4f6', cursor: 'pointer', background: expanded === i ? '#f8fafc' : 'white' }}
                  >
                    <td style={{ padding: '12px 14px', fontWeight: 600 }}>
                      {f.periodo ? `${MESI[parseInt(f.periodo.split('-')[1])]} ${f.periodo.split('-')[0]}` : f.periodo || '—'}
                    </td>
                    <td style={{ padding: '12px 14px', color: '#6b7280' }}>
                      {f.data_scadenza ? formatDateIT(f.data_scadenza) : '—'}
                    </td>
                    <td style={{ padding: '12px 14px', fontWeight: 700 }}>{formatEuro(f.totale)}</td>
                    <td style={{ padding: '12px 14px' }}><BadgeStato stato={f.stato_pagamento} /></td>
                    <td style={{ padding: '12px 14px', width: 30 }}>
                      {expanded === i ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </td>
                  </tr>
                  {expanded === i && f.tributi && f.tributi.length > 0 && (
                    <tr>
                      <td colSpan={5} style={{ padding: '0 14px 14px', background: '#f8fafc' }}>
                        <div style={{ padding: 12, background: 'white', borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12 }}>
                          <div style={{ fontWeight: 600, marginBottom: 8, color: '#374151' }}>Tributi ({f.tributi.length})</div>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                            {f.tributi.slice(0, 10).map((t, ti) => (
                              <span key={ti} style={{ padding: '4px 8px', background: '#fee2e2', borderRadius: 4, fontSize: 11 }}>
                                {t.codice || t.codice_tributo}: {formatEuro(t.importo || t.importo_a_debito)}
                              </span>
                            ))}
                            {f.tributi.length > 10 && (
                              <span style={{ padding: '4px 8px', background: '#f3f4f6', borderRadius: 4, fontSize: 11 }}>
                                +{f.tributi.length - 10} altri
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ====== MAIN COMPONENT ======
export default function PagheHub() {
  const { annoGlobale } = useAnnoGlobale();
  const anno = annoGlobale || new Date().getFullYear();

  return (
    <PageLayout 
      title="Paghe" 
      icon={<Wallet size={22} />}
      description="Riepilogo buste paga e F24 importati"
    >
      <div style={{ maxWidth: 1000, margin: '0 auto' }}>
        
        {/* Info */}
        <div style={{ 
          marginBottom: 20, 
          padding: 14, 
          background: '#eff6ff', 
          borderRadius: 10, 
          border: '1px solid #bfdbfe',
          fontSize: 13,
          color: '#1e40af'
        }}>
          <strong>Come funziona:</strong> Carica i PDF (Libro Unico, F24) dalla pagina <strong>Import Documenti</strong>. 
          Il sistema importa automaticamente i dati e li mostra qui. Al caricamento dell'estratto conto, 
          i pagamenti vengono riconciliati automaticamente.
        </div>

        {/* Sezioni */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          <SezioneBustePaga anno={anno} />
          <SezioneF24 anno={anno} />
        </div>
        
      </div>
    </PageLayout>
  );
}
