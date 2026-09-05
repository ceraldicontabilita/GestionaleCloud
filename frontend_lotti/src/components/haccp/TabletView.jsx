/**
 * TabletView.jsx — Vista kiosk dopo il login PIN
 *
 * SICUREZZA KIOSK:
 *  - Nessun pulsante porta fuori dal kiosk senza PIN admin
 *  - Il ritorno ai reparti è libero e conserva l'operatore identificato
 *  - L'ingresso nel gestionale resta protetto dalla home kiosk
 *  - I dipendenti restano sempre nel kiosk
 *
 * REPARTI:
 *  - Pasticceria: prodotti, lotti, acquaviva, SAIMA/MEPA ordini, giacenze calanti → ordine automatico
 *  - Rosticceria: prodotti, lotti, produzione mattina
 *  - Magazzino:   giacenze materie prime, alert sottoscorta, conferma riordini
 */
import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { User } from "lucide-react";
import { norm } from "../../utils/textNormalize";
import { conferma } from "../../utils/conferma";
import { apiError } from "../../utils/apiError";

import { ModalCambioFoto }    from "./tablet/ModalCambioFoto";
import { ModalRegistraLotto } from "./tablet/ModalRegistraLotto";
import { ModalAlpha }         from "./tablet/ModalAlpha";
import ModalRichiediMerce     from "./tablet/ModalRichiediMerce";
import CardProdotto           from "./tablet/CardProdotto";
import SchedaRicettaKiosk     from "./tablet/SchedaRicettaKiosk";
import PannelloReparti        from "./tablet/PannelloReparti";
import MagazzinoBarView      from "./MagazzinoBarView";
import ColazioneAcquavivaView from "./ColazioneAcquavivaView";
import { API, fotoSrc }       from "../../utils/constants";
import { clearTabletSession, getTabletSession } from "../../utils/tabletSession";

const REPARTI_INFO = {
  pasticceria: { emoji:"🍰", label:"Pasticceria", grad:"linear-gradient(135deg,#fb923c,#ea580c)" },
  rosticceria: { emoji:"🥙", label:"Rosticceria", grad:"linear-gradient(135deg,#86efac,#22c55e)" },
  bar:         { emoji:"☕", label:"Bar",         grad:"linear-gradient(135deg,#b45309,#78350f)" },
  magazzino:   { emoji:"📦", label:"Magazzino",   grad:"linear-gradient(135deg,#6f583a,#4a3f33)" },
};

function getOp() {
  return getTabletSession();
}

// ── Vista Magazzino completa: Scarica (veloce) + Giacenze (riordino) ──────────

// ── Vista Magazzino ───────────────────────────────────────────────────────────

export const TabletView = ({ reparto: repartoIniziale = "pasticceria", onBack }) => {
  const operatore = getOp();
  const [reparto,             setReparto]             = useState(repartoIniziale);
  const [prodotti,            setProdotti]            = useState([]);
  const [loading,             setLoading]             = useState(true);
  const [search,              setSearch]              = useState("");
  const [prodottoSel,         setProdottoSel]         = useState(null);
  const [showAdmin,           setShowAdmin]           = useState(false);
  const [cambiaFotoProd,      setCambiaFotoProd]      = useState(null);
  // «Vedi la ricetta» dal tablet, in sola lettura (Enzo 25/07/2026: il
  // dipendente deve poter LEGGERE la ricetta, non modificarla).
  const [ricettaDaVedere,     setRicettaDaVedere]     = useState(null);
  const [showAlpha,           setShowAlpha]           = useState(false);
  const [showColazione,       setShowColazione]       = useState(false);
  const [showRichiediMerce,   setShowRichiediMerce]   = useState(false);
  const [showAggiungi,        setShowAggiungi]        = useState(false);
  const [eliminandoId,        setEliminandoId]        = useState(null);
  const [idConVarianti,       setIdConVarianti]       = useState(new Set());
  const [taskOggi,            setTaskOggi]            = useState([]);
  const [showTask,            setShowTask]            = useState(false);
  // Frigoriferi/congelatori REALI configurati dal titolare (Attrezzature),
  // non l'elenco generico di fallback — richiesta Enzo 20/07/2026: "non mi
  // fa scegliere in quale congelatore o frigo, mancano".
  const [attrezzature,        setAttrezzature]        = useState({ frigoriferi: [], congelatori: [] });
  useEffect(() => {
    axios.get(`${API}/attrezzature/`)
      .then(r => setAttrezzature(r.data || { frigoriferi: [], congelatori: [] }))
      .catch(() => {});
  }, []);

  // Carica task del giorno per questo reparto
  const caricaTask = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/task-dipendenti/oggi?reparto=${reparto}`);
      setTaskOggi((res.data?.tasks || []).filter(t => !t.completato));
    } catch { /* silenzioso */ }
  }, [reparto]);

  const completaTask = async (taskId) => {
    try {
      await axios.patch(`${API}/task-dipendenti/${taskId}/completa?operatore_nome=${encodeURIComponent(operatore?.nome || "operatore")}`);
      setTaskOggi(prev => prev.filter(t => t.id !== taskId));
      toast.success("✓ Task completato");
    } catch { toast.error("Errore"); }
  };

  const carica = useCallback(async () => {
    if (reparto === "magazzino") { setLoading(false); return; }
    setLoading(true);
    try {
      const [resProd, resRic] = await Promise.all([
        axios.get(`${API}/tablet/${reparto}`),
        axios.get(`${API}/ricette`),
      ]);
      const ricette = resRic.data || [];
      const ricettePerId = new Map(ricette.map(r => [r.id, r]));
      const prodottiConFotoBase = (resProd.data.prodotti || []).map(prodotto => {
        if (prodotto.foto_url || !prodotto.ricetta_base_id) return prodotto;
        const ricettaBase = ricettePerId.get(prodotto.ricetta_base_id);
        if (!ricettaBase?.foto_url) return prodotto;
        return {
          ...prodotto,
          foto_fallback_url: ricettaBase.foto_url,
          foto_fallback_nome: ricettaBase.nome,
        };
      });
      setProdotti(prodottiConFotoBase);
      const baseIds = new Set(ricette.filter(r=>r.ricetta_base_id).map(r=>r.ricetta_base_id));
      setIdConVarianti(baseIds);
    } catch { toast.error("Errore caricamento prodotti"); }
    finally { setLoading(false); }
  }, [reparto]);

  useEffect(() => { carica(); caricaTask(); }, [carica, caricaTask]);

  useEffect(() => {
  }, [reparto]);

  const info = REPARTI_INFO[reparto] || REPARTI_INFO.pasticceria;



  const tutti = Object.keys(REPARTI_INFO).filter(r => r !== reparto); // BUG FIX: escludeva sempre Pasticceria
  const prodottiFiltrati = prodotti
    .filter(p=>!search||norm(p.nome).includes(norm(search)))  // stesso motore di ricerca dell'app: senza accenti ("babà"→"baba")
    .sort((a,b)=>(a.nome||"").localeCompare(b.nome||"","it"));

  const puoEliminareRicette = operatore?.ruolo === "amministratore";
  const eliminaRicetta = async (prodotto) => {
    if (!puoEliminareRicette || !prodotto?.id || eliminandoId) return;
    const ok = await conferma(
      `Eliminare la ricetta "${prodotto.nome}" dalle card operative?`,
      {
        titolo: "Elimina ricetta",
        ok: "Sposta nel cestino",
        pericolo: true,
      },
    );
    if (!ok) return;
    setEliminandoId(prodotto.id);
    try {
      const risposta = await axios.delete(`${API}/ricette/${prodotto.id}`);
      setProdotti((correnti) => correnti.filter((r) => r.id !== prodotto.id));
      toast.success(risposta.data?.recuperabile
        ? "Ricetta eliminata e conservata nel cestino"
        : "Ricetta eliminata");
    } catch (errore) {
      toast.error(apiError(errore, "Non è stato possibile eliminare la ricetta"));
    } finally {
      setEliminandoId(null);
    }
  };

  const esciAdmin = () => {
    const op = getTabletSession({ allowExpired: true });
    if (op?.nome) axios.post(`${process.env.REACT_APP_LOTTI_BACKEND_URL}/api/tablet-operatori/logout`, { nome: op.nome, reparto: op.reparto || "" }).catch(() => {});
    clearTabletSession();
    if (onBack) onBack();
    else { window.location.hash=""; window.location.reload(); }
  };

  if (reparto === "magazzino") {
    // Dal reparto produzione (bar/pasticceria/rosticceria) si accede alla
    // LAVAGNA per richiedere al magazzino, NON al preleva: il preleva è solo
    // nella card Magazzino dedicata (accesso da #tablet/magazzino).
    return (
      <MagazzinoBarView onBack={esciAdmin} soloLavagna />
    );
  }


  return (
    <div style={{minHeight:"100vh",background:"#f7f4ec",display:"flex",flexDirection:"column"}}>

      {/* Header */}
      <div style={{background:info.grad,padding:"14px 16px",boxShadow:"0 4px 16px rgba(0,0,0,.18)",flexShrink:0}}>
        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:reparto!=="magazzino"?14:0,flexWrap:"wrap",gap:8}}>

          {/* Sinistra: emoji + nome */}
          <div style={{display:"flex",alignItems:"center",gap:10}}>
            <div style={{fontSize:28}}>{info.emoji}</div>
            <div>
              <h1 style={{color:"#fff",margin:0,fontSize:19,fontWeight:800,letterSpacing:"-.5px"}}>{info.label}</h1>
              {operatore && (
                <p style={{color:"rgba(255,255,255,.8)",margin:0,fontSize:11,display:"flex",alignItems:"center",gap:4}}>
                  <User size={12} style={{flexShrink:0}} /> {operatore.nome}
                </p>
              )}
            </div>
          </div>

          {/* Destra: azioni — l'operatore vede SOLO Colazione + Esci.
              Acquaviva/Alpha e Aggiungi prodotto NON sono più qui (gestione da sezione dedicata). */}
          <div style={{display:"flex",gap:8,flexWrap:"wrap",alignItems:"center"}}>
            {reparto === "pasticceria" && (
              <>
                <button onClick={()=>setShowColazione(true)}
                  style={{padding:"9px 16px",border:"none",borderRadius:12,background:"#fff",color:"#2a3329",fontWeight:800,fontSize:13,cursor:"pointer",fontFamily:"inherit",boxShadow:"0 2px 8px rgba(0,0,0,.15)"}}>
                  ☕ Colazione
                </button>
                <button onClick={()=>setShowAlpha(true)}
                  style={{padding:"9px 16px",border:"none",borderRadius:12,background:"#fff",color:"#064e3b",fontWeight:800,fontSize:13,cursor:"pointer",fontFamily:"inherit",boxShadow:"0 2px 8px rgba(0,0,0,.15)"}}>
                  🌾 Senza Glutine
                </button>
              </>
            )}

            {/* Richiedi merce — UNICO modo di chiedere al magazzino, da ogni reparto */}
            {reparto !== "magazzino" && (
              <button onClick={()=>setShowRichiediMerce(true)}
                style={{padding:"9px 16px",border:"none",borderRadius:12,background:"#fff",color:"#7c2d12",fontWeight:800,fontSize:13,cursor:"pointer",fontFamily:"inherit",boxShadow:"0 2px 8px rgba(0,0,0,.15)"}}>
                📦 Richiedi merce
              </button>
            )}

            {/* Tornare alle card non cambia operatore e non richiede un nuovo PIN. */}
            <button onClick={()=>{ window.location.hash = "tablet/home"; }} style={{padding:"9px 14px",border:"2px solid rgba(255,255,255,.45)",borderRadius:12,background:"rgba(255,255,255,.16)",color:"#fff",fontWeight:700,fontSize:13,cursor:"pointer",fontFamily:"inherit"}}
              title="Torna alla scelta reparto">
              ← Reparti
            </button>
          </div>
        </div>

        {/* Ricerca — solo per reparti prodotti */}
        {reparto !== "magazzino" && (
          <div style={{position:"relative"}}>
            <span style={{position:"absolute",left:14,top:"50%",transform:"translateY(-50%)",color:"rgba(255,255,255,.7)",fontSize:16}}>🔍</span>
            <input
              type="text"
              value={search}
              onChange={e=>setSearch(e.target.value)}
              placeholder={`Cerca ${reparto==="pasticceria"?"dolce":"piatto"}…`}
              style={{width:"100%",padding:"11px 16px 11px 42px",borderRadius:12,border:"1px solid rgba(255,255,255,.35)",background:"rgba(0,0,0,.22)",color:"#fff",fontSize:15,backdropFilter:"blur(8px)",outline:"none",boxSizing:"border-box",fontFamily:"inherit"}}
            />
          </div>
        )}
      </div>

      {/* Corpo */}
      {(
        <div style={{flex:1,minHeight:0,padding:"14px 16px",overflowY:"auto"}}>

          {/* Widget task del giorno */}
          {taskOggi.length > 0 && !showTask && (
            <button onClick={() => setShowTask(true)} style={{position:"fixed",bottom:18,left:14,zIndex:240,border:"none",borderRadius:999,padding:"10px 16px",fontWeight:800,fontSize:14,color:"#fff",background:"linear-gradient(135deg,#3f5a4e,#5b7a6b)",boxShadow:"0 6px 18px rgba(42,51,41,.35)",cursor:"pointer"}}>
              📋 {taskOggi.length} task
            </button>
          )}
          {taskOggi.length > 0 && showTask && (
            <div style={{
              background: "linear-gradient(135deg, #4a3f33, #3f5a4e)",
              borderRadius: 16, padding: "12px 14px", marginBottom: 14,
              border: "1px solid rgba(111,145,128,.35)",
            }}>
              <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:8}}>
                <span style={{fontSize:13,fontWeight:700,color:"#dcebe2"}}>
                  📋 Cosa fare oggi ({taskOggi.length})
                </span>
                <button onClick={()=>setShowTask(false)} style={{background:"none",border:"none",color:"#6f9180",cursor:"pointer",fontSize:13}}>×</button>
              </div>
              {taskOggi.slice(0,4).map(t => (
                <div key={t.id} style={{
                  display:"flex",alignItems:"center",gap:10,marginBottom:6,
                  background:"rgba(255,255,255,.08)",borderRadius:10,padding:"8px 10px",
                }}>
                  <span style={{fontSize:16,flexShrink:0}}>
                    {t.tipo==="scadenza"?"⏰":t.tipo==="produzione"?"👨‍🍳":t.tipo==="temperatura"?"🌡":"📌"}
                  </span>
                  <div style={{flex:1,minWidth:0}}>
                    <p style={{margin:0,fontSize:12,fontWeight:600,color:"#dcebe2",
                      whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>
                      {t.titolo}
                    </p>
                    {t.priorita==="urgente" && (
                      <span style={{fontSize:9,background:"rgba(239,68,68,.3)",color:"#fca5a5",
                        padding:"1px 5px",borderRadius:3,fontWeight:700}}>URGENTE</span>
                    )}
                  </div>
                  <button
                    onClick={()=>completaTask(t.id)}
                    style={{
                      background:"rgba(16,185,129,.2)",border:"1px solid rgba(16,185,129,.4)",
                      color:"#6ee7b7",borderRadius:8,padding:"4px 8px",fontSize:11,
                      fontWeight:700,cursor:"pointer",flexShrink:0,
                    }}
                  >✓ Fatto</button>
                </div>
              ))}
              {taskOggi.length > 4 && (
                <p style={{fontSize:10,color:"#6f9180",textAlign:"center",margin:"4px 0 0"}}>
                  +{taskOggi.length-4} altri task...
                </p>
              )}
            </div>
          )}
          {loading ? (
            <div style={{textAlign:"center",padding:"60px 0",color:"#9aa593",fontSize:16}}>Caricamento…</div>
          ) : prodottiFiltrati.length === 0 && !search ? (
            <div style={{textAlign:"center",padding:"60px 0",color:"#9aa593"}}>
              <div style={{fontSize:48,marginBottom:12}}>🍽️</div>
              <p style={{fontSize:16}}>Nessun prodotto per {reparto}</p>
            </div>
          ) : (
            <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(150px,1fr))",gap:12}}>
                                                        {prodottiFiltrati.map(p => (
                <CardProdotto
                  key={p.id}
                  prodotto={p}
                  reparto={reparto}
                  onTap={setProdottoSel}
                  onCambiaFoto={prod=>setCambiaFotoProd(prod)}
                  hasVarianti={idConVarianti.has(p.id)}
                  onVediRicetta={prod=>setRicettaDaVedere(prod)}
                  onElimina={puoEliminareRicette ? eliminaRicetta : undefined}
                  eliminando={eliminandoId === p.id}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Footer lotti */}
      {/* Modali */}
      {cambiaFotoProd && <ModalCambioFoto prodotto={cambiaFotoProd} onClose={()=>setCambiaFotoProd(null)} onSalvato={carica}/>}
      {ricettaDaVedere && <SchedaRicettaKiosk
        ricettaId={ricettaDaVedere.id}
        nome={ricettaDaVedere.nome}
        modificabile={puoEliminareRicette}
        onSalvato={carica}
        onClose={()=>setRicettaDaVedere(null)}
      />}
      {prodottoSel && <ModalRegistraLotto prodotto={prodottoSel} reparto={reparto} onClose={()=>setProdottoSel(null)} onSuccess={()=>{setProdottoSel(null);carica();}} onRefreshLista={carica} frigoriferi={attrezzature.frigoriferi} congelatori={attrezzature.congelatori}/>}
      {showAdmin && <PannelloReparti onClose={()=>{setShowAdmin(false);carica();}}/>}
      {showAlpha && <ModalAlpha modo="banco" onClose={()=>setShowAlpha(false)}/>}
      {showColazione && <ColazioneAcquavivaView modoTablet={true} onClose={()=>{setShowColazione(false);carica();}}/>}
      {showRichiediMerce && <ModalRichiediMerce operatoreNome={operatore?.nome || ""} onClose={()=>setShowRichiediMerce(false)}/>}
      {showAggiungi && <ModalAggiungiProdotto reparto={reparto} onClose={()=>setShowAggiungi(false)} onSalvato={()=>{setShowAggiungi(false);carica();}}/>}
    </div>
  );
};

// ── Modale: aggiungi prodotto alla card — scegli un esistente (con foto) o creane uno nuovo ──
function ModalAggiungiProdotto({ reparto, onClose, onSalvato }) {
  const [modo, setModo]         = useState("esistente"); // esistente | nuovo
  const [tutte, setTutte]       = useState([]);
  const [sceltoId, setSceltoId] = useState("");
  const [caricando, setCaricando] = useState(true);
  const [inserisco, setInserisco] = useState(null);
  // crea nuovo
  const [nome, setNome]         = useState("");
  const [porzioni, setPorzioni] = useState("1");
  const [salvo, setSalvo]       = useState(false);

  useEffect(() => {
    let vivo = true;
    axios.get(`${API}/ricette`)
      .then(r => { if (vivo) setTutte(Array.isArray(r.data) ? r.data : (r.data?.ricette || [])); })
      .catch(() => {})
      .finally(() => { if (vivo) setCaricando(false); });
    return () => { vivo = false; };
  }, []);

  const lista = [...tutte]
    .sort((a, b) => {
      // prima quelli NON ancora in questa card, poi alfabetico
      const ai = (a.reparto === reparto) ? 1 : 0;
      const bi = (b.reparto === reparto) ? 1 : 0;
      if (ai !== bi) return ai - bi;
      return (a.nome || "").localeCompare(b.nome || "", "it");
    });

  const scelto = tutte.find(r => r.id === sceltoId) || null;

  const inserisci = async (r) => {
    setInserisco(r.id);
    try {
      await axios.put(`${API}/ricette/${r.id}/reparto?reparto=${reparto}`);
      toast.success(`"${r.nome}" aggiunto alla card`);
      onSalvato();
    } catch {
      toast.error("Errore nell'inserimento");
      setInserisco(null);
    }
  };

  const creaNuovo = async () => {
    const n = nome.trim();
    if (!n) { toast.error("Inserisci il nome del prodotto"); return; }
    setSalvo(true);
    try {
      await axios.post(`${API}/ricette`, { nome: n, reparto, porzioni: parseFloat(porzioni) || 1, approvata: false, ingredienti_dettaglio: [] });
      toast.success(`Prodotto "${n}" creato e aggiunto alla card`);
      onSalvato();
    } catch { toast.error("Errore nel salvataggio"); setSalvo(false); }
  };

  const labelReparto = reparto === "rosticceria" ? "salato" : reparto === "pasticceria" ? "di pasticceria" : reparto === "bar" ? "bar" : "";
  const accent = reparto === "rosticceria" ? "#2f5d50" : reparto === "bar" ? "#7c4a02" : "#b45309";

  return (
    <div onClick={onClose} style={{position:"fixed",inset:0,zIndex:60,background:"rgba(0,0,0,.45)",display:"flex",alignItems:"center",justifyContent:"center",padding:14}}>
      <div onClick={e=>e.stopPropagation()} style={{background:"#fff",borderRadius:18,padding:18,width:"100%",maxWidth:520,maxHeight:"88vh",display:"flex",flexDirection:"column",fontFamily:"'Plus Jakarta Sans',system-ui,sans-serif"}}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
          <h2 style={{margin:0,fontSize:18,fontWeight:800,color:"#1f2937"}}>Aggiungi prodotto {labelReparto}</h2>
          <button onClick={onClose} style={{background:"none",border:"none",fontSize:22,color:"#9ca3af",cursor:"pointer",lineHeight:1}}>×</button>
        </div>

        {/* Switch modalità */}
        <div style={{display:"flex",gap:8,marginBottom:14}}>
          {[["esistente","Scegli esistente"],["nuovo","Crea nuovo"]].map(([id,lbl])=>(
            <button key={id} onClick={()=>setModo(id)} style={{flex:1,padding:"9px 0",borderRadius:10,fontWeight:800,fontSize:13,cursor:"pointer",fontFamily:"inherit",border:modo===id?"none":"1px solid #ece4d6",background:modo===id?accent:"#fff",color:modo===id?"#fff":"#7a7266"}}>{lbl}</button>
          ))}
        </div>

        {modo === "esistente" ? (
          <>
            <label style={{fontSize:12,fontWeight:700,color:"#7a7266",marginBottom:4,display:"block"}}>Scegli la ricetta</label>
            <select value={sceltoId} onChange={e=>setSceltoId(e.target.value)}
              style={{width:"100%",padding:"13px 12px",borderRadius:11,border:"1px solid #ece4d6",fontSize:15,background:"#fff",outline:"none",boxSizing:"border-box",fontFamily:"inherit",marginBottom:12}}>
              <option value="">{caricando ? "Carico ricette…" : "— Seleziona un prodotto —"}</option>
              {lista.map(r => (
                <option key={r.id} value={r.id} disabled={r.reparto === reparto}>
                  {r.nome}{r.reparto === reparto ? "  (già in card)" : ""}
                </option>
              ))}
            </select>

            {/* Anteprima della ricetta scelta */}
            {scelto && (
              <div style={{display:"flex",gap:12,alignItems:"center",background:"#faf7f0",border:"1px solid #ece4d6",borderRadius:12,padding:10,marginBottom:14}}>
                <div style={{width:64,height:64,borderRadius:10,overflow:"hidden",background:"#f3f0e8",flexShrink:0,display:"flex",alignItems:"center",justifyContent:"center"}}>
                  {scelto.foto_url
                    ? <img src={fotoSrc(scelto.foto_url)} alt="" style={{width:"100%",height:"100%",objectFit:"cover"}} onError={e=>{e.target.style.display="none";}}/>
                    : <span style={{fontSize:26}}>🍽️</span>}
                </div>
                <div style={{minWidth:0}}>
                  <div style={{fontSize:14,fontWeight:800,color:"#1f2937",lineHeight:1.25}}>{scelto.nome}</div>
                  <div style={{fontSize:12,color:"#9aa593",marginTop:2}}>{scelto.reparto ? `attualmente: ${scelto.reparto}` : "non assegnato"}</div>
                </div>
              </div>
            )}

            <div style={{display:"flex",gap:10}}>
              <button onClick={onClose} style={{flex:1,padding:"12px 0",borderRadius:11,border:"1px solid #ece4d6",background:"#fff",color:"#7a7266",fontWeight:700,fontSize:14,cursor:"pointer"}}>Annulla</button>
              <button onClick={()=>scelto && inserisci(scelto)} disabled={!scelto || inserisco}
                style={{flex:2,padding:"12px 0",borderRadius:11,border:"none",background:(!scelto||inserisco)?"#cfc6b4":accent,color:"#fff",fontWeight:800,fontSize:14,cursor:(!scelto||inserisco)?"default":"pointer"}}>
                {inserisco ? "Inserisco…" : "Inserisci nella card"}
              </button>
            </div>
          </>
        ) : (
          <>
            <label style={{fontSize:12,fontWeight:700,color:"#7a7266"}}>Nome prodotto</label>
            <input autoFocus value={nome} onChange={e=>setNome(e.target.value)} placeholder="es. Arancino al ragù"
              onKeyDown={e=>{ if(e.key==="Enter") creaNuovo(); }}
              style={{width:"100%",padding:"11px 13px",borderRadius:11,border:"1px solid #ece4d6",fontSize:15,outline:"none",margin:"4px 0 14px",boxSizing:"border-box"}}/>
            <label style={{fontSize:12,fontWeight:700,color:"#7a7266"}}>Pezzi per ricetta</label>
            <input type="number" min="1" value={porzioni} onChange={e=>setPorzioni(e.target.value)}
              style={{width:"100%",padding:"11px 13px",borderRadius:11,border:"1px solid #ece4d6",fontSize:15,outline:"none",margin:"4px 0 18px",boxSizing:"border-box"}}/>
            <div style={{display:"flex",gap:10}}>
              <button onClick={onClose} style={{flex:1,padding:"12px 0",borderRadius:11,border:"1px solid #ece4d6",background:"#fff",color:"#7a7266",fontWeight:700,fontSize:14,cursor:"pointer"}}>Annulla</button>
              <button onClick={creaNuovo} disabled={salvo} style={{flex:2,padding:"12px 0",borderRadius:11,border:"none",background:salvo?"#cfc6b4":"#8a6f47",color:"#fff",fontWeight:800,fontSize:14,cursor:salvo?"default":"pointer"}}>
                {salvo ? "Salvo…" : "Crea e aggiungi"}
              </button>
            </div>
            <p style={{margin:"12px 0 0",fontSize:11,color:"#9aa593",textAlign:"center"}}>Ingredienti e ricetta li aggiungi poi dalla sezione Ricette.</p>
          </>
        )}
      </div>
    </div>
  );
}

export default TabletView;
