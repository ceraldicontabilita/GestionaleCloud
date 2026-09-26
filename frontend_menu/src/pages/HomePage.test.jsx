import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import HomePage, { CollegamentiEsterni, leggiVista, hashVista } from './HomePage';
import MenuContext from '../context/MenuContext';
import { CartProvider } from '../context/CartContext';

// Le finestre Radix (filtro allergeni, carrello) non sono l'oggetto di questi
// test e Jest 27 non risolve i sottopercorsi `exports` dei loro pacchetti.
jest.mock('../components/AllergensModal', () => () => null);
jest.mock('../components/CartDrawer', () => () => null);

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const MENU = {
  menuCategories: [
    {
      id: 1, name: 'Bar', nameIT: 'Bar', image: '/bar.jpg',
      subcategories: [
        {
          id: 11, name: 'Coffee', nameIT: 'Caffetteria', image: null,
          items: [{ id: 101, name: 'Espresso', nameIT: 'Caffè', price: '1,20', allergens: [] }],
        },
      ],
    },
  ],
  allergensList: [],
  loading: false,
  error: null,
  refreshMenu: () => {},
};

let contenitore;
let radice;

async function monta(elemento) {
  contenitore = document.createElement('div');
  document.body.appendChild(contenitore);
  radice = createRoot(contenitore);
  await act(async () => { radice.render(elemento); });
}

async function montaHome() {
  await monta(
    <MenuContext.Provider value={MENU}>
      <CartProvider>
        <HomePage />
      </CartProvider>
    </MenuContext.Provider>
  );
}

async function smonta() {
  await act(async () => { radice.unmount(); });
  contenitore.remove();
}

beforeEach(() => {
  localStorage.clear();
  window.history.replaceState(null, '', '/');
  jest.spyOn(axios, 'get').mockResolvedValue({ data: [] });
});

afterEach(async () => {
  await smonta();
  jest.restoreAllMocks();
});

test('parte in italiano', async () => {
  await montaHome();
  expect(contenitore.textContent).toContain('Filtro allergeni');
  expect(contenitore.querySelector('[data-testid="lingua-it"]').getAttribute('aria-pressed')).toBe('true');
});

test('rispetta la lingua salvata', async () => {
  localStorage.setItem('menu_lingua', 'en');
  await montaHome();
  expect(contenitore.textContent).toContain('Allergens filter');
});

test('categorie e sottocategorie sono veri pulsanti e cambiano la vista nella pagina', async () => {
  await montaHome();
  const categoria = contenitore.querySelector('[data-testid="category-1"]');
  expect(categoria.tagName).toBe('BUTTON');
  expect(categoria.getAttribute('type')).toBe('button');

  await act(async () => { categoria.click(); });
  expect(window.location.hash).toBe('#categoria=1');
  expect(document.querySelector('[role="dialog"]')).toBeNull();
  const sotto = contenitore.querySelector('[data-testid="subcategory-11"]');
  expect(sotto.tagName).toBe('BUTTON');

  await act(async () => { sotto.click(); });
  expect(window.location.hash).toBe('#categoria=1&sottocategoria=11');
  expect(contenitore.querySelector('[data-testid="vista-prodotti"]').textContent).toContain('Caffè');
  expect(contenitore.textContent).toContain('1,20');

  await act(async () => { contenitore.querySelector('[data-testid="menu-indietro"]').click(); });
  expect(contenitore.querySelector('[data-testid="vista-sottocategorie"]')).not.toBeNull();

  await act(async () => { contenitore.querySelector('[data-testid="menu-indietro"]').click(); });
  expect(window.location.hash).toBe('');
  expect(contenitore.querySelector('[data-testid="vista-categorie"]')).not.toBeNull();
});

test('il tasto indietro del browser torna al livello precedente', async () => {
  await montaHome();
  await act(async () => { contenitore.querySelector('[data-testid="category-1"]').click(); });
  await act(async () => {
    window.history.replaceState(null, '', '/');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  expect(contenitore.querySelector('[data-testid="vista-categorie"]')).not.toBeNull();
});

test('un hash aperto da link riporta alla sezione', async () => {
  window.history.replaceState(null, '', '/#categoria=1&sottocategoria=11');
  await montaHome();
  expect(contenitore.querySelector('[data-testid="vista-prodotti"]')).not.toBeNull();
});

test('il «Rifiuto» sui cookie resta registrato dopo una nuova visita', async () => {
  await montaHome();
  const rifiuto = [...contenitore.querySelectorAll('[data-testid="banner-cookie"] button')]
    .find((b) => b.textContent === 'Rifiuto');
  await act(async () => { rifiuto.click(); });
  expect(contenitore.querySelector('[data-testid="banner-cookie"]')).toBeNull();
  expect(JSON.parse(localStorage.getItem('menu_consenso_cookie')).scelta).toBe('rifiutato');

  await smonta();
  await montaHome();
  expect(contenitore.querySelector('[data-testid="banner-cookie"]')).toBeNull();
});

test('i collegamenti non configurati non si mostrano', async () => {
  await montaHome();
  expect(contenitore.querySelector('[data-testid="collegamenti-esterni"]')).toBeNull();
  expect(contenitore.querySelector('a[href="#"]')).toBeNull();
});

test('un collegamento configurato si mostra, gli altri no', async () => {
  await monta(
    <CollegamentiEsterni
      language="it"
      collegamenti={{ facebook: 'https://www.facebook.com/esempio', instagram: '#', cookiePolicy: null, privacyPolicy: '' }}
    />
  );
  const link = contenitore.querySelectorAll('a');
  expect(link).toHaveLength(1);
  expect(link[0].getAttribute('href')).toBe('https://www.facebook.com/esempio');
  expect(link[0].getAttribute('aria-label')).toBe('Facebook');
});

test('hash della vista: andata e ritorno', () => {
  expect(hashVista({ categoriaId: 3, sottocategoriaId: 12 })).toBe('#categoria=3&sottocategoria=12');
  expect(hashVista(null)).toBe('');
  expect(leggiVista('#categoria=3&sottocategoria=12')).toEqual({ categoriaId: '3', sottocategoriaId: '12' });
});
