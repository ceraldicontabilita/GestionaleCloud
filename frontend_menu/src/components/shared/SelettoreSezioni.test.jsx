import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import SelettoreSezioni from './SelettoreSezioni';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// Forma di `/api/sezioni` (app/routers/sezioni.py).
const SEZIONI = [
  { id: 'gestionale', nome: 'Gestionale', percorso: '/', icona: 'Landmark' },
  { id: 'lotti', nome: 'Magazzino e HACCP', percorso: '/lotti/', icona: 'Boxes' },
  {
    id: 'menu', nome: 'Menu', percorso: '/menu/', icona: 'UtensilsCrossed',
    collegamenti: [
      { id: 'menu-clienti', nome: 'Menu clienti', percorso: '/menu/', icona: 'UtensilsCrossed' },
      { id: 'menu-gestione', nome: 'Gestione Menu', percorso: '/menu/admin', icona: 'Settings' },
    ],
  },
];

test('dalla gestione del Menu il selettore offre il Menu clienti', async () => {
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ sezioni: SEZIONI }) });
  const contenitore = document.createElement('div');
  const radice = createRoot(contenitore);
  await act(async () => {
    radice.render(<SelettoreSezioni sezioneCorrente="menu" paginaCorrente="menu-gestione" escludi={['gestionale']} />);
  });

  const voci = [...contenitore.querySelectorAll('a')].map((a) => [a.textContent, a.getAttribute('href')]);
  expect(voci).toEqual([['Menu clienti', '/menu/'], ['Magazzino e HACCP', '/lotti/']]);

  await act(async () => { radice.unmount(); });
  delete global.fetch;
});
