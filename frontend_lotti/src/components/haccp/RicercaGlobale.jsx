// RicercaGlobale — Tranche 6 (Miglioramenti UI trasversali).
// Ricerca per prodotto, lotto, fornitore, ricetta, frigorifero in un solo
// posto (backend: GET /api/ricerca-globale). Prima esisteva solo la
// ricerca universale dei lotti dentro LottiList.
import { useState, useEffect } from "react";
import axios from "axios";
import { Search, X, Layers, ChefHat, Building2, Wheat, Refrigerator, FileText, ShoppingCart, Factory } from "lucide-react";
import { API } from "../../utils/constants";

const TAB_PER_CATEGORIA = {
  lotti: "lotti",
  ricette: "ricette",
  fornitori: "fornitori",
  materie_prime: "dizionario",
  attrezzature: "cosa_usare_oggi",
  fatture: "fatture",
  ordini: "ordini",
  produzioni: "storico_produzioni",
};

const ICONA_PER_CATEGORIA = {
  lotti: Layers, ricette: ChefHat, fornitori: Building2, materie_prime: Wheat, attrezzature: Refrigerator,
  fatture: FileText, ordini: ShoppingCart, produzioni: Factory,
};

const LABEL_PER_CATEGORIA = {
  lotti: "Lotti", ricette: "Ricette", fornitori: "Fornitori", materie_prime: "Materie prime", attrezzature: "Frigoriferi/attrezzature",
  fatture: "Fatture", ordini: "Ordini", produzioni: "Produzioni",
};

function etichettaRisultato(cat, r) {
  if (cat === "lotti") return `${r.prodotto} · ${r.numero_lotto}`;
  if (cat === "ricette") return `${r.nome}${r.reparto ? " · " + r.reparto : ""}`;
  if (cat === "fornitori") return r.nome;
  // Fallback a catena: molti doc del dizionario non hanno nome_canonico e la
  // riga risultava VUOTA nel menu della ricerca (audit visivo 24/07/2026).
  if (cat === "materie_prime") return r.nome_display || r.nome_canonico || r.nome_normalizzato || r.nome_originale || "(senza nome)";
  if (cat === "attrezzature") return `${r.nome}`;
  if (cat === "fatture") return `${r.numero_fattura || "—"} · ${r.fornitore || ""}${r.data_fattura ? " · " + r.data_fattura : ""}`;
  if (cat === "ordini") return `${r.fornitore || "—"} · ${r.stato || ""}`;
  if (cat === "produzioni") return `${r.ricetta_nome || "—"} · ${r.numero_lotto || ""}${r.pezzi ? " · " + r.pezzi + " pz" : ""}`;
  return "";
}

export function RicercaGlobale({ onNavigate }) {
  const [aperto, setAperto] = useState(false);
  const [q, setQ] = useState("");
  const [risultati, setRisultati] = useState(null);
  const [loading, setLoading] = useState(false);
  const [dettaglioLotto, setDettaglioLotto] = useState(null); // {id, dati}

  const apriDettaglioLotto = async (r) => {
    if (dettaglioLotto?.id === r.id) { setDettaglioLotto(null); return; }
    setDettaglioLotto({ id: r.id, dati: null });
    try {
      const res = await axios.get(`${API}/ricerca-globale/lotto/${encodeURIComponent(r.id)}`);
      setDettaglioLotto({ id: r.id, dati: res.data });
    } catch { setDettaglioLotto(null); }
  };

  useEffect(() => {
    if (!aperto || q.trim().length < 2) { setRisultati(null); return; }
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const r = await axios.get(`${API}/ricerca-globale`, { params: { q: q.trim() } });
        setRisultati(r.data);
      } catch {
        setRisultati(null);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [q, aperto]);

  const vai = (categoria) => {
    onNavigate?.(TAB_PER_CATEGORIA[categoria] || "dashboard");
    setAperto(false);
    setQ("");
  };

  const categorie = ["lotti", "ricette", "fornitori", "materie_prime", "attrezzature", "fatture", "ordini", "produzioni"];

  return (
    <div className="relative">
      <button
        onClick={() => setAperto((v) => !v)}
        title="Ricerca globale"
        aria-label="Ricerca globale"
        style={{
          display: "flex", alignItems: "center", gap: 6,
          background: "rgba(255,255,255,.12)", color: "#fff",
          border: "1px solid rgba(255,255,255,.25)", borderRadius: 10,
          padding: "7px 11px", fontSize: 13, fontWeight: 600, cursor: "pointer",
          flexShrink: 0,
        }}
      >
        <Search size={15} />
        <span className="hidden sm:inline" style={{ whiteSpace: "nowrap" }}>Cerca</span>
      </button>

      {aperto && (
        <>
          <div className="fixed inset-0 z-[998] bg-black/20" onClick={() => setAperto(false)} />
          <div className="fixed left-2 right-2 sm:left-auto sm:right-2 top-16 z-[999] sm:w-[380px] max-w-[calc(100vw-16px)] bg-white rounded-2xl shadow-2xl border border-gray-200 overflow-hidden">
            <div className="p-3 border-b border-gray-100 flex items-center gap-2">
              <Search size={16} className="text-gray-400 shrink-0" />
              <input
                autoFocus
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Prodotto, lotto, fornitore, ricetta, frigorifero..."
                className="w-full text-sm outline-none"
              />
              <button onClick={() => setAperto(false)}><X size={16} className="text-gray-400" /></button>
            </div>
            <div className="max-h-96 overflow-y-auto">
              {q.trim().length < 2 && (
                <p className="p-4 text-sm text-gray-400 text-center">Scrivi almeno 2 caratteri.</p>
              )}
              {loading && <p className="p-4 text-sm text-gray-400 text-center">Cerco...</p>}
              {!loading && risultati && risultati.totale === 0 && (
                <p className="p-4 text-sm text-gray-400 text-center">Nessun risultato per "{risultati.query}".</p>
              )}
              {!loading && risultati && categorie.map((cat) => {
                const righe = risultati[cat] || [];
                if (righe.length === 0) return null;
                const Icona = ICONA_PER_CATEGORIA[cat];
                return (
                  <div key={cat} className="border-b border-gray-50 last:border-0">
                    <div className="px-3 pt-2 pb-1 text-[11px] font-bold text-gray-400 uppercase tracking-wide flex items-center gap-1">
                      <Icona size={12} /> {LABEL_PER_CATEGORIA[cat]}
                    </div>
                    {righe.map((r, i) => (
                      <div key={i}>
                        <button onClick={() => (cat === "lotti" ? apriDettaglioLotto(r) : vai(cat))}
                          className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-[#f2f6f3] flex items-center justify-between gap-2">
                          <span className="truncate">{etichettaRisultato(cat, r)}</span>
                          {cat === "lotti" && <span className="text-[10px] text-gray-400 shrink-0">{dettaglioLotto?.id === r.id ? "chiudi" : "dettagli"}</span>}
                        </button>
                        {cat === "lotti" && dettaglioLotto?.id === r.id && (
                          <div className="mx-3 mb-2 rounded-xl border border-[#e6e0d4] bg-[#faf7f0] p-3 text-xs text-gray-700">
                            {!dettaglioLotto.dati ? "Carico…" : !dettaglioLotto.dati.trovato ? "Lotto non trovato" : (
                              <>
                                <div className="font-bold">{dettaglioLotto.dati.prodotto} · {dettaglioLotto.dati.numero_lotto}</div>
                                <div>Prod. {dettaglioLotto.dati.data_produzione} · Scad. <b>{dettaglioLotto.dati.data_scadenza}</b> · stato {dettaglioLotto.dati.stato}</div>
                                <div>Quantità {dettaglioLotto.dati.quantita} · consumato {dettaglioLotto.dati.consumato} · residuo <b>{dettaglioLotto.dati.residuo}</b>{dettaglioLotto.dati.destinazione ? ` · ${dettaglioLotto.dati.destinazione}` : ""}</div>
                                {dettaglioLotto.dati.origine?.length > 0 && (
                                  <div className="mt-1">
                                    <div className="font-bold text-[10px] uppercase text-gray-500">Origine (fornitori/fatture)</div>
                                    {dettaglioLotto.dati.origine.slice(0, 6).map((o, k) => (
                                      <div key={k}>• {o.ingrediente}{o.fornitore ? ` — ${o.fornitore}` : ""}{o.fattura ? ` (fatt. ${o.fattura})` : ""}</div>
                                    ))}
                                  </div>
                                )}
                                <button onClick={() => vai("lotti")} className="mt-2 rounded-lg bg-[#5b7a6b] px-3 py-1.5 font-bold text-white">Apri nei Lotti</button>
                              </>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
