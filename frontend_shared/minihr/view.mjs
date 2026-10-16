import {CORE_VERSION,buildMonthly,safeHref,START_MONTH} from './core.mjs';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=c=>new Intl.NumberFormat('it-IT',{style:'currency',currency:'EUR'}).format(c/100);
const monthName=m=>new Date(m+'-15T12:00:00Z').toLocaleDateString('it-IT',{month:'long',year:'numeric'});
const columns='<colgroup><col style="width:9%"><col style="width:18%"><col style="width:23%"><col style="width:9%"><col style="width:9%"><col style="width:12%"><col style="width:20%"></colgroup>';
const headings='<tr><th scope="col">Mese</th><th scope="col">Rapporto / cedolino</th><th scope="col">Cedolini e documenti</th><th scope="col" class="amount">Dovuto</th><th scope="col" class="amount">Pagato</th><th scope="col" class="amount">Saldo progressivo</th><th scope="col">Pagamenti / dettagli</th></tr>';
export class MiniHRFascicolo extends HTMLElement {
  constructor(){super();this.attachShadow({mode:'open'});this._data={employees:[]};this._selected='';this._from=START_MONTH;this._to=new Date().toISOString().slice(0,7);this._anomalies=false;}
  set data(value){this._data=value||{employees:[]};if(!this._data.employees.some(e=>e.id===this._selected))this._selected=this._data.employees[0]?.id||'';this.render();}
  get data(){return this._data;}
  connectedCallback(){this.render();}
  disconnectedCallback(){this._toolbarObserver?.disconnect();}
  bindStickyHeading(){
    this._toolbarObserver?.disconnect();
    const toolbar=this.shadowRoot.querySelector('.top'),body=this.shadowRoot.getElementById('bodyScroll'),head=this.shadowRoot.getElementById('headingScroll');
    // The sticky shell lives outside the horizontal scroll container, so
    // page scrolling, rather than a second vertical scrollbar, keeps it fixed.
    if(body&&head){
      body.addEventListener('scroll',()=>{if(head.scrollLeft!==body.scrollLeft)head.scrollLeft=body.scrollLeft;},{passive:true});
      head.addEventListener('scroll',()=>{if(body.scrollLeft!==head.scrollLeft)body.scrollLeft=head.scrollLeft;},{passive:true});
    }
    if(toolbar&&typeof ResizeObserver!=='undefined'){
      this._toolbarObserver=new ResizeObserver(()=>this.style.setProperty('--minihr-filter-height',toolbar.getBoundingClientRect().height+'px'));
      this._toolbarObserver.observe(toolbar);
    }
  }
  docLink(d,label){const href=safeHref(d.url);return href?`<a href="${esc(href)}" data-pdf target="_blank" rel="noopener">${esc(label||d.label||d.name||d.kind||'Apri documento')}</a>`:'<span>Documento non collegato</span>';}
  render(){
    const employee=this._data.employees.find(e=>e.id===this._selected),rows=employee?buildMonthly(employee,{from:this._from,to:this._to,today:this._data.today}):[],shown=this._anomalies?rows.filter(r=>['danger','warning'].includes(r.status.level)||r.anomalies.length):rows;
    const due=rows.reduce((a,r)=>a+r.dueCents,0),paid=rows.reduce((a,r)=>a+r.paidCents,0),docs=(d)=>this.docLink(d);
    this.shadowRoot.innerHTML=`<style>:host{display:block;color:#203c48;font:14px/1.35 system-ui;--minihr-filter-height:0px}*{box-sizing:border-box}
.top{display:flex;align-items:end;gap:6px;flex-wrap:wrap;position:sticky;top:var(--minihr-toolbar-top,0px);z-index:4;background:#f4f7f5;padding:7px 8px;border:1px solid #d4e1db;border-radius:7px}
label{display:flex;flex-direction:column;gap:3px;font-weight:600;font-size:12px}.top label:first-child{flex:1;min-width:190px}
select,input,button{font:inherit;font-size:13px;min-height:32px;padding:5px 7px;border:1px solid #b7c9c0;border-radius:5px;background:white}select{max-width:100%}button{cursor:pointer}input[type=month]{width:148px}
.summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin:6px 0}
.card{padding:7px 10px;border:1px solid #d6e2dc;border-radius:6px;background:white;font-size:12px}.card strong{display:block;font-size:20px;line-height:1.25;font-variant-numeric:tabular-nums}
.muted{color:#596e68;font-size:11px;line-height:1.35;margin:5px 0}.wrap{overflow-x:auto;overflow-y:hidden;max-width:100%;border:1px solid #dbe5df;border-top:0}
table{border-collapse:collapse;table-layout:fixed;width:100%;min-width:1100px;background:white}
.table-heading{position:sticky;top:calc(var(--minihr-toolbar-top,0px) + var(--minihr-filter-height,0px));z-index:3;background:#294d43;border:1px solid #dbe5df;border-bottom:0;box-shadow:0 2px 3px #183e3426}
.heading-scroll{overflow-x:auto;overflow-y:hidden;scrollbar-width:none}.heading-scroll::-webkit-scrollbar{display:none}
th,td{padding:7px 8px;border-bottom:1px solid #dbe5df;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#294d43;color:white;font-size:12px;line-height:1.3}td{font-size:13px}
.amount{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}.badge{display:inline-block;border-radius:5px;padding:3px 5px;background:#edf0ef;font-weight:600;font-size:12px}
.danger{background:#fbe5e1;color:#942f21}.warning{background:#fff1d6;color:#755116}.ok{background:#e1f1e8;color:#245c43}
a{color:#056692}a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,.wrap:focus-visible{outline:2px solid #056692;outline-offset:2px}small{display:block;margin:2px 0;font-size:11px}
.notice{padding:8px;border:1px solid #d4dfd7;border-radius:6px;margin:6px 0;background:#fffaf0}
.doc-list{display:grid;gap:3px}.doc-list>small{margin-top:-2px}details{margin-top:3px}summary{cursor:pointer}
.notes{font-size:12px;color:#536b61;margin:5px 0 7px}.notes p{margin:5px 0}h2{font-size:17px;margin:7px 0 5px}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);clip-path:inset(50%);white-space:nowrap;border:0}
@media(max-width:650px){.top{position:relative;top:auto}.top label:first-child{flex-basis:100%;min-width:0}.top label{flex:1;min-width:120px}.top input[type=month]{width:100%}.top button{flex:1}.table-heading{top:var(--minihr-toolbar-top,0px)}.summary{grid-template-columns:repeat(2,minmax(0,1fr))}.card strong{font-size:18px}th,td{padding:6px}}
@media print{.top{display:none}.table-heading{position:static}.wrap{overflow:visible}table{min-width:0}a{color:inherit}.heading-scroll{overflow:visible}}</style>
    <div class="top"><label>Dipendente<select id="employee">${this._data.employees.map(e=>`<option value="${esc(e.id)}" ${e.id===this._selected?'selected':''}>${esc(e.name)}</option>`).join('')}</select></label><label>Dal mese<input id="from" type="month" min="2022-12" value="${esc(this._from)}"></label><label>Al mese<input id="to" type="month" value="${esc(this._to)}"></label><button id="current">2023–oggi</button><button id="all">Da dicembre 2022</button><label><span>Vista</span><select id="mode"><option value="all">Tutti i mesi</option><option value="anomalies" ${this._anomalies?'selected':''}>Solo da controllare</option></select></label></div>
    <p class="muted">${esc(this._data.sourceLabel||'Vista documentale')} · sola lettura · saldo = pagamenti − cedolini.</p>
    ${employee?`<h2>${esc(employee.name)}</h2><div class="summary"><div class="card">Cedolini conteggiati<strong>${money(due)}</strong></div><div class="card">Pagamenti conteggiati<strong>${money(paid)}</strong></div><div class="card">Saldo del periodo<strong>${money(paid-due)}</strong></div><div class="card">Cedolini mancanti<strong>${rows.filter(r=>r.status.code==='missing').length}</strong></div></div>`:'<p class="notice">Nessun dipendente disponibile. Verificare l’accesso e il caricamento dei dati.</p>'}
    <details class="notes"><summary>Note sui conteggi e sulle fonti</summary><p>Nucleo comune ${CORE_VERSION}. Il saldo parte da zero nel periodo selezionato, senza riporto implicito.</p>${(this._data.notices||[]).map(n=>`<p>${esc(n)}</p>`).join('')}</details>
    <div class="table-heading"><div class="heading-scroll" id="headingScroll"><table aria-hidden="true">${columns}<thead>${headings}</thead></table></div></div><div class="wrap" id="bodyScroll" tabindex="0" role="region" aria-label="Movimenti mensili: scorri orizzontalmente per vedere tutte le colonne"><table>${columns}<caption class="sr-only">Movimenti mensili con saldo progressivo</caption><thead class="sr-only">${headings}</thead><tbody>${shown.map(r=>`<tr><td>${esc(monthName(r.month))}${r.excluded?'<small>Anno escluso dal conteggio</small>':''}</td><td><span class="badge ${r.status.level}">${esc(r.status.label)}</span><small>${esc(r.period.label)}</small>${r.anomalies.map(a=>`<small class="warning">${esc(a)}</small>`).join('')}</td><td><div class="doc-list">${r.slips.filter(s=>!s.placeholder).map(s=>`${this.docLink(s,s.type||'Cedolino')}<small>${(s.amountCents===null?'Importo non leggibile':money(s.amountCents))}${s.counted===false?' · escluso dal conteggio':''}</small>`).join('')}${r.documents.filter(d=>!r.slips.some(s=>s.url===d.url)).map(d=>`${this.docLink(d,d.type||d.label||'Documento acquisito')}<small>Fonte documentale: non aggiunta al saldo</small>`).join('')}${r.period.proofs.length?`<details><summary>Rapporto: ${r.period.proofs.length} riferimenti</summary>${r.period.proofs.map(d=>`<div>${docs(d)}<small>${esc(d.start||'')} ${d.end?' → '+esc(d.end):''}${d.effective?' · decorrenza '+esc(d.effective):''}${d.protocol?' · prot. '+esc(d.protocol):''}</small></div>`).join('')}</details>`:''}</div></td><td class="amount">${r.slips.some(s=>!s.placeholder)?money(r.dueCents):'—'}</td><td class="amount">${r.payments.length?money(r.paidCents):'—'}</td><td class="amount">${money(r.balanceCents)}</td><td>${r.payments.map(p=>`<div>${this.docLink(p,p.reference||p.type||'Pagamento')}<small>${esc(p.date)} · ${(p.amountCents===null?'Importo non leggibile':money(p.amountCents))}${p.counted?'':' · non conteggiato'}</small></div>`).join('')}${r.unverifiedCents?`<small>Da verificare: ${money(r.unverifiedCents)}</small>`:''}</td></tr>`).join('')||'<tr><td colspan="7">Nessun mese per questi filtri.</td></tr>'}</tbody></table></div>`;
    this.bindStickyHeading();
    for(const id of ['employee','from','to','mode'])this.shadowRoot.getElementById(id)?.addEventListener('change',e=>{if(id==='employee'){this._selected=e.target.value;this.dispatchEvent(new CustomEvent('minihr-employee',{detail:{id:this._selected},bubbles:true,composed:true}));}if(id==='from')this._from=e.target.value;if(id==='to')this._to=e.target.value;if(id==='mode')this._anomalies=e.target.value==='anomalies';this.render();});
    this.shadowRoot.getElementById('current')?.addEventListener('click',()=>{this._from='2023-01';this._to=(this._data.today||new Date().toISOString()).slice(0,7);this.render();});
    this.shadowRoot.getElementById('all')?.addEventListener('click',()=>{this._from=START_MONTH;this._to=(this._data.today||new Date().toISOString()).slice(0,7);this.render();});
    for(const a of this.shadowRoot.querySelectorAll('a[data-pdf]'))a.addEventListener('click',event=>{const custom=new CustomEvent('minihr-document',{detail:{href:a.getAttribute('href')},bubbles:true,composed:true,cancelable:true});if(!this.dispatchEvent(custom))event.preventDefault();});
  }
}
if(!customElements.get('minihr-fascicolo'))customElements.define('minihr-fascicolo',MiniHRFascicolo);
