import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api', () => ({
  default: { get: vi.fn() },
  getAuthToken: () => localStorage.getItem('auth_token'),
}));

import api from '../api';
import { aggiornatoAlle, getConCopia } from './cacheGuscio';

describe('copia delle pagine nel browser', () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.setItem('auth_token', 'token-di-prova-abcdefghijklmnopqrstuvwxyz');
    api.get.mockReset();
  });

  it('la prima volta non c\'e\' copia; la seconda si vede subito, poi arriva la fresca', async () => {
    api.get.mockResolvedValueOnce({ data: { n: 1 } }).mockResolvedValueOnce({ data: { n: 2 } });
    const copie = [];
    await getConCopia('/api/x', undefined, d => copie.push(d));
    expect(copie).toEqual([]);
    const risposta = await getConCopia('/api/x', undefined, d => copie.push(d));
    expect(copie).toEqual([{ n: 1 }]);
    expect(risposta.data).toEqual({ n: 2 });
  });

  it('dopo un nuovo accesso la copia del token precedente non vale', async () => {
    api.get.mockResolvedValue({ data: { n: 1 } });
    await getConCopia('/api/x');
    localStorage.setItem('auth_token', 'un-altro-token-zyxwvutsrqponmlkjihgfedcba');
    const copie = [];
    await getConCopia('/api/x', undefined, d => copie.push(d));
    expect(copie).toEqual([]);
  });

  it('una richiesta fallita non cancella la copia e passa l\'errore', async () => {
    api.get.mockResolvedValueOnce({ data: { n: 1 } }).mockRejectedValueOnce(new Error('giu'));
    await getConCopia('/api/x');
    const copie = [];
    await expect(getConCopia('/api/x', undefined, d => copie.push(d))).rejects.toThrow('giu');
    expect(copie).toEqual([{ n: 1 }]);
  });

  it('dice l\'ora in italiano', () => {
    const adesso = new Date();
    expect(aggiornatoAlle(adesso.toISOString())).toMatch(/^aggiornato alle \d{2}:\d{2}$/);
    expect(aggiornatoAlle(null)).toBe('');
  });
});
