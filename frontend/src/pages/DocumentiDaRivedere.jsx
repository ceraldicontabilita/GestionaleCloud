import React, { useState, useEffect } from 'react';
import api from '../api';
import { formatEuro } from '../lib/utils';
import { PageLayout, PageSection, PageGrid, PageLoading, PageEmpty } from '../components/PageLayout';
import { AlertCircle, Brain, CheckCircle, Clock, Tag, Filter, RefreshCw, FileText, Building2, ChevronDown } from 'lucide-react';
import { useAnnoGlobale } from '../contexts/AnnoContext';

export default function DocumentiDaRivedere() {
  const [documents, setDocuments] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [centriCosto, setCentriCosto] = useState([]);
  const [filterType, setFilterType] = useState('');
  const [classifyingId, setClassifyingId] = useState(null);

  useEffect(() => {
    fetchDocuments();
    fetchCentriCosto();
  }, [filterType]);

  const fetchDocuments = async () => {
    setLoading(true);
    try {
      const url = filterType ? `/api/ai-parser/da-rivedere?tipo=${filterType}` : '/api/ai-parser/da-rivedere';
      const docsRes = await api.get(url);
      const docs = Array.isArray(docsRes.data) ? docsRes.data : docsRes.data?.documents || [];
      setDocuments(docs);
      // Calcola stats dai documenti
      const calcStats = {
        totale: docs.length,
        fatture: docs.filter(d => d.tipo === 'fattura').length,
        f24: docs.filter(d => d.tipo === 'f24').length,
        buste_paga: docs.filter(d => d.tipo === 'busta_paga').length,
        altro: docs.filter(d => !['fattura', 'f24', 'busta_paga'].includes(d.tipo)).length
      };
      setStats(calcStats);
    } catch (err) {
      console.error('Errore caricamento documenti:', err);
      setDocuments([]);
      setStats({});
    } finally {
      setLoading(false);
    }
  };

  const fetchCentriCosto = async () => {
    try {
      const res = await api.get('/api/centri-costo/centri-costo');
      setCentriCosto(res.data || []);
    } catch (err) {
      console.error('Errore caricamento CDC:', err);
    }
  };

  const handleProcessBatch = async () => {
    setProcessing(true);
    try {
      await api.post('/api/ai-parser/da-rivedere/process-batch');
      fetchDocuments();
    } catch (err) {
      alert('Errore: ' + (err.response?.data?.detail || err.message));
    } finally {
      setProcessing(false);
    }
  };

  const handleClassify = async (docId, cdcCode) => {
    setClassifyingId(docId);
    try {
      await api.put(`/api/ai-parser/da-rivedere/${docId}/classifica`, { centro_costo: cdcCode });
      fetchDocuments();
    } catch (err) {
      alert('Errore classificazione: ' + (err.response?.data?.detail || err.message));
    } finally {
      setClassifyingId(null);
    }
  };

  const getTypeColor = (type) => ({
    fattura: { bg: '#dbeafe', color: '#1535a8' },
    f24: { bg: '#fee2e2', color: '#dc2626' },
    busta_paga: { bg: '#dcfce7', color: '#166534' },
    altro: { bg: '#f3f4f6', color: '#6b7280' }
  }[type] || { bg: '#f3f4f6', color: '#6b7280' });

  const getTypeLabel = (type) => ({ fattura: 'Fattura', f24: 'F24', busta_paga: 'Busta Paga', altro: 'Altro' }[type] || type);

  const KPICard = ({ label, value, color, icon }) => (
    <div style={{ padding: 16, background: 'white', borderRadius: 12, boxShadow: '0 1px 3px rgba(0,0,0,0.1)', borderLeft: `4px solid ${color}` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ color }}>{icon}</span>
        <span style={{ fontSize: 12, color: '#64748b', textTransform: 'uppercase' }}>{label}</span>
      </div>
      <p style={{ margin: 0, fontSize: 24, fontWeight: 700, color }}>{value}</p>
    </div>
  );

  return (
    <PageLayout
      title="Documenti Da Rivedere"
      icon={<AlertCircle size={28} color="#d97706" />}
      subtitle="Documenti che richiedono classificazione manuale o verifica dei dati estratti dall'AI"
      actions={
        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={handleProcessBatch} disabled={processing}
            style={{ padding: '10px 16px', borderRadius: 8, border: 'none', background: processing ? '#94a3b8' : '#8b5cf6', color: 'white', fontSize: 13, fontWeight: 600, cursor: processing ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
            <Brain size={16} /> {processing ? 'Elaborazione...' : 'Processa Email'}
          </button>
          <button onClick={fetchDocuments} disabled={loading}
            style={{ padding: '10px 16px', borderRadius: 8, border: '1px solid #e2e8f0', background: 'white', fontSize: 13, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
            <RefreshCw size={16} /> Aggiorna
          </button>
        </div>
      }
    >
      {/* KPI */}
      <PageGrid cols={5} gap={12}>
        <KPICard label="Da Rivedere" value={stats.needs_review || documents.length} color="#d97706" icon={<AlertCircle size={20} />} />
        <KPICard label="Processati AI" value={stats.total_parsed || 0} color="#1535a8" icon={<Brain size={20} />} />
        <KPICard label="Classificati Auto" value={stats.auto_classified || 0} color="#16a34a" icon={<CheckCircle size={20} />} />
        <KPICard label="In Attesa" value={stats.pending_processing || 0} color="#8b5cf6" icon={<Clock size={20} />} />
        <KPICard label="Tasso Classif." value={`${stats.classification_rate || 0}%`} color="#06b6d4" icon={<Tag size={20} />} />
      </PageGrid>

      {/* Filtri */}
      <PageSection title="Filtri" icon={<Filter size={16} />} style={{ marginTop: 20 }}>
        <select value={filterType} onChange={(e) => setFilterType(e.target.value)}
          style={{ padding: '10px 16px', borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 14 }}>
          <option value="">Tutti i tipi</option>
          <option value="fattura">Fatture</option>
          <option value="f24">F24</option>
          <option value="busta_paga">Buste Paga</option>
        </select>
      </PageSection>

      {/* Lista Documenti */}
      <PageSection title={`Documenti (${documents.length})`} icon={<FileText size={16} />} style={{ marginTop: 20, padding: 0 }}>
        {loading ? (
          <div style={{ padding: 20 }}><PageLoading message="Caricamento documenti..." /></div>
        ) : documents.length === 0 ? (
          <div style={{ padding: 40 }}>
            <PageEmpty icon={<CheckCircle size={48} color="#16a34a" />} message="Nessun documento da rivedere. Tutti i documenti sono stati classificati correttamente." />
          </div>
        ) : (
          <div>
            {documents.map(doc => (
              <DocumentRow key={doc.id} doc={doc} centriCosto={centriCosto} onClassify={handleClassify} classifying={classifyingId === doc.id} getTypeColor={getTypeColor} getTypeLabel={getTypeLabel} />
            ))}
          </div>
        )}
      </PageSection>
    </PageLayout>
  );
}

function DocumentRow({ doc, centriCosto, onClassify, classifying, getTypeColor, getTypeLabel }) {
  const [expanded, setExpanded] = useState(false);
  const [selectedCdc, setSelectedCdc] = useState('');
  const typeStyle = getTypeColor(doc.ai_parsed_type);

  return (
    <div style={{ borderBottom: '1px solid #e2e8f0' }}>
      <div onClick={() => setExpanded(!expanded)}
        style={{ padding: 16, display: 'grid', gridTemplateColumns: '1fr auto auto auto', alignItems: 'center', gap: 16, cursor: 'pointer', transition: 'background 0.2s' }}
        onMouseEnter={(e) => e.currentTarget.style.background = '#f8fafc'}
        onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <FileText size={18} color="#64748b" />
            <span style={{ fontWeight: 600, color: '#1e293b' }}>{doc.filename}</span>
            <span style={{ padding: '4px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600, background: typeStyle.bg, color: typeStyle.color }}>{getTypeLabel(doc.ai_parsed_type)}</span>
          </div>
          {doc.fornitore_nome && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
              <Building2 size={14} color="#94a3b8" />
              <span style={{ fontSize: 13, color: '#64748b' }}>{doc.fornitore_nome}</span>
            </div>
          )}
        </div>
        <div style={{ textAlign: 'right' }}>
          {doc.importo_totale && <span style={{ fontWeight: 600, color: '#1e293b' }}>{formatEuro(doc.importo_totale)}</span>}
          {doc.data_documento && <p style={{ margin: 0, fontSize: 12, color: '#94a3b8' }}>{doc.data_documento}</p>}
        </div>
        <div>
          {doc.ai_parsing_error ? (
            <span style={{ padding: '4px 8px', borderRadius: 4, fontSize: 11, background: '#fef2f2', color: '#dc2626' }}>Errore AI</span>
          ) : !doc.classificazione_automatica ? (
            <span style={{ padding: '4px 8px', borderRadius: 4, fontSize: 11, background: '#fef3c7', color: '#d97706' }}>Da classificare</span>
          ) : null}
        </div>
        <ChevronDown size={20} color="#94a3b8" style={{ transform: expanded ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform 0.2s' }} />
      </div>

      {expanded && (
        <div style={{ padding: 16, background: '#f8fafc', borderTop: '1px solid #e2e8f0' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
            <div>
              <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#64748b' }}>Dati Estratti</h4>
              <div style={{ fontSize: 13 }}>
                {doc.ai_parsed_type === 'fattura' && (<><p><strong>Numero:</strong> {doc.numero_documento || '-'}</p><p><strong>P.IVA:</strong> {doc.fornitore_piva || '-'}</p><p><strong>Imponibile:</strong> {formatEuro(doc.imponibile)}</p></>)}
                {doc.ai_parsed_type === 'f24' && (<><p><strong>CF:</strong> {doc.codice_fiscale || '-'}</p><p><strong>Data Pag:</strong> {doc.data_pagamento || '-'}</p><p><strong>Totale:</strong> {formatEuro(doc.totale_versato)}</p></>)}
                {doc.ai_parsed_type === 'busta_paga' && (<><p><strong>Dipendente:</strong> {doc.dipendente_nome || '-'}</p><p><strong>Periodo:</strong> {doc.periodo_mese}/{doc.periodo_anno}</p><p><strong>Netto:</strong> {formatEuro(doc.netto_pagato)}</p></>)}
              </div>
            </div>
            <div>
              <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#64748b' }}>Classifica Manualmente</h4>
              <div style={{ display: 'flex', gap: 8 }}>
                <select value={selectedCdc} onChange={(e) => setSelectedCdc(e.target.value)} style={{ flex: 1, padding: 8, borderRadius: 6, border: '1px solid #e2e8f0', fontSize: 13 }}>
                  <option value="">Seleziona CDC...</option>
                  {centriCosto.map(cdc => (<option key={cdc.codice} value={cdc.codice}>{cdc.nome}</option>))}
                </select>
                <button onClick={() => selectedCdc && onClassify(doc.id, selectedCdc)} disabled={!selectedCdc || classifying}
                  style={{ padding: '8px 16px', borderRadius: 6, border: 'none', background: selectedCdc && !classifying ? '#16a34a' : '#e2e8f0', color: selectedCdc && !classifying ? 'white' : '#94a3b8', fontWeight: 600, cursor: selectedCdc && !classifying ? 'pointer' : 'not-allowed' }}>
                  {classifying ? '...' : 'Classifica'}
                </button>
              </div>
            </div>
          </div>
          {doc.ai_parsing_error && (
            <div style={{ padding: 12, background: '#fef2f2', borderRadius: 6, fontSize: 13, color: '#dc2626' }}><strong>Errore:</strong> {doc.ai_parsing_error}</div>
          )}
        </div>
      )}
    </div>
  );
}
