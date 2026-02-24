import React, { useState, useEffect, useMemo } from 'react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro } from '../lib/utils';
import { PageLayout, PageSection, PageGrid, PageLoading } from '../components/PageLayout';
import { 
  Users, Building2, Search, Download, ChevronDown, ChevronRight,
  FileText, CreditCard, AlertCircle, CheckCircle, ArrowUpDown, Eye
} from 'lucide-react';

const NOMI_MESI = ['', 'Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic'];

export default function PartitarioCliFor() {
  const { anno } = useAnnoGlobale();
  const [activeTab, setActiveTab] = useState('fornitori');
  const [fornitori, setFornitori] = useState(null);
  const [clienti, setClienti] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filtroStato, setFiltroStato] = useState('tutti');
  const [expandedForn, setExpandedForn] = useState(new Set());
  const [sortField, setSortField] = useState('fornitore');
  const [sortDir, setSortDir] = useState('asc');

  useEffect(() => { loadData(); }, [anno]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [fornRes, cliRes] = await Promise.all([
        api.get(`/api/contabilita-gestionale/partitario/fornitori?anno=${anno}`),
        api.get(`/api/contabilita-gestionale/partitario/clienti?anno=${anno}`)
      ]);
      setFornitori(fornRes.data);
      setClienti(cliRes.data);
    } catch (err) {
      console.error('Errore partitario:', err);
    } finally {
      setLoading(false);
    }
  };

  // --- FORNITORI ---
  const fornitoriFiltered = useMemo(() => {
    if (!fornitori?.fornitori) return [];
    let list = [...fornitori.fornitori];
    
    // Filtro ricerca
    if (search) {
      const s = search.toLowerCase();
      list = list.filter(f => f.fornitore.toLowerCase().includes(s) || f.partita_iva.includes(s));
    }
    
    // Filtro stato
    if (filtroStato === 'aperto') list = list.filter(f => f.stato === 'aperto');
    else if (filtroStato === 'saldato') list = list.filter(f => f.stato === 'saldato');
    else if (filtroStato === 'credito') list = list.filter(f => f.stato === 'a_credito');
    
    // Ordinamento
    list.sort((a, b) => {
      let va, vb;
      if (sortField === 'fornitore') { va = a.fornitore; vb = b.fornitore; }
      else if (sortField === 'saldo') { va = a.saldo; vb = b.saldo; }
      else if (sortField === 'dare') { va = a.totale_dare; vb = b.totale_dare; }
      else if (sortField === 'avere') { va = a.totale_avere; vb = b.totale_avere; }
      else if (sortField === 'n_doc') { va = a.n_documenti; vb = b.n_documenti; }
      else { va = a.fornitore; vb = b.fornitore; }
      
      if (typeof va === 'string') return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
      return sortDir === 'asc' ? va - vb : vb - va;
    });
    
    return list;
  }, [fornitori, search, filtroStato, sortField, sortDir]);

  const handleSort = (field) => {
    if (sortField === field) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortField(field); setSortDir('asc'); }
  };

  const toggleForn = (piva) => {
    setExpandedForn(prev => {
      const next = new Set(prev);
      next.has(piva) ? next.delete(piva) : next.add(piva);
      return next;
    });
  };

  const getStatoBadge = (stato) => {
    const map = {
      aperto: { bg: '#fef3c7', color: '#b45309', label: 'Aperto' },
      saldato: { bg: '#dcfce7', color: '#16a34a', label: 'Saldato' },
      a_credito: { bg: '#dbeafe', color: '#1535a8', label: 'A credito' }
    };
    const s = map[stato] || { bg: '#f1f5f9', color: '#64748b', label: stato };
    return (
      <span style={{ padding: '2px 10px', borderRadius: 10, fontSize: 11, fontWeight: 600, background: s.bg, color: s.color }}>
        {s.label}
      </span>
    );
  };

  const exportCSV = () => {
    if (!fornitoriFiltered.length) return;
    const rows = [['Fornitore', 'P.IVA', 'Dare', 'Avere', 'Saldo', 'Stato', 'N.Doc'].join(';')];
    for (const f of fornitoriFiltered) {
      rows.push([`"${f.fornitore}"`, f.partita_iva, f.totale_dare.toFixed(2), f.totale_avere.toFixed(2), f.saldo.toFixed(2), f.stato, f.n_documenti].join(';'));
    }
    const blob = new Blob(['\uFEFF' + rows.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `partitario-fornitori-${anno}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const SortHeader = ({ field, children, align = 'left' }) => (
    <th onClick={() => handleSort(field)}
      style={{ padding: '12px 8px', textAlign: align, cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        {children}
        {sortField === field && <ArrowUpDown size={12} style={{ opacity: 0.7 }} />}
      </span>
    </th>
  );

  // --- TAB FORNITORI ---
  const FornitoriView = () => (
    <>
      {/* Summary */}
      {fornitori?.totali && (
        <PageGrid cols={4} gap={16}>
          <div style={{ background: '#f0fdf4', padding: 16, borderRadius: 12, textAlign: 'center' }}>
            <div style={{ fontSize: 12, color: '#059669', fontWeight: 600 }}>TOTALE DARE (Fatture)</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#059669', marginTop: 4 }}>{formatEuro(fornitori.totali.totale_dare)}</div>
          </div>
          <div style={{ background: '#fef2f2', padding: 16, borderRadius: 12, textAlign: 'center' }}>
            <div style={{ fontSize: 12, color: '#dc2626', fontWeight: 600 }}>TOTALE AVERE (Pagamenti)</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#dc2626', marginTop: 4 }}>{formatEuro(fornitori.totali.totale_avere)}</div>
          </div>
          <div style={{ background: '#fffbeb', padding: 16, borderRadius: 12, textAlign: 'center' }}>
            <div style={{ fontSize: 12, color: '#b45309', fontWeight: 600 }}>SALDO (Debito residuo)</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#b45309', marginTop: 4 }}>{formatEuro(fornitori.totali.saldo_totale)}</div>
          </div>
          <div style={{ background: '#f8fafc', padding: 16, borderRadius: 12, textAlign: 'center' }}>
            <div style={{ fontSize: 12, color: '#475569', fontWeight: 600 }}>FORNITORI</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#1e293b', marginTop: 4 }}>
              {fornitori.totali.n_fornitori}
              <span style={{ fontSize: 13, color: '#ef4444', marginLeft: 8 }}>
                ({fornitori.totali.n_aperti} aperti)
              </span>
            </div>
          </div>
        </PageGrid>
      )}

      {/* Filtri */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', margin: '20px 0', flexWrap: 'wrap' }}>
        <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
          <Search size={16} style={{ position: 'absolute', left: 12, top: 10, color: '#94a3b8' }} />
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Cerca fornitore o P.IVA..."
            style={{ width: '100%', padding: '8px 12px 8px 36px', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 14 }} />
        </div>
        <select value={filtroStato} onChange={e => setFiltroStato(e.target.value)}
          style={{ padding: '8px 16px', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 13, fontWeight: 500 }}>
          <option value="tutti">Tutti gli stati</option>
          <option value="aperto">Solo aperti</option>
          <option value="saldato">Solo saldati</option>
          <option value="credito">A credito</option>
        </select>
        <button onClick={exportCSV}
          style={{ padding: '8px 16px', borderRadius: 8, border: 'none', background: '#1535a8', color: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 600 }}>
          <Download size={14} /> CSV
        </button>
      </div>

      {/* Tabella */}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
          <thead>
            <tr style={{ background: '#1e293b', color: 'white' }}>
              <th style={{ padding: '12px 8px', width: 30 }}></th>
              <SortHeader field="fornitore">Fornitore</SortHeader>
              <th style={{ padding: '12px 8px', textAlign: 'left', width: 130 }}>P.IVA</th>
              <SortHeader field="dare" align="right">Dare (Fatture)</SortHeader>
              <SortHeader field="avere" align="right">Avere (Pagamenti)</SortHeader>
              <SortHeader field="saldo" align="right">Saldo</SortHeader>
              <th style={{ padding: '12px 8px', textAlign: 'center', width: 90 }}>Stato</th>
              <SortHeader field="n_doc" align="center">Doc.</SortHeader>
            </tr>
          </thead>
          <tbody>
            {fornitoriFiltered.map((f, idx) => {
              const isExpanded = expandedForn.has(f.partita_iva);
              return (
                <React.Fragment key={f.partita_iva}>
                  <tr onClick={() => toggleForn(f.partita_iva)}
                    style={{ background: idx % 2 === 0 ? 'white' : '#fafafa', cursor: 'pointer', borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '10px 8px' }}>
                      {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </td>
                    <td style={{ padding: '10px 8px', fontWeight: 500 }}>{f.fornitore}</td>
                    <td style={{ padding: '10px 8px', fontFamily: 'monospace', fontSize: 12, color: '#64748b' }}>{f.partita_iva}</td>
                    <td style={{ padding: '10px 8px', textAlign: 'right', color: '#059669', fontWeight: 500 }}>{formatEuro(f.totale_dare)}</td>
                    <td style={{ padding: '10px 8px', textAlign: 'right', color: '#dc2626', fontWeight: 500 }}>{formatEuro(f.totale_avere)}</td>
                    <td style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 700, color: f.saldo > 0 ? '#b45309' : (f.saldo < 0 ? '#1535a8' : '#16a34a') }}>
                      {formatEuro(f.saldo)}
                    </td>
                    <td style={{ padding: '10px 8px', textAlign: 'center' }}>{getStatoBadge(f.stato)}</td>
                    <td style={{ padding: '10px 8px', textAlign: 'center', fontSize: 12, color: '#64748b' }}>{f.n_documenti}</td>
                  </tr>
                  {/* Dettaglio movimenti */}
                  {isExpanded && f.movimenti?.length > 0 && (
                    <tr>
                      <td colSpan={8} style={{ padding: '0 0 8px 40px', background: '#f8fafc' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                          <thead>
                            <tr style={{ color: '#94a3b8', borderBottom: '1px solid #e2e8f0' }}>
                              <th style={{ padding: '8px', textAlign: 'left' }}>Data</th>
                              <th style={{ padding: '8px', textAlign: 'left' }}>Tipo</th>
                              <th style={{ padding: '8px', textAlign: 'left' }}>Numero</th>
                              <th style={{ padding: '8px', textAlign: 'right' }}>Dare</th>
                              <th style={{ padding: '8px', textAlign: 'right' }}>Avere</th>
                              <th style={{ padding: '8px', textAlign: 'right' }}>Pagato</th>
                              <th style={{ padding: '8px', textAlign: 'center' }}>Stato</th>
                            </tr>
                          </thead>
                          <tbody>
                            {f.movimenti.map((m, mi) => (
                              <tr key={mi} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                <td style={{ padding: '6px 8px', color: '#6080a0' }}>{m.data}</td>
                                <td style={{ padding: '6px 8px' }}>
                                  <span style={{ 
                                    padding: '1px 6px', borderRadius: 4, fontSize: 10, fontWeight: 600,
                                    background: m.tipo === 'nota_credito' ? '#dbeafe' : '#f1f5f9',
                                    color: m.tipo === 'nota_credito' ? '#1535a8' : '#475569'
                                  }}>
                                    {m.tipo === 'nota_credito' ? 'NC' : 'FATT'}
                                  </span>
                                </td>
                                <td style={{ padding: '6px 8px', fontFamily: 'monospace' }}>{m.numero}</td>
                                <td style={{ padding: '6px 8px', textAlign: 'right', color: m.dare > 0 ? '#059669' : '#cbd5e1' }}>
                                  {m.dare > 0 ? formatEuro(m.dare) : '-'}
                                </td>
                                <td style={{ padding: '6px 8px', textAlign: 'right', color: m.avere > 0 ? '#dc2626' : '#cbd5e1' }}>
                                  {m.avere > 0 ? formatEuro(m.avere) : '-'}
                                </td>
                                <td style={{ padding: '6px 8px', textAlign: 'right', color: '#7c3aed', fontWeight: 500 }}>
                                  {m.pagato > 0 ? formatEuro(m.pagato) : '-'}
                                </td>
                                <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                                  {m.stato === 'pagata' 
                                    ? <CheckCircle size={14} color="#16a34a" />
                                    : <AlertCircle size={14} color="#d97706" />
                                  }
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
          {fornitoriFiltered.length > 0 && (
            <tfoot>
              <tr style={{ background: '#1e293b', color: 'white', fontWeight: 700 }}>
                <td colSpan={3} style={{ padding: '12px 8px' }}>TOTALE ({fornitoriFiltered.length} fornitori)</td>
                <td style={{ padding: '12px 8px', textAlign: 'right' }}>
                  {formatEuro(fornitoriFiltered.reduce((s, f) => s + f.totale_dare, 0))}
                </td>
                <td style={{ padding: '12px 8px', textAlign: 'right' }}>
                  {formatEuro(fornitoriFiltered.reduce((s, f) => s + f.totale_avere, 0))}
                </td>
                <td style={{ padding: '12px 8px', textAlign: 'right' }}>
                  {formatEuro(fornitoriFiltered.reduce((s, f) => s + f.saldo, 0))}
                </td>
                <td colSpan={2}></td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      {fornitoriFiltered.length === 0 && (
        <div style={{ textAlign: 'center', padding: 60, color: '#64748b' }}>
          <Building2 size={48} style={{ margin: '0 auto 16px', opacity: 0.3 }} />
          <p>Nessun fornitore trovato{search ? ` per "${search}"` : ''}</p>
        </div>
      )}
    </>
  );

  // --- TAB CLIENTI ---
  const ClientiView = () => {
    if (!clienti) return null;
    const { corrispettivi_mensili, fatture_emesse, totali } = clienti;
    
    return (
      <>
        {/* Summary */}
        <PageGrid cols={4} gap={16}>
          <div style={{ background: '#f0fdf4', padding: 16, borderRadius: 12, textAlign: 'center' }}>
            <div style={{ fontSize: 12, color: '#059669', fontWeight: 600 }}>TOTALE CORRISPETTIVI</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#059669', marginTop: 4 }}>{formatEuro(totali.totale_corrispettivi)}</div>
          </div>
          <div style={{ background: '#eff6ff', padding: 16, borderRadius: 12, textAlign: 'center' }}>
            <div style={{ fontSize: 12, color: '#1535a8', fontWeight: 600 }}>FATTURE EMESSE</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#1535a8', marginTop: 4 }}>{formatEuro(totali.totale_fatture_emesse)}</div>
          </div>
          <div style={{ background: '#fdf4ff', padding: 16, borderRadius: 12, textAlign: 'center' }}>
            <div style={{ fontSize: 12, color: '#9333ea', fontWeight: 600 }}>GIORNI VENDITA</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#9333ea', marginTop: 4 }}>{totali.n_giorni_vendita}</div>
          </div>
          <div style={{ background: '#fffbeb', padding: 16, borderRadius: 12, textAlign: 'center' }}>
            <div style={{ fontSize: 12, color: '#b45309', fontWeight: 600 }}>MEDIA GIORNALIERA</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#b45309', marginTop: 4 }}>{formatEuro(totali.media_giornaliera)}</div>
          </div>
        </PageGrid>

        {/* Corrispettivi mensili */}
        <PageSection title="Corrispettivi Mensili" icon={<CreditCard size={18} />} style={{ marginTop: 24 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ background: '#1e293b', color: 'white' }}>
                <th style={{ padding: '12px 8px', textAlign: 'left' }}>Mese</th>
                <th style={{ padding: '12px 8px', textAlign: 'right' }}>Totale Lordo</th>
                <th style={{ padding: '12px 8px', textAlign: 'right' }}>Imponibile</th>
                <th style={{ padding: '12px 8px', textAlign: 'right' }}>IVA</th>
                <th style={{ padding: '12px 8px', textAlign: 'center' }}>Giorni</th>
                <th style={{ padding: '12px 8px', textAlign: 'right' }}>Media/giorno</th>
              </tr>
            </thead>
            <tbody>
              {corrispettivi_mensili.map((m, idx) => {
                const media = m.n_operazioni > 0 ? m.totale_dare / m.n_operazioni : 0;
                const hasData = m.totale_dare > 0;
                return (
                  <tr key={m.mese} style={{ background: idx % 2 === 0 ? 'white' : '#fafafa', borderBottom: '1px solid #f1f5f9', opacity: hasData ? 1 : 0.4 }}>
                    <td style={{ padding: '10px 8px', fontWeight: 500 }}>{m.nome_mese}</td>
                    <td style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 600, color: '#059669' }}>
                      {hasData ? formatEuro(m.totale_dare) : '-'}
                    </td>
                    <td style={{ padding: '10px 8px', textAlign: 'right', color: '#475569' }}>
                      {hasData ? formatEuro(m.imponibile) : '-'}
                    </td>
                    <td style={{ padding: '10px 8px', textAlign: 'right', color: '#dc2626' }}>
                      {hasData ? formatEuro(m.iva) : '-'}
                    </td>
                    <td style={{ padding: '10px 8px', textAlign: 'center', color: '#64748b' }}>
                      {m.n_operazioni || '-'}
                    </td>
                    <td style={{ padding: '10px 8px', textAlign: 'right', color: '#7c3aed', fontWeight: 500 }}>
                      {hasData ? formatEuro(media) : '-'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr style={{ background: '#1e293b', color: 'white', fontWeight: 700 }}>
                <td style={{ padding: '12px 8px' }}>TOTALE</td>
                <td style={{ padding: '12px 8px', textAlign: 'right' }}>{formatEuro(totali.totale_corrispettivi)}</td>
                <td style={{ padding: '12px 8px', textAlign: 'right' }}>
                  {formatEuro(corrispettivi_mensili.reduce((s, m) => s + m.imponibile, 0))}
                </td>
                <td style={{ padding: '12px 8px', textAlign: 'right' }}>
                  {formatEuro(corrispettivi_mensili.reduce((s, m) => s + m.iva, 0))}
                </td>
                <td style={{ padding: '12px 8px', textAlign: 'center' }}>{totali.n_giorni_vendita}</td>
                <td style={{ padding: '12px 8px', textAlign: 'right' }}>{formatEuro(totali.media_giornaliera)}</td>
              </tr>
            </tfoot>
          </table>
        </PageSection>

        {/* Fatture emesse */}
        {fatture_emesse?.length > 0 && (
          <PageSection title={`Fatture Emesse a Clienti (${fatture_emesse.length})`} icon={<FileText size={18} />} style={{ marginTop: 24 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr style={{ background: '#f1f5f9', borderBottom: '2px solid #e2e8f0' }}>
                  <th style={{ padding: '10px 8px', textAlign: 'left' }}>Cliente</th>
                  <th style={{ padding: '10px 8px', textAlign: 'left' }}>Numero</th>
                  <th style={{ padding: '10px 8px', textAlign: 'center' }}>Data</th>
                  <th style={{ padding: '10px 8px', textAlign: 'right' }}>Importo</th>
                  <th style={{ padding: '10px 8px', textAlign: 'center' }}>Stato</th>
                </tr>
              </thead>
              <tbody>
                {fatture_emesse.map((fe, idx) => (
                  <tr key={idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '8px', fontWeight: 500 }}>{fe.cliente}</td>
                    <td style={{ padding: '8px', fontFamily: 'monospace', fontSize: 12 }}>{fe.numero}</td>
                    <td style={{ padding: '8px', textAlign: 'center', color: '#64748b' }}>{fe.data}</td>
                    <td style={{ padding: '8px', textAlign: 'right', fontWeight: 600 }}>{formatEuro(fe.importo)}</td>
                    <td style={{ padding: '8px', textAlign: 'center' }}>
                      <span style={{ padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600, background: '#dcfce7', color: '#16a34a' }}>
                        {fe.stato}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </PageSection>
        )}

        {/* Nota HORECA */}
        <div style={{ marginTop: 24, padding: 16, background: '#eff6ff', borderRadius: 8, border: '1px solid #bfdbfe' }}>
          <p style={{ margin: 0, fontSize: 12, color: '#1535a8' }}>
            <strong>Nota HORECA:</strong> Per le attività al dettaglio (ristoranti, bar) i clienti sono prevalentemente anonimi. 
            I corrispettivi rappresentano vendite con incasso contestuale, quindi Dare = Avere (saldo zero). 
            Le eventuali fatture emesse a clienti sono già incluse nei corrispettivi e servono solo per la detrazione IVA del cliente.
          </p>
        </div>
      </>
    );
  };

  return (
    <PageLayout
      title="Partitario Clienti/Fornitori"
      icon={<Users size={28} />}
      subtitle={`Estratti conto dare/avere per soggetto – Anno ${anno}`}
    >
      {/* Tabs */}
      <div style={{ display: 'flex', gap: 0, marginBottom: 24, borderBottom: '2px solid #e2e8f0' }}>
        <button onClick={() => setActiveTab('fornitori')}
          style={{ 
            padding: '14px 28px', border: 'none', 
            background: activeTab === 'fornitori' ? '#1e293b' : 'transparent', 
            color: activeTab === 'fornitori' ? 'white' : '#64748b', 
            fontSize: 15, fontWeight: 600, cursor: 'pointer', borderRadius: '8px 8px 0 0',
            display: 'flex', alignItems: 'center', gap: 8
          }}>
          <Building2 size={18} /> Fornitori
          {fornitori?.totali && (
            <span style={{ 
              padding: '2px 8px', borderRadius: 10, fontSize: 11,
              background: activeTab === 'fornitori' ? 'rgba(255,255,255,0.2)' : '#e2e8f0'
            }}>
              {fornitori.totali.n_fornitori}
            </span>
          )}
        </button>
        <button onClick={() => setActiveTab('clienti')}
          style={{ 
            padding: '14px 28px', border: 'none', 
            background: activeTab === 'clienti' ? '#1e293b' : 'transparent', 
            color: activeTab === 'clienti' ? 'white' : '#64748b', 
            fontSize: 15, fontWeight: 600, cursor: 'pointer', borderRadius: '8px 8px 0 0',
            display: 'flex', alignItems: 'center', gap: 8
          }}>
          <CreditCard size={18} /> Clienti (Corrispettivi)
        </button>
      </div>

      {loading ? (
        <PageLoading message="Caricamento partitario..." />
      ) : (
        <>
          {activeTab === 'fornitori' && <FornitoriView />}
          {activeTab === 'clienti' && <ClientiView />}
        </>
      )}
    </PageLayout>
  );
}
