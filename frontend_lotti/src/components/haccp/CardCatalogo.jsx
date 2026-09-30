/**
 * CardCatalogo — l'unica card prodotto di tutti i cataloghi fornitori.
 *
 * Solo l'indispensabile: foto, nome, prezzo, l'eventuale fornitore che costa
 * meno (nome e prezzo, niente frasi) e i due gesti da mani sporche: Acquista
 * e Al ricettario. Codice, descrizione, prezzo netto da scrivere, preferito
 * e scheda tecnica stanno nel dettaglio, che si apre toccando la card.
 */
import { Check, Package, Plus, ShoppingCart, TrendingDown } from "lucide-react";

const COLORI_FOTO = {
  amber: "bg-amber-50", rose: "bg-rose-50", orange: "bg-orange-50",
  yellow: "bg-yellow-50", sage: "bg-[#f2f6f3]",
};

/** Riga di confronto: solo chi costa meno e a quanto. `null` se non c'e' confronto. */
export function rigaConfronto(c, formatta) {
  if (!c || !c.migliore) return null;
  if (c.questo_migliore) {
    return { tipo: "qui", testo: `Il più conveniente · ${formatta(c.prezzo_pezzo)}` };
  }
  return { tipo: "altrove", testo: `Meglio da ${c.migliore} · ${formatta(c.migliore_prezzo_pezzo)}` };
}

export default function CardCatalogo({
  nome, foto, prezzo, notaPrezzo, confronto, inCart, inRicette, preferito,
  colore = "sage", onApri, onCarrello, onRicetta, onPreferito, testId,
}) {
  const stop = (fn) => (e) => { e.stopPropagation(); fn?.(); };
  return (
    <div
      data-testid={testId}
      onClick={onApri}
      className="flex cursor-pointer flex-col gap-3 rounded-2xl border border-[#e6e0d4] bg-[#fffefb] p-3 shadow-sm"
    >
      <div className="flex gap-3">
        <div className={`relative flex h-24 w-24 flex-shrink-0 items-center justify-center overflow-hidden rounded-xl ${COLORI_FOTO[colore] || COLORI_FOTO.sage}`}>
          {foto ? (
            <img src={foto} alt="" className="h-full w-full object-contain p-1.5"
              onError={(e) => { e.target.style.display = "none"; }} />
          ) : (
            <Package size={30} className="text-[#5b7a6b] opacity-30" aria-hidden="true" />
          )}
          {onPreferito && (
            <button type="button" onClick={stop(onPreferito)}
              aria-label={preferito ? "Togli dai preferiti colazione" : "Segna come preferito colazione"}
              className={`absolute left-1 top-1 flex h-7 w-7 items-center justify-center rounded-full text-sm ${preferito ? "bg-white text-[#c4894a]" : "bg-black/30 text-white"}`}>
              {preferito ? "★" : "☆"}
            </button>
          )}
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <p className="m-0 line-clamp-3 text-[15px] font-bold leading-snug text-[#2a3329]">{nome}</p>
          {prezzo ? (
            <p className="m-0 flex flex-wrap items-baseline gap-x-2 text-[17px] font-extrabold tabular-nums text-[#3f5a4e]">
              {prezzo}
              {notaPrezzo && <span className="text-[11px] font-semibold text-[#8a7f70]">{notaPrezzo}</span>}
            </p>
          ) : (
            <p className="m-0 text-[13px] text-[#8a7f70]">Prezzo non disponibile</p>
          )}
          {confronto && (
            <p className={`m-0 flex items-center gap-1 rounded-lg px-2 py-1 text-[12px] font-bold ${confronto.tipo === "qui" ? "bg-[#eef3ef] text-[#3d8168]" : "bg-[#fbf3e8] text-[#7a5a2e]"}`}
              data-testid="riga-confronto">
              <TrendingDown size={13} aria-hidden="true" /> {confronto.testo}
            </p>
          )}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <button type="button" onClick={stop(onCarrello)} aria-pressed={!!inCart}
          className={`flex min-h-[44px] items-center justify-center gap-1.5 rounded-xl border text-[14px] font-bold ${inCart ? "border-[#cfe3d8] bg-[#e2efe8] text-[#3d8168]" : "border-[#ecd9b8] bg-[#fbf3e8] text-[#7a5a2e]"}`}>
          {inCart ? <Check size={16} aria-hidden="true" /> : <ShoppingCart size={16} aria-hidden="true" />}
          {inCart ? "Nel carrello" : "Acquista"}
        </button>
        <button type="button" onClick={stop(onRicetta)} aria-pressed={!!inRicette}
          className={`flex min-h-[44px] items-center justify-center gap-1.5 rounded-xl border text-[14px] font-bold ${inRicette ? "border-[#cfe3d8] bg-[#e2efe8] text-[#3d8168]" : "border-[#dce8e0] bg-[#f2f6f3] text-[#3f5a4e]"}`}>
          {inRicette ? <Check size={16} aria-hidden="true" /> : <Plus size={16} aria-hidden="true" />}
          {inRicette ? "Nel ricettario" : "Al ricettario"}
        </button>
      </div>
    </div>
  );
}

// Le carte occupano tutta la larghezza sul telefono e si affiancano sui monitor.
export const GRIGLIA_CARD = "grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3";
