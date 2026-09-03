/**
 * TabProdotti (prodotti e soglie di riordino) — estratto da BackofficeView.jsx (refactor 25/07/2026).
 * Markup e logica identici: cambia solo il file che li contiene.
 */
import { useState, useEffect, useCallback } from "react";
import { conferma } from "../../../utils/conferma";
import axios from "axios";
import { toast } from "./toastBackoffice";
// usati dal blocco prodotti: senza questi due import la pagina crasherebbe
// a runtime (la build non se ne accorge)
import { withToken } from "../../../utils/constants";
import { getOperatoreNome } from "../../../auth";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

// ══════════════════════════════════════════════════════════════════
// 1. PRODOTTI & SOGLIE RIORDINO
// ══════════════════════════════════════════════════════════════════

function RowProdotto({ prod, onSave }) {
  const [soglia,  setSoglia]  = useState(prod.soglia_minima ?? 0);
  const [qRiord,  setQRiord]  = useState(prod.quantita_riordino ?? 0);
  const [saving,  setSaving]  = useState(false);
  const changed = String(soglia) !== String(prod.soglia_minima ?? 0) || String(qRiord) !== String(prod.quantita_riordino ?? 0);
  const sottoScorta = prod.stock > 0 && soglia > 0 && prod.stock < soglia;
  const esaurito    = prod.stock === 0 || prod.stock === null;

  const salva = async () => {
    setSaving(true);
    try {
      await axios.patch(`${API}/magazzino-bar/prodotti/${prod.id}/soglia`, {
        soglia_minima:      parseFloat(soglia) || 0,
        quantita_riordino:  parseFloat(qRiord) || 0,
      });
      onSave(prod.id, parseFloat(soglia) || 0, parseFloat(qRiord) || 0);
      toast("Salvato");
    } catch { toast("Errore salvataggio", "err"); }
    finally { setSaving(false); }
  };

  const riordina = async () => {
    if (!qRiord) { toast("Imposta prima la quantità di riordino", "warn"); return; }
    setSaving(true);
    try {
      await axios.post(`${API}/ordini-fornitori`, {
        reparto: "magazzino", operatore: getOperatoreNome() || "Backoffice",
        source: "backoffice",
        prodotti: [{
          prodotto_id: prod.id, nome: prod.nome,
          fornitore: prod.fornitore || "",
          quantita: parseFloat(qRiord),
          unita: prod.unita || "cf",
          prezzo_ultimo: 0,
          richiesto_da: getOperatoreNome() || "Backoffice",
          note: `Riordino da Backoffice — stock: ${prod.stock} ${prod.unita}`,
        }],
      });
      toast(`Ordine creato: ${prod.nome}`);
    } catch { toast("Errore ordine", "err"); }
    finally { setSaving(false); }
  };

  const semaforoColor = esaurito ? "var(--danger)" : sottoScorta ? "var(--warning)" : "var(--success)";
  const lbl = { fontSize:10, fontWeight:800, color:"var(--text-3)", textTransform:"uppercase", letterSpacing:".05em", display:"block", marginBottom:3 };
  const inp = { width:86, padding:"8px 8px", border:"1.5px solid var(--border)", borderRadius:10,
                fontSize:14, textAlign:"center", fontFamily:"var(--font)", color:"var(--text)", background:"#fff" };

  return (
    <div style={{background: sottoScorta || esaurito ? "#fdf6ec" : "var(--card)",
                 border:"1px solid var(--border)", borderRadius:14, padding:"12px 14px",
                 marginBottom:8, boxShadow:"var(--shadow-list)"}}>
      <div style={{display:"flex", alignItems:"center", gap:10}}>
        <div style={{width:9,height:9,borderRadius:99,background:semaforoColor,flexShrink:0}}/>
        <div style={{flex:1, minWidth:0}}>
          <div style={{fontWeight:700,fontSize:14,color:"var(--text)",overflow:"hidden",textOverflow:"ellipsis"}}>{prod.nome}</div>
          <div style={{fontSize:11,color:"var(--text-3)"}}>{prod.categoria} · {prod.fornitore || "—"}</div>
        </div>
        <div style={{textAlign:"right",flexShrink:0}}>
          <div style={{fontWeight:800,fontSize:18,color:semaforoColor,lineHeight:1}}>{prod.stock ?? 0}</div>
          <div style={{fontSize:10,color:"var(--text-3)"}}>{prod.unita} in stock</div>
        </div>
      </div>
      <div style={{display:"flex", alignItems:"flex-end", gap:10, marginTop:10, flexWrap:"wrap"}}>
        <label>
          <span style={lbl}>Soglia min.</span>
          <input type="number" min="0" value={soglia} onChange={e => setSoglia(e.target.value)} style={inp}/>
        </label>
        <label>
          <span style={lbl}>Qt. riordino</span>
          <input type="number" min="0" value={qRiord} onChange={e => setQRiord(e.target.value)} style={inp}/>
        </label>
        <div style={{flex:1}}/>
        {changed && (
          <button onClick={salva} disabled={saving}
            style={{padding:"9px 18px",border:"none",borderRadius:10,background:"var(--primary)",color:"#fff",fontWeight:800,fontSize:13,cursor:"pointer",fontFamily:"var(--font)"}}>
            {saving ? "…" : "Salva"}
          </button>
        )}
        {(sottoScorta || esaurito) && (
          <button onClick={riordina} disabled={saving}
            style={{padding:"9px 14px",border:"none",borderRadius:10,background:"var(--warning)",color:"#fff",fontWeight:800,fontSize:13,cursor:"pointer",fontFamily:"var(--font)"}}>
            📦 Riordina
          </button>
        )}
      </div>
    </div>
  );
}

function PannelloSoglieSuggerite({ onApplicato }) {
  const [aperto, setAperto] = useState(false);
  const [sugg, setSugg] = useState(null);
  const [busy, setBusy] = useState(false);

  const calcola = async () => {
    setBusy(true);
    try {
      const r = await axios.get(`${API}/magazzino-bar/soglie-suggerite`);
      setSugg(r.data?.suggerimenti || []);
    } catch { toast("Calcolo non riuscito", "err"); }
    finally { setBusy(false); }
  };
  const applica = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/magazzino-bar/soglie-suggerite/applica`, { solo_mancanti: true });
      toast(`${r.data?.applicate || 0} soglie applicate dai consumi`);
      setSugg(null); setAperto(false); onApplicato && onApplicato();
    } catch { toast("Applicazione non riuscita", "err"); }
    finally { setBusy(false); }
  };

  return (
    <div style={{background:"var(--card)",borderRadius:14,padding:"14px 16px",boxShadow:"var(--shadow-list)",marginBottom:16,borderLeft:"4px solid #8a6f47"}}>
      <button onClick={()=>{ setAperto(a=>!a); if(!sugg) calcola(); }} style={{all:"unset",cursor:"pointer",display:"flex",alignItems:"center",gap:8,fontWeight:800,color:"var(--text)",fontSize:15}}>
        📊 Soglie suggerite dai consumi {aperto ? "▲" : "▼"}
      </button>
      {aperto && (
        <div style={{marginTop:12}}>
          <div style={{fontSize:12,color:"var(--text-2)",marginBottom:10}}>
            Calcolate dallo storico acquisti delle tue fatture (quantita media per acquisto). Rispetta le soglie gia' messe a mano.
          </div>
          {busy && !sugg && <div style={{color:"var(--text-2)"}}>Calcolo dai consumi…</div>}
          {sugg && (<>
            <div style={{fontSize:13,fontWeight:800,marginBottom:8}}>{sugg.length} prodotti con storico acquisti</div>
            <div style={{maxHeight:240,overflowY:"auto",marginBottom:10}}>
              {sugg.slice(0,40).map(s=>(
                <div key={s.id} style={{display:"flex",alignItems:"center",gap:8,padding:"6px 0",borderBottom:"1px solid var(--border)",fontSize:13}}>
                  <span style={{flex:1,minWidth:0,fontWeight:600,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{s.nome}</span>
                  <span style={{color:"var(--text-2)"}}>{s.acquisti_storici}× acq.</span>
                  <span style={{fontWeight:800,color:"#8a6f47"}}>→ {s.soglia_suggerita}</span>
                </div>
              ))}
            </div>
            <button onClick={applica} disabled={busy}
              style={{width:"100%",padding:"10px 16px",borderRadius:10,border:"none",background:"#8a6f47",color:"#fff",fontWeight:800,cursor:busy?"wait":"pointer"}}>
              {busy ? "Applico…" : `Applica le ${sugg.length} soglie suggerite (solo dove mancano)`}
            </button>
          </>)}
        </div>
      )}
    </div>
  );
}

function TabProdotti() {
  const [prodotti, setProdotti] = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [search,   setSearch]   = useState("");
  const [filtro,   setFiltro]   = useState("tutti");

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/magazzino-bar/prodotti`);
      setProdotti(r.data || []);
    } catch { toast("Errore caricamento", "err"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  const onSave = (id, soglia, qRiord) => {
    setProdotti(p => p.map(x => x.id === id ? {...x, soglia_minima: soglia, quantita_riordino: qRiord} : x));
  };

  const filtrati = prodotti
    .filter(p => {
      if (search && !p.nome?.toLowerCase().includes(search.toLowerCase()) &&
          !p.categoria?.toLowerCase().includes(search.toLowerCase())) return false;
      if (filtro === "sotto") return (p.stock ?? 0) > 0 && p.soglia_minima > 0 && p.stock < p.soglia_minima;
      if (filtro === "esauriti") return (p.stock ?? 0) === 0;
      if (filtro === "senza_soglia") return !p.soglia_minima || p.soglia_minima === 0;
      return true;
    })
    .sort((a, b) => {
      const aKo = (a.stock ?? 0) <= (a.soglia_minima ?? 0) && (a.soglia_minima ?? 0) > 0;
      const bKo = (b.stock ?? 0) <= (b.soglia_minima ?? 0) && (b.soglia_minima ?? 0) > 0;
      if (aKo !== bKo) return aKo ? -1 : 1;
      return (a.nome || "").localeCompare(b.nome || "", "it");
    });

  const nSotto    = prodotti.filter(p => (p.stock ?? 0) > 0 && p.soglia_minima > 0 && p.stock < p.soglia_minima).length;
  const nEsauriti = prodotti.filter(p => (p.stock ?? 0) === 0).length;

  return (
    <div>
      {/* KPI */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:12,marginBottom:20}}>
        {[
          ["Totale prodotti", prodotti.length, "var(--primary)"],
          ["Sotto scorta",    nSotto,          "var(--warning)"],
          ["Esauriti",        nEsauriti,       "var(--danger)"],
        ].map(([lbl, val, col]) => (
          <div key={lbl} style={{background:"var(--card)",borderRadius:14,padding:"14px 16px",boxShadow:"var(--shadow-list)",borderLeft:`4px solid ${col}`}}>
            <div style={{fontSize:22,fontWeight:800,color:col}}>{val}</div>
            <div style={{fontSize:12,color:"var(--text-2)",marginTop:2}}>{lbl}</div>
          </div>
        ))}
      </div>

      {/* Filtri */}
      <PannelloSoglieSuggerite onApplicato={carica} />

      <div style={{display:"flex",gap:8,marginBottom:14,flexWrap:"wrap",alignItems:"center"}}>
        <input value={search} onChange={e=>setSearch(e.target.value)}
          placeholder="🔍 Cerca prodotto…"
          style={{padding:"8px 14px",border:"1.5px solid var(--border)",borderRadius:10,fontSize:14,fontFamily:"var(--font)",flex:1,minWidth:180}}/>
        {[["tutti","Tutti"],["sotto","⚠️ Sotto scorta"],["esauriti","🔴 Esauriti"],["senza_soglia","Senza soglia"]].map(([id,lbl]) => (
          <button key={id} onClick={() => setFiltro(id)}
            style={{padding:"7px 14px",borderRadius:10,border:"1.5px solid",fontFamily:"var(--font)",fontSize:13,fontWeight:600,cursor:"pointer",
              background: filtro===id?"var(--primary)":"var(--card)",
              color: filtro===id?"#fff":"var(--text-2)",
              borderColor: filtro===id?"var(--primary)":"var(--border)"}}>
            {lbl}
          </button>
        ))}
        <button onClick={carica}
          style={{padding:"7px 14px",borderRadius:10,border:"1.5px solid var(--border)",background:"var(--card)",fontFamily:"var(--font)",fontSize:13,cursor:"pointer"}}>
          🔄
        </button>
        <button onClick={() => window.open(withToken(`${API}/magazzino-bar/report-giacenze`), "_blank")}
          title="Report settimanale giacenze: stock e scadenze"
          style={{padding:"7px 14px",borderRadius:10,border:"1.5px solid var(--primary)",background:"var(--primary)",color:"#fff",fontFamily:"var(--font)",fontSize:13,fontWeight:600,cursor:"pointer"}}>
          📄 Report settimanale
        </button>
      </div>

      {/* Tabella */}
      {loading ? (
        <div style={{textAlign:"center",padding:"40px 0",color:"var(--text-3)"}}>Caricamento…</div>
      ) : (
       <>
        <div style={{display:"flex",flexWrap:"wrap",gap:"6px 16px",fontSize:12,color:"var(--text-2)",background:"var(--bg)",borderRadius:10,padding:"9px 12px",marginBottom:10}}>
          <span><b style={{color:"var(--text)"}}>Stock</b>: quante ne hai ora in magazzino</span>
          <span><b style={{color:"var(--text)"}}>Soglia min.</b>: sotto questo numero scatta il riordino (sotto scorta)</span>
          <span><b style={{color:"var(--text)"}}>Qt. riordino</b>: quante ordinarne quando riordini</span>
        </div>
        <div>
          {filtrati.map(p => (
            <RowProdotto key={p.id} prod={p} onSave={onSave}/>
          ))}
          {filtrati.length === 0 && (
            <div style={{textAlign:"center",padding:"40px",color:"var(--text-3)",background:"var(--card)",borderRadius:14}}>Nessun prodotto trovato</div>
          )}
        </div>
       </>
      )}
    </div>
  );
}

export default TabProdotti;
