// Collaudo delle scritture SOLO sul backend tests.menu.e2e_server (in memoria).
const assert = require('node:assert/strict');
const { chromium } = require('../../frontend/node_modules/playwright-core');
const base = process.env.MENU_E2E_BASE_URL || 'http://127.0.0.1:8790';
if (!['127.0.0.1', 'localhost', '[::1]'].includes(new URL(base).hostname)) {
  throw new Error('Il collaudo con scritture richiede un backend locale isolato');
}

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM || '/usr/bin/chromium', args: ['--no-sandbox'] });
  try {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const salute = await (await context.request.get(`${base}/__fixture__/health`)).json();
    assert.equal(salute.fixture, 'menu-e2e-isolato', 'Backend fixture non riconosciuto: nessuna scrittura autorizzata');
    const reset = await (await context.request.post(`${base}/__fixture__/reset`)).json();
    assert.equal(reset.reset, true);
    await context.addInitScript(() => localStorage.setItem('admin_token', 'token-solo-fixture-isolata'));
    const admin = await context.newPage();
    const errors = [];
    admin.on('pageerror', e => errors.push(e.message));
    await admin.goto(`${base}/menu/admin`);
    await admin.getByRole('tab', { name: 'Menu e allergeni' }).waitFor();
    assert.equal(await admin.getByRole('tab', { name: 'Menu e allergeni' }).getAttribute('aria-selected'), 'true');
    await admin.getByRole('button', { name: 'Modifica Prodotto di prova', exact: true }).click();
    let dialog = admin.getByRole('dialog');
    await dialog.getByLabel('Nome Italiano').fill('Prodotto aggiornato');
    await dialog.getByLabel('Prezzo', { exact: true }).fill('5.25€');
    await dialog.getByRole('button', { name: 'Latte', exact: true }).click();
    await dialog.getByRole('button', { name: 'Uova', exact: true }).click();
    await dialog.getByRole('button', { name: 'Salva', exact: true }).click();
    await dialog.waitFor({ state: 'hidden' });

    const clienti = await context.newPage();
    clienti.on('pageerror', e => errors.push(e.message));
    await clienti.goto(`${base}/menu/carta/index.html`);
    await clienti.getByText('Menu di prova', { exact: true }).click();
    await clienti.locator('#cat-head-10').click();
    await clienti.getByText('Prodotto aggiornato', { exact: true }).waitFor();
    const item = clienti.locator('#item-100');
    assert.match(await item.locator('.price').textContent(), /5,25/);
    assert.equal(await item.locator('img[alt="Uova"]').count(), 1);
    assert.equal(await item.locator('img[alt="Latte"]').count(), 0);

    await admin.reload();
    await admin.getByRole('button', { name: 'Modifica Prodotto aggiornato', exact: true }).click();
    dialog = admin.getByRole('dialog');
    assert.equal(await dialog.getByLabel('Prezzo', { exact: true }).inputValue(), '5.25€');
    await dialog.getByRole('switch').click();
    await dialog.getByRole('button', { name: 'Salva', exact: true }).click();
    await dialog.waitFor({ state: 'hidden' });
    const carta = await (await context.request.get(`${base}/menu/api/menu/carta`)).json();
    assert.deepEqual(carta.items.map(i => i.id), [101]);
    await clienti.reload();
    await clienti.getByText('Menu di prova', { exact: true }).click();
    await clienti.locator('#cat-head-10').click();
    await clienti.getByText('Ricetta di prova', { exact: true }).waitFor();
    assert.equal(await clienti.locator('#item-100').count(), 0);

    await admin.getByRole('button', { name: 'Modifica Ricetta di prova', exact: true }).click();
    dialog = admin.getByRole('dialog');
    assert.equal(await dialog.getByLabel('Prezzo', { exact: true }).isDisabled(), true);
    assert.equal(await dialog.getByRole('button', { name: 'Salva', exact: true }).isDisabled(), true);
    await dialog.getByRole('button', { name: 'Annulla', exact: true }).click();
    for (const width of [360, 390, 768]) {
      for (const page of [admin, clienti]) {
        await page.setViewportSize({ width, height: 900 });
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
        assert.equal(overflow, false, `Overflow a ${width}px: ${page.url()}`);
      }
    }
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ esito: 'VERIFICATO', salvataggio: true, persistenza: true,
      carta_clienti: true, allergeni: true, pubblicazione: true, lotti_sola_lettura: true,
      larghezze: [360, 390, 768], errori_javascript: errors.length }));
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e.message); process.exitCode = 1; });
