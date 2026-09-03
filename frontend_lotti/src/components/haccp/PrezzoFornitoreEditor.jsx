import { useEffect, useState } from "react";
import axios from "axios";
import { Save } from "lucide-react";
import { toast } from "sonner";
import { API } from "../../utils/constants";

const numeroItaliano = (valore) => Number(String(valore ?? "").replace(",", "."));

/** Salva il prezzo netto dichiarato dal fornitore senza confonderlo con il
 * prezzo realmente pagato, che continua ad arrivare dalle fatture XML. */
export default function PrezzoFornitoreEditor({ prodotto, fonte, fornitore, codiceArticolo, onSaved, compatto = false }) {
  const [valore, setValore] = useState("");
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    const corrente = Number(prodotto?.prezzo_fornitore ?? prodotto?.prezzoFornitore ?? 0);
    setValore(corrente > 0 ? String(corrente).replace(".", ",") : "");
  }, [prodotto?.id, prodotto?.prezzo_fornitore, prodotto?.prezzoFornitore]);

  const salva = async (event) => {
    event?.stopPropagation();
    const prezzo = numeroItaliano(valore);
    if (!Number.isFinite(prezzo) || prezzo <= 0) {
      toast.error("Inserisci un prezzo maggiore di zero");
      return;
    }
    setSalvando(true);
    try {
      const response = await axios.put(`${API}/cataloghi/prezzo`, {
        fonte,
        fornitore: fornitore || fonte,
        prodotto_id: prodotto?.id || "",
        codice_articolo: codiceArticolo || prodotto?.codice_articolo || prodotto?.codice || "",
        prezzo,
      });
      onSaved?.(response.data);
      toast.success(`Prezzo fornitore salvato: €${prezzo.toFixed(2)}`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Impossibile salvare il prezzo");
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className={compatto ? "space-y-1" : "rounded-xl border border-blue-100 bg-blue-50 p-3 space-y-2"}
      onClick={(event) => event.stopPropagation()}>
      <label className="block text-[10px] font-bold uppercase tracking-wide text-blue-700">
        Prezzo netto (IVA esclusa)
      </label>
      <div className="flex gap-1.5">
        <div className="relative flex-1 min-w-0">
          <span className="absolute left-2 top-1/2 -translate-y-1/2 text-xs text-gray-500">€</span>
          <input
            value={valore}
            onChange={(event) => setValore(event.target.value)}
            onKeyDown={(event) => { if (event.key === "Enter") salva(event); }}
            inputMode="decimal"
            aria-label="Prezzo comunicato dal fornitore"
            placeholder="0,00"
            className="w-full rounded-lg border border-blue-200 bg-white py-1.5 pl-6 pr-2 text-sm font-semibold outline-none focus:border-blue-500"
          />
        </div>
        <button type="button" onClick={salva} disabled={salvando}
          title="Salva prezzo comunicato dal fornitore"
          className="rounded-lg bg-blue-700 px-2.5 text-white disabled:opacity-50">
          <Save size={14} />
        </button>
      </div>
      {!compatto && <p className="text-[10px] text-blue-700/80">Usato nell’ordine finché una fattura XML registra il prezzo realmente pagato.</p>}
    </div>
  );
}
