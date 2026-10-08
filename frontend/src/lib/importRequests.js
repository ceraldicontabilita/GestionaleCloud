import api from '../api';

const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
let lastRequest = 0;

// Import sequenziale sotto il limite del servizio. Il 429 e' un rifiuto prima
// dell'handler: si attende sullo stesso file, senza fallire tutta la selezione.
export async function inviaFileImport(url, formData, config, onWait = () => {}) {
  for (let attempt = 0; ; attempt++) {
    await wait(Math.max(0, 450 - (Date.now() - lastRequest)));
    lastRequest = Date.now();
    try {
      return await api.post(url, formData, config);
    } catch (error) {
      if (error.response?.status !== 429 || attempt >= 3) throw error;
      const header = error.response.headers?.['retry-after'];
      const parsed = Number(header);
      const delay = header && Number.isFinite(parsed) ? parsed * 1000
        : header && Number.isFinite(Date.parse(header)) ? Date.parse(header) - Date.now() : 61000;
      const seconds = Math.ceil(Math.max(1000, Math.min(300000, delay)) / 1000);
      for (let remaining = seconds; remaining > 0; remaining--) {
        onWait(remaining);
        await wait(1000);
      }
      onWait(0);
    }
  }
}
