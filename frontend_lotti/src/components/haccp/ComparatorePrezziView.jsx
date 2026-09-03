/**
 * ComparatorePrezziView.jsx
 * ═══════════════════════════════════════════════════════════════
 * Confronto prezzi sui DATI REALI degli acquisti.
 *
 * Fonte unica: GET /food-cost/confronto-prezzi
 *   - raggruppa dizionario_prodotti per nome canonico
 *     (nome_canonico > ingrediente_canonico > nome_normalizzato)
 *   - prezzi SOLO dalle fatture XML (prezzo_kg per fornitore)
 *   - ricerca con stems_ricerca: lo stesso motore di tutte le ricerche
 *
 * Stile: come la Dashboard (Tailwind stone/white, icone Lucide,
 * palette salvia #5b7a6b — mai blu/indaco/viola, niente emoji).
 * ═══════════════════════════════════════════════════════════════
 */
import { useState, useEffect, useRef } from "react";
import axios from "axios";
import {
  Search, ChevronRight, Star, RefreshCw, Package, Scale,
  TrendingDown, ArrowDownUp, X, Coffee, Droplets, Wine, Beer,
  Milk, Egg, Wheat, Candy, CupSoda, Citrus, Snowflake, Box,
  SprayCan, Croissant, Fish, Beef, Salad, Nut,
} from "lucide-react";
import { API } from "../../utils/constants";

const SALVIA = "#5b7a6b";

// Icona Lucide per categoria (niente emoji, come da design system)
const CAT_ICONS = [
  [/caff|caffe/i, Coffee], [/acqua/i, Droplets], [/vino|prosecco|spumante/i, Wine],
  [/birr/i, Beer], [/latt|latticin|formagg/i, Milk], [/uov/i, Egg],
  [/farin|cereal|pane/i, Wheat], [/zuccher|dolcificant|candy|caramell/i, Candy],
  [/bibit|succ|bevand/i, CupSoda], [/frutt|verdur|ortofrutt/i, Citrus],
  [/surgelat|gelat|congelat/i, Snowflake], [/pulizia|detersiv|igien/i, SprayCan],
  [/croissant|cornett|pasticc|brioch/i, Croissant], [/pesce|ittic/i, Fish],
  [/carne|salum/i, Beef], [/insalat|fresch/i, Salad], [/secca|nocciol|mandorl/i, Nut],
  [/imball|monous|carta/i, Box],
];
const iconaCategoria = (cat) => {
  for (const [rx, I] of CAT_ICONS) if (rx.test(cat || "")) return I;
  return Package;
};

const fmtPrezzo = (v, um) =>
  !v || v <= 0 ? "—" : `€${Number(v).toFixed(2)}/${um || "kg"}`;

// Bevande/alcolici (bar): si confrontano a cartone, MAI a kg/litro — un rum o
// una birra si comprano a bottiglia/cartone, non "al chilo" (Enzo 02/07/2026).
const prezzoConfronto = (v, prod) =>
  prod?.vendita_a_unita ? v?.prezzo_unita_fattura : v?.prezzo_kg;
const unitaConfronto = (prod) => (prod?.vendita_a_unita ? "cartone" : prod?.unita || "kg");

// ── Card prodotto (stile ActionCard/QuickLink della dashboard) ───────────────
function CardProdotto({ prod, onClick }) {
  const Icon = iconaCategoria(prod.categoria);
  const multi = prod.n_fornitori >= 2;
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center gap-3 rounded-lg border border-stone-200 bg-white p-3 text-left shadow-sm transition hover:border-stone-300 hover:bg-stone-50 active:scale-[.99]"
      style={multi ? { borderLeft: `3px solid ${SALVIA}` } : undefined}
    >
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-stone-100 text-stone-700">
        <Icon size={19} />
      </span>
      {/* Nomi COMPLETI su 2 righe: il truncate li rendeva illeggibili sul
          telefono ("Pista…", "Stru…") — segnalato da Enzo 04/07/2026 */}
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-black leading-tight text-stone-900 break-words [display:-webkit-box] [-webkit-line-clamp:2] [-webkit-box-orient:vertical] overflow-hidden">
          {prod.nome}
        </span>
        <span className="block text-xs font-semibold text-stone-500 break-words">
          {multi
            ? <>{prod.n_fornitori} fornitori · migliore: <strong className="text-emerald-700">{prod.miglior_fornitore}</strong></>
            : prod.miglior_fornitore}
        </span>
      </span>
      <span className="shrink-0 text-right">
        <span className="block text-sm font-black tabular-nums text-stone-900">
          {fmtPrezzo(prod.vendita_a_unita ? prod.miglior_prezzo_confezione : prod.miglior_prezzo_kg, unitaConfronto(prod))}
        </span>
        {prod.risparmio_pct >= 2 && (
          <span
            title="Quanto risparmi scegliendo il fornitore più economico invece del più caro"
            className="mt-0.5 inline-flex items-center gap-1 rounded-md bg-emerald-50 px-1.5 py-0.5 text-[11px] font-black text-emerald-700"
          >
            <TrendingDown size={11} /> −{prod.risparmio_pct}%
          </span>
        )}
      </span>
      <ChevronRight size={16} className="shrink-0 text-stone-400" />
    </button>
  );
}

// ── Sheet dettaglio: prezzi per fornitore ────────────────────────────────────
function SheetDettaglio({ prod, onClose }) {
  const Icon = iconaCategoria(prod.categoria);
  const varianti = prod.varianti || [];
  const min = varianti.length ? prezzoConfronto(varianti[0], prod) : 0;
  const max = varianti.length ? prezzoConfronto(varianti[varianti.length - 1], prod) : 0;
  const unitaProd = unitaConfronto(prod);
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center"
      style={{ background: "rgba(42,51,41,.5)" }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl overflow-y-auto rounded-t-2xl bg-white px-5 pb-8 pt-2"
        style={{ maxHeight: "90vh", animation: "slideUp .25s cubic-bezier(.4,0,.2,1)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mx-auto mb-4 mt-1 h-1 w-10 rounded bg-stone-300" />

        <div className="mb-4 flex items-start gap-3">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-lg bg-stone-100 text-stone-700">
            <Icon size={22} />
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="m-0 text-lg font-black leading-tight text-stone-900">{prod.nome}</h2>
            <p className="m-0 mt-1 text-xs font-semibold text-stone-500">
              {prod.categoria || "ALTRO"} · prezzi per {unitaProd} · {prod.acquisti} acquisti registrati
            </p>
          </div>
        </div>

        {varianti.length >= 2 && (
          <div
            className="mb-4 rounded-2xl p-4 text-white"
            style={{ background: `linear-gradient(135deg, ${SALVIA} 0%, #6f9180 100%)` }}
          >
            <div className="mb-2 text-[11px] font-black uppercase tracking-wider opacity-80">
              Confronto tra {varianti.length} fornitori
            </div>
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[10px] font-black opacity-75">MIGLIOR PREZZO</div>
                <div className="text-2xl font-black tabular-nums">{fmtPrezzo(min, unitaProd)}</div>
                <div className="text-xs opacity-90">{prod.miglior_fornitore}</div>
              </div>
              <div className="text-right">
                <div className="text-[10px] font-black opacity-75">RISPARMIO VS PEGGIORE</div>
                <div className="text-2xl font-black tabular-nums">{max > 0 ? `${prod.risparmio_pct}%` : "—"}</div>
                <div className="text-xs opacity-90">€{(max - min).toFixed(2)}/{unitaProd} di differenza</div>
              </div>
            </div>
          </div>
        )}

        <div className="mb-2 text-sm font-black text-stone-900">Prezzi per fornitore</div>
        {varianti.map((v, i) => {
          const prezzoV = prezzoConfronto(v, prod);
          const best = i === 0 && prezzoV > 0;
          const pctMore = min > 0 && prezzoV > min ? Math.round(((prezzoV - min) / min) * 100) : 0;
          return (
            <div
              key={`${v.fornitore}-${i}`}
              className={`mb-2 flex items-center gap-3 rounded-lg border p-3 ${
                best ? "border-emerald-200 bg-emerald-50" : "border-stone-200 bg-white"
              }`}
            >
              {best && (
                <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-emerald-600">
                  <Star size={13} className="text-white" fill="#fff" />
                </span>
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 text-sm font-black text-stone-900">
                  <span className="truncate">{v.fornitore}</span>
                  {best && <span className="text-[10px] font-black text-emerald-700">MIGLIORE</span>}
                  {pctMore > 0 && <span className="text-[10px] font-black" style={{ color: "#d35f4e" }}>+{pctMore}%</span>}
                </div>
                <div className="truncate text-xs font-semibold text-stone-500">{v.nome_fattura}</div>
                {v.data && <div className="text-[11px] font-semibold text-stone-400">ultima fattura {v.data}</div>}
              </div>
              <div className="shrink-0 text-right">
                <div className={`text-base font-black tabular-nums ${best ? "text-emerald-700" : "text-stone-900"}`}>
                  {fmtPrezzo(prezzoV, unitaProd)}
                </div>
                {prod.vendita_a_unita ? (
                  v.prezzo_kg > 0 && (
                    <div className="text-[11px] font-semibold text-stone-400">€{Number(v.prezzo_kg).toFixed(2)}/{v.unita || "l"} equiv.</div>
                  )
                ) : (
                  v.prezzo_confezione > 0 && (
                    <div className="text-[11px] font-semibold text-stone-400">€{Number(v.prezzo_confezione).toFixed(2)}/conf.</div>
                  )
                )}
              </div>
            </div>
          );
        })}

        <button
          type="button"
          onClick={onClose}
          className="mt-3 w-full rounded-lg border border-stone-200 bg-white py-3 text-sm font-black text-stone-600 transition hover:bg-stone-50"
        >
          Chiudi
        </button>
      </div>
    </div>
  );
}

// ── VISTA PRINCIPALE ─────────────────────────────────────────────────────────
export function ComparatorePrezziView() {
  const [prodotti, setProdotti] = useState([]);
  const [categorie, setCategorie] = useState([]);
  const [totale, setTotale] = useState(0);
  const [loading, setLoading] = useState(true);
  // deep-link dalla Dashboard economica (variazione prezzi): apre il
  // Confronto con la ricerca già compilata sull'ingrediente toccato
  const [search, setSearch] = useState(() => {
    try {
      const s = sessionStorage.getItem("comparatore_search");
      if (s) { sessionStorage.removeItem("comparatore_search"); return s; }
    } catch { /* no-op */ }
    return "";
  });
  const [catFiltro, setCatFiltro] = useState("");
  const [soloMulti, setSoloMulti] = useState(false);
  const [dettaglio, setDettaglio] = useState(null);
  const timerRef = useRef(null);

  // Ricerca server-side (motore unico a radici), con debounce
  useEffect(() => {
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const r = await axios.get(`${API}/food-cost/confronto-prezzi`, {
          params: {
            q: search || undefined,
            categoria: catFiltro || undefined,
            solo_confrontabili: soloMulti || undefined,
            limit: 200,
          },
        });
        setProdotti(r.data?.prodotti || []);
        setCategorie(r.data?.categorie || []);
        setTotale(r.data?.totale || 0);
      } catch (e) {
        console.error("Errore confronto prezzi:", e);
        setProdotti([]);
      } finally {
        setLoading(false);
      }
    }, search ? 300 : 0);
    return () => clearTimeout(timerRef.current);
  }, [search, catFiltro, soloMulti]);

  return (
    <div className="min-h-screen" style={{ background: "#faf7f0" }}>
      <div className="mx-auto max-w-3xl px-4 pb-10 pt-4">

        {/* Intestazione — come SectionTitle della dashboard */}
        <div className="mb-3 flex items-end justify-between gap-3">
          <div className="min-w-0">
            <h2 className="m-0 text-lg font-black text-stone-900">Confronto prezzi</h2>
            <p className="m-0 mt-0.5 text-sm font-medium text-stone-500">
              Prezzi reali dalle fatture, per fornitore
            </p>
          </div>
          <button
            type="button"
            onClick={() => { setSearch(""); setCatFiltro(""); setSoloMulti(false); }}
            className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-stone-200 bg-white text-stone-500 shadow-sm transition hover:border-stone-300"
            title="Azzera filtri"
          >
            <RefreshCw size={16} />
          </button>
        </div>

        {/* Ricerca */}
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2.5 shadow-sm">
          <Search size={16} className="shrink-0 text-stone-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Cerca prodotto o fornitore (es. crodino)…"
            className="min-w-0 flex-1 border-none bg-transparent text-sm font-semibold text-stone-900 outline-none placeholder:font-medium placeholder:text-stone-400"
          />
          {search && (
            <button type="button" onClick={() => setSearch("")} className="grid h-6 w-6 place-items-center rounded text-stone-400 hover:text-stone-600">
              <X size={14} />
            </button>
          )}
        </div>

        {/* Categorie (dinamiche dai dati) */}
        <div className="-mx-4 mb-3 overflow-x-auto px-4" style={{ scrollbarWidth: "none" }}>
          <div className="flex w-max gap-2">
            <button
              type="button"
              onClick={() => setCatFiltro("")}
              className={`whitespace-nowrap rounded-full px-3.5 py-1.5 text-xs font-black transition ${
                !catFiltro ? "text-white" : "border border-stone-200 bg-white text-stone-600"
              }`}
              style={!catFiltro ? { background: SALVIA } : undefined}
            >
              Tutte
            </button>
            {categorie.map(([cat, n]) => (
              <button
                key={cat}
                type="button"
                onClick={() => setCatFiltro(catFiltro === cat ? "" : cat)}
                className={`whitespace-nowrap rounded-full px-3.5 py-1.5 text-xs font-black transition ${
                  catFiltro === cat ? "text-white" : "border border-stone-200 bg-white text-stone-600"
                }`}
                style={catFiltro === cat ? { background: SALVIA } : undefined}
              >
                {cat} ({n})
              </button>
            ))}
          </div>
        </div>

        {/* Solo confrontabili + conteggio */}
        <div className="mb-4 flex items-center gap-3">
          <button
            type="button"
            onClick={() => setSoloMulti((v) => !v)}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-black transition ${
              soloMulti ? "text-white" : "border border-stone-200 bg-white text-stone-600"
            }`}
            style={soloMulti ? { background: SALVIA } : undefined}
          >
            <ArrowDownUp size={13} /> Solo con più fornitori
          </button>
          <span className="text-xs font-bold text-stone-400">{totale} prodotti</span>
        </div>

        {/* Lista */}
        {loading && (
          <div className="py-12 text-center">
            <RefreshCw size={22} className="mx-auto mb-2 animate-spin text-stone-400" />
            <p className="text-sm font-semibold text-stone-400">Caricamento…</p>
          </div>
        )}

        {!loading && prodotti.length === 0 && (
          <div className="rounded-lg border border-stone-200 bg-white py-12 text-center shadow-sm">
            <Scale size={40} className="mx-auto mb-3 text-stone-300" />
            <p className="m-0 text-sm font-black text-stone-700">Nessun prodotto trovato</p>
            <p className="m-0 mt-1 text-xs font-semibold text-stone-400">
              {search ? "Prova con un termine diverso o togli i filtri" : "I prezzi arrivano automaticamente dalle fatture XML"}
            </p>
          </div>
        )}

        {!loading && (
          <div className="flex flex-col gap-2">
            {prodotti.map((p) => (
              <CardProdotto key={p.nome} prod={p} onClick={() => setDettaglio(p)} />
            ))}
          </div>
        )}
      </div>

      {dettaglio && <SheetDettaglio prod={dettaglio} onClose={() => setDettaglio(null)} />}

      <style>{`
        @keyframes slideUp {
          from { transform: translateY(100%); opacity: 0; }
          to   { transform: translateY(0);    opacity: 1; }
        }
      `}</style>
    </div>
  );
}

export default ComparatorePrezziView;
