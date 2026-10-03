const csvCell = (value) => {
  const text = String(value ?? "");
  return /[;"\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};

export function buildPresenzeCsv({ giorni, righe }) {
  const header = ["Dipendente", ...Array.from({ length: giorni }, (_, i) => String(i + 1))];
  const rows = righe.map((r) => {
    const cells = Array.from({ length: giorni }, (_, i) => r.celle?.[i] || "");
    return [r.nome, ...cells];
  });
  // BOM + direttiva sep rendono la griglia immediatamente leggibile anche da
  // Excel quando il separatore di sistema non coincide con quello del file.
  return `\ufeffsep=;\r\n${[header, ...rows].map((row) => row.map(csvCell).join(";")).join("\r\n")}\r\n`;
}
