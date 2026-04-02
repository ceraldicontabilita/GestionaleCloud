import { formatDateIT } from '../../lib/utils';
/**
 * Tab Contratti - Componente ottimizzato
 * Gestisce visualizzazione e gestione contratti dipendenti
 * NOTA: Usa React Query per caricare dipendenti in modo indipendente dal parent
 */
import React, { memo, useCallback, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../../api';
import { queryKeys } from '../../lib/queryClient';

const TIPOLOGIE_CONTRATTO = [
  'Tempo Indeterminato',
  'Tempo Determinato',
  'Apprendistato',
  'Stage',
  'Collaborazione',
  'Partita IVA'
];

const ContrattiTab = memo(function ContrattiTab() {
  // Carica dipendenti direttamente con React Query (non dipende dal parent)
  const { data: dipendenti = [] } = useQuery({
    queryKey: queryKeys.dipendenti.list({}),
    queryFn: async () => {
      const res = await api.get('/api/dipendenti');
      return res.data || [];
    },
    staleTime: 5 * 60 * 1000, // Cache 5 minuti
  });
  
  console.log('ContrattiTab dipendenti:', dipendenti?.length || 0);
  
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    dipendente_id: '',
    tipologia: '',
    data_inizio: '',
    data_fine: '',
    ore_settimanali: '',
    retribuzione: '',
    note: ''
  });

  // Query per contratti
  const { data: contratti = [], isLoading } = useQuery({
    queryKey: queryKeys.contratti.list(),
    queryFn: async () => {
      const res = await api.get('/api/dipendenti/contratti');
      return res.data || [];
    }
  });

  // Query per scadenze
  const { data: scadenze = { scaduti: [], in_scadenza: [] } } = useQuery({
    queryKey: queryKeys.contratti.scadenze(),
    queryFn: async () => {
      const res = await api.get('/api/dipendenti/contratti/scadenze');
      return res.data || { scaduti: [], in_scadenza: [] };
    }
  });

  // Mutations
  const createMutation = useMutation({
    mutationFn: async (data) => {
      const res = await api.post('/api/dipendenti/contratti', data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.contratti.all });
      setShowForm(false);
      setFormData({ dipendente_id: '', tipologia: '', data_inizio: '', data_fine: '', ore_settimanali: '', retribuzione: '', note: '' });
    }
  });

  const terminateMutation = useMutation({
    mutationFn: async (contrattoId) => {
      const oggi = new Date().toISOString().split('T')[0];
      await api.post(`/api/dipendenti/contratti/${contrattoId}/termina?data_fine=${oggi}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.contratti.all });
    }
  });

  const importMutation = useMutation({
    mutationFn: async (file) => {
      const formData = new FormData();
      formData.append('file', file);
      const res = await api.post('/api/dipendenti/contratti/import-excel', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.contratti.all });
    }
  });

  // Handlers
  const handleSubmit = useCallback((e) => {
    e.preventDefault();
    if (!formData.dipendente_id || !formData.tipologia || !formData.data_inizio) {
      alert('Compila i campi obbligatori');
      return;
    }
    createMutation.mutate(formData);
  }, [formData, createMutation]);

  const handleTerminate = useCallback((contrattoId) => {
    if (window.confirm('Sei sicuro di voler terminare questo contratto?')) {
      terminateMutation.mutate(contrattoId);
    }
  }, [terminateMutation]);

  const handleImport = useCallback((e) => {
    const file = e.target.files[0];
    if (file) importMutation.mutate(file);
    e.target.value = '';
  }, [importMutation]);

  const updateField = useCallback((field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  }, []);

  return (
    <>
      {/* Header */}
      <div style={{
        background: 'linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)',
        padding: 20,
        borderRadius: 12,
        color: 'white',
        marginBottom: 20,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: 12
      }}>
        <div>
          <h3 style={{ margin: '0 0 8px 0' }}>📄 Gestione Contratti</h3>
          <div style={{ fontSize: 14, opacity: 0.9 }}>
            {contratti.length} contratti totali • {scadenze.scaduti?.length || 0} scaduti • {scadenze.in_scadenza?.length || 0} in scadenza
          </div>
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          <label style={{
            padding: '10px 20px',
            background: 'rgba(255,255,255,0.2)',
            color: 'white',
            border: '1px solid rgba(255,255,255,0.3)',
            borderRadius: 8,
            cursor: 'pointer',
            fontWeight: 'bold'
          }}>
            📥 Importa Excel
            <input
              type="file"
              accept=".xlsx,.xls"
              onChange={handleImport}
              style={{ display: 'none' }}
            />
          </label>
          <button
            onClick={() => setShowForm(true)}
            style={{
              padding: '10px 20px',
              background: 'white',
              color: '#7c3aed',
              border: 'none',
              borderRadius: 8,
              cursor: 'pointer',
              fontWeight: 'bold'
            }}
          >
            ➕ Nuovo Contratto
          </button>
        </div>
      </div>

      {/* Alert scadenze */}
      {(scadenze.scaduti?.length > 0 || scadenze.in_scadenza?.length > 0) && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: 16,
          marginBottom: 20
        }}>
          {scadenze.scaduti?.length > 0 && (
            <div style={{
              padding: 16,
              borderRadius: 12,
              background: '#fee2e2',
              border: '1px solid #fecaca'
            }}>
              <div style={{ fontWeight: 'bold', color: '#dc2626', marginBottom: 8 }}>
                ⚠️ {scadenze.scaduti.length} Contratti Scaduti
              </div>
              {scadenze.scaduti.slice(0, 3).map((c, i) => (
                <div key={i} style={{ fontSize: 14, color: '#991b1b' }}>
                  • {c.dipendente_nome}
                </div>
              ))}
            </div>
          )}
          {scadenze.in_scadenza?.length > 0 && (
            <div style={{
              padding: 16,
              borderRadius: 12,
              background: '#fef3c7',
              border: '1px solid #fde68a'
            }}>
              <div style={{ fontWeight: 'bold', color: '#d97706', marginBottom: 8 }}>
                ⏰ {scadenze.in_scadenza.length} In Scadenza (30 giorni)
              </div>
              {scadenze.in_scadenza.slice(0, 3).map((c, i) => (
                <div key={i} style={{ fontSize: 14, color: '#92400e' }}>
                  • {c.dipendente_nome}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tabella */}
      <div style={{ background: 'white', borderRadius: 12, overflow: 'hidden', border: '1px solid #e2e8f0' }}>
        {isLoading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>⏳ Caricamento...</div>
        ) : contratti.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>📄</div>
            <div>Nessun contratto registrato</div>
            <div style={{ fontSize: 13, marginTop: 8 }}>Clicca &quot;Nuovo Contratto&quot; o importa da Excel</div>
          </div>
        ) : (
          <div style={{ maxHeight: 450, overflowY: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead style={{ position: 'sticky', top: 0, background: '#f9fafb' }}>
                <tr>
                  <th style={{ padding: 12, textAlign: 'left', borderBottom: '1px solid #e2e8f0' }}>Dipendente</th>
                  <th style={{ padding: 12, textAlign: 'left', borderBottom: '1px solid #e2e8f0' }}>Tipologia</th>
                  <th style={{ padding: 12, textAlign: 'center', borderBottom: '1px solid #e2e8f0' }}>Inizio</th>
                  <th style={{ padding: 12, textAlign: 'center', borderBottom: '1px solid #e2e8f0' }}>Fine</th>
                  <th style={{ padding: 12, textAlign: 'center', borderBottom: '1px solid #e2e8f0' }}>Ore/Sett</th>
                  <th style={{ padding: 12, textAlign: 'center', borderBottom: '1px solid #e2e8f0' }}>Stato</th>
                  <th style={{ padding: 12, textAlign: 'center', borderBottom: '1px solid #e2e8f0', width: 80 }}>Azioni</th>
                </tr>
              </thead>
              <tbody>
                {contratti.map((contratto, idx) => (
                  <tr key={contratto.id || idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: 12, fontWeight: 500 }}>{contratto.dipendente_nome}</td>
                    <td style={{ padding: 12 }}>{contratto.tipologia}</td>
                    <td style={{ padding: 12, textAlign: 'center' }}>
                      {contratto.data_inizio ? formatDateIT(contratto.data_inizio) : '-'}
                    </td>
                    <td style={{ padding: 12, textAlign: 'center' }}>
                      {contratto.data_fine ? formatDateIT(contratto.data_fine) : 'Indeterminato'}
                    </td>
                    <td style={{ padding: 12, textAlign: 'center' }}>{contratto.ore_settimanali || '-'}</td>
                    <td style={{ padding: 12, textAlign: 'center' }}>
                      <span style={{
                        padding: '4px 12px',
                        borderRadius: 20,
                        fontSize: 12,
                        fontWeight: 'bold',
                        background: contratto.attivo ? '#dcfce7' : '#f3f4f6',
                        color: contratto.attivo ? '#16a34a' : '#6b7280'
                      }}>
                        {contratto.attivo ? '✅ Attivo' : '⏹️ Terminato'}
                      </span>
                    </td>
                    <td style={{ padding: 12, textAlign: 'center' }}>
                      {contratto.attivo && (
                        <button
                          onClick={() => handleTerminate(contratto.id)}
                          disabled={terminateMutation.isPending}
                          style={{
                            padding: '4px 8px',
                            background: '#fee2e2',
                            color: '#dc2626',
                            border: 'none',
                            borderRadius: 4,
                            cursor: 'pointer',
                            fontSize: 12
                          }}
                          title="Termina contratto"
                        >
                          ⏹️
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modal nuovo contratto */}
      {showForm && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000
        }}>
          <div style={{
            background: 'white',
            padding: 24,
            borderRadius: 12,
            width: '90%',
            maxWidth: 500,
            boxShadow: '0 20px 60px rgba(0,0,0,0.3)'
          }}>
            <h3 style={{ margin: '0 0 20px 0' }}>➕ Nuovo Contratto</h3>
            <form onSubmit={handleSubmit}>
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold' }}>Dipendente *</label>
                <select
                  value={formData.dipendente_id}
                  onChange={(e) => updateField('dipendente_id', e.target.value)}
                  style={{ width: '100%', padding: 10, borderRadius: 6, border: '1px solid #e2e8f0' }}
                  required
                >
                  <option value="">-- Seleziona --</option>
                  {dipendenti.map(d => (
                    <option key={d.id} value={d.id}>
                      {d.nome_completo || `${d.cognome || ''} ${d.nome || ''}`.trim()}
                    </option>
                  ))}
                </select>
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold' }}>Tipologia *</label>
                <select
                  value={formData.tipologia}
                  onChange={(e) => updateField('tipologia', e.target.value)}
                  style={{ width: '100%', padding: 10, borderRadius: 6, border: '1px solid #e2e8f0' }}
                  required
                >
                  <option value="">-- Seleziona --</option>
                  {TIPOLOGIE_CONTRATTO.map(t => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
                <div>
                  <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold' }}>Data Inizio *</label>
                  <input
                    type="date"
                    value={formData.data_inizio}
                    onChange={(e) => updateField('data_inizio', e.target.value)}
                    style={{ width: '100%', padding: 10, borderRadius: 6, border: '1px solid #e2e8f0', boxSizing: 'border-box' }}
                    required
                  />
                </div>
                <div>
                  <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold' }}>Data Fine</label>
                  <input
                    type="date"
                    value={formData.data_fine}
                    onChange={(e) => updateField('data_fine', e.target.value)}
                    style={{ width: '100%', padding: 10, borderRadius: 6, border: '1px solid #e2e8f0', boxSizing: 'border-box' }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
                <div>
                  <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold' }}>Ore Settimanali</label>
                  <input
                    type="number"
                    value={formData.ore_settimanali}
                    onChange={(e) => updateField('ore_settimanali', e.target.value)}
                    style={{ width: '100%', padding: 10, borderRadius: 6, border: '1px solid #e2e8f0', boxSizing: 'border-box' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold' }}>Retribuzione €</label>
                  <input
                    type="number"
                    step="0.01"
                    value={formData.retribuzione}
                    onChange={(e) => updateField('retribuzione', e.target.value)}
                    style={{ width: '100%', padding: 10, borderRadius: 6, border: '1px solid #e2e8f0', boxSizing: 'border-box' }}
                  />
                </div>
              </div>

              <div style={{ marginBottom: 20 }}>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold' }}>Note</label>
                <textarea
                  value={formData.note}
                  onChange={(e) => updateField('note', e.target.value)}
                  rows={3}
                  style={{ width: '100%', padding: 10, borderRadius: 6, border: '1px solid #e2e8f0', boxSizing: 'border-box', resize: 'vertical' }}
                />
              </div>

              <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  onClick={() => setShowForm(false)}
                  style={{
                    padding: '10px 20px',
                    background: '#f1f5f9',
                    border: 'none',
                    borderRadius: 6,
                    cursor: 'pointer'
                  }}
                >
                  Annulla
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  style={{
                    padding: '10px 20px',
                    background: createMutation.isPending ? '#9ca3af' : '#7c3aed',
                    color: 'white',
                    border: 'none',
                    borderRadius: 6,
                    cursor: createMutation.isPending ? 'wait' : 'pointer',
                    fontWeight: 'bold'
                  }}
                >
                  {createMutation.isPending ? '⏳ Salvataggio...' : '✓ Salva'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
});

export default ContrattiTab;
