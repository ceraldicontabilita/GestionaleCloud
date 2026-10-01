import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import axios from 'axios'
import './App.jsx'

let memoria, replace
beforeEach(() => {
  memoria = { pt_token: 'sessione-prova', pt_role: 'responsabile_turni', pt_name: 'Persona prova' }
  replace = vi.fn()
  vi.stubGlobal('localStorage', {
    getItem: k => memoria[k] ?? null,
    removeItem: k => { delete memoria[k] },
  })
  vi.stubGlobal('location', { pathname: '/hr/dipendenti/turni', replace })
})
afterEach(() => { vi.unstubAllGlobals() })

async function richiestaRifiutata(status) {
  await expect(axios.get('/hr/api/dipendenti-cloud/documenti', {
    adapter: async config => { throw { config, response: { status } } },
  })).rejects.toMatchObject({ response: { status } })
}

test('una rotta vietata lascia attiva la sessione del responsabile turni', async () => {
  await richiestaRifiutata(403)
  expect(memoria.pt_token).toBe('sessione-prova')
  expect(memoria.pt_role).toBe('responsabile_turni')
  expect(replace).not.toHaveBeenCalled()
})

test('una sessione rifiutata dal server torna al login', async () => {
  await richiestaRifiutata(401)
  expect(memoria).toEqual({})
  expect(replace).toHaveBeenCalledWith('/hr/portale')
})
