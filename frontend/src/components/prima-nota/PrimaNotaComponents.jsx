/**
 * Componenti ottimizzati per Prima Nota Salari
 * - React.memo per evitare re-render inutili
 * - useCallback per funzioni stabili
 */
import React, { memo, useCallback, useState } from 'react';
import { formatEuro } from '../../lib/utils';

// Costanti
const MESI_NOMI = [
  'Gennaio',
  'Febbraio',
  'Marzo',
  'Aprile',
  'Maggio',
  'Giugno',
  'Luglio',
  'Agosto',
  'Settembre',
  'Ottobre',
  'Novembre',
  'Dicembre',
];

const ANNI_ESCLUDIBILI = [2018, 2019, 2020, 2021, 2022];

/**
 * Bottoni per escludere anni dal calcolo - Memoizzato
 */
export const YearExclusionButtons = memo(function YearExclusionButtons({
  anniEsclusi,
  onToggleAnno,
  onReset,
}) {
  return (
    <div
      style={{
        display: 'flex',
        gap: 8,
        marginBottom: 20,
        alignItems: 'center',
        flexWrap: 'wrap',
        background: '#fef3c7',
        padding: 12,
        borderRadius: 8,
        border: '1px solid #f59e0b',
      }}
    >
      <span style={{ fontWeight: 'bold', color: '#92400e', marginRight: 8 }}>
        🚫 Escludi anni dal calcolo:
      </span>
      {ANNI_ESCLUDIBILI.map(anno => (
        <button
          key={anno}
          onClick={() => onToggleAnno(anno)}
          style={{
            padding: '6px 14px',
            borderRadius: 6,
            border: anniEsclusi.includes(anno) ? '2px solid #dc2626' : '1px solid #d1d5db',
            background: anniEsclusi.includes(anno) ? '#fee2e2' : 'white',
            color: anniEsclusi.includes(anno) ? '#dc2626' : '#374151',
            fontWeight: anniEsclusi.includes(anno) ? 'bold' : 'normal',
            cursor: 'pointer',
            textDecoration: anniEsclusi.includes(anno) ? 'line-through' : 'none',
          }}
        >
          {anno}
        </button>
      ))}
      {anniEsclusi.length > 0 && (
        <button
          onClick={onReset}
          style={{
            padding: '6px 12px',
            borderRadius: 6,
            border: 'none',
            background: '#6b7280',
            color: 'white',
            cursor: 'pointer',
            marginLeft: 8,
          }}
        >
          Reset
        </button>
      )}
    </div>
  );
});

/**
 * Card riepilogo totali - Memoizzato
 */
export const SummaryCard = memo(function SummaryCard({
  totals,
  anniEsclusi,
  selectedMonth,
  selectedYear,
  filtroDipendente,
  onOpenAggiustamento,
}) {
  const differenzaColor = totals.differenza >= 0 ? '#22c55e' : '#ef4444';

  return (
    <div
      style={{
        background: '#b45309',
        padding: 20,
        borderRadius: 12,
        color: 'white',
        marginBottom: 20,
      }}
    >
      <h3 style={{ margin: '0 0 12px 0' }}>
        📒 Prima Nota Salari - {selectedMonth ? MESI_NOMI[selectedMonth - 1] : 'Tutti i mesi'}{' '}
        {selectedYear || 'Tutti gli anni'}
        {filtroDipendente && ` - ${filtroDipendente}`}
      </h3>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
          gap: 16,
        }}
      >
        <div>
          <div style={{ fontSize: 12, opacity: 0.8 }}>Records</div>
          <div style={{ fontSize: 28, fontWeight: 'bold' }}>
            {totals.records}
            {anniEsclusi.length > 0 && (
              <span style={{ fontSize: 14, opacity: 0.7 }}> / {totals.totalRecords}</span>
            )}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 12, opacity: 0.8 }}>Totale Buste</div>
          <div style={{ fontSize: 24, fontWeight: 'bold' }}>{formatEuro(totals.totaleBuste)}</div>
        </div>
        <div>
          <div style={{ fontSize: 12, opacity: 0.8 }}>Totale Bonifici</div>
          <div style={{ fontSize: 24, fontWeight: 'bold' }}>
            {formatEuro(totals.totaleBonifici)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 12, opacity: 0.8 }}>
            {filtroDipendente ? 'Saldo Progressivo' : 'Differenza'}
            {anniEsclusi.length > 0 && (
              <span style={{ fontSize: 10, display: 'block' }}>
                (esclusi: {anniEsclusi.join(', ')})
              </span>
            )}
          </div>
          <div style={{ fontSize: 24, fontWeight: 'bold', color: differenzaColor }}>
            {formatEuro(totals.differenza)}
          </div>
        </div>
      </div>
      <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end' }}>
        <button
          onClick={onOpenAggiustamento}
          style={{
            padding: '10px 20px',
            background: '#15803d',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            fontWeight: 'bold',
            fontSize: 14,
          }}
        >
          ➕ Aggiustamento Saldo
        </button>
      </div>
    </div>
  );
});

/**
 * Filtri periodo - Memoizzato
 */
export const PeriodFilters = memo(function PeriodFilters({
  selectedMonth,
  selectedYear,
  filtroDipendente,
  dipendentiLista,
  onChangeMonth,
  onChangeYear,
  onChangeDipendente,
}) {
  return (
    <div
      style={{
        display: 'flex',
        gap: 12,
        marginBottom: 20,
        alignItems: 'center',
        flexWrap: 'wrap',
        background: '#f8fafc',
        padding: 16,
        borderRadius: 12,
      }}
    >
      <span style={{ fontWeight: 'bold', color: '#475569' }}>📅 Periodo:</span>
      <select
        value={selectedMonth}
        onChange={e => onChangeMonth(e.target.value ? parseInt(e.target.value) : '')}
        style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #e2e8f0' }}
      >
        <option value="">Tutti i mesi</option>
        {MESI_NOMI.map((m, i) => (
          <option key={i} value={i + 1}>
            {m}
          </option>
        ))}
      </select>

      <select
        value={selectedYear || ''}
        onChange={e => onChangeYear(e.target.value ? parseInt(e.target.value) : null)}
        style={{
          padding: '8px 12px',
          borderRadius: 6,
          border: '1px solid #e2e8f0',
          background: '#e3f2fd',
          fontWeight: 'bold',
        }}
      >
        <option value="">Tutti gli anni</option>
        {[2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026].map(y => (
          <option key={y} value={y}>
            {y}
          </option>
        ))}
      </select>

      <span style={{ fontWeight: 'bold', color: '#475569', marginLeft: 12 }}>👤 Dipendente:</span>
      <select
        value={filtroDipendente}
        onChange={e => onChangeDipendente(e.target.value)}
        style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #e2e8f0', minWidth: 180 }}
      >
        <option value="">Tutti i dipendenti</option>
        {dipendentiLista.map((d, i) => (
          <option key={i} value={d}>
            {d}
          </option>
        ))}
      </select>
    </div>
  );
});

/**
 * Bottoni azioni import/export - Memoizzato
 */
export const ActionButtons = memo(function ActionButtons({
  importing,
  onImportPaghe,
  onImportBonifici,
  onExport,
  onReset,
  onRefresh,
  onPulisciVuote,
  hasData,
  righeVuote = 0,
}) {
  const handleImportPaghe = useCallback(
    e => {
      const file = e.target.files[0];
      if (file) onImportPaghe(file);
      e.target.value = '';
    },
    [onImportPaghe]
  );

  const handleImportBonifici = useCallback(
    e => {
      const file = e.target.files[0];
      if (file) onImportBonifici(file);
      e.target.value = '';
    },
    [onImportBonifici]
  );

  return (
    <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
      <label
        style={{
          padding: '10px 20px',
          background: importing ? '#9ca3af' : '#15803d',
          color: 'white',
          borderRadius: 8,
          cursor: importing ? 'not-allowed' : 'pointer',
          fontWeight: 'bold',
        }}
      >
        {importing ? '⏳ Importando...' : '📊 Importa PAGHE (Excel)'}
        <input
          type="file"
          accept=".xlsx,.xls"
          onChange={handleImportPaghe}
          disabled={importing}
          style={{ display: 'none' }}
        />
      </label>

      <label
        style={{
          padding: '10px 20px',
          background: importing ? '#9ca3af' : '#1d4ed8',
          color: 'white',
          borderRadius: 8,
          cursor: importing ? 'not-allowed' : 'pointer',
          fontWeight: 'bold',
        }}
      >
        {importing ? '⏳ Importando...' : '🏦 Importa BONIFICI (Excel)'}
        <input
          type="file"
          accept=".xlsx,.xls"
          onChange={handleImportBonifici}
          disabled={importing}
          style={{ display: 'none' }}
        />
      </label>

      <button
        onClick={onExport}
        disabled={!hasData}
        style={{
          padding: '10px 20px',
          background: !hasData ? '#d1d5db' : '#15803d',
          color: 'white',
          border: 'none',
          borderRadius: 8,
          cursor: !hasData ? 'not-allowed' : 'pointer',
          fontWeight: 'bold',
        }}
      >
        📥 Esporta Excel
      </button>

      {onPulisciVuote && righeVuote > 0 && (
        <button
          onClick={onPulisciVuote}
          style={{
            padding: '10px 20px',
            background: '#b45309',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            fontWeight: 'bold',
          }}
        >
          🧹 Pulisci {righeVuote} Righe Vuote
        </button>
      )}

      <button
        onClick={onReset}
        style={{
          padding: '10px 20px',
          background: '#b91c1c',
          color: 'white',
          border: 'none',
          borderRadius: 8,
          cursor: 'pointer',
          fontWeight: 'bold',
        }}
      >
        🗑️ Reset Tutti i Dati
      </button>

      <button
        onClick={onRefresh}
        style={{
          padding: '10px 20px',
          background: '#475569',
          color: 'white',
          border: 'none',
          borderRadius: 8,
          cursor: 'pointer',
          fontWeight: 'bold',
        }}
      >
        🔄 Aggiorna
      </button>
    </div>
  );
});

/**
 * Tabella per performance con liste lunghe
 * Usa scroll nativo con rendering ottimizzato
 */
export const VirtualizedSalariTable = memo(function VirtualizedSalariTable({
  data,
  loading,
  onDelete,
  onEdit,
  height = 500,
}) {
  if (loading) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>⏳ Caricamento...</div>
    );
  }

  if (data.length === 0) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>📊</div>
        <div>Nessun dato disponibile</div>
        <div style={{ fontSize: 13, marginTop: 8 }}>Importa file PAGHE o BONIFICI per iniziare</div>
      </div>
    );
  }

  return (
    <div
      style={{
        background: 'white',
        borderRadius: 12,
        overflow: 'hidden',
        border: '1px solid #e2e8f0',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 1fr 80px',
          background: '#f8fafc',
          borderBottom: '2px solid #e2e8f0',
          padding: '12px',
          fontWeight: 'bold',
          fontSize: 13,
          color: '#475569',
        }}
      >
        <div>Dipendente</div>
        <div style={{ textAlign: 'center' }}>Mese</div>
        <div style={{ textAlign: 'center' }}>Anno</div>
        <div style={{ textAlign: 'right' }}>Busta</div>
        <div style={{ textAlign: 'right' }}>Bonifico</div>
        <div style={{ textAlign: 'right' }}>Progressivo</div>
        <div style={{ textAlign: 'center' }}>Azioni</div>
      </div>

      {/* Scrollable Table Body */}
      <div style={{ maxHeight: height, overflowY: 'auto' }}>
        {data.map((mov, index) => {
          const saldoColor = (mov.progressivo || 0) >= 0 ? '#22c55e' : '#ef4444';
          return (
            <div
              key={mov.id || index}
              style={{
                display: 'grid',
                gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 1fr 80px',
                alignItems: 'center',
                borderBottom: '1px solid #f1f5f9',
                background: index % 2 === 0 ? 'white' : '#f8fafc',
                padding: '12px',
              }}
            >
              <div style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {mov.dipendente}
              </div>
              <div style={{ textAlign: 'center' }}>{mov.mese_nome || mov.mese}</div>
              <div style={{ textAlign: 'center' }}>{mov.anno}</div>
              <div style={{ textAlign: 'right', color: '#dc2626' }}>
                {mov.importo_busta ? formatEuro(mov.importo_busta) : '-'}
              </div>
              <div style={{ textAlign: 'right', color: '#22c55e' }}>
                {mov.importo_bonifico ? formatEuro(mov.importo_bonifico) : '-'}
              </div>
              <div style={{ textAlign: 'right', fontWeight: 'bold', color: saldoColor }}>
                {formatEuro(mov.progressivo || 0)}
              </div>
              <div style={{ textAlign: 'center' }}>
                <button
                  onClick={() => onDelete(mov.id)}
                  style={{
                    padding: '4px 8px',
                    background: '#fee2e2',
                    color: '#dc2626',
                    border: 'none',
                    borderRadius: 4,
                    cursor: 'pointer',
                    fontSize: 12,
                  }}
                >
                  🗑️
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div
        style={{
          padding: 12,
          borderTop: '1px solid #e2e8f0',
          background: '#f8fafc',
          fontSize: 13,
          color: '#64748b',
        }}
      >
        📝 {data.length} record totali
      </div>
    </div>
  );
});

/**
 * Modal Aggiustamento Saldo - Memoizzato
 */
export const AggiustamentoModal = memo(function AggiustamentoModal({
  isOpen,
  onClose,
  onSubmit,
  dipendentiLista,
}) {
  const [formData, setFormData] = useState({
    dipendente: '',
    anno: new Date().getFullYear(),
    mese: new Date().getMonth() + 1,
    importo: '',
    descrizione: 'Aggiustamento saldo commercialista',
  });

  const handleSubmit = useCallback(async () => {
    if (!formData.dipendente) {
      alert('Seleziona un dipendente');
      return;
    }
    if (!formData.importo || formData.importo === 0) {
      alert('Inserisci un importo');
      return;
    }

    const success = await onSubmit(formData);
    if (success) {
      setFormData({
        dipendente: '',
        anno: new Date().getFullYear(),
        mese: new Date().getMonth() + 1,
        importo: '',
        descrizione: 'Aggiustamento saldo commercialista',
      });
      onClose();
    }
  }, [formData, onSubmit, onClose]);

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
    >
      <div
        style={{
          background: 'white',
          padding: 24,
          borderRadius: 12,
          width: '90%',
          maxWidth: 500,
          boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
        }}
      >
        <h3 style={{ margin: '0 0 20px 0' }}>➕ Aggiustamento Saldo</h3>
        <p style={{ fontSize: 13, color: '#64748b', marginBottom: 16 }}>
          Inserisci una riga di aggiustamento per allineare il saldo con il commercialista.
        </p>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold' }}>
            Dipendente *
          </label>
          <select
            value={formData.dipendente}
            onChange={e => setFormData({ ...formData, dipendente: e.target.value })}
            style={{ width: '100%', padding: 10, borderRadius: 6, border: '1px solid #e2e8f0' }}
          >
            <option value="">-- Seleziona dipendente --</option>
            {dipendentiLista.map(d => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
          <div>
            <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold' }}>Mese</label>
            <select
              value={formData.mese}
              onChange={e => setFormData({ ...formData, mese: parseInt(e.target.value) })}
              style={{ width: '100%', padding: 10, borderRadius: 6, border: '1px solid #e2e8f0' }}
            >
              {MESI_NOMI.map((m, i) => (
                <option key={i + 1} value={i + 1}>
                  {m}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold' }}>Anno</label>
            <select
              value={formData.anno}
              onChange={e => setFormData({ ...formData, anno: parseInt(e.target.value) })}
              style={{ width: '100%', padding: 10, borderRadius: 6, border: '1px solid #e2e8f0' }}
            >
              {[2023, 2024, 2025, 2026].map(y => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold' }}>
            Importo € *
            <span style={{ fontWeight: 'normal', color: '#64748b', fontSize: 12 }}>
              {' '}
              (positivo = aumenta saldo, negativo = diminuisce)
            </span>
          </label>
          <input
            type="number"
            step="0.01"
            value={formData.importo}
            onChange={e => setFormData({ ...formData, importo: e.target.value })}
            placeholder="Es: 150.00 o -150.00"
            style={{
              width: '100%',
              padding: 10,
              borderRadius: 6,
              border: '1px solid #e2e8f0',
              boxSizing: 'border-box',
            }}
          />
        </div>

        <div style={{ marginBottom: 20 }}>
          <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold' }}>
            Descrizione
          </label>
          <input
            type="text"
            value={formData.descrizione}
            onChange={e => setFormData({ ...formData, descrizione: e.target.value })}
            style={{
              width: '100%',
              padding: 10,
              borderRadius: 6,
              border: '1px solid #e2e8f0',
              boxSizing: 'border-box',
            }}
          />
        </div>

        <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            style={{
              padding: '10px 20px',
              background: '#f1f5f9',
              border: 'none',
              borderRadius: 6,
              cursor: 'pointer',
            }}
          >
            Annulla
          </button>
          <button
            onClick={handleSubmit}
            disabled={!formData.dipendente || !formData.importo}
            style={{
              padding: '10px 20px',
              background: !formData.dipendente || !formData.importo ? '#9ca3af' : '#10b981',
              color: 'white',
              border: 'none',
              borderRadius: 6,
              cursor: !formData.dipendente || !formData.importo ? 'not-allowed' : 'pointer',
              fontWeight: 'bold',
            }}
          >
            ✓ Inserisci Aggiustamento
          </button>
        </div>
      </div>
    </div>
  );
});

/**
 * Alert risultato import - Memoizzato
 */
export const ImportResultAlert = memo(function ImportResultAlert({ result, onClose }) {
  if (!result) return null;

  const isError = result.error;

  return (
    <div
      style={{
        padding: 16,
        marginBottom: 20,
        borderRadius: 12,
        background: isError ? '#ffebee' : '#e8f5e9',
        border: `1px solid ${isError ? '#ef5350' : '#4caf50'}`,
      }}
    >
      {isError ? (
        <div style={{ color: '#c62828' }}>❌ {result.message}</div>
      ) : (
        <>
          <div style={{ fontWeight: 'bold', color: '#2e7d32', marginBottom: 8 }}>
            ✅ {result.message}
          </div>
          <div style={{ display: 'flex', gap: 20 }}>
            <div>
              <strong>{result.created}</strong> creati
            </div>
            <div>
              <strong>{result.updated}</strong> aggiornati
            </div>
          </div>
        </>
      )}
      <button
        onClick={onClose}
        style={{
          marginTop: 8,
          fontSize: 12,
          cursor: 'pointer',
          background: 'transparent',
          border: 'none',
        }}
      >
        ✕ Chiudi
      </button>
    </div>
  );
});
