// MappaTracciabilitaView — Tranche 6 (Miglioramenti UI trasversali).
// Mappa visiva del percorso di un prodotto: fattura → materia prima →
// ricetta → lotto → frigo → banco → invenduto → recupero/smaltimento.
// Puramente navigazionale: ogni nodo porta alla pagina reale corrispondente,
// nessun dato inventato.
import { FileText, Wheat, ChefHat, Layers, Refrigerator, Store, RotateCcw, Trash2, ArrowRight } from "lucide-react";

const NODI = [
  { id: "fattura", label: "Fattura", sotto: "Import XML fornitori", icon: FileText, tono: "#8a6f47", tab: "fatture" },
  { id: "materia_prima", label: "Materia prima", sotto: "Dizionario ingredienti", icon: Wheat, tono: "#8a6f47", tab: "dizionario" },
  { id: "ricetta", label: "Ricetta", sotto: "Food cost e allergeni", icon: ChefHat, tono: "#5b7a6b", tab: "ricette" },
  { id: "lotto", label: "Lotto", sotto: "Tracciabilità e scadenze", icon: Layers, tono: "#5b7a6b", tab: "lotti" },
  { id: "frigo", label: "Frigo / posizione", sotto: "Cosa usare oggi", icon: Refrigerator, tono: "#3f5a4e", tab: "cosa_usare_oggi" },
  { id: "banco", label: "Banco", sotto: "Vendita al banco (tablet)", icon: Store, tono: "#c4894a", tab: "tablet/vendita" },
  { id: "invenduto", label: "Invenduto", sotto: "Rientro serale (tablet)", icon: RotateCcw, tono: "#c4894a", tab: "tablet/vendita" },
  { id: "fine", label: "Recupero / Smaltimento", sotto: "Azioni sul lotto", icon: Trash2, tono: "#d35f4e", tab: "cosa_usare_oggi" },
];

export default function MappaTracciabilitaView({ onNavigate }) {
  const vai = (tab) => {
    if (tab.startsWith("tablet/")) { window.location.hash = tab; return; }
    onNavigate?.(tab);
  };

  return (
    <div className="max-w-5xl mx-auto p-4">
      <div className="mb-4">
        <h1 className="text-2xl font-black text-stone-900">Mappa tracciabilità</h1>
        <p className="text-sm text-stone-500">Il percorso di un prodotto, dalla fattura allo smaltimento — clicca un passaggio per aprirlo</p>
      </div>

      <div className="flex flex-wrap items-stretch gap-2">
        {NODI.map((n, i) => (
          <div key={n.id} className="flex items-center gap-2">
            <button onClick={() => vai(n.tab)}
              className="w-40 text-left bg-white rounded-2xl border-2 p-3 hover:shadow-md transition-shadow"
              style={{ borderColor: n.tono + "55" }}>
              <div className="w-9 h-9 rounded-xl flex items-center justify-center mb-2" style={{ background: n.tono + "1a", color: n.tono }}>
                <n.icon size={18} />
              </div>
              <div className="font-black text-sm text-stone-900">{n.label}</div>
              <div className="text-[11px] text-stone-500 mt-0.5">{n.sotto}</div>
            </button>
            {i < NODI.length - 1 && <ArrowRight size={18} className="text-stone-300 shrink-0" />}
          </div>
        ))}
      </div>

      <p className="text-xs text-stone-400 mt-6">
        "Banco" e "Invenduto" aprono l'app tablet di vendita — sul telefono/tablet in negozio, non nell'ufficio.
      </p>
    </div>
  );
}
