/**
 * prodotti/ProdottoCard.jsx — Card prodotto nella griglia di ProdottiVenditaView
 */
import { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Package, Save, X } from "lucide-react";

import { API, BACKEND_URL } from "../../../utils/constants";

function ProdottoCard({ prodotto, onClick, onPrezzoSalvato }) {
  const cp = parseFloat(prodotto.costo_produzione) || 0;
  const pv = parseFloat(prodotto.prezzo_vendita) || 0;
  const margineP = pv > 0 ? ((pv - cp) / pv * 100) : 0;
  const [editingPrezzo, setEditingPrezzo] = useState(false);
  const [inputPrezzo, setInputPrezzo] = useState("");
  const [salvando, setSalvando] = useState(false);

  const badges = [];
  if (!prodotto.attivo) badges.push({ label: "Inattivo", color: "bg-gray-200 text-gray-500" });
  if (prodotto.stagionale) badges.push({ label: "Stagionale", color: "bg-amber-100 text-amber-700" });
  if (prodotto.visibile_tablet === false) badges.push({ label: "No Tablet", color: "bg-red-100 text-red-600" });
  if (prodotto.visibile_ricette === false) badges.push({ label: "No Ricette", color: "bg-orange-100 text-orange-600" });

  const imgUrl = prodotto.immagine_url || prodotto.foto_url || prodotto.immagine || null;
  const imgSrc = imgUrl ? (imgUrl.startsWith("http") ? imgUrl : `${BACKEND_URL}${imgUrl}`) : null;
  const isAcquaviva = prodotto.fonte === "acquaviva";
  const imgH = isAcquaviva ? "h-40" : "h-28";

  const salvaPrezzo = async (e) => {
    e.stopPropagation();
    const nuovoPrezzo = parseFloat(inputPrezzo.replace(",", "."));
    if (!nuovoPrezzo || nuovoPrezzo <= 0) return;
    setSalvando(true);
    try {
      await axios.put(`${API}/prodotti-vendita/${prodotto.id}/prezzo?prezzo_vendita=${nuovoPrezzo}`);
      toast.success(`Prezzo impostato: €${nuovoPrezzo.toFixed(2)}`);
      setEditingPrezzo(false);
      if (onPrezzoSalvato) onPrezzoSalvato();
    } catch { toast.error("Errore salvataggio prezzo"); }
    setSalvando(false);
  };

  return (
    <div
      data-testid={`prodotto-card-${prodotto.id}`}
      onClick={() => { if (editingPrezzo) return; onClick(prodotto); }}
      className={`bg-white rounded-xl border border-gray-100 overflow-hidden cursor-pointer hover:border-[#b8d0c2] hover:shadow-lg transition-all group ${!prodotto.attivo ? "opacity-60" : ""}`}
    >
      <div className={`w-full ${imgH} overflow-hidden bg-gray-50 relative`}>
        {imgSrc ? (
          <img src={imgSrc} alt={prodotto.nome}
            className="w-full h-full object-contain group-hover:scale-105 transition-transform duration-300 p-1"
            onError={e => {
              const parent = e.target.parentElement;
              e.target.style.display = 'none';
              const div = document.createElement('div');
              div.className = 'w-full h-full flex items-center justify-center text-gray-300 text-3xl';
              div.textContent = String.fromCodePoint(0x1F4F7);
              parent.appendChild(div);
            }} />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-gray-200"><Package size={32} /></div>
        )}
        <div className="absolute top-2 right-2">
          {isAcquaviva && <span className="text-xs bg-[#5b7a6b] text-white px-2 py-0.5 rounded-full font-medium shadow-sm">Acquaviva</span>}
          {prodotto.fonte === "esterno" && <span className="text-xs bg-[#7a5f3d] text-white px-2 py-0.5 rounded-full font-medium shadow-sm">Esterno</span>}
        </div>
        {pv <= 0 && !editingPrezzo && (
          <div className="absolute bottom-2 left-2">
            <span className="text-xs bg-amber-500 text-white px-2 py-0.5 rounded-full font-medium">Senza prezzo</span>
          </div>
        )}
      </div>

      <div className="p-3">
        <h3 className="font-semibold text-gray-800 text-sm leading-snug line-clamp-2 group-hover:text-[#5b7a6b] mb-0.5">{prodotto.nome}</h3>
        <p className="text-xs text-gray-400 truncate mb-2">{prodotto.categoria || "Senza categoria"}</p>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <span className="bg-gray-50 px-2 py-0.5 rounded">€{cp > 0 ? cp.toFixed(cp < 0.1 ? 4 : 2) : "--"}</span>
            <span className="text-gray-300">→</span>
            <span className={`font-semibold text-sm ${pv > 0 ? "text-gray-800" : "text-gray-300"}`}>{pv > 0 ? `€${pv.toFixed(2)}` : "--"}</span>
          </div>
          {pv > 0 && cp > 0 && (
            <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${margineP >= 30 ? "bg-green-50 text-green-700" : margineP >= 15 ? "bg-yellow-50 text-yellow-700" : "bg-red-50 text-red-600"}`}>
              {margineP.toFixed(0)}%
            </span>
          )}
        </div>
        {/* Modifica prezzo rapida — sempre visibile */}
        <div className="mt-2" onClick={e => e.stopPropagation()}>
          {!editingPrezzo ? (
            <button data-testid={`btn-imposta-prezzo-${prodotto.id}`}
              onClick={e => { e.stopPropagation(); setInputPrezzo(pv > 0 ? pv.toFixed(2) : ""); setEditingPrezzo(true); }}
              className={`w-full py-1.5 border border-dashed rounded-lg text-xs transition-colors font-medium ${pv > 0 ? "border-green-300 text-green-600 hover:bg-green-50" : "border-amber-300 text-amber-600 hover:bg-amber-50"}`}>
              {pv > 0 ? `✎ Modifica €${pv.toFixed(2)}` : "+ Imposta prezzo"}
            </button>
          ) : (
            <div className="flex items-center gap-1">
              <span className="text-xs text-gray-500">€</span>
              <input autoFocus type="number" step="0.01" placeholder="0.00" value={inputPrezzo}
                onChange={e => setInputPrezzo(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter") salvaPrezzo(e); if (e.key === "Escape") setEditingPrezzo(false); }}
                className="flex-1 border border-[#b8d0c2] rounded-lg px-2 py-1 text-sm text-center focus:ring-2 focus:ring-[#5b7a6b] outline-none" />
              <button onClick={e => { e.stopPropagation(); salvaPrezzo(e); }} disabled={salvando}
                className="px-2 py-1 bg-[#5b7a6b] text-white rounded-lg text-xs hover:bg-[#4d6a5c] disabled:opacity-50">
                {salvando ? "..." : <Save size={12} />}
              </button>
              <button onClick={e => { e.stopPropagation(); setEditingPrezzo(false); }}
                className="px-2 py-1 border border-gray-200 rounded-lg text-xs text-gray-500 hover:bg-gray-50">
                <X size={12} />
              </button>
            </div>
          )}
        </div>
        {(prodotto.pezzi_cartone > 0 || prodotto.peso_pezzo_g > 0) && (
          <div className="flex items-center gap-2 text-xs text-gray-400 mt-1.5">
            {prodotto.pezzi_cartone > 0 && <span>{prodotto.pezzi_cartone} pz/cart</span>}
            {prodotto.peso_pezzo_g > 0 && <span>{prodotto.peso_pezzo_g}g</span>}
            {prodotto.codice_prodotto && <span className="font-mono text-gray-300">{prodotto.codice_prodotto}</span>}
          </div>
        )}
        {badges.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {badges.map((b, i) => <span key={i} className={`text-xs px-2 py-0.5 rounded-full font-medium ${b.color}`}>{b.label}</span>)}
          </div>
        )}
      </div>
    </div>
  );
}

export default ProdottoCard;
