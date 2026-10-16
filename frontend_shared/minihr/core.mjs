/** MiniHR shared contract. No network, storage, writes or personal data. */
export const CORE_VERSION = '1.0.0';
export const SCHEMA_VERSION = 1;
export const START_MONTH = '2022-12';
export function monthOf(value) { const s=String(value||'');return /^\d{4}-(?:0[1-9]|1[0-2])(?:-\d{2})?$/.test(s)?s.slice(0,7):''; }
export function validDate(value) { if(!/^\d{4}-\d{2}-\d{2}$/.test(String(value||'')))return false;const d=new Date(value+'T12:00:00Z');return !Number.isNaN(d.getTime())&&d.toISOString().slice(0,10)===value; }
export function cents(value) { if(value===null||value===undefined||value==='')return null;const number=Number(value); return Number.isFinite(number) ? Math.round(number*100) : null; }
export function safeHref(value) {
  const text=String(value||'').trim();
  if (!text || /[\u0000-\u0020\\]/.test(text) || text.startsWith('//')) return '';
  if (/^https?:\/\//i.test(text)) { try { const u=new URL(text); return u.username||u.password?'':u.href; } catch { return ''; } }
  return /^(?:\/|\.\/)?[A-Za-z0-9_./%-]+(?:[?#][^<>"']*)?$/.test(text) && !text.includes(':') ? text : '';
}
function dayAfter(value) { if(!validDate(value)) return ''; const d=new Date(value+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+1);return d.toISOString().slice(0,10); }
function nextMonth(value) { const [year,month]=value.split('-').map(Number);return `${year+(month===12?1:0)}-${String(month===12?1:month+1).padStart(2,'0')}`; }
export function months(from, to) {
  if (!monthOf(from)||!monthOf(to)||from<START_MONTH||from>to) return [];
  const out=[];for(let m=from;m<=to&&out.length<240;m=nextMonth(m))out.push(m);return out;
}
const finalType = type => /tfr|cessazione/i.test(type||'');
const additionalType = type => /tredicesima|quattordicesima|13ª|14ª|aggiuntiv/i.test(type||'');
const ordinaryType = type => !additionalType(type) && (!finalType(type)||/con tfr/i.test(type));
export function periodsFor(employee) {
  const groups=new Map();
  for(const event of employee.events||[]) {
    if(!event.verified || !validDate(event.start) || event.kind==='revoca')continue;
    const key=event.relationshipId||event.start;
    if(!groups.has(key))groups.set(key,{id:key,start:event.start,endExclusive:'',scheduledEnd:'',proofs:[],conflicts:[]});
    const period=groups.get(key);period.proofs.push(event);
    if(event.start!==period.start)period.conflicts.push('Date iniziali discordanti');
    if(event.kind==='cessazione'&&validDate(event.effective)) {
      if(period.endExclusive&&period.endExclusive!==event.effective)period.conflicts.push('Cessazioni discordanti');
      if(!period.endExclusive||event.effective<period.endExclusive)period.endExclusive=event.effective;
    }
  }
  for(const period of groups.values()) {
    const ordered=period.proofs.filter(e=>e.kind!=='cessazione').sort((a,b)=>(a.effective||a.start).localeCompare(b.effective||b.start));
    let openEnded=false;
    for(const e of ordered) {
      if(e.indefinite){openEnded=true;period.scheduledEnd='';}
      else if(validDate(e.end)&&!openEnded)period.scheduledEnd=period.scheduledEnd>e.end?period.scheduledEnd:e.end;
    }
  }
  return [...groups.values()].sort((a,b)=>a.start.localeCompare(b.start));
}
export function employmentInMonth(employee, month) {
  const start=month+'-01',end=nextMonth(month)+'-01',periods=periodsFor(employee);
  const latest=periods.filter(p=>p.start<end).at(-1);
  // An older open record must not revive employment after the latest
  // documented relationship has ended.
  if(latest?.endExclusive&&latest.endExclusive<=start)return {code:'ceased',label:'Rapporto cessato',expected:false,proofs:latest.proofs,reasons:[]};
  const overlapping=periods.filter(p=>p.start<end&&(!p.endExclusive||p.endExclusive>start));
  if(overlapping.length) {
    const p=overlapping.at(-1),expired=p.scheduledEnd&&dayAfter(p.scheduledEnd)<=start;
    if(p.conflicts.length)return {code:'uncertain',label:'Rapporto da verificare',expected:false,proofs:p.proofs,reasons:p.conflicts};
    if(expired)return {code:'contract_expired',label:'Scadenza contratto: proroga non reperita',expected:false,proofs:p.proofs,reasons:['La scadenza non prova da sola una cessazione effettiva']};
    return {code:'active',label:p.endExclusive&&p.endExclusive<end?'Cessazione nel mese':'Rapporto documentato nel mese',expected:true,proofs:p.proofs,reasons:[]};
  }
  const prior=periods.filter(p=>p.start<end).at(-1);
  if(prior?.endExclusive&&prior.endExclusive<=start)return {code:'ceased',label:'Rapporto cessato',expected:false,proofs:prior.proofs,reasons:[]};
  if(periods.length&&start<periods[0].start)return {code:'not_started',label:'Prima del rapporto documentato',expected:false,proofs:[],reasons:[]};
  return {code:'unknown',label:'Rapporto da accertare',expected:false,proofs:[],reasons:['Nessuna data certa sufficiente: non si presume un rapporto attivo']};
}
export function buildMonthly(employee, options={}) {
  const today=options.today||new Date().toISOString().slice(0,10),from=options.from||START_MONTH,to=options.to||today.slice(0,7);
  let balance=0;
  return months(from,to).map(month=>{
    const slips=(employee.slips||[]).filter(s=>s.month===month),documents=(employee.documents||[]).filter(d=>d.month===month),payments=(employee.payments||[]).filter(p=>monthOf(p.date)===month);
    const period=employmentInMonth(employee,month),ordinary=slips.filter(s=>s.isPayslip!==false&&ordinaryType(s.type)&&!s.placeholder),pdfs=ordinary.filter(s=>safeHref(s.url)),acquired=documents.filter(d=>d.isPayslip!==false&&ordinaryType(d.type)&&safeHref(d.url));
    const excluded=!!employee.excludedYears?.includes(Number(month.slice(0,4)));
    const due=excluded?0:slips.filter(s=>s.counted!==false&&Number.isInteger(s.amountCents)).reduce((a,s)=>a+s.amountCents,0);
    const paid=excluded?0:payments.filter(p=>p.counted===true&&Number.isInteger(p.amountCents)).reduce((a,p)=>a+p.amountCents,0);
    const unverified=excluded?0:payments.filter(p=>p.counted!==true&&!p.excluded&&Number.isInteger(p.amountCents)).reduce((a,p)=>a+p.amountCents,0);
    balance+=paid-due;
    let status={code:'not_expected',label:period.label,level:'neutral'};
    if(pdfs.length)status={code:'available',label:pdfs.every(s=>s.amountCents===0)?'Cedolino a zero disponibile':'Cedolino disponibile',level:'ok'};
    else if(ordinary.length)status={code:'missing_pdf',label:'Dati cedolino presenti: PDF mancante',level:'warning'};
    else if(acquired.length)status={code:'acquired',label:'PDF reperito: da confrontare con la scheda',level:'warning'};
    else if(slips.some(s=>!s.placeholder&&safeHref(s.url)&&finalType(s.type)))status={code:'final_documents',label:'Documenti finali / TFR disponibili',level:'ok'};
    else if(period.expected)status=month>=today.slice(0,7)?{code:'waiting',label:'Mese in corso / in attesa',level:'neutral'}:{code:'missing',label:'Cedolino mancante',level:'danger'};
    else if(['unknown','uncertain','contract_expired'].includes(period.code))status={code:'uncertain',label:period.label,level:'warning'};
    const anomalies=[...period.reasons];
    if(slips.some(s=>s.documentConflict))anomalies.push('Importo o documento discordante: nessuna rettifica automatica');
    if(period.code==='ceased'&&ordinary.some(s=>!/compenso/i.test(s.type||'')))anomalies.push('Dati ordinari successivi alla cessazione: verificare eventuali arretrati o riassunzione');
    if(period.code==='contract_expired'&&ordinary.length)anomalies.push('Cedolino successivo alla scadenza: recuperare proroga o trasformazione');
    if(slips.some(s=>s.placeholder))anomalies.push('Riga a zero non documentata: non prova un cedolino emesso');
    return {month,period,status,slips,documents,payments,excluded,dueCents:due,paidCents:paid,unverifiedCents:unverified,balanceCents:balance,anomalies};
  });
}
