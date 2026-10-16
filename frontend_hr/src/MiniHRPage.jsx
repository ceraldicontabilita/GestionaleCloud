import React, {useEffect, useRef, useState} from 'react';
import axios from 'axios';
import {safeHref} from '../../frontend_shared/minihr/core.mjs';
import {apriFinestraPdfAttesa, mostraPdfNellaFinestra} from './pdfWindow';

const API='/hr/api/minihr';
const euro=c=>new Intl.NumberFormat('it-IT',{style:'currency',currency:'EUR'}).format(c/100);
const failure=e=>typeof e?.response?.data?.detail==='string'?e.response.data.detail:'Caricamento non riuscito. Verificare l’accesso e riprovare.';

export default function MiniHRPage(){
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
      el.data={employees:[payload.employee],today:new Date().toISOString().slice(0,10),sourceLabel:'GestionaleCloud · archivi propri · vista parallela',notices:payload.notices};
      el.addEventListener('minihr-document',click);
    }).catch(()=>{if(!cancelled)setError('Vista documentale non disponibile. Ricaricare la pagina. Nessun dato modificato.');});
    return()=>{cancelled=true;el.removeEventListener('minihr-document',click);};
  },[payload]);
  const fiscalRequest=useRef(0);
  useEffect(()=>{fiscalRequest.current++;setFiscalLoading(false);},[selected,cf]);
  async function loadFiscal(){const generation=++fiscalRequest.current;setFiscalLoading(true);setFiscal(null);try{const r=await axios.get(`${API}/company-f24/${encodeURIComponent(cf.trim())}`);if(generation===fiscalRequest.current)setFiscal(r.data);}catch(e){if(generation===fiscalRequest.current)setError(failure(e));}finally{if(generation===fiscalRequest.current)setFiscalLoading(false);}}
  return <div className="dc-page">
    <div className="dc-card"><h1>Fascicolo mensile · MiniHR</h1><p>Vista parallela in sola lettura, da dicembre 2022. Nessun archivio del minisito è stato importato o sovrascritto.</p><a href="https://salari-dipendenti-ceraldi.ceraldigroupsrl.chatgpt.site/Fascicolo_mensile_v43" target="_blank" rel="noopener noreferrer">Apri il minisito, che resta operativo</a></div>
    <div className="dc-card"><label>Dipendente <select value={selected} onChange={e=>setSelected(e.target.value)} aria-label="Dipendente fascicolo"><option value="">Scegli dipendente</option>{roster.map(e=><option key={e.id} value={e.id}>{e.name}</option>)}</select></label> <button className="dc-btn" onClick={()=>setRetry(n=>n+1)}>Ricarica</button></div>
    {error&&<div className="dc-card" role="alert">{error}</div>}
    {loading&&<p role="status">Caricamento del fascicolo…</p>}
    {!loading&&!error&&!roster.length&&<p>Nessuna anagrafica disponibile nell’archivio HR.</p>}
    {payload&&<><minihr-fascicolo ref={widget}/><div className="dc-card"><h2>Documenti senza competenza certa</h2><p>Non collocati usando la data di caricamento.</p>{payload.undatedDocuments.length?payload.undatedDocuments.map(d=><p key={d.id}><button className="dc-btn" onClick={()=>openDocument(d.url)}>{d.label} · {d.type}</button></p>):<p>Nessun documento senza competenza in questa anagrafica.</p>}</div></>}
    <div className="dc-card"><h2>F24 aziendali · registro fiscale esistente</h2><p>Separati dal netto del dipendente. Inserire il codice fiscale del datore: non viene dedotto dal nome o dall’importo. Le righe annuali o prive di mese non sono ripartite automaticamente.</p><label>Codice fiscale azienda <input value={cf} onChange={e=>{setCf(e.target.value);setFiscal(null);setFiscalLoading(false);}} /></label> <button className="dc-btn" disabled={!cf.trim()||fiscalLoading} onClick={loadFiscal}>{fiscalLoading?'Caricamento…':'Leggi F24'}</button>
      {fiscal&&<><p>{fiscal.notice}</p>{!fiscal.documents.length&&<p>Nessun F24 disponibile per questo codice fiscale.</p>}<div style={{overflowX:'auto'}}><table className="dc-table"><thead><tr><th>Documento</th><th>Competenza della riga</th><th>Tributo</th><th>Debito</th><th>Credito</th><th>Evidenza pagamento</th></tr></thead><tbody>{fiscal.documents.flatMap(d=>d.lines.map((r,n)=><tr key={`${d.id}:${n}`}><td><button onClick={()=>openDocument(d.url)}>Apri F24</button></td><td>{r.anno?(r.mese?`${r.anno}-${String(r.mese).padStart(2,'0')}`:`${r.anno} · mese non certo/annuale`):'Da verificare'}</td><td>{r.codice} · {r.sezione}</td><td>{euro(r.importo_debito_cents)}</td><td>{euro(r.importo_credito_cents)}</td><td>{d.evidence.stato}</td></tr>))}</tbody></table></div></>}
    </div>
  </div>;
}
