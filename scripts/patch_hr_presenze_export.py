#!/usr/bin/env python3
"""
Patch UI HR Presenze: rimuove il flusso concettualmente sbagliato di import PDF
come azione primaria e aggiunge export consulente CSV/PDF.

La patch e' testuale e conservativa: modifica solo HRPresenze.jsx.
Uso in ambiente repo:
    python3 scripts/patch_hr_presenze_export.py
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "frontend" / "src" / "pages" / "hr" / "HRPresenze.jsx"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        print(f"[SKIP] pattern non trovato: {label}")
        return text
    print(f"[FIX] {label}")
    return text.replace(old, new, 1)


def main() -> int:
    if not TARGET.exists():
        raise SystemExit(f"File non trovato: {TARGET}")

    text = TARGET.read_text(encoding="utf-8")
    original = text

    # 1) Aggiunge handler export dopo handleUploadPDF, mantenendo il vecchio handler
    # per retrocompatibilita' interna ma non piu' come CTA primaria.
    marker = "  // Stats\n"
    export_handler = """  const handleExportConsulente = async (format = 'csv') => {
    if (!mese) {
      setUploadResult({
        success: false,
        message: 'Seleziona un mese specifico prima di esportare per il consulente',
      });
      return;
    }

    setUploading(true);
    setUploadResult(null);
    try {
      const endpoint = format === 'pdf'
        ? '/api/attendance/genera-pdf-consulente'
        : '/api/attendance/export-consulente/csv';

      const response = format === 'pdf'
        ? await api.post(endpoint, { anno, mese }, { responseType: 'blob' })
        : await api.get(endpoint, { params: { anno, mese }, responseType: 'blob' });

      const blob = new Blob([response.data], {
        type: format === 'pdf' ? 'application/pdf' : 'text/csv;charset=utf-8',
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = format === 'pdf'
        ? `presenze_consulente_${anno}_${String(mese).padStart(2, '0')}.pdf`
        : `presenze_consulente_${anno}_${String(mese).padStart(2, '0')}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);

      setUploadResult({
        success: true,
        message: `Export ${format.toUpperCase()} consulente generato`,
      });
    } catch (err) {
      setUploadResult({
        success: false,
        message: err?.response?.data?.detail || 'Errore export consulente',
      });
    } finally {
      setUploading(false);
    }
  };

"""
    if "const handleExportConsulente" not in text:
        text = replace_once(text, marker, export_handler + marker, "aggiungi handler export consulente")

    # 2) Sostituisce il label che prima apriva input file PDF con due pulsanti export.
    old_block = """          <label
            data-testid=\"btn-upload-pdf\"
            style={{
              padding: '8px 16px',
              border: 'none',
              borderRadius: 8,
              fontSize: 13,
              background: uploading ? COLORS.border : '#1a40b5',
              color: 'white',
              cursor: uploading ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontWeight: 600,
            }}
          >
            <Calendar size={14} />
            {uploading ? 'Importazione…' : 'Importa PDF Libro Unico'}
            <input
              type=\"file\"
              accept=\".pdf\"
              onChange={handleUploadPDF}
              style={{ display: 'none' }}
              disabled={uploading}
            />
          </label>
"""
    new_block = """          <button
            data-testid=\"btn-export-consulente-csv\"
            onClick={() => handleExportConsulente('csv')}
            disabled={uploading || !mese}
            title={!mese ? 'Seleziona un mese specifico per esportare' : 'Esporta CSV per consulente'}
            style={{
              padding: '8px 16px',
              border: 'none',
              borderRadius: 8,
              fontSize: 13,
              background: uploading || !mese ? COLORS.border : '#1a40b5',
              color: 'white',
              cursor: uploading || !mese ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontWeight: 600,
            }}
          >
            <Calendar size={14} />
            Export CSV consulente
          </button>
          <button
            data-testid=\"btn-export-consulente-pdf\"
            onClick={() => handleExportConsulente('pdf')}
            disabled={uploading || !mese}
            title={!mese ? 'Seleziona un mese specifico per esportare' : 'Esporta PDF per consulente'}
            style={{
              padding: '8px 16px',
              border: 'none',
              borderRadius: 8,
              fontSize: 13,
              background: uploading || !mese ? COLORS.border : '#b8860b',
              color: 'white',
              cursor: uploading || !mese ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontWeight: 600,
            }}
          >
            <Calendar size={14} />
            Export PDF consulente
          </button>
"""
    text = replace_once(text, old_block, new_block, "sostituisci CTA import PDF con export consulente")

    # 3) Corregge copy pagina/empty state.
    text = text.replace(
        "Libro Unico del Lavoro — Dati importati dal consulente",
        "Presenze e giustificativi — Export mensile per consulente del lavoro",
    )
    text = text.replace(
        "Le presenze vengono importate dal Libro Unico del consulente.",
        "Inserisci presenze/giustificativi nel gestionale, poi esporta il mese per il consulente.",
    )
    text = text.replace("Importazione…", "Elaborazione…")

    if text == original:
        print("[DONE] Nessuna modifica: UI gia' aggiornata o pattern non presenti.")
        return 0

    TARGET.write_text(text, encoding="utf-8")
    print(f"[DONE] Aggiornato {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
