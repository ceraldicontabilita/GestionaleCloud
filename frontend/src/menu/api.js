/**
 * Client API del modulo Menu (ex app Menu Ceraldi) dentro GestionaleCloud.
 *
 * Tutti gli URL del modulo vivono qui. Base composta ("/api" + "/menu") come
 * nel modulo HR: la guardia tests/test_frontend_api_contracts.py controlla i
 * soli URL letterali, i percorsi reali sono verificati da
 * tests/test_menu_modulo.py; scripts/frontend_api_refs.py ricompone le
 * costanti per le mappe endpoint.
 *
 * Sessione: token del gestionale (auth_token) oppure del portale dipendenti
 * (pt_token) per le schermate di banco. Il menu pubblico non ha sessione.
 */
import axios from 'axios';

const PUBBLICO = '/api' + '/menu/pubblico';
const STAFF = '/api' + '/menu/staff';
const ADMIN = '/api' + '/menu/admin';

export const menuApi = axios.create({ baseURL: '', timeout: 30000 });
menuApi.interceptors.request.use((cfg) => {
  const t = localStorage.getItem('auth_token') || localStorage.getItem('pt_token');
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});
menuApi.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401 && !String(err.config?.url || '').startsWith(PUBBLICO)) {
      if (localStorage.getItem('auth_token')) {
        localStorage.removeItem('auth_token');
        if (!location.pathname.startsWith('/login')) location.replace('/login');
      } else if (localStorage.getItem('pt_token')) {
        localStorage.removeItem('pt_token');
        localStorage.removeItem('pt_role');
        localStorage.removeItem('pt_name');
        if (!location.pathname.startsWith('/portale')) location.replace('/portale');
      }
    }
    return Promise.reject(err);
  }
);

/** Messaggio d'errore leggibile dalla risposta del backend. */
export const messaggioErrore = (err, fallback) =>
  err?.response?.data?.message || err?.response?.data?.detail || fallback;

function decodeRole(token) {
  try {
    return JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).role || null;
  } catch {
    return null;
  }
}

/** Ruolo della sessione corrente: quello del gestionale se c'e', altrimenti del portale. */
export function ruoloCorrente() {
  if (typeof window === 'undefined') return null;
  const t = localStorage.getItem('auth_token');
  if (t) return decodeRole(t);
  return localStorage.getItem('pt_role');
}

export const puoGestire = (ruolo) => ruolo === 'admin' || ruolo === 'operatore';
export const eAdmin = (ruolo) => ruolo === 'admin';
export const soloLettura = (ruolo) => ruolo === 'sola_lettura';

const data = (p) => p.then((r) => r.data);

// ---- pubblico (clienti)
export const caricaMenu = () => data(menuApi.get(`${PUBBLICO}/`));
export const caricaSalePubbliche = () => data(menuApi.get(`${PUBBLICO}/sale`));
export const inviaOrdine = (body) => data(menuApi.post(`${PUBBLICO}/ordini`, body));
export const statoOrdine = (id) => data(menuApi.get(`${PUBBLICO}/ordini/${id}`));
export const configQrPubblica = () => data(menuApi.get(`${PUBBLICO}/qrcode/config`));

// ---- banco (ordini, cassa, cucina, magazzino)
export const elencoOrdini = (params) => data(menuApi.get(`${STAFF}/ordini`, { params }));
export const ordineCassa = (body) => data(menuApi.post(`${STAFF}/ordini`, body));
export const aggiornaStatoOrdine = (id, status) => data(menuApi.patch(`${STAFF}/ordini/${id}/stato`, { status }));
export const aggiornaPagamentoOrdine = (id, paid, payment_method) =>
  data(menuApi.patch(`${STAFF}/ordini/${id}/pagamento`, { paid, payment_method }));
export const eliminaOrdine = (id) => data(menuApi.delete(`${STAFF}/ordini/${id}`));
export const elencoSale = () => data(menuApi.get(`${STAFF}/sale`));
export const articoliMagazzino = (params) => data(menuApi.get(`${STAFF}/magazzino/articoli`, { params }));
export const creaArticolo = (body) => data(menuApi.post(`${STAFF}/magazzino/articoli`, body));
export const aggiornaArticolo = (id, body) => data(menuApi.put(`${STAFF}/magazzino/articoli/${id}`, body));
export const eliminaArticolo = (id) => data(menuApi.delete(`${STAFF}/magazzino/articoli/${id}`));
export const movimentoArticolo = (id, body) => data(menuApi.post(`${STAFF}/magazzino/articoli/${id}/movimento`, body));
export const movimentiMagazzino = (params) => data(menuApi.get(`${STAFF}/magazzino/movimenti`, { params }));

// ---- gestione (admin/operatore)
export const prodottiPiatti = () => data(menuApi.get(`${ADMIN}/prodotti`));
export const creaCategoria = (body) => data(menuApi.post(`${ADMIN}/categorie`, body));
export const aggiornaCategoria = (id, body) => data(menuApi.put(`${ADMIN}/categorie/${id}`, body));
export const eliminaCategoria = (id) => data(menuApi.delete(`${ADMIN}/categorie/${id}`));
export const creaSottocategoria = (body) => data(menuApi.post(`${ADMIN}/sottocategorie`, body));
export const aggiornaSottocategoria = (id, body) => data(menuApi.put(`${ADMIN}/sottocategorie/${id}`, body));
export const eliminaSottocategoria = (id) => data(menuApi.delete(`${ADMIN}/sottocategorie/${id}`));
export const creaProdotto = (body) => data(menuApi.post(`${ADMIN}/prodotti`, body));
export const aggiornaProdotto = (id, body, subcategory_id) =>
  data(menuApi.put(`${ADMIN}/prodotti/${id}`, body, { params: subcategory_id ? { subcategory_id } : {} }));
export const eliminaProdotto = (id) => data(menuApi.delete(`${ADMIN}/prodotti/${id}`));
export const creaSala = (body) => data(menuApi.post(`${ADMIN}/sale`, body));
export const aggiornaSala = (id, body) => data(menuApi.put(`${ADMIN}/sale/${id}`, body));
export const eliminaSala = (id) => data(menuApi.delete(`${ADMIN}/sale/${id}`));
export const configQr = () => data(menuApi.get(`${ADMIN}/qrcode/config`));
export const salvaConfigQr = (body) => data(menuApi.put(`${ADMIN}/qrcode/config`, body));
export const elencoImmagini = () => data(menuApi.get(`${ADMIN}/immagini`));
export const caricaImmagine = (file) => {
  const form = new FormData();
  form.append('file', file);
  return data(menuApi.post(`${ADMIN}/immagini`, form, { headers: { 'Content-Type': 'multipart/form-data' } }));
};
export const eliminaImmagine = (id) => data(menuApi.delete(`${ADMIN}/immagini/${id}`));
export const esportaBackup = () => data(menuApi.get(`${ADMIN}/backup/esporta`));
export const ripristinaBackup = (json) => data(menuApi.post(`${ADMIN}/backup/ripristina`, json));
export const statoDati = () => data(menuApi.get(`${ADMIN}/stato-dati`));
export const avviaSincronizzazioneQromo = (body) => data(menuApi.post(`${ADMIN}/migrazione-qromo`, body));
export const statoSincronizzazioneQromo = (id) => data(menuApi.get(`${ADMIN}/migrazione-qromo/${id}`));

/** "3,50" / "3.50€" -> 3.5 */
export const prezzoNumero = (price) => parseFloat(String(price ?? '').replace('€', '').trim().replace(',', '.')) || 0;
export const euro = (n) => `€ ${(Number(n) || 0).toFixed(2)}`;
