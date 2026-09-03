/**
 * printHtml.js — Utility sicura per stampa HTML in finestra separata.
 * Utilizza Blob URL per aprire la finestra di stampa in modo sicuro.
 *
 * @param {string} html - HTML completo da stampare
 * @param {object} [options]
 * @param {boolean} [options.autoPrint=true] - Avvia stampa automaticamente
 * @param {boolean} [options.autoClose=true] - Chiudi finestra dopo stampa
 * @param {string} [options.size] - Dimensioni finestra es. "width=800,height=600"
 */
import { toast } from "sonner";

export function printHtml(html, { autoPrint = true, autoClose = true, size = "width=900,height=700" } = {}) {
  // Inietta lo script di stampa automatica nell'HTML se non già presente
  let safeHtml = html;
  if (autoPrint && !safeHtml.includes("window.print()")) {
    const printScript = `<script>
      window.addEventListener("load", function() {
        window.print();
        ${autoClose ? 'window.addEventListener("afterprint", function() { window.close(); });' : ""}
      });
    <\/script>`;
    safeHtml = safeHtml.replace("</body>", printScript + "</body>");
    if (!safeHtml.includes(printScript)) {
      safeHtml += printScript;
    }
  }

  const blob = new Blob([safeHtml], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);

  const win = window.open(url, "_blank", size);
  if (!win) {
    URL.revokeObjectURL(url);
    toast.error("Popup bloccato — consenti i popup per questa pagina e riprova.");
    return;
  }

  // Pulizia URL dopo 2 minuti (tempo sufficiente per il caricamento e la stampa)
  setTimeout(() => URL.revokeObjectURL(url), 120_000);
}
