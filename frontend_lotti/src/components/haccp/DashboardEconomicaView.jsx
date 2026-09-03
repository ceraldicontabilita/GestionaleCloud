import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Wallet, TrendingUp, TrendingDown, Package, Building2, AlertTriangle,
  Trash2, ChevronDown, ChevronUp, RefreshCw, Calendar,
} from "lucide-react";
import Button from "../ui/Button";
import { API } from "../../utils/constants";
import { apiError } from "../../utils/apiError";
import { apriLottiConRicerca } from "../../utils/apriLotti";

const euro = (v) => (v === null || v === undefined) ? "—" : `€ ${Number(v).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

// Toni di stato dal design system (CLAUDE.md): mai colori freddi.
const TONI = {
  neutro:   { bg: "bg-white", bordo: "border-stone-200", testo: "text-stone-900", icona: "bg-stone-100 text-stone-600" },
  info:     { bg: "bg-[#f2f6f3]", bordo: "border-[#cfdfd5]", testo: "text-[#3f5a4e]", icona: "bg-[#e8efe9] text-[#3f5a4e]" },
  warning:  { bg: "bg-amber-50", bordo: "border-amber-200", testo: "text-amber-800", icona: "bg-amber-100 text-amber-700" },
  danger:   { bg: "bg-red-50", bordo: "border-red-200", testo: "text-red-700", icona: "bg-red-100 text-red-700" },
  success:  { bg: "bg-emerald-50", bordo: "border-emerald-200", testo: "text-emerald-800", icona: "bg-emerald-100 text-emerald-700" },
};

// ── Tile KPI cliccabile (espande il dettaglio sotto) ─────────────────────────
function KpiTile({ icon: Icon, label, valore, sotto, tono = "neutro", aperto, onClick }) {
  const t = TONI[tono];
  return (
    <button onClick={onClick}
      className={`text-left rounded-2xl border-2 ${t.bordo} ${t.bg} p-4 transition-shadow hover:shadow-md w-full`}>
      <div className="flex items-start justify-between">
        <div className={`p-2 rounded-xl ${t.icona}`}><Icon size={18} /></div>
        {onClick && (aperto ? <ChevronUp size={16} className="text-stone-400 mt-1" /> : <ChevronDown size={16} className="text-stone-400 mt-1" />)}
      </div>
      <div className={`text-2xl font-black mt-2 ${t.testo}`}>{valore}</div>
      <div className="text-xs text-stone-500 mt-0.5">{label}</div>
      {sotto && <div className="text-[11px] text-stone-400 mt-0.5">{sotto}</div>}
    </button>
  );
}

// ── Barra proporzionale per liste classificate (un solo hue, per grandezza) ──
// onRiga (facoltativo): rende ogni riga TOCCABILE verso il dettaglio
// (drill-down riga per riga — audit onesto 04/07/2026).
function BarraLista({ righe, campoLabel, campoValore, campoSotto, formatta = euro, coloreBar = "bg-[#5b7a6b]", onRiga }) {
  const max = Math.max(1, ...righe.map((r) => Math.abs(r[campoValore]) || 0));
  const Riga = onRiga ? "button" : "div";
  return (
    <div className="space-y-2">
      {righe.map((r, i) => (
        <Riga key={i} className={`text-xs block w-full text-left ${onRiga ? "hover:bg-stone-50 rounded-lg px-1 -mx-1 py-0.5" : ""}`}
          onClick={onRiga ? () => onRiga(r) : undefined}>
          <div className="flex justify-between mb-0.5">
            <span className="font-medium text-stone-700 truncate pr-2">{r[campoLabel]}</span>
            <span className="font-bold text-stone-900 whitespace-nowrap">{formatta(r[campoValore])}</span>
          </div>
          <div className="h-1.5 bg-stone-100 rounded-full overflow-hidden">
            <div className={`h-full ${coloreBar} rounded-full`} style={{ width: `${Math.max(4, (Math.abs(r[campoValore]) / max) * 100)}%` }} />
          </div>
          {campoSotto && <div className="text-stone-400 mt-0.5">{campoSotto(r)}</div>}
        </Riga>
      ))}
      {righe.length === 0 && <p className="text-xs text-stone-400">Nessun dato nel periodo.</p>}
    </div>
  );
}

// Slug fornitore identico a FornitoriList.forniSlug: apre #fornitori/{slug}
const forniSlug = (nome) => (nome || "").toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9\-]/g, "").slice(0, 60);

function Sezione({ title, icon: Icon, children }) {
  return (
    <div className="bg-white rounded-2xl border border-stone-200 p-4">
      <h3 className="text-sm font-black text-stone-900 mb-3 flex items-center gap-2">
        <Icon size={16} className="text-[#5b7a6b]" /> {title}
      </h3>
      {children}
    </div>
  );
}

export default function DashboardEconomicaView() {
  const [dati, setDati] = useState(null);
  const [loading, setLoading] = useState(true);
  const [mese, setMese] = useState(() => new Date().toISOString().slice(0, 7));
  const [espansi, setEspansi] = useState({});

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/dashboard-economica/riepilogo`, { params: { mese } });
      setDati(r.data);
    } catch (e) {
      toast.error(apiError(e, "Impossibile caricare la dashboard economica"));
    } finally {
      setLoading(false);
    }
  }, [mese]);

  useEffect(() => { carica(); }, [carica]);

  const toggle = (k) => setEspansi((s) => ({ ...s, [k]: !s[k] }));

  if (loading || !dati) {
    return <div className="max-w-5xl mx-auto p-4 text-center text-stone-500 py-12">Carico dashboard economica...</div>;
  }

  return (
    <div className="max-w-5xl mx-auto p-4 space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-black text-stone-900">Dashboard economica</h1>
          <p className="text-sm text-stone-500">Valore lotti, spreco, margini e fornitori — {dati.periodo_mese}</p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-sm text-stone-600">
            <Calendar size={16} />
            <input type="month" value={mese} onChange={(e) => setMese(e.target.value)}
              className="border border-stone-200 rounded-lg px-2 py-1.5 text-sm" />
          </label>
          <Button variant="secondary" size="sm" onClick={carica}><RefreshCw size={16}/> Aggiorna</Button>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <KpiTile icon={Wallet} label="Valore lotti attivi" valore={euro(dati.valore_totale_lotti_attivi)}
          sotto={`${dati.n_lotti_attivi} lotti`} tono="info"
          aperto={espansi.attivi} onClick={() => toggle("attivi")} />
        <KpiTile icon={AlertTriangle} label="Valore in scadenza" valore={euro(dati.valore_lotti_in_scadenza)}
          sotto={`${dati.n_lotti_in_scadenza} lotti`} tono={dati.n_lotti_in_scadenza ? "warning" : "success"}
          aperto={espansi.scadenza} onClick={() => toggle("scadenza")} />
        <KpiTile icon={Trash2} label="Smaltiti nel mese" valore={euro(dati.valore_lotti_smaltiti_mese)}
          tono={dati.valore_lotti_smaltiti_mese ? "danger" : "success"}
          aperto={espansi.smaltiti} onClick={() => toggle("smaltiti")} />
        <KpiTile icon={TrendingDown} label="Costo spreco oggi" valore={euro(dati.costo_spreco_giorno)} tono="warning"
          aperto={espansi.sprecoOggi} onClick={() => toggle("sprecoOggi")} />
        <KpiTile icon={TrendingDown} label="Costo spreco mese" valore={euro(dati.costo_spreco_mese)} tono="warning"
          sotto={`banco ${euro(dati.dettaglio_spreco_mese?.costo_banco_invenduto)} · smaltiti ${euro(dati.dettaglio_spreco_mese?.costo_lotti_smaltiti)}`}
          aperto={espansi.spreco} onClick={() => toggle("spreco")} />
      </div>

      {espansi.attivi && (
        <Sezione title="Lotti attivi (per valore)" icon={Wallet}>
          <BarraLista righe={dati.lotti_attivi_dettaglio || []} campoLabel="prodotto" campoValore="valore_economico"
            campoSotto={(r) => `${r.numero_lotto} · ${r.quantita ?? "—"} ${r.unita_misura || ""}`}
            onRiga={(r) => apriLottiConRicerca(r.numero_lotto || r.prodotto || "")} />
        </Sezione>
      )}
      {espansi.sprecoOggi && (
        <Sezione title="Spreco di oggi (dettaglio)" icon={TrendingDown}>
          <p className="text-[11px] text-stone-400 mb-2">
            Banco {euro(dati.dettaglio_spreco_giorno?.costo_banco_invenduto)} · lotti smaltiti {euro(dati.dettaglio_spreco_giorno?.costo_lotti_smaltiti)}
          </p>
          <BarraLista righe={[
            ...(dati.dettaglio_spreco_giorno?.dettaglio_banco || []).map((r) => ({ nome: `${r.prodotto} (banco, ${r.pezzi_invenduto} pz)`, valore: r.costo_sprecato })),
            ...(dati.dettaglio_spreco_giorno?.dettaglio_smaltiti || []).map((r) => ({ nome: `${r.prodotto} (smaltito, lotto ${r.numero_lotto})`, valore: r.valore || 0 })),
          ].sort((a, b) => b.valore - a.valore)} campoLabel="nome" campoValore="valore" coloreBar="bg-orange-500" />
        </Sezione>
      )}

      {espansi.scadenza && (
        <Sezione title="Lotti in scadenza (dettaglio)" icon={AlertTriangle}>
          <BarraLista righe={dati.lotti_in_scadenza_dettaglio || []} campoLabel="prodotto" campoValore="valore_economico"
            campoSotto={(r) => `${r.numero_lotto} · ${r.stato_scadenza?.label || ""}`} coloreBar="bg-amber-500" />
        </Sezione>
      )}
      {espansi.smaltiti && (
        <Sezione title="Lotti smaltiti nel mese (dettaglio)" icon={Trash2}>
          <BarraLista righe={dati.lotti_smaltiti_mese_dettaglio || []} campoLabel="prodotto" campoValore="valore"
            campoSotto={(r) => `${r.numero_lotto} · ${r.motivo || ""}`} coloreBar="bg-red-500" />
        </Sezione>
      )}

      {/* Drill-down riga per riga: ogni riga apre la pagina del dato
          (mancava — audit onesto 04/07/2026) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Sezione title="Margine per reparto" icon={Building2}>
          <BarraLista righe={dati.margine_per_reparto || []} campoLabel="reparto" campoValore="margine_euro_totale"
            campoSotto={(r) => `${r.n_prodotti} prodotti · margine medio ${r.margine_percentuale_medio}%`}
            onRiga={() => { window.location.hash = "ricette"; }} />
        </Sezione>
        <Sezione title="Fornitori con maggiore incidenza" icon={Building2}>
          <BarraLista righe={dati.fornitori_maggiore_incidenza || []} campoLabel="fornitore" campoValore="spesa"
            campoSotto={(r) => `${r.incidenza_pct}% della spesa del mese`} coloreBar="bg-[#8a6f47]"
            onRiga={(r) => { window.location.hash = `fornitori/${forniSlug(r.fornitore)}`; }} />
        </Sezione>
        <Sezione title="Prodotti più costosi" icon={TrendingUp}>
          <BarraLista righe={dati.prodotti_piu_costosi || []} campoLabel="nome" campoValore="costo_produzione"
            campoSotto={(r) => `prezzo ${euro(r.prezzo_vendita)} · margine ${r.margine_percentuale}%`}
            onRiga={(r) => {
              if (r.ricetta_id) { try { sessionStorage.setItem("apri_ricetta_id", r.ricetta_id); } catch { /* no-op */ } }
              window.location.hash = "ricette";
            }} />
        </Sezione>
        <Sezione title="Prodotti meno redditizi" icon={TrendingDown}>
          <BarraLista righe={dati.prodotti_meno_redditizi || []} campoLabel="nome" campoValore="margine_percentuale"
            formatta={(v) => `${v}%`} campoSotto={(r) => `costo ${euro(r.costo_produzione)} · prezzo ${euro(r.prezzo_vendita)}`}
            coloreBar="bg-orange-500"
            onRiga={(r) => {
              if (r.ricetta_id) { try { sessionStorage.setItem("apri_ricetta_id", r.ricetta_id); } catch { /* no-op */ } }
              window.location.hash = "ricette";
            }} />
        </Sezione>
        <Sezione title="Variazione prezzi materie prime" icon={Package}>
          <BarraLista righe={dati.variazione_prezzi_materie_prime || []} campoLabel="ingrediente" campoValore="variazione_pct"
            formatta={(v) => `+${v}%`} campoSotto={(r) => `€${r.prezzo_min_kg}/kg → €${r.prezzo_max_kg}/kg tra fornitori`}
            coloreBar="bg-orange-500"
            onRiga={(r) => {
              try { sessionStorage.setItem("comparatore_search", r.ingrediente || ""); } catch { /* no-op */ }
              window.location.hash = "comparatore";
            }} />
        </Sezione>
      </div>
    </div>
  );
}
