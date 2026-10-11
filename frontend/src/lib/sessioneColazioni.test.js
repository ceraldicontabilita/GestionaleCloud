import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

const html = readFileSync('../frontend_colazioni/index.html', 'utf8');
// Il VM esercita lo script classico della sessione. Il modulo delle card viene
// caricato dal browser e verificato dal collaudo Playwright delle cinque app.
const script = [...html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)]
  .filter(m => !/type=["']module["']/.test(m[1])).map(m => m[2]).join('\n');

function avvia(status = 200, sessione = null) {
  localStorage.clear();
  sessionStorage.clear();
  if (sessione) sessionStorage.setItem('sess', JSON.stringify(sessione));
  document.body.innerHTML = '<header><h1 id="ttl"></h1><span id="area_badge"></span><a id="gestionale" href="/" hidden>Gestionale</a><button id="back"></button></header><main id="app"></main>';
  const location = { hash: '#/titolare/fatture', href: 'https://erp.invalid/convenzioni/#/titolare/fatture', replace: vi.fn(), assign: vi.fn() };
  const fetch = vi.fn(async url => {
    if (url === '/api/colazioni/accesso') return { status, ok: status === 200, json: async () => ({ token: 'tk:fixture' }) };
    if (url === '/api/auth/logout' || url.endsWith('/rpc/bb_tit_logout')) return { status: 200, ok: true, json: async () => null, text: async () => 'null' };
    throw new Error('Richiesta inattesa nel test: ' + url);
  });
  const context = vm.createContext({ document, location, window: {}, localStorage, sessionStorage, fetch, URL, Date, console, setTimeout, clearTimeout, addEventListener: vi.fn() });
  vm.runInContext(script, context);
  context.tit = vi.fn(); // Il cruscotto non fa parte del login e non deve chiamare il DB.
  return { context, location, fetch };
}

afterEach(() => { document.body.innerHTML = ''; sessionStorage.clear(); localStorage.clear(); });

it('B&B diretto riusa il cookie centrale e mantiene la sezione richiesta', async () => {
  const { context, location, fetch } = avvia(200, { r: 'tit', p: 'tk:vecchia-sessione' });
  await waitFor(() => expect(context.tit).toHaveBeenCalledWith('fatture', undefined));
  expect(fetch).toHaveBeenCalledWith('/api/colazioni/accesso', { method: 'POST', credentials: 'same-origin' });
  expect(location.replace).not.toHaveBeenCalled();
  expect(document.getElementById('gestionale').hidden).toBe(false);
  expect(document.querySelector('input[type=password]')).toBeNull();
  expect(JSON.parse(sessionStorage.getItem('sess')).p).toBe('tk:fixture');
});

it('senza sessione rimanda al PIN centrale e conserva il ritorno dopo MFA', async () => {
  const { context, location } = avvia(401);
  await waitFor(() => expect(location.replace).toHaveBeenCalledWith('/login?next=' + encodeURIComponent('/convenzioni/#/titolare/fatture')));
  expect(context.tit).not.toHaveBeenCalled();
});

it.each([403, 503])('un rifiuto %s non crea un giro continuo di richieste PIN', async status => {
  const { context, location } = avvia(status);
  await waitFor(() => expect(document.body.textContent).toContain(status === 403 ? 'riservata all’amministratore'.replace('’', "'") : 'temporaneamente non disponibile'));
  expect(location.replace).not.toHaveBeenCalled();
  expect(context.tit).not.toHaveBeenCalled();
});

it('Esci dal B&B chiude sia la sessione B&B che quella centrale', async () => {
  const { context, location, fetch } = avvia();
  await waitFor(() => expect(context.tit).toHaveBeenCalled());
  await vm.runInContext('esci()', context);
  expect(fetch.mock.calls.some(([url]) => url.endsWith('/rpc/bb_tit_logout'))).toBe(true);
  expect(fetch).toHaveBeenCalledWith('/api/auth/logout', { method: 'POST', credentials: 'same-origin' });
  expect(location.assign).toHaveBeenCalledWith('/login');
  expect(JSON.parse(sessionStorage.getItem('sess'))).toBeNull();
});
