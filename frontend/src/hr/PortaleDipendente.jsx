import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import {
  Calendar, FileText, Inbox, Bell, Users, LogOut, Download,
  Check, ChevronLeft, Send, Eye, ClipboardList, Settings,
  FolderOpen, Upload, Trash2, AlertTriangle, Grid3X3, Clock, MapPin,
} from "lucide-react";
import "./portale.css";

const TK = "pt_token";
// Legge la scadenza (exp) dal JWT senza verificarne la firma (la verifica vera
// e' lato server, qui serve solo a decidere se riaprire il portale senza PIN).
// Stessa logica di main.jsx (RequireRole per l'area gestione), duplicata qui
// perche' main.jsx non e' un modulo condiviso.
function tokenValido(token) {
  if (!token) return false;
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return !payload.exp || payload.exp * 1000 > Date.now();
  } catch {
    return false;
  }
}
// Millisecondi mancanti alla scadenza (null se assente/invalido/senza exp):
// serve a pianificare il logout automatico anche se la pagina resta in
// primo piano ininterrottamente, senza aspettare un evento di focus.
function msAllaScadenza(token) {
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return payload.exp ? payload.exp * 1000 - Date.now() : null;
  } catch {
    return null;
  }
}
// timeout esplicito: senza, su wifi scarso al banco una richiesta puo' restare
// appesa a tempo indeterminato e il bottone (es. Timbra) resta bloccato su
// "Attendi..." senza che il dipendente sappia se e' andata a buon fine.
// Prefisso composto (non letterale): vedi nota HR_API in HRApp.jsx.
const api = axios.create({ baseURL: "/api" + "/hr", timeout: 15000 });
// Upload/download di file (buste PDF, documenti fino a 12MB) possono legittimamente
// superare 15s su wifi scarso: qui serve piu' margine, non un fallimento prematuro
// di un trasferimento che sta andando bene ma lentamente (trovato da una review
// automatica: il timeout condiviso avrebbe interrotto upload/download validi).
const FILE_TIMEOUT = 60000;
// Le scritture (POST/PUT/DELETE) possono restare in attesa lato server anche
// dopo aver gia' fatto l'inserimento — es. POST /richieste inserisce la riga
// e SOLO DOPO aspetta l'invio email (fino a 30s, backend/app/services/
// email_smtp.py). Con soli 15s il client vede un timeout, mostra "riprova",
// ma un secondo tentativo crea una SECONDA richiesta/notifica/email per un
// inserimento gia' andato a buon fine (trovato da una review automatica).
// Le sole GET restano a 15s: sono sicure da interrompere e riprovare.
const WRITE_TIMEOUT = 40000;
// Generazione corrente della vista montata: incrementata ad ogni cambio tab
// (vedi _azzeraConnessione). Ogni richiesta viene marcata con la generazione
// in cui e' partita — se fallisce DOPO che l'utente ha gia' cambiato tab, la
// generazione non combacia piu' e il fallimento viene ignorato: senza,
// una richiesta lenta partita dalla tab abbandonata poteva riaccendere il
// banner sopra la tab nuova, gia' caricata con successo, senza modo di
// spegnersi da solo (trovato da una review automatica).
let _connGenerazione = 0;
api.interceptors.request.use((c) => {
  const t = localStorage.getItem(TK);
  if (t) c.headers.Authorization = `Bearer ${t}`;
  if ((c.method || "get").toLowerCase() !== "get" && (!c.timeout || c.timeout <= 15000)) {
    c.timeout = WRITE_TIMEOUT;
  }
  c._connGen = _connGenerazione;
  return c;
});
// Banner "connessione assente" condiviso da tutte le tab: un errore di rete/
// timeout (nessuna risposta dal server) sembra identico ad ogni singola vista
// — qui si segnala una volta sola, visibile ovunque, con un modo di riprovare
// invece di restare bloccati. Tenuto per CHIAVE richiesta (metodo+url), non
// come flag unico: una richiesta diversa andata a buon fine nel frattempo NON
// deve spegnere il banner se la vista che ha fallito e' ancora rotta (es. un
// altro tab che sta caricando con successo) — ma quando la STESSA richiesta
// che aveva fallito va a buon fine (l'utente/la vista si e' ripresa da sola),
// il banner si spegne senza dover premere "Ricarica" (trovato da una review
// automatica: prima non si spegneva mai da solo, nemmeno a vista recuperata).
// LIMITE NOTO (trovato da una review automatica, non risolto qui): se una
// stessa vista rifà la stessa richiesta con parametri diversi (es. un admin
// che cambia la data filtrata su un endpoint che fallisce su un giorno e poi
// ne interroga un altro con successo), la query "vecchia" fallita resta in
// _connFallite finché non si cambia tab — nessuno la richiede più per farla
// scadere da sola. Tracciare l'owner-vista invece della sola chiave
// richiesta risolverebbe anche questo, ma è un cambio di disegno più ampio
// di un banner informativo con "Ricarica" già disponibile come via d'uscita
// manuale: non affrontato qui.
let _connFallite = new Set();
let _connListeners = [];
function _chiaveRichiesta(config) {
  return `${(config?.method || "get").toLowerCase()} ${config?.url || ""}`;
}
function _notificaConnessione() {
  const assente = _connFallite.size > 0;
  _connListeners.forEach((fn) => fn(assente));
}
function _azzeraConnessione() {
  _connGenerazione++;
  _connFallite.clear();
  _notificaConnessione();
}
// Un token persistito puo' sembrare valido lato client (exp futuro) ma essere
// rifiutato dal server — segreto ruotato, o il dipendente e' stato cessato/
// disattivato nel frattempo (il PIN viene revocato alla cessazione, ma un
// token gia' emesso resta valido fino alla scadenza naturale: qui si copre
// almeno il caso in cui il server lo rifiuta comunque). Senza questo, il
// portale restava aperto sulla schermata principale mentre ogni chiamata API
// falliva silenziosamente con 401 (trovato da una review automatica).
let _authListeners = [];
function _sessioneRifiutata() {
  localStorage.removeItem(TK);
  localStorage.removeItem("pt_role");
  localStorage.removeItem("pt_name");
  _authListeners.forEach((fn) => fn());
}
api.interceptors.response.use(
  (r) => {
    if (_connFallite.delete(_chiaveRichiesta(r.config))) _notificaConnessione();
    return r;
  },
  (error) => {
    // Una risposta del server (anche un errore HTTP, es. 409 su un retry di
    // una scrittura gia' andata a buon fine) dimostra che la connessione
    // funziona quanto un successo: va tolta dai fallimenti come un successo,
    // altrimenti resta "connessione assente" mentre si vede gia' l'errore
    // specifico del server (trovato da una review automatica).
    if (error.response) {
      if (_connFallite.delete(_chiaveRichiesta(error.config))) _notificaConnessione();
      if (error.response.status === 401) _sessioneRifiutata();
    } else if (error.config?._connGen === _connGenerazione) {
      // Ignora il fallimento se la vista che l'ha generato e' stata nel
      // frattempo abbandonata (cambio tab -> nuova generazione): altrimenti
      // una richiesta lenta partita dalla tab precedente potrebbe riaccendere
      // il banner sopra la tab nuova, gia' caricata con successo, senza che
      // nulla la richieda piu' per farlo spegnere da solo.
      _connFallite.add(_chiaveRichiesta(error.config));
      _notificaConnessione();
    }
    return Promise.reject(error);
  }
);

const TIPI = [
  { v: "ferie_programmate", l: "Ferie programmate", date: true },
  { v: "indisponibilita", l: "Indisponibilità", date: true },
  { v: "cambio_turno", l: "Cambio turno" },
  { v: "acconto_stipendio", l: "Acconto stipendio" },
  { v: "acconto_tfr", l: "Acconto TFR" },
  { v: "anticipo_retribuzione", l: "Anticipo retribuzione" },
  { v: "cambio_mansione", l: "Cambio mansione" },
  { v: "reclamo", l: "Reclamo" },
  { v: "contestazione_busta", l: "Contestazione busta paga" },
];
const tipoLabel = (v) => (TIPI.find((t) => t.v === v) || {}).l || v;
const fmt = (d) => (d ? `${d.slice(8, 10)}/${d.slice(5, 7)}` : "-");

/* ---------------- LOGIN ---------------- */
function Login({ onLogin }) {
  // Selettore a tocco: elenco nomi (GET pubblico, solo id+nome) invece di
  // digitare il cognome — decisione esplicita del titolare per un dispositivo
  // condiviso in negozio (cucina/pasticceria), dove ridigitare il nome ad ogni
  // uso era scomodissimo. Tocca il tuo nome -> tastierino PIN, come prima.
  const [elenco, setElenco] = useState(null);   // null = in caricamento
  const [elencoErr, setElencoErr] = useState(false);
  const [sel, setSel] = useState(null);   // {id, nome} del dipendente scelto
  const [pin, setPin] = useState("");
  const [err, setErr] = useState("");

  // Estratta (non solo nell'effetto) per poterla richiamare dal bottone
  // "Riprova": senza, un fallimento di rete lasciava l'elenco vuoto per
  // sempre, senza alcun modo di ricaricarlo se non l'intera pagina — proprio
  // sulla wifi scarsa che questo selettore doveva gestire (trovato da una
  // review automatica).
  const caricaElenco = () => {
    setElenco(null);
    setElencoErr(false);
    api.get("/auth/dipendenti-attivi")
      .then((r) => setElenco(r.data.dipendenti || []))
      .catch(() => { setElenco([]); setElencoErr(true); });
  };
  useEffect(() => { caricaElenco(); }, []);

  const press = (n) => { setErr(""); if (pin.length < 8) setPin(pin + n); };
  const submit = async (p) => {
    try {
      const body = { dipendente_id: sel.id, pin: p };
      const r = await api.post("/auth/pin-login", body);
      // Un login riuscito e' la prova piu' diretta possibile che la
      // connessione funziona: se un tentativo precedente aveva acceso il
      // banner "Connessione assente" (prima del login, quindi non visibile
      // in questa schermata), va spento qui — altrimenti l'app si apre con
      // un banner falso proprio nel momento in cui la connessione e' appena
      // stata dimostrata funzionante (trovato da una review automatica).
      _azzeraConnessione();
      localStorage.setItem(TK, r.data.access_token);
      localStorage.setItem("pt_role", r.data.role);
      localStorage.setItem("pt_name", r.data.name || sel.nome);
      onLogin();
    } catch (e) {
      // Prima del login il banner globale "Connessione assente" non e' ancora
      // visibile (schermata separata da pt-root): senza questa distinzione un
      // timeout di rete veniva mostrato come "PIN errato", proprio sulla wifi
      // scarsa che questo fix doveva coprire (trovato da una review automatica).
      // Login via id (non piu' per nome): un PIN errato e' sempre "PIN errato",
      // niente piu' ambiguita' da riportare come "nome o PIN non validi".
      setErr(!e.response ? "Connessione assente — riprova" : "PIN errato");
      setPin("");
    }
  };

  if (!sel) return (
    <div className="login">
      <div className="brand"><div className="logo"><Users size={30} /></div>
        <h2>Portale Dipendenti</h2><div className="muted" style={{textAlign:"center"}}>Ceraldi Group</div></div>
      <div className="card"><h3>Chi sei?</h3>
        {elenco === null && <div className="muted">Caricamento…</div>}
        {elenco !== null && elenco.length === 0 && elencoErr && (
          <>
            <div className="muted">Connessione assente</div>
            <button className="btn gh sm" style={{ marginTop: 8 }} onClick={caricaElenco}>Riprova</button>
          </>
        )}
        {elenco !== null && elenco.length === 0 && !elencoErr && (
          <div className="muted">Nessun nome disponibile: contatta l'amministratore</div>
        )}
        <div className="nomi-grid">
          {(elenco || []).map((d) => (
            <button key={d.id} className="btn nome-tile" onClick={() => setSel(d)}>{d.nome}</button>
          ))}
        </div>
      </div>
      <button className="btn sec" onClick={() => { window.location.href = "/login"; }}>
        Accesso amministratore</button>
    </div>
  );

  return (
    <div className="login">
      <button className="btn gh sm" style={{ width: "auto" }} onClick={() => { setSel(null); setPin(""); setErr(""); }}>
        <ChevronLeft size={16} /> indietro</button>
      <h2 style={{ marginTop: 18 }}>Ciao {sel.nome}</h2>
      <div className="muted" style={{ textAlign: "center" }}>Inserisci il tuo PIN</div>
      <div className="pin-dots">{Array.from({length: Math.max(4, pin.length)}).map((_,i)=><i key={i} className={pin.length>i?"on":""} />)}</div>
      {err && <div className="err">{err}</div>}
      <div className="pinpad">
        {[1,2,3,4,5,6,7,8,9].map((n)=><button key={n} onClick={()=>press(n)}>{n}</button>)}
        <button onClick={()=>setPin("")}>C</button>
        <button onClick={()=>press(0)}>0</button>
        <button onClick={()=>submit(pin)} disabled={pin.length<4} style={{color:"var(--violet)"}}>OK</button>
      </div>
    </div>
  );
}

/* ---------------- TURNI ----------------
   Il portale legge la STESSA settimana composta in gestione (pagina Turni,
   assegnazioni_turni_cloud): un solo sistema, niente griglie parallele. */
const GG = ["Lunedì","Martedì","Mercoledì","Giovedì","Venerdì","Sabato","Domenica"];

function settimanaDate(monday){ const out=[]; const base=new Date(monday+"T12:00:00"); for(let i=0;i<7;i++){ const x=new Date(base); x.setDate(x.getDate()+i); out.push(x.toLocaleDateString("it-IT",{day:"2-digit",month:"2-digit"})); } return out; }

function mioIdDaToken() {
  try {
    const t = localStorage.getItem("pt_token") || "";
    return JSON.parse(atob(t.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))).sub || "";
  } catch { return ""; }
}

function Turni() {
  const [dati, setDati] = useState(null);       // {settimana, assegnazioni, turni, dipendenti}
  const [tutti, setTutti] = useState(false);
  const [pref, setPref] = useState(null);       // {settimana, giorno} — preferenza riposo prossima settimana
  const [prefMsg, setPrefMsg] = useState("");
  const [mieDisp, setMieDisp] = useState([]);   // mie disponibilità a coprire il bar
  const [nd, setNd] = useState({ dal: "", al: "", fascia: "mattina", sostituisce_id: "" });
  const [dispMsg, setDispMsg] = useState("");
  const mioId = mioIdDaToken();
  const caricaDisp = () => api.get("/turni/disponibilita-bar").then((r)=>setMieDisp(r.data||[])).catch(()=>{});
  useEffect(() => {
    api.get("/turni/azienda/settimana").then((r)=>setDati(r.data)).catch(()=>setDati({assegnazioni:[],turni:[],dipendenti:[]}));
    api.get("/turni/preferenza-riposo").then((r)=>setPref(r.data)).catch(()=>{});
    caricaDisp();
  }, []);
  if (!dati) return <div className="spin">Caricamento…</div>;
  const date = dati.settimana ? settimanaDate(dati.settimana) : [];
  const turnoDiGiorno = (dipId, giorno) => {
    const a = (dati.assegnazioni||[]).find(x => x.dipendente_id === dipId && x.giorno === giorno);
    return a ? (dati.turni||[]).find(t => t.id === a.turno_id) : null;
  };
  const ChipT = ({t}) => t
    ? <span style={{background:(t.colore||"#5b7a6b")+"30", border:`1.5px solid ${t.colore||"#5b7a6b"}`, color:"#2a3329", borderRadius:8, padding:"3px 8px", fontWeight:700, fontSize:12, whiteSpace:"nowrap"}}>{t.nome}</span>
    : <span className="muted">—</span>;
  // Solo i colleghi che hanno almeno un turno nella settimana (via i non-turnisti)
  const colleghi = (dati.dipendenti||[]).filter(d => (dati.assegnazioni||[]).some(a => a.dipendente_id === d.id));
  const nomeDi = (d) => d.cognome ? `${d.cognome} ${d.nome?.[0]||""}.` : (d.nome_completo || d.nome);
  const salvaPref = async (giorno) => {
    const nuovo = pref?.giorno === giorno ? null : giorno; // ri-tocco = tolgo
    try {
      await api.post("/turni/preferenza-riposo", { settimana: pref?.settimana, giorno: nuovo });
      setPref(p => ({ ...(p||{}), giorno: nuovo }));
      setPrefMsg(nuovo ? "Preferenza inviata a chi fa i turni ✓" : "Preferenza tolta");
      setTimeout(()=>setPrefMsg(""), 2500);
    } catch { setPrefMsg("Errore, riprova"); }
  };
  return (
    <>
      <details className="card" style={{padding:"12px 14px"}}>
        <summary style={{cursor:"pointer",fontWeight:700,fontSize:14}}>📖 Come funziona</summary>
        <div className="muted" style={{fontSize:13,lineHeight:1.6,marginTop:8}}>
          Qui vedi <b>i tuoi turni</b> della settimana, aggiornati in tempo reale appena il responsabile li compone.
          Con <b>"Vedi i turni di tutti"</b> apri la tabella completa dei colleghi (la tua riga è evidenziata).
          Nel riquadro <b>💤 Riposo preferito</b> tocca il giorno in cui vorresti riposare la prossima settimana:
          la preferenza arriva subito a chi fa i turni, che ne tiene conto quando li genera. Non è un obbligo:
          l'ultima parola resta a chi compone i turni. Per ferie e permessi usa la scheda <b>Richieste</b>.
        </div>
      </details>
      <div className="card">
        <div className="row"><h3 style={{margin:0}}>I miei turni</h3>
          {dati.settimana && <span className="pill info">sett. {fmt(dati.settimana)}</span>}</div>
        {GG.map((g,i)=>(
          <div className="daycard" key={g}>
            <div><b>{g}</b> <span className="muted">{date[i]||""}</span></div>
            <div><ChipT t={turnoDiGiorno(mioId, g)}/></div>
          </div>
        ))}
      </div>
      <div className="card">
        <h3>💤 Riposo preferito · prossima settimana</h3>
        <div className="muted" style={{fontSize:12.5, marginBottom:8}}>
          Tocca il giorno in cui preferiresti riposare{pref?.settimana ? ` (settimana del ${fmt(pref.settimana)})` : ""}: chi
          compone i turni riceve la tua preferenza. Non è un obbligo: l'ultima parola resta a chi fa i turni.
        </div>
        <div style={{display:"flex", gap:6, flexWrap:"wrap"}}>
          {GG.map((g)=>(
            <button key={g} className="btn sm" onClick={()=>salvaPref(g)}
              style={pref?.giorno===g
                ? {background:"#3f5a4e", color:"#fff", borderRadius:8}
                : {background:"#eef1ea", color:"#2a3329", borderRadius:8}}>
              {g.slice(0,3)}{pref?.giorno===g ? " ✓" : ""}
            </button>
          ))}
        </div>
        {prefMsg && <div className="muted" style={{marginTop:8}}>{prefMsg}</div>}
      </div>
      {(dati.sostituti_bar||[]).includes(mioId) && (
        <div className="card">
          <h3>🆘 Copro il bar</h3>
          <div className="muted" style={{fontSize:12.5, marginBottom:8}}>
            Se manca un barista e vuoi coprirlo tu, scegli i giorni e la fascia: chi fa i turni
            riceve subito la tua disponibilità e riorganizza la sala.
          </div>
          <label>Al posto di</label>
          <select value={nd.sostituisce_id||""} onChange={(e)=>setNd({...nd, sostituisce_id:e.target.value})}>
            <option value="">— scegli il barista assente —</option>
            {(dati.baristi_rotazione||[]).map((id)=>{ const d=(dati.dipendenti||[]).find(x=>x.id===id); return d ? <option key={id} value={id}>{nomeDi(d)}</option> : null; })}
          </select>
          <div className="row" style={{gap:8, marginTop:8}}>
            <div style={{flex:1}}><label>Dal</label><input className="input" type="date" value={nd.dal} onChange={(e)=>setNd({...nd, dal:e.target.value})}/></div>
            <div style={{flex:1}}><label>Al</label><input className="input" type="date" value={nd.al} onChange={(e)=>setNd({...nd, al:e.target.value})}/></div>
          </div>
          <label style={{marginTop:8, display:"block"}}>Fascia (fondamentale)</label>
          <div style={{display:"flex", gap:6}}>
            {[["mattina","☀️ Mattina"],["pomeriggio","🌆 Pomeriggio"]].map(([v,l])=>(
              <button key={v} className="btn sm" onClick={()=>setNd({...nd, fascia:v})}
                style={nd.fascia===v?{background:"#3f5a4e",color:"#fff",borderRadius:8}:{background:"#eef1ea",color:"#2a3329",borderRadius:8}}>{l}</button>
            ))}
          </div>
          <button className="btn" style={{marginTop:10}} disabled={!nd.dal}
            onClick={async ()=>{
              try {
                await api.post("/turni/disponibilita-bar", { dal: nd.dal, al: nd.al || nd.dal, fascia: nd.fascia, sostituisce_id: nd.sostituisce_id || null });
                setNd({ dal:"", al:"", fascia:"mattina", sostituisce_id:"" }); setDispMsg("Disponibilità inviata ✓"); caricaDisp();
              } catch (e) { setDispMsg(e.response?.data?.message || "Errore, riprova"); }
              setTimeout(()=>setDispMsg(""), 3000);
            }}>Invia disponibilità</button>
          {dispMsg && <div className="muted" style={{marginTop:8}}>{dispMsg}</div>}
          {mieDisp.map((d)=>(
            <div className="daycard" key={d.id}>
              <div><b>bar {d.fascia==="pomeriggio"?"🌆 pomeriggio":"☀️ mattina"}</b>{d.sostituisce_nome?<span className="muted"> · al posto di {d.sostituisce_nome}</span>:null}
                <div className="muted">dal {fmt(d.dal)} al {fmt(d.al)}</div></div>
              <button className="btn gh sm" onClick={async ()=>{ try{ await api.delete(`/turni/disponibilita-bar/${d.id}`);}catch{} caricaDisp(); }}>Annulla</button>
            </div>
          ))}
        </div>
      )}
      {!tutti ? (
        <button className="btn sec" onClick={()=>setTutti(true)}><Users size={16}/> Vedi i turni di tutti</button>
      ) : (
        <div className="card"><h3>Tutti i colleghi · sett. {fmt(dati.settimana)}</h3>
          <div className="tgrid"><table>
            <thead><tr><th>Dip.</th>{GG.map((g,i)=><th key={g}>{g.slice(0,3)}<br/>{date[i]||""}</th>)}</tr></thead>
            <tbody>
              {colleghi.map((d)=>(
                <tr key={d.id} style={d.id===mioId?{background:"#eef1ea"}:undefined}>
                  <td className="name">{nomeDi(d)}</td>
                  {GG.map((g)=><td key={g}><ChipT t={turnoDiGiorno(d.id, g)}/></td>)}
                </tr>
              ))}
              {colleghi.length===0 && <tr><td colSpan={8} className="muted">Turni della settimana non ancora compilati.</td></tr>}
            </tbody>
          </table></div>
        </div>
      )}
    </>
  );
}

/* ---------------- BUSTE ---------------- */
function Buste() {
  const [buste, setBuste] = useState(null);
  const [aperta, setAperta] = useState(null);
  const [visionato, setVisionato] = useState(false);
  const load = useCallback(()=>{ api.get("/portale/buste").then((r)=>setBuste(r.data)).catch(()=>setBuste([])); },[]);
  useEffect(()=>{load();},[load]);
  const apri = (b) => { setVisionato(false); setAperta(b); };
  const chiudi = () => { setVisionato(false); setAperta(null); };
  const mm = (b)=>String(b.mese).padStart(2,"0");
  const visiona = async (b) => {
    setVisionato(true);                            // sblocca subito Accetto/Contesta
    const win = window.open("", "_blank");         // aperto nel gesto utente: niente blocco popup
    try {
      const r = await api.get(`/portale/buste/${b.id}/pdf`, { responseType: "blob", timeout: FILE_TIMEOUT });
      const url = URL.createObjectURL(r.data);
      if (win) { win.location = url; }
      else { const a=document.createElement("a"); a.href=url; a.download=b.filename||`busta_${b.mese}_${b.anno}.pdf`; a.click(); }
      setTimeout(()=>URL.revokeObjectURL(url), 60000);
    } catch { if (win) win.close(); alert("PDF non disponibile, riprova o contatta l'ufficio."); }
  };
  const accetta = async (b) => {
    try { await api.post(`/portale/buste/${b.id}/presa-visione`); } catch {}
    chiudi(); load();
    setTimeout(()=>alert("Presa visione registrata con data e ora."), 80);
  };
  const contesta = async (b) => {
    try { await api.post(`/portale/buste/${b.id}/contesta`); } catch {}
    try {
      const r = await api.get(`/portale/buste/${b.id}/modulo-contestazione`, { responseType: "blob", timeout: FILE_TIMEOUT });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a"); a.href=url; a.download=`contestazione_busta_${mm(b)}_${b.anno}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch {}
    chiudi(); load();
    setTimeout(()=>alert(
      "Contestazione registrata e inviata all'azienda (PEC).\n\n" +
      "Hai scaricato il modulo già intestato: barra le cause, compila le note e ricaricalo " +
      "nella sezione Documenti. La busta resta NON accettata."
    ), 80);
  };
  if (!buste) return <div className="spin">Caricamento…</div>;
  if (buste.length === 0) return <div className="empty">Nessuna busta paga disponibile.</div>;
  return (
    <>
      {buste.map((b)=>(
        <div className="card" key={b.id}>
          <div className="row">
            <div><b>{mm(b)}/{b.anno}</b>
              <div className="muted">Netto € {Number(b.netto||0).toFixed(2)}</div></div>
            {b.presa_visione ? <span className="pill ok"><Check size={11}/> Presa visione</span>
              : <span className="pill warn">Da leggere</span>}
          </div>
          <div className="row" style={{marginTop:10}}>
            <button className="btn sm" style={{width:"100%",justifyContent:"center"}} onClick={()=>apri(b)}>
              <Eye size={14}/> Apri busta
            </button>
          </div>
        </div>
      ))}
      {aperta && (
        <div onClick={chiudi}
             style={{position:"fixed",inset:0,background:"rgba(30,27,40,.5)",display:"flex",
                     alignItems:"center",justifyContent:"center",padding:18,zIndex:1000}}>
          <div onClick={(e)=>e.stopPropagation()}
               style={{background:"#fff",borderRadius:16,padding:20,maxWidth:440,width:"100%",
                       maxHeight:"85vh",overflowY:"auto",boxShadow:"0 20px 60px rgba(0,0,0,.3)"}}>
            <h3 style={{margin:"0 0 2px"}}>Busta paga {mm(aperta)}/{aperta.anno}</h3>
            <div className="muted">Netto € {Number(aperta.netto||0).toFixed(2)}</div>
            {aperta.acconto_cedolino ? (
              <div className="muted" style={{marginTop:2}}>
                Acconto già erogato € {Number(aperta.acconto_cedolino).toFixed(2)} · saldo € {Number(aperta.saldo_residuo||0).toFixed(2)}
              </div>
            ) : null}
            <div style={{background:"#eef3ef",border:"1px solid #d9e4dc",borderRadius:10,
                         padding:12,fontSize:13,lineHeight:1.55,margin:"12px 0"}}>
              Dichiaro di aver ricevuto e preso visione della busta paga relativa al mese
              di <b>{mm(aperta)}/{aperta.anno}</b>. La presente accettazione viene registrata
              con data e ora e ha valore di ricevuta. In caso di disaccordo posso contestare
              la busta tramite il modulo già intestato.
            </div>
            {aperta.presa_visione && (
              <div className="pill ok" style={{marginBottom:12}}><Check size={11}/> Già accettata il {aperta.presa_visione_il ? fmt(aperta.presa_visione_il) : ""}</div>
            )}
            <div style={{display:"flex",flexDirection:"column",gap:8}}>
              <button className="btn sec" onClick={()=>visiona(aperta)}><Download size={14}/> Apri / visiona la busta (PDF)</button>
              {aperta.presa_visione
                ? <button className="btn" onClick={chiudi}>Chiudi</button>
                : (visionato
                    ? <>
                        <button className="btn" onClick={()=>accetta(aperta)}><Check size={14}/> Accetto la busta</button>
                        <button className="btn gh" style={{color:"#a6531c",borderColor:"#e6c6a8"}} onClick={()=>contesta(aperta)}><AlertTriangle size={14}/> Contesta la busta</button>
                      </>
                    : <div className="muted" style={{textAlign:"center",fontSize:12,padding:"4px 0"}}>
                        Apri prima la busta: i pulsanti <b>Accetto</b> / <b>Contesta</b> compaiono dopo la visione.
                      </div>)}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/* ---------------- RICHIESTE ---------------- */
function Richieste() {
  const [tipo, setTipo] = useState("ferie_programmate");
  const [dettaglio, setDettaglio] = useState("");
  const [dal, setDal] = useState(""); const [al, setAl] = useState("");
  const [mie, setMie] = useState([]);
  const [msg, setMsg] = useState("");
  const conDate = (TIPI.find((t)=>t.v===tipo)||{}).date;
  const load = useCallback(()=>{ api.get("/richieste/mie").then((r)=>setMie(r.data)).catch(()=>{}); },[]);
  useEffect(()=>{load();},[load]);
  const invia = async () => {
    const dati = conDate ? { dal, al } : {};
    try {
      await api.post("/richieste", { tipo, dettaglio, dati });
      setDettaglio(""); setDal(""); setAl(""); setMsg("Richiesta inviata"); load();
      setTimeout(()=>setMsg(""),2500);
    } catch { setMsg("Errore invio"); }
  };
  return (
    <>
      <div className="card"><h3>Nuova richiesta</h3>
        <label>Tipo</label>
        <select value={tipo} onChange={(e)=>setTipo(e.target.value)}>
          {TIPI.map((t)=><option key={t.v} value={t.v}>{t.l}</option>)}
        </select>
        {conDate && <div className="row" style={{gap:8}}>
          <div style={{flex:1}}><label>Dal</label><input className="input" type="date" value={dal} onChange={(e)=>setDal(e.target.value)}/></div>
          <div style={{flex:1}}><label>Al</label><input className="input" type="date" value={al} onChange={(e)=>setAl(e.target.value)}/></div>
        </div>}
        <label>Note</label>
        <textarea rows={2} value={dettaglio} onChange={(e)=>setDettaglio(e.target.value)} placeholder="Dettagli…" />
        {msg && <div className="muted" style={{marginTop:8}}>{msg}</div>}
        <button className="btn" style={{marginTop:12}} onClick={invia}><Send size={15}/> Invia richiesta</button>
        <div className="muted" style={{marginTop:8,fontSize:12}}>
          Turni → Luigi (responsabile). Tutto il resto → amministratore.</div>
      </div>
      <div className="card"><h3>Le mie richieste</h3>
        {mie.length===0 && <div className="muted">Nessuna richiesta.</div>}
        {mie.map((r)=>(
          <div className="daycard" key={r.id}>
            <div><b>{tipoLabel(r.tipo)}</b><div className="muted">{r.dettaglio||"—"}</div></div>
            <span className={`pill ${r.stato==="approvata"?"ok":r.stato==="rifiutata"?"danger":"muted"}`}>{r.stato}</span>
          </div>
        ))}
      </div>
    </>
  );
}

/* ---------------- NOTIFICHE ---------------- */
function Notifiche({ onChange, onOpen }) {
  const [list, setList] = useState([]);
  const load = useCallback(()=>{ api.get("/notifiche").then((r)=>{setList(r.data);onChange&&onChange();}).catch(()=>{}); },[onChange]);
  useEffect(()=>{load();},[load]);
  const apri = async (n) => {
    if (!n.letta) { try { await api.post(`/notifiche/${n.id}/letta`); } catch {} }
    onOpen && onOpen(n);
    load();
  };
  if (list.length===0) return <div className="empty">Nessuna notifica.</div>;
  return list.map((n)=>(
    <div className="card" key={n.id} onClick={()=>apri(n)} style={{opacity:n.letta?.7:1, cursor:"pointer"}}>
      <div className="row"><b>{n.titolo}</b>{!n.letta&&<span className="pill info">nuova</span>}
        <span className="muted" style={{marginLeft:"auto",fontSize:12}}>apri ›</span></div>
      <div className="muted" style={{whiteSpace:"pre-line",marginTop:6}}>{n.messaggio}</div>
    </div>
  ));
}

/* ---------------- GESTIONE (responsabile turni) ---------------- */
function Gestione() {
  const [coda, setCoda] = useState([]);
  const [prefs, setPrefs] = useState([]);
  const loadCoda = useCallback(()=>{ api.get("/richieste?stato=aperta").then((r)=>setCoda(r.data)).catch(()=>{}); },[]);
  useEffect(()=>{
    loadCoda();
    api.get("/dipendenti-cloud/turni-preferenze").then((r)=>setPrefs(r.data||[])).catch(()=>{});
  },[loadCoda]);
  const risolvi = async (r, esito) => { await api.post(`/richieste/${r.id}/risolvi`,{esito}); loadCoda(); };
  return (
    <>
      <div className="card"><h3>Turni settimana</h3>
        <div className="muted" style={{fontSize:13}}>
          I turni si compongono nella pagina <b>Turni azienda</b>: vista semplice a caselle
          (un click = turno successivo tra le sponde del dipendente), copertura del giorno
          e preferenze di riposo dei colleghi già in evidenza. I dipendenti li vedono
          in tempo reale nella scheda Turni del portale.
        </div>
        <button className="btn" style={{marginTop:10}} onClick={()=>{window.location.href="/hr-turni";}}>
          <Calendar size={15}/> Apri Turni azienda
        </button>
      </div>
      <div className="card"><h3>💤 Preferenze di riposo ricevute</h3>
        {prefs.length===0 && <div className="muted">Nessuna preferenza inviata dai dipendenti.</div>}
        {prefs.slice(0,20).map((p,i)=>(
          <div className="daycard" key={i}>
            <div><b>{p.nome||"Dipendente"}</b><div className="muted">settimana del {fmt(p.settimana)}</div></div>
            <span className="pill info">{p.giorno}</span>
          </div>
        ))}
      </div>
      <div className="card"><h3>Richieste da gestire</h3>
        {coda.length===0 && <div className="muted">Nessuna richiesta aperta.</div>}
        {coda.map((r)=>(
          <div className="daycard" key={r.id}>
            <div><b>{r.dipendente_nome}</b><div className="muted">{tipoLabel(r.tipo)} · {r.dettaglio||"—"}</div></div>
            <div style={{display:"flex",gap:6}}>
              <button className="btn sm" onClick={()=>risolvi(r,"approvata")}><Check size={14}/></button>
              <button className="btn gh sm" onClick={()=>risolvi(r,"rifiutata")}>✕</button>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

/* ---------------- DOCUMENTI ---------------- */
function Documenti() {
  const [docs, setDocs] = useState(null);
  const [busy, setBusy] = useState("");
  const [reg, setReg] = useState(null);
  const load = useCallback(()=>{ api.get("/portale/documenti").then((r)=>setDocs(r.data)).catch(()=>setDocs([])); },[]);
  const loadReg = useCallback(()=>{ api.get("/portale/documenti/regolamento/stato").then((r)=>setReg(r.data)).catch(()=>setReg({disponibile:false})); },[]);
  useEffect(()=>{load();loadReg();},[load,loadReg]);
  const perTipo = (t)=> (docs||[]).filter((d)=>d.tipo===t);

  const blobDownload = (data, nome) => {
    const url = URL.createObjectURL(data);
    const a = document.createElement("a"); a.href=url; a.download=nome; a.click();
    URL.revokeObjectURL(url);
  };
  const scaricaModulo = async (tipo) => {
    try { const r = await api.get(`/portale/documenti/modulo/${tipo}`, {responseType:"blob", timeout: FILE_TIMEOUT});
      blobDownload(r.data, `modulo_${tipo}.pdf`);
    } catch { alert("Modulo non disponibile"); }
  };
  const scaricaFile = async (d) => {
    try { const r = await api.get(`/portale/documenti/${d.id}/file`, {responseType:"blob", timeout: FILE_TIMEOUT});
      blobDownload(r.data, d.nome_file || "documento");
    } catch { alert("Documento non disponibile"); }
  };
  const carica = async (tipo, ev) => {
    const file = ev.target.files?.[0]; if(!file) return;
    const fd = new FormData(); fd.append("tipo", tipo); fd.append("file", file);
    setBusy(tipo);
    try { await api.post("/portale/documenti/upload", fd, {headers:{"Content-Type":"multipart/form-data"}, timeout: FILE_TIMEOUT}); load(); }
    catch(e){ alert(e?.response?.data?.message || "Errore nel caricamento"); }
    setBusy(""); ev.target.value="";
  };
  const elimina = async (d) => {
    if(!window.confirm("Eliminare questo documento?")) return;
    try { await api.delete(`/portale/documenti/${d.id}`); load(); } catch {}
  };
  const scaricaRegolamento = async () => {
    try { const r = await api.get("/portale/documenti/regolamento/file", {responseType:"blob", timeout: FILE_TIMEOUT});
      blobDownload(r.data, "regolamento_interno.docx");
    } catch { alert("Regolamento non ancora pubblicato dall'azienda."); }
  };
  const accettaRegolamento = async () => {
    if(!window.confirm("Confermi di aver letto e di accettare il Regolamento Interno Aziendale?")) return;
    try { await api.post("/portale/documenti/regolamento/accetta"); loadReg(); }
    catch(e){ alert(e?.response?.data?.message || "Errore"); }
  };

  if (!docs) return <div className="spin">Caricamento…</div>;

  const FileRow = ({d, eliminabile}) => (
    <div className="row" style={{padding:"8px 0",borderTop:"1px solid #efeae0"}}>
      <div style={{minWidth:0}}>
        <div style={{fontWeight:600,whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>{d.nome_file}</div>
        <div className="muted" style={{fontSize:12}}>{fmt(d.caricato_il)} · {d.caricato_da==="azienda"?"dall'azienda":"caricato da te"}</div>
      </div>
      <div style={{display:"flex",gap:6}}>
        <button className="btn gh sm" onClick={()=>scaricaFile(d)}><Download size={14}/></button>
        {eliminabile && <button className="btn gh sm" onClick={()=>elimina(d)}><Trash2 size={14}/></button>}
      </div>
    </div>
  );
  const UploadBtn = ({tipo, label}) => (
    <label className="btn sec sm" style={{cursor:"pointer",margin:0}}>
      <Upload size={14}/> {busy===tipo ? "Carico…" : (label||"Carica file")}
      <input type="file" style={{display:"none"}} disabled={busy===tipo}
             onChange={(e)=>carica(tipo,e)} />
    </label>
  );

  const moduli = [
    { t:"contestazione", l:"Contestazione busta paga" },
    { t:"richiesta_ferie", l:"Richiesta ferie / permessi" },
    { t:"richiesta_acconto_tfr", l:"Richiesta acconto TFR" },
  ];

  return (
    <>
      {reg && reg.disponibile && (
        <div className="card" style={{borderLeft:"3px solid #5b7a6b"}}>
          <h3 style={{marginTop:0}}><FolderOpen size={16}/> Regolamento interno aziendale</h3>
          <div style={{display:"flex",gap:8,flexWrap:"wrap",marginBottom:8}}>
            <button className="btn gh sm" onClick={scaricaRegolamento}><Download size={14}/> Scarica e leggi</button>
          </div>
          {reg.accettato
            ? <div className="pill ok"><Check size={11}/> Accettato il {reg.accettato_il ? fmt(reg.accettato_il) : ""}</div>
            : <>
                <div className="muted" style={{fontSize:13,marginBottom:8}}>
                  Dopo averlo letto, conferma l'accettazione: viene registrata con data e ora.
                </div>
                <button className="btn" onClick={accettaRegolamento}><Check size={14}/> Dichiaro di aver letto e accetto</button>
              </>}
        </div>
      )}
      <div className="card">
        <h3 style={{marginTop:0}}><FolderOpen size={16}/> Moduli da compilare</h3>
        <div className="muted" style={{fontSize:13,marginBottom:6}}>
          Scarica il modulo, compilalo e ricaricalo qui. L'azienda lo riceverà.
        </div>
        {moduli.map((m)=>(
          <div key={m.t} style={{borderTop:"1px solid #efeae0",padding:"10px 0"}}>
            <div style={{fontWeight:700,marginBottom:6}}>{m.l}</div>
            <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
              <button className="btn gh sm" onClick={()=>scaricaModulo(m.t)}><Download size={14}/> Scarica modulo</button>
              <UploadBtn tipo={m.t} label="Invia compilato"/>
            </div>
            {perTipo(m.t).map((d)=><FileRow key={d.id} d={d} eliminabile={d.categoria==="caricato_dipendente"}/>)}
          </div>
        ))}
      </div>

      <div className="card">
        <h3 style={{marginTop:0}}>Certificazione Unica (CU)</h3>
        {perTipo("certificazione_unica").length===0
          ? <div className="muted" style={{fontSize:13}}>Nessuna CU caricata dall'azienda.</div>
          : perTipo("certificazione_unica").map((d)=><FileRow key={d.id} d={d}/>)}
      </div>

      <div className="card">
        <h3 style={{marginTop:0}}>Unilav</h3>
        {perTipo("unilav").length===0
          ? <div className="muted" style={{fontSize:13}}>Nessun Unilav caricato dall'azienda.</div>
          : perTipo("unilav").map((d)=><FileRow key={d.id} d={d}/>)}
      </div>

      <div className="card">
        <h3 style={{marginTop:0}}>Documenti di riconoscimento</h3>
        <div className="muted" style={{fontSize:13,marginBottom:8}}>
          Carica carta d'identità, codice fiscale o patente.
        </div>
        <UploadBtn tipo="documento_riconoscimento" label="Carica documento"/>
        {perTipo("documento_riconoscimento").map((d)=><FileRow key={d.id} d={d} eliminabile={d.categoria==="caricato_dipendente"}/>)}
      </div>
    </>
  );
}

/* ---------------- SHELL ---------------- */
/* ---------------- TIMBRATURA (geolocalizzata) ---------------- */
function Timbra() {
  const [stato, setStato] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const load = useCallback(() => {
    api.get("/timbrature/mie/oggi").then(r => setStato(r.data)).catch(() => setStato({ stato: "fuori", timbrature: [] }));
  }, []);
  useEffect(() => { load(); }, [load]);

  const timbra = (tipo) => {
    setMsg(""); setBusy(true);
    const invia = (lat, lng, acc) => {
      api.post("/timbrature", { tipo, lat, lng, accuracy: acc })
        .then(r => {
          const t = r.data.timbratura;
          let m = `Timbrata ${tipo} alle ${t.ora}` +
            (r.data.fuori_sede ? " — ⚠ fuori sede" : "") +
            (r.data.ore_lavorate != null ? ` · ${r.data.ore_lavorate} h` : "") + ".";
          if (tipo === "entrata") m += " La presenza sarà valida con l'uscita in sede dopo almeno 1 ora.";
          else m += r.data.validata ? " ✓ Presenza validata." : " ⚠ Presenza NON validata (serve almeno 1 ora in sede).";
          setMsg(m);
          load();
        })
        .catch(e => setMsg(e?.response?.data?.message || "Errore timbratura"))
        .finally(() => setBusy(false));
    };
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        p => invia(p.coords.latitude, p.coords.longitude, Math.round(p.coords.accuracy)),
        () => { setMsg("Posizione non disponibile: timbratura senza geolocalizzazione."); invia(null, null, null); },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 });
    } else invia(null, null, null);
  };

  const dentro = stato?.stato === "dentro";
  return (
    <div>
      <div className="card" style={{ textAlign: "center" }}>
        <h3>Timbratura</h3>
        <div className="muted" style={{ marginBottom: 14 }}>
          {dentro ? "Sei al lavoro — entrata registrata" : "Non sei in turno"}
        </div>
        <button className="btn" disabled={busy || dentro} onClick={() => timbra("entrata")}
          style={{ marginBottom: 10, background: dentro ? undefined : "var(--ok)" }}>
          <Clock size={16} /> {busy ? "Attendi…" : "Timbra ENTRATA"}
        </button>
        <button className="btn" disabled={busy || !dentro} onClick={() => timbra("uscita")}
          style={{ background: dentro ? "var(--danger)" : undefined }}>
          <Clock size={16} /> {busy ? "Attendi…" : "Timbra USCITA"}
        </button>
        {msg && <div className="muted" style={{ marginTop: 12 }}>{msg}</div>}
        <div className="muted" style={{ fontSize: 11, marginTop: 12 }}>
          <MapPin size={11} /> Viene registrata la posizione del telefono al momento della timbratura.
        </div>
      </div>
      <div className="card">
        <h3>Oggi</h3>
        {(stato?.timbrature || []).length === 0
          ? <div className="muted">Nessuna timbratura.</div>
          : stato.timbrature.map(t => (
            <div key={t.id} className="row" style={{ padding: "7px 0", borderBottom: "1px solid var(--line)" }}>
              <span><b>{t.tipo === "entrata" ? "Entrata" : "Uscita"}</b> · {t.ora}</span>
              {t.fuori_sede
                ? <span className="pill danger">fuori sede{t.distanza_m != null ? ` · ${t.distanza_m} m` : ""}</span>
                : (t.lat != null ? <span className="pill ok">in sede</span> : <span className="pill muted">no GPS</span>)}
            </div>
          ))}
      </div>
    </div>
  );
}

/* ============ VISTE ADMIN NEL PORTALE (il titolare dal telefono) ============ */
/* Riusano gli endpoint admin già esistenti: nessun sistema parallelo. */

function BusteAdmin() {
  const annoCorr = new Date().getFullYear();
  const [anno, setAnno] = useState(annoCorr);
  const [q, setQ] = useState("");
  const [buste, setBuste] = useState(null);
  const load = useCallback(() => {
    const p = new URLSearchParams();
    if (anno) p.set("anno", anno);
    if (q.trim()) p.set("q", q.trim());
    api.get(`/portale/buste?${p.toString()}`).then(r => setBuste(r.data)).catch(() => setBuste([]));
  }, [anno, q]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);
  const apri = async (b) => {
    const win = window.open("", "_blank");
    try {
      const r = await api.get(`/portale/buste/${b.id}/pdf`, { responseType: "blob", timeout: FILE_TIMEOUT });
      const url = URL.createObjectURL(r.data);
      if (win) win.location = url;
      else { const a = document.createElement("a"); a.href = url; a.download = b.filename || "busta.pdf"; a.click(); }
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch { if (win) win.close(); alert("PDF non disponibile."); }
  };
  const mm = (b) => String(b.mese).padStart(2, "0");
  return (<>
    <div className="card">
      <h3>Buste paga · tutti i dipendenti</h3>
      <div className="row" style={{ gap: 8, marginTop: 8 }}>
        <select value={anno} onChange={e => setAnno(Number(e.target.value))}>
          {Array.from({ length: 8 }, (_, i) => annoCorr - i).map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <input className="input" placeholder="Cerca dipendente…" value={q} onChange={e => setQ(e.target.value)} style={{ flex: 1 }} />
      </div>
    </div>
    {!buste && <div className="spin">Caricamento…</div>}
    {buste && buste.length === 0 && <div className="empty">Nessuna busta per i filtri scelti.</div>}
    {buste && buste.map(b => (
      <div className="card" key={b.id}>
        <div className="row">
          <div><b>{b.dipendente_nome}</b>
            <div className="muted">{mm(b)}/{b.anno} · Netto € {Number(b.netto || 0).toFixed(2)}</div></div>
          {b.presa_visione ? <span className="pill ok"><Check size={11} /> Vista</span> : <span className="pill warn">Da leggere</span>}
        </div>
        <button className="btn sm" style={{ width: "100%", justifyContent: "center", marginTop: 10 }} onClick={() => apri(b)}>
          <Eye size={14} /> Apri busta (PDF)
        </button>
      </div>
    ))}
  </>);
}

function AvvisiAdmin({ onChange }) {
  const [vista, setVista] = useState("attivi"); // attivi | archivio
  const [alerts, setAlerts] = useState([]);
  const [notif, setNotif] = useState([]);
  const [caricato, setCaricato] = useState(false);
  const archivio = vista === "archivio";
  const load = useCallback(() => {
    setCaricato(false);
    const statoAlert = archivio ? "risolto" : "aperto";
    api.get(`/dipendenti-cloud/alerts?stato=${statoAlert}`).then(r => setAlerts(r.data.alerts || [])).catch(() => setAlerts([]));
    api.get("/notifiche").then(r => { setNotif(r.data || []); onChange && onChange(); }).catch(() => setNotif([]))
      .finally(() => setCaricato(true));
  }, [onChange, archivio]);
  useEffect(() => { load(); }, [load]);
  const risolvi = async (a) => { try { await api.post(`/dipendenti-cloud/alerts/${a.id}/risolvi`); } catch {} load(); };
  const segnaLetta = async (n) => { if (!n.letta) { try { await api.post(`/notifiche/${n.id}/letta`); } catch {} } load(); };
  // In "attivi" mostro avvisi aperti + notifiche da leggere; in "archivio" i risolti + le notifiche già lette.
  const notifMostrate = notif.filter(n => archivio ? n.letta : !n.letta);
  const vuoto = caricato && alerts.length === 0 && notifMostrate.length === 0;
  const fmtData = (s) => (s ? `${s.slice(8,10)}/${s.slice(5,7)}/${s.slice(0,4)}` : "");
  return (<>
    <div className="card" style={{ paddingBottom: 10 }}>
      <h3 style={{ marginBottom: 8 }}>Avvisi</h3>
      <div className="row" style={{ gap: 8 }}>
        <button className={`btn sm ${archivio ? "gh" : ""}`} onClick={() => setVista("attivi")}>Da gestire</button>
        <button className={`btn sm ${archivio ? "" : "gh"}`} onClick={() => setVista("archivio")}>Archivio</button>
      </div>
      <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
        {archivio ? "Avvisi già gestiti e notifiche lette: restano qui, non vengono cancellati." : "Avvisi e notifiche da leggere. Una volta gestiti vanno in Archivio."}
      </div>
    </div>
    {!caricato && <div className="spin">Caricamento…</div>}
    {vuoto && <div className="empty">{archivio ? "Archivio vuoto." : "Nessun avviso da gestire. Tutto in regola."}</div>}
    {alerts.length > 0 && <div className="card"><h3>Scadenze &amp; alert dipendenti</h3>
      {alerts.map(a => (
        <div className="daycard" key={a.id} style={{ alignItems: "flex-start" }}>
          <div><b>{a.titolo || a.tipo || "Avviso"}</b>
            <div className="muted" style={{ whiteSpace: "pre-line" }}>{a.messaggio || a.descrizione || ""}</div>
            {archivio && a.resolved_at && <div className="muted" style={{ fontSize: 11 }}>Gestito il {fmtData(a.resolved_at)}</div>}
          </div>
          {!archivio && <button className="btn sm gh" onClick={() => risolvi(a)}>Risolvi</button>}
        </div>
      ))}
    </div>}
    {notifMostrate.length > 0 && <div className="card"><h3>Notifiche</h3>
      {notifMostrate.map(n => (
        <div className="daycard" key={n.id} onClick={() => !archivio && segnaLetta(n)} style={{ opacity: archivio ? .7 : 1, cursor: archivio ? "default" : "pointer" }}>
          <div><b>{n.titolo}</b><div className="muted" style={{ whiteSpace: "pre-line" }}>{n.messaggio}</div></div>
          {!n.letta && <span className="pill info">nuova</span>}
        </div>
      ))}
    </div>}
  </>);
}

function RichiesteAdmin() {
  const [list, setList] = useState(null);
  const [filtro, setFiltro] = useState("aperta");
  const load = useCallback(() => {
    const p = filtro ? `?stato=${filtro}` : "";
    api.get(`/richieste${p}`).then(r => setList(r.data)).catch(() => setList([]));
  }, [filtro]);
  useEffect(() => { load(); }, [load]);
  const risolvi = async (r, esito) => { try { await api.post(`/richieste/${r.id}/risolvi`, { esito }); } catch {} load(); };
  return (<>
    <div className="card"><h3>Richieste dipendenti</h3>
      <div className="row" style={{ gap: 6, marginTop: 8, flexWrap: "wrap" }}>
        {[["aperta", "Da gestire"], ["approvata", "Approvate"], ["rifiutata", "Rifiutate"], ["", "Tutte"]].map(([v, l]) =>
          <button key={v} className={`btn sm ${filtro === v ? "" : "gh"}`} onClick={() => setFiltro(v)}>{l}</button>)}
      </div>
    </div>
    {!list && <div className="spin">Caricamento…</div>}
    {list && list.length === 0 && <div className="empty">Nessuna richiesta.</div>}
    {list && list.map(r => (
      <div className="card" key={r.id}>
        <div className="row">
          <div><b>{r.dipendente_nome || "Dipendente"}</b>
            <div className="muted">{tipoLabel(r.tipo)}{r.dettaglio ? ` · ${r.dettaglio}` : ""}
              {r.dati?.dal ? ` · ${fmt(r.dati.dal)}→${fmt(r.dati.al)}` : ""}</div></div>
          <span className={`pill ${r.stato === "approvata" ? "ok" : r.stato === "rifiutata" ? "danger" : "muted"}`}>{r.stato}</span>
        </div>
        {r.stato === "aperta" && <div className="row" style={{ gap: 8, marginTop: 10 }}>
          <button className="btn sm" style={{ flex: 1, justifyContent: "center" }} onClick={() => risolvi(r, "approvata")}><Check size={14} /> Approva</button>
          <button className="btn sm gh" style={{ flex: 1, justifyContent: "center", color: "#a6531c", borderColor: "#e6c6a8" }} onClick={() => risolvi(r, "rifiutata")}>Rifiuta</button>
        </div>}
      </div>
    ))}
  </>);
}

function DocumentiAdmin() {
  const [docs, setDocs] = useState(null);
  const [q, setQ] = useState("");
  useEffect(() => { api.get("/dipendenti-cloud/documenti").then(r => setDocs(r.data || [])).catch(() => setDocs([])); }, []);
  const scarica = async (d) => {
    const win = window.open("", "_blank");
    try {
      const r = await api.get(`/dipendenti-cloud/documenti/${d.id}/file`, { responseType: "blob", timeout: FILE_TIMEOUT });
      const url = URL.createObjectURL(r.data);
      if (win) win.location = url;
      else { const a = document.createElement("a"); a.href = url; a.download = d.filename || "documento"; a.click(); }
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch { if (win) win.close(); alert("File non disponibile."); }
  };
  const filtered = (docs || []).filter(d => {
    const s = q.trim().toLowerCase();
    if (!s) return true;
    return `${d.dipendente_nome || ""} ${d.tipo || d.categoria || ""} ${d.filename || ""}`.toLowerCase().includes(s);
  });
  const gruppi = {};
  filtered.forEach(d => { const k = d.dipendente_nome || "Senza dipendente"; (gruppi[k] = gruppi[k] || []).push(d); });
  return (<>
    <div className="card"><h3>Documenti · tutti i dipendenti</h3>
      <input className="input" placeholder="Cerca dipendente / tipo…" value={q} onChange={e => setQ(e.target.value)} style={{ marginTop: 8 }} />
    </div>
    {!docs && <div className="spin">Caricamento…</div>}
    {docs && Object.keys(gruppi).length === 0 && <div className="empty">Nessun documento.</div>}
    {docs && Object.entries(gruppi).sort((a, b) => a[0].localeCompare(b[0])).map(([nome, lista]) => (
      <div className="card" key={nome}>
        <h3 style={{ marginBottom: 6 }}>{nome}</h3>
        {lista.map(d => (
          <div className="daycard" key={d.id}>
            <div><b>{d.tipo || d.categoria || "Documento"}</b><div className="muted">{d.filename || "—"}</div></div>
            <button className="btn sm gh" onClick={() => scarica(d)}><Download size={14} /> Apri</button>
          </div>
        ))}
      </div>
    ))}
  </>);
}

function TimbraAdmin() {
  const oggi = new Date().toISOString().slice(0, 10);
  const [data, setData] = useState(oggi);
  const [ts, setTs] = useState(null);
  useEffect(() => {
    api.get(`/timbrature?data=${data}`).then(r => setTs(r.data.timbrature || [])).catch(() => setTs([]));
  }, [data]);
  const gruppi = {};
  (ts || []).forEach(t => { const k = t.dipendente_nome || t.dipendente_id || "—"; (gruppi[k] = gruppi[k] || []).push(t); });
  return (<>
    <div className="card"><h3>Timbrature · tutti i dipendenti</h3>
      <input className="input" type="date" value={data} onChange={e => setData(e.target.value)} style={{ marginTop: 8 }} />
    </div>
    {!ts && <div className="spin">Caricamento…</div>}
    {ts && Object.keys(gruppi).length === 0 && <div className="empty">Nessuna timbratura per questa data.</div>}
    {ts && Object.entries(gruppi).sort((a, b) => a[0].localeCompare(b[0])).map(([nome, lista]) => (
      <div className="card" key={nome}>
        <div className="row"><b>{nome}</b></div>
        {lista.sort((a, b) => (a.ora || "").localeCompare(b.ora || "")).map((t, i) => (
          <div className="daycard" key={i}>
            <div><b style={{ color: t.tipo === "entrata" ? "#3d8168" : "#b04a3a" }}>{t.tipo}</b>
              <div className="muted">{t.ora || ""}{t.fuori_sede ? " · ⚠ fuori sede" : ""}</div></div>
          </div>
        ))}
      </div>
    ))}
  </>);
}

export default function PortaleDipendente() {
  // La sessione dura quanto il token (7 giorni, backend/app/config.py): su un
  // dispositivo condiviso in cucina/pasticceria chiedere il PIN ad ogni
  // apertura/reload era scomodissimo — richiesta esplicita del titolare di
  // renderlo persistente. Il PIN resta comunque richiesto quando il token
  // scade o dopo "Esci", e resta il vero controllo di sicurezza lato server
  // su ogni chiamata API.
  const [logged, setLogged] = useState(() => tokenValido(localStorage.getItem(TK)));
  // Timbra e' l'azione piu' frequente in assoluto (piu' volte al giorno, ogni
  // dipendente): e' la tab di apertura, non Turni, cosi' non serve un tap in piu'.
  const [tab, setTab] = useState("timbra");
  const [nonLette, setNonLette] = useState(0);
  const [connErr, setConnErr] = useState(false);
  const role = localStorage.getItem("pt_role");
  const isGestore = role === "responsabile_turni" || role === "admin";

  useEffect(() => {
    _connListeners.push(setConnErr);
    return () => { _connListeners = _connListeners.filter((fn) => fn !== setConnErr); };
  }, []);

  // Un 401 dal server (token rifiutato: segreto ruotato, o dipendente cessato/
  // disattivato nel frattempo) riporta subito al login invece di lasciare il
  // portale aperto con ogni chiamata che fallisce in silenzio (trovato da una
  // review automatica sulla sessione persistente sopra).
  useEffect(() => {
    const f = () => setLogged(false);
    _authListeners.push(f);
    return () => { _authListeners = _authListeners.filter((fn) => fn !== f); };
  }, []);

  // Il controllo sopra scatta solo alla PROSSIMA chiamata API: su un
  // dispositivo condiviso, se il token scade mentre il portale resta aperto
  // in background (tab non chiusa, telefono/tablet bloccato), riaprendolo
  // mostrerebbe ancora i dati gia' caricati della sessione precedente —
  // buste paga, documenti — finche' qualcosa non fa una richiesta. Rivalida
  // subito la scadenza quando la pagina torna visibile/in focus (trovato da
  // una review automatica).
  useEffect(() => {
    const rivalida = () => {
      if (document.visibilityState !== "hidden" && !tokenValido(localStorage.getItem(TK))) {
        setLogged(false);
      }
    };
    document.addEventListener("visibilitychange", rivalida);
    window.addEventListener("focus", rivalida);
    return () => {
      document.removeEventListener("visibilitychange", rivalida);
      window.removeEventListener("focus", rivalida);
    };
  }, []);

  // Il controllo sopra scatta su un evento di focus/visibilita': se il
  // tablet resta acceso con il portale sempre in primo piano ininterrottamente
  // (mai in background) fino alla scadenza, nessuno di quegli eventi si
  // verifica. Un timer pianificato sulla scadenza esatta del token chiude
  // comunque la sessione, indipendentemente da come cambia il focus (trovato
  // da una review automatica). Riarmato ad ogni nuovo login (`logged` passa
  // a true con un token diverso, quindi una scadenza diversa).
  useEffect(() => {
    if (!logged) return;
    const ms = msAllaScadenza(localStorage.getItem(TK));
    if (ms === null || ms <= 0) return;
    const id = setTimeout(() => setLogged(false), ms);
    return () => clearTimeout(id);
  }, [logged]);

  // Ogni tab monta UN SOLO componente alla volta (nessuna richiesta in
  // background per una tab abbandonata: niente polling/setInterval in tutto
  // il portale) — quindi un fallimento agganciato alla tab appena lasciata
  // non puo' piu' guarire da solo (nessuno la richiede piu'), e il banner
  // restava acceso per sempre finche' non si tornava proprio li' o si
  // ricaricava la pagina (trovato dal giro di review successivo a quello che
  // aveva introdotto il tracciamento per chiave). Cambiare tab azzera i
  // fallimenti registrati: quelli della tab lasciata non contano piu' (vista
  // non piu' montata), quella nuova riparte pulita e si riaggiungera' da
  // sola se fallisce a sua volta.
  useEffect(() => { _azzeraConnessione(); }, [tab]);

  const refreshBadge = useCallback(()=>{ api.get("/notifiche/conteggio").then((r)=>setNonLette(r.data.non_lette)).catch(()=>{}); },[]);
  useEffect(()=>{ if(logged) refreshBadge(); },[logged,tab,refreshBadge]);

  if (!logged) return <div className="pt-root"><Login onLogin={()=>setLogged(true)} /></div>;
  const logout = () => { localStorage.removeItem(TK); localStorage.removeItem("pt_role"); localStorage.removeItem("pt_name"); setLogged(false); };

  const tabs = [
    { k:"timbra", l:"Timbra", icon:Clock },
    { k:"turni", l:"Turni", icon:Calendar },
    { k:"buste", l:"Buste", icon:FileText },
    { k:"documenti", l:"Documenti", icon:FolderOpen },
    { k:"richieste", l:"Richieste", icon:Inbox },
    { k:"notifiche", l:"Avvisi", icon:Bell },
    ...(isGestore ? [{ k:"gestione", l:"Gestione", icon:Settings }] : []),
  ];

  return (
    <div className="pt-root">
      {connErr && (
        <div className="pt-connerr">
          Connessione assente — riprova
          <button onClick={() => window.location.reload()}>Ricarica</button>
        </div>
      )}
      <div className="pt-head">
        <h1>Portale Dipendenti</h1>
        <div className="sub">{localStorage.getItem("pt_name")}{isGestore?` · ${role==="admin"?"admin":"responsabile turni"}`:""}</div>
        {role==="responsabile_turni" && <button className="logout" style={{right:96,background:"#3f5a4e",color:"#fff"}} onClick={()=>{window.location.href="/hr-turni";}}><Grid3X3 size={13}/> Turni azienda</button>}
        <button className="logout" onClick={logout}><LogOut size={13}/> Esci</button>
      </div>
      <div className="pt-body">
        {tab==="timbra" && (role==="admin" ? <TimbraAdmin/> : <Timbra/>)}
        {tab==="turni" && <Turni/>}
        {tab==="buste" && (role==="admin" ? <BusteAdmin/> : <Buste/>)}
        {tab==="documenti" && (role==="admin" ? <DocumentiAdmin/> : <Documenti/>)}
        {tab==="richieste" && (role==="admin" ? <RichiesteAdmin/> : <Richieste/>)}
        {tab==="notifiche" && (role==="admin"
          ? <AvvisiAdmin onChange={refreshBadge}/>
          : <Notifiche onChange={refreshBadge} onOpen={(n)=>{
              const t = n.tipo;
              if (t==="richiesta") setTab("richieste");
              else if (t==="richiesta_risolta") setTab("richieste");
              else if (t==="turni" || t==="turno_pubblicato") setTab("turni");
              else if (t==="busta_paga") setTab("buste");
            }}/>)}
        {tab==="gestione" && isGestore && <Gestione/>}
      </div>
      <div className="tabbar">
        {tabs.map((t)=>{
          const I=t.icon;
          return <button key={t.k} className={`tab ${tab===t.k?"active":""}`} onClick={()=>setTab(t.k)}>
            <I size={20}/>{t.l}
            {t.k==="notifiche" && nonLette>0 && <span className="dot">{nonLette}</span>}
          </button>;
        })}
      </div>
    </div>
  );
}
