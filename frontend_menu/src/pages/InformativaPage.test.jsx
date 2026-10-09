import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import InformativaPage from './InformativaPage';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let contenitore;
let radice;

async function monta(elemento) {
  contenitore = document.createElement('div');
  document.body.appendChild(contenitore);
  radice = createRoot(contenitore);
  await act(async () => { radice.render(elemento); });
  await act(async () => { await Promise.resolve(); });
}

afterEach(async () => {
  await act(async () => { radice.unmount(); });
  contenitore.remove();
  jest.restoreAllMocks();
  localStorage.clear();
});

test('privacy: il titolare arriva dall anagrafica azienda, non dal codice', async () => {
  const get = jest.spyOn(axios, 'get').mockResolvedValue({
    data: { ragione_sociale: 'Prova S.r.l.', indirizzo: 'Via Uno 1', partita_iva: '01234567890', email: '', telefono: '' },
  });
  await monta(<InformativaPage tipo="privacy" />);
  expect(get.mock.calls[0][0]).toMatch(/\/api\/menu\/titolare$/);
  expect(contenitore.querySelector('[data-testid="titolare"]').textContent).toContain('Prova S.r.l.');
  expect(contenitore.textContent).toContain('01234567890');
  expect(contenitore.textContent).toContain('Informativa sulla privacy');
});

test('titolare non leggibile: lo dice, non lo inventa', async () => {
  jest.spyOn(axios, 'get').mockRejectedValue(new Error('giu'));
  await monta(<InformativaPage tipo="cookie" />);
  expect(contenitore.querySelector('[data-testid="titolare"]')).toBeNull();
  expect(contenitore.textContent).toContain('chiedili al personale');
  // la politica elenca le due sole chiavi che il menu salva davvero
  expect(contenitore.textContent).toContain('menu_lingua');
  expect(contenitore.textContent).toContain('menu_consenso_cookie');
});
