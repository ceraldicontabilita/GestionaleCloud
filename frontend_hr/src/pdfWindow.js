const PAGINA_ATTESA_PDF = `<!doctype html>
<html lang="it">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Caricamento PDF</title>
    <style>
      body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #f7f4ec; color: #234d3d; font: 16px system-ui, sans-serif; }
      p { padding: 24px; text-align: center; }
    </style>
  </head>
  <body><p>Caricamento PDF…</p></body>
</html>`;

/**
 * Apre subito una pagina blob isolata. Usare una scheda vuota dello stesso
 * origin permette alla SPA/PWA di ripristinare la propria rotta predefinita
 * mentre il PDF autenticato viene scaricato.
 */
export function apriFinestraPdfAttesa() {
  const attesaUrl = URL.createObjectURL(
    new Blob([PAGINA_ATTESA_PDF], { type: "text/html;charset=utf-8" }),
  );
  const finestra = window.open(attesaUrl, "_blank");
  if (finestra) finestra.opener = null;
  setTimeout(() => URL.revokeObjectURL(attesaUrl), 10000);
  return finestra;
}

export function mostraPdfNellaFinestra(finestra, pdfUrl, pagina = null) {
  if (!finestra || finestra.closed) return false;
  const destinazione = pagina ? `${pdfUrl}#page=${pagina}` : pdfUrl;
  finestra.location.replace(destinazione);
  return true;
}
