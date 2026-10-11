/** Regressione browser con righe popolate, modali, intestazioni multiple e controlli.
 * Non contatta API né database. Eseguire dopo le build delle quattro applicazioni.
 */
const {chromium}=require('playwright-core');
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..');
const engine=fs.readFileSync(path.join(root,'frontend_shared/tabelleCard.js'),'utf8').replace(/export /g,'');
function css(dir){return fs.readdirSync(dir,{recursive:true}).filter(n=>n.endsWith('.css')).map(n=>fs.readFileSync(path.join(dir,n),'utf8')).join('\n').replace(/@import[^;]+;/g,'');}
const apps=[
 ['ERP','frontend/dist','<div class="page-content">','</div>'],
 ['HR','frontend_hr/dist','<div class="dc-app"><div class="dc-content">','</div></div>'],
 ['Lotti','frontend_lotti/build','<main class="g-page">','</main>'],
 ['Menu','frontend_menu/build','<main class="container">','</main>'],
 ['B&B',null,'<main>','</main>'],
];
const dates=Array.from({length:31},(_,i)=>i+1);
const fixture=`<section class="dc-card" style="overflow-x:auto"><table class="dc-table dc-table--cards" style="min-width:1000px;white-space:nowrap"><thead>
<tr><th rowspan="2">Dipendente</th><th colspan="2">13ª 2026</th><th colspan="2">14ª 2026</th><th rowspan="2">Documento e azioni</th></tr>
<tr><th>Busta €</th><th>Pagato €</th><th>Busta €</th><th>Pagato €</th></tr></thead>
<tbody><tr><th>Persona di prova con nome completo lungo</th><td>1.234,56</td><td>900,00</td><td>1.000,00</td><td>500,00</td><td><div style="display:flex;gap:12px"><span class="truncate">Documento_con_identificativo_molto_lungo_senza_spazi_012345678901234567890123456789.pdf</span><button onclick="this.dataset.clicked='yes'">Apri documento completo</button></div><select aria-label="Dipendente"><option>Persona di prova con nome completo lungo</option></select><input aria-label="Importo" value="500,00"></td></tr></tbody>
<tfoot><tr><td colspan="4">Totale pagato</td><td>500,00</td><td><a href="#dettaglio">Dettagli</a></td></tr></tfoot></table></section>
<section class="dc-scroll-x" style="overflow-x:auto"><table class="dc-presenze-table" style="min-width:1500px"><thead><tr><th>Dipendente</th>${dates.map(d=>`<th>${d} ottobre</th>`).join('')}</tr></thead><tbody><tr><th>Persona prova</th>${dates.map(d=>`<td><button>${d} · Presente</button></td>`).join('')}</tr></tbody></table></section>
<section role="dialog" aria-label="Dettaglio"><table><tr><th>Voce</th><th>Valore</th></tr><tr><td>Causale</td><td>Descrizione completa senza omissioni</td></tr></table></section>`;
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM||(fs.existsSync('/usr/bin/chromium')?'/usr/bin/chromium':undefined),args:['--no-sandbox']});
 try{
 for(const [name,dir,start,end] of apps.filter(x=>!process.env.MOBILE_CARDS_APP||x[0]===process.env.MOBILE_CARDS_APP)){
  const styles=dir?css(path.join(root,dir)):fs.readFileSync(path.join(root,'frontend_colazioni/index.html'),'utf8').match(/<style>([\s\S]*?)<\/style>/)[1];
  const p=await browser.newPage({viewport:{width:390,height:844}});await p.route('**/*',r=>r.abort());
  await p.setContent(`<style>${styles}</style><style>body{margin:0}#test-host{padding:16px}#test-host>main,#test-host>.page-content,#test-host .dc-content{padding:0;margin:0;width:100%;max-width:100%}.dc-app{display:block}</style><div id="test-host">${start}${fixture}${end}</div>`);
  await p.addScriptTag({content:engine+'\navviaTabelleCard();'});await p.waitForTimeout(100);
  for(const width of [360,390,768]){
   await p.setViewportSize({width,height:844});await p.waitForTimeout(100);
   const m=await p.evaluate(()=>{
    const cells=[...document.querySelectorAll('tbody td,tbody th,tfoot td')].filter(e=>!e.closest('[data-card-header]'));
    return {width:document.documentElement.scrollWidth, tables:[...document.querySelectorAll('table')].map(t=>t.dataset.card),
     clipped:cells.filter(e=>{const r=e.getBoundingClientRect();return r.right>innerWidth+1||r.left<0||e.scrollWidth>e.clientWidth+1||r.height===0}).map(e=>e.textContent),
     scrollers:[...document.querySelectorAll('div,section,table')].filter(e=>e.scrollWidth>e.clientWidth+1&&['auto','scroll'].includes(getComputedStyle(e).overflowX)).length,
     labels:[...document.querySelectorAll('table:first-child tbody [data-label]')].map(e=>e.dataset.label)};
   });
   assert.ok(m.width<=width,`${name} ${width}: pagina larga ${m.width}`);
   assert.equal(m.scrollers,0,`${name} ${width}: contenitore con scroll orizzontale`);
   assert.deepEqual(m.clipped,[],`${name} ${width}: celle tagliate`);
   assert.ok(m.tables.every(x=>x==='si'),`${name}: tabelle non trasformate`);
   assert.ok(m.labels.includes('13ª 2026 · Busta €')&&m.labels.includes('14ª 2026 · Busta €'));
  }
  const button=p.getByRole('button',{name:'Apri documento completo'});await button.click();assert.equal(await button.getAttribute('data-clicked'),'yes');
  await p.getByLabel('Importo',{exact:true}).fill('600,00');assert.equal(await p.getByLabel('Importo',{exact:true}).inputValue(),'600,00');
  // Aggiornamento intestazione dopo caricamento dati + modal aggiunta dopo mount.
  await p.evaluate(()=>{document.querySelector('thead th').firstChild.textContent='Collaboratore';document.body.insertAdjacentHTML('beforeend','<div role="dialog"><table><thead><tr><th>Nuovo dettaglio</th></tr></thead><tbody><tr><td>Valore aggiunto dopo apertura</td></tr></tbody></table></div>')});
  await p.waitForTimeout(100);
  assert.equal(await p.locator('table').last().getAttribute('data-card'),'si');
  assert.equal(await p.locator('tbody th').first().getAttribute('data-label'),'Collaboratore');
  await p.setViewportSize({width:1280,height:900});assert.equal(await p.locator('table').first().evaluate(t=>getComputedStyle(t).display),'table');
  await p.close();console.log(`${name}: card complete a 360/390/768px, etichette, modali, controlli e ritorno desktop OK`);
 }
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
