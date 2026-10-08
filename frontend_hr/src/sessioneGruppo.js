import axios from 'axios'

// Sessione unica del gruppo: l'amministratore entra nel Gestionale una volta
// (PIN piu' MFA) e da li' apre HR senza un secondo PIN. Il backend legge il
// cookie del Gestionale e restituisce un token HR, mai quello dell'ERP
// (`app/services/group_session.py`). I dipendenti continuano a entrare col
// proprio nome e il proprio PIN: e' la loro identita', non un accesso admin.
const API = import.meta.env.VITE_API_URL || '/hr/api'

// 'ok' | 'nessuna_sessione' | 'non_disponibile'
export async function entraDalGestionale() {
  try {
    const r = await axios.get(`${API}/auth/session`, { withCredentials: true, timeout: 15000 })
    if (!r.data?.access_token) return 'nessuna_sessione'
    localStorage.setItem('pt_token', r.data.access_token)
    localStorage.setItem('pt_role', r.data.role || 'admin')
    localStorage.setItem('pt_name', r.data.name || 'Amministratore')
    return 'ok'
  } catch (error) {
    const stato = error?.response?.status
    return stato === 401 || stato === 403 ? 'nessuna_sessione' : 'non_disponibile'
  }
}

export function loginGestionale(destinazione = '/hr/dipendenti') {
  return `/login?next=${encodeURIComponent(destinazione)}`
}
