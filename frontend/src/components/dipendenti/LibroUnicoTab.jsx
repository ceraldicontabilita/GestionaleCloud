/**
 * Tab Libro Unico - Componente ottimizzato
 * Gestisce upload, visualizzazione e export buste paga
 */
import React, { memo, useCallback, useEffect, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../../api';
import { formatEuro } from '../../lib/utils';
import { queryKeys } from '../../lib/queryClient';

const MESI_NOMI = ['Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
  'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre'];

const LibroUnicoTab = memo(function LibroUnicoTab({
  selectedYear,
  selectedMonth,
  onChangeYear,
  onChangeMonth
}) {
  const queryClient = useQueryClient();
  const monthYear = `${selectedYear}-${String(selectedMonth).padStart(2, '0')}`;

  // Query per caricare i dati
  const { data: salaries = [], isLoading } = useQuery({
    queryKey: queryKeys.libroUnico.salaries(monthYear),
    queryFn: async () => {
      const res = await api.get(`/api/dipendenti/libro-unico/salaries?month_year=${monthYear}`);
      return res.data || [];
    }
  });

  // Mutation per upload
  const uploadMutation = useMutation({
    mutationFn: async (file) => {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('month_year', monthYear);
      const res = await api.post('/api/dipendenti/libro-unico/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.libroUnico.salaries(monthYear) });
    }
  });

  // Mutation per delete
  const deleteMutation = useMutation({
    mutationFn: async (salaryId) => {
      await api.delete(`/api/dipendenti/libro-unico/salaries/${salaryId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.libroUnico.salaries(monthYear) });
    }
  });

  // Handlers
  const handleUpload = useCallback((e) => {
    const file = e.target.files[0];
    if (file) uploadMutation.mutate(file);
    e.target.value = '';
  }, [uploadMutation]);

  const handleExport = useCallback(async () => {
    try {
      const response = await api.get(`/api/dipendenti/libro-unico/export-excel?month_year=${monthYear}`, {
        responseType: 'blob'
      });
      const blob = new Blob([response.data]);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `libro_unico_${monthYear}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (error) {
      alert('Errore export: ' + (error.response?.data?.detail || error.message));
    }
  }, [monthYear]);

  const handleDelete = useCallback((salaryId) => {
    if (window.confirm('Sei sicuro di voler eliminare questo record?')) {
      deleteMutation.mutate(salaryId);
    }
  }, [deleteMutation]);

  // Computed totals
  const totals = useMemo(() => ({
    count: salaries.length,
    netto: salaries.reduce((sum, s) => sum + (s.netto_a_pagare || 0), 0),
    acconti: salaries.reduce((sum, s) => sum + (s.acconto_pagato || 0), 0),
    daPagare: salaries.reduce((sum, s) => sum + (s.differenza || 0), 0)
  }), [salaries]);

  return (
    <>
      {/* Filtri periodo + Upload */}
      <div style={{
        display: 'flex',
        gap: 12,
        marginBottom: 20,
        alignItems: 'center',
        flexWrap: 'wrap',
        background: '#f8fafc',
        padding: 16,
        borderRadius: 12
      }}>
        <span style={{ fontWeight: 'bold', color: '#475569' }}>📅 Periodo:</span>
        <select
          value={selectedMonth}
          onChange={(e) => onChangeMonth(parseInt(e.target.value))}
          style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #e2e8f0' }}
        >
          {MESI_NOMI.map((m, i) => (
            <option key={i} value={i + 1}>{m}</option>
          ))}
        </select>
        <select
          value={selectedYear}
          onChange={(e) => onChangeYear(parseInt(e.target.value))}
          style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #e2e8f0', background: '#dcfce7', fontWeight: 'bold' }}
        >
          {[2020, 2021, 2022, 2023, 2024, 2025, 2026].map(y => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
      </div>

      {/* Pulsanti Upload/Export */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <label style={{
          padding: '10px 20px',
          background: uploadMutation.isPending ? '#9ca3af' : 'linear-gradient(135deg, #10b981, #059669)',
          color: 'white',
          border: 'none',
          borderRadius: 8,
          cursor: uploadMutation.isPending ? 'wait' : 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          fontWeight: 'bold'
        }}>
          {uploadMutation.isPending ? '⏳ Caricamento...' : '📤 Upload PDF/Excel'}
          <input
            type="file"
            accept=".pdf,.xlsx,.xls"
            onChange={handleUpload}
            disabled={uploadMutation.isPending}
            style={{ display: 'none' }}
          />
        </label>

        <button
          onClick={handleExport}
          disabled={salaries.length === 0}
          style={{
            padding: '10px 20px',
            background: salaries.length === 0 ? '#d1d5db' : 'linear-gradient(135deg, #3b82f6, #2563eb)',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: salaries.length === 0 ? 'not-allowed' : 'pointer',
            fontWeight: 'bold'
          }}
        >
          📊 Esporta Excel
        </button>

        <button
          onClick={() => queryClient.invalidateQueries({ queryKey: queryKeys.libroUnico.salaries(monthYear) })}
          style={{
            padding: '10px 20px',
            background: 'linear-gradient(135deg, #6b7280, #4b5563)',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            fontWeight: 'bold'
          }}
        >
          🔄 Aggiorna
        </button>
      </div>

      {/* Risultato upload */}
      {uploadMutation.isSuccess && uploadMutation.data && (
        <div style={{
          padding: 16,
          marginBottom: 20,
          borderRadius: 12,
          background: '#dcfce7',
          border: '1px solid #10b981'
        }}>
          <div style={{ fontWeight: 'bold', color: '#166534', marginBottom: 8 }}>
            ✅ {uploadMutation.data.message}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 12 }}>
            <div>
              <div style={{ fontSize: 12, color: '#666' }}>Buste Paga</div>
              <div style={{ fontSize: 24, fontWeight: 'bold', color: '#166534' }}>{uploadMutation.data.salaries_count}</div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: '#666' }}>Presenze</div>
              <div style={{ fontSize: 24, fontWeight: 'bold', color: '#0369a1' }}>{uploadMutation.data.presenze_count}</div>
            </div>
          </div>
          <button onClick={() => uploadMutation.reset()} style={{ marginTop: 8, fontSize: 12, cursor: 'pointer', background: 'transparent', border: 'none' }}>
            ✕ Chiudi
          </button>
        </div>
      )}

      {uploadMutation.isError && (
        <div style={{
          padding: 16,
          marginBottom: 20,
          borderRadius: 12,
          background: '#ffebee',
          border: '1px solid #ef5350'
        }}>
          <div style={{ color: '#c62828' }}>❌ {uploadMutation.error?.response?.data?.detail || uploadMutation.error?.message}</div>
          <button onClick={() => uploadMutation.reset()} style={{ marginTop: 8, fontSize: 12, cursor: 'pointer', background: 'transparent', border: 'none' }}>
            ✕ Chiudi
          </button>
        </div>
      )}

      {/* Riepilogo */}
      <div style={{
        background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
        padding: 20,
        borderRadius: 12,
        color: 'white',
        marginBottom: 20
      }}>
        <h3 style={{ margin: '0 0 12px 0' }}>📚 Libro Unico - {MESI_NOMI[selectedMonth - 1]} {selectedYear}</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 16 }}>
          <div>
            <div style={{ fontSize: 12, opacity: 0.8 }}>Buste Paga</div>
            <div style={{ fontSize: 28, fontWeight: 'bold' }}>{totals.count}</div>
          </div>
          <div>
            <div style={{ fontSize: 12, opacity: 0.8 }}>Totale Netto</div>
            <div style={{ fontSize: 28, fontWeight: 'bold' }}>{formatEuro(totals.netto)}</div>
          </div>
          <div>
            <div style={{ fontSize: 12, opacity: 0.8 }}>Acconti Pagati</div>
            <div style={{ fontSize: 28, fontWeight: 'bold' }}>{formatEuro(totals.acconti)}</div>
          </div>
          <div>
            <div style={{ fontSize: 12, opacity: 0.8 }}>Da Pagare</div>
            <div style={{ fontSize: 28, fontWeight: 'bold' }}>{formatEuro(totals.daPagare)}</div>
          </div>
        </div>
      </div>

      {/* Tabella */}
      <div style={{ background: 'white', borderRadius: 12, overflow: 'hidden', border: '1px solid #e2e8f0' }}>
        <div style={{
          padding: '16px 20px',
          background: '#f8fafc',
          borderBottom: '1px solid #e2e8f0',
          fontWeight: 'bold'
        }}>
          📋 Buste Paga - {MESI_NOMI[selectedMonth - 1]} {selectedYear}
        </div>

        {isLoading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>⏳ Caricamento...</div>
        ) : salaries.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
            Nessuna busta paga per questo periodo. Carica un file PDF o Excel.
          </div>
        ) : (
          <div style={{ maxHeight: 450, overflowY: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead style={{ position: 'sticky', top: 0, background: '#f9fafb' }}>
                <tr>
                  <th style={{ padding: 12, textAlign: 'left', borderBottom: '1px solid #e2e8f0' }}>Dipendente</th>
                  <th style={{ padding: 12, textAlign: 'right', borderBottom: '1px solid #e2e8f0' }}>Netto</th>
                  <th style={{ padding: 12, textAlign: 'right', borderBottom: '1px solid #e2e8f0' }}>Acconto</th>
                  <th style={{ padding: 12, textAlign: 'right', borderBottom: '1px solid #e2e8f0' }}>Differenza</th>
                  <th style={{ padding: 12, textAlign: 'left', borderBottom: '1px solid #e2e8f0' }}>Note</th>
                  <th style={{ padding: 12, textAlign: 'center', borderBottom: '1px solid #e2e8f0', width: 60 }}>Azioni</th>
                </tr>
              </thead>
              <tbody>
                {salaries.map((salary, idx) => (
                  <tr key={salary.id || idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: 12, fontWeight: 500 }}>{salary.dipendente_nome}</td>
                    <td style={{ padding: 12, textAlign: 'right', fontWeight: 'bold', color: '#10b981' }}>
                      {formatEuro(salary.netto_a_pagare)}
                    </td>
                    <td style={{ padding: 12, textAlign: 'right', color: '#6b7280' }}>
                      {formatEuro(salary.acconto_pagato)}
                    </td>
                    <td style={{
                      padding: 12,
                      textAlign: 'right',
                      fontWeight: 'bold',
                      color: salary.differenza > 0 ? '#f59e0b' : '#10b981'
                    }}>
                      {formatEuro(salary.differenza)}
                    </td>
                    <td style={{ padding: 12, fontSize: 12, color: '#6b7280' }}>{salary.note || '-'}</td>
                    <td style={{ padding: 12, textAlign: 'center' }}>
                      <button
                        onClick={() => handleDelete(salary.id)}
                        disabled={deleteMutation.isPending}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 16, opacity: 0.6 }}
                        title="Elimina"
                      >
                        🗑️
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
});

export default LibroUnicoTab;
