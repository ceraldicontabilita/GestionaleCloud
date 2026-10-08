import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { API } from "../../../utils/constants";

// Nota libera dell'operatore sulla scheda di ricevimento di una fattura.
// Estratto da FornitoriList.jsx (refactor 25/07/2026): è usato SOLO da
// SchedeRicevimentoPanel, che prima lo referenziava senza import (crash
// "NoteRicevimento is not defined" all'apertura del pannello).
const NoteRicevimento = ({ idFattura }) => {
  const [nota, setNota]       = useState("");
  const [salvata, setSalvata] = useState("");
  const [saving, setSaving]   = useState(false);
  const [loaded, setLoaded]   = useState(false);

  useEffect(() => {
    axios.get(`${API}/fornitori/note-ricevimento/${idFattura}`)
      .then(r => { setNota(r.data.nota || ""); setSalvata(r.data.nota || ""); })
      .catch(() => {})
      .finally(() => setLoaded(true));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idFattura]);

  const salva = async () => {
    setSaving(true);
    try {
      await axios.post(`${API}/fornitori/schede-ricevimento/${idFattura}/nota?nota=${encodeURIComponent(nota)}`);
      setSalvata(nota);
      toast.success("Nota salvata");
    } catch { toast.error("Errore salvataggio nota"); }
    setSaving(false);
  };

  if (!loaded) return null;

  return (
    <div className="mt-2 pt-2 border-t border-gray-100">
      <p className="text-[10px] text-gray-500 font-medium mb-1 uppercase tracking-wide">Note operatore</p>
      <div className="flex gap-2">
        <textarea
          value={nota}
          onChange={e => setNota(e.target.value)}
          placeholder="Anomalie, non conformità, stato imballaggio..."
          className="flex-1 text-[11px] border border-gray-200 rounded-lg px-2 py-1.5 resize-none h-14 focus:ring-1 focus:ring-[#5b7a6b] outline-none"
          data-testid={`nota-ricevimento-${idFattura}`}
        />
        <button
          onClick={salva}
          disabled={saving || nota === salvata}
          className={`px-3 py-1 rounded-lg text-[10px] font-bold transition-all flex-shrink-0 self-end ${
            nota !== salvata && !saving
              ? "bg-[#5b7a6b] text-white hover:bg-[#4d6a5c]"
              : "bg-gray-100 text-gray-400 cursor-not-allowed"
          }`}
        >
          {saving ? "..." : "Salva"}
        </button>
      </div>
      {salvata && <p className="text-[9px] text-green-600 mt-1">Nota salvata: {salvata.slice(0,60)}</p>}
    </div>
  );
};

export default NoteRicevimento;
