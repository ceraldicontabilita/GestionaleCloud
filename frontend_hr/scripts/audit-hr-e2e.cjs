// Avvio fixture: python -m uvicorn tests.hr.e2e_server:app --host 127.0.0.1 --port 8791
// Esecuzione: cd frontend_hr && npm run test:e2e
const { chromium } = require('../../frontend/node_modules/playwright-core');
const fs = require('fs');
const assert = require('assert').strict;
const base = process.env.HR_E2E_BASE_URL || 'http://127.0.0.1:8791';
const origine = new URL(base);
if (!['127.0.0.1','localhost','[::1]'].includes(origine.hostname)
    || origine.username || origine.password || !['http:','https:'].includes(origine.protocol)) {
  throw new Error('Il collaudo con scritture richiede un backend locale isolato');
}
(async () => {
  // Un localhost potrebbe inoltrare verso un servizio reale: il marker
  // fixture e' obbligatorio PRIMA del login e di qualsiasi scrittura.
  const salute = await fetch(`${base}/__fixture__/health`);
  assert.equal(salute.status,200,'Backend fixture non riconosciuto');
  assert.equal((await salute.json()).fixture,'hr-e2e-isolato','Nessuna scrittura autorizzata su questo backend');
  const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM || '/usr/bin/chromium', args: ['--no-sandbox'] });
  try {
  const result = [];
  for (const width of [360,390,768]) {
    const context = await browser.newContext({ viewport: { width, height: 900 } });
    // Il browser puo' raggiungere solo il backend fixture locale.
    await context.route('**/*', async route => {
      const u = new URL(route.request().url());
      if (u.origin !== origine.origin) return route.abort();
      return route.continue();
    });
    const page = await context.newPage();
    const errors = [], forbidden = [];
    page.on('pageerror', e => errors.push(e.name));
    page.on('response', r => { if (r.status() >= 400) forbidden.push({ status:r.status(),path:new URL(r.url()).pathname }); });
    await page.goto(`${base}/hr/portale`);
    await page.getByRole('button', {name:'Persona',exact:true}).click();
    for (const digit of ['1','2','3','4']) await page.getByTestId(`pin-key-${digit}`).click();
    await page.getByTestId('pin-key-submit').click();
    await page.getByRole('button',{name:'Turni azienda',exact:true}).waitFor();
    await page.getByRole('button',{name:'Turni azienda',exact:true}).click();
    await page.locator('button[title^="Prova · Lunedì:"]').waitFor();
    assert.equal(new URL(page.url()).pathname,'/hr/dipendenti/turni');
    const networkWrite = page.waitForResponse(r => r.url().includes('/assegnazioni-turni') && r.request().method()==='POST');
    await page.locator('button[title^="Prova · Lunedì:"]').click();
    assert.equal((await networkWrite).status(),200);
    await page.waitForTimeout(350);
    // Lo stesso database fixture e' condiviso dalle tre viewport. Se il
    // ciclo e' arrivato al vuoto, il tap successivo assegna il primo turno.
    if ((await page.locator('button[title^="Prova · Lunedì:"]').innerText()).trim() === '—') {
      const nextWrite = page.waitForResponse(r => r.url().includes('/assegnazioni-turni') && r.request().method()==='POST');
      await page.locator('button[title^="Prova · Lunedì:"]').click();
      assert.equal((await nextWrite).status(),200);
    }
    const verification = await page.evaluate(async () => {
      const token = localStorage.getItem('pt_token');
      const headers = {Authorization:`Bearer ${token}`};
      const management = await fetch('/hr/api/dipendenti-cloud/assegnazioni-turni',{headers}).then(r=>r.json());
      const portal = await fetch('/hr/api/turni/azienda/settimana',{headers}).then(r=>r.json());
      const own = management.find(x=>x.dipendente_id==='dip-prova'&&x.giorno==='Lunedì');
      const visible = portal.assegnazioni.find(x=>x.dipendente_id==='dip-prova'&&x.giorno==='Lunedì');
      return {managementId:own?.turno_id,portalId:visible?.turno_id,
        overflow:document.documentElement.scrollWidth>innerWidth+1,
        smallButtons:[...document.querySelectorAll('button')].filter(x=>{const r=x.getBoundingClientRect();return r.width&&r.height&&(r.width<44||r.height<44)}).length};
    });
    assert.ok(verification.managementId);
    assert.equal(verification.portalId,verification.managementId);
    assert.equal(verification.overflow,false,`Overflow a ${width}px`);
    assert.equal(verification.smallButtons,0,`Controlli sotto44px a ${width}px`);
    assert.deepEqual(errors,[]);
    const before = await page.evaluate(()=>localStorage.getItem('pt_token'));
    const status = await page.evaluate(async () => (await fetch('/hr/api/dipendenti-cloud/documenti',{headers:{Authorization:`Bearer ${localStorage.getItem('pt_token')}`}})).status);
    assert.equal(status,403);
    assert.equal(await page.evaluate(()=>localStorage.getItem('pt_token')),before);
    result.push({width,login:'PASS',turnoPersistito:'PASS',relazioneGestionePortale:'PASS',...verification,jsErrors:errors,failedRequests:forbidden});
    assert.deepEqual(forbidden,[{status:403,path:'/hr/api/dipendenti-cloud/documenti'}]);
    await context.close();
  }
  if (process.env.HR_E2E_REPORT) fs.writeFileSync(process.env.HR_E2E_REPORT,JSON.stringify({environment:'fixture-in-memory',timestamp:new Date().toISOString(),result},null,2));
  console.log(JSON.stringify(result));
  } finally {
    await browser.close();
  }
})().catch(error=>{console.error(error.message);process.exitCode=1});
