const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Errore server')
  }
  return res.json()
}

export const api = {
  getDipendenti: (stato) => request(`/dipendenti${stato ? `?stato=${stato}` : ''}`),
  getDipendente: (id) => request(`/dipendenti/${id}`),
  creaDipendente: (data) => request('/dipendenti', { method: 'POST', body: JSON.stringify(data) }),
  aggiornaDipendente: (id, data) => request(`/dipendenti/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  getPignoramenti: (dipId) => request(`/dipendenti/${dipId}/pignoramenti`),
  aggiungiPignoramento: (dipId, data) => request(`/dipendenti/${dipId}/pignoramenti`, { method: 'POST', body: JSON.stringify(data) }),
  aggiornaStatoPignoramento: (dipId, pigId, stato) => request(`/dipendenti/${dipId}/pignoramenti/${pigId}/stato`, { method: 'PUT', body: JSON.stringify({ stato }) }),
  generaDichiarazione: (dipId, pigId) => request(`/dipendenti/${dipId}/pignoramenti/${pigId}/genera-dichiarazione`, { method: 'POST' }),
}
