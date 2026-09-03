/**
 * OrdiniView — Pagina Ordini NATIVA (ex iframe /ordini-app.html, ora integrata).
 * Collegata al sistema centrale: axios (token JWT automatico via interceptor),
 * design system salvia, flusso bozza→confermato→inviato su ordini_fornitori.
 * Quattro schede: Catalogo · Carrello · Giacenze · Da inviare.
 */
import { useState, useEffect, useMemo, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { API, withToken } from "../../utils/constants";
import { norm } from "../../utils/textNormalize";
import { getOperatoreNome } from "../../auth";
import { Search, ShoppingCart, Package, Send, Plus, Check, X, Minus, AlertTriangle, Scale } from "lucide-react";
// UN solo confronto prezzi in tutta l'app (prima Ordini usava un componente
// diverso dalla pagina «Confronto prezzi» del menu → due schermate per la
// stessa decisione d'acquisto, con numeri potenzialmente diversi).
import ConfrontoProdottoView from "./ConfrontoProdottoView";
import { useConferma } from "./shared/useConferma";

const C = { bg:"#faf7f0", card:"#fffefb", line:"#e6e0d4", ink:"#2a3329", muted:"#6b7669",
  brand:"#5b7a6b", green:"#3d8168", red:"#d35f4e", amber:"#c4894a", soft:"#e8efe9" };

const SECTORS = ["Tutti","Bar","Pasticceria","Cucina","Carta"];
function secOf(p){
  const c=(p.categoria||"").toUpperCase(), n=(p.nome||"").toUpperCase();
  if(["ACQUA","AMARI","BIRRE","LIQUORI","SUCCHI","VINO","SODATI"].some(x=>c.includes(x)||n.includes(x)))return"Bar";
  if(["FARINA","CIOCCOLATO","CREMA","UOVA","ZUCCHERO","LIEVITO"].some(x=>c.includes(x)||n.includes(x)))return"Pasticceria";
  if(["PASTA","SALE","CONSERVE","LATTICINI","VERDURE"].some(x=>c.includes(x)||n.includes(x)))return"Cucina";
  if(["CARTA","BICCHIERI","TOVAGLIOLI","POSATE"].some(x=>c.includes(x)||n.includes(x)))return"Carta";
  return "Bar";
}

// Carrello condiviso coi cataloghi fornitori (CatalogoFornitoreView/CatalogoGenericoView
// scrivono qui con "+ Aggiungi all'ordine"). BUG STORICO corretto il 03/07/2026: il
// consumatore originale (ordini-app.html) era stato eliminato e NESSUNO leggeva più
// questa chiave — i prodotti aggiunti dai cataloghi finivano in un carrello fantasma.
const CART_LS_KEY = "ordini_smart_carrello";
// Semplificazione: 3 schede in basso (Compra / Carrello / Da inviare). "Compra"
// raggruppa Riordini/Catalogo/Confronto/Giacenze come sotto-voci (2 livelli),
// così la barra non ha più 6 voci. Le viste restano identiche.
const COMPRA_TABS = ["riordini", "catalogo", "confronto", "giacenze"];
// Accetta la virgola italiana negli input numerici: "1,5" -> 1.5 (gli input
// type=number scartavano la virgola, dando NaN e valori non salvati).
const numIt = (v) => parseFloat(String(v ?? "").replace(",", "."));
function leggiCarrelloCataloghi() {
  try { return JSON.parse(localStorage.getItem(CART_LS_KEY) || "[]"); } catch { return []; }
}
function rimuoviDaCarrelloCataloghi(idOriginale) {
  try {
    const items = leggiCarrelloCataloghi().filter(x => x.id !== idOriginale);
    localStorage.setItem(CART_LS_KEY, JSON.stringify(items));
    axios.put(`${API}/ordini-fornitori/carrello-sospesi`, { righe: items }).catch(() => {});
  } catch { /* no-op */ }
}
function aggiornaQuantitaCarrelloCataloghi(idOriginale, quantita) {
  try {
    const items = leggiCarrelloCataloghi().map(x => x.id === idOriginale ? { ...x, quantita } : x);
    localStorage.setItem(CART_LS_KEY, JSON.stringify(items));
    axios.put(`${API}/ordini-fornitori/carrello-sospesi`, { righe: items }).catch(() => {});
  } catch { /* no-op */ }
}
function svuotaCarrelloCataloghi() {
  try { localStorage.removeItem(CART_LS_KEY); } catch { /* no-op */ }
  axios.put(`${API}/ordini-fornitori/carrello-sospesi`, { righe: [] }).catch(() => {});
  try { window.dispatchEvent(new Event("ordini_smart_cart_update")); } catch { /* no-op */ }
}

export default function OrdiniView({ initialTab = "riordini" }) {
  const [tab, setTab] = useState(initialTab);          // riordini | catalogo | confronto | carrello | giacenze | invio
  const [richieste, setRichieste] = useState([]);      // lavagna magazzino (stato=aperta)
  const [prodotti, setProdotti] = useState([]);
  const [giacBy, setGiacBy] = useState({});
  const [cart, setCart] = useState({});
  const [q, setQ] = useState("");
  const [sector, setSector] = useState("Tutti");
  const [cat, setCat] = useState("Tutti");
  const [forn, setForn] = useState("Tutti");
  const [loading, setLoading] = useState(true);
  // "Cervello da magazziniere": festività imminenti (consegne a rischio) e
  // coerenza incassi↔ordini dai corrispettivi. Endpoint già esistenti nel
  // backend ma prima visibili solo nella pagina Corrispettivi.
  const [festivita, setFestivita] = useState([]);
  const [correlazione, setCorrelazione] = useState(null);
  const [fontiCataloghi, setFontiCataloghi] = useState([]);

  const carica = useCallback(async () => {
    setLoading(true);
    const [rp, rg, rr] = await Promise.allSettled([
      axios.get(`${API}/prodotti-master?limit=2000&solo_con_prezzo=false`),
      axios.get(`${API}/ordini-app/giacenze`),
      axios.get(`${API}/magazzino-bar/richieste?stato=aperta`),
    ]);
    if (rr.status === "fulfilled") setRichieste(rr.value.data?.richieste || []);
    if (rp.status === "fulfilled") {
      const items = rp.value.data?.items || [];
      setProdotti(items.map((x,i)=>{
        const f60 = x.fornitori_60gg || [];
        const best = f60[0] || null;
        return {
          id: x.id||i+1, nome: x.nome_canonico||x.nome||"Prodotto",
          conf: x.unita_misura||x.confezione||"CT", categoria: x.categoria||"",
          // miglior fornitore: il backend garantisce sempre un prezzo (recente o
          // ultimo noto). best = comparatore (recenti in cima, poi più economico).
          // SOLO prezzo da fattura (comparatore). Niente fallback su listino/ultimo:
          // un prezzo mostrato dev'essere un prezzo davvero pagato.
          fornitore: (best&&best.fornitore) || x.miglior_fornitore_60gg || "",
          prezzo: Number((best&&best.prezzo) ?? x.miglior_prezzo_60gg ?? 0)||0,
          fornitori60: f60,           // elenco comparatore per la scelta manuale
          dataPrezzo: (best&&best.data) || x.miglior_prezzo_data || "",
          prezzoRecente: (best ? best.recente : !!x.prezzo_recente),
          prezzoGiorniFa: (best ? best.giorni_fa : x.prezzo_giorni_fa),
        };
      }));
    }
    if (rg.status === "fulfilled") {
      // mappa costruita QUI con la stessa norm() usata nei lookup: il by_key
      // del backend usa un normalizzatore diverso (parole ordinate, numeri
      // rimossi) e non matchava mai → giacenze sempre lette 0
      const mappa = {};
      (rg.value.data?.giacenze || []).forEach(g => {
        const k = norm(g.nome); if (k && !mappa[k]) mappa[k] = g;
      });
      setGiacBy(mappa);
    }
    setLoading(false);
  }, []);
  useEffect(() => { carica(); }, [carica]);

  useEffect(() => {
    // non bloccanti: se i corrispettivi non sono caricati, il banner non appare
    axios.get(`${API}/corrispettivi/festivita-imminenti?giorni=12`)
      .then(r => setFestivita(r.data?.festivita || [])).catch(() => {});
    axios.get(`${API}/corrispettivi/correlazione-ordini`)
      .then(r => setCorrelazione(r.data)).catch(() => {});
    // fonti web sincronizzate (es. Sunset Cash) → chip catalogo anche qui
    axios.get(`${API}/fonti-catalogo`)
      .then(r => setFontiCataloghi((Array.isArray(r.data) ? r.data : []).filter(f => (f.prodotti_trovati || 0) > 0)))
      .catch(() => {});
  }, []);

  // Travaso dal carrello dei cataloghi fornitori: ogni prodotto aggiunto da
  // Saima/MePA/Bindi/Tre Marie/... compare qui nel Carrello (id prefissato
  // "cat_" per non collidere coi prodotti del catalogo master).
  const mergeCarrelloCataloghi = useCallback(() => {
    const esterni = leggiCarrelloCataloghi();
    if (!esterni.length) return;
    setCart(c => {
      const nc = { ...c };
      esterni.forEach(e => {
        const id = `cat_${e.id}`;
        if (!nc[id]) nc[id] = {
          id, idCatalogo: e.id, nome: e.nome, conf: e.unita_misura || "pz",
          fornitore: e.fornitore || "DA ASSEGNARE", prezzo: Number(e.prezzo) || 0,
          fornitori60: [], qty: Number(e.quantita) || 1, stock_iniziale: 0, soglia: 0,
          richiesto_da: getOperatoreNome() || "Catalogo fornitori", da_catalogo: true,
        };
      });
      return nc;
    });
  }, []);
  useEffect(() => {
    // Il carrello cataloghi e' condiviso dal backend: se l'ordine e' stato
    // iniziato su un tablet, compare anche sull'altro senza dover ricominciare.
    axios.get(`${API}/ordini-fornitori/carrello-sospesi`).then(response => {
      const remoti = response.data?.righe || [];
      const locali = leggiCarrelloCataloghi();
      const uniti = Array.from(new Map([...remoti, ...locali].map(item => [item.id, item])).values());
      localStorage.setItem(CART_LS_KEY, JSON.stringify(uniti));
      mergeCarrelloCataloghi();
    }).catch(() => {});
  }, [mergeCarrelloCataloghi]);
  useEffect(() => {
    mergeCarrelloCataloghi();
    window.addEventListener("ordini_smart_cart_update", mergeCarrelloCataloghi);
    window.addEventListener("storage", mergeCarrelloCataloghi);
    return () => {
      window.removeEventListener("ordini_smart_cart_update", mergeCarrelloCataloghi);
      window.removeEventListener("storage", mergeCarrelloCataloghi);
    };
  }, [mergeCarrelloCataloghi]);

  const stockOf = (p) => { const g = giacBy[norm(p.nome)]||{}; return Number(g.stock ?? p.stock ?? 0)||0; };
  const sogliaOf = (p) => { const g = giacBy[norm(p.nome)]||{}; return Number(g.soglia ?? 0)||0; };

  const categorie = useMemo(() => ["Tutti", ...Array.from(new Set(
    prodotti.filter(p=>sector==="Tutti"||secOf(p)===sector).map(p=>p.categoria).filter(Boolean))).slice(0,60)], [prodotti, sector]);
  const fornitori = useMemo(() => {
    const cnt={}; prodotti.forEach(p=>{const f=p.fornitore; if(f&&f!=="Auto")cnt[f]=(cnt[f]||0)+1;});
    return ["Tutti", ...Object.keys(cnt).sort((a,b)=>cnt[b]-cnt[a]).slice(0,10)];
  }, [prodotti]);

  const lista = useMemo(() => {
    const qs = norm(q).split(" ").filter(w=>w.length>=2);
    return prodotti.filter(p =>
      (sector==="Tutti"||secOf(p)===sector) && (cat==="Tutti"||p.categoria===cat) &&
      (forn==="Tutti"||p.fornitore===forn) &&
      (!qs.length || qs.every(t=>norm(p.nome+" "+p.categoria).includes(t)))
    ).slice(0,120);
  }, [prodotti, q, sector, cat, forn]);

  const inc = (p, d=1) => setCart(c => {
    const cur = c[p.id]?.qty || 0; const next = Math.max(0, cur+d);
    const nc = {...c};
    if (next<=0) { if (nc[p.id]?.da_catalogo) rimuoviDaCarrelloCataloghi(nc[p.id].idCatalogo); delete nc[p.id]; }
    else {
      const precedente = nc[p.id];
      nc[p.id] = { id:p.id, nome:p.nome, conf:p.conf, fornitore:p.fornitore, prezzo:p.prezzo, fornitori60:p.fornitori60||[], prezzoRecente:p.prezzoRecente, prezzoGiorniFa:p.prezzoGiorniFa, qty:next, stock_iniziale:stockOf(p), soglia:sogliaOf(p), richiesto_da:(c[p.id]&&c[p.id].richiesto_da)||getOperatoreNome()||"Ordini app", ...(precedente?.da_catalogo ? { da_catalogo:true, idCatalogo:precedente.idCatalogo } : {}) };
      if (precedente?.da_catalogo) aggiornaQuantitaCarrelloCataloghi(precedente.idCatalogo, next);
    }
    return nc;
  });
  const toggle = (p) => setCart(c => { const nc={...c}; if(nc[p.id])delete nc[p.id]; else nc[p.id]={id:p.id,nome:p.nome,conf:p.conf,fornitore:p.fornitore,prezzo:p.prezzo,fornitori60:p.fornitori60||[],prezzoRecente:p.prezzoRecente,prezzoGiorniFa:p.prezzoGiorniFa,qty:1,stock_iniziale:stockOf(p),soglia:sogliaOf(p),richiesto_da:getOperatoreNome()||"Ordini app"}; return nc; });
  const markLow = (p, qta) => { const n = qta || Math.max(1,Math.ceil((sogliaOf(p)||1)-stockOf(p))); inc(p, n); toast.success(`Aggiunto riordino: ${n} pz`); };

  const setFornitore = (id, fornitore, prezzo) => setCart(c => {
    const nc = {...c};
    if (nc[id]) nc[id] = { ...nc[id], fornitore, prezzo: Number(prezzo)||0 };
    return nc;
  });

  const cartRows = Object.values(cart);
  const cartTot = cartRows.reduce((s,r)=>s+(r.prezzo||0)*r.qty, 0);

  // ── RIORDINI: i tre segnali in una lista sola (richiesta Enzo: pochi tap) ──
  // 1) prodotti sotto soglia di giacenza; 2) richieste lavagna dei dipendenti.
  const sottoSoglia = useMemo(() => prodotti.filter(p => {
    const sg = sogliaOf(p); return sg > 0 && stockOf(p) <= sg;
  }), [prodotti, giacBy]); // eslint-disable-line react-hooks/exhaustive-deps

  const trovaProdotto = (nome) => {
    const n = norm(nome);
    return prodotti.find(p => norm(p.nome) === n)
        || prodotti.find(p => norm(p.nome).includes(n) || n.includes(norm(p.nome)));
  };
  const addRichiesta = (r) => {
    const p = trovaProdotto(r.prodotto_nome || r.nome || "");
    if (!p) { toast.error(`"${r.prodotto_nome}" non trovato nel catalogo: aggiungilo dal Catalogo`); return; }
    inc(p, Number(r.quantita) || 1);
    if (r.richiesto_da) setCart(c => c[p.id] ? { ...c, [p.id]: { ...c[p.id], richiesto_da: `${r.richiesto_da} (lavagna)` } } : c);
    toast.success(`${p.nome}: +${r.quantita || 1} nel carrello`);
  };
  const addTuttiSotto = () => {
    let n = 0;
    sottoSoglia.forEach(p => { if (!cart[p.id]) { const need = Math.max(1, Math.ceil((sogliaOf(p)||1) - stockOf(p))); inc(p, need); n++; } });
    toast.success(n ? `${n} prodotti sotto soglia aggiunti al carrello` : "Già tutti nel carrello");
  };
  const nRiordini = sottoSoglia.length + richieste.length;

  const creaBozze = async () => {
    const rows = cartRows.filter(r=>r.qty>0);
    if (!rows.length) { toast("Carrello vuoto"); return; }
    const by = {}; rows.forEach(r=>{ const f=r.fornitore||"DA ASSEGNARE"; (by[f]=by[f]||[]).push(r); });
    let ok=0;
    for (const f of Object.keys(by)) {
      const doc = { source:"ordini_app", reparto:"", operatore:getOperatoreNome()||"Ordini app",
        note_operatore:"Bozza da pagina Ordini — "+new Date().toLocaleDateString("it-IT"),
        prodotti: by[f].map(r=>({prodotto_id:String(r.id),nome:r.nome,fornitore:f,quantita:r.qty,unita:r.conf||"pz",prezzo_ultimo:r.prezzo||0,note:"",richiesto_da:r.richiesto_da||getOperatoreNome()||"Ordini app"})),
        ricette_da_produrre:[] };
      try { await axios.post(`${API}/ordini-fornitori`, doc); ok++; } catch { /* continua */ }
    }
    setCart({}); svuotaCarrelloCataloghi();
    toast.success(`${ok} bozze create: vai su "Da inviare" per confermare`);
    setTab("invio");
  };

  return (
    <div style={{ background:C.bg, minHeight:"100dvh", fontFamily:"'Plus Jakarta Sans',system-ui,sans-serif", color:C.ink }}>
      {/* Sotto-voci del gruppo "Compra" (2° livello): appaiono solo dentro Compra */}
      {COMPRA_TABS.includes(tab) && (
        <div style={{ display:"flex", gap:6, overflowX:"auto", padding:"8px 10px", background:"#fff", borderBottom:`1px solid ${C.line}` }}>
          {[["riordini",`Riordini${nRiordini?" ("+nRiordini+")":""}`],["catalogo","Catalogo"],["confronto","Confronto"],["giacenze","Giacenze"]].map(([id,lbl])=>(
            <button key={id} onClick={()=>setTab(id)} style={{ flexShrink:0, border:`1px solid ${tab===id?C.brand:C.line}`, background:tab===id?C.brand:"#fff", color:tab===id?"#fff":C.muted, borderRadius:999, padding:"6px 14px", fontWeight:800, fontSize:13, cursor:"pointer" }}>{lbl}</button>
          ))}
        </div>
      )}
      {/* ricerca */}
      {tab==="catalogo" && (
        <div style={{ background:"#fff", borderBottom:`1px solid ${C.line}`, padding:"10px 12px" }}>
          <div style={{ display:"flex", alignItems:"center", gap:8, border:`2px solid ${C.line}`, borderRadius:14, padding:"10px 12px" }}>
            <Search size={18} color={C.muted}/>
            <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Cerca articolo… (es. margarina)"
              style={{ border:"none", outline:"none", width:"100%", fontWeight:700, fontSize:16, background:"transparent" }}/>
          </div>
          <Filtro label="Settore" valori={SECTORS} sel={sector} onSel={v=>{setSector(v);setCat("Tutti");}}/>
          <Filtro label="Categoria" valori={categorie} sel={cat} onSel={setCat}/>
          <Filtro label="Fornitore" valori={fornitori} sel={forn} onSel={setForn}/>
          {/* qui ci sono solo i prodotti GIÀ comprati (fatture); i cataloghi
              completi dei fornitori vivono in #prodotti — stesso carrello.
              UN BOTTONE PER CATALOGO (richiesta Enzo 04/07/2026: "sul pulsante
              catalogo non escono Acquaviva, Saima e così via"). */}
          <div style={{ marginTop:8 }}>
            <div style={{ fontSize:11, fontWeight:800, color:C.muted, textTransform:"uppercase", letterSpacing:.5, marginBottom:6 }}>
              Cataloghi completi dei fornitori — stesso carrello
            </div>
            <div style={{ display:"flex", gap:6, flexWrap:"wrap" }}>
              {[
                ["acquaviva","Acquaviva"], ["saima","SAIMA"], ["mepa","MePA"],
                ["pasticcere","Il Pasticcere"], ["tremarie","Tre Marie"],
                ["alfa","Alfa (s. glutine)"], ["sammontana","Sammontana"], ["bindi","Bindi"],
                ...fontiCataloghi.map(f => [f.fornitore_key, f.nome]),
              ].map(([k, label]) => (
                <button key={k} onClick={()=>{ window.location.hash = `prodotti/${k}`; }}
                  style={{ border:`1px solid ${C.line}`, background:"#fff", color:C.brand, borderRadius:99, padding:"7px 13px", fontWeight:800, fontSize:12.5, cursor:"pointer" }}>
                  {label} →
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      <div style={{ padding:"14px 12px 90px" }}>
        {loading && <div style={{ textAlign:"center", color:C.muted, padding:40 }}>Carico catalogo…</div>}

        {!loading && tab==="catalogo" && (<>
          <div style={{ fontSize:13, fontWeight:800, color:C.muted, letterSpacing:1, margin:"4px 4px 12px", textTransform:"uppercase" }}>{lista.length} articoli</div>
          {lista.map(p => {
            const inC=!!cart[p.id], qty=cart[p.id]?.qty||0, st=stockOf(p), sg=sogliaOf(p);
            return (
              <div key={p.id} style={{ background:C.card, border:`2px solid ${inC?C.brand:C.line}`, borderRadius:20, marginBottom:12, padding:14,
                boxShadow:inC?`0 0 0 3px rgba(91,122,107,.18)`:"0 2px 12px rgba(63,90,78,.06)" }}>
                <div style={{ textAlign:"center", fontWeight:800, fontSize:17, lineHeight:1.25 }}>{p.nome}</div>
                <div style={{ display:"flex", gap:7, justifyContent:"center", flexWrap:"wrap", marginTop:6 }}>
                  <Badge>{p.conf}</Badge>
                  <Badge tone={st<=0?"zero":"giac"}>Giac. {st}</Badge>
                  {sg>0 && <Badge>Min. {sg}</Badge>}
                  <Badge>{p.fornitore}</Badge>
                  {p.prezzo>0
                    ? <Badge tone={p.prezzoRecente?"giac":"warn"}>€ {p.prezzo.toFixed(2)} / {p.conf}{p.prezzoRecente?"":" ·vecchio"}</Badge>
                    : <Badge tone="zero">prezzo n/d</Badge>}
                </div>
                {p.fornitori60 && p.fornitori60.length>1 && (
                  <div style={{ textAlign:"center", fontSize:11, color:C.muted, marginTop:4 }}>
                    {p.fornitori60.length} fornitori — confronta e scegli nel carrello
                  </div>
                )}
                <EditGiacenzaSoglia giac={giacBy[norm(p.nome)]} onSalvato={carica} />
                <div style={{ display:"flex", justifyContent:"center", alignItems:"center", gap:18, marginTop:14 }}>
                  <button onClick={()=>toggle(p)} style={ico(inC)}>{inC?<Check size={22}/>:<Plus size={22}/>}</button>
                  <div style={{ display:"flex", alignItems:"center", gap:16, background:C.soft, borderRadius:16, padding:"8px 14px" }}>
                    <button onClick={()=>inc(p,-1)} style={qtybtn}><Minus size={20}/></button>
                    <span style={{ minWidth:36, textAlign:"center", fontSize:22, fontWeight:800 }}>{qty}</span>
                    <button onClick={()=>inc(p,1)} style={qtybtn}><Plus size={20}/></button>
                  </div>
                  <button onClick={()=>markLow(p)} title="Riordino fino a soglia" style={ico(false)}><AlertTriangle size={20}/></button>
                </div>
              </div>
            );
          })}
        </>)}

        {tab==="riordini" && (festivita.length > 0 || correlazione) && (
          <div style={{ marginBottom:14 }}>
            {festivita.map((f,i)=>(
              <div key={i} style={{ background:"#fdf0d8", border:"1px solid #ecd9ac", borderRadius:14, padding:"10px 14px", marginBottom:8 }}>
                <div style={{ fontWeight:800, fontSize:13, color:"#8a5a12", display:"flex", alignItems:"center", gap:6 }}>
                  <AlertTriangle size={15}/> {f.nome} — {f.giorno_settimana} {new Date(f.data).toLocaleDateString("it-IT")} (tra {f.giorni_mancanti} gg{f.ponte?` + ${f.ponte.tipo}`:""})
                </div>
                <div style={{ fontSize:12.5, color:"#7a5a1e", marginTop:3 }}>
                  Le consegne di quei giorni potrebbero saltare: <b>anticipa l'ordine o aumenta le quantità</b>. Il riordino automatico raddoppia già le proposte in questi giorni.
                </div>
              </div>
            ))}
            {correlazione?.messaggio && (
              <div style={{ background:C.soft, border:`1px solid ${C.line}`, borderRadius:14, padding:"10px 14px" }}>
                <div style={{ fontWeight:800, fontSize:13, color:C.brand }}>📊 Incassi ↔ ordini (corrispettivi)</div>
                <div style={{ fontSize:12.5, color:C.ink, marginTop:3 }}>{correlazione.messaggio}</div>
                {correlazione.periodo && (
                  <div style={{ fontSize:11.5, color:C.muted, marginTop:3 }}>
                    Questo periodo: incassato €{(correlazione.periodo.incasso||0).toFixed(0)} · ordinato €{(correlazione.periodo.spesa_ordini||0).toFixed(0)}
                    {correlazione.periodo.incidenza_pct != null ? ` · incidenza ${correlazione.periodo.incidenza_pct}%` : ""}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
        {tab==="riordini" && (
          <DaOrdinare sotto={sottoSoglia} richieste={richieste} cart={cart}
            stockOf={stockOf} sogliaOf={sogliaOf}
            giacByNome={(nome)=>giacBy[norm(nome)]}
            onAdd={markLow} onInc={inc} onAddAll={addTuttiSotto} onAddRichiesta={addRichiesta}
            onVaiCarrello={()=>setTab("carrello")} onVaiCatalogo={()=>setTab("catalogo")} loading={loading} />
        )}
        {tab==="confronto" && <ConfrontoProdottoView />}
        {tab==="giacenze" && <Giacenze giacBy={giacBy} onReload={carica} />}
        {tab==="carrello" && <Carrello rows={cartRows} tot={cartTot} inc={inc} prodotti={prodotti} onSetFornitore={setFornitore} onCrea={creaBozze}
          onRemove={(id)=>setCart(c=>{
            const n={...c};
            if (n[id]?.da_catalogo) rimuoviDaCarrelloCataloghi(n[id].idCatalogo);
            delete n[id]; return n;
          })} />}
        {tab==="invio" && <DaInviare />}
      </div>

      {/* barra inferiore */}
      <div style={{ position:"fixed", left:0, right:0, bottom:0, background:"#fff", borderTop:`1px solid ${C.line}`, display:"flex" }}>
        {[["compra",<Search size={20}/>,"Compra"],["carrello",<ShoppingCart size={20}/>,`Carrello${cartRows.length?" ("+cartRows.length+")":""}`],["invio",<Send size={20}/>,"Da inviare"]].map(([id,icon,lbl])=>{
          const attivo = id==="compra" ? COMPRA_TABS.includes(tab) : tab===id;
          const target = id==="compra" ? (COMPRA_TABS.includes(tab)?tab:"riordini") : id;
          return (
          <button key={id} onClick={()=>setTab(target)} style={{ flex:1, border:"none", background:"#fff", padding:"10px 4px", fontWeight:800, fontSize:11,
            color: attivo?C.brand:C.muted, display:"flex", flexDirection:"column", alignItems:"center", gap:3, cursor:"pointer" }}>
            {icon}{lbl}
          </button>);
        })}
      </div>
    </div>
  );
}

function Filtro({ label, valori, sel, onSel }) {
  return (
    <div style={{ display:"flex", gap:8, overflowX:"auto", alignItems:"center", marginTop:8 }}>
      <span style={{ flex:"0 0 auto", fontSize:11, fontWeight:800, color:C.muted, textTransform:"uppercase", letterSpacing:1, minWidth:70 }}>{label}</span>
      {valori.map(v=>(
        <button key={v} onClick={()=>onSel(v)} style={{ flex:"0 0 auto", height:34, padding:"0 14px", borderRadius:999, fontWeight:800, fontSize:13, cursor:"pointer", whiteSpace:"nowrap",
          border:`2px solid ${sel===v?C.brand:C.line}`, background: sel===v?C.brand:"#fff", color: sel===v?"#fff":C.muted }}>{v}</button>
      ))}
    </div>
  );
}
const Badge = ({ children, tone }) => (
  <span style={{ borderRadius:999, padding:"4px 10px", fontSize:12, fontWeight:800,
    background: tone==="zero"?"#fee2e2":tone==="giac"?"#e2f0e7":tone==="warn"?"#fdf0d8":"#f3ead8",
    color: tone==="zero"?"#b91c1c":tone==="giac"?C.green:tone==="warn"?"#b06d12":"#8a6f47" }}>{children}</span>
);
const ico = (on) => ({ width:48, height:48, border:"none", borderRadius:14, cursor:"pointer",
  background: on?C.brand:"#e8efe9", color: on?"#fff":C.brand, display:"grid", placeItems:"center" });
const qtybtn = { width:40, height:40, border:"none", borderRadius:12, background:C.brand, color:"#fff", cursor:"pointer", display:"grid", placeItems:"center" };

// ── Scheda RIORDINI: dal segnale all'ordine in pochi tap (richiesta Enzo) ──
// Riga sotto-soglia: la quantità si REGOLA PRIMA di aggiungere (richiesta
// Enzo 04/07/2026: "seleziono 3 e non posso aggiungerli" — prima l'unico
// modo era aggiungere il suggerito e poi correggere a colpi di −).
function RigaAggiungiQta({ suggerita, onAggiungi }) {
  const [qta, setQta] = useState(suggerita);
  const btn = { border:"none", background:C.brand, color:"#fff", borderRadius:10, padding:"6px 10px", fontWeight:800, fontSize:12, cursor:"pointer", whiteSpace:"nowrap" };
  return (
    <span style={{ display:"inline-flex", alignItems:"center", gap:6 }}>
      <button onClick={()=>setQta(q=>Math.max(1,q-1))} style={{ ...btn, background:"#fff", color:C.ink, border:`1.5px solid ${C.line}` }}><Minus size={13}/></button>
      <b style={{ minWidth:24, textAlign:"center", fontSize:14 }}>{qta}</b>
      <button onClick={()=>setQta(q=>q+1)} style={{ ...btn, background:"#fff", color:C.ink, border:`1.5px solid ${C.line}` }}><Plus size={13}/></button>
      <button onClick={()=>onAggiungi(qta)} style={btn}>+ Aggiungi</button>
    </span>
  );
}

function DaOrdinare({ sotto, richieste, cart, stockOf, sogliaOf, giacByNome, onAdd, onInc, onAddAll, onAddRichiesta, onVaiCarrello, onVaiCatalogo, loading }) {
  const nCart = Object.keys(cart).length;
  if (loading) return <div style={{ textAlign:"center", color:C.muted, padding:40 }}>Carico i segnali di riordino…</div>;
  if (!sotto.length && !richieste.length) return (
    <div style={{ textAlign:"center", color:C.muted, padding:40 }}>
      <Check size={34} style={{ color:C.green, marginBottom:8 }} />
      <div style={{ fontWeight:800, color:C.ink, marginBottom:4 }}>Niente da riordinare</div>
      <div style={{ fontSize:13, marginBottom:14 }}>Nessun prodotto sotto soglia e nessuna richiesta dei dipendenti.</div>
      <button onClick={onVaiCatalogo} style={{ border:`1px solid ${C.line}`, background:"#fff", color:C.brand, borderRadius:12, padding:"10px 18px", fontWeight:800, cursor:"pointer" }}>Apri il catalogo</button>
    </div>
  );
  const box = { background:"#fff", border:`1px solid ${C.line}`, borderRadius:14, marginBottom:14, overflow:"hidden" };
  const head = { display:"flex", alignItems:"center", justifyContent:"space-between", gap:8, padding:"10px 12px", borderBottom:`1px solid ${C.line}`, background:C.soft };
  const row = { display:"flex", alignItems:"center", gap:10, padding:"10px 12px", borderBottom:`1px solid ${C.line}` };
  const addBtn = { border:"none", background:C.brand, color:"#fff", borderRadius:10, padding:"8px 12px", fontWeight:800, fontSize:12, cursor:"pointer", whiteSpace:"nowrap" };
  return (
    <div>
      {nCart > 0 && (
        <button onClick={onVaiCarrello} style={{ width:"100%", marginBottom:12, border:"none", background:C.green, color:"#fff", borderRadius:12, padding:"12px", fontWeight:900, fontSize:14, cursor:"pointer" }}>
          Vai al carrello ({nCart}) e crea le bozze →
        </button>
      )}

      {sotto.length > 0 && (
        <div style={box}>
          <div style={head}>
            <b style={{ fontSize:13.5 }}>⚠ Sotto soglia di giacenza ({sotto.length})</b>
            <button onClick={onAddAll} style={addBtn}>+ Aggiungi tutti</button>
          </div>
          {sotto.map(p => {
            const st = stockOf(p), sg = sogliaOf(p), need = Math.max(1, Math.ceil((sg||1)-st));
            const inCart = !!cart[p.id];
            return (
              <div key={p.id} style={row}>
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ fontWeight:700, fontSize:13.5, color:C.ink, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{p.nome}</div>
                  <div style={{ fontSize:12, color:C.muted }}>Giacenza {st} · soglia {sg} · {p.fornitore || "fornitore da scegliere"}</div>
                </div>
                {inCart
                  ? <span style={{ display:"inline-flex", alignItems:"center", gap:6 }}>
                      <button onClick={()=>onInc(p,-1)} style={{ ...addBtn, background:"#fff", color:C.ink, border:`1.5px solid ${C.line}`, padding:"6px 10px" }}><Minus size={13}/></button>
                      <b style={{ minWidth:24, textAlign:"center", fontSize:14 }}>{cart[p.id]?.qty||0}</b>
                      <button onClick={()=>onInc(p,1)} style={{ ...addBtn, padding:"6px 10px" }}><Plus size={13}/></button>
                    </span>
                  : <RigaAggiungiQta suggerita={need} onAggiungi={(qta)=>onAdd(p, qta)} />}
              </div>
            );
          })}
        </div>
      )}

      {richieste.length > 0 && (
        <div style={box}>
          <div style={head}>
            <b style={{ fontSize:13.5 }}>📋 Richieste dei dipendenti — lavagna ({richieste.length})</b>
          </div>
          {richieste.map(r => {
            // Richiesta lavagna = trasferimento INTERNO (bar ← magazzino).
            // Se il magazzino ha stock, va solo consegnata dal tablet: comprare
            // sarebbe un doppione. Il carrello si propone solo se manca.
            const g = giacByNome(r.prodotto_nome);
            const stockMag = g ? Number(g.stock) || 0 : null;
            const disponibile = stockMag !== null && stockMag >= (Number(r.quantita) || 1);
            return (
              <div key={r.id} style={row}>
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ fontWeight:700, fontSize:13.5, color:C.ink, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{r.prodotto_nome}</div>
                  <div style={{ fontSize:12, color:C.muted }}>
                    {r.quantita} {r.unita_movimento === "collo" ? "cartoni" : "pz"} · chiesto da {r.richiesto_da || "?"}
                    {stockMag !== null && ` · magazzino: ${stockMag}`}
                  </div>
                </div>
                {disponibile
                  ? <span style={{ fontSize:12, fontWeight:800, color:C.green, whiteSpace:"nowrap" }}>in magazzino ✓ consegna dal tablet</span>
                  : <button onClick={()=>onAddRichiesta(r)} style={addBtn}>+ carrello</button>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// Modifica giacenza + soglia direttamente dalla card del catalogo (richiesta
// Enzo 03/07/2026): tocca "✎ giacenza/soglia", correggi, Salva — senza cambiare
// pagina. Solo per prodotti presenti nel magazzino bar (hanno un id).
function EditGiacenzaSoglia({ giac, onSalvato }) {
  const [open, setOpen] = useState(false);
  const [stock, setStock] = useState("");
  const [soglia, setSoglia] = useState("");
  const [saving, setSaving] = useState(false);
  if (!giac || !giac.id) return null;
  const salva = async () => {
    setSaving(true);
    try {
      const ops = [];
      if (stock !== "" && !isNaN(numIt(stock)))
        ops.push(axios.post(`${API}/magazzino-bar/prodotti/${giac.id}/rettifica`,
          { stock_contato: numIt(stock), operatore_nome: getOperatoreNome() || "Ordini app" }));
      if (soglia !== "" && !isNaN(numIt(soglia)))
        ops.push(axios.patch(`${API}/magazzino-bar/prodotti/${giac.id}/soglia`,
          { soglia_minima: numIt(soglia) }));
      if (!ops.length) { toast.error("Scrivi almeno un valore"); setSaving(false); return; }
      await Promise.all(ops);
      toast.success("Giacenza/soglia aggiornate");
      setOpen(false); setStock(""); setSoglia("");
      onSalvato && onSalvato();
    } catch { toast.error("Errore nel salvataggio"); }
    finally { setSaving(false); }
  };
  if (!open) return (
    <div style={{ textAlign:"center", marginTop:6 }}>
      <button onClick={()=>setOpen(true)} style={{ border:"none", background:"transparent", color:C.brand, fontWeight:800, fontSize:12, cursor:"pointer", textDecoration:"underline" }}>
        ✎ correggi giacenza / soglia
      </button>
    </div>
  );
  const inp = { flex:1, minWidth:0, padding:"8px 10px", borderRadius:10, border:`1.5px solid ${C.line}`, fontSize:15, fontWeight:700 };
  return (
    <div style={{ marginTop:8, background:C.soft, borderRadius:12, padding:10 }}>
      <div style={{ display:"flex", gap:8 }}>
        <input type="text" inputMode="decimal" placeholder={`Giac. (ora ${giac.stock})`} value={stock} onChange={e=>setStock(e.target.value)} style={inp} />
        <input type="text" inputMode="decimal" placeholder={`Soglia (ora ${giac.soglia||0})`} value={soglia} onChange={e=>setSoglia(e.target.value)} style={inp} />
      </div>
      <div style={{ display:"flex", gap:8, marginTop:8 }}>
        <button onClick={salva} disabled={saving} style={{ flex:1, border:"none", background:C.brand, color:"#fff", borderRadius:10, padding:"9px 0", fontWeight:800, cursor:"pointer" }}>{saving?"…":"Salva"}</button>
        <button onClick={()=>setOpen(false)} style={{ border:`1px solid ${C.line}`, background:"#fff", color:C.muted, borderRadius:10, padding:"9px 14px", fontWeight:800, cursor:"pointer" }}>Annulla</button>
      </div>
    </div>
  );
}

function Giacenze({ giacBy, onReload }) {
  const ks = Object.keys(giacBy);
  const [q, setQ] = useState("");
  const [draft, setDraft] = useState({});   // key -> valore digitato
  const [saving, setSaving] = useState("");
  let totPz=0, zero=0, sotto=0;
  ks.forEach(k=>{ const s=Number(giacBy[k].stock)||0; totPz+=s; if(s<=0)zero++; else if(giacBy[k].sotto_soglia)sotto++; });

  const salva = async (k) => {
    const g = giacBy[k];
    const val = draft[k];
    if (val === undefined || val === "" || isNaN(numIt(val))) { toast.error("Inserisci un numero"); return; }
    if (!g.id) { toast.error("Prodotto non rettificabile"); return; }
    setSaving(k);
    try {
      const r = await axios.post(`${API}/magazzino-bar/prodotti/${g.id}/rettifica`, { stock_contato: numIt(val), operatore_nome: "Ordini app" });
      toast.success(`${g.nome||k}: giacenza = ${r.data.stock_nuovo}`);
      setDraft(d=>{ const n={...d}; delete n[k]; return n; });
      onReload && onReload();
    } catch { toast.error("Errore nel salvataggio"); }
    finally { setSaving(""); }
  };

  const visibili = ks.filter(k => !q || (giacBy[k].nome||k).toLowerCase().includes(q.toLowerCase()));

  return (<>
    <div style={{ background:C.soft, border:`2px solid ${C.brand}`, borderRadius:16, padding:14, marginBottom:12 }}>
      <b>Giacenze magazzino</b>
      <div style={{ fontSize:14, fontWeight:800, marginTop:4 }}>{ks.length} prodotti · {totPz.toFixed(1).replace(".0","")} colli/pezzi</div>
      <div style={{ fontSize:12, color:C.muted, marginTop:2 }}>{zero} esauriti · {sotto} sotto scorta · scrivi quanto hai contato e premi Salva</div>
    </div>
    <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Cerca prodotto…"
      style={{ width:"100%", padding:"11px 14px", borderRadius:12, border:`1.5px solid ${C.line}`, marginBottom:12, fontSize:15 }} />
    {visibili.map(k=>{ const g=giacBy[k]; const st=Number(g.stock)||0; const dirty=draft[k]!==undefined;
      return (<div key={k} style={{ border:`1px solid ${st<=0?"#f0c4c0":C.line}`, borderRadius:14, padding:12, marginBottom:8 }}>
        <b style={{ fontSize:15 }}>{g.nome||k}</b>
        <div style={{ marginTop:6, display:"flex", alignItems:"center", gap:8, flexWrap:"wrap" }}>
          <Badge tone={st<=0?"zero":g.sotto_soglia?"warn":"giac"}>Giac. {st}{g.unita?` ${g.unita}`:""}</Badge>
          <span style={{ color:C.muted, fontSize:13 }}>Soglia {g.soglia||0}</span>
        </div>
        <EditGiacenzaSoglia giac={g} onSalvato={onReload} />
        <div style={{ display:"flex", alignItems:"center", gap:8, marginTop:10 }}>
          <input type="text" inputMode="decimal" value={draft[k]??""} placeholder="ho contato…"
            onChange={e=>setDraft(d=>({...d, [k]:e.target.value}))}
            style={{ flex:1, minWidth:0, padding:"10px 12px", borderRadius:12, border:`1.5px solid ${dirty?C.brand:C.line}`, fontSize:16, fontWeight:700 }} />
          <button onClick={()=>salva(k)} disabled={!dirty||saving===k}
            style={{ padding:"10px 18px", borderRadius:12, border:"none", background:dirty?C.brand:"#cfd8d0", color:"#fff", fontWeight:800, fontSize:15, cursor:dirty?"pointer":"default" }}>
            {saving===k?"…":"Salva"}
          </button>
        </div>
      </div>);
    })}
  </>);
}

function Carrello({ rows, tot, inc, prodotti, onSetFornitore, onCrea, onRemove }) {
  if (!rows.length) return <div style={{ textAlign:"center", color:C.muted, padding:40 }}>Carrello vuoto</div>;
  const find = (id) => prodotti.find(p=>String(p.id)===String(id)) || {};
  return (<>
    {rows.map(r=>{ const fut=(Number(r.stock_iniziale)||0)+(Number(r.qty)||0);
      return (<div key={r.id} style={{ border:`1px solid ${C.line}`, borderRadius:14, padding:12, marginBottom:10 }}>
        <div style={{ display:"flex", gap:10 }}>
          <div style={{ flex:1, minWidth:0, fontWeight:800 }}>{r.nome}
            <div style={{ fontSize:12, color:C.muted, marginTop:2 }}>Giac. {r.stock_iniziale||0} → prevista {fut}{r.richiesto_da?` · inserito da ${r.richiesto_da}`:""}</div>
          </div>
          <button onClick={()=>onRemove(r.id)} style={{ width:40, height:40, border:"none", borderRadius:12, background:"#fee2e2", color:"#b91c1c", cursor:"pointer" }}><X size={18}/></button>
        </div>
        {/* COMPARATORE: il MIGLIORE è già selezionato in automatico (il backend
            ordina: recente, poi più economico) — il menu serve solo a cambiarlo */}
        {(r.fornitori60 && r.fornitori60.length>1) ? (
          <div style={{ marginTop:8 }}>
            <div style={{ fontSize:11, fontWeight:800, color:C.muted, textTransform:"uppercase", letterSpacing:.5, marginBottom:4 }}>
              Fornitore · il migliore è già scelto{r.fornitore===r.fornitori60[0]?.fornitore ? " ✓" : " (cambiato a mano)"}
            </div>
            <select value={r.fornitore}
              onChange={(e)=>{ const f=r.fornitori60.find(x=>x.fornitore===e.target.value); if(f) onSetFornitore(r.id, f.fornitore, f.prezzo); }}
              style={{ width:"100%", padding:"10px 12px", borderRadius:12, border:`1.5px solid ${C.line}`, fontWeight:700, fontSize:14, background:"#fff" }}>
              {r.fornitori60.map((f,fi)=>(
                <option key={f.fornitore} value={f.fornitore}>
                  {fi===0?"★ ":""}{f.fornitore} — € {Number(f.prezzo).toFixed(2)} {f.recente?"· recente":(f.giorni_fa!=null?`· ${f.giorni_fa}gg fa`:"")}{fi===0?" · MIGLIORE":""}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <div style={{ fontSize:12, color:C.muted, marginTop:6 }}>{r.fornitore}{r.prezzo>0?` · € ${Number(r.prezzo).toFixed(2)}/${r.conf||"pz"}${r.prezzoRecente===false?" (vecchio)":""}`:" · prezzo n/d"}</div>
        )}
        <div style={{ display:"flex", alignItems:"center", gap:10, marginTop:10 }}>
          <button onClick={()=>inc(find(r.id),-1)} style={qtybtn}><Minus size={18}/></button>
          <b>{r.qty}</b>
          <button onClick={()=>inc(find(r.id),1)} style={qtybtn}><Plus size={18}/></button>
          <span style={{ marginLeft:"auto", fontWeight:800 }}>€ {((r.prezzo||0)*r.qty).toFixed(2)}</span>
        </div>
      </div>);
    })}
    <button onClick={onCrea} style={{ width:"100%", border:"none", borderRadius:16, background:`linear-gradient(135deg,${C.brand},#6f9180)`, color:"#fff", padding:15, fontWeight:800, fontSize:15, cursor:"pointer", marginTop:8 }}>
      Crea bozze ordine · € {tot.toFixed(2)}
    </button>
  </>);
}

function TotaliOrdine({ prodotti }) {
  let imp = 0, iva = 0, senzaIva = 0, senzaPrezzo = 0;
  (prodotti||[]).forEach(p => {
    const prz = Number(p.prezzo_ultimo)||0, q = Number(p.quantita)||0;
    if (prz<=0 || q<=0) { senzaPrezzo++; return; }
    imp += prz*q;
    const al = Number(p.iva_pct)||0;
    if (al>0) iva += prz*q*al/100; else senzaIva++;
  });
  if (imp<=0) return null;
  const r = { display:"flex", justifyContent:"space-between", fontSize:13, padding:"3px 2px" };
  return (
    <div style={{ marginTop:10, borderTop:`2px solid ${C.line}`, paddingTop:8 }}>
      <div style={r}><span style={{color:C.muted}}>Imponibile</span><b>€ {imp.toFixed(2)}</b></div>
      <div style={r}><span style={{color:C.muted}}>IVA{senzaIva?` (manca su ${senzaIva} riga/e)`:""}</span><b>€ {iva.toFixed(2)}</b></div>
      <div style={{ ...r, fontSize:15 }}><span style={{fontWeight:800}}>Totale ordine</span><b style={{color:C.brand}}>€ {(imp+iva).toFixed(2)}</b></div>
      {senzaPrezzo>0 && <div style={{fontSize:11,color:C.muted}}>{senzaPrezzo} riga/e senza prezzo non conteggiate</div>}
    </div>
  );
}

function DaInviare() {
  const { conferma, dialogConferma } = useConferma();
  const [ordini, setOrdini] = useState(null);
  const [busy, setBusy] = useState(false);
  const carica = useCallback(async () => {
    try {
      const [r1,r2] = await Promise.all([
        axios.get(`${API}/ordini-fornitori?stato=bozza&limit=100`),
        axios.get(`${API}/ordini-fornitori?stato=confermato&limit=100`),
      ]);
      const lista = [...(r1.data||[]),...(r2.data||[])].filter(o=>(o.prodotti||[]).length);
      setOrdini(lista);
      // Righe TUTTE pre-spuntate (richiesta Enzo 04/07/2026: "se le ho già
      // aggiunte io, perché devo rispuntarle?"): togli solo quelle che NON vuoi.
      setSel(Object.fromEntries(lista.map(o => [o.id, new Set((o.prodotti||[]).map(p => String(p.prodotto_id)))])));
    } catch { setOrdini([]); }
  }, []);
  useEffect(()=>{ carica(); }, [carica]);
  const [sel, setSel] = useState({});  // oid -> Set(pid)

  const toggleRiga = (oid,pid) => setSel(s=>{ const set=new Set(s[oid]||[]); set.has(pid)?set.delete(pid):set.add(pid); return {...s,[oid]:set}; });

  const cambiaQta = async (o, p, delta) => {
    const nuova = Math.max(0.5, (Number(p.quantita)||1) + delta);
    try {
      await axios.put(`${API}/ordini-fornitori/${o.id}/modifica-quantita`,
        { prodotti: [{ prodotto_id: String(p.prodotto_id), quantita: nuova }] });
      setOrdini(os => os.map(x => x.id!==o.id ? x : {...x,
        prodotti: x.prodotti.map(r => String(r.prodotto_id)===String(p.prodotto_id) ? {...r, quantita: nuova} : r)}));
    } catch { toast.error("Modifica non riuscita"); }
  };

  const annulla = async (o) => {
    if (!(await conferma(`Annullare l'ordine ${o.prodotti[0]?.fornitore||""}?`, { dettaglio: `${o.prodotti.length} righe` }))) return;
    try { await axios.delete(`${API}/ordini-fornitori/${o.id}`); toast.success("Ordine annullato"); carica(); }
    catch(e){ toast.error(e.response?.data?.detail || "Annullamento non riuscito"); }
  };

  const confermaInvia = async (o) => {
    const ids=[...(sel[o.id]||[])];
    if(!ids.length){ toast("Spunta almeno una riga"); return; }
    try {
      await axios.put(`${API}/ordini-fornitori/${o.id}/conferma-righe`, { prodotto_ids: ids });
      await axios.post(`${API}/ordini-fornitori/${o.id}/invia`);
      // Invio automatico rimosso: scarico il PDF da inviare a mano al fornitore.
      window.open(withToken(`${API}/ordini-fornitori/${o.id}/pdf`), "_blank");
      toast.success("Ordine confermato — PDF scaricato, invialo al fornitore"); carica();
    } catch(e){ toast.error(e.response?.data?.detail || "Errore invio"); }
  };

  const riordinoAuto = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/ordini-fornitori/genera-riordino`);
      const n = (r.data?.bozze_create||[]).length;
      toast.success(n ? `${n} bozze di riordino create` : "Niente da riordinare: scorte ok");
      carica();
    } catch(e){ toast.error(e.response?.data?.detail || "Riordino non riuscito"); }
    finally { setBusy(false); }
  };

  if (ordini===null) return <div style={{ textAlign:"center", color:C.muted, padding:40 }}>Carico ordini…</div>;
  return (<>
    {dialogConferma}
    <button onClick={riordinoAuto} disabled={busy}
      style={{ width:"100%", border:`2px solid ${C.brand}`, borderRadius:14, background:"#fff", color:C.brand, padding:12, fontWeight:800, cursor:"pointer", marginBottom:10 }}>
      {busy ? "Controllo scorte…" : "🔄 Genera riordino da sotto-scorta"}
    </button>
    {!ordini.length && <div style={{ textAlign:"center", color:C.muted, padding:40 }}>Nessuna bozza in attesa. Tutto inviato.</div>}
    {ordini.length>0 && (
      <div style={{ background:"#fff7ed", color:"#9a3412", border:"1px solid #fed7aa", borderRadius:14, padding:"10px 12px", fontSize:13, fontWeight:800, marginBottom:10 }}>
        Le righe sono GIÀ tutte spuntate: togli la spunta a quelle che NON vuoi ordinare, regola le quantità con −/+, poi Conferma.
      </div>
    )}
    {ordini.map(o=>(
      <div key={o.id} style={{ border:`1px solid ${C.line}`, borderRadius:14, padding:12, marginBottom:10 }}>
        <div style={{ display:"flex", alignItems:"center", gap:8 }}>
          <div style={{ flex:1, minWidth:0, fontWeight:800 }}>{o.prodotti[0]?.fornitore||"Fornitore"} <Badge tone={o.stato==="confermato"?"giac":undefined}>{o.stato}</Badge>
            <div style={{ fontSize:12, color:C.muted }}>{o.source==="riordino_auto"?"riordino automatico":o.source||""} · {o.data_ordine||""}</div>
          </div>
          <button onClick={()=>annulla(o)} title="Annulla ordine"
            style={{ border:"none", borderRadius:12, background:"#fee2e2", color:"#b91c1c", padding:"8px 12px", fontWeight:800, cursor:"pointer", fontSize:12 }}>
            Annulla
          </button>
        </div>
        {o.prodotti.map((p,i)=>{
          const przR = Number(p.prezzo_ultimo)||0, qtaR = Number(p.quantita)||0, impR = przR*qtaR;
          return (
          <div key={i} style={{ display:"flex", gap:8, alignItems:"center", padding:"7px 2px", borderTop:`1px solid #f1ede2`, flexWrap:"wrap" }}>
            <input type="checkbox" checked={(sel[o.id]||new Set()).has(String(p.prodotto_id))} onChange={()=>toggleRiga(o.id,String(p.prodotto_id))} style={{ width:22, height:22, flexShrink:0 }}/>
            <span style={{ flex:1, minWidth:140, fontWeight:700, fontSize:14 }}>{p.nome}
              <span style={{ display:"block", fontSize:11, color:C.muted, fontWeight:400 }}>
                {[przR>0?`€ ${przR.toFixed(2)}/${p.unita||"pz"}${p.iva_pct?` · IVA ${p.iva_pct}%`:""}`:"prezzo n/d",
                  p.richiesto_da?`inserito da ${p.richiesto_da}`:"", p.note||""].filter(Boolean).join(" · ")}
              </span>
            </span>
            <button onClick={()=>cambiaQta(o,p,-1)} style={{ ...qtybtn, width:32, height:32 }}><Minus size={14}/></button>
            <b style={{ minWidth:34, textAlign:"center", fontSize:14 }}>{p.quantita} {p.unita||""}</b>
            <button onClick={()=>cambiaQta(o,p,1)} style={{ ...qtybtn, width:32, height:32 }}><Plus size={14}/></button>
            <b style={{ minWidth:72, textAlign:"right", fontSize:13, color:C.ink }}>{impR>0?`€ ${impR.toFixed(2)}`:"—"}</b>
          </div>
        );})}
        <TotaliOrdine prodotti={o.prodotti}/>
        <button onClick={()=>confermaInvia(o)} style={{ width:"100%", border:"none", borderRadius:14, background:`linear-gradient(135deg,${C.brand},#6f9180)`, color:"#fff", padding:13, fontWeight:800, cursor:"pointer", marginTop:10 }}>
          Conferma e scarica PDF (invio manuale)
        </button>
      </div>
    ))}
  </>);
}
