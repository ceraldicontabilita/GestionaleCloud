// Avviso in basso, stile Backoffice — estratto da BackofficeView.jsx
// (refactor 25/07/2026): stesso markup e stessi colori di prima.
export const toast = (msg, tipo = "ok") => {
  const div = document.createElement("div");
  div.textContent = msg;
  div.style.cssText = `
    position:fixed;bottom:24px;left:50%;transform:translateX(-50%);
    padding:10px 20px;border-radius:12px;font-weight:700;font-size:14px;
    color:#fff;z-index:9999;animation:fadeUp .3s ease;
    background:${tipo === "ok" ? "var(--success)" : tipo === "err" ? "var(--danger)" : "var(--warning)"};
    box-shadow:0 4px 20px rgba(0,0,0,.2);font-family:var(--font);
  `;
  document.body.appendChild(div);
  setTimeout(() => div.remove(), 2800);
};
