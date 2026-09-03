import React, { useState, useEffect, useRef, useCallback } from "react";
import { Search, ShoppingCart, TrendingDown, Check, Pencil } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";
import { API } from "../../utils/constants";
import { apiError } from "../../utils/apiError";
import Button from "../ui/Button";

const Card = ({ children, className = "" }) => (
  <div className={`bg-white rounded-2xl border border-[#e6e0d4] shadow-sm ${className}`}>{children}</div>
);

// Stesso carrello di OrdiniView (localStorage "ordini_smart_carrello"): i
// prodotti aggiunti qui compaiono in Ordini → Carrello grazie all'evento.
const CART_LS_KEY = "ordini_smart_carrello";
function aggiungiAlCarrello(item) {
  let items = [];
  try { items = JSON.parse(localStorage.getItem(CART_LS_KEY) || "[]"); } catch { items = []; }
  const idx = items.findIndex(x => x.id === item.id);
  if (idx >= 0) items[idx].quantita = (Number(items[idx].quantita) || 0) + (Number(item.quantita) || 1);
  else items.push(item);
  try { localStorage.setItem(CART_LS_KEY, JSON.stringify(items)); } catch { /* no-op */ }
  try { window.dispatchEvent(new Event("ordini_smart_cart_update")); } catch { /* no-op */ }
}

function fmtPrezzo(v) {
  return "€ " + (Number(v) || 0).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ── Riga fornitore ──────────────────────────────────────────────────────────
function RigaFornitore({ r, prodottoNome, migliore }) {
  const add = () => {
    aggiungiAlCarrello({
      id: `conf_${r.prodotto_id || r.nome_normalizzato}`,
      nome: prodottoNome,
      unita_misura: r.unita || "pz",
      fornitore: r.fornitore,
      prezzo: r.prezzo,
      quantita: 1,
    });
    toast.success(`${prodottoNome}: aggiunto al carrello (${r.fornitore})`);
  };
  return (
    <div
      className="flex items-center justify-between gap-2 rounded-xl px-3 py-2"
      style={migliore
        ? { background: "#eef3ef", border: "1px solid #b8d0c2" }
        : { background: "#fffefb", border: "1px solid #e6e0d4" }}
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-gray-800 truncate">{r.fornitore}</span>
          {migliore && (
            <span className="inline-flex items-center gap-1 rounded-full bg-[#3d8168] px-2 py-0.5 text-[10px] font-bold text-white">
              <TrendingDown size={11} /> più conveniente
            </span>
          )}
        </div>
        <div className="text-[11px] text-gray-500">
          {r.prezzo_kg ? `${fmtPrezzo(r.prezzo_kg)}/kg` : ""}{r.data ? ` · ultima fattura ${r.data}` : ""}
        </div>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <span className="text-sm font-extrabold text-[#3f5a4e] whitespace-nowrap">
          {fmtPrezzo(r.prezzo)}<span className="text-[11px] font-semibold text-gray-500"> / {r.unita}</span>
        </span>
        <Button onClick={add} variant={migliore ? "primary" : "secondary"} className="!px-2.5 !py-1.5">
          <ShoppingCart size={15} />
        </Button>
      </div>
    </div>
  );
}

// ── Card prodotto ───────────────────────────────────────────────────────────
function CardProdotto({ p, onRinominato }) {
  const [editNome, setEditNome] = useState(false);
  const [nuovoNome, setNuovoNome] = useState(p.nome || "");
  const [salvando, setSalvando] = useState(false);

  const nomeMostrato = p.canonico || p.nome;
  const migliore = p.righe && p.righe.length ? p.righe[0] : null;

  const salvaNome = async () => {
    const nome = (nuovoNome || "").trim();
    if (!nome) return;
    setSalvando(true);
    try {
      // memorizza il canonico per TUTTE le righe del gruppo (per ogni fornitore)
      const chiavi = Array.from(new Set((p.righe || []).map(r => r.nome_normalizzato).filter(Boolean)));
      for (const k of chiavi) {
        await axios.post(`${API}/normalizzazione/correggi-mapping`, { descrizione_key: k, nome_canc: nome });
      }
      toast.success(`Nome memorizzato: ${nome}`);
      setEditNome(false);
      if (onRinominato) onRinominato();
    } catch (e) { toast.error(apiError(e, "Errore nel salvataggio del nome")); }
    finally { setSalvando(false); }
  };

  return (
    <Card className="p-4 space-y-2.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-base font-extrabold text-gray-900 capitalize truncate">{nomeMostrato}</h3>
          <p className="text-[11px] text-gray-500">{p.n_fornitori} forniter{p.n_fornitori === 1 ? "e" : "i"} · prezzi dall'ultima fattura</p>
        </div>
        <button
          onClick={() => { setNuovoNome(nomeMostrato); setEditNome(v => !v); }}
          className="inline-flex items-center gap-1 rounded-lg border border-stone-200 bg-white px-2 py-1 text-[11px] font-bold text-stone-600 hover:bg-stone-50 flex-shrink-0"
          title="Correggi il nome del prodotto: verrà memorizzato"
        >
          <Pencil size={12} /> {p.senza_canonico ? "dai un nome" : "correggi nome"}
        </button>
      </div>

      {p.senza_canonico && !editNome && (
        <p className="text-[11px] text-[#8a6f47]">Nome non ancora confermato — tocca «dai un nome» per memorizzarlo.</p>
      )}

      {editNome && (
        <div className="flex items-center gap-2">
          <input
            value={nuovoNome}
            onChange={e => setNuovoNome(e.target.value)}
            placeholder="nome del prodotto (es. Coca Cola 33cl)"
            className="flex-1 rounded-lg border border-[#e6e0d4] bg-white px-3 py-2 text-sm"
          />
          <Button onClick={salvaNome} disabled={salvando || !nuovoNome.trim()} variant="primary" className="!px-3 !py-2">
            <Check size={16} /> Salva
          </Button>
        </div>
      )}

      <div className="space-y-1.5">
        {(p.righe || []).map((r, i) => (
          <RigaFornitore key={(r.prodotto_id || r.nome_normalizzato || "") + i}
            r={r} prodottoNome={nomeMostrato} migliore={migliore && r === migliore} />
        ))}
      </div>
    </Card>
  );
}

// ── Pagina ──────────────────────────────────────────────────────────────────
export default function ConfrontoProdottoView() {
  const [q, setQ] = useState("");
  const [prodotti, setProdotti] = useState([]);
  const [loading, setLoading] = useState(false);
  const [cercato, setCercato] = useState(false);
  const timer = useRef(null);

  const cerca = useCallback(async (query) => {
    if (!query || query.trim().length < 2) { setProdotti([]); setCercato(false); return; }
    setLoading(true);
    try {
      const r = await axios.get(`${API}/food-cost/confronto-prodotto`, { params: { q: query.trim() } });
      setProdotti(r.data?.prodotti || []);
      setCercato(true);
    } catch (e) { toast.error(apiError(e, "Errore nella ricerca")); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => cerca(q), 350);
    return () => timer.current && clearTimeout(timer.current);
  }, [q, cerca]);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-extrabold text-gray-900">Confronto prezzi fornitori</h2>
        <p className="text-sm text-gray-500">Cerca un prodotto: vedi l'ultimo prezzo di ogni fornitore, il più conveniente è evidenziato e lo aggiungi al carrello ordini.</p>
      </div>

      <div className="relative">
        <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          value={q}
          onChange={e => setQ(e.target.value)}
          autoFocus
          placeholder="es. coca cola, farina, mozzarella…"
          className="w-full rounded-xl border border-[#e6e0d4] bg-white pl-10 pr-3 py-3 text-base shadow-sm focus:outline-none focus:ring-2 focus:ring-[#b8d0c2]"
        />
      </div>

      {loading && <div className="py-8 text-center text-gray-500">Cerco…</div>}

      {!loading && cercato && prodotti.length === 0 && (
        <div className="py-8 text-center text-gray-500">
          Nessun prodotto trovato per «{q}». Prova un nome più semplice, oppure importa prima le fatture.
        </div>
      )}

      {!loading && prodotti.map((p, i) => (
        <CardProdotto key={(p.canonico || p.nome || "") + i} p={p} onRinominato={() => cerca(q)} />
      ))}

      {!cercato && !loading && (
        <div className="py-10 text-center text-gray-400">Scrivi il nome di un prodotto per iniziare.</div>
      )}
    </div>
  );
}
