import React, { useState } from 'react';
import * as XLSX from 'xlsx';

/**
 * Componente per esportare dati in CSV o Excel
 *
 * @param {Array} data - Array di oggetti da esportare
 * @param {Array} columns - Array di {key, label} per le colonne
 * @param {string} filename - Nome del file (senza estensione)
 * @param {string} format - 'csv' o 'excel' (default: csv)
 */
export function ExportButton({
  data = [],
  columns = [],
  filename = 'export',
  format = 'csv',
  disabled = false,
  size = 'md',
  variant = 'default',
}) {
  const [exporting, setExporting] = useState(false);

  const exportToCSV = () => {
    if (!data || data.length === 0) {
      alert('Nessun dato da esportare');
      return;
    }

    setExporting(true);

    try {
      // Header
      const headers =
        columns.length > 0 ? columns.map(c => c.label || c.key) : Object.keys(data[0]);

      const keys = columns.length > 0 ? columns.map(c => c.key) : Object.keys(data[0]);

      // Rows
      const rows = data.map(row =>
        keys
          .map(key => {
            let value = row[key];

            // Formatta valori
            if (value === null || value === undefined) return '';
            if (typeof value === 'object') return JSON.stringify(value);
            if (typeof value === 'number') return value.toString().replace('.', ',');

            // Escape virgolette e virgole
            const strValue = String(value);
            if (strValue.includes(',') || strValue.includes('"') || strValue.includes('\n')) {
              return `"${strValue.replace(/"/g, '""')}"`;
            }
            return strValue;
          })
          .join(';')
      );

      // CSV content con BOM per Excel
      const BOM = '\uFEFF';
      const csvContent = BOM + [headers.join(';'), ...rows].join('\n');

      // Download
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${filename}_${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Errore export:', error);
      alert("Errore durante l'esportazione");
    } finally {
      setExporting(false);
    }
  };

  const exportToExcel = async () => {
    if (!data || data.length === 0) {
      alert('Nessun dato da esportare');
      return;
    }

    setExporting(true);

    try {
      const headers =
        columns.length > 0 ? columns.map(c => c.label || c.key) : Object.keys(data[0]);

      const keys = columns.length > 0 ? columns.map(c => c.key) : Object.keys(data[0]);

      const wsData = [
        headers,
        ...data.map(row =>
          keys.map(key => {
            const val = row[key];
            // Formatta numeri
            if (typeof val === 'number') return val;
            if (val === null || val === undefined) return '';
            return String(val);
          })
        ),
      ];

      const ws = XLSX.utils.aoa_to_sheet(wsData);

      // Auto-width colonne
      const colWidths = headers.map((h, i) => {
        const maxLen = Math.max(
          h.length,
          ...wsData.slice(1).map(row => String(row[i] || '').length)
        );
        return { wch: Math.min(maxLen + 2, 50) };
      });
      ws['!cols'] = colWidths;

      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, 'Dati');
      XLSX.writeFile(wb, `${filename}_${new Date().toISOString().split('T')[0]}.xlsx`);
    } catch (error) {
      console.error('Errore export Excel:', error);
      alert("Errore durante l'esportazione Excel");
    } finally {
      setExporting(false);
    }
  };

  const handleExport = () => {
    if (format === 'excel') {
      exportToExcel();
    } else {
      exportToCSV();
    }
  };

  const sizeStyles = {
    sm: { padding: '6px 12px', fontSize: 12 },
    md: { padding: '8px 16px', fontSize: 13 },
    lg: { padding: '10px 20px', fontSize: 14 },
  };

  const variantStyles = {
    default: { background: '#f1f5f9', color: '#475569', border: '1px solid #e2e8f0' },
    primary: { background: '#3b82f6', color: 'white', border: 'none' },
    success: { background: '#10b981', color: 'white', border: 'none' },
  };

  return (
    <button
      onClick={handleExport}
      disabled={disabled || exporting || !data || data.length === 0}
      data-testid="export-button"
      style={{
        ...sizeStyles[size],
        ...variantStyles[variant],
        borderRadius: 6,
        fontWeight: 600,
        cursor: disabled || exporting ? 'not-allowed' : 'pointer',
        opacity: disabled || exporting ? 0.6 : 1,
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        transition: 'all 0.2s',
      }}
    >
      {exporting ? (
        <>⏳ Esportazione...</>
      ) : (
        <>
          📥 {format === 'excel' ? 'Excel' : 'CSV'}
          {data && data.length > 0 && (
            <span
              style={{
                background: 'rgba(0,0,0,0.1)',
                padding: '2px 6px',
                borderRadius: 4,
                fontSize: '0.85em',
              }}
            >
              {data.length}
            </span>
          )}
        </>
      )}
    </button>
  );
}

/**
 * Dropdown per scegliere formato export
 */
export function ExportDropdown({ data, columns, filename, disabled = false }) {
  const [open, setOpen] = useState(false);

  return (
    <div style={{ position: 'relative', display: 'inline-block' }}>
      <button
        onClick={() => setOpen(!open)}
        disabled={disabled || !data || data.length === 0}
        data-testid="export-dropdown"
        style={{
          padding: '8px 16px',
          background: '#f1f5f9',
          color: '#475569',
          border: '1px solid #e2e8f0',
          borderRadius: 6,
          fontWeight: 600,
          cursor: disabled ? 'not-allowed' : 'pointer',
          opacity: disabled ? 0.6 : 1,
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        📥 Esporta ▼
      </button>

      {open && (
        <>
          <div style={{ position: 'fixed', inset: 0, zIndex: 99 }} onClick={() => setOpen(false)} />
          <div
            style={{
              position: 'absolute',
              top: '100%',
              right: 0,
              marginTop: 4,
              background: 'white',
              border: '1px solid #e2e8f0',
              borderRadius: 8,
              boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
              zIndex: 100,
              minWidth: 150,
              overflow: 'hidden',
            }}
          >
            <ExportButton
              data={data}
              columns={columns}
              filename={filename}
              format="csv"
              size="sm"
              style={{ width: '100%', borderRadius: 0, border: 'none' }}
            />
            <div style={{ height: 1, background: '#e2e8f0' }} />
            <ExportButton
              data={data}
              columns={columns}
              filename={filename}
              format="excel"
              size="sm"
              style={{ width: '100%', borderRadius: 0, border: 'none' }}
            />
          </div>
        </>
      )}
    </div>
  );
}

export default ExportButton;
