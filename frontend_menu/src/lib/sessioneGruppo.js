import axios from 'axios';
import { pulisciSessioneGruppoBrowser } from '../../../frontend_shared/SessioneGruppo';

// Sessione unica del gruppo: l'amministratore entra nel Gestionale una volta
// (PIN piu' MFA) e da li' apre il Menu senza un secondo PIN. Il backend legge
// il cookie del Gestionale e restituisce un token del Menu, mai quello
// dell'ERP (`app/services/group_session.py`).
const BACKEND_URL = process.env.REACT_APP_MENU_BACKEND_URL;

export const DESTINAZIONE_ADMIN = '/menu/admin';

// 'ok' | 'nessuna_sessione' | 'non_disponibile'
export async function entraDalGestionale() {
  try {
    const r = await axios.get(`${BACKEND_URL}/api/qrcode/session`, { withCredentials: true, timeout: 15000 });
    if (!r.data?.success || !r.data?.token) return 'nessuna_sessione';
    localStorage.setItem('admin_token', r.data.token);
    return 'ok';
  } catch (error) {
    const stato = error?.response?.status;
    return stato === 401 || stato === 403 ? 'nessuna_sessione' : 'non_disponibile';
  }
}

export function loginGestionale(destinazione = DESTINAZIONE_ADMIN) {
  return `/login?next=${encodeURIComponent(destinazione)}`;
}

// «Esci» chiude la sessione di tutto il gruppo: con una sessione unica
// togliere solo il token del Menu non farebbe uscire nessuno, perche' la
// pagina d'ingresso lo ricreerebbe dal cookie del Gestionale.
export async function esciDalGruppo() {
  try {
    await axios.post('/api/auth/logout', {}, { withCredentials: true, timeout: 10000 });
  } catch {
    // La pulizia locale resta necessaria anche se il backend non risponde.
  }
  pulisciSessioneGruppoBrowser();
  window.location.assign('/login');
}
