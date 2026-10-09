import { describe, expect, it, vi, beforeEach } from 'vitest';
import api from '../api';
import { conEstensione, scaricaOriginale } from './scaricaOriginale';

vi.mock('../api', () => ({ default: { get: vi.fn() } }));

describe('scaricaOriginale', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.URL.createObjectURL = vi.fn(() => 'blob:x');
    window.URL.revokeObjectURL = vi.fn();
  });

  it('usa il nome del file dato dal server', async () => {
    api.get.mockResolvedValue({
      data: new Blob(['%PDF'], { type: 'application/pdf' }),
      headers: { 'content-type': 'application/pdf', 'content-disposition': 'inline; filename="F24 aprile.pdf"' },
    });
    expect(await scaricaOriginale('/api/originale/f24/1', 'F24')).toBe('F24 aprile.pdf');
    expect(api.get).toHaveBeenCalledWith('/api/originale/f24/1', { responseType: 'blob' });
  });

  it('senza nome dal server prende l estensione dal tipo del file', async () => {
    api.get.mockResolvedValue({
      data: new Blob(['<html>'], { type: 'text/html' }),
      headers: { 'content-type': 'text/html; charset=utf-8' },
    });
    expect(await scaricaOriginale('/api/corrispettivi/1/view', 'Corrispettivo_18_09')).toBe('Corrispettivo_18_09.html');
  });

  it('non raddoppia un estensione gia presente', () => {
    expect(conEstensione('fattura_12.xml', 'application/pdf')).toBe('fattura_12.xml');
    expect(conEstensione('quietanza', 'application/pdf')).toBe('quietanza.pdf');
  });
});
