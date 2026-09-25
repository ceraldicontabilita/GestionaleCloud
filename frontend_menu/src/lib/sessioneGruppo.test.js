import axios from 'axios';
import { entraDalGestionale, loginGestionale } from './sessioneGruppo';

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
});
