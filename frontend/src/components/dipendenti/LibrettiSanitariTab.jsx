import { formatDateIT } from '../../lib/utils';
/**
 * Tab Libretti Sanitari - Componente ottimizzato
 * Gestisce visualizzazione e gestione libretti sanitari
 * NOTA: Usa React Query per caricare dipendenti in modo indipendente dal parent
 */
import React, { memo, useCallback, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../../api';
import { queryKeys } from '../../lib/queryClient';

const DEFAULT_FORM = {
  dipendente_nome: '',
  numero_libretto: '',
  data_rilascio: '',
  data_scadenza: '',
  note: ''
};

const LibrettiSanitariTab = memo(function LibrettiSanitariTab() {
  // Carica dipendenti direttamente con React Query (non dipende dal parent)
  const { data: dipendenti = [] } = useQuery({
    queryKey: queryKeys.dipendenti.list({}),
    queryFn: async () => {
      const res = await api.get('/api/dipendenti');
      return res.data || [];
    },
    staleTime: 5 * 60 * 1000, // Cache 5 minuti
  });
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState(DEFAULT_FORM);

  // Query per caricare i dati
  const { data: libretti = [], isLoading } = useQuery({
    queryKey: queryKeys.libretti.list(),
    queryFn: async () => {
      const res = await api.get('/api/dipendenti/libretti-sanitari/all');
      return res.data || [];
    }
  });

  // Mutation per creare
  const createMutation = useMutation({
    mutationFn: async (data) => {
      const res = await api.post('/api/dipendenti/libretti-sanitari', data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.libretti.list() });
      setShowForm(false);
      setFormData(DEFAULT_FORM);
    }
  });

  // Mutation per eliminare
  const deleteMutation = useMutation({
    mutationFn: async (librettoId) => {
      await api.delete(`/api/dipendenti/libretti-sanitari/${librettoId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.libretti.list() });
    }
  });

  // Handlers
  const handleSubmit = useCallback((e) => {
    e.preventDefault();
    if (!formData.dipendente_nome || !formData.numero_libretto) {
      alert('Compila i campi obbligatori');
      return;
    }
    createMutation.mutate(formData);
  }, [formData, createMutation]);

  const handleDelete = useCallback((librettoId) => {
    if (window.confirm('Sei sicuro di voler eliminare questo libretto sanitario?')) {
      deleteMutation.mutate(librettoId);
    }
  }, [deleteMutation]);

  const updateField = useCallback((field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  }, []);

  // Check scadenze
  const checkScadenza = useCallback((dataScadenza) => {
    if (!dataScadenza) return 'valid';
    const oggi = new Date();
    const scadenza = new Date(dataScadenza);
    const diffDays = Math.ceil((scadenza - oggi) / (1000 * 60 * 60 * 24));
    if (diffDays < 0) return 'expired';
    if (diffDays <= 30) return 'expiring';
    return 'valid';
  }, []);

  const scaduti = libretti.filter(l => checkScadenza(l.data_scadenza) === 'expired');
  const inScadenza = libretti.filter(l => checkScadenza(l.data_scadenza) === 'expiring');

  return (
    <>
      {/* Header con pulsanti */}
      <div style={{
        background: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
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
          <h3 style={{ margin: '0 0 8px 0' }}>🏥 Libretti Sanitari</h3>
          <div style={{ fontSize: 14, opacity: 0.9 }}>
            {libretti.length} libretti totali • {scaduti.length} scaduti • {inScadenza.length} in scadenza
          </div>
        </div>
        <button
          onClick={() => setShowForm(true)}
          style={{
            padding: '10px 20px',
            background: 'white',
            color: '#dc2626',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            fontWeight: 'bold'
          }}
        >
          ➕ Nuovo Libretto
        </button>
      </div>

      {/* Alerts scadenze */}
      {scaduti.length > 0 && (
        <div style={{
          padding: 16,
          marginBottom: 16,
          borderRadius: 12,
          background: '#fee2e2',
          border: '1px solid #fecaca'
        }}>
          <div style={{ fontWeight: 'bold', color: '#dc2626', marginBottom: 8 }}>
            ⚠️ {scaduti.length} Libretti Scaduti
          </div>
          {scaduti.map(l => (
            <div key={l.id} style={{ fontSize: 14, color: '#991b1b' }}>
              • {l.dipendente_nome} - Scaduto il {formatDateIT(l.data_scadenza)}
            </div>
          ))}
        </div>
      )}

      {inScadenza.length > 0 && (
        <div style={{
          padding: 16,
          marginBottom: 16,
          borderRadius: 12,
          background: '#fef3c7',
          border: '1px solid #fde68a'
        }}>
          <div style={{ fontWeight: 'bold', color: '#d97706', marginBottom: 8 }}>
            ⏰ {inScadenza.length} Libretti in Scadenza (prossimi 30 giorni)
          </div>
          {inScadenza.map(l => (
            <div key={l.id} style={{ fontSize: 14, color: '#92400e' }}>
              • {l.dipendente_nome} - Scade il {formatDateIT(l.data_scadenza)}
            </div>
          ))}
        </div>
      )}

      {/* Tabella */}
      <div style={{ background: 'white', borderRadius: 12, overflow: 'hidden', border: '1px solid #e2e8f0' }}>
        {isLoading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>⏳ Caricamento...</div>
        ) : libretti.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🏥</div>
            <div>Nessun libretto sanitario registrato</div>
          </div>
        ) : (
          <div style={{ maxHeight: 450, overflowY: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead style={{ position: 'sticky', top: 0, background: '#f9fafb' }}>
                <tr>
                  <th style={{ padding: 12, textAlign: 'left', borderBottom: '1px solid #e2e8f0' }}>Dipendente</th>
                  <th style={{ padding: 12, textAlign: 'left', borderBottom: '1px solid #e2e8f0' }}>N° Libretto</th>
                  <th style={{ padding: 12, textAlign: 'center', borderBottom: '1px solid #e2e8f0' }}>Rilascio</th>
                  <th style={{ padding: 12, textAlign: 'center', borderBottom: '1px solid #e2e8f0' }}>Scadenza</th>
                  <th style={{ padding: 12, textAlign: 'center', borderBottom: '1px solid #e2e8f0' }}>Stato</th>
                  <th style={{ padding: 12, textAlign: 'left', borderBottom: '1px solid #e2e8f0' }}>Note</th>
                  <th style={{ padding: 12, textAlign: 'center', borderBottom: '1px solid #e2e8f0', width: 60 }}>Azioni</th>
                </tr>
              </thead>
              <tbody>
                {libretti.map((libretto, idx) => {
                  const stato = checkScadenza(libretto.data_scadenza);
                  return (
                    <tr key={libretto.id || idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: 12, fontWeight: 500 }}>{libretto.dipendente_nome}</td>
                      <td style={{ padding: 12 }}>{libretto.numero_libretto}</td>
                      <td style={{ padding: 12, textAlign: 'center' }}>
                        {libretto.data_rilascio ? formatDateIT(libretto.data_rilascio) : '-'}
                      </td>
                      <td style={{ padding: 12, textAlign: 'center' }}>
                        {libretto.data_scadenza ? formatDateIT(libretto.data_scadenza) : '-'}
                      </td>
                      <td style={{ padding: 12, textAlign: 'center' }}>
                        <span style={{
                          padding: '4px 12px',
                          borderRadius: 20,
                          fontSize: 12,
                          fontWeight: 'bold',
                          background: stato === 'expired' ? '#fee2e2' : stato === 'expiring' ? '#fef3c7' : '#dcfce7',
                          color: stato === 'expired' ? '#dc2626' : stato === 'expiring' ? '#d97706' : '#16a34a'
                        }}>
                          {stato === 'expired' ? '❌ Scaduto' : stato === 'expiring' ? '⚠️ In Scadenza' : '✅ Valido'}
                        </span>
                      </td>
                      <td style={{ padding: 12, fontSize: 12, color: '#6b7280' }}>{libretto.note || '-'}</td>
                      <td style={{ padding: 12, textAlign: 'center' }}>
                        <button
                          onClick={() => handleDelete(libretto.id)}
                          disabled={deleteMutation.isPending}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 16, opacity: 0.6 }}
                          title="Elimina"
                        >
                          🗑️
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modal nuovo libretto */}
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
            <h3 style={{ margin: '0 0 20px 0' }}>➕ Nuovo Libretto Sanitario</h3>
            <form onSubmit={handleSubmit}>
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold' }}>Dipendente *</label>
                <select
                  value={formData.dipendente_nome}
                  onChange={(e) => updateField('dipendente_nome', e.target.value)}
                  style={{ width: '100%', padding: 10, borderRadius: 6, border: '1px solid #e2e8f0' }}
                  required
                >
                  <option value="">-- Seleziona --</option>
                  {dipendenti.map(d => {
                    const nomeCompleto = d.nome_completo || `${d.cognome || ''} ${d.nome || ''}`.trim();
                    return (
                      <option key={d.id} value={nomeCompleto}>
                        {nomeCompleto}
                      </option>
                    );
                  })}
                </select>
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold' }}>N° Libretto *</label>
                <input
                  type="text"
                  value={formData.numero_libretto}
                  onChange={(e) => updateField('numero_libretto', e.target.value)}
                  style={{ width: '100%', padding: 10, borderRadius: 6, border: '1px solid #e2e8f0', boxSizing: 'border-box' }}
                  required
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
                <div>
                  <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold' }}>Data Rilascio</label>
                  <input
                    type="date"
                    value={formData.data_rilascio}
                    onChange={(e) => updateField('data_rilascio', e.target.value)}
                    style={{ width: '100%', padding: 10, borderRadius: 6, border: '1px solid #e2e8f0', boxSizing: 'border-box' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold' }}>Data Scadenza</label>
                  <input
                    type="date"
                    value={formData.data_scadenza}
                    onChange={(e) => updateField('data_scadenza', e.target.value)}
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
                  onClick={() => { setShowForm(false); setFormData(DEFAULT_FORM); }}
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
                    background: createMutation.isPending ? '#9ca3af' : '#dc2626',
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

export default LibrettiSanitariTab;
