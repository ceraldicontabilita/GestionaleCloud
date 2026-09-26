import axios from 'axios';
import { entraDalGestionale, esciDalGruppo, loginGestionale } from './sessioneGruppo';

// Sessione unica: l'amministrazione del Menu si apre con la sessione del
// Gestionale, non con un secondo PIN.
describe('ingresso amministratore Menu dal Gestionale', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => jest.restoreAllMocks());

  test('con la sessione salva il token del Menu', async () => {
    const get = jest.spyOn(axios, 'get').mockResolvedValue({ data: { success: true, token: 'tok-menu' } });
    expect(await entraDalGestionale()).toBe('ok');
    expect(get.mock.calls[0][0]).toMatch(/\/api\/qrcode\/session$/);
    expect(get.mock.calls[0][1]).toMatchObject({ withCredentials: true });
    expect(localStorage.getItem('admin_token')).toBe('tok-menu');
  });

  test('senza sessione non entra', async () => {
    jest.spyOn(axios, 'get').mockRejectedValue({ response: { status: 401 } });
    expect(await entraDalGestionale()).toBe('nessuna_sessione');
    expect(localStorage.getItem('admin_token')).toBeNull();
  });

  test('servizio giu: non e un accesso negato', async () => {
    jest.spyOn(axios, 'get').mockRejectedValue({ code: 'ECONNABORTED' });
    expect(await entraDalGestionale()).toBe('non_disponibile');
  });

  test('il login del Gestionale riporta alla gestione del menu', () => {
    expect(loginGestionale()).toBe('/login?next=%2Fmenu%2Fadmin');
  });

  test('Esci chiude la sessione del Gestionale e i token di tutte le app', async () => {
    ['auth_token', 'admin_token', 'pt_token', 'lotti_token'].forEach((k) => localStorage.setItem(k, 'x'));
    const fetchFinta = jest.fn().mockResolvedValue({ ok: true });
    global.fetch = fetchFinta;
    const posizione = window.location;
    delete window.location;
    window.location = { assign: jest.fn() };
    try {
      await esciDalGruppo();
      expect(fetchFinta).toHaveBeenCalledWith('/api/auth/logout', expect.objectContaining({ method: 'POST', credentials: 'same-origin' }));
      ['auth_token', 'admin_token', 'pt_token', 'lotti_token'].forEach((k) => expect(localStorage.getItem(k)).toBeNull());
      expect(window.location.assign).toHaveBeenCalledWith('/login');
    } finally {
      window.location = posizione;
      delete global.fetch;
    }
  });
});
