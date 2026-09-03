/**
 * ListinoView.jsx
 * Listino Prezzi Merci — adattato da listino-prezzi-merci (React Native → React Web)
 * Catalogo prodotti con prezzi per fornitore. Sync automatico da fatture XML.
 * Sezione Alias: raggruppa prodotti equivalenti da fornitori diversi.
 */
import React, { useState, useEffect, useCallback } from "react";
import { conferma } from "../../utils/conferma";
import axios from "axios";
import { norm } from "../../utils/textNormalize";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

// ── Colori categoria ───────────────────────────────────────────────────────────
const CAT_COLORS = {
  ACQUA:"#a8854f",BIBITE:"#a8854f",BIRRE:"var(--warning-dark)",VINO:"#8f3829",PROSECCO:"#ec4899",
  LIQUORI:"var(--danger-dark)",AMARI:"var(--warning-text)",SCIROPPI:"var(--success-dark)",SUCCHI:"var(--warning)",
  DOLCIFICANTI:"#6b7280",CAFFE:"#78350f",FARINE:"#ca8a04",LATTICINI:"#c9a877",
  UOVA:"#ea580c",GRASSI:"#65a30d",ZUCCHERI:"#b8960c",CREME:"#f43f5e",
  CIOCCOLATO:"var(--warning-text)",LIEVITI:"#84cc16",FRUTTA_SECCA:"#f97316",
  MONOUSO:"#94a3b8",IMBALLAGGI:"#64748b",PULIZIA:"#57534e",ATTREZZATURE:"#334155",
  ALTRO:"#9ca3af",
};
const fmtP   = (v) => v != null ? `€ ${Number(v).toFixed(2)}` : "—";
const catClr = (c) => CAT_COLORS[c] || "#9ca3af";

// ── VIEWS ─────────────────────────────────────────────────────────────────────
// Due sole viste (unificazione 02/07/2026): "Genera listino" (la funzione
// principale: listino fornitore con sconto %) e "Catalogo prezzi" (gestione
// voci). L'ALIAS (vecchio raggruppamento) e il CARRELLO interno sono stati
// eliminati: i prodotti si raggruppano col Confronto in Ordini e si ordina
// SOLO dal carrello di Ordini — un solo flusso d'acquisto.
const VIEWS = [
  { id: "genera",   label: "Genera listino" },
  { id: "catalogo", label: "Catalogo prezzi" },
];

// ── Modal prodotto ─────────────────────────────────────────────────────────────
function ModalProdotto({ prodotto, fornitori, onClose, onSaved }) {
  const isEdit = !!prodotto;
  const [nome,      setNome]      = useState(prodotto?.nome || "");
  const [categoria, setCategoria] = useState(prodotto?.categoria || "ALTRO");
  const [conf,      setConf]      = useState(prodotto?.conf || "PZ");
  const [prezziRaw, setPrezziRaw] = useState(() =>
    prodotto?.prezzi
      ? Object.entries(prodotto.prezzi).map(([f,p]) => ({fornitore:f, prezzo:String(p)}))
      : [{fornitore: fornitori[0]?.nome||"", prezzo:""}]
  );
  const [busy, setBusy] = useState(false);
  const [err,  setErr]  = useState("");

  const CATS = ["ACQUA","BIBITE","BIRRE","VINO","PROSECCO","LIQUORI","AMARI","SCIROPPI",
    "SUCCHI","DOLCIFICANTI","CAFFE","FARINE","LATTICINI","UOVA","GRASSI",
    "ZUCCHERI","CREME","CIOCCOLATO","LIEVITI","FRUTTA_SECCA","MONOUSO","IMBALLAGGI","PULIZIA","ATTREZZATURE","ALTRO"];

  const salva = async () => {
    if (!nome.trim()) { setErr("Nome obbligatorio"); return; }
    const prezzi = {};
    for (const r of prezziRaw) {
      if (r.fornitore.trim() && r.prezzo) {
        const p = parseFloat(r.prezzo.replace(",","."));
        if (p > 0) prezzi[r.fornitore.trim()] = p;
      }
    }
    setBusy(true);
    try {
      const payload = {nome:nome.trim(), categoria, conf, prezzi, custom:true};
      if (isEdit) await axios.put(`${API}/listino/prodotti/${prodotto.id}`, payload);
      else        await axios.post(`${API}/listino/prodotti`, payload);
      onSaved();
    } catch(e) { setErr(e.response?.data?.detail||"Errore"); setBusy(false); }
  };

  return (
    <div style={overlay}>
      <div style={{...box, maxWidth:500}}>
        <h3 style={{margin:"0 0 18px",fontSize:17,fontWeight:800,color:"#1e293b"}}>
          {isEdit?"Modifica prodotto":"Nuovo prodotto"}
        </h3>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:14}}>
          <div style={{gridColumn:"1/-1"}}>
            <label style={lbl}>Nome</label>
            <input value={nome} onChange={e=>setNome(e.target.value)} style={inp} placeholder="es. ACQUA SAN PELLEGRINO CL.50 CTX24"/>
          </div>
          <div><label style={lbl}>Categoria</label>
            <select value={categoria} onChange={e=>setCategoria(e.target.value)} style={inp}>
              {CATS.map(c=><option key={c}>{c}</option>)}
            </select>
          </div>
          <div><label style={lbl}>Confezione</label>
            <input value={conf} onChange={e=>setConf(e.target.value)} style={inp} placeholder="CT / BT / PZ / KG"/>
          </div>
        </div>
        <label style={lbl}>Prezzi per fornitore</label>
        {prezziRaw.map((r,i)=>(
          <div key={i} style={{display:"flex",gap:8,marginBottom:8,alignItems:"center"}}>
            <input value={r.fornitore} onChange={e=>setPrezziRaw(pr=>pr.map((x,j)=>j===i?{...x,fornitore:e.target.value}:x))}
              style={{...inp,flex:2}} placeholder="Fornitore" list="forn-list"/>
            <datalist id="forn-list">{fornitori.map(f=><option key={f.id} value={f.nome}/>)}</datalist>
            <input value={r.prezzo} onChange={e=>setPrezziRaw(pr=>pr.map((x,j)=>j===i?{...x,prezzo:e.target.value}:x))}
              style={{...inp,flex:1}} placeholder="€" type="number" step="0.01" min="0"/>
            <button onClick={()=>setPrezziRaw(pr=>pr.filter((_,j)=>j!==i))}
              style={{background:"none",border:"none",color:"var(--danger)",fontSize:18,cursor:"pointer"}}>×</button>
          </div>
        ))}
        <button onClick={()=>setPrezziRaw(r=>[...r,{fornitore:"",prezzo:""}])}
          style={{fontSize:12,color:"var(--info)",background:"none",border:"none",cursor:"pointer",marginBottom:14}}>
          + Aggiungi fornitore
        </button>
        {err && <p style={{color:"var(--danger)",fontSize:12,margin:"0 0 10px"}}>{err}</p>}
        <div style={{display:"flex",gap:10}}>
          <button onClick={onClose} style={btnSec} disabled={busy}>Annulla</button>
          <button onClick={salva} style={btnBlue} disabled={busy}>{busy?"Salvo...":"Salva"}</button>
        </div>
      </div>
    </div>
  );
}

// ── Card prodotto ──────────────────────────────────────────────────────────────
function CardProdotto({prod, fornitori, onEdit, onDelete, onToggleFav}) {
  const prezzi   = prod.prezzi||{};
  const voci     = Object.entries(prezzi).sort((a,b)=>a[1]-b[1]);
  const best     = prod.miglior_fornitore;
  const hasAlias = !!prod.gruppo_alias_id;
  const cc       = catClr(prod.categoria);

  // Delta % tra fornitore migliore e peggiore (se multi-fornitore)
  let delta = null;
  if (voci.length >= 2) {
    const min = voci[0][1], max = voci[voci.length-1][1];
    delta = Math.round(((max-min)/min)*100);
  }

  return (
    <div data-testid={`card-listino-${prod.id}`} style={{
      background:"#fff", borderRadius:14, padding:"14px 16px",
      border:"1.5px solid #e5e7eb",
      display:"flex", flexDirection:"column", gap:10,
    }}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",gap:8}}>
        <div style={{flex:1,minWidth:0}}>
          <div style={{display:"flex",gap:5,marginBottom:5,flexWrap:"wrap"}}>
            <span style={{
              fontSize:9,fontWeight:700,letterSpacing:.5,textTransform:"uppercase",
              background:cc+"22",color:cc,borderRadius:4,padding:"2px 7px",
            }}>{prod.categoria}</span>
            {hasAlias && (
              <span style={{
                fontSize:9,fontWeight:700,letterSpacing:.5,textTransform:"uppercase",
                background:"#e8efe9",color:"#5b7a6b",borderRadius:4,padding:"2px 7px",
              }}>ALIAS</span>
            )}
            {delta !== null && (
              <span style={{
                fontSize:9,fontWeight:700,letterSpacing:.5,
                background:"#fff7ed",color:"#c2410c",borderRadius:4,padding:"2px 7px",
              }}>Δ{delta}%</span>
            )}
          </div>
          <p style={{margin:0,fontSize:13,fontWeight:700,color:"#1e293b",lineHeight:1.35}}>{prod.nome}</p>
          <p style={{margin:"2px 0 0",fontSize:11,color:"#94a3b8"}}>{prod.conf}{prod.preferito?" · ⭐":""}</p>
        </div>
        <div style={{textAlign:"right",flexShrink:0}}>
          {best && prezzi[best]!=null ? (
            <>
              <div style={{fontSize:18,fontWeight:800,color:"var(--success-dark)"}}>{fmtP(prezzi[best])}</div>
              <div style={{fontSize:10,color:"#6b7280"}}>{best}</div>
            </>
          ) : <div style={{fontSize:13,color:"#94a3b8"}}>—</div>}
        </div>
      </div>

      {/* Prezzi multi-fornitore */}
      {voci.length > 1 && (
        <div style={{display:"flex",flexWrap:"wrap",gap:5}}>
          {voci.map(([f,p])=>(
            <span key={f} style={{
              fontSize:10,padding:"2px 8px",borderRadius:16,
              background: f===best?"#dcfce7":"#f1f5f9",
              color: f===best?"var(--success-dark)":"#475569",
              fontWeight: f===best?700:500,
            }}>{f}: {fmtP(p)}</span>
          ))}
        </div>
      )}

      <div style={{display:"flex",gap:6,marginTop:2,justifyContent:"flex-end"}}>
        <button onClick={()=>onToggleFav(prod)} style={iconBtn} title="Preferito">{prod.preferito?"⭐":"☆"}</button>
        <button onClick={()=>onEdit(prod)} style={iconBtn} title="Modifica">✎</button>
        <button onClick={()=>onDelete(prod)} style={{...iconBtn,color:"var(--danger)",background:"#fff1f2"}} title="Elimina">✕</button>
      </div>
    </div>
  );
}

// ── Pannello PDF listino (l'invio email è stato rimosso dal backend) ──────────
function PannelloInvioListino({ fornitori, prodotti, onChiudi, onToast }) {
  const [sconto, setSconto] = useState(0);
  const [conIva, setConIva] = useState(false);
  const [iva, setIva]       = useState(22);
  const [fonte, setFonte]   = useState("best");
  const [busy, setBusy]     = useState(false);

  const fonti = [...new Set((prodotti || []).flatMap(p => Object.keys(p.prezzi || {})))]
    .sort((a, b) => norm(a).localeCompare(norm(b)));

  const scarica = async () => {
    setBusy(true);
    try {
      const res = await axios.post(`${API}/listino/genera-pdf`, { sconto, con_iva: conIva, iva, fonte }, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a"); a.href = url; a.download = "listino_ceraldi.pdf"; document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      onToast && onToast("PDF del listino scaricato");
      onChiudi();
    } catch { onToast && onToast("Errore nel generare il PDF"); } finally { setBusy(false); }
  };

  const btnTab = (on, bg) => ({ flex: 1, minWidth: 56, padding: "10px 0", borderRadius: 9, fontWeight: 800, fontSize: 13, cursor: "pointer", border: on ? "none" : "1.5px solid #e2e8f0", background: on ? bg : "#fff", color: on ? "#fff" : "#475569" });

  return (
    <div style={overlay} onClick={onChiudi}>
      <div style={{ ...box, maxWidth: 560, maxHeight: "88vh", display: "flex", flexDirection: "column", padding: 22 }} onClick={e => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 18, fontWeight: 800, color: "#1e293b" }}>Genera PDF del listino</h3>
          <button onClick={onChiudi} style={{ background: "none", border: "none", fontSize: 22, cursor: "pointer", color: "#94a3b8" }}>×</button>
        </div>

        <label style={lbl}>Sconto da applicare ai prezzi</label>
        <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
          {[0, 2, 4, 8, 10].map(v => (
            <button key={v} onClick={() => setSconto(v)} style={btnTab(sconto === v, "#8a6f47")}>{v === 0 ? "Nessuno" : `${v}%`}</button>
          ))}
        </div>

        <label style={lbl}>Prezzi</label>
        <div style={{ display: "flex", gap: 8, marginBottom: 14, alignItems: "center" }}>
          <button onClick={() => setConIva(false)} style={btnTab(!conIva, "#4a3f33")}>Senza IVA</button>
          <button onClick={() => setConIva(true)} style={btnTab(conIva, "#4a3f33")}>Con IVA</button>
          {conIva && (
            <select value={iva} onChange={e => setIva(Number(e.target.value))} style={{ ...inp, width: 92, flex: "none" }}>
              <option value={4}>4%</option><option value={10}>10%</option><option value={22}>22%</option>
            </select>
          )}
        </div>

        <label style={lbl}>Prezzi di partenza (fornitore)</label>
        <select value={fonte} onChange={e => setFonte(e.target.value)} style={{ ...inp, marginBottom: 4 }}>
          <option value="best">Prezzo più basso tra tutti i fornitori</option>
          {fonti.map(f => <option key={f} value={f}>{f}</option>)}
        </select>
        <p style={{ fontSize: 11, color: "#94a3b8", margin: "0 0 14px" }}>Il listino userà i prezzi di questo fornitore, scontati. “Prezzo più basso” usa il migliore disponibile.</p>

        <button onClick={scarica} disabled={busy} style={{ ...btnBlue, background: "#8a6f47" }}>
          {busy ? "Genero…" : "⬇ Scarica PDF listino"}
        </button>
        <p style={{ fontSize: 11, color: "#94a3b8", margin: "10px 0 0", textAlign: "center" }}>PDF professionale con i dati Ceraldi Group, da condividere via WhatsApp o email.</p>
      </div>
    </div>
  );
}

// ── Genera & Esporta: best/media/ultimo + filtro + sconto + PDF ────────────────
function GeneraListino({ categorie }) {
  const [modo,      setModo]      = useState("best");
  const [filtro,    setFiltro]    = useState("categoria"); // categoria | fornitore | prodotto
  const [categoria, setCategoria] = useState("");
  const [fornitore, setFornitore] = useState("");
  const [prodotto,  setProdotto]  = useState("");
  const [sconto,    setSconto]    = useState(0);
  const [analc,     setAnalc]     = useState("tutte");     // tutte | alc | analc
  const [fornElenco,setFornElenco]= useState([]);
  const [righe,     setRighe]     = useState(null);
  const [loading,   setLoading]   = useState(false);
  const [err,       setErr]       = useState("");

  useEffect(()=>{ axios.get(`${API}/listino/fornitori-elenco`).then(r=>setFornElenco(r.data.fornitori||[])).catch(()=>{}); },[]);

  const buildParams = () => {
    const p = new URLSearchParams();
    p.set("modo", modo);
    if (sconto) p.set("sconto", String(sconto));
    if (filtro==="categoria" && categoria) {
      p.set("categoria", categoria);
      if (categoria==="BIRRE" && analc!=="tutte") p.set("analcoliche", analc==="analc"?"true":"false");
    }
    if (filtro==="fornitore" && fornitore) p.set("fornitore", fornitore);
    if (filtro==="prodotto"  && prodotto)  p.set("prodotto", prodotto);
    return p;
  };

  const calcola = async () => {
    setLoading(true); setErr(""); setRighe(null);
    try { const r = await axios.get(`${API}/listino/calcola?${buildParams()}`); setRighe(r.data.righe||[]); }
    catch(e){ setErr(e.response?.data?.detail || "Errore nel calcolo"); }
    finally{ setLoading(false); }
  };

  const scaricaPDF = async () => {
    setErr("");
    try {
      const r = await axios.get(`${API}/listino/calcola-pdf?${buildParams()}`, { responseType:"blob" });
      const url = URL.createObjectURL(new Blob([r.data],{type:"application/pdf"}));
      const a = document.createElement("a"); a.href=url; a.download=`listino_${modo}.pdf`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch(e){ setErr("Errore generazione PDF"); }
  };

  const segBtn = (attivo) => ({
    padding:"8px 14px",borderRadius:8,border:attivo?"none":"1.5px solid #e2e8f0",cursor:"pointer",
    fontWeight:700,fontSize:13,background:attivo?"var(--info)":"#fff",color:attivo?"#fff":"#64748b",
  });

  return (
    <div>
      <div style={{display:"flex",flexWrap:"wrap",gap:18,marginBottom:16}}>
        {/* Modo prezzo */}
        <div>
          <span style={lbl}>Modalità prezzo</span>
          <div style={{display:"flex",gap:8}}>
            {[["best","Miglior prezzo"],["media","Media prezzi"],["ultimo","Ultimo prezzo"]].map(([id,l])=>(
              <button key={id} onClick={()=>setModo(id)} style={segBtn(modo===id)}>{l}</button>
            ))}
          </div>
        </div>
        {/* Sconto */}
        <div>
          <span style={lbl}>Sconto</span>
          <div style={{display:"flex",gap:6}}>
            {[0,3,5,7,10].map(s=>(
              <button key={s} onClick={()=>setSconto(s)} style={segBtn(sconto===s)}>{s===0?"Nessuno":`${s}%`}</button>
            ))}
          </div>
        </div>
      </div>

      {/* Filtro */}
      <div style={{marginBottom:16}}>
        <span style={lbl}>Filtra per</span>
        <div style={{display:"flex",gap:8,marginBottom:10}}>
          {[["categoria","Categoria"],["fornitore","Fornitore"],["prodotto","Prodotto"]].map(([id,l])=>(
            <button key={id} onClick={()=>setFiltro(id)} style={segBtn(filtro===id)}>{l}</button>
          ))}
        </div>
        {filtro==="categoria" && (
          <div style={{display:"flex",gap:10,flexWrap:"wrap",alignItems:"center"}}>
            <select value={categoria} onChange={e=>setCategoria(e.target.value)} style={{...inp,maxWidth:260}}>
              <option value="">— tutte le categorie —</option>
              {categorie.map(c=><option key={c} value={c}>{c}</option>)}
            </select>
            {categoria==="BIRRE" && (
              <div style={{display:"flex",gap:6}}>
                {[["tutte","Tutte"],["alc","Alcoliche"],["analc","Analcoliche"]].map(([id,l])=>(
                  <button key={id} onClick={()=>setAnalc(id)} style={segBtn(analc===id)}>{l}</button>
                ))}
              </div>
            )}
          </div>
        )}
        {filtro==="fornitore" && (
          <>
            <input list="forn-elenco" value={fornitore} onChange={e=>setFornitore(e.target.value)}
              placeholder="Scrivi o scegli il fornitore..." style={{...inp,maxWidth:360}}/>
            <datalist id="forn-elenco">{fornElenco.map(f=><option key={f} value={f}/>)}</datalist>
          </>
        )}
        {filtro==="prodotto" && (
          <input value={prodotto} onChange={e=>setProdotto(e.target.value)}
            placeholder="Es. PERONI CL.33 — anche parziale" style={{...inp,maxWidth:360}}/>
        )}
      </div>

      <div style={{display:"flex",gap:10,marginBottom:18}}>
        <button onClick={calcola} disabled={loading} style={{...btnBlue,opacity:loading?.6:1}}>
          {loading?"Calcolo...":"Calcola"}
        </button>
        <button onClick={scaricaPDF} disabled={!righe||!righe.length} style={{...btnSec,opacity:(!righe||!righe.length)?.5:1}}>
          ⬇ Scarica PDF
        </button>
      </div>

      {err && <div style={{background:"#fef2f2",border:"1px solid #fecaca",color:"#b91c1c",borderRadius:8,padding:"10px 14px",marginBottom:14,fontSize:13}}>{err}</div>}

      {righe && (
        righe.length===0 ? (
          <div style={{textAlign:"center",color:"#94a3b8",paddingTop:40,fontSize:14}}>Nessun prodotto per questi criteri.</div>
        ) : (
          <div style={{border:"1px solid #e2e8f0",borderRadius:12,overflow:"hidden"}}>
            <div style={{display:"flex",justifyContent:"space-between",padding:"10px 14px",background:"#f8fafc",fontSize:13,fontWeight:700,color:"#475569"}}>
              <span>{righe.length} prodotti</span>
              <span>{({best:"Miglior prezzo",media:"Media prezzi",ultimo:"Ultimo prezzo"})[modo]}{sconto?` · -${sconto}%`:""}</span>
            </div>
            <div style={{maxHeight:520,overflowY:"auto",overflowX:"auto"}}>
              <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>
                <thead><tr style={{background:"#fff",borderBottom:"2px solid #e2e8f0"}}>
                  <th style={{textAlign:"left",padding:"8px 12px",fontSize:11,color:"#64748b"}}>PRODOTTO</th>
                  <th style={{textAlign:"left",padding:"8px 12px",fontSize:11,color:"#64748b"}}>FORNITORE</th>
                  <th style={{textAlign:"center",padding:"8px 12px",fontSize:11,color:"#64748b"}}>ULT. ACQ.</th>
                  <th style={{textAlign:"right",padding:"8px 12px",fontSize:11,color:"#64748b"}}>PREZZO</th>
                </tr></thead>
                <tbody>
                  {righe.map((r,i)=>(
                    <tr key={i} style={{borderBottom:"1px solid #f1f5f9",background:i%2?"#fbfaff":"#fff"}}>
                      <td style={{padding:"7px 12px",color:"#1e293b"}}>{r.nome}</td>
                      <td style={{padding:"7px 12px",color:"#64748b",fontSize:12}}>{r.fornitore||"—"}</td>
                      <td style={{padding:"7px 12px",textAlign:"center",color:"#475569",fontSize:12}}>{r.data_ultimo||"—"}</td>
                      <td style={{padding:"7px 12px",textAlign:"right",fontWeight:700,color:"#0f172a"}}>{fmtP(r.prezzo)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      )}
    </div>
  );
}

export default function ListinoView() {
  const [view,      setView]      = useState("genera");
  const [prodotti,  setProdotti]  = useState([]);
  const [categorie, setCategorie] = useState([]);
  const [fornitori, setFornitori] = useState([]);
  const [catSel,    setCatSel]    = useState("tutti");
  const [search,    setSearch]    = useState("");
  const [soloFav,   setSoloFav]   = useState(false);
  const [loading,   setLoading]   = useState(true);
  const [syncing,   setSyncing]   = useState(false);
  const [syncMsg,   setSyncMsg]   = useState("");
  const [modalP,    setModalP]    = useState(null);
  const [showInvio, setShowInvio] = useState(false);
  const [toastMsg,  setToastMsg]  = useState("");

  const carica = useCallback(async()=>{
    setLoading(true);
    const params = new URLSearchParams();
    if(search)           params.set("search",search);
    if(catSel!=="tutti") params.set("categoria",catSel);
    if(soloFav)          params.set("preferiti","true");
    try{
      const [pRes,cRes,fRes] = await Promise.all([
        axios.get(`${API}/listino/prodotti?${params}`),
        axios.get(`${API}/listino/categorie`),
        axios.get(`${API}/fornitori`),
      ]);
      setProdotti(pRes.data);
      setCategorie(cRes.data.categorie||[]);
      setFornitori(fRes.data||[]);
    }finally{setLoading(false);}
  },[search,catSel,soloFav]);

  useEffect(()=>{carica();},[carica]);

  const toast = (m)=>{setToastMsg(m);setTimeout(()=>setToastMsg(""),3500);};

  const syncDaFatture = async()=>{
    setSyncing(true);setSyncMsg("");
    try{
      const r = await axios.post(`${API}/listino/sync-da-fatture`);
      setSyncMsg(r.data.message);
      await carica();
    }catch(e){setSyncMsg(e.response?.data?.detail||"Errore sync");}
    finally{setSyncing(false);}
  };

  const handleDelete = async(prod)=>{
    if(!await conferma(`Eliminare "${prod.nome}"?`))return;
    await axios.delete(`${API}/listino/prodotti/${prod.id}`);
    await carica();
  };

  return (
    <div style={{padding:"0 0 40px"}}>
      {/* Header */}
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:18,flexWrap:"wrap",gap:12}}>
        <div>
          <h2 style={{margin:0,fontSize:22,fontWeight:800,color:"#0f172a"}}>Listino Prezzi</h2>
          <p style={{margin:"4px 0 0",fontSize:13,color:"#64748b"}}>
            {prodotti.length} prodotti · prezzi per fornitore da fatture XML
          </p>
        </div>
        <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
          {view==="catalogo" && <>
            <button data-testid="btn-sync-listino" onClick={syncDaFatture} disabled={syncing}
              style={{...btnSec,padding:"9px 14px",fontSize:13}}>
              {syncing?"Sync...":"↻ Sync da fatture"}
            </button>
            <button data-testid="btn-nuovo-prodotto" onClick={()=>setModalP("new")}
              style={{...btnBlue,padding:"9px 14px",fontSize:13}}>
              + Prodotto
            </button>
            <button data-testid="btn-invia-listino" onClick={()=>setShowInvio(true)}
              style={{padding:"9px 14px",fontSize:13,fontWeight:700,borderRadius:8,border:"none",background:"#8a6f47",color:"#fff",cursor:"pointer"}}>
              Invia listino
            </button>
          </>}
        </div>
      </div>

      {/* Sub-tab */}
      <div style={{display:"flex",gap:0,marginBottom:20,borderBottom:"2px solid #e2e8f0"}}>
        {VIEWS.map(v=>(
          <button key={v.id} onClick={()=>setView(v.id)} style={{
            padding:"10px 18px",border:"none",background:"transparent",cursor:"pointer",
            fontWeight:700,fontSize:13,color:view===v.id?"var(--info)":"#64748b",
            borderBottom:`2px solid ${view===v.id?"var(--info)":"transparent"}`,
            marginBottom:-2,
          }}>{v.label}</button>
        ))}
      </div>

      {/* Sync msg */}
      {syncMsg && (
        <div style={{background:"#f0fdf4",border:"1px solid #86efac",borderRadius:8,padding:"10px 14px",marginBottom:14,fontSize:13,color:"var(--success-dark)"}}>
          {syncMsg}
        </div>
      )}

      {/* ── CATALOGO ── */}
      {view==="catalogo" && (
        <>
          <div style={{display:"flex",gap:10,marginBottom:12}}>
            <input data-testid="input-search-listino" value={search} onChange={e=>setSearch(e.target.value)}
              placeholder="Cerca prodotto..." style={{flex:1,padding:"10px 14px",borderRadius:10,border:"1.5px solid #e2e8f0",fontSize:14,outline:"none"}}/>
            <button onClick={()=>setSoloFav(v=>!v)} style={{
              padding:"10px 14px",borderRadius:10,border:"none",cursor:"pointer",fontWeight:700,fontSize:13,
              background:soloFav?"var(--warning-soft)":"#f1f5f9",color:soloFav?"var(--warning-dark)":"#64748b",
            }}>{soloFav?"⭐ Preferiti":"☆ Tutti"}</button>
          </div>

          {/* Filtri categoria */}
          <div style={{display:"flex",gap:8,marginBottom:18,overflowX:"auto",paddingBottom:4}}>
            {["tutti",...categorie].map(cat=>(
              <button key={cat} data-testid={`filtro-cat-listino-${cat}`}
                onClick={()=>setCatSel(cat)} style={{
                  padding:"6px 14px",borderRadius:20,cursor:"pointer",fontWeight:700,fontSize:12,
                  whiteSpace:"nowrap",flexShrink:0,transition:"all .15s",
                  border: catSel===cat?"none":"1.5px solid #e2e8f0",
                  background: catSel===cat ? catClr(cat.toUpperCase()) : "#fff",
                  color: catSel===cat?"#fff":"#64748b",
                }}>{cat==="tutti"?"Tutti":cat}</button>
            ))}
          </div>

          {loading ? (
            <div style={{textAlign:"center",color:"#94a3b8",paddingTop:60,fontSize:15}}>Caricamento...</div>
          ) : prodotti.length===0 ? (
            <div style={{textAlign:"center",color:"#94a3b8",paddingTop:60}}>
              <p style={{fontSize:15,fontWeight:600}}>Nessun prodotto</p>
              <p style={{fontSize:13}}>Clicca "Sync da fatture" per importare i prezzi dalle fatture XML</p>
              <button onClick={syncDaFatture} disabled={syncing} style={{...btnBlue,marginTop:12}}>Sync da fatture XML</button>
            </div>
          ) : (
            <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(300px,1fr))",gap:14}}>
              {prodotti.map(p=>(
                <CardProdotto key={p.id} prod={p} fornitori={fornitori}
                  onEdit={()=>setModalP(p)} onDelete={handleDelete}
                  onToggleFav={async(pr)=>{await axios.patch(`${API}/listino/prodotti/${pr.id}/preferito`);await carica();}}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* ── GENERA & ESPORTA ── */}
      {view==="genera" && <GeneraListino categorie={categorie} />}

      {/* Modal prodotto */}
      {modalP && (
        <ModalProdotto prodotto={modalP==="new"?null:modalP} fornitori={fornitori}
          onClose={()=>setModalP(null)}
          onSaved={async()=>{setModalP(null);await carica();}}/>
      )}

      {/* Carrello */}
      {showInvio && (
        <PannelloInvioListino fornitori={fornitori} prodotti={prodotti} onToast={toast} onChiudi={()=>setShowInvio(false)} />
      )}
      {/* Toast */}
      {toastMsg && (
        <div style={{
          position:"fixed",bottom:24,left:"50%",transform:"translateX(-50%)",
          background:"#1e293b",color:"#fff",padding:"12px 24px",borderRadius:12,
          fontSize:14,fontWeight:600,zIndex:9999,boxShadow:"0 8px 32px rgba(0,0,0,.3)",
        }}>{toastMsg}</div>
      )}
    </div>
  );
}

// ── Stili ──────────────────────────────────────────────────────────────────────
const overlay = {position:"fixed",inset:0,background:"rgba(0,0,0,0.6)",display:"flex",alignItems:"center",justifyContent:"center",zIndex:500,padding:16};
const box     = {background:"#fff",borderRadius:18,padding:28,width:"100%",boxShadow:"0 20px 60px rgba(0,0,0,.35)",overflow:"hidden"};
const lbl     = {display:"block",fontSize:11,fontWeight:700,color:"#64748b",marginBottom:5,textTransform:"uppercase",letterSpacing:.5};
const inp     = {width:"100%",padding:"9px 12px",borderRadius:8,border:"1.5px solid #e2e8f0",fontSize:14,outline:"none",boxSizing:"border-box"};
const btnBlue = {padding:"10px 18px",borderRadius:8,border:"none",background:"var(--info)",color:"#fff",fontWeight:700,fontSize:14,cursor:"pointer"};
const btnSec  = {padding:"10px 18px",borderRadius:8,border:"1.5px solid #e2e8f0",background:"#fff",color:"#475569",fontWeight:700,fontSize:14,cursor:"pointer"};
const iconBtn = {padding:"8px 10px",borderRadius:8,border:"none",background:"#f8fafc",cursor:"pointer",fontSize:13,color:"#64748b"};
const qtyBtn  = {width:28,height:28,borderRadius:6,border:"1.5px solid #e2e8f0",background:"#f8fafc",cursor:"pointer",fontSize:16,fontWeight:700};
