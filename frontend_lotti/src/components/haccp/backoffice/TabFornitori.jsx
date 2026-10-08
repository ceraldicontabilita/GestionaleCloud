/**
 * TabFornitori (qualifica e visibilità in magazzino) — estratto da BackofficeView.jsx (refactor 25/07/2026).
 * Markup e logica identici: cambia solo il file che li contiene.
 */
import { useState, useEffect, useCallback } from "react";
import { conferma } from "../../../utils/conferma";
import axios from "axios";
import { toast } from "./toastBackoffice";

const API = process.env.REACT_APP_LOTTI_BACKEND_URL + "/api";

// ══════════════════════════════════════════════════════════════════
// 2. FORNITORI — qualifica / escludi per magazzino
// ══════════════════════════════════════════════════════════════════

const BADGE_STATO = {
  qualificato: { label:"✅ Qualificato", bg:"var(--success-soft)", color:"var(--success-text)" },
  escluso:     { label:"🚫 Escluso",     bg:"var(--danger-soft)",  color:"var(--danger-text)"  },
  in_attesa:   { label:"⏳ In attesa",   bg:"var(--warning-soft)", color:"var(--warning-text)" },
};

function RowFornitore({ forn, onUpdate }) {
  const [saving, setSaving] = useState(false);
  const [mon, setMon] = useState(!!forn.monitora_sconti);
  const [savingMon, setSavingMon] = useState(false);
  const stato = forn.stato_qualifica || "in_attesa";

  const toggleSconti = async () => {
    setSavingMon(true);
    try {
      const nuovo = !mon;
      await axios.post(`${API}/fornitori/monitora-sconti?nome=${encodeURIComponent(forn.nome || "")}&monitora=${nuovo}`);
      setMon(nuovo);
      toast(nuovo ? `💰 ${forn.nome}: sconti monitorati` : `${forn.nome}: sconti esclusi dalla sezione`);
    } catch { toast("Errore aggiornamento sconti", "err"); }
    finally { setSavingMon(false); }
  };
  const badge = BADGE_STATO[stato] || BADGE_STATO.in_attesa;

  const cambia = async (nuovoStato) => {
    setSaving(true);
    try {
      const endpoint = nuovoStato === "qualificato" ? "approva" : "escludi";
      await axios.post(`${API}/fornitori/${endpoint}`, { pive: [forn.partita_iva] });
      onUpdate(forn.partita_iva, nuovoStato);
      toast(nuovoStato === "qualificato" ? `✅ ${forn.nome} qualificato` : `🚫 ${forn.nome} escluso`);
    } catch { toast("Errore aggiornamento", "err"); }
    finally { setSaving(false); }
  };

  return (
    <div style={{background:"var(--card)", border:"1px solid var(--border)", borderRadius:14,
                 padding:"12px 14px", marginBottom:8, boxShadow:"var(--shadow-list)"}}>
      <div style={{display:"flex", alignItems:"flex-start", justifyContent:"space-between", gap:10}}>
        <div style={{minWidth:0, flex:1}}>
          <div style={{fontWeight:700,fontSize:14,color:"var(--text)",overflow:"hidden",textOverflow:"ellipsis"}}>{forn.nome || forn.denominazione || "—"}</div>
          <div style={{fontSize:11,color:"var(--text-3)",marginTop:2}}>
            P.IVA: {forn.partita_iva || "—"} {forn.citta && `· ${forn.citta}`}
          </div>
          {forn.email && <div style={{fontSize:11,color:"var(--info)"}}>📧 {forn.email}</div>}
          <div style={{fontSize:11,color:"var(--text-2)",marginTop:2}}>
            {forn.n_fatture || 0} fatture{forn.ultima_fattura && ` · ultima ${forn.ultima_fattura}`}
          </div>
        </div>
        <span style={{padding:"3px 10px",borderRadius:99,fontSize:11,fontWeight:700,background:badge.bg,color:badge.color,flexShrink:0,whiteSpace:"nowrap"}}>
          {badge.label}
        </span>
      </div>
      <div style={{display:"flex",gap:6,marginTop:10,flexWrap:"wrap"}}>
        {stato !== "qualificato" && (
          <button onClick={() => cambia("qualificato")} disabled={saving}
            style={{padding:"7px 12px",border:"none",borderRadius:8,background:"var(--success)",color:"#fff",fontWeight:700,fontSize:12,cursor:"pointer",fontFamily:"var(--font)"}}>
            ✅ Qualifica
          </button>
        )}
        {stato !== "escluso" && (
          <button onClick={() => cambia("escluso")} disabled={saving}
            style={{padding:"7px 12px",border:"none",borderRadius:8,background:"var(--danger)",color:"#fff",fontWeight:700,fontSize:12,cursor:"pointer",fontFamily:"var(--font)"}}>
            🚫 Escludi
          </button>
        )}
        <button onClick={toggleSconti} disabled={savingMon} title="Mostra questo fornitore nella sezione Sconti"
          style={{padding:"7px 12px",border:"1px solid var(--border)",borderRadius:8,background: mon ? "var(--warning)" : "transparent",color: mon ? "#fff" : "var(--text-2)",fontWeight:700,fontSize:12,cursor:"pointer",fontFamily:"var(--font)"}}>
          {mon ? "💰 Sconti ON" : "💰 Sconti OFF"}
        </button>
      </div>
    </div>
  );
}

function TabFornitori() {
  const [fornitori, setFornitori] = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [search,    setSearch]    = useState("");
  const [filtro,    setFiltro]    = useState("tutti");

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const [rAll, rEscl, rMon] = await Promise.all([
        axios.get(`${API}/fornitori?limit=500`),
        axios.get(`${API}/fornitori/esclusi`).catch(() => ({ data: [] })),
        axios.get(`${API}/fornitori/sconti-monitorati`).catch(() => ({ data: [] })),
      ]);
      const esclusi = new Set((rEscl.data || []).map(f => f.partita_iva));
      const monNomi = new Set((rMon.data || []).map(f => (f.nome || "").trim().toLowerCase()));
      const tutti = (rAll.data || []).map(f => ({
        ...f,
        stato_qualifica: esclusi.has(f.partita_iva) ? "escluso" : "qualificato",
        monitora_sconti: monNomi.has((f.nome || "").trim().toLowerCase()),
      }));
      setFornitori(tutti);
    } catch { toast("Errore caricamento fornitori", "err"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  const onUpdate = (piva, nuovoStato) => {
    setFornitori(f => f.map(x => x.partita_iva === piva ? {...x, stato_qualifica: nuovoStato} : x));
  };

  const filtrati = fornitori
    .filter(f => {
      const nome = (f.nome || f.denominazione || "").toLowerCase();
      if (search && !nome.includes(search.toLowerCase()) && !(f.partita_iva||"").includes(search)) return false;
      if (filtro === "qualificati") return f.stato_qualifica === "qualificato";
      if (filtro === "esclusi")     return f.stato_qualifica === "escluso";
      if (filtro === "attesa")      return f.stato_qualifica === "in_attesa";
      return true;
    })
    .sort((a, b) => (a.nome || "").localeCompare(b.nome || "", "it"));

  const nQual  = fornitori.filter(f => f.stato_qualifica === "qualificato").length;
  const nEscl  = fornitori.filter(f => f.stato_qualifica === "escluso").length;
  const nAtt   = fornitori.filter(f => f.stato_qualifica === "in_attesa").length;

  return (
    <div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:12,marginBottom:20}}>
        {[["Qualificati", nQual,"var(--success)"],["Esclusi",nEscl,"var(--danger)"],["In attesa",nAtt,"var(--warning)"]].map(([lbl,val,col]) => (
          <div key={lbl} style={{background:"var(--card)",borderRadius:14,padding:"14px 16px",boxShadow:"var(--shadow-list)",borderLeft:`4px solid ${col}`}}>
            <div style={{fontSize:22,fontWeight:800,color:col}}>{val}</div>
            <div style={{fontSize:12,color:"var(--text-2)",marginTop:2}}>{lbl}</div>
          </div>
        ))}
      </div>

      <div style={{display:"flex",gap:8,marginBottom:14,flexWrap:"wrap",alignItems:"center"}}>
        <input value={search} onChange={e=>setSearch(e.target.value)}
          placeholder="🔍 Cerca fornitore o P.IVA…"
          style={{padding:"8px 14px",border:"1.5px solid var(--border)",borderRadius:10,fontSize:14,fontFamily:"var(--font)",flex:1,minWidth:200}}/>
        {[["tutti","Tutti"],["qualificati","✅ Qualificati"],["esclusi","🚫 Esclusi"],["attesa","⏳ In attesa"]].map(([id,lbl]) => (
          <button key={id} onClick={() => setFiltro(id)}
            style={{padding:"7px 14px",borderRadius:10,border:"1.5px solid",fontFamily:"var(--font)",fontSize:13,fontWeight:600,cursor:"pointer",
              background:filtro===id?"var(--primary)":"var(--card)",
              color:filtro===id?"#fff":"var(--text-2)",
              borderColor:filtro===id?"var(--primary)":"var(--border)"}}>
            {lbl}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={{textAlign:"center",padding:"40px 0",color:"var(--text-3)"}}>Caricamento…</div>
      ) : (
        <div>
          {filtrati.map(f => (
            <RowFornitore key={f.partita_iva || f.id} forn={f} onUpdate={onUpdate}/>
          ))}
          {filtrati.length === 0 && (
            <div style={{textAlign:"center",padding:"40px",color:"var(--text-3)",background:"var(--card)",borderRadius:14}}>Nessun fornitore trovato</div>
          )}
        </div>
      )}
    </div>
  );
}

export default TabFornitori;
