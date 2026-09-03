import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { format } from "date-fns";
import { it } from "date-fns/locale";
import {
  AlertTriangle,
  BookOpen,
  Building2,
  ChefHat,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  FileText,
  Layers,
  Package,
  RefreshCw,
  Settings,
  ShoppingCart,
  Store,
  Truck,
  IceCreamBowl,
  Wallet,
  Coffee,
  TrendingDown,
  Thermometer,
  Network,
  ShieldCheck,
  Fish,
} from "lucide-react";
import { API } from "../../utils/constants";
import { isAdmin } from "../../auth";
import StatoSistemaWidget from "./StatoSistemaWidget";
import HACCPHomeCard from "./HACCPHomeCard";
import PesceTraceabilityCard from "./PesceTraceabilityCard";

const fmt = (n) => (n === undefined || n === null ? "-" : n);

const actionTones = {
  neutral: {
    card: "bg-white border-stone-200 hover:border-stone-300",
    icon: "bg-stone-100 text-stone-700",
    badge: "bg-stone-100 text-stone-700",
  },
  amber: {
    card: "bg-amber-50 border-amber-200 hover:border-amber-300",
    icon: "bg-amber-100 text-amber-700",
    badge: "bg-white text-amber-700",
  },
  blue: {
    card: "bg-amber-50 border-amber-200 hover:border-amber-300",
    icon: "bg-amber-100 text-amber-700",
    badge: "bg-white text-amber-700",
  },
  green: {
    card: "bg-emerald-50 border-emerald-200 hover:border-emerald-300",
    icon: "bg-emerald-100 text-emerald-700",
    badge: "bg-white text-emerald-700",
  },
  red: {
    card: "bg-red-50 border-red-200 hover:border-red-300",
    icon: "bg-red-100 text-red-700",
    badge: "bg-white text-red-700",
  },
  violet: {
    card: "bg-[#f2f6f3] border-[#cfdfd5] hover:border-[#b8d0c2]",
    icon: "bg-[#e8efe9] text-[#3f5a4e]",
    badge: "bg-white text-[#3f5a4e]",
  },
  // Tono VIVIDI per le card reparto (stessi colori del tablet), testo bianco.
  pinkV:   { vivid: true, card: "bg-gradient-to-br from-pink-400 to-pink-600 border-pink-600",     icon: "bg-white/25 text-white", badge: "bg-white/25 text-white" },
  orangeV: { vivid: true, card: "bg-gradient-to-br from-orange-400 to-orange-600 border-orange-600", icon: "bg-white/25 text-white", badge: "bg-white/25 text-white" },
  coffeeV: { vivid: true, card: "bg-gradient-to-br from-amber-700 to-amber-900 border-amber-900",   icon: "bg-white/25 text-white", badge: "bg-white/25 text-white" },
  cyanV:   { vivid: true, card: "bg-gradient-to-br from-[#8a6f47] to-[#6f583a] border-[#6f583a]",       icon: "bg-white/25 text-white", badge: "bg-white/25 text-white" },
  greenV:  { vivid: true, card: "bg-gradient-to-br from-emerald-400 to-emerald-600 border-emerald-600", icon: "bg-white/25 text-white", badge: "bg-white/25 text-white" },
  violetV: { vivid: true, card: "bg-gradient-to-br from-[#6f9180] to-[#5b7a6b] border-[#5b7a6b]", icon: "bg-white/25 text-white", badge: "bg-white/25 text-white" },
  greenLightV: { vivid: true, card: "bg-gradient-to-br from-green-300 to-green-500 border-green-500", icon: "bg-white/25 text-white", badge: "bg-white/25 text-white" },
  // ex "slate" (blu-grigio freddo, fuori palette): rimappato su sabbia scura
  slateV:  { vivid: true, card: "bg-gradient-to-br from-[#6f583a] to-[#4a3f33] border-[#4a3f33]", icon: "bg-white/25 text-white", badge: "bg-white/25 text-white" },
};

function SectionTitle({ title, subtitle }) {
  return (
    <div className="mb-3 flex items-end justify-between gap-3">
      <div className="min-w-0">
        <h2 className="m-0 text-lg font-black text-stone-900">{title}</h2>
        {subtitle ? <p className="m-0 mt-0.5 text-sm font-medium text-stone-500">{subtitle}</p> : null}
      </div>
    </div>
  );
}

function ActionCard({ icon: Icon, title, subtitle, badge, tone = "neutral", onClick }) {
  const toneClasses = actionTones[tone] || actionTones.neutral;

  return (
    <button
      type="button"
      onClick={onClick}
      className={`group flex min-h-[132px] flex-col justify-between rounded-lg border p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md active:translate-y-0 ${toneClasses.card}`}
    >
      <div className="flex w-full items-start justify-between gap-3">
        <span className={`grid h-10 w-10 place-items-center rounded-lg ${toneClasses.icon}`}>
          <Icon size={21} strokeWidth={2.3} />
        </span>
        {badge ? <span className={`rounded-md px-2 py-1 text-xs font-black ${toneClasses.badge}`}>{badge}</span> : null}
      </div>
      <div className="mt-4">
        <h3 className={`m-0 text-base font-black leading-tight ${toneClasses.vivid ? "text-white" : "text-stone-900"}`}>{title}</h3>
        <p className={`m-0 mt-1 text-sm font-medium leading-snug ${toneClasses.vivid ? "text-white/85" : "text-stone-500"}`}>{subtitle}</p>
      </div>
    </button>
  );
}


function QuickLink({ icon: Icon, title, subtitle, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-3 rounded-lg border border-stone-200 bg-white p-3 text-left shadow-sm transition hover:border-stone-300 hover:bg-stone-50 active:scale-[.99]"
    >
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-stone-100 text-stone-700"><Icon size={18} /></span>
      <span className="min-w-0">
        <span className="block text-sm font-black text-stone-900">{title}</span>
        <span className="block truncate text-xs font-semibold text-stone-500">{subtitle}</span>
      </span>
    </button>
  );
}


// ── Cruscotto: KPI grandi + grafico temperature ────────────────────────────
function KpiBig({ label, value, sub, color, icon: Icon, onClick }) {
  return (
    <button onClick={onClick} type="button"
      className="group flex flex-col items-start gap-1 rounded-2xl border bg-white p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
      style={{ borderColor: "#e6e0d4" }}>
      <div className="flex w-full items-center justify-between">
        <span className="grid h-9 w-9 place-items-center rounded-xl" style={{ background: `${color}1a`, color }}>
          <Icon size={18} />
        </span>
      </div>
      <div className="mt-1 text-2xl font-black tabular-nums" style={{ color: "#1f2937" }}>{value}</div>
      <div className="text-xs font-bold uppercase tracking-wide" style={{ color: "#9a917f" }}>{label}</div>
      {sub ? <div className="text-xs font-semibold" style={{ color }}>{sub}</div> : null}
    </button>
  );
}

export default function DashboardView({ stats = {}, onRefresh, onNavigate }) {
  const [loading, setLoading] = useState(true);
  const [pesceOpen, setPesceOpen] = useState(false);
  const [ufficioOpen, setUfficioOpen] = useState(false);
  const [lottiScadenza, setLottiScadenza] = useState([]);
  const [produzioniOggi, setProduzioniOggi] = useState([]);
  const [venditeOggi, setVenditeOggi] = useState([]);
  const [ordiniBozza, setOrdiniBozza] = useState(0);
  const [ordiniInviati, setOrdiniInviati] = useState(0);
  const [cruscotto, setCruscotto] = useState(null);
  const [sommarioSupervisore, setSommarioSupervisore] = useState(null);
  const [produzioneDaDecidere, setProduzioneDaDecidere] = useState(0);

  const navigate = useCallback((tab) => {
    if (tab?.includes("/")) {
      window.location.hash = tab;
      return;
    }
    onNavigate?.(tab);
  }, [onNavigate]);

  const caricaDati = useCallback(async () => {
    setLoading(true);
    try {
      const domani = new Date(); domani.setDate(domani.getDate() + 1);
      const [scadenze, produzioni, vendite, ordini, ordiniInv, crusc, sommario, prodConsigliata] = await Promise.allSettled([
        axios.get(`${API}/supervisor/lotti-in-scadenza?giorni=7&limit=10`, { timeout: 15000 }),
        axios.get(`${API}/produzioni/per-oggi`, { timeout: 15000 }),
        axios.get(`${API}/vendita-banco/oggi`, { timeout: 15000 }),
        axios.get(`${API}/ordini-fornitori?stato=bozza&limit=100`, { timeout: 15000 }),
        axios.get(`${API}/ordini-fornitori?stato=inviato&limit=100`, { timeout: 15000 }),
        axios.get(`${API}/supervisor/cruscotto`, { timeout: 45000 }),
        axios.get(`${API}/supervisor/sommario`, { timeout: 15000 }),
        axios.get(`${API}/produzione-consigliata`, { params: { data: domani.toISOString().slice(0, 10) }, timeout: 15000 }),
      ]);
      if (crusc.status === "fulfilled") setCruscotto(crusc.value.data || null);
      if (scadenze.status === "fulfilled") setLottiScadenza(scadenze.value.data?.lotti || []);
      if (produzioni.status === "fulfilled") setProduzioniOggi(produzioni.value.data || []);
      if (vendite.status === "fulfilled") setVenditeOggi(vendite.value.data || []);
      if (ordini.status === "fulfilled") setOrdiniBozza((ordini.value.data || []).length);
      if (ordiniInv.status === "fulfilled") setOrdiniInviati((ordiniInv.value.data || []).length);
      if (sommario.status === "fulfilled") setSommarioSupervisore(sommario.value.data || null);
      if (prodConsigliata.status === "fulfilled") {
        const suggeriti = prodConsigliata.value.data?.suggerimenti || [];
        setProduzioneDaDecidere(suggeriti.filter((s) => !s.decisione).length);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { caricaDati(); }, [caricaDati]);

  const riepilogo = useMemo(() => {
    const scadenzeUrgenti = lottiScadenza.filter((l) => (l.giorni_alla_scadenza ?? 99) <= 2).length;
    const pezziProdotti = produzioniOggi.reduce((s, p) => s + (p.pezzi || p.quantita || 0), 0);
    const bancoAperto = venditeOggi.filter((v) => v.stato === "aperto").length;
    return { scadenzeUrgenti, pezziProdotti, bancoAperto };
  }, [lottiScadenza, produzioniOggi, venditeOggi]);

  const [refreshing, setRefreshing] = useState(false);
  const aggiorna = async () => {
    if (refreshing) return;
    setRefreshing(true);
    try {
      await Promise.allSettled([onRefresh?.(), caricaDati()]);
      toast.success("Dati aggiornati", { duration: 1500 });
    } finally {
      setRefreshing(false);
    }
  };


  return (
    <div className="dashboard-home space-y-5">
      <div className="flex flex-col gap-3 border-b border-stone-200 pb-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <p className="m-0 text-xs font-black uppercase text-stone-400">Dashboard</p>
          <h1 className="m-0 mt-1 text-3xl font-black tracking-tight text-stone-900">Home operativa</h1>
          <p className="m-0 mt-1 text-sm font-semibold text-stone-500">
            {format(new Date(), "EEEE d MMMM yyyy", { locale: it })} · accessi rapidi, priorità e controlli in un unico punto.
          </p>
        </div>
        <button
          type="button"
          onClick={aggiorna}
          disabled={refreshing}
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-stone-200 bg-white px-4 py-3 text-sm font-black text-stone-700 shadow-sm hover:bg-stone-50 disabled:opacity-60"
        >
          <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} /> {refreshing ? "Aggiorno…" : "Aggiorna"}
        </button>
      </div>

      {/* ── COSA DEVO FARE OGGI: priorità consolidate in un unico posto ── */}
      {(() => {
        const voci = [];
        if (sommarioSupervisore?.critici > 0) {
          voci.push({ label: `${sommarioSupervisore.critici} alert critici HACCP (Supervisore, in alto a destra)`, onClick: null, tono: "#d35f4e" });
        }
        if (cruscotto?.kpi?.lotti_scaduti > 0) {
          voci.push({ label: `${cruscotto.kpi.lotti_scaduti} lotti SCADUTI da controllare/smaltire`, onClick: () => navigate("lotti"), tono: "#d35f4e" });
        }
        if (riepilogo.scadenzeUrgenti > 0) {
          voci.push({ label: `${riepilogo.scadenzeUrgenti} lotti da usare con urgenza`, onClick: () => navigate("cosa_usare_oggi"), tono: "#d35f4e" });
        }
        if (produzioniOggi.length > 0) {
          voci.push({ label: `${produzioniOggi.length} produzioni previste per oggi`, onClick: () => navigate("storico_produzioni"), tono: "#5b7a6b" });
        }
        if (ordiniInviati > 0) {
          voci.push({ label: `${ordiniInviati} ordini inviati: merce da ricevere e controllare`, onClick: () => navigate("ricezione_merce"), tono: "#8a6f47" });
        }
        if (cruscotto?.kpi?.sotto_scorta > 0) {
          voci.push({ label: `${cruscotto.kpi.sotto_scorta} prodotti sotto scorta`, onClick: () => navigate("backoffice"), tono: "#c4894a" });
        }
        if (ordiniBozza > 0) {
          voci.push({ label: `${ordiniBozza} ordini in bozza da convalidare`, onClick: () => navigate("ordini"), tono: "#8a6f47" });
        }
        if (produzioneDaDecidere > 0) {
          voci.push({ label: `${produzioneDaDecidere} suggerimenti di produzione da decidere per domani`, onClick: () => navigate("produzione_consigliata"), tono: "#c4894a" });
        }
        if (voci.length === 0) {
          return (
            <section className="rounded-2xl border-2 border-emerald-200 bg-emerald-50 p-4 flex items-center gap-3">
              <ShieldCheck className="text-emerald-600 shrink-0" size={22} />
              <div>
                <p className="m-0 font-black text-emerald-800">Cosa devo fare oggi: tutto in regola</p>
                <p className="m-0 text-sm text-emerald-700">Nessuna priorità urgente al momento.</p>
              </div>
            </section>
          );
        }
        return (
          <section className="rounded-2xl border-2 border-amber-200 bg-amber-50 p-4">
            <p className="m-0 font-black text-amber-900 mb-2">Cosa devo fare oggi</p>
            <div className="space-y-1.5">
              {voci.map((v, i) => (
                <button key={i} onClick={v.onClick} disabled={!v.onClick}
                  className="w-full text-left flex items-center gap-2 bg-white rounded-xl px-3 py-2 text-sm font-semibold disabled:cursor-default"
                  style={{ color: v.tono }}>
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ background: v.tono }} />
                  {v.label}
                </button>
              ))}
            </div>
          </section>
        );
      })()}

      <section>
        <div>
          <SectionTitle title="Operazioni di oggi" subtitle="Flussi principali per laboratorio, banco e magazzino." />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <ActionCard icon={ChefHat} title="Pasticceria" subtitle="Produci ricette, registra lotti e stampa etichette." badge="Tablet" tone="orangeV" onClick={() => navigate("tablet/pasticceria")} />
            <ActionCard icon={ChefHat} title="Rosticceria" subtitle="Produzione salato, cucina e tavola calda." badge="Tablet" tone="greenLightV" onClick={() => navigate("tablet/rosticceria")} />
            <ActionCard icon={Coffee} title="Bar" subtitle="Caffetteria e bevande: produci e registra lotti." badge="Tablet" tone="coffeeV" onClick={() => navigate("tablet/bar")} />
            <ActionCard icon={Store} title="Banco vendita" subtitle="Apri il banco, registra vendita e scarica lotti." badge={riepilogo.bancoAperto ? `${riepilogo.bancoAperto} aperto` : "Tablet"} tone="cyanV" onClick={() => navigate("tablet/vendita")} />
            <ActionCard icon={Package} title="Magazzino" subtitle="Scarichi rapidi, giacenze e movimenti da PIN." badge="PIN" tone="slateV" onClick={() => navigate("tablet/magazzino")} />
            <ActionCard icon={IceCreamBowl} title="Gelati" subtitle="Calcolo ricette, produzioni con lotto e invenduti." badge="Lab" tone="violetV" onClick={() => navigate("gelati")} />
            <ActionCard icon={AlertTriangle} title="Cosa usare oggi" subtitle="Lotti per urgenza scadenza e valore economico, con azioni rapide." badge={riepilogo.scadenzeUrgenti ? `${riepilogo.scadenzeUrgenti} urgenti` : "OK"} tone={riepilogo.scadenzeUrgenti ? "red" : "amber"} onClick={() => navigate("cosa_usare_oggi")} />
            <ActionCard icon={ChefHat} title="Produzione consigliata" subtitle="Cosa produrre domani, in base a storico, invenduto e festività." badge="Nuovo" tone="amber" onClick={() => navigate("produzione_consigliata")} />
            <ActionCard icon={Layers} title="Lotti" subtitle="Scadenze, tracciabilità e registro lotti." badge={lottiScadenza.length ? `${lottiScadenza.length} scadenze` : "OK"} tone={lottiScadenza.length ? "red" : "neutral"} onClick={() => navigate("lotti")} />
          </div>
        </div>
      </section>

      <section>
        <SectionTitle
          title="Cataloghi fornitori"
          subtitle="Accesso diretto ai cataloghi completi collegati agli acquisti."
        />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <ActionCard icon={Package} title="Acquaviva" subtitle="Catalogo Dolciaria Acquaviva e prodotti acquistati." badge="Catalogo" tone="amber" onClick={() => navigate("prodotti/acquaviva")} />
          <ActionCard icon={Building2} title="SAIMA" subtitle="Categorie, prodotti e ricettari SAIMA." badge="Catalogo" tone="green" onClick={() => navigate("prodotti/saima")} />
          <ActionCard icon={ShoppingCart} title="MEPA" subtitle="Catalogo prodotti MEPA Alimentari." badge="Catalogo" tone="neutral" onClick={() => navigate("prodotti/mepa")} />
        </div>
      </section>

      {/* ── CRUSCOTTO: colpo d'occhio del mattino ──────────────────────── */}
      {cruscotto?.kpi && (
        <section className="space-y-3">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <KpiBig label="Spesa 30 giorni" value={`€${Math.round(cruscotto.kpi.spesa_mese).toLocaleString("it-IT")}`}
              sub={`${cruscotto.kpi.fatture_mese} fatture`} color="#5b7a6b" icon={Wallet} onClick={() => navigate("fatture")} />
            <KpiBig label="Sotto scorta" value={cruscotto.kpi.sotto_scorta}
              sub={cruscotto.kpi.esauriti ? `${cruscotto.kpi.esauriti} esauriti` : "tutto ok"} color={cruscotto.kpi.sotto_scorta ? "#c4894a" : "#3d8168"} icon={TrendingDown} onClick={() => navigate("backoffice")} />
            <KpiBig label="Lotti scaduti" value={cruscotto.kpi.lotti_scaduti}
              sub={cruscotto.kpi.lotti_in_scadenza ? `${cruscotto.kpi.lotti_in_scadenza} in scadenza` : "nessuno"} color={cruscotto.kpi.lotti_scaduti ? "#d35f4e" : "#3d8168"} icon={AlertTriangle} onClick={() => navigate("lotti")} />
            <KpiBig label="Ordini da convalidare" value={cruscotto.kpi.ordini_bozza}
              sub={cruscotto.kpi.ordini_bozza ? "bozze in attesa" : "nessuno"} color={cruscotto.kpi.ordini_bozza ? "#8a6f47" : "#3d8168"} icon={ShoppingCart} onClick={() => navigate("ordini")} />
            <KpiBig label="Prodotti oggi" value={loading ? "..." : fmt(riepilogo.pezziProdotti)}
              sub="pezzi in produzione" color="#8a6f47" icon={ChefHat} onClick={() => navigate("storico_produzioni")} />
          </div>
        </section>
      )}


      {/* Home più pulita: Area ufficio e Archivio (roba da scrivania, non
          quotidiana in negozio) sotto un pulsante a comparsa, chiuso di default. */}
      <button
        type="button"
        onClick={() => setUfficioOpen(v => !v)}
        className="flex w-full items-center justify-between gap-3 rounded-lg border border-stone-200 bg-white p-4 text-left shadow-sm transition hover:bg-stone-50"
        aria-expanded={ufficioOpen}
      >
        <span className="flex items-center gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-stone-100"><Settings size={20} className="text-stone-500" /></span>
          <span>
            <span className="block text-base font-black text-stone-900">Ufficio e archivio</span>
            <span className="block text-sm font-semibold text-stone-500">Ricette, fatture, fornitori, dati e listini — tocca per aprire.</span>
          </span>
        </span>
        {ufficioOpen ? <ChevronDown className="shrink-0 text-stone-400" size={20} /> : <ChevronRight className="shrink-0 text-stone-400" size={20} />}
      </button>

      {ufficioOpen && (<>
      <section>
        <SectionTitle title="Area ufficio" subtitle="Gestione dati, cataloghi e fornitori." />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <ActionCard icon={BookOpen} title="Ricette" subtitle="Ricettario, varianti, food cost e allergeni." badge={stats.ricette ? `${stats.ricette}` : ""} tone="violet" onClick={() => navigate("ricette")} />
          <ActionCard icon={FileText} title="Fatture XML" subtitle="Import fatture e aggiornamento prodotti." badge={stats.fatture ? `${stats.fatture}` : "Import"} tone="blue" onClick={() => navigate("fatture")} />
          <ActionCard icon={ShoppingCart} title="Acquisti & Ordini" subtitle="Catalogo, confronto prezzi, carrello e invio." badge={ordiniBozza ? `${ordiniBozza}` : "OK"} tone={ordiniBozza ? "amber" : "neutral"} onClick={() => navigate("ordini")} />
          <ActionCard icon={Building2} title="Fornitori" subtitle="Anagrafica, qualifica e schede ricevimento." badge="Rubrica" tone="green" onClick={() => navigate("fornitori")} />
          <ActionCard icon={Wallet} title="Dashboard economica" subtitle="Valore lotti, spreco, margini e fornitori." badge="€" tone="green" onClick={() => navigate("dashboard_economica")} />
          <ActionCard icon={Network} title="Mappa tracciabilità" subtitle="Il percorso di un prodotto, dalla fattura allo smaltimento." badge="Mappa" tone="neutral" onClick={() => navigate("mappa_tracciabilita")} />
        </div>
      </section>

      <section>
        <SectionTitle title="Archivio" subtitle="Accessi veloci ai dati strutturali." />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <QuickLink icon={Package} title="Materie prime" subtitle={`${fmt(stats.materie_prime)} articoli`} onClick={() => navigate("materie")} />
          <QuickLink icon={Layers} title="Lotti totali" subtitle={`${fmt(stats.lotti_totali)} registrazioni`} onClick={() => navigate("lotti")} />
          <QuickLink icon={Truck} title="Ricezione merce" subtitle="Arrivi, controlli e fornitori" onClick={() => navigate("ricezione_merce")} />
          {isAdmin() && <QuickLink icon={Settings} title="Impostazioni" subtitle="Personale, PIN e permessi" onClick={() => navigate("personale")} />}
          {isAdmin() && <QuickLink icon={Network} title="Controllo Dati" subtitle="Integrità dati e pulizia database" onClick={() => navigate("controllo_dati")} />}
          {isAdmin() && <QuickLink icon={ClipboardCheck} title="Collaudi da fare" subtitle="Test da spuntare dopo ogni modifica" onClick={() => navigate("collaudi")} />}
          <QuickLink icon={FileText} title="Listini e cataloghi" subtitle="Listini, cataloghi fornitori, prezzi banco e magazzino" onClick={() => navigate("prodotti")} />
        </div>
      </section>
      </>)}

      <section className="border-t border-stone-200 pt-4">
        <SectionTitle title="Strumenti avanzati" subtitle="Registro pesce, centro HACCP e stato sistema." />
        <div className="mt-4 space-y-4">
          {/* Card pesce: piccola, al clic si espande nel registro completo. */}
          {!pesceOpen ? (
            <button
              type="button"
              onClick={() => setPesceOpen(true)}
              className="flex w-full items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4 text-left shadow-sm transition hover:border-amber-300 hover:bg-amber-100"
              aria-expanded={false}
            >
              <span className="flex min-w-0 items-center gap-3">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-amber-100"><Fish size={20} className="text-[#8a6f47]" /></span>
                <span className="min-w-0">
                  <span className="block text-base font-black text-stone-900">Registro pesce</span>
                  <span className="block text-sm font-semibold text-stone-500">Tracciabilità pesce — tocca per aprire.</span>
                </span>
              </span>
              <ChevronRight className="shrink-0 text-amber-500" size={20} />
            </button>
          ) : (
            <div>
              <button
                type="button"
                onClick={() => setPesceOpen(false)}
                className="mb-2 flex items-center gap-1 text-sm font-bold text-amber-700 hover:text-amber-900"
                aria-expanded={true}
              >
                <ChevronDown size={16} /> Chiudi registro pesce
              </button>
              <PesceTraceabilityCard />
            </div>
          )}
          <HACCPHomeCard navigate={navigate} />
          <StatoSistemaWidget />
        </div>
      </section>
    </div>
  );
}
