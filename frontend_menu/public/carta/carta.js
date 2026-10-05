const CC_PARAMS=new URLSearchParams(location.search),CC_BB=(CC_PARAMS.get('bb')||'').trim(),CC_GIORNO=CC_PARAMS.get('giorno')||'',CC_CANALE=['sala','delivery'].includes(CC_PARAMS.get('canale'))?CC_PARAMS.get('canale'):'',CC_COD=(CC_PARAMS.get('p')||'').trim();
const CC_DATI=CC_BB?fetch('/api/colazioni/menu-ospite/catalogo',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({codice:CC_BB,giorno:CC_GIORNO})}):fetch('../api/menu/carta'+(CC_CANALE?'?canale='+CC_CANALE:''),{cache:'no-store'});
CC_DATI.then(async r=>{if(!r.ok){const j=await r.json().catch(()=>({}));throw new Error(j.detail||r.status)}return r.json()}).then(D=>{
const TPL=JSON.parse(document.getElementById('tpl').textContent);
const ICONS=JSON.parse(document.getElementById('icons').textContent);
const IMG=new Proxy({},{get:(_,k)=>k}); // le foto sono gia' URL
const AL={celery:'Sedano',clams:'Molluschi',dioxide:'Solfiti',egg:'Uova',fish:'Pesce',gluten:'Glutine',lupins:'Lupini',milk:'Latte',mustard:'Senape',peanuts:'Arachidi',sesame:'Sesamo',shellfish:'Crostacei',soia:'Soia',wot:'Frutta a guscio',almond:'Mandorle',barley:'Orzo',brazil_nuts:'Noci del Brasile',cashew:'Anacardi',hazelnuts:'Nocciole',macadamia:'Macadamia',oats:'Avena',pecan:'Noci pecan',pistachios:'Pistacchi',rye:'Segale',spelt:'Farro',walnuts:'Noci',wheat:'Grano',kamut:'Kamut',alcohol:'Alcol',halal:'Halal',kosher:'Kosher',vegan:'Vegano',vegetarian:'Vegetariano',no_allergens:'Nessun allergene',gluten_free:'Senza glutine',bio:'Biologico',spicy:'Piccante',frost:'Surgelato',super_frost:'Abbattuto'};
const $=s=>document.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const frag=h=>{const t=document.createElement('template');t.innerHTML=h.trim();return t.content.firstElementChild};
const eur=c=>c==null?'Prezzo da definire':'€ '+(c/100).toFixed(2).replace('.',',');
const txtCol=h=>{h=(h||'a67b01').replace('#','');const r=parseInt(h.substr(0,2),16),g=parseInt(h.substr(2,2),16),b=parseInt(h.substr(4,2),16);return (r*299+g*587+b*114)/1000>=160?'#000000':'#ffffff'};
const store={get(k,d){try{const v=localStorage.getItem('cc_'+k);return v==null?d:JSON.parse(v)}catch(e){return d}},set(k,v){try{localStorage.setItem('cc_'+k,JSON.stringify(v))}catch(e){}}};
const CART_KEY='bb_cart_'+CC_BB+'_'+CC_GIORNO;
let cart=CC_BB?store.get(CART_KEY,{}):{};

const itemsBy={},catsBy={};
D.items.forEach(i=>(itemsBy[i.c]=itemsBy[i.c]||[]).push(i));
D.cats.forEach(c=>(catsBy[c.m]=catsBy[c.m]||[]).push(c));
const catById=Object.fromEntries(D.cats.map(c=>[c.id,c]));
const itemById=Object.fromEntries(D.items.map(i=>[i.id,i]));

// ora di Napoli
function nowMin(){try{const p=new Intl.DateTimeFormat('it-IT',{timeZone:'Europe/Rome',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(new Date());return (+p.find(x=>x.type==='hour').value)*60+(+p.find(x=>x.type==='minute').value)}catch(e){const d=new Date();return d.getHours()*60+d.getMinutes()}}
const inTime=t=>{if(!t)return true;const n=nowMin(),a=t[0]*60+t[1],b=t[2]*60+t[3];return a<=b?(n>=a&&n<b):(n>=a||n<b)};
const catVisible=c=>c.on===1||(c.on===null&&c.t&&inTime(c.t));
const itemVisible=i=>i.on===1&&inTime(i.t);
let excluded=new Set(store.get('ex',[]));
const passAl=i=>!i.a.some(a=>excluded.has(a));
const catItems=c=>(itemsBy[c.id]||[]).filter(itemVisible);
const menuVisible=m=>m.on&&(catsBy[m.id]||[]).some(c=>catVisible(c)&&catItems(c).length);

// ---------- elementi base ----------
const mainMC=$('main .menu-container');
const HOME_VARS='--theme-bg1-color-animated: #303D2100; --blur-animated: 0px; --theme-dark-animated: #00000000; --opacity-animated: 0; --opacity-animated-reverse: 1; --image-size: 250px;';
const MENU_VARS='--theme-bg1-color-animated: #303D2180; --blur-animated: 6px; --theme-dark-animated: #00000080; --opacity-animated: 1; --opacity-animated-reverse: 0; --image-size: 250px;';
const imgMulti=$('.image-multi-menu'), imgMenu=$('.image-menu');
const spacer=$('.banner-spacer');
const blockBtn=$('.menu-back-container-block .multi-menu-back-button');
const absBar=$('.menu-back-container-absolute');
const pc=$('.pagination-content'), pages=$$('.pagination-content > .page-content');
const menusBox=$('.menus-container');
const scroller=$('#menu-container-scroll')||document.scrollingElement;
let current=null;

function setState(menu){
  const cls=(el,add,rem)=>{if(!el)return;rem.forEach(c=>el.classList.remove(c));add.forEach(c=>el.classList.add(c))};
  if(menu){
    const col='#'+menu.col, tc=txtCol(menu.col);
    mainMC.setAttribute('style',MENU_VARS+`--business-color: ${col}; --business-color-alpha20: ${col}32; --business-color-alpha40: ${col}64; --business-color-alpha60: ${col}96; --business-color-alpha80: ${col}CC; --business-text-color: ${tc};`);
    imgMenu.src=menu.pic?IMG[menu.pic]:ICONS.generic; imgMenu.alt=menu.n;
    cls(imgMulti,['hidden','hiding'],[]); cls(imgMenu,[],['hidden','hiding']);
    cls(spacer,[],['hiddenBack']); cls(blockBtn,[],['hidingBack','hiddenBack']);
    cls(absBar,['visible'],['hidingBack','hiddenBack']);cls(absBar.querySelector('.search-container'),['visible'],[]);
    $$('.multi-menu-back-button p').forEach(p=>p.textContent=menu.n);
    pc.style.setProperty('--current-page',1);
    pages[0].classList.remove('active-page');pages[0].style.maxHeight='0px';
    pages[1].classList.add('active-page');pages[1].style.maxHeight='';
  }else{
    mainMC.setAttribute('style',HOME_VARS);
    cls(imgMulti,[],['hidden','hiding']); cls(imgMenu,['hidden','hiding'],[]);
    cls(spacer,['hiddenBack'],[]); cls(blockBtn,['hidingBack','hiddenBack'],[]);
    cls(absBar,['hidingBack','hiddenBack'],['visible']);cls(absBar.querySelector('.search-container'),[],['visible']);
    $$('.multi-menu-back-button p').forEach(p=>p.textContent='Indietro');
    pc.style.setProperty('--current-page',0);
    pages[1].classList.remove('active-page');pages[1].style.maxHeight='0px';
    pages[0].classList.add('active-page');pages[0].style.maxHeight='';
    closeSearch();
  }
}

// ---------- home: schede menù ----------
function renderMenus(){
  menusBox.innerHTML='';
  D.menus.filter(menuVisible).forEach(m=>{
    const el=frag(TPL.menu); const col='#'+m.col;
    el.setAttribute('style',`--menu-color: ${col}; --menu-color-alpha80: ${col}cc; --menu-color-alpha40: ${col}66; --menu-color-alpha20: ${col}33; --menu-text-color: ${txtCol(m.col)};`);
    el.querySelector('canvas')&&el.querySelector('canvas').remove();
    const ic=el.querySelector('.items-counter-container');ic&&ic.remove();
    const im=el.querySelector('.menu-banner img'); if(m.pic){im.src=IMG[m.pic];im.alt=m.n} else im.remove();
    el.querySelector('.menu-title').textContent=m.n;
    el.setAttribute('role','button');el.tabIndex=0;
    el.addEventListener('click',()=>openMenu(m.id));
    el.addEventListener('keydown',e=>{if(e.key==='Enter')openMenu(m.id)});
    menusBox.appendChild(el);
  });
}

// ---------- pagina menù: categorie ----------
function itemEl(i){
  const el=frag(TPL.item); el.id='item-'+i.id;
  el.querySelector('.title span').textContent=i.n;
  const ds=el.querySelector('.description');
  if(i.d){let t=i.d; if(t.length>105) t=t.slice(0,105).trimEnd()+'...'; ds.textContent=t;} else ds.remove();
  const al=el.querySelector('.allergens'); al.innerHTML='';
  i.a.forEach(a=>{if(!ICONS.al[a])return;const w=document.createElement('div');w.className='allergen-icon';w.setAttribute('data-v-8c35a48a','');w.innerHTML=`<img data-v-8c35a48a="" alt="${AL[a]||a}" title="${AL[a]||a}" src="${ICONS.al[a]}">`;al.appendChild(w)});
  const pr=el.querySelector('.price'); pr.textContent=eur(i.p);
  const img=el.querySelector('.item-image img'); img.alt=i.n; img.src=i.pic?IMG[i.pic]:ICONS.generic; img.loading='lazy';
  const ctr=el.querySelector('.item-counter');ctr&&ctr.remove();
  if(CC_BB){
    const add=document.createElement('button');add.className='cc-add';add.type='button';add.textContent='＋ Aggiungi';add.setAttribute('aria-label','Aggiungi '+i.n+' al carrello');
    add.addEventListener('click',e=>{e.stopPropagation();cartQ(i.id,1)});el.appendChild(add);
  }
  if(i.disp===0){const tt=el.querySelector('.title span');const b=document.createElement('small');b.className='cc-esaurito';b.textContent=' · Esaurito';b.style.cssText='font-weight:700;color:#d35f4e';tt.after(b);el.style.opacity='.6';const ad=el.querySelector('.cc-add');ad&&ad.remove()}
  if(i.deep||i.lists||i.cod||(i.ag&&i.ag.length)||(i.rm&&i.rm.length)){el.addEventListener('click',()=>openItem(i.id));el.tabIndex=0;el.addEventListener('keydown',e=>{if(e.key==='Enter')openItem(i.id)})}
  else el.classList.add('noDeep');
  return el;
}
function setOpen(catEl,open){
  const head=catEl.querySelector('.category-head');
  head.classList.toggle('open',open);head.classList.toggle('isCollapsed',!open);
  catEl.querySelectorAll('.expand-icon > div').forEach(x=>{x.classList.toggle('up',open);x.classList.toggle('down',!open)});
  const dd=catEl.querySelector('.dropdown');
  dd.classList.toggle('collapsed',!open);dd.classList.toggle('overflow-auto',open);dd.style.maxHeight=open?'unset':'0px';
  const body=catEl.querySelector('.category-body');
  if(open&&!body.firstChild){
    const c=catById[+catEl.dataset.c];
    const box=document.createElement('div');box.className='items-container';box.setAttribute('data-v-d9d8994b','');box.id='cat-items-'+c.id;
    const its=catItems(c).filter(passAl);
    its.forEach(i=>box.appendChild(itemEl(i)));
    if(!its.length){const e=document.createElement('div');e.className='cc-empty';e.textContent='Tutti i prodotti di questa categoria contengono allergeni che hai filtrato.';box.appendChild(e)}
    body.appendChild(box);
  }
  if(!open) body.innerHTML='';
}
function renderCats(){
  const m=D.menus.find(x=>x.id===current); pages[1].innerHTML='';
  const wrap=document.createElement('div');wrap.className='menu-categories';wrap.setAttribute('data-v-4e6f31cd','');
  (catsBy[m.id]||[]).filter(c=>catVisible(c)&&catItems(c).length).forEach(c=>{
    const el=frag(TPL.cat); el.dataset.c=c.id; const col='#'+c.col;
    el.setAttribute('style',`--category-color: ${col}; --category-color-alpha40: ${col}64; --category-text-color: ${txtCol(c.col)}; --category-color-alpha60: ${col}96;`);
    const head=el.querySelector('.category-head');head.id='cat-head-'+c.id;
    el.querySelector('.category-title .title').textContent=c.n;
    const ic=el.querySelector('.items-counter-container');ic&&ic.remove();
    const im=el.querySelector('.category-banner img'); im.alt=c.n; im.src=c.pic?IMG[c.pic]:ICONS.generic;
    head.setAttribute('role','button');head.tabIndex=0;
    const tog=()=>{const open=!head.classList.contains('open');setOpen(el,open);if(open)setTimeout(()=>head.scrollIntoView({behavior:'smooth',block:'start'}),60)};
    head.addEventListener('click',tog);head.addEventListener('keydown',e=>{if(e.key==='Enter')tog()});
    wrap.appendChild(el);
  });
  pages[1].appendChild(wrap);
}
function openMenu(id){
  current=id; store.set('menu',id); renderCats(); setState(D.menus.find(m=>m.id===id));
  try{history.pushState({m:id},'')}catch(e){}
  setTimeout(()=>{const mb=pages[1].querySelector('.menu-category')||document.getElementById('menu-body');if(!mb)return;const y=mb.getBoundingClientRect().top+window.scrollY-68;window.scrollTo({top:Math.max(0,y)});if(scroller!==document.scrollingElement&&scroller.scrollHeight>scroller.clientHeight){scroller.scrollTop=mb.offsetTop-68}},60);
}
function goHome(){current=null;setState(null);(scroller.scrollTo?scroller:window).scrollTo({top:0});window.scrollTo({top:0})}
$$('.multi-menu-back-button').forEach(b=>{b.style.cursor='pointer';b.addEventListener('click',()=>{if(current){try{history.back()}catch(e){goHome()}}})});
window.addEventListener('popstate',()=>{if(current)goHome()});

// ---------- ricerca (evidenzia le categorie, Invio passa al risultato dopo) ----------
const sc=absBar.querySelector('.search-container'), q=$('#q'), rn=absBar.querySelector('.results-num');
let hits=[],hitIdx=0;
function closeSearch(){if(!sc)return;sc.classList.remove('open');q.value='';rn.classList.remove('visible');$$('.category-head.notRelevant').forEach(h=>h.classList.remove('notRelevant'));$$('.cc-hit').forEach(x=>{x.classList.remove('cc-hit');x.style.outline=''});hits=[]}
function runSearch(){
  const s=q.value.trim().toLowerCase(); hits=[];hitIdx=0;
  $$('.cc-hit').forEach(x=>{x.classList.remove('cc-hit');x.style.outline=''});
  if(!s){$$('.category-head.notRelevant').forEach(h=>h.classList.remove('notRelevant'));rn.classList.remove('visible');return}
  $$('.page-content.active-page .menu-category').forEach(el=>{
    const c=catById[+el.dataset.c]; const m=catItems(c).filter(passAl).filter(i=>i.n.toLowerCase().includes(s));
    el.querySelector('.category-head').classList.toggle('notRelevant',!m.length);
    m.forEach(i=>hits.push([el,i.id]));
  });
  rn.textContent=(hits.length?1:0)+'/'+hits.length; rn.classList.add('visible');
}
function gotoHit(){
  if(!hits.length)return; const [el,id]=hits[hitIdx]; rn.textContent=(hitIdx+1)+'/'+hits.length;
  if(!el.querySelector('.category-head').classList.contains('open')) setOpen(el,true);
  $$('.cc-hit').forEach(x=>{x.classList.remove('cc-hit');x.style.outline=''});
  const it=document.getElementById('item-'+id); if(it){it.classList.add('cc-hit');it.style.outline='2px solid var(--theme-txt1-color)';it.scrollIntoView({behavior:'smooth',block:'center'})}
}
if(sc){
  sc.addEventListener('click',e=>{if(e.target.closest('.icon-search-close')){closeSearch();e.stopPropagation();return}sc.classList.add('open');q.focus()});
  q.addEventListener('input',runSearch);
  q.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();if(!hits.length)return;gotoHit();hitIdx=(hitIdx+1)%hits.length}});
}
const rm=absBar.querySelector('.read-mode-container'); if(rm) rm.remove();

// ---------- carrello B&B: stessa carta, prezzi specifici della struttura ----------
let cartButton=null,cartPanel=null;
function cartQ(id,d){const n=Math.max(0,Math.min(20,(+cart[id]||0)+d));if(n)cart[id]=n;else delete cart[id];store.set(CART_KEY,cart);renderCart()}
function cartTotals(){return Object.entries(cart).reduce((a,[id,q])=>{const i=itemById[id];if(i){a.pezzi+=q;a.totale+=i.p*q}return a},{pezzi:0,totale:0})}
function renderCart(){
  if(!CC_BB)return;const t=cartTotals();
  cartButton.innerHTML=`🛒 <b>${t.pezzi}</b><span>${eur(t.totale)}</span>`;cartButton.hidden=!t.pezzi;
  const righe=Object.entries(cart).map(([id,q])=>{const i=itemById[id];return i?`<div class="cc-cart-line"><div><b>${i.n}</b><small>${eur(i.p)} ciascuno</small></div><div class="cc-step"><button onclick="cartQ(${i.id},-1)">−</button><b>${q}</b><button onclick="cartQ(${i.id},1)">+</button></div></div>`:''}).join('');
  cartPanel.querySelector('.cc-cart-body').innerHTML=righe||'<p>Il carrello è vuoto.</p>';
  cartPanel.querySelector('.cc-cart-total').textContent=eur(t.totale);
  cartPanel.querySelector('.cc-cart-send').disabled=!t.pezzi;
}
function openCart(v=true){cartPanel.classList.toggle('open',v);cartPanel.setAttribute('aria-hidden',v?'false':'true')}
async function sendCart(){
  const b=cartPanel.querySelector('.cc-cart-send'),righe=Object.entries(cart).map(([id,quantita])=>({prodotto_id:+id,quantita}));if(!righe.length)return;
  b.disabled=true;b.textContent='Invio…';
  try{const r=await fetch('/api/colazioni/menu-ospite/ordine',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({codice:CC_BB,giorno:CC_GIORNO,righe})}),j=await r.json().catch(()=>({}));if(!r.ok||!j.ok)throw new Error(j.detail||j.errore||'Ordine non salvato');cart={};store.set(CART_KEY,cart);renderCart();cartPanel.querySelector('.cc-cart-body').innerHTML=`<div class="cc-cart-ok"><b>Ordine inviato al bar ✓</b><br>Totale da pagare al ritiro: ${eur(Math.round((+j.totale||0)*100))}</div>`;b.textContent='Ordine inviato';setTimeout(()=>location.href='/convenzioni/#/ospite/'+encodeURIComponent(CC_BB),1200)}catch(e){alert(e.message);b.disabled=false;b.textContent='Invia ordine al bar'}}
function initCart(){
  if(!CC_BB)return;document.body.classList.add('cc-bb');
  Object.assign(window,{cartQ,openCart,sendCart});
  const info=document.createElement('div');info.className='cc-bb-head';info.innerHTML=`<b>Menu per la colazione del ${CC_GIORNO.split('-').reverse().join('/')}</b><span>${D.bb&&D.bb.struttura?D.bb.struttura:''} · scegli solo per questo giorno</span>`;document.body.appendChild(info);
  cartButton=document.createElement('button');cartButton.className='cc-cart-button';cartButton.onclick=()=>openCart(true);document.body.appendChild(cartButton);
  cartPanel=document.createElement('div');cartPanel.className='cc-cart-panel';cartPanel.setAttribute('aria-hidden','true');cartPanel.innerHTML=`<div class="cc-cart-sheet"><div class="cc-cart-title"><h2>Il tuo carrello</h2><button onclick="openCart(false)" aria-label="Chiudi">×</button></div><p class="cc-cart-note">Prodotti extra del ${CC_GIORNO.split('-').reverse().join('/')} · pagamento al bar al ritiro.</p><div class="cc-cart-body"></div><div class="cc-cart-footer"><div>Totale <b class="cc-cart-total">€ 0,00</b></div><button class="cc-cart-send" onclick="sendCart()">Invia ordine al bar</button><a href="/convenzioni/#/ospite/${encodeURIComponent(CC_BB)}">Torna alla colazione</a></div></div>`;cartPanel.addEventListener('click',e=>{if(e.target===cartPanel)openCart(false)});document.body.appendChild(cartPanel);renderCart();
}

// ---------- schede in basso ----------
function openOverlay(el){el.classList.remove('hidden');document.body.style.overflow='hidden';const m=el.querySelector('.bottom-sheet-measurer');m&&m.classList.add('activeScroll');m&&(m.scrollTop=0)}
function closeOverlay(el){el.classList.add('hidden');document.body.style.overflow=''}
const sheet=$('#product-details-bottom-sheet'), filt=$('#allergens-filter-bottom-sheet');
const TPL_SP=sheet.querySelector('.selected-product').outerHTML;
[sheet,filt].forEach(o=>{
  o.addEventListener('click',e=>{if(e.target===o||e.target.classList.contains('bottom-sheet-container')||e.target.closest('.details-footer .menu-button, .allergens-filter-footer .menu-button, .quantity-button'))closeOverlay(o)});
});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){[sheet,filt].forEach(o=>{if(!o.classList.contains('hidden'))closeOverlay(o)})}});

function openItem(id){
  const i=itemById[id], c=catById[i.c], m=D.menus.find(x=>x.id===c.m);
  const old=sheet.querySelector('.selected-product'); const sp=frag(TPL_SP); old.replaceWith(sp);
  const col='#'+m.col;
  sp.setAttribute('style',`--business-color: ${col}; --business-color-alpha20: ${col}33; --business-color-alpha40: ${col}66; --business-color-alpha60: ${col}99; --business-color-alpha80: ${col}CC; --business-text-color: ${txtCol(m.col)};`);
  sp.querySelector('.title-span').textContent=i.n;
  const tag=sp.querySelector('.category-tag'); tag.textContent=c.n; tag.style.backgroundColor='#'+c.col; tag.style.color=txtCol(c.col);
  sp.querySelector('.head-right.no-wrap').textContent=eur(i.p);
  const car=sp.querySelector('.carousel-container');
  if(i.pic){const im=car.querySelector('img');im.src=IMG[i.pic];im.alt=i.n}else car.remove();
  const dc=sp.querySelector('.descriptions-container'); const tplD=dc.querySelector('.description').outerHTML; const tplLine=(dc.querySelector('.line-description')||{outerHTML:''}).outerHTML;
  dc.innerHTML='';
  const blocks=[];
  if(i.long) blocks.push(['Descrizione lunga',i.long]);
  if(i.mat) blocks.push(['Ingredienti',i.mat]);
  if(!blocks.length&&i.d&&!i.lists) blocks.push(['Descrizione',i.d]);
  if(i.disp===0) blocks.push(['Disponibilità','Esaurito oggi']);
  if(i.ag&&i.ag.length) blocks.push(['Aggiunte',i.ag.map(a=>a.n+(a.p!=null?' (+'+eur(a.p)+')':'')).join(', ')]);
  if(i.rm&&i.rm.length) blocks.push(['Si può togliere',i.rm.join(', ')]);
  if(i.cod) blocks.push(['Codice prodotto',i.cod]);
  blocks.forEach((b,k)=>{if(k)dc.appendChild(frag(tplLine));const el=frag(tplD);el.querySelector('.description-title').textContent=b[0];el.querySelector('.description-value').textContent=b[1];dc.appendChild(el)});
  if(!blocks.length) dc.remove();
  if(i.lists){
    const lc=document.createElement('div');lc.className='lists-container';lc.setAttribute('data-v-c6075a9f','');
    i.lists.forEach(l=>{
      const el=frag(TPL.list); el.querySelector('.item-list-title').textContent=l.n;
      const body=el.querySelector('.item-list-body'); const tp=body.querySelector('.item-list-product').outerHTML; body.innerHTML='';
      l.p.forEach(p=>{const pe=frag(tp);const qn=pe.querySelector('.quantity');qn&&qn.remove();pe.querySelector('.product-title-span').textContent=p.n;pe.querySelector('.product-price').textContent=p.p?('+'+eur(p.p)):'';body.appendChild(pe)});
      lc.appendChild(el);
    });
    (sp.querySelector('.descriptions-container')||sp.querySelector('.carousel-container')||sp.querySelector('.head-container')).after(lc);
  }
  const qn=sp.querySelector('.title .quantity');qn&&qn.remove();
  if(CC_BB){const f=sp.querySelector('.details-footer');const add=document.createElement('button');add.type='button';add.className='cc-add-detail';add.textContent='＋ Aggiungi al carrello';add.addEventListener('click',()=>{cartQ(i.id,1);closeOverlay(sheet)});f.prepend(add)}
  openOverlay(sheet);
}

// ---------- filtro allergeni ----------
const counter=$('.filter-icon-container .filtered-number'), fic=$('.filter-icon-container'), fbox=$('.container-allergens');
$$('.allergen[data-k]',filt).forEach(a=>{
  const n=D.items.filter(i=>itemVisible(i)&&i.a.includes(a.dataset.k)).length;
  a.classList.toggle('withProducts',n>0);
  const conteggio=a.querySelector('.allergen-products');
  if(conteggio)conteggio.textContent=n===1?'Un prodotto':`${n} prodotti`;
});
function syncFilter(){
  $$('.allergen[data-k]',filt).forEach(a=>a.classList.toggle('off',excluded.has(a.dataset.k)));
  $$('.category-container',filt).forEach(cc=>{const all=$$('.allergen[data-k]',cc);const sw=cc.querySelector('.menu-switch');if(sw)sw.classList.toggle('active',!all.every(a=>excluded.has(a.dataset.k)))});
  const n=excluded.size; counter.textContent=n; counter.style.display=n?'':'none'; fic.classList.toggle('activeFilter',!!n); fbox.classList.toggle('active',!!n);
  store.set('ex',[...excluded]);
}
$$('.allergen[data-k]',filt).forEach(a=>{a.style.cursor='pointer';a.addEventListener('click',()=>{const k=a.dataset.k;excluded.has(k)?excluded.delete(k):excluded.add(k);syncFilter();refresh()})});
$$('.category-container',filt).forEach(cc=>{const sw=cc.querySelector('.menu-switch');if(!sw)return;sw.style.cursor='pointer';sw.addEventListener('click',()=>{const all=$$('.allergen[data-k]',cc).map(a=>a.dataset.k);const allOff=all.every(k=>excluded.has(k));all.forEach(k=>allOff?excluded.delete(k):excluded.add(k));syncFilter();refresh()})});
fbox.style.cursor='pointer';fbox.addEventListener('click',()=>openOverlay(filt));
function refresh(){ if(current){const open=$$('.page-content.active-page .menu-category').filter(e=>e.querySelector('.category-head.open')).map(e=>e.dataset.c);renderCats();open.forEach(id=>{const e=document.querySelector(`.menu-category[data-c="${id}"]`);e&&setOpen(e,true)})} }

// ---------- avvio ----------
renderMenus(); syncFilter(); setState(null);initCart();
// QR del singolo prodotto: ?p=PRD-000123 apre la sua scheda
if(CC_COD){const it=D.items.find(x=>x.cod===CC_COD);if(it)openItem(it.id)}
}).catch(e=>{document.querySelector('.menus-container').textContent='Menu non disponibile, riprova tra poco.';console.error(e)});
