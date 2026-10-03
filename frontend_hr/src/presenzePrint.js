const DEFAULT_COLORS = {
  P: "#3d8168", AS: "#d35f4e", F: "#5b7a6b", PE: "#7d5526",
  M: "#f59e0b", R: "#8a9a5b", RS: "#9aa593", CH: "#6b7669",
  FNL: "#a6724a", X: "#495247",
};

const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

export function buildPresenzePrintHtml({ anno, meseLabel, giorni, righe, colors = DEFAULT_COLORS }) {
  const th = Array.from({ length: giorni }, (_, i) => `<th>${i + 1}</th>`).join("");
  const rows = righe.map((r) => {
    const cells = Array.from({ length: giorni }, (_, index) => r.celle[index] || "");
    return `<tr><td class="nm">${escapeHtml(r.nome)}</td>${cells.map((code) => (
      `<td style="background:${colors[code] || '#fff'};color:${code ? '#fff' : '#000'}">${escapeHtml(code)}</td>`
    )).join("")}</tr>`;
  }).join("");

  return `<!doctype html><html><head><meta charset="utf-8"><title>Presenze ${escapeHtml(meseLabel)} ${anno}</title>
    <style>@page{size:A4 landscape;margin:8mm} body{font-family:Arial,sans-serif;margin:0}
    h2{margin:0 0 6px;font-size:14px} table{border-collapse:collapse;width:100%;table-layout:fixed}
    th,td{border:1px solid #ccc;text-align:center;font-size:8px;padding:1px;overflow:hidden}
    td.nm,th.nm{text-align:left;width:110px;font-size:8px;padding:2px 4px;overflow:hidden;white-space:nowrap}
    thead th{background:#eee}</style></head>
    <body onload="setTimeout(function(){window.print()},250)"><h2>Presenze ${escapeHtml(meseLabel)} ${anno} — Ceraldi Group S.r.l.</h2>
    <table><thead><tr><th class="nm">Dipendente</th>${th}</tr></thead><tbody>${rows}</tbody></table>
    <p style="font-size:8px;color:#555;margin-top:6px">Legenda: P=Presente · AS=Assente · F=Ferie · PE=Permesso · M=Malattia · R=ROL · RS=Riposo · CH=Chiuso · FNL=Festività non lav.</p>
    </body></html>`;
}

