import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { X, MoreVertical, Edit, Copy, Printer, Trash2 } from "lucide-react";
import { apiError } from "../../utils/apiError";
import { API } from "../../utils/constants";
import { stampaDoc } from "../../utils/stampa";
import { chiediTesto } from "../../utils/conferma";
import RicetteDashboardView from "./RicetteDashboardView";
import TabIngredienti from "./scheda/TabIngredienti";
import TabAllergeni from "./scheda/TabAllergeni";
import TabNutrizionali from "./scheda/TabNutrizionali";

const labelReparto = (r) => ({ pasticceria: "Pasticceria", rosticceria: "Rosticceria", bar: "Bar", altro: "Altro", tutti: "Tutte" }[r] || "Altro");

function RicettaModal({ title, color, values, setValues, onClose, onSave, saving }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">
        <div className={`p-4 ${color} text-white flex items-center justify-between`}>
          <h3 className="font-black">{title}</h3>
          <button onClick={onClose}><X size={18} /></button>
        </div>
        <div className="p-4 space-y-3">
          <input autoFocus value={values.nome} onChange={e => setValues(v => ({ ...v, nome: e.target.value }))} placeholder="Nome ricetta" className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm" />
          <div className="grid grid-cols-2 gap-3">
            <input type="number" min="1" value={values.porzioni} onChange={e => setValues(v => ({ ...v, porzioni: e.target.value }))} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm" />
            <select value={values.reparto} onChange={e => setValues(v => ({ ...v, reparto: e.target.value }))} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white">
              <option value="pasticceria">Pasticceria</option>
              <option value="rosticceria">Rosticceria</option>
              <option value="bar">Bar</option>
              <option value="altro">Altro</option>
            </select>
          </div>
          {"note" in values && <textarea value={values.note} onChange={e => setValues(v => ({ ...v, note: e.target.value }))} placeholder="Note" rows={3} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm resize-none" />}
          <div className="flex gap-2 pt-2">
            <button onClick={onClose} className="flex-1 py-2 border border-slate-200 rounded-lg text-sm">Annulla</button>
            <button onClick={onSave} disabled={saving} className={`flex-1 py-2 ${color} text-white rounded-lg text-sm font-bold disabled:opacity-60`}>{saving ? "Salvo..." : "Salva"}</button>
          </div>
        </div>
      </div>
    </div>
  );
}

export const SchedaProdottoView = ({
  ricette = [],
  loadingRicette = false,
  onDeleteRicetta,
  onAddRicetta,
  onUpdateRicetta,
  searchRicette,
  setSearchRicette,
  onRicetteUpdate,
}) => {
  const [selected, setSelected] = useState(null);
  const [modalView, setModalView] = useState("ingredienti");
  const [showActions, setShowActions] = useState(false);
  const [showNuova, setShowNuova] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [saving, setSaving] = useState(false);
  const [duplicating, setDuplicating] = useState(false);
  const [nuova, setNuova] = useState({ nome: "", porzioni: 1, reparto: "pasticceria" });
  const [edit, setEdit] = useState({ nome: "", porzioni: 1, reparto: "altro", note: "" });

  const refresh = () => onRicetteUpdate && onRicetteUpdate();

  // Deep-link dal Supervisore HACCP: apri direttamente la ricetta indicata
  useEffect(() => {
    if (loadingRicette || !ricette.length) return;
    try {
      const raw = sessionStorage.getItem("supervisore_apri");
      if (!raw) return;
      const { id, tab } = JSON.parse(raw);
      const r = ricette.find(x => x.id === id);
      if (r) { sessionStorage.removeItem("supervisore_apri"); openRicetta(r, tab || "allergeni"); }
    } catch { sessionStorage.removeItem("supervisore_apri"); }
  }, [loadingRicette, ricette]); // eslint-disable-line react-hooks/exhaustive-deps

  const openRicetta = (r, view = "produci") => {
    setSelected(r);
    setModalView(view);
    setShowActions(false);
  };

  const createRicetta = async () => {
    const nome = nuova.nome.trim();
    if (!nome) return toast.error("Inserisci il nome della ricetta");
    setSaving(true);
    try {
      const creata = await onAddRicetta({ nome, porzioni: Number(nuova.porzioni) || 1, reparto: nuova.reparto, ingredienti: [], ingredienti_dettaglio: [] });
      setShowNuova(false);
      setNuova({ nome: "", porzioni: 1, reparto: "pasticceria" });
      refresh();
      if (creata && creata.id) {
        setSelected(creata);
        setModalView("ingredienti");
        toast.success("Ricetta creata — aggiungi gli ingredienti");
      }
    } finally {
      setSaving(false);
    }
  };

  const openEdit = () => {
    if (!selected) return;
    setEdit({ nome: selected.nome || "", porzioni: selected.porzioni || 1, reparto: selected.reparto || "altro", note: selected.note || "" });
    setShowEdit(true);
  };

  const saveEdit = async () => {
    const nome = edit.nome.trim();
    if (!nome || !selected) return toast.error("Il nome e obbligatorio");
    setSaving(true);
    try {
      const updated = { ...selected, nome, porzioni: Number(edit.porzioni) || 1, reparto: edit.reparto, note: edit.note };
      await onUpdateRicetta(selected.id, updated);
      setSelected(updated);
      setShowEdit(false);
      refresh();
      toast.success("Ricetta aggiornata");
    } finally {
      setSaving(false);
    }
  };

  const duplicateRicetta = async (ricetta) => {
    const base = ricetta || selected;
    if (!base || duplicating) return;
    const varianti = ["Cioccolato", "Pistacchio", "Nutella", "Crema", "Fiordilatte", "Caprese"];
    const scelta = (await chiediTesto(`Variante da creare per ${base.nome}\nEsempi: ${varianti.join(", ")}`, { titolo: "Nuova variante", valore: varianti[0] }))?.trim();
    if (!scelta) return;
    const chosen = `${base.nome} ${scelta}`.replace(/\s+/g, " ").trim();
    setDuplicating(true);
    try {
      const dettagli = (base.ingredienti_dettaglio || []).map(i => ({
        nome: i.nome,
        quantita: i.quantita,
        unita_misura: i.unita_misura || i.unita || "g",
        prezzo_kg: i.prezzo_kg,
        costo_unitario: i.costo_unitario,
        allergeni: i.allergeni || [],
      }));
      await axios.post(`${API}/ricette`, {
        nome: chosen,
        porzioni: base.porzioni || 1,
        reparto: base.reparto || "altro",
        note: `Variante ${scelta} da ${base.nome}`,
        ingredienti: dettagli.length ? dettagli.map(i => i.nome).filter(Boolean) : [...(base.ingredienti || [])],
        ingredienti_dettaglio: dettagli,
        ricetta_base_id: base.ricetta_base_id || base.id,
        ricetta_base_nome: base.ricetta_base_nome || base.nome,
        ingrediente_variante: { nome: scelta, quantita: 0, unita: "g" },
        // Il backend clona la foto in un file autonomo: non salvare lo stesso
        // URL della base, altrimenti un cambio si propaga a tutte le varianti.
        foto_url: "",
      });
      toast.success(`Variante creata: ${chosen}`);
      refresh();
    } catch (e) {
      toast.error("Errore duplicazione: " + apiError(e));
    } finally {
      setDuplicating(false);
    }
  };

  const deleteSelected = () => {
    if (!selected) return;
    setShowActions(false);
    toast(`Eliminare "${selected.nome}"?`, {
      description: "L'operazione non puo essere annullata.",
      action: { label: "Elimina", onClick: async () => { await onDeleteRicetta(selected.id); setSelected(null); refresh(); } },
      cancel: { label: "Annulla", onClick: () => {} },
      duration: 8000,
    });
  };

  const printSelected = () => {
    if (!selected) return;
    setShowActions(false);
    stampaDoc({
      categoria: "ricette",
      url: `${API}/ricette/${selected.id}/pdf-scheda`,
      formato: "html",
      titolo: `Scheda ${selected.nome || selected.id}`,
    }).catch(() => {});
  };

  return (
    <>
      <RicetteDashboardView
        ricette={ricette}
        loadingRicette={loadingRicette}
        searchRicette={searchRicette}
        setSearchRicette={setSearchRicette}
        onRicetteUpdate={refresh}
        onOpenRicetta={openRicetta}
        onCloneRicetta={duplicateRicetta}
        onNuovaRicetta={() => setShowNuova(true)}
      />

      {selected && (
        <div className="fixed inset-0 z-[120] bg-black/50 flex items-end md:items-center justify-center p-3" onClick={() => setSelected(null)}>
          <div className="bg-white rounded-2xl w-full max-w-lg max-h-[92vh] flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-slate-100">
              <div className="min-w-0 flex-1">
                <h3 className="font-black text-slate-800 capitalize truncate leading-tight">{selected.nome}</h3>
                <p className="text-xs text-slate-400">{modalView === "allergeni" ? "Allergeni" : modalView === "nutrizionali" ? "Valori nutrizionali" : "Ingredienti"} · {labelReparto(selected.reparto)}</p>
              </div>
              <div className="relative flex items-center gap-1">
                <button onClick={() => setModalView("ingredienti")} title="Modifica ingredienti" className="w-9 h-9 bg-[#f2f6f3] text-[#5b7a6b] rounded-lg hover:bg-[#dce8e0] inline-flex items-center justify-center"><Edit size={16} /></button>
                <button onClick={() => setShowActions(v => !v)} className="w-9 h-9 bg-white border border-slate-200 text-slate-600 rounded-lg hover:bg-slate-50 inline-flex items-center justify-center" title="Altre azioni"><MoreVertical size={18} /></button>
                {showActions && <div className="absolute right-10 top-10 z-20 w-52 bg-white border border-slate-200 rounded-lg shadow-xl py-1"><button onClick={() => { setShowActions(false); openEdit(); }} className="w-full px-3 py-2 text-left text-sm font-semibold text-slate-700 hover:bg-slate-50 flex items-center gap-2"><Edit size={15} /> Modifica nome/reparto</button><button onClick={() => duplicateRicetta(selected)} disabled={duplicating} className="w-full px-3 py-2 text-left text-sm font-semibold text-slate-700 hover:bg-slate-50 flex items-center gap-2 disabled:opacity-60"><Copy size={15} /> {duplicating ? "Copio..." : "Crea variante"}</button><button onClick={printSelected} className="w-full px-3 py-2 text-left text-sm font-semibold text-slate-700 hover:bg-slate-50 flex items-center gap-2"><Printer size={15} /> Stampa scheda</button><button onClick={deleteSelected} className="w-full px-3 py-2 text-left text-sm font-semibold text-red-600 hover:bg-red-50 flex items-center gap-2"><Trash2 size={15} /> Elimina</button></div>}
                <button onClick={() => setSelected(null)} className="w-9 h-9 text-slate-400 hover:bg-slate-50 rounded-lg inline-flex items-center justify-center"><X size={18} /></button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              {modalView === "ingredienti" && <TabIngredienti ricetta={selected} onUpdated={refresh} />}
              {modalView === "allergeni" && <TabAllergeni ricetta={selected} onUpdated={refresh} />}
              {modalView === "nutrizionali" && <TabNutrizionali ricettaId={selected.id} />}
            </div>
          </div>
        </div>
      )}

      {showNuova && <RicettaModal title="Nuova ricetta" color="bg-green-600" values={nuova} setValues={setNuova} onClose={() => setShowNuova(false)} onSave={createRicetta} saving={saving} />}
      {showEdit && <RicettaModal title="Modifica ricetta" color="bg-[#5b7a6b]" values={edit} setValues={setEdit} onClose={() => setShowEdit(false)} onSave={saveEdit} saving={saving} />}
    </>
  );
};
