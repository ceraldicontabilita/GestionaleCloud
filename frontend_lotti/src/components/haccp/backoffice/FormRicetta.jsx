// FormRicetta — estratto da BackofficeView.jsx (fase 2 refactoring 24/07/2026).
// Nessun cambio di comportamento: form completo di creazione/modifica ricetta
// (eredita scheda, proposta ingredienti, foto, rivendita, allergeni, food cost).
import { useState, useEffect, useRef } from "react";
import axios from "axios";
import { Globe } from "lucide-react";
import { conferma } from "../../../utils/conferma";
import { stampaDoc } from "../../../utils/stampa";
import PinKeypad from "../shared/PinKeypad";

const API = process.env.REACT_APP_LOTTI_BACKEND_URL + "/api";
const BACKEND = process.env.REACT_APP_LOTTI_BACKEND_URL || "";
// foto_url è relativo (/api/foto/..): per <img>/background va reso assoluto sul backend.
const fotoSrc = (u) => (u ? (/^https?:/.test(u) ? u : BACKEND + u) : "");

const toast = (msg, tipo = "ok") => {
  const div = document.createElement("div");
  div.textContent = msg;
  div.style.cssText = `
    position:fixed;bottom:24px;left:50%;transform:translateX(-50%);
    padding:10px 20px;border-radius:12px;font-weight:700;font-size:14px;
    color:#fff;z-index:9999;animation:fadeUp .3s ease;
    background:${tipo === "ok" ? "var(--success)" : tipo === "err" ? "var(--danger)" : "var(--warning)"};
    box-shadow:0 4px 20px rgba(0,0,0,.2);font-family:var(--font);
  `;
  document.body.appendChild(div);
  setTimeout(() => div.remove(), 2800);
};

const UNITA_OPTIONS = ["g","kg","ml","l","pz","uova","cucchiaio","cucchiaino","pizzico","q.b.","noce","foglio","bustina"];
const REPARTI = ["pasticceria","rosticceria","bar","altro"];
const METODI_CONS = [
  {id:"ambiente",  label:"Ambiente"},
  {id:"frigo",     label:"Frigo 0-4°C"},
  {id:"abbattitore_positivo", label:"Abbattitore +"},
  {id:"abbattitore_negativo", label:"Freezer −18°C"},
];

// Stile unico per tutte le file di scelte del form ricetta (fornitori,
// conservazione): chip piccole e uniformi, così stanno su meno righe possibili.
const chip = (attivo, colore = "var(--primary)") => ({
  padding:"6px 10px", borderRadius:8, border:"1.5px solid",
  fontFamily:"var(--font)", fontSize:12, fontWeight:700, cursor:"pointer",
  lineHeight:1.2, whiteSpace:"nowrap",
  background: attivo ? colore : "var(--card)",
  color: attivo ? "#fff" : "var(--text-2)",
  borderColor: attivo ? colore : "var(--border)",
});

function RigaIngrediente({ ing, idx, onChange, onRemove, bloccato = false }) {
  const [sugg, setSugg] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const justPicked = useRef(false);
  const digitando = useRef(false);  // true SOLO quando Enzo scrive in questo campo
  const boxRef = useRef(null);

  // Autocomplete dai prodotti reali delle fatture XML (dizionario_prodotti).
  // FIX 23/07/2026 ("errore nella visualizzazione quando clicco Proponi"):
  // si apre SOLO se il nome cambia perché Enzo sta scrivendo — quando
  // «Proponi»/proposta automatica riempie le righe, i menù restano chiusi
  // (prima si aprivano tutti insieme, uno sopra l'altro).
  useEffect(() => {
    if (justPicked.current) { justPicked.current = false; return; }
    if (!digitando.current) return;
    digitando.current = false;
    const q = (ing.nome || "").trim();
    if (q.length < 2) { setSugg([]); setOpen(false); return; }
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const r = await axios.get(`${API}/food-cost/dizionario/search`, { params: { q } });
        setSugg((r.data || []).slice(0, 12));
        setOpen(true);
      } catch { setSugg([]); }
      finally { setLoading(false); }
    }, 250);
    return () => clearTimeout(t);
  }, [ing.nome]);

  useEffect(() => {
    const h = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const titleCase = (s) => (s || "").replace(/\b\w/g, (c) => c.toUpperCase());
  const scegli = (p) => {
    justPicked.current = true;
    const nome = p.nome_canonico || titleCase(p.nome_normalizzato || p.nome || "");
    onChange(idx, "nome", nome);
    setOpen(false);
    setSugg([]);
  };

  return (
    <div style={{display:"flex",gap:8,alignItems:"center",marginBottom:8,background:"#fff",border:"1.5px solid var(--border)",borderRadius:10,padding:"8px 10px",flexWrap:"wrap"}}>
      <span style={{color:"var(--text-2)",fontSize:13,fontWeight:800,minWidth:20,textAlign:"center"}}>{idx+1}.</span>
      {/* Nome con autocomplete */}
      <div ref={boxRef} style={{flex:"1 1 180px",position:"relative",minWidth:140}}>
        <input
          value={ing.nome || ""}
          onChange={e => onChange(idx,"nome",e.target.value)}
          onFocus={() => { if (sugg.length) setOpen(true); }}
          placeholder="Ingrediente (cerca dalle fatture)…"
          style={{width:"100%",boxSizing:"border-box",padding:"10px 12px",border:"1.5px solid var(--border)",borderRadius:9,fontSize:15,fontWeight:700,color:"var(--text)",fontFamily:"var(--font)"}}
        />
        {open && (sugg.length > 0 || loading) && (
          <div style={{position:"absolute",top:"100%",left:0,right:0,zIndex:30,background:"#fff",border:"1px solid var(--border)",borderRadius:10,marginTop:4,maxHeight:240,overflowY:"auto",boxShadow:"0 10px 30px rgba(0,0,0,.18)"}}>
            {loading && <div style={{padding:"8px 12px",fontSize:12,color:"var(--text-3)"}}>Cerco…</div>}
            {sugg.map((p, i) => (
              <button key={i} type="button" onClick={() => scegli(p)}
                style={{display:"block",width:"100%",textAlign:"left",border:"none",background:"transparent",padding:"10px 12px",cursor:"pointer",fontFamily:"var(--font)",borderBottom:"1px solid var(--bg)"}}
                onMouseDown={(e)=>e.preventDefault()}>
                <div style={{fontSize:14,fontWeight:700,color:"var(--text)"}}>{p.nome_canonico || titleCase(p.nome_normalizzato || "")}</div>
                <div style={{fontSize:12,color:"var(--text-3)"}}>
                  {p.fornitore || "—"}{p.prezzo_kg ? ` · €${Number(p.prezzo_kg).toFixed(2)}/kg` : ""}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
      {/* Quantità */}
      <input
        type="number" min="0" step="0.01"
        value={ing.quantita || ""}
        onChange={e => onChange(idx,"quantita",e.target.value)}
        placeholder="Qtà"
        readOnly={bloccato}
        title={bloccato ? "Ricetta bloccata: per cambiare le dosi usa «Sblocca dosi» col PIN amministratore" : undefined}
        style={{width:72,padding:"10px 8px",border:"1.5px solid var(--border)",borderRadius:9,fontSize:15,fontWeight:700,textAlign:"center",fontFamily:"var(--font)",
          background: bloccato ? "#f0ebe0" : "#fff", color: bloccato ? "#7a7266" : "inherit", cursor: bloccato ? "not-allowed" : "auto"}}
      />
      {/* Unità */}
      <select
        value={ing.unita || "g"}
        disabled={bloccato}
        onChange={e => onChange(idx,"unita",e.target.value)}
        style={{padding:"10px 8px",border:"1.5px solid var(--border)",borderRadius:9,fontSize:15,fontFamily:"var(--font)",background:"#fff"}}>
        {UNITA_OPTIONS.map(u => <option key={u}>{u}</option>)}
      </select>
      {/* Elimina */}
      {!bloccato && <button onClick={() => onRemove(idx)} title="Rimuovi ingrediente"
        style={{width:34,height:34,flexShrink:0,border:"none",borderRadius:9,background:"var(--danger-soft)",color:"var(--danger)",fontWeight:800,fontSize:18,cursor:"pointer",display:"grid",placeItems:"center"}}>
        ×
      </button>}
    </div>
  );
}


function FormRicetta({ ricetta, onSalvato, onAnnulla, onApriScheda, onElimina, ricette = [] }) {
  const [form, setForm] = useState(() => {
    if (!ricetta) {
      return { nome:"", reparto:"pasticceria", porzioni:10, metodo_conservazione:"frigo", prezzo_vendita:"", note:"", ingredienti:[], fornitore_rivendita:"" };
    }
    // Converte ingredienti_dettaglio (o la lista legacy) nel formato editabile
    // {nome, quantita, unita}, così l'editor e il "+ Aggiungi" funzionano sempre.
    const det = ricetta.ingredienti_dettaglio || [];
    let ingredienti = [];
    if (det.length) {
      ingredienti = det.map(i => (typeof i === "string"
        ? { nome: i, quantita: "", unita: "g" }
        : { nome: i.nome || "", quantita: i.quantita ?? "", unita: i.unita_misura || i.unita || "g" }));
    } else if (Array.isArray(ricetta.ingredienti)) {
      ingredienti = ricetta.ingredienti.map(x => (typeof x === "string"
        ? { nome: x, quantita: "", unita: "g" }
        : { nome: x.nome || "", quantita: x.quantita ?? "", unita: x.unita_misura || x.unita || "g" }));
    }
    return { ...ricetta, ingredienti };
  });
  const [saving, setSaving] = useState(false);
  const [scadenza, setScadenza] = useState(null);
  const mountTs = useRef(Date.now());  // anti ghost-click sul backdrop

  // ── ORIGINE degli ingredienti (richiesta Enzo 23/07/2026): il sistema deve
  // distinguere le ricette scritte da lui ("manuale"), quelle con ingredienti
  // proposti in automatico ("automatica") e quelle ereditate da una ricetta
  // base ("ereditata"). Su manuale/ereditata NON si propone mai nulla da soli.
  // Ricette esistenti senza il campo → "manuale" (prudente: mai sovrascrivere).
  const [origineIngredienti, setOrigineIngredienti] = useState(
    ricetta?.origine_ingredienti || (ricetta?.id ? "manuale" : "")
  );
  // ── EREDITA SCHEDA: nuova variante da una ricetta di riferimento
  const [baseSel, setBaseSel] = useState("");
  const [ereditando, setEreditando] = useState(false);
  const autoProposta = useRef({ ultimoNome: "", inCorso: false });
  const nomeAuto = useRef("");  // nome messo DA NOI con l'eredità (per poterlo togliere)

  // Se Enzo toglie la ricetta di riferimento, il nome auto-inserito va via
  // (23/07/2026: "se elimino la ricetta di riferimento non si cancella il nome")
  const cambiaBase = (v) => {
    setBaseSel(v);
    if (!v) {
      setForm(f => ({
        ...f,
        nome: f.nome === nomeAuto.current ? "" : f.nome,
        ricetta_base_id: undefined,
        ricetta_base_nome: undefined,
      }));
      nomeAuto.current = "";
      setOrigineIngredienti(o => (o === "ereditata" ? "manuale" : o));
    }
  };

  const ereditaScheda = async () => {
    if (!baseSel) { toast("Scegli prima la ricetta di riferimento", "warn"); return; }
    setEreditando(true);
    try {
      const r = await axios.get(`${API}/ricette/${baseSel}`);
      const base = r.data || {};
      const det = base.ingredienti_dettaglio || [];
      const ings = det.length
        ? det.map(i => (typeof i === "string"
            ? { nome: i, quantita: "", unita: "g" }
            : { nome: i.nome || "", quantita: i.quantita ?? "", unita: i.unita_misura || i.unita || "g" }))
        : (base.ingredienti || []).map(x => (typeof x === "string"
            ? { nome: x, quantita: "", unita: "g" }
            : { nome: x.nome || "", quantita: x.quantita ?? "", unita: x.unita_misura || x.unita || "g" }));
      setForm(f => ({
        ...f,
        // Il nome parte da quello della base: Enzo aggiunge SOLO la variante
        // ("Arancini di riso " → "Arancini di riso ai funghi"). Se il nome
        // presente è quello auto-inserito da un'eredità precedente, si
        // sostituisce con la nuova base.
        nome: (f.nome || "").trim() && f.nome !== nomeAuto.current ? f.nome : `${base.nome} `,
        ingredienti: ings,
        reparto: base.reparto || f.reparto,
        porzioni: base.porzioni || f.porzioni,
        metodo_conservazione: base.metodo_conservazione || f.metodo_conservazione,
        ricetta_base_id: base.id,
        ricetta_base_nome: base.nome,
      }));
      nomeAuto.current = `${base.nome} `;
      setOrigineIngredienti("ereditata");
      toast(`Scheda ereditata da "${base.nome}" ✅ — aggiungi la variante al nome e l'ingrediente in più`);
    } catch { toast("Errore caricamento ricetta di riferimento", "err"); }
    finally { setEreditando(false); }
  };

  // Sezione "Costo, allergeni & nutrizione" (richiede ricetta salvata)
  const [allergeni, setAllergeni] = useState(ricetta?.allergeni || []);
  const [allSugg, setAllSugg]     = useState(null);
  const [costo, setCosto]         = useState(ricetta?.costo_totale != null ? { costo_totale: ricetta.costo_totale, costo_porzione: ricetta.costo_porzione } : null);
  const [nutri, setNutri]         = useState(ricetta?.nutrizionale || null);
  const [busyFc, setBusyFc]       = useState("");
  const [openExtra, setOpenExtra] = useState(false);
  const [uploadingFoto, setUploadingFoto] = useState(false);

  // Foto su ricetta NUOVA (Enzo 23/07/2026: "permettimi di inserire la foto
  // direttamente"): il file scelto resta in attesa e parte insieme al Salva.
  const [fotoPending, setFotoPending] = useState(null);
  const [fotoPreview, setFotoPreview] = useState(null);

  // Tendina "Comprato da…": i fornitori VERI dal database (Magazzino+Lotti,
  // non esclusi) — Enzo 23/07/2026: "elimina i tab, tendina coi fornitori
  // che popolano magazzino e lotti" (così ci sono anche Bigfood, Rondinella…).
  const [fornitoriRivendita, setFornitoriRivendita] = useState([]);
  useEffect(() => {
    axios.get(`${API}/fornitori`)
      .then(r => {
        const lista = Array.isArray(r.data) ? r.data : [];
        setFornitoriRivendita(lista
          .filter(f => !f.escluso && (f.tipo_fornitura || "completo") === "completo")
          .map(f => f.nome)
          .sort((a, b) => a.localeCompare(b, "it")));
      })
      .catch(() => {});
  }, []);

  const caricaFoto = async (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    if (!ricetta?.id) {
      setFotoPending(f);
      const fr = new FileReader();
      fr.onload = () => setFotoPreview(fr.result);
      fr.readAsDataURL(f);
      return;
    }
    setUploadingFoto(true);
    try {
      const fd = new FormData(); fd.append("file", f);
      const r = await axios.post(`${API}/ricette/${ricetta.id}/upload-foto`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setForm(s => ({ ...s, foto_url: r.data?.foto_url || s.foto_url }));
      toast("Foto aggiornata ✅");
    } catch { toast("Errore caricamento foto", "err"); }
    finally { setUploadingFoto(false); }
  };

  const calcolaCosto = async () => {
    setBusyFc("costo");
    try { const r = await axios.get(`${API}/food-cost/calcola/${ricetta.id}`); setCosto(r.data); }
    catch { toast("Errore calcolo food cost", "err"); }
    finally { setBusyFc(""); }
  };
  const rilevaAllergeni = async () => {
    setBusyFc("all");
    try {
      const r = await axios.post(`${API}/food-cost/auto-rileva-allergeni-ricetta/${ricetta.id}`);
      const suggeriti = r.data?.allergeni_suggeriti || [];
      setAllSugg(suggeriti);
      if (suggeriti.length > 0) setAllergeni(suggeriti); // evidenzia subito, resta modificabile a mano
    }
    catch { toast("Errore rilevamento allergeni", "err"); }
    finally { setBusyFc(""); }
  };
  const salvaAllergeni = async (lista) => {
    try { await axios.post(`${API}/food-cost/aggiorna-allergeni-ricetta`, { ricetta_id: ricetta.id, allergeni: lista });
      setAllergeni(lista); setAllSugg(null); toast("Allergeni salvati ✅"); }
    catch { toast("Errore salvataggio allergeni", "err"); }
  };
  const calcolaNutri = async () => {
    setBusyFc("nutri");
    try { const r = await axios.post(`${API}/food-cost/calcola-nutrizionale/${ricetta.id}`);
      setNutri(r.data?.valori_nutrizionali || r.data?.nutrizionale || r.data); toast("Valori nutrizionali calcolati ✅"); }
    catch { toast("Servono ingredienti a peso (g/kg/ml)", "err"); }
    finally { setBusyFc(""); }
  };
  const stampaScheda = () => stampaDoc({
    categoria: "ricette", url: `${API}/ricette/${ricetta.id}/pdf-scheda`,
    formato: "html", titolo: `Scheda ${ricetta?.nome || ""}`,
  }).catch(() => {});

  const [openProc, setOpenProc] = useState(false);
  const toText = (v) => Array.isArray(v)
    ? v.map(x => typeof x === "object"
        ? (x.titolo ? `${x.titolo}: ${x.testo || x.descrizione || ""}` : `${x.elemento || x.nome || ""}${x.nota ? " — " + x.nota : ""}`)
        : x).join("\n")
    : (v || "");
  const toLines = (t) => (t || "").split("\n").map(s => s.trim()).filter(Boolean);
  const asLines = (v) => toLines(typeof v === "string" ? v : toText(v));

  const setField = (k, v) => setForm(f => ({...f,[k]:v}));

  // Colore del reparto (banner "stai modificando"): coerente con le card.
  const bannerColor = form.reparto === "pasticceria" ? "#ea580c"
    : form.reparto === "rosticceria" ? "#16a34a"
    : form.reparto === "bar" ? "#78350f" : "var(--primary)";
  const lbl = { fontSize: 12, fontWeight: 800, color: "var(--text-2)", textTransform: "uppercase", letterSpacing: ".05em", display: "block", marginBottom: 6 };
  const inp = { width: "100%", padding: "12px 14px", border: "1.5px solid var(--border)", borderRadius: 10, fontSize: 15, fontFamily: "var(--font)", boxSizing: "border-box" };

  // Ogni tocco di Enzo sugli ingredienti rende la ricetta SUA ("manuale"):
  // da quel momento il sistema non propone/sostituisce più nulla da solo.
  const _segnaManuale = () => setOrigineIngredienti(o => (o === "ereditata" ? o : "manuale"));
  const addIng = () => { _segnaManuale(); setForm(f => ({...f, ingredienti:[...f.ingredienti,{nome:"",quantita:"",unita:"g"}]})); };
  const changeIng = (idx, k, v) => { _segnaManuale(); setForm(f => {
    const ings = [...f.ingredienti];
    ings[idx] = {...ings[idx],[k]:v};
    return {...f, ingredienti:ings};
  }); };
  const removeIng = (idx) => { _segnaManuale(); setForm(f => ({...f, ingredienti:f.ingredienti.filter((_,i)=>i!==idx)})); };

  // ── DOSI BLOCCATE (richiesta Enzo 25/07/2026) ──────────────────────────────
  // Una ricetta già salvata nasce BLOCCATA: le dosi non si toccano per sbaglio
  // con le freccette. Per correggerle serve il PIN amministratore. Le ricette
  // nuove restano libere finché non vengono salvate la prima volta.
  const [doseSbloccata, setDoseSbloccata] = useState(!ricetta?.id);
  const [chiediPinDosi, setChiediPinDosi] = useState(false);
  const doseBloccata = !doseSbloccata;

  // Intelligenza: propone gli ingredienti tipici dal NOME della ricetta.
  const [proponendo, setProponendo] = useState(false);
  const proponiIngredienti = async () => {
    const nome = (form.nome || "").trim();
    if (!nome) { toast("Scrivi prima il nome della ricetta", "warn"); return; }
    setProponendo(true);
    try {
      const r = await axios.post(`${API}/food-cost/suggerisci-ingredienti`,
        { nome_ricetta: nome, porzioni: parseInt(form.porzioni) || 10 }, { timeout: 45000 });
      const sugg = r.data?.ingredienti || [];
      if (!sugg.length) { toast(r.data?.messaggio || "Nessun suggerimento", "warn"); return; }
      // FIX 25/07/2026 (segnalato da Enzo): prima si AGGIUNGEVA in coda, quindi
      // premendo "Proponi" due volte gli ingredienti si duplicavano. Ora si
      // uniscono senza doppioni: quelli già in elenco restano come sono (con
      // le quantità che hai corretto tu), si aggiungono solo i mancanti.
      let aggiunti = 0;
      setForm(f => {
        const chiave = (n) => (n || "").trim().toLowerCase()
          .normalize("NFD").replace(/[\u0300-\u036f]/g, "");
        const presenti = new Set((f.ingredienti || []).map(i => chiave(i.nome)));
        const nuovi = sugg
          .filter(s => !presenti.has(chiave(s.nome)))
          .map(s => ({ nome: s.nome, quantita: s.quantita ?? "", unita: s.unita || "g" }));
        aggiunti = nuovi.length;
        return { ...f, ingredienti: [...(f.ingredienti || []), ...nuovi] };
      });
      setOrigineIngredienti(o => (o === "" ? "automatica" : o));
      const fonte = r.data?.fonte === "ai" ? "AI" : r.data?.fonte === "kb" ? "ricettario" : r.data?.fonte || "ricettario";
      setTimeout(() => toast(
        aggiunti > 0
          ? `Aggiunti ${aggiunti} ingredienti (${fonte}) — controlla e salva`
          : "Gli ingredienti proposti ci sono già tutti: niente da aggiungere"
      ), 0);
    } catch { toast("Errore nel suggerimento ingredienti", "err"); }
    finally { setProponendo(false); }
  };

  // ── PROPOSTA AUTOMATICA (richiesta Enzo 23/07/2026): su una ricetta NUOVA,
  // appena scrive il nome ("babà misù", "arancino ai funghi"...) gli
  // ingredienti tipici arrivano DA SOLI, senza premere «Proponi». MAI su:
  // ricette esistenti (id presente), ricette ereditate («qui non devi
  // propormi gli ingredienti»), ricette dove ha già messo mano lui (manuale).
  // Finché resta "automatica" e cambia il nome, la proposta si aggiorna.
  useEffect(() => {
    if (ricetta?.id) return;
    if (form.fornitore_rivendita) return;  // prodotto comprato: niente proposta
    if (origineIngredienti === "ereditata" || origineIngredienti === "manuale") return;
    const nome = (form.nome || "").trim();
    if (nome.length < 4 || autoProposta.current.ultimoNome === nome) return;
    const t = setTimeout(async () => {
      if (autoProposta.current.inCorso) return;
      autoProposta.current.inCorso = true;
      autoProposta.current.ultimoNome = nome;
      setProponendo(true);
      try {
        const r = await axios.post(`${API}/food-cost/suggerisci-ingredienti`, {
          nome_ricetta: nome, porzioni: parseInt(form.porzioni) || 10,
        }, { timeout: 45000 });
        const sugg = r.data?.ingredienti || [];
        if (sugg.length) {
          setForm(f => ({ ...f, ingredienti: sugg.map(s => ({ nome: s.nome, quantita: s.quantita ?? "", unita: s.unita || "g" })) }));
          setOrigineIngredienti("automatica");
          toast(`${sugg.length} ingredienti proposti in automatico — correggili pure: appena li tocchi la ricetta diventa tua`);
        }
      } catch { /* proposta silenziosa: se fallisce, resta il bottone Proponi */ }
      finally { setProponendo(false); autoProposta.current.inCorso = false; }
    }, 1200);
    return () => clearTimeout(t);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.nome, origineIngredienti, form.fornitore_rivendita]);

  // Intelligenza visiva: legge la foto di un'etichetta e ne estrae gli ingredienti.
  const [leggendoFoto, setLeggendoFoto] = useState(false);
  const leggiEtichetta = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";              // permette di riscattare la stessa foto
    if (!file) return;
    setLeggendoFoto(true);
    try {
      const b64 = await new Promise((res, rej) => {
        const fr = new FileReader();
        fr.onload = () => res(fr.result);
        fr.onerror = rej;
        fr.readAsDataURL(file);
      });
      const r = await axios.post(`${API}/food-cost/leggi-ingredienti-foto`, {
        immagine_base64: b64, media_type: file.type || "image/jpeg",
      });
      const sugg = r.data?.ingredienti || [];
      if (!sugg.length) { toast(r.data?.messaggio || "Nessun ingrediente letto", "warn"); return; }
      setForm(f => ({ ...f, ingredienti: [...f.ingredienti, ...sugg.map(s => ({ nome: s.nome, quantita: s.quantita ?? "", unita: s.unita || "g" }))] }));
      toast(`Letti ${sugg.length} ingredienti dall'etichetta — controlla e salva`);
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast(`Lettura etichetta non riuscita${typeof d === "string" ? ": " + d : ""}`, "err");
    } finally { setLeggendoFoto(false); }
  };

  // Calcola scadenza preview
  const calcolaScadenza = async () => {
    try {
      const r = await axios.post(`${API}/shelf-life/calcola`, {
        nome_prodotto: form.nome,
        ingredienti: form.ingredienti.map(i=>i.nome).filter(Boolean),
        metodo_conservazione: form.metodo_conservazione,
      });
      setScadenza(r.data);
    } catch {}
  };

  // Converte numeri scritti all'italiana ("0,5") in float (0.5).
  const num = (v) => {
    if (v == null || v === "") return 0;
    const n = parseFloat(String(v).replace(",", "."));
    return Number.isFinite(n) ? n : 0;
  };

  const salva = async () => {
    if (!form.nome.trim()) { toast("Inserisci il nome ricetta","warn"); return; }
    setSaving(true);
    try {
      // Invia solo i campi che il backend si aspetta: evita di rispedire
      // _id / created_at / oggetti annidati che facevano fallire la validazione.
      const payload = {
        nome: form.nome.trim(),
        reparto: form.reparto || "pasticceria",
        porzioni: parseInt(form.porzioni) || 10,
        prezzo_vendita: num(form.prezzo_vendita),
        metodo_conservazione: form.metodo_conservazione || "frigo",
        foto_url: form.foto_url || "",
        note: typeof form.note === "string" ? form.note : "",
        ingredienti: form.ingredienti.map(i => i.nome).filter(Boolean),
        ingredienti_dettaglio: form.ingredienti
          .filter(i => (i.nome || "").trim())
          .map(i=>({
            nome: i.nome.trim(),
            quantita: num(i.quantita),
            unita_misura: i.unita || "g",
          })),
        // Memoria manuale/automatica/ereditata (richiesta Enzo 23/07/2026)
        origine_ingredienti: origineIngredienti || "manuale",
        // Prodotto di rivendita: "" = lo produciamo noi
        fornitore_rivendita: form.fornitore_rivendita || "",
        // Menu digitale (Enzo 03/09/2026): la ricetta va SEMPRE anche nel Menu
        // con la stessa foto; questo flag decide se i clienti la vedono.
        menu_pubblico: !!form.menu_pubblico,
        ...(form.ricetta_base_id && { ricetta_base_id: form.ricetta_base_id,
                                       ricetta_base_nome: form.ricetta_base_nome || "" }),
      };
      let creata = null;
      let menuSync = null;
      if (ricetta?.id) {
        const ru = await axios.put(`${API}/ricette/${ricetta.id}`, payload);
        menuSync = ru.data?.menu_sync || null;
      } else {
        const rr = await axios.post(`${API}/ricette`, payload);
        creata = rr.data;
        menuSync = creata?.menu_sync || null;
      }
      // Foto scelta PRIMA del salvataggio (ricetta nuova): parte adesso
      const idFoto = ricetta?.id || creata?.id;
      if (fotoPending && idFoto) {
        try {
          const fd = new FormData(); fd.append("file", fotoPending);
          await axios.post(`${API}/ricette/${idFoto}/upload-foto`, fd, { headers: { "Content-Type": "multipart/form-data" } });
        } catch {
          toast("Ricetta salvata, ma la foto non è partita: riaprila e ricaricala", "warn");
        }
      }
      if (menuSync?.esito === "errore") {
        toast("Ricetta salvata, ma il Menu digitale non è stato aggiornato: riprova con «Aggiorna ricetta»", "warn");
      } else {
        toast("Ricetta salvata ✅");
      }
      onSalvato();
    } catch (e) {
      const d = e?.response?.data?.detail;
      const msg = typeof d === "string" ? d
        : Array.isArray(d) ? d.map(x => x.msg || "").filter(Boolean).join(" · ")
        : (e?.message || "");
      toast(`Errore salvataggio${msg ? ": " + msg : ""}`, "err");
    }
    finally { setSaving(false); }
  };

  return (
    <div
      onClick={(e) => {
        // Chiudi solo se il click parte e finisce sul backdrop stesso (non sul
        // contenuto) e non nei primi 400ms dal montaggio: evita il "ghost click"
        // del tocco di navigazione su tablet che chiudeva il modale appena aperto.
        if (e.target !== e.currentTarget) return;
        if (Date.now() - mountTs.current < 400) return;
        onAnnulla();
      }}
      style={{position:"fixed",inset:0,zIndex:2000,background:"rgba(0,0,0,.55)",display:"flex",alignItems:"flex-start",justifyContent:"center",padding:"18px 10px"}}>
    <div onClick={e=>e.stopPropagation()} style={{background:"var(--card)",borderRadius:16,boxShadow:"0 24px 70px rgba(0,0,0,.45)",overflow:"hidden",overflowY:"auto",width:"100%",maxWidth:620,maxHeight:"94vh"}}>
      {/* Fascia EVIDENTE: stai modificando questa ricetta (colore del reparto) */}
      <div style={{position:"sticky",top:0,zIndex:5,background:bannerColor,color:"#fff",padding:"16px 20px",display:"flex",alignItems:"center",justifyContent:"space-between",gap:10,flexWrap:"wrap"}}>
        <div style={{minWidth:0}}>
          <div style={{fontSize:11,fontWeight:800,letterSpacing:".08em",textTransform:"uppercase",opacity:.85}}>
            {ricetta?.id ? "✏️ Stai modificando la ricetta" : "✨ Nuova ricetta"}
          </div>
          <div style={{fontSize:21,fontWeight:900,lineHeight:1.2,whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>
            {form.nome || ricetta?.nome || "Senza nome"}
            {form.reparto ? <span style={{fontSize:12,fontWeight:800,opacity:.85,marginLeft:8}}>· {form.reparto}</span> : null}
          </div>
        </div>
        <div style={{display:"flex",gap:8,flexShrink:0,flexWrap:"wrap"}}>
          {ricetta?.id && onApriScheda && (
            <button onClick={() => onApriScheda(ricetta)}
              title="Procedimento, consigli, varianti — la scheda stampabile"
              style={{padding:"8px 14px",border:"none",borderRadius:10,background:"rgba(255,255,255,.22)",color:"#fff",fontFamily:"var(--font)",fontSize:13,fontWeight:800,cursor:"pointer"}}>
              📋 Procedimento
            </button>
          )}
          {ricetta?.id && (
            <button onClick={stampaScheda}
              style={{padding:"8px 14px",border:"none",borderRadius:10,background:"rgba(255,255,255,.22)",color:"#fff",fontFamily:"var(--font)",fontSize:13,fontWeight:800,cursor:"pointer"}}>
              🖨️ Stampa
            </button>
          )}
          <button onClick={onAnnulla}
            style={{padding:"8px 14px",border:"none",borderRadius:10,background:"#fff",color:bannerColor,fontFamily:"var(--font)",fontSize:13,fontWeight:800,cursor:"pointer"}}>
            ✕ Chiudi
          </button>
        </div>
      </div>

      <div style={{padding:24}}>

      {/* Foto ricetta — anche su ricetta NUOVA: la scelta resta in anteprima
          e la foto parte insieme al Salva */}
      <div style={{display:"flex",alignItems:"center",gap:14,marginBottom:16}}>
        <div style={{width:84,height:84,borderRadius:12,flexShrink:0,overflow:"hidden",
          background: fotoPreview ? `center/cover no-repeat url('${fotoPreview}')`
            : form.foto_url ? `center/cover no-repeat url('${fotoSrc(form.foto_url)}')` : "var(--primary-soft)",
          display:"grid",placeItems:"center"}}>
          {!fotoPreview && !form.foto_url && <span style={{fontSize:34}}>📷</span>}
        </div>
        <div>
          <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
            <label style={{display:"inline-flex",alignItems:"center",gap:6,padding:"9px 14px",borderRadius:10,border:"1.5px solid var(--border)",background:"var(--card)",fontSize:13,fontWeight:700,cursor:uploadingFoto?"wait":"pointer"}}>
              🖼️ {uploadingFoto ? "Carico…" : (form.foto_url || fotoPreview ? "Cambia foto" : "Aggiungi foto")}
              <input type="file" accept="image/*" onChange={caricaFoto} disabled={uploadingFoto} style={{display:"none"}} />
            </label>
            <label style={{display:"inline-flex",alignItems:"center",gap:6,padding:"9px 14px",borderRadius:10,border:"none",background:"var(--primary)",color:"#fff",fontSize:13,fontWeight:800,cursor:uploadingFoto?"wait":"pointer"}}>
              📸 Scatta foto
              <input type="file" accept="image/*" capture="environment" onChange={caricaFoto} disabled={uploadingFoto} style={{display:"none"}} />
            </label>
          </div>
          {!ricetta?.id && fotoPending && (
            <div style={{marginTop:6,fontSize:12,fontWeight:700,color:"var(--success-text)"}}>
              ✓ Foto pronta: si salva insieme alla ricetta
            </div>
          )}
        </div>
      </div>

      {/* Dati base — nome a riga intera, il resto compatto su una riga
          (prima erano 4 righe piene: il form sembrava infinito) */}
      <div style={{display:"flex",flexDirection:"column",gap:14,marginBottom:18}}>
        <div>
          <label style={lbl}>Nome ricetta *</label>
          <input value={form.nome} onChange={e=>setField("nome",e.target.value)} placeholder="es. Babà al Rum" style={inp}/>
        </div>
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit, minmax(140px, 1fr))",gap:10}}>
          <div>
            <label style={lbl}>Reparto</label>
            <select value={form.reparto} onChange={e=>setField("reparto",e.target.value)} style={{...inp,background:"var(--card)"}}>
              {REPARTI.map(r=><option key={r} value={r}>{r.charAt(0).toUpperCase()+r.slice(1)}</option>)}
            </select>
          </div>
          <div>
            <label style={lbl}>Pezzi base</label>
            <input type="number" min="1" value={form.porzioni} onChange={e=>setField("porzioni",e.target.value)} style={inp}/>
          </div>
          <div>
            <label style={lbl}>Prezzo (€)</label>
            <input type="number" min="0" step="0.01" value={form.prezzo_vendita} onChange={e=>setField("prezzo_vendita",e.target.value)} placeholder="0.00" style={inp}/>
          </div>
        </div>
        {/* Menu digitale (richiesta Enzo 03/09/2026): ogni ricetta finisce
            comunque nel Menu con la stessa foto; qui decide lui se i clienti
            la vedono nel menu pubblico (QR al tavolo). */}
        <label style={{display:"flex",alignItems:"center",gap:12,padding:"10px 14px",borderRadius:10,cursor:"pointer",
          border:"1.5px solid", borderColor: form.menu_pubblico ? "var(--primary)" : "var(--border)",
          background: form.menu_pubblico ? "var(--primary-soft)" : "var(--card)"}}>
          <input type="checkbox" checked={!!form.menu_pubblico}
            onChange={e=>setField("menu_pubblico",e.target.checked)}
            style={{width:20,height:20,flexShrink:0,accentColor:"var(--primary)",cursor:"pointer"}}/>
          <Globe size={18} color="var(--primary)" style={{flexShrink:0}} aria-hidden="true" />
          <span style={{display:"flex",flexDirection:"column",gap:2,minWidth:0}}>
            <span style={{fontSize:14,fontWeight:800,color:"var(--text)"}}>Mostra nel menu pubblico (Menu digitale)</span>
            <span style={{fontSize:12,fontWeight:600,color:"var(--text-2)"}}>
              La ricetta va comunque nel Menu con la stessa foto: spunta per farla vedere ai clienti.
            </span>
          </span>
        </label>
      </div>

      {/* Variante di una ricetta esistente (solo nuova ricetta): scegli la
          base e «Eredita scheda» — ingredienti/reparto/pezzi arrivano da lì,
          poi Enzo dà il nome e aggiunge l'ingrediente della variante. */}
      {!ricetta?.id && (
        <div style={{border:"1.5px dashed var(--border)",borderRadius:12,padding:"12px 14px",marginBottom:16,background:"var(--bg)"}}>
          <div style={{fontSize:12,fontWeight:800,color:"var(--text-2)",textTransform:"uppercase",letterSpacing:".05em",marginBottom:8}}>
            🧬 È la variante di una ricetta che hai già? (es. arancini di riso → ai funghi)
          </div>
          <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
            <select value={baseSel} onChange={e=>cambiaBase(e.target.value)}
              style={{...inp,flex:1,minWidth:180,width:"auto",background:"var(--card)"}}>
              <option value="">— Scegli la ricetta di riferimento —</option>
              {[...ricette].sort((a,b)=>(a.nome||"").localeCompare(b.nome||"","it")).map(r =>
                <option key={r.id} value={r.id}>{r.nome}</option>)}
            </select>
            <button onClick={ereditaScheda} disabled={ereditando || !baseSel}
              style={{padding:"10px 16px",border:"none",borderRadius:10,background:"var(--primary)",color:"#fff",
                fontWeight:800,fontSize:13,cursor:baseSel?"pointer":"not-allowed",fontFamily:"var(--font)",opacity:baseSel?1:.5}}>
              {ereditando ? "Eredito…" : "🧬 Eredita scheda"}
            </button>
          </div>
          {form.ricetta_base_nome && (
            <div style={{marginTop:8,fontSize:12,fontWeight:700,color:"var(--primary)"}}>
              ✓ Variante di «{form.ricetta_base_nome}» — ingredienti ereditati, aggiungi quello in più
            </div>
          )}
        </div>
      )}

      {/* Prodotto COMPRATO già pronto? Tab dei fornitori di rivendita.
          Con un fornitore selezionato la proposta automatica ingredienti si
          spegne (è un prodotto acquistato, non una ricetta da comporre). */}
      <div style={{marginBottom:12}}>
        <label style={{fontSize:11,fontWeight:700,color:"var(--text-2)",textTransform:"uppercase",letterSpacing:".05em",display:"block",marginBottom:6}}>
          Lo produciamo noi o lo compriamo?
        </label>
        <div style={{display:"flex",gap:6,flexWrap:"wrap",alignItems:"center"}}>
          <button onClick={()=>setField("fornitore_rivendita","")} style={chip(!form.fornitore_rivendita)}>
            🏠 Lo produciamo noi
          </button>
          <select value={form.fornitore_rivendita || ""} onChange={e=>setField("fornitore_rivendita",e.target.value)}
            style={{...inp,flex:1,minWidth:170,width:"auto",background:"var(--card)",
              borderColor: form.fornitore_rivendita ? "#8a6f47" : "var(--border)",
              color: form.fornitore_rivendita ? "#6f583a" : "var(--text-2)",fontWeight:700}}>
            <option value="">🛒 Comprato da… (scegli il fornitore)</option>
            {fornitoriRivendita.map(n => <option key={n} value={n}>{n}</option>)}
            {form.fornitore_rivendita && !fornitoriRivendita.includes(form.fornitore_rivendita) && (
              <option value={form.fornitore_rivendita}>{form.fornitore_rivendita}</option>
            )}
          </select>
        </div>
        {form.fornitore_rivendita && (
          <div style={{marginTop:6,fontSize:12,fontWeight:700,color:"#8a6f47"}}>
            Prodotto comprato da {form.fornitore_rivendita}: niente ingredienti proposti in automatico.
          </div>
        )}
      </div>

      {/* Metodo conservazione */}
      <div style={{marginBottom:12}}>
        <label style={{fontSize:11,fontWeight:700,color:"var(--text-2)",textTransform:"uppercase",letterSpacing:".05em",display:"block",marginBottom:6}}>Metodo di conservazione</label>
        <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
          {METODI_CONS.map(m => (
            <button key={m.id} onClick={()=>{setField("metodo_conservazione",m.id);setScadenza(null);}}
              style={chip(form.metodo_conservazione===m.id)}>
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {/* Scadenza preview */}
      {form.ingredienti.length > 0 && (
        <div style={{marginBottom:16}}>
          <button onClick={calcolaScadenza}
            style={{padding:"7px 16px",border:"none",borderRadius:10,background:"var(--primary-soft)",color:"var(--primary)",fontWeight:700,fontSize:13,cursor:"pointer",fontFamily:"var(--font)"}}>
            🕐 Calcola scadenza stimata
          </button>
          {scadenza && (
            <div style={{marginTop:10,padding:"10px 14px",borderRadius:10,
              background: scadenza.livello_rischio==="alto"?"var(--danger-soft)":scadenza.livello_rischio==="medio"?"var(--warning-soft)":"var(--success-soft)",
              color: scadenza.livello_rischio==="alto"?"var(--danger-text)":scadenza.livello_rischio==="medio"?"var(--warning-text)":"var(--success-text)",
            }}>
              <strong>Scade il {scadenza.data_scadenza}</strong> ({scadenza.giorni} giorni)
              {scadenza.ingrediente_critico && ` · critico: ${scadenza.ingrediente_critico}`}
            </div>
          )}
        </div>
      )}

      {/* Ingredienti */}
      <div style={{marginBottom:16}}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12,flexWrap:"wrap",gap:8}}>
          <div style={{fontSize:16,fontWeight:800,color:"var(--text)"}}>
            🧺 Ingredienti <span style={{color:"var(--text-3)",fontWeight:700}}>({form.ingredienti.length})</span>
            {origineIngredienti && (
              <span style={{marginLeft:8,fontSize:11,fontWeight:800,padding:"3px 8px",borderRadius:999,
                background: origineIngredienti==="manuale" ? "var(--success-soft)" : origineIngredienti==="ereditata" ? "var(--primary-soft)" : "var(--warning-soft)",
                color: origineIngredienti==="manuale" ? "var(--success-text)" : origineIngredienti==="ereditata" ? "var(--primary)" : "var(--warning-text)"}}>
                {origineIngredienti==="manuale" ? "✍️ scritti da te" : origineIngredienti==="ereditata" ? `🧬 ereditati${form.ricetta_base_nome ? ` da ${form.ricetta_base_nome}` : ""}` : "🤖 proposti in automatico"}
              </span>
            )}
          </div>
          <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
            <label title="Scatta/carica la foto di un'etichetta: l'AI ne legge gli ingredienti"
              style={{display:"inline-flex",alignItems:"center",gap:5,padding:"6px 12px",border:"1.5px solid #78350f",borderRadius:8,background:"var(--card)",color:"#78350f",fontWeight:800,fontSize:13,cursor:leggendoFoto?"wait":"pointer",fontFamily:"var(--font)"}}>
              {leggendoFoto ? "Leggo…" : "📷 Leggi etichetta"}
              <input type="file" accept="image/*" capture="environment" onChange={leggiEtichetta} disabled={leggendoFoto} style={{display:"none"}} />
            </label>
            <button onClick={proponiIngredienti} disabled={proponendo}
              title="Proponi gli ingredienti tipici dal nome della ricetta"
              style={{padding:"6px 12px",border:"1.5px solid var(--primary)",borderRadius:8,background:"var(--card)",color:"var(--primary)",fontWeight:800,fontSize:13,cursor:"pointer",fontFamily:"var(--font)"}}>
              {proponendo ? "Penso…" : "✨ Proponi"}
            </button>
          </div>
        </div>
        {form.ingredienti.length === 0 && (
          <div style={{textAlign:"center",padding:"22px 16px",color:"var(--text-3)",fontSize:14,background:"var(--bg)",borderRadius:10,marginBottom:10}}>
            Nessun ingrediente.<br/>Usa <b>+ Aggiungi ingrediente</b> qui sotto, oppure <b>✨ Proponi</b> / <b>📷 Leggi etichetta</b>.
          </div>
        )}
        {form.ingredienti.map((ing,idx) => (
          <RigaIngrediente key={idx} ing={ing} idx={idx} onChange={changeIng} onRemove={removeIng} bloccato={doseBloccata}/>
        ))}
        {doseBloccata && (
          <div style={{display:"flex",alignItems:"center",gap:10,flexWrap:"wrap",marginTop:8,padding:"10px 12px",
            background:"var(--info-soft)",border:"1.5px solid var(--info-border)",borderRadius:10}}>
            <span style={{fontSize:12,fontWeight:700,color:"var(--info-text)",flex:1,minWidth:180}}>
              Dosi bloccate: questa è la ricetta ufficiale. Per produrre di più o di meno
              usa <b>Dose di oggi</b> — qui si cambia solo la ricetta.
            </span>
            <button onClick={() => setChiediPinDosi(true)}
              style={{padding:"9px 14px",borderRadius:10,border:"none",background:"var(--info)",color:"#fff",
                fontWeight:800,fontSize:13,cursor:"pointer",fontFamily:"var(--font)",whiteSpace:"nowrap"}}>
              🔓 Sblocca dosi
            </button>
          </div>
        )}
        {/* Aggiungi: bottone grande e chiaro a tutta larghezza */}
        {!doseBloccata && <button onClick={addIng}
          style={{width:"100%",marginTop:6,padding:"12px",border:"2px dashed var(--primary)",borderRadius:10,background:"var(--primary-soft)",color:"var(--primary)",fontWeight:800,fontSize:15,cursor:"pointer",fontFamily:"var(--font)"}}>
          + Aggiungi ingrediente
        </button>}
      </div>

      {/* Costo, allergeni & nutrizione (sezione richiudibile) */}
      <div style={{border:"1px solid var(--border)",borderRadius:12,marginBottom:16,overflow:"hidden"}}>
        <button onClick={()=>setOpenExtra(o=>!o)}
          style={{all:"unset",cursor:"pointer",display:"flex",alignItems:"center",gap:8,fontWeight:800,color:"var(--text)",fontSize:14,padding:"12px 14px",width:"100%",boxSizing:"border-box",background:"var(--bg)"}}>
          🧮 Costo, allergeni & valori nutrizionali {openExtra ? "▲" : "▼"}
        </button>
        {openExtra && (
          <div style={{padding:"14px"}}>
            {!ricetta?.id ? (
              <div style={{fontSize:13,color:"var(--text-2)"}}>Salva prima la ricetta, poi qui calcoli costo, allergeni e valori nutrizionali.</div>
            ) : (
              <div style={{display:"flex",flexDirection:"column",gap:16}}>
                {/* Food cost */}
                <div>
                  <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:6}}>
                    <b style={{fontSize:13,color:"var(--text)"}}>Food cost</b>
                    <button onClick={calcolaCosto} disabled={busyFc==="costo"}
                      style={{padding:"5px 12px",borderRadius:8,border:"none",background:"var(--primary)",color:"#fff",fontSize:12,fontWeight:700,cursor:"pointer"}}>
                      {busyFc==="costo"?"Calcolo…":"Calcola"}
                    </button>
                  </div>
                  {costo && (
                    <div style={{display:"flex",gap:18,fontSize:14}}>
                      <span>Totale: <b>€ {Number(costo.costo_totale||0).toFixed(2)}</b></span>
                      <span>Per porzione: <b>€ {Number(costo.costo_porzione||0).toFixed(2)}</b></span>
                    </div>
                  )}
                </div>
                {/* Allergeni */}
                <div>
                  <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:6,flexWrap:"wrap"}}>
                    <b style={{fontSize:13,color:"var(--text)"}}>Allergeni</b>
                    <button onClick={rilevaAllergeni} disabled={busyFc==="all"}
                      style={{padding:"5px 12px",borderRadius:8,border:"1px solid var(--border)",background:"var(--card)",fontSize:12,fontWeight:700,cursor:"pointer"}}>
                      {busyFc==="all"?"Rilevo…":"Rileva dagli ingredienti"}
                    </button>
                  </div>
                  <div style={{display:"flex",flexWrap:"wrap",gap:6}}>
                    {["Glutine","Crostacei","Uova","Pesce","Arachidi","Soia","Latte","Frutta a guscio","Sedano","Senape","Sesamo","Anidride solforosa","Lupini","Molluschi"].map(a => {
                      const on = allergeni.includes(a);
                      return (
                        <button key={a} onClick={()=>setAllergeni(l=> on ? l.filter(x=>x!==a) : [...l,a])}
                          style={{padding:"4px 10px",borderRadius:14,fontSize:12,fontWeight:600,cursor:"pointer",
                            border:on?"none":"1px solid var(--border)",
                            background:on?"#b45309":"var(--card)",color:on?"#fff":"var(--text-2)"}}>
                          {a}
                        </button>
                      );
                    })}
                  </div>
                  {allSugg && (
                    <div style={{marginTop:8,fontSize:12,color:"var(--text-2)"}}>
                      Suggeriti dagli ingredienti: <b>{allSugg.join(", ") || "nessuno"}</b>
                      {allSugg.length>0 && <button onClick={()=>setAllergeni(allSugg)} style={{marginLeft:8,padding:"3px 10px",borderRadius:8,border:"none",background:"var(--primary)",color:"#fff",fontSize:11,fontWeight:700,cursor:"pointer"}}>Usa questi</button>}
                    </div>
                  )}
                  <button onClick={()=>salvaAllergeni(allergeni)}
                    style={{marginTop:8,padding:"6px 14px",borderRadius:8,border:"none",background:"#5b7a6b",color:"#fff",fontSize:12,fontWeight:700,cursor:"pointer"}}>
                    Salva allergeni
                  </button>
                </div>
                {/* Nutrizione */}
                <div>
                  <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:6}}>
                    <b style={{fontSize:13,color:"var(--text)"}}>Valori nutrizionali (per 100 g)</b>
                    <button onClick={calcolaNutri} disabled={busyFc==="nutri"}
                      style={{padding:"5px 12px",borderRadius:8,border:"none",background:"var(--primary)",color:"#fff",fontSize:12,fontWeight:700,cursor:"pointer"}}>
                      {busyFc==="nutri"?"Calcolo…":"Calcola"}
                    </button>
                  </div>
                  {nutri && (
                    <div style={{display:"flex",flexWrap:"wrap",gap:"4px 16px",fontSize:13}}>
                      {[["kcal","Energia"," kcal"],["grassi","Grassi"," g"],["saturi","di cui saturi"," g"],["carboidrati","Carboidrati"," g"],["zuccheri","di cui zuccheri"," g"],["proteine","Proteine"," g"],["sale","Sale"," g"]].map(([k,l,u])=>
                        nutri[k]!=null && nutri[k]!=="" ? <span key={k}>{l}: <b>{Number(nutri[k]).toLocaleString("it-IT")}{u}</b></span> : null
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Note */}
      <div style={{marginBottom:20}}>
        <label style={{fontSize:11,fontWeight:700,color:"var(--text-2)",textTransform:"uppercase",letterSpacing:".05em",display:"block",marginBottom:5}}>Note / Procedimento</label>
        <textarea value={form.note || ""} onChange={e=>setField("note",e.target.value)}
          rows={3} placeholder="Procedimento, note di cottura, avvertenze…"
          style={{width:"100%",padding:"10px 12px",border:"1.5px solid var(--border)",borderRadius:10,fontSize:13,fontFamily:"var(--font)",resize:"vertical",boxSizing:"border-box"}}/>
      </div>

      {/* Salva */}
      <button onClick={salva} disabled={saving}
        style={{width:"100%",padding:"14px",border:"none",borderRadius:12,
          background:"var(--primary-grad)",color:"#fff",fontFamily:"var(--font)",
          fontSize:15,fontWeight:800,cursor:"pointer",
          boxShadow:"0 4px 14px rgba(63,90,78,.3)",opacity:saving?.6:1}}>
        {saving ? "Salvo…" : ricetta?.id ? "💾 Aggiorna ricetta" : "✨ Crea ricetta"}
      </button>

      {/* Elimina: tolto dalla card (dove un cestino sempre in vista su ogni
          ricetta era rumore e rischio-tocco) e messo qui, in fondo, discreto. */}
      {ricetta?.id && onElimina && (
        <button onClick={() => onElimina(ricetta)}
          style={{width:"100%",marginTop:10,padding:"10px",border:"none",borderRadius:10,
            background:"transparent",color:"var(--danger)",fontFamily:"var(--font)",
            fontSize:13,fontWeight:700,cursor:"pointer"}}>
          🗑 Elimina questa ricetta
        </button>
      )}
      </div>
    </div>
    {chiediPinDosi && (
      <PinKeypad
        titolo="Sblocca le dosi"
        sottotitolo="Solo l'amministratore può correggere la ricetta ufficiale"
        soloAdmin
        onSuccess={() => { setChiediPinDosi(false); setDoseSbloccata(true); toast("Dosi sbloccate: ora puoi correggere la ricetta"); }}
        onCancel={() => setChiediPinDosi(false)}
      />
    )}
    </div>
  );
}

export default FormRicetta;
export { RigaIngrediente, METODI_CONS, UNITA_OPTIONS, REPARTI };
