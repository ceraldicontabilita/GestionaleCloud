import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import axios from 'axios'
import { entraDalGestionale, loginGestionale } from './sessioneGruppo.js'

// Sessione unica: l'amministratore apre HR con la sessione del Gestionale,
// senza un secondo PIN; senza sessione non entra.
describe('ingresso amministratore dal Gestionale', () => {
  let memoria
  beforeEach(() => {
    memoria = {}
    vi.stubGlobal('localStorage', {
      getItem: (k) => (k in memoria ? memoria[k] : null),
      setItem: (k, v) => { memoria[k] = String(v) },
      removeItem: (k) => { delete memoria[k] },
    })
  })
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

  test('con la sessione riceve il token HR, mai quello dell ERP', async () => {
    const get = vi.spyOn(axios, 'get').mockResolvedValue({ data: { access_token: 'tok-hr', role: 'admin', name: 'Titolare' } })
    expect(await entraDalGestionale()).toBe('ok')
    expect(get).toHaveBeenCalledWith('/hr/api/auth/session', expect.objectContaining({ withCredentials: true }))
    expect(memoria).toEqual({ pt_token: 'tok-hr', pt_role: 'admin', pt_name: 'Titolare' })
  })

  test('senza sessione (401) non scrive niente', async () => {
    vi.spyOn(axios, 'get').mockRejectedValue({ response: { status: 401 } })
    expect(await entraDalGestionale()).toBe('nessuna_sessione')
    expect(memoria).toEqual({})
  })

  test('servizio giu: si distingue dal non autorizzato', async () => {
    vi.spyOn(axios, 'get').mockRejectedValue({ code: 'ECONNABORTED' })
    expect(await entraDalGestionale()).toBe('non_disponibile')
  })

  test('il login del Gestionale riporta alla gestione HR', () => {
    expect(loginGestionale()).toBe('/login?next=%2Fhr%2Fdipendenti')
  })
})
