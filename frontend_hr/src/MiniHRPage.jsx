import React, {useEffect, useRef, useState} from 'react';
import axios from 'axios';
import {safeHref,buildMonthly} from '../../frontend_shared/minihr/core.mjs';
import {apriFinestraPdfAttesa, mostraPdfNellaFinestra} from './pdfWindow';

const API='/hr/api/minihr';
const euro=c=>c===null||c===undefined?'Importo non leggibile':new Intl.NumberFormat('it-IT',{style:'currency',currency:'EUR'}).format(c/100);
const failure=e=>typeof e?.response?.data?.detail==='string'?e.response.data.detail:'Caricamento non riuscito. Verificare l’accesso e riprovare.';

export default function MiniHRPage(){
  const [tab,setTab]=useState('partitario'),[from,setFrom]=useState('2022-12'),[to,setTo]=useState(new Date().toISOString().slice(0,7));
  const widget=useRef(null),[roster,setRoster]=useState([]),[selected,setSelected]=useState(''),[payload,setPayload]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(false),[cf,setCf]=useState(''),[fiscal,setFiscal]=useState(null),[fiscalLoading,setFiscalLoading]=useState(false),[retry,setRetry]=useState(0);
  useEffect(()=>{const c=new AbortController();axios.get(`${API}/employees`,{signal:c.signal}).then(({data})=>{setRoster(data.employees);setSelected(data.employees[0]?.id||'');}).catch(e=>{if(!axios.isCancel(e))setError(failure(e));});return()=>c.abort();},[retry]);
  useEffect(()=>{if(!selected)return;const c=new AbortController();setLoading(true);setPayload(null);setError('');setFiscal(null);setCf('');axios.get(`${API}/employees/${encodeURIComponent(selected)}`,{signal:c.signal}).then(({data})=>{setPayload(data);setCf(data.companyFiscalCode||'');}).catch(e=>{if(!axios.isCancel(e))setError(failure(e));}).finally(()=>{if(!c.signal.aborted)setLoading(false);});return()=>c.abort();},[selected,retry]);
  async function openDocument(href){
    if(!safeHref(href))return;
    // Never attach ERP credentials to Drive or any external origin.
    if(!href.startsWith('/hr/api/')&&!href.startsWith('/api/originale/')){window.open(href,'_blank','noopener');return;}
    const popup=apriFinestraPdfAttesa();
    if(!popup){setError('Consentire l’apertura delle finestre PDF e riprovare.');return;}
    try{const r=await axios.get(href,{responseType:'blob'});const url=URL.createObjectURL(r.data);mostraPdfNellaFinestra(popup,url);setTimeout(()=>URL.revokeObjectURL(url),60000);}catch(e){popup.close();setError('Documento non disponibile o accesso non consentito. Nessun dato modificato.');}
  }
  useEffect(()=>{const el=widget.current;if(!el||!payload)return;let cancelled=false;
    const click=e=>{e.preventDefault();openDocument(e.detail.href);};
    // Register the browser-only custom element after mount, not while the
    // existing HR routes are imported by Node/SSR permission checks.
    import('../../frontend_shared/minihr/view.mjs').then(()=>{
      if(cancelled)return;
      el._from=from;el._to=to;el.data={employees:[payload.employee],today:new Date().toISOString().slice(0,10),sourceLabel:'GestionaleCloud · archivi propri · vista parallela',notices:payload.notices};
      el.addEventListener('minihr-document',click);
    }).catch(()=>{if(!cancelled)setError('Vista documentale non disponibile. Ricaricare la pagina. Nessun dato modificato.');});
    return()=>{cancelled=true;el.removeEventListener('minihr-document',click);};
  },[payload,tab,from,to]);
  const fiscalRequest=useRef(0);
  useEffect(()=>{fiscalRequest.current++;setFiscalLoading(false);},[selected,cf]);
  async function loadFiscal(){const generation=++fiscalRequest.current;setFiscalLoading(true);setFiscal(null);try{const r=await axios.get(`${API}/company-f24/${encodeURIComponent(cf.trim())}`);if(generation===fiscalRequest.current)setFiscal(r.data);}catch(e){if(generation===fiscalRequest.current)setError(failure(e));}finally{if(generation===fiscalRequest.current)setFiscalLoading(false);}}
  const monthly=payload?buildMonthly(payload.employee,{from,to}):[],slips=monthly.flatMap(r=>r.slips),payments=monthly.flatMap(r=>r.payments),due=monthly.reduce((a,r)=>a+r.dueCents,0),paid=monthly.reduce((a,r)=>a+r.paidCents,0),opening=(payload?.employee.slips||[]).filter(s=>s.month==='2022-12');
  const documentButton=(url,label)=>safeHref(url)?<button className="dc-btn" onClick={()=>openDocument(url)}>{label||'Apri documento'}</button>:<span>PDF mancante</span>;
  return <div className="dc-page">
    <div className="dc-card"><h1>Fascicolo mensile · MiniHR</h1><p>Un’unica scheda: cedolini, pagamenti, partitario e apertura 2023. Vista parallela in sola lettura, da dicembre 2022. Nessun archivio del minisito è stato importato o sovrascritto.</p><a href="https://salari-dipendenti-ceraldi.ceraldigroupsrl.chatgpt.site/MiniHR_v37" target="_blank" rel="noopener noreferrer">Apri il minisito, che resta operativo</a></div>
    <div className="dc-card"><label>Dipendente <select value={selected} onChange={e=>setSelected(e.target.value)} aria-label="Dipendente fascicolo"><option value="">Scegli dipendente</option>{roster.map(e=><option key={e.id} value={e.id}>{e.name}</option>)}</select></label> <label>Dal mese <input type="month" min="2022-12" value={from} onChange={e=>{if(e.target.value>='2022-12'&&e.target.value<=to)setFrom(e.target.value);}}/></label> <label>Al mese <input type="month" min={from} value={to} onChange={e=>{if(e.target.value>=from)setTo(e.target.value);}}/></label> <button className="dc-btn" onClick={()=>setRetry(n=>n+1)}>Ricarica</button></div>
    {error&&<div className="dc-card" role="alert">{error}</div>}
    {loading&&<p role="status">Caricamento del fascicolo…</p>}
    {!loading&&!error&&!roster.length&&<p>Nessuna anagrafica disponibile nell’archivio HR.</p>}
    {payload&&<><div className="dc-card"><p>Dovuto {euro(due)} · Pagato {euro(paid)} · Saldo del periodo {euro(paid-due)}</p><nav aria-label="Viste dipendente">{[['cedolini','Cedolini e documenti'],['pagamenti','Pagamenti'],['partitario','Partitario mensile'],['apertura','Apertura 2023']].map(([key,label])=><button key={key} className="dc-btn" aria-pressed={tab===key} onClick={()=>setTab(key)}>{label}</button>)}</nav></div>
      {tab==='partitario'&&<minihr-fascicolo ref={widget} external-filters=""/>}
      {tab==='cedolini'&&<div className="dc-card"><h2>Cedolini e documenti</h2><table className="dc-table"><thead><tr><th>Competenza</th><th>Tipo</th><th>Importo</th><th>Documento</th><th>Conteggio</th></tr></thead><tbody>{slips.map(s=><tr key={s.id}><td>{s.month}</td><td>{s.type}</td><td>{euro(s.amountCents)}</td><td>{documentButton(s.url)}</td><td>{s.counted===false?'Escluso':'Da archivio HR'}</td></tr>)}</tbody></table><h3>Documenti senza competenza certa</h3><p>Non collocati usando la data di caricamento.</p>{payload.undatedDocuments.length?payload.undatedDocuments.map(d=><p key={d.id}>{documentButton(d.url,`${d.label} · ${d.type}`)}</p>):<p>Nessun documento senza competenza in questa anagrafica.</p>}</div>}
      {tab==='pagamenti'&&<div className="dc-card"><h2>Pagamenti</h2><table className="dc-table"><thead><tr><th>Data</th><th>Riferimento</th><th>Importo</th><th>Documento</th><th>Conteggio</th></tr></thead><tbody>{payments.map(p=><tr key={p.id}><td>{p.date}</td><td>{p.reference}</td><td>{euro(p.amountCents)}</td><td>{documentButton(p.url)}</td><td>{p.counted?'Conteggiato':'Da verificare / escluso'}</td></tr>)}</tbody></table></div>}
      {tab==='apertura'&&<div className="dc-card"><h2>Apertura 2023</h2><p>Documenti di dicembre 2022, comprese le tredicesime. Non è un saldo iniziale certificato. Le conferme/esclusioni del minisito non vengono importate automaticamente nel Gestionale.</p><table className="dc-table"><thead><tr><th>Tipo</th><th>Importo</th><th>Documento</th></tr></thead><tbody>{opening.map(s=><tr key={s.id}><td>{s.type}</td><td>{euro(s.amountCents)}</td><td>{documentButton(s.url)}</td></tr>)}</tbody></table></div>}
    </>}
    <div className="dc-card"><h2>F24 aziendali · registro fiscale esistente</h2><p>Separati dal netto del dipendente. Inserire il codice fiscale del datore: non viene dedotto dal nome o dall’importo. Le righe annuali o prive di mese non sono ripartite automaticamente.</p><label>Codice fiscale azienda <input value={cf} onChange={e=>{setCf(e.target.value);setFiscal(null);setFiscalLoading(false);}} /></label> <button className="dc-btn" disabled={!cf.trim()||fiscalLoading} onClick={loadFiscal}>{fiscalLoading?'Caricamento…':'Leggi F24'}</button>
      {fiscal&&<><p>{fiscal.notice}</p>{!fiscal.documents.length&&<p>Nessun F24 disponibile per questo codice fiscale.</p>}<div style={{overflowX:'auto'}}><table className="dc-table"><thead><tr><th>Documento</th><th>Competenza della riga</th><th>Tributo</th><th>Debito</th><th>Credito</th><th>Evidenza pagamento</th></tr></thead><tbody>{fiscal.documents.flatMap(d=>d.lines.map((r,n)=><tr key={`${d.id}:${n}`}><td><button onClick={()=>openDocument(d.url)}>Apri F24</button></td><td>{r.anno?(r.mese?`${r.anno}-${String(r.mese).padStart(2,'0')}`:`${r.anno} · mese non certo/annuale`):'Da verificare'}</td><td>{r.codice} · {r.sezione}</td><td>{euro(r.importo_debito_cents)}</td><td>{euro(r.importo_credito_cents)}</td><td>{d.evidence.stato}</td></tr>))}</tbody></table></div></>}
    </div>
  </div>;
}
