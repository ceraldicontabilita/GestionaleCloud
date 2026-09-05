/**
 * BackofficeView.jsx — Backoffice Amministratore Ceraldi Group
 *
 * 3 sezioni in una pagina sola:
 *   1. PRODOTTI & SOGLIE  — tabella con quantità riordino e alert sotto scorta
 *   2. FORNITORI          — lista da anagrafica, qualifica/escludi per magazzino
 *   3. RICETTE            — form schematico per creare/modificare ricette
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { conferma } from "../../utils/conferma";
import axios from "axios";
import { withToken } from "../../utils/constants";
import { getOperatoreNome } from "../../auth";
import { stampaDoc } from "../../utils/stampa";
import { ModalRegistraLotto } from "./tablet/ModalRegistraLotto";
import { SchedaEditorModal, VerificaDisponibilitaModal } from "./RicetteDashboardView";
import SchedaRicettaChiaraModal from "./SchedaRicettaChiaraModal";
import FormRicetta, { REPARTI } from "./backoffice/FormRicetta";
import TabProdotti from "./backoffice/TabProdotti";
import TabFornitori from "./backoffice/TabFornitori";
import { toast } from "./backoffice/toastBackoffice";

const API = process.env.REACT_APP_LOTTI_BACKEND_URL + "/api";
const BACKEND = process.env.REACT_APP_LOTTI_BACKEND_URL || "";
// foto_url è relativo (/api/foto/..): per <img>/background va reso assoluto sul backend.
const fotoSrc = (u) => (u ? (/^https?:/.test(u) ? u : BACKEND + u) : "");
const ORIGINI_FORNITORE = new Set(["saima", "mepa", "acquaviva", "vandemoortele", "tremarie", "tre_marie", "sammontana", "bindi", "alfa", "alpha", "il_pasticcere"]);
const riferimentoFornitoreNonAttivo = (r) =>
  r?.visibile_tablet !== true && (
    ORIGINI_FORNITORE.has(String(r?.origine || "").toLowerCase()) ||
    r?.ricettario_saima_id || r?.ricettario_mepa_id || r?.ricettario_acquaviva_id || r?.ricettario_fornitore_id
  );


// ══════════════════════════════════════════════════════════════════
// 3. RICETTE — form schematico e semplice
// ══════════════════════════════════════════════════════════════════

function TabRicette() {
  const [ricette,    setRicette]    = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [search,     setSearch]     = useState("");
  const [repFiltro,  setRepFiltro]  = useState("tutti");
  const [editRicetta,setEditRicetta]= useState(null);   // null=lista, {}=nuova, {id}=modifica
  const [showForm,   setShowForm]   = useState(false);
  const [produciR,   setProduciR]   = useState(null);   // ricetta da produrre (modal)
  const [verificaR,  setVerificaR]  = useState(null);   // fatture/magazzino/sostituzioni
  const [schedaR,    setSchedaR]    = useState(null);   // ricetta di cui compilare la scheda
  const [dettaglioR, setDettaglioR] = useState(null);   // scheda chiara unica
  const [promuovendo, setPromuovendo] = useState(false);
  // Frigoriferi/congelatori REALI configurati (Attrezzature), non la lista
  // generica di fallback — richiesta Enzo 20/07/2026.
  const [attrezzature, setAttrezzature] = useState({ frigoriferi: [], congelatori: [] });
  useEffect(() => {
    axios.get(`${API}/attrezzature/`)
      .then(r => setAttrezzature(r.data || { frigoriferi: [], congelatori: [] }))
      .catch(() => {});
  }, []);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/ricette-unificate`);
      setRicette(r.data || []);
    } catch { toast("Errore caricamento ricette","err"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  // Apertura diretta di una ricetta nell'editor (es. dal pulsante Modifica del tablet).
  useEffect(() => {
    let id;
    try { id = sessionStorage.getItem("apri_ricetta_id"); } catch (_) { id = null; }
    if (!id) return;
    try { sessionStorage.removeItem("apri_ricetta_id"); } catch (_) { /* no-op */ }
    (async () => {
      try {
        const r = await axios.get(`${API}/ricette/${id}`);
        if (r.data) { setEditRicetta(r.data); setShowForm(true); }
      } catch { /* ignora */ }
    })();
  }, []);

  const elimina = async (id, nome) => {
    if (!await conferma(`Eliminare "${nome}"?`)) return false;
    try {
      await axios.delete(`${API}/ricette/${id}`);
      setRicette(r => r.filter(x => x.id !== id));
      toast("Ricetta eliminata");
      return true;
    } catch { toast("Errore eliminazione","err"); return false; }
  };

  const [importando, setImportando] = useState(false);
  const importaTracciabilita = async () => {
    if (!await conferma("Aggiorno il ricettario con i quattro file Excel Ceraldi?\n\nLe ricette nuove verranno aggiunte. Foto, nomi e ingredienti già corretti a mano non saranno sovrascritti.")) return;
    setImportando(true);
    try {
      const r = await axios.post(`${API}/ricette/importa-excel?anteprima=false`, null, { timeout: 120000 });
      const d = r.data || {};
      toast(`Ricettari aggiornati ✅ — ${d.create||0} nuove, ${d.aggiornate||0} arricchite, ${d.invariate||0} già a posto`);
      carica();
    } catch (e) {
      const det = e?.response?.data?.detail;
      toast(`Errore importazione${typeof det === "string" ? ": " + det : ""}`, "err");
    } finally { setImportando(false); }
  };

  // ── Proposta ingredienti per TUTTE le ricette ancora vuote (Enzo 25/07/2026).
  // Lavora a blocchi: ogni proposta passa dal motore AI (secondi), quindi il
  // frontend richiama finché il backend non dice che non ne restano.
  const [compilando, setCompilando] = useState(false);
  const [avanzamento, setAvanzamento] = useState("");
  const proponiTutte = async () => {
    let da = 0, pre = {};
    try {
      const r0 = await axios.get(`${API}/food-cost/ricette-senza-ingredienti`);
      pre = r0.data || {};
      da = pre.da_compilare || 0;
    } catch { toast("Non riesco a leggere l'elenco delle ricette", "err"); return; }
    if (!da) { toast("Tutte le ricette hanno già ingredienti e dosi"); return; }
    const senzaIng = pre?.senza_ingredienti ?? 0, senzaQta = pre?.senza_quantita ?? 0;
    if (!await conferma(
      `Compilo ${da} ricette?\n\n` +
      `• ${senzaIng} senza ingredienti\n• ${senzaQta} con ingredienti ma senza dosi\n\n` +
      "Le dosi escono in misura da laboratorio: l'ingrediente principale portato a 1 kg " +
      "(150 g di farina diventano 1 kg, 500 g di riso diventano 1 kg) e tutto il resto " +
      "riscalato di conseguenza.\n\n" +
      "Le ricette già complete NON vengono toccate. Quelle compilate restano segnate " +
      "come proposta automatica: controllale con calma."
    )) return;

    setCompilando(true);
    let fatte = 0, saltate = 0;
    try {
      for (let giro = 0; giro < 60; giro++) {   // tetto di sicurezza
        const r = await axios.post(`${API}/food-cost/proponi-ingredienti-tutte`,
          { limite: 15, normalizza_un_kg: true }, { timeout: 600000 });
        const d = r.data || {};
        fatte += d.compilate || 0;
        saltate += (d.senza_proposta || []).length;
        setAvanzamento(`${fatte} compilate, ne restano ${d.restanti || 0}…`);
        if (!d.restanti || (!d.compilate && !(d.senza_proposta || []).length)) break;
      }
      toast(`Fatto: ${fatte} ricette compilate${saltate ? `, ${saltate} senza proposta (da fare a mano)` : ""}`);
      carica();
    } catch (e) {
      const det = e?.response?.data?.detail;
      toast(`Errore compilazione${typeof det === "string" ? ": " + det : ""}`, "err");
    } finally { setCompilando(false); setAvanzamento(""); }
  };

  const filtrate = ricette.filter(r => {
    if (repFiltro !== "tutti" && r.reparto !== repFiltro) return false;
    if (search && !r.nome?.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  }).sort((a,b) => (a.nome||"").localeCompare(b.nome||"","it"));

  const rendiOperativa = async (ricetta) => {
    if (!ricetta?.archivio_id || promuovendo) return;
    setPromuovendo(true);
    try {
      const r = await axios.post(`${API}/ricette-archivio/${ricetta.tipo_archivio || "recipe"}/${ricetta.archivio_id}/rendi-operativa`);
      const operativa = r.data?.ricetta;
      toast(r.data?.creata ? "Ricetta inserita: ora puoi modificarla e produrla" : "La ricetta operativa esiste già");
      await carica();
      if (operativa) setDettaglioR(operativa);
    } catch (e) {
      const dettaglio = e?.response?.data?.detail;
      toast(typeof dettaglio === "string" ? dettaglio : "Errore inserimento ricetta", "err");
    } finally { setPromuovendo(false); }
  };

  return (
    <div>
      {/* Header */}
      <div style={{display:"flex",gap:10,marginBottom:16,alignItems:"center",flexWrap:"wrap"}}>
        <input value={search} onChange={e=>setSearch(e.target.value)}
          placeholder="🔍 Cerca ricetta…"
          style={{padding:"8px 14px",border:"1.5px solid var(--border)",borderRadius:10,fontSize:14,fontFamily:"var(--font)",flex:1,minWidth:200}}/>
        <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
          {["tutti",...REPARTI].map(r=>(
            <button key={r} onClick={()=>setRepFiltro(r)}
              style={{padding:"7px 12px",borderRadius:10,border:"1.5px solid",fontFamily:"var(--font)",fontSize:12,fontWeight:600,cursor:"pointer",
                background:repFiltro===r?"var(--primary)":"var(--card)",
                color:repFiltro===r?"#fff":"var(--text-2)",
                borderColor:repFiltro===r?"var(--primary)":"var(--border)"}}>
              {r.charAt(0).toUpperCase()+r.slice(1)}
            </button>
          ))}
        </div>
        {/* Azione una-tantum: discreta, non deve competere con «Nuova ricetta» */}
        <button onClick={importaTracciabilita} disabled={importando}
          title="Importa e aggiorna i quattro ricettari Excel Ceraldi senza perdere le modifiche già fatte"
          style={{padding:"8px 12px",border:"1.5px solid var(--border)",borderRadius:10,background:"var(--card)",color:"var(--text-2)",fontWeight:700,fontSize:12,cursor:importando?"wait":"pointer",fontFamily:"var(--font)",whiteSpace:"nowrap"}}>
          {importando ? "Aggiorno…" : "📥 Aggiorna ricettari Excel"}
        </button>
        <button onClick={proponiTutte} disabled={compilando}
          title="Compila ingredienti e dosi delle ricette incomplete, con l'ingrediente principale portato a 1 kg (non tocca quelle già complete)"
          style={{padding:"8px 12px",border:"1.5px solid #cfdfd5",borderRadius:10,background:"#f2f6f3",color:"#3f5a4e",fontWeight:700,fontSize:12,cursor:compilando?"wait":"pointer",fontFamily:"var(--font)",whiteSpace:"nowrap"}}>
          {compilando ? (avanzamento || "Compilo…") : "Compila ricette incomplete (dosi a 1 kg)"}
        </button>
        <button onClick={() => { setEditRicetta(null); setShowForm(true); }}
          style={{padding:"8px 18px",border:"none",borderRadius:10,background:"var(--primary-grad)",color:"#fff",fontWeight:700,fontSize:13,cursor:"pointer",fontFamily:"var(--font)",whiteSpace:"nowrap"}}>
          + Nuova ricetta
        </button>
      </div>

      {loading ? (
        <div style={{textAlign:"center",padding:"40px",color:"var(--text-3)"}}>Caricamento…</div>
      ) : (
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill, minmax(210px, 1fr))",gap:14}}>
          {filtrate.map(r => {
            const foto = r.foto_url || r.foto || r.immagine || "";
            const emoji = r.reparto==="pasticceria"?"🍰":r.reparto==="rosticceria"?"🥙":r.reparto==="bar"?"☕":"🍽️";
            const soloLettura = r.origine === "archivio" || r.sola_lettura;
            const riferimentoFornitore = riferimentoFornitoreNonAttivo(r);
            return (
            <div key={r.id} style={{background:soloLettura?"#fffaf1":"var(--card)",border:`1px solid ${soloLettura?"#e2d8ca":"transparent"}`,borderRadius:16,boxShadow:"var(--shadow-list)",overflow:"hidden",display:"flex",flexDirection:"column",position:"relative"}}>
              {!soloLettura && <button
                type="button"
                aria-label={`Elimina ${r.nome}`}
                title="Elimina ricetta (resta recuperabile)"
                onClick={() => elimina(r.id, r.nome)}
                style={{position:"absolute",right:8,top:8,zIndex:3,width:34,height:34,border:"1px solid rgba(255,255,255,.65)",borderRadius:"50%",background:"rgba(35,30,25,.72)",color:"#fff",fontSize:22,lineHeight:1,cursor:"pointer",display:"grid",placeItems:"center"}}>
                ×
              </button>}
              {/* Foto / copertina */}
              <div style={{
                height:120,
                background: foto ? `center/cover no-repeat url('${fotoSrc(foto)}')` : "var(--primary-soft)",
                display:"grid",placeItems:"center",position:"relative",
              }}>
                {!foto && <span style={{fontSize:46}}>{emoji}</span>}
                <span style={{position:"absolute",top:8,left:8,fontSize:10,fontWeight:800,textTransform:"uppercase",letterSpacing:.5,
                  background:"rgba(0,0,0,.55)",color:"#fff",borderRadius:6,padding:"3px 8px"}}>
                  {soloLettura ? (r.tipo_archivio === "component" ? "Preparazione base" : "Pasticceria") : (r.reparto || "—")}
                </span>
              </div>
              {/* Corpo */}
              <div style={{padding:"12px 14px",display:"flex",flexDirection:"column",gap:8,flex:1}}>
                <div style={{fontWeight:800,fontSize:15,color:"var(--text)",lineHeight:1.3,
                  display:"-webkit-box",WebkitLineClamp:2,WebkitBoxOrient:"vertical",overflow:"hidden",minHeight:"2.6em"}}>
                  {r.nome}
                </div>
                <div style={{fontSize:12,color:"var(--text-2)",display:"flex",gap:"4px 10px",flexWrap:"wrap"}}>
                  {r.porzioni > 0 && <span>{r.porzioni} pz</span>}
                  {r.ingredienti?.length > 0 && <span>· {r.ingredienti.length} ingr.</span>}
                  {r.prezzo_vendita > 0 && <span>· €{r.prezzo_vendita}</span>}
                  {r.fonte_archivio && <span>· {r.fonte_archivio}</span>}
                </div>
                {riferimentoFornitore && <div style={{fontSize:11,fontWeight:800,color:"#8a5a14",background:"#fff4d8",border:"1px solid #ead19a",borderRadius:8,padding:"6px 8px"}}>
                  Ricetta fornitore: non compare in produzione finché non la adatti e salvi
                </div>}
                {/* Azioni visibili richieste: produzione, modifica immediata e scheda. */}
                <div style={{display:"flex",flexDirection:"column",gap:6,marginTop:"auto"}}>
                  {!soloLettura && !riferimentoFornitore && <button
                    onClick={() => setProduciR(r)}
                    style={{width:"100%",padding:"9px 0",border:"none",borderRadius:8,background:"var(--primary-grad)",color:"#fff",fontFamily:"var(--font)",fontSize:13,fontWeight:800,cursor:"pointer"}}>
                    🏭 Produci
                  </button>}
                  {!soloLettura && !riferimentoFornitore && <button
                    onClick={() => setVerificaR(r)}
                    style={{width:"100%",padding:"9px 0",border:"none",borderRadius:8,background:"#16835c",color:"#fff",fontFamily:"var(--font)",fontSize:13,fontWeight:800,cursor:"pointer"}}>
                    ✅ Posso produrla?
                  </button>}
                  <button
                    onClick={() => setDettaglioR(r)}
                    style={{width:"100%",padding:"8px 0",border:"1.5px solid var(--border)",borderRadius:8,background:"var(--card)",fontFamily:"var(--font)",fontSize:13,fontWeight:700,cursor:"pointer"}}>
                    📖 Apri scheda
                  </button>
                  {!soloLettura ? <button
                    onClick={() => { setEditRicetta(r); setShowForm(true); }}
                    style={{width:"100%",padding:"8px 0",border:"1.5px solid #b9cec1",borderRadius:8,background:"#edf4ef",color:"#3f5a4e",fontFamily:"var(--font)",fontSize:13,fontWeight:800,cursor:"pointer"}}>
                    {riferimentoFornitore ? "✏️ Usa in ricetta" : "✏️ Modifica nome e ingredienti"}
                  </button> : <button
                    onClick={() => rendiOperativa(r)}
                    disabled={promuovendo}
                    style={{width:"100%",padding:"8px 0",border:"1.5px solid #b9cec1",borderRadius:8,background:"#edf4ef",color:"#3f5a4e",fontFamily:"var(--font)",fontSize:13,fontWeight:800,cursor:promuovendo?"wait":"pointer"}}>
                    ✏️ Rendi modificabile
                  </button>}
                </div>
              </div>
            </div>
            );
          })}
          {filtrate.length === 0 && (
            <div style={{gridColumn:"1/-1",textAlign:"center",padding:"60px",color:"var(--text-3)"}}>
              <div style={{fontSize:40,marginBottom:12}}>🍽️</div>
              <p>Nessuna ricetta trovata</p>
            </div>
          )}
        </div>
      )}
      {produciR && (
        <ModalRegistraLotto
          prodotto={produciR}
          reparto={produciR.reparto || "pasticceria"}
          onClose={() => setProduciR(null)}
          onSuccess={() => { setProduciR(null); carica(); }}
          frigoriferi={attrezzature.frigoriferi}
          congelatori={attrezzature.congelatori}
        />
      )}
      {showForm && (
        <FormRicetta
          key={editRicetta?.id || "nuova"}
          ricetta={editRicetta}
          ricette={ricette.filter(r => !(r.origine === "archivio" || r.sola_lettura))}
          onSalvato={() => { setShowForm(false); carica(); }}
          onAnnulla={() => setShowForm(false)}
          onApriScheda={(r) => { setShowForm(false); setSchedaR(r); }}
          onElimina={async (r) => {
            // Il form si chiude SUBITO e la conferma compare in primo piano
            // (23/07/2026: prima la conferma finiva dietro al modale)
            setShowForm(false);
            await elimina(r.id, r.nome);
          }}
        />
      )}
      {schedaR && (
        <SchedaEditorModal
          ricetta={schedaR}
          onClose={() => setSchedaR(null)}
          onSaved={() => { setSchedaR(null); carica(); }}
        />
      )}
      {verificaR && (
        <VerificaDisponibilitaModal
          ricetta={verificaR}
          onClose={() => setVerificaR(null)}
          onRicetteUpdate={carica}
        />
      )}
      {dettaglioR && (
        <SchedaRicettaChiaraModal
          ricetta={dettaglioR}
          tutte={ricette}
          occupato={promuovendo}
          onClose={() => setDettaglioR(null)}
          onRendiOperativa={rendiOperativa}
          onProduci={(r) => { setDettaglioR(null); setProduciR(r); }}
          onModifica={(r) => { setDettaglioR(null); setEditRicetta(r); setShowForm(true); }}
        />
      )}
    </div>
  );
}

function TabAttivita() {
  const [log, setLog] = useState([]);
  const [tipi, setTipi] = useState([]);
  const [tipo, setTipo] = useState("");
  const [operatore, setOperatore] = useState("");
  const [giorni, setGiorni] = useState(7);
  const [loading, setLoading] = useState(false);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams();
      if (tipo) p.set("tipo", tipo);
      if (operatore) p.set("operatore", operatore);
      p.set("giorni", giorni);
      const r = await axios.get(`${API}/log-attivita?${p.toString()}`);
      setLog(r.data?.log || []);
      setTipi(r.data?.tipi || []);
    } catch { toast("Errore caricamento registro", "err"); }
    finally { setLoading(false); }
  }, [tipo, operatore, giorni]);

  useEffect(() => { carica(); }, [carica]);

  const ICONA = { login:"🔓", logout:"🔒", magazzino:"📦", produzione:"🍰" };
  const fmt = (ts) => { try { return new Date(ts).toLocaleString("it-IT"); } catch { return ts || ""; } };
  const selStyle = {padding:"8px 12px",borderRadius:8,border:"1px solid var(--border)",fontFamily:"var(--font)",fontSize:13,background:"var(--card)"};

  return (
    <div>
      <div style={{display:"flex",gap:8,flexWrap:"wrap",marginBottom:16}}>
        <select value={tipo} onChange={e=>setTipo(e.target.value)} style={selStyle}>
          <option value="">Tutti i tipi</option>
          {tipi.map(t => <option key={t} value={t}>{(ICONA[t]||"")+" "+t}</option>)}
        </select>
        <input value={operatore} onChange={e=>setOperatore(e.target.value)} placeholder="Operatore…" style={selStyle} />
        <select value={giorni} onChange={e=>setGiorni(Number(e.target.value))} style={selStyle}>
          <option value={1}>Oggi</option>
          <option value={7}>Ultimi 7 giorni</option>
          <option value={30}>Ultimi 30 giorni</option>
          <option value={90}>Ultimi 90 giorni</option>
        </select>
      </div>
      {loading && <div style={{color:"var(--text-3)",fontSize:13}}>Caricamento…</div>}
      {!loading && log.length===0 && <div style={{color:"var(--text-3)",fontSize:13}}>Nessuna attività nel periodo.</div>}
      <div style={{display:"flex",flexDirection:"column",gap:8}}>
        {log.map((r,i) => (
          <div key={i} style={{display:"flex",gap:12,alignItems:"center",padding:"10px 14px",background:"var(--card)",border:"1px solid var(--border)",borderRadius:10}}>
            <span style={{fontSize:18}}>{ICONA[r.tipo]||"•"}</span>
            <div style={{flex:1,minWidth:0}}>
              <div style={{fontSize:13,fontWeight:600,color:"var(--text)"}}>{r.descrizione}</div>
              <div style={{fontSize:11,color:"var(--text-3)"}}>{fmt(r.timestamp)}{r.reparto ? " · "+r.reparto : ""}</div>
            </div>
            <span style={{fontSize:10,fontWeight:700,color:"var(--text-2)",textTransform:"uppercase",letterSpacing:".04em"}}>{r.tipo}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
// COMPONENTE PRINCIPALE BACKOFFICE
// ══════════════════════════════════════════════════════════════════

const TABS = [
  { id:"prodotti",   label:"📦 Prodotti & Soglie",  desc:"Quantità riordino e alert sotto scorta" },
  { id:"fornitori",  label:"🏭 Fornitori",           desc:"Qualifica e gestione fornitori magazzino" },
  // "Ricette" NON è qui: ha la pagina dedicata #ricette (niente doppione nel backoffice).
  { id:"ricette",    label:"📋 Ricette",              desc:"Crea e modifica ricette", soloPagina:true },
  { id:"attivita",   label:"🕑 Attività",             desc:"Chi è entrato e cosa ha fatto" },
];

export default function BackofficeView({ initialTab = "prodotti", solo = false }) {
  const [tab, setTab] = useState(initialTab);
  const cur = TABS.find(t => t.id === tab);

  return (
    <div style={{background:"var(--bg)",minHeight:"100vh",padding:"0 0 40px"}}>

      {/* Header */}
      <div style={{background:"var(--primary-grad)",padding: solo ? "20px 20px 16px" : "20px 20px 0"}}>
        <h1 style={{margin:"0 0 4px",fontSize:22,fontWeight:900,color:"#fff",letterSpacing:"-.02em"}}>
          {solo ? (cur?.label?.replace(/^[^\wÀ-ÿ]+\s*/, "") || "Ricette") : "Backoffice"}
        </h1>
        <p style={{margin: solo ? 0 : "0 0 16px",fontSize:13,color:"rgba(255,255,255,.75)"}}>
          {cur?.desc}
        </p>
        {/* Tab bar (nascosta in modalità solo) */}
        {!solo && (
          <div style={{display:"flex",gap:4}}>
            {TABS.filter(t => !t.soloPagina).map(t => (
              <button key={t.id} onClick={() => setTab(t.id)}
                style={{
                  padding:"10px 18px",border:"none",borderRadius:"10px 10px 0 0",
                  fontFamily:"var(--font)",fontSize:13,fontWeight:700,cursor:"pointer",
                  background: tab===t.id ? "var(--bg)" : "rgba(255,255,255,.15)",
                  color: tab===t.id ? "var(--primary)" : "rgba(255,255,255,.9)",
                  transition:"all .15s",
                }}>
                {t.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Contenuto */}
      <div style={{padding:"24px 20px", maxWidth:1000, margin:"0 auto"}}>
        {tab === "prodotti"  && <TabProdotti/>}
        {tab === "fornitori" && <TabFornitori/>}
        {tab === "ricette"   && <TabRicette/>}
        {tab === "attivita"  && <TabAttivita/>}
      </div>

      <style>{`
        @keyframes fadeUp {
          from { opacity:0; transform:translateX(-50%) translateY(10px); }
          to   { opacity:1; transform:translateX(-50%) translateY(0); }
        }
      `}</style>
    </div>
  );
}
