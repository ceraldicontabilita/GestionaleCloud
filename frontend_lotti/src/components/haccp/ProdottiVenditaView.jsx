/**
 * ProdottiVenditaView — Vista centralizzata gestione prodotti, prezzi e margini.
 * Tab: Miei Prodotti | Acquaviva | SAIMA S.p.a. | Ricettari SAIMA | MEPA Alimentari
 * URL: #prodotti/{tab}
 * Deep-link: #prodotti/saima → tab SAIMA, #prodotti/acquaviva → Acquaviva
 */
import React, { useState, useEffect, useMemo, useCallback } from "react";
import axios from "axios";
import { Package, Plus, Search, RefreshCw, AlertTriangle, Calculator, Zap, DollarSign } from "lucide-react";
import { toast } from "sonner";
import BulkPrezziView from "./BulkPrezziView";
import CatalogoFornitoreView from "./CatalogoFornitoreView";
import CatalogoGenericoView from "./CatalogoGenericoView";
import SaimaRicettariView from "./SaimaRicettariView";
import ModalProdotto from "./prodotti/ModalProdotto";
import ProdottoCard from "./prodotti/ProdottoCard";
import SenzaPesoPanel from "./prodotti/SenzaPesoPanel";
import VistaTabellaPrezzi from "./prodotti/VistaTabellaPrezzi";
import { risolviCatalogoProdotti } from "../../router/prodottiRoute";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

/** Normalizza un prodotto di catalogo_forno (import da PDF o dal connettore
 * "incolla il link"). Il prezzo arriva dal backend SOLO se il prodotto è
 * stato davvero comprato in fattura XML (prezzo_listino + gia_acquistato,
 * stesso motore di Saima/MePA/Acquaviva): vedendo il prezzo si sa a colpo
 * d'occhio che quel prodotto è già stato acquistato. */
function mapItemCatalogoForno(p) {
  const prezzoFattura = p.gia_acquistato ? Number(p.prezzo_fattura || p.prezzo_listino || 0) : 0;
  return {
    id: `${p.fornitore}-${p.codice_articolo}`,
    nome: p.nome_completo || p.nome,
    foto_url: p.immagine_url || null,
    categoria: p.categoria || null,
    prezzo: prezzoFattura || p.prezzo_fornitore || p.prezzo || 0,
    prezzoFattura,
    prezzo_fattura: prezzoFattura,
    prezzo_listino: prezzoFattura,
    prezzoFornitore: p.prezzo_fornitore || 0,
    codice: p.codice_articolo,
    codice_articolo: p.codice_articolo,
    fornitore: p.fornitore,
    descrizione: p.descrizione || "",
    giaAcquistato: !!p.gia_acquistato,
    quantitaFattura: p.quantita_ultima_fattura || 0,
    grammi: p.grammi || "",
    pezziCartone: p.pezzi_cartone || "",
    inRicette: !!p.in_ricette,
    link_prodotto: p.link_prodotto || "",
    raw: p,
  };
}

/** Normalizza un prodotto Alfa (senza glutine, stesso schema di acquaviva_prodotti) */
function mapItemAlfa(p) {
  const prezzoFattura = p.gia_acquistato ? Number(p.prezzo_fattura || p.prezzo_listino || 0) : 0;
  return {
    id: p.id,
    nome: p.nome,
    foto_url: p.foto_url || null,
    categoria: p.categoria || null,
    prezzo: prezzoFattura || p.prezzo_fornitore || p.prezzo_vendita || 0,
    prezzoFattura,
    prezzo_fattura: prezzoFattura,
    prezzo_listino: prezzoFattura,
    prezzoFornitore: p.prezzo_fornitore || 0,
    codice: p.codice || null,
    codice_articolo: p.codice || null,
    fornitore: "alfa",
    descrizione: p.descrizione || "",
    giaAcquistato: !!p.gia_acquistato,
    quantitaFattura: p.quantita_ultima_fattura || 0,
    inRicette: !!p.in_ricette,
    grammi: p.peso_g || p.grammi || "",
    pezziCartone: p.pz_confezione || p.qty_cartone || "",
    link_prodotto: p.link_prodotto || "",
    raw: p,
  };
}

/** Aggiorna l'hash mantenendo i segmenti dopo il tab (es. categoria) */
function setHashTab(tab) {
  const segs = window.location.hash.replace("#", "").split("/");
  segs[0] = "prodotti";
  segs[1] = tab;
  // Reset segmenti successivi quando si cambia tab
  window.location.hash = segs.slice(0, 2).join("/");
}

export default function ProdottiVenditaView({ defaultTab = "acquaviva" }) {
  const [paginaTab, setPaginaTabState] = useState(() =>
    risolviCatalogoProdotti(window.location.hash, [], defaultTab)
  );
  const mostraCatalogo = paginaTab !== "miei";
  
  const setPaginaTab = (tab) => {
    setPaginaTabState(tab);
    setHashTab(tab);
  };
  const [vistaPrezzi, setVistaPrezzi] = useState(false);
  const [prodotti, setProdotti] = useState([]);
  const [ricette, setRicette] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filtroCategoria, setFiltroCategoria] = useState("");
  const [filtroFonte, setFiltroFonte] = useState("tutti");
  const [filtroVisibilita, setFiltroVisibilita] = useState("tutti");
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedProdotto, setSelectedProdotto] = useState(null);
  const [senzaPesoOpen, setSenzaPesoOpen] = useState(false);
  const [bulkPrezziOpen, setBulkPrezziOpen] = useState(false);
  const [stats, setStats] = useState({});
  const [senzaPesoCount, setSenzaPesoCount] = useState(0);
  const [normalizzando, setNormalizzando] = useState(false);
  const scrollPosRef = React.useRef(0);
  // Fonti aggiunte da "Cataloghi Fornitori (web)" (es. Sunset Cash): ogni fonte
  // sincronizzata con prodotti diventa una scheda catalogo DINAMICA qui,
  // senza toccare il codice (richiesta Enzo: "inserisco l'indirizzo e basta").
  const [fontiEsterne, setFontiEsterne] = useState([]);
  useEffect(() => {
    axios.get(`${API}/fonti-catalogo`)
      .then(r => setFontiEsterne((Array.isArray(r.data) ? r.data : []).filter(f => (f.prodotti_trovati || 0) > 0)))
      .catch(() => { /* non bloccante */ });
  }, []);

  // Sync tab ↔ URL hash (back/forward browser). Le fonti web diventano
  // risolvibili appena /fonti-catalogo le restituisce; prima venivano
  // erroneamente ricondotte ad Acquaviva.
  useEffect(() => {
    const dinamici = fontiEsterne.map(f => f.fornitore_key);
    const onHash = () => {
      const t = risolviCatalogoProdotti(window.location.hash, dinamici, defaultTab);
      setPaginaTabState(prev => prev !== t ? t : prev);
    };
    onHash();
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [defaultTab, fontiEsterne]);

  useEffect(() => {
    axios.get(`${API}/normalizzazione/prodotti-senza-peso?limit=1`)
      .then(r => setSenzaPesoCount(r.data.total || 0))
      .catch(() => {});
  }, []);

  const load = useCallback(async () => {
    scrollPosRef.current = window.scrollY;
    setLoading(true);
    try {
      const [pRes, rRes] = await Promise.all([
        axios.get(`${API}/prodotti-vendita/?solo_attivi=false`),
        axios.get(`${API}/ricette`)
      ]);
      const ps = pRes.data || [];
      setProdotti(ps);
      setRicette(rRes.data || []);
      const conPrezzo = ps.filter(p => (p.prezzo_vendita || 0) > 0);
      const marginiMedi = conPrezzo.length > 0
        ? conPrezzo.reduce((s, p) => s + (p.margine_pct || p.margine_percentuale || 0), 0) / conPrezzo.length : 0;
      setStats({
        totale: ps.length,
        conPrezzo: conPrezzo.length,
        stagionali: ps.filter(p => p.stagionale).length,
        inattivi: ps.filter(p => !p.attivo).length,
        margineM: Math.round(marginiMedi * 10) / 10
      });
    } catch { toast.error("Errore caricamento prodotti"); }
    setLoading(false);
    requestAnimationFrame(() => window.scrollTo(0, scrollPosRef.current));
  }, []);

  useEffect(() => { load(); }, [load]);

  const syncFatture = async () => {
    try {
      setLoading(true);
      const r = await axios.post(`${API}/prodotti-vendita/sync-acquaviva`);
      toast.success(`Sync completato: ${r.data.creati} nuovi, ${r.data.aggiornati} aggiornati`);
      await load();
    } catch { toast.error("Errore sincronizzazione"); }
  };

  const syncCosti = async () => {
    try {
      setLoading(true);
      const r = await axios.post(`${API}/prodotti-vendita/sync-da-ricette`);
      toast.success(`Costi aggiornati: ${r.data.prodotti_aggiornati} prodotti`);
      await load();
    } catch { toast.error("Errore sync costi"); }
  };

  const normalizza = async () => {
    setNormalizzando(true);
    try {
      const r = await axios.post(`${API}/normalizzazione/processa-nuovi-prodotti?limit=50`);
      toast.success(`Normalizzati: ${r.data.processati} (${r.data.via_ai} via AI, ${r.data.via_sinonimi_statici} via dizionario)`);
    } catch { toast.error("Errore normalizzazione"); }
    setNormalizzando(false);
  };

  const handleSave = async (payload) => {
    try {
      if (selectedProdotto?.id) {
        await axios.put(`${API}/prodotti-vendita/${selectedProdotto.id}`, payload);
        toast.success("Prodotto aggiornato");
      } else {
        await axios.post(`${API}/prodotti-vendita/`, payload);
        toast.success("Prodotto creato");
      }
      setModalOpen(false);
      await load();
    } catch { toast.error("Errore salvataggio"); }
  };

  const handleDelete = async (id) => {
    try {
      await axios.delete(`${API}/prodotti-vendita/${id}`);
      toast.success("Prodotto eliminato");
      setModalOpen(false);
      await load();
    } catch { toast.error("Errore eliminazione"); }
  };

  const prodottiFiltrati = useMemo(() => {
    if (["saima", "mepa", "saima_ricettari", "pasticcere", "tremarie", "alfa", "sammontana", "bindi"].includes(paginaTab)
        || fontiEsterne.some(f => f.fornitore_key === paginaTab)) return [];
    let ps = prodotti;
    if (paginaTab === "miei") ps = ps.filter(p => p.fonte !== "acquaviva");
    if (search) ps = ps.filter(p => p.nome?.toLowerCase().includes(search.toLowerCase()) || p.categoria?.toLowerCase().includes(search.toLowerCase()) || p.descrizione_fattura?.toLowerCase().includes(search.toLowerCase()));
    if (filtroCategoria) ps = ps.filter(p => (p.categoria || "").includes(filtroCategoria));
    if (filtroFonte !== "tutti" && paginaTab === "miei") ps = ps.filter(p => p.fonte === filtroFonte);
    if (filtroVisibilita === "stagionale") ps = ps.filter(p => p.stagionale);
    if (filtroVisibilita === "inattivi") ps = ps.filter(p => !p.attivo);
    if (filtroVisibilita === "no_tablet") ps = ps.filter(p => !p.visibile_tablet);
    return ps;
  }, [prodotti, search, filtroCategoria, filtroFonte, filtroVisibilita, paginaTab, fontiEsterne]);

  const prodottiPerCategoria = useMemo(() => {
    const groups = {};
    prodottiFiltrati.forEach(p => {
      const cat = p.categoria || "Senza categoria";
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(p);
    });
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }, [prodottiFiltrati]);

  const categorie = useMemo(() => [...new Set(prodotti.map(p => p.categoria?.split(" > ")[0]).filter(Boolean))], [prodotti]);

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      {/* Header */}
      <div className="mb-4 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">
            {mostraCatalogo ? "Cataloghi fornitori" : "Prodotti in vendita"}
          </h1>
          <p className="text-gray-500 text-sm mt-0.5">
            {mostraCatalogo
              ? "Acquaviva, SAIMA, MEPA e gli altri cataloghi collegati agli acquisti"
              : "Gestione centralizzata prodotti, prezzi e margini"}
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap justify-end">
          <button onClick={() => setBulkPrezziOpen(true)} data-testid="btn-bulk-prezzi"
            className="flex items-center gap-2 px-4 py-2 bg-[#f2f6f3] border border-[#cfdfd5] text-[#5b7a6b] rounded-xl text-sm hover:bg-[#dce8e0] transition-all font-medium">
            <DollarSign size={14} /> Imposta Prezzi ({stats.totale - stats.conPrezzo || 0})
          </button>
          <button onClick={() => setSenzaPesoOpen(true)}
            className="flex items-center gap-2 px-4 py-2 bg-amber-50 border border-amber-200 text-amber-700 rounded-xl text-sm hover:bg-amber-100 transition-all">
            <AlertTriangle size={14} /> Senza Peso ({senzaPesoCount})
          </button>
          <button onClick={normalizza} disabled={normalizzando}
            className="flex items-center gap-2 px-4 py-2 bg-[#f2f6f3] border border-[#cfdfd5] text-[#5b7a6b] rounded-xl text-sm hover:bg-[#dce8e0] transition-all">
            <Zap size={14} className={normalizzando ? "animate-pulse" : ""} />
            {normalizzando ? "Normalizzando..." : "Normalizza Nomi AI"}
          </button>
          <button onClick={syncCosti}
            className="flex items-center gap-2 px-4 py-2 bg-green-50 border border-green-200 text-green-700 rounded-xl text-sm hover:bg-green-100 transition-all">
            <Calculator size={14} /> Sync Costi
          </button>
          <button onClick={syncFatture}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 border border-gray-200 text-gray-700 rounded-xl text-sm hover:bg-gray-200 transition-all">
            <RefreshCw size={14} /> Sync Fatture
          </button>
          {paginaTab === "miei" && (
            <button data-testid="btn-nuovo-prodotto" onClick={() => { setSelectedProdotto(null); setModalOpen(true); }}
              className="flex items-center gap-2 px-4 py-2 bg-[#5b7a6b] text-white rounded-xl text-sm font-medium hover:bg-[#4d6a5c] transition-all shadow-sm">
              <Plus size={14} /> Nuovo Prodotto
            </button>
          )}
        </div>
      </div>

      {/* Tab pagina */}
      <div role="tablist" aria-label="Prodotti e cataloghi fornitori" className="flex gap-1 bg-gray-100 rounded-xl p-1 mb-5 w-fit flex-wrap">
        {[
          { id: "miei", label: "Miei Prodotti", count: prodotti.filter(p => p.fonte !== "acquaviva").length, color: "violet" },
          { id: "acquaviva", label: "Acquaviva catalogo", count: null, color: "blue" },
          { id: "saima", label: "SAIMA S.p.a.", count: null, color: "blue" },
          { id: "saima_ricettari", label: "Ricettari SAIMA", count: null, color: "blue" },
          { id: "mepa", label: "MEPA Alimentari", count: null, color: "green" },
          { id: "pasticcere", label: "Il Pasticcere", count: null, color: "amber" },
          { id: "tremarie", label: "Tre Marie", count: null, color: "rose" },
          { id: "alfa", label: "Alfa (senza glutine)", count: null, color: "amber" },
          { id: "sammontana", label: "Sammontana", count: null, color: "orange" },
          { id: "bindi", label: "Bindi", count: null, color: "yellow" },
          // schede dinamiche: una per ogni fonte web sincronizzata con prodotti
          ...fontiEsterne.map(f => ({ id: f.fornitore_key, label: f.nome, count: f.prodotti_trovati, color: "green" })),
        ].map(t => (
          <button key={t.id} role="tab" aria-selected={paginaTab === t.id} data-testid={`tab-${t.id.replace("_", "-")}`} onClick={() => setPaginaTab(t.id)}
            className={`px-5 py-2 rounded-lg text-sm font-medium transition-all ${paginaTab === t.id ? `bg-white text-${t.color}-700 shadow-sm` : "text-gray-500 hover:text-gray-700"}`}>
            {t.label}
            {t.count !== null && <span className={`ml-2 text-xs bg-${t.color}-100 text-${t.color}-600 px-1.5 py-0.5 rounded-full`}>{t.count}</span>}
          </button>
        ))}
      </div>

      {/* Catalogo esterno (SAIMA / MEPA) */}
      {paginaTab === "acquaviva" && <CatalogoFornitoreView fornitore="acquaviva" nome="Dolciaria Acquaviva" />}
      {paginaTab === "saima" && <CatalogoFornitoreView fornitore="saima" nome="SAIMA S.p.a." />}
      {paginaTab === "saima_ricettari" && <SaimaRicettariView />}
      {paginaTab === "mepa" && <CatalogoFornitoreView fornitore="mepa" nome="MEPA Alimentari" />}

      {/* Catalogo esterno (Il Pasticcere / Tre Marie / Alfa / Sammontana) — stesso asterisco preferito colazione + carrello ordini di SAIMA/MEPA */}
      {paginaTab === "pasticcere" && (
        <CatalogoGenericoView titolo="Il Pasticcere" sourceKey="pasticcere"
          fetchUrl="/catalogo-forno/prodotti?fornitore=pasticcere" mapItem={mapItemCatalogoForno}
          emojiVuoto="📦" messaggioVuoto="Nessun catalogo Il Pasticcere ancora importato — premi 'Importa dal catalogo PDF' qui sopra."
          coloreAccento="amber"
          importaPrecaricatoUrl="/catalogo-forno/importa-precaricato?fornitore=pasticcere"
          importaPrecaricatoLabel="Importa dal catalogo PDF 2026" />
      )}
      {paginaTab === "tremarie" && (
        <CatalogoGenericoView titolo="Tre Marie" sourceKey="tremarie"
          fetchUrl="/catalogo-forno/prodotti?fornitore=tremarie" mapItem={mapItemCatalogoForno}
          emojiVuoto="📦" messaggioVuoto="Nessun catalogo Tre Marie ancora importato — premi 'Importa dal catalogo PDF' qui sopra."
          coloreAccento="rose"
          importaPrecaricatoUrl="/catalogo-forno/sincronizza-ufficiale?fornitore=tremarie"
          importaPrecaricatoLabel="Aggiorna foto e catalogo ufficiale 2026" />
      )}
      {paginaTab === "alfa" && (
        <CatalogoGenericoView titolo="Alfa (senza glutine)" sourceKey="alpha"
          fetchUrl="/acquaviva/prodotti/senza-glutine" mapItem={mapItemAlfa}
          emojiVuoto="🌾" messaggioVuoto="Nessun prodotto senza glutine trovato."
          coloreAccento="amber" />
      )}
      {paginaTab === "sammontana" && (
        <CatalogoGenericoView titolo="Sammontana" sourceKey="sammontana"
          fetchUrl="/catalogo-forno/prodotti?fornitore=sammontana" mapItem={mapItemCatalogoForno}
          emojiVuoto="🍦" messaggioVuoto="Nessun catalogo Sammontana ancora sincronizzato — vai in Impostazioni → Cataloghi fornitori (web) e premi Sincronizza."
          coloreAccento="orange"
          importaPrecaricatoUrl="/catalogo-forno/sincronizza-ufficiale?fornitore=sammontana"
          importaPrecaricatoLabel="Aggiorna foto e catalogo ufficiale 2026" />
      )}
      {paginaTab === "bindi" && (
        <CatalogoGenericoView titolo="Bindi" sourceKey="bindi"
          fetchUrl="/catalogo-forno/prodotti?fornitore=bindi" mapItem={mapItemCatalogoForno}
          emojiVuoto="🍰" messaggioVuoto="Nessun catalogo Bindi ancora importato — premi 'Importa dal catalogo PDF' qui sopra."
          coloreAccento="yellow"
          importaPrecaricatoUrl="/catalogo-forno/importa-precaricato?fornitore=bindi"
          importaPrecaricatoLabel="Importa dai cataloghi PDF 2022-2026" />
      )}
      {/* Cataloghi delle fonti web aggiunte da Enzo (Cataloghi Fornitori (web)) */}
      {fontiEsterne.filter(f => f.fornitore_key === paginaTab).map(f => (
        <CatalogoGenericoView key={f.fornitore_key} titolo={f.nome} sourceKey={f.fornitore_key}
          fetchUrl={`/catalogo-forno/prodotti?fornitore=${encodeURIComponent(f.fornitore_key)}`}
          mapItem={mapItemCatalogoForno}
          emojiVuoto="📦"
          messaggioVuoto={`Nessun prodotto ancora sincronizzato per ${f.nome} — vai in Cataloghi Fornitori (web) e premi Sincronizza.`}
          coloreAccento="green" />
      ))}

      {/* Contenuto Miei Prodotti / Acquaviva */}
      {paginaTab === "miei" && (
        <>
          {/* Stats bar */}
          <div className="grid grid-cols-5 gap-4 mb-6">
            {[
              { label: "Totale Prodotti", value: stats.totale || 0, color: "text-gray-700" },
              { label: "Con Prezzo", value: stats.conPrezzo || 0, color: "text-[#5b7a6b]" },
              { label: "Margine Medio", value: `${stats.margineM || 0}%`, color: "text-green-600" },
              { label: "Stagionali", value: stats.stagionali || 0, color: "text-amber-600" },
              { label: "Inattivi", value: stats.inattivi || 0, color: "text-gray-400" }
            ].map((s, i) => (
              <div key={i} className="bg-white rounded-xl border border-gray-100 p-4 text-center">
                <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
                <p className="text-xs text-gray-400 mt-0.5">{s.label}</p>
              </div>
            ))}
          </div>

          {/* Filtri */}
          <div className="bg-white rounded-xl border border-gray-100 p-4 mb-5 flex flex-wrap gap-3 items-center">
            <div className="relative flex-1 min-w-[200px]">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input data-testid="search-prodotti"
                className="w-full pl-8 pr-3 py-2 border border-gray-200 rounded-lg text-sm"
                placeholder="Cerca prodotto..." value={search} onChange={e => setSearch(e.target.value)} />
            </div>
            {paginaTab === "miei" && (
              <select className="border border-gray-200 rounded-lg px-3 py-2 text-sm" value={filtroFonte} onChange={e => setFiltroFonte(e.target.value)}>
                <option value="tutti">Tutti (interno + esterno)</option>
                <option value="interno">Solo Nostri</option>
                <option value="esterno">Solo Esterni</option>
              </select>
            )}
            <select className="border border-gray-200 rounded-lg px-3 py-2 text-sm" value={filtroCategoria} onChange={e => setFiltroCategoria(e.target.value)}>
              <option value="">Tutte le categorie</option>
              {categorie.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            <select className="border border-gray-200 rounded-lg px-3 py-2 text-sm" value={filtroVisibilita} onChange={e => setFiltroVisibilita(e.target.value)}>
              <option value="tutti">Tutti gli stati</option>
              <option value="stagionale">Solo stagionali</option>
              <option value="inattivi">Solo inattivi</option>
              <option value="no_tablet">Nascosti da tablet</option>
            </select>
            <p className="text-xs text-gray-400 ml-auto">{prodottiFiltrati.length} prodotti</p>
            <button onClick={() => setVistaPrezzi(v => !v)} data-testid="toggle-vista-prezzi"
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium border transition-all ${vistaPrezzi ? "bg-green-600 text-white border-green-600" : "border-gray-200 text-gray-600 hover:bg-gray-50"}`}>
              <DollarSign size={14} /> {vistaPrezzi ? "Vista griglia" : "Gestisci Prezzi"}
            </button>
          </div>

          {vistaPrezzi && <VistaTabellaPrezzi prodotti={prodottiFiltrati} onAggiornato={load} />}

          {!vistaPrezzi && loading ? (
            <div className="text-center py-20 text-gray-400">Caricamento...</div>
          ) : prodottiFiltrati.length === 0 ? (
            <div className="text-center py-20">
              <Package size={40} className="mx-auto text-gray-200 mb-3" />
              <p className="text-gray-400">Nessun prodotto trovato</p>
              <button onClick={() => { setSelectedProdotto(null); setModalOpen(true); }}
                className="mt-4 px-6 py-2 bg-[#5b7a6b] text-white rounded-lg text-sm">+ Crea il primo prodotto</button>
            </div>
          ) : (
            <div className="space-y-6">
              {prodottiPerCategoria.map(([cat, ps]) => (
                <div key={cat}>
                  <div className="flex items-center gap-2 mb-3">
                    <h2 className="text-sm font-semibold text-gray-600">{cat}</h2>
                    <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">{ps.length}</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                    {ps.map(p => (
                      <ProdottoCard key={p.id} prodotto={p}
                        onClick={(prod) => { setSelectedProdotto(prod); setModalOpen(true); }}
                        onPrezzoSalvato={load} />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {modalOpen && (
            <ModalProdotto prodotto={selectedProdotto} ricette={ricette}
              onSave={handleSave} onDelete={handleDelete}
              onClose={() => setModalOpen(false)} isNew={!selectedProdotto?.id} />
          )}

          <SenzaPesoPanel open={senzaPesoOpen} onClose={() => setSenzaPesoOpen(false)} />

          {bulkPrezziOpen && <BulkPrezziView onClose={() => { setBulkPrezziOpen(false); load(); }} />}
        </>
      )}
    </div>
  );
}
