/**
 * prodotti/ModalProdotto.jsx — Modal completo per creazione/modifica prodotto
 */
import { useState, useMemo } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Save, Trash2, X } from "lucide-react";
import { calcolaMargine, CategoriaSelect } from "./constants";

import { API } from "../../../utils/constants";

function ModalProdotto({ prodotto, ricette, onSave, onDelete, onClose, isNew }) {
  const [form, setForm] = useState(() => ({
    nome: "", categoria: "", descrizione: "",
    ricetta_id: "", fonte: "interno",
    pezzi_per_ricetta: "", pezzi_singolo: "",
    pezzi_cartone: prodotto?.pezzi_cartone || "",
    peso_pezzo_g: prodotto?.peso_pezzo_g || "",
    codice_prodotto: "",
    prezzo_vendita: "", costo_produzione: "",
    iva: -1, iva_compresa_aliquota: 10,
    allergeni: [], stagionale: false, stagione_note: "",
    visibile_tablet: true, visibile_ricette: true,
    attivo: true,
    ...(prodotto || {})
  }));
  const [tab, setTab] = useState(prodotto?.fonte === "acquaviva" ? "acquaviva" : prodotto?.fonte === "esterno" ? "esterno" : "interno");
  const [allergenInput, setAllergenInput] = useState((prodotto?.allergeni || []).join(", "));
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showCascadeDialog, setShowCascadeDialog] = useState(false);
  const [cascadeOpts, setCascadeOpts] = useState({ da_prodotti: true, da_ricette: false, da_magazzino: false, da_dizionario: false });

  const ivaIsCompresa = form.iva === -1;
  const ivaCompresaAliquota = form.iva_compresa_aliquota || 10;

  const margini = useMemo(
    () => calcolaMargine(form.prezzo_vendita, form.costo_produzione, form.iva, ivaCompresaAliquota),
    [form.prezzo_vendita, form.costo_produzione, form.iva, ivaCompresaAliquota]
  );

  const set = (key, val) => setForm(f => ({ ...f, [key]: val }));

  const onPrezzoChange = (val) => {
    const newForm = { ...form, prezzo_vendita: val };
    if (val && parseFloat(val) > 0 && newForm.iva !== -1) {
      newForm.iva = -1;
      newForm.iva_compresa_aliquota = form.iva > 0 ? form.iva : 10;
    }
    setForm(newForm);
  };

  const cambiaTab = (nuovoTab) => {
    setTab(nuovoTab);
    const fonteMap = { interno: "interno", acquaviva: "acquaviva", esterno: "esterno" };
    set("fonte", fonteMap[nuovoTab]);
  };

  const onRicettaChange = async (ricettaId) => {
    set("ricetta_id", ricettaId);
    if (!ricettaId) { set("costo_produzione", ""); return; }
    const r = ricette.find(r => r.id === ricettaId);
    if (r) {
      const pzRicetta = parseInt(form.pezzi_per_ricetta) || parseInt(r.porzioni) || 1;
      const costoPz = (r.costo_totale || 0) / pzRicetta;
      set("costo_produzione", Math.round(costoPz * 10000) / 10000);
      if (r.allergeni?.length) setAllergenInput(r.allergeni.join(", "));
    }
  };

  const onPzRicettaChange = (val) => {
    set("pezzi_per_ricetta", val);
    if (form.ricetta_id && val > 0) {
      const r = ricette.find(r => r.id === form.ricetta_id);
      if (r && r.costo_totale > 0) {
        const costoPz = r.costo_totale / parseInt(val);
        set("costo_produzione", Math.round(costoPz * 10000) / 10000);
      }
    }
  };

  const handleSave = async () => {
    if (!form.nome?.trim()) { toast.error("Il nome è obbligatorio"); return; }
    setSaving(true);
    const payload = {
      ...form,
      allergeni: allergenInput.split(",").map(a => a.trim()).filter(Boolean),
      pezzi_per_ricetta: form.pezzi_per_ricetta ? parseInt(form.pezzi_per_ricetta) : null,
      pezzi_cartone: form.pezzi_cartone ? parseInt(form.pezzi_cartone) : null,
      peso_pezzo_g: form.peso_pezzo_g ? parseFloat(form.peso_pezzo_g) : null,
      prezzo_vendita: parseFloat(form.prezzo_vendita) || 0,
      costo_produzione: parseFloat(form.costo_produzione) || 0,
      iva: -1,  // IVA compresa sempre
      iva_compresa_aliquota: 10,  // 10% fisso
      ...margini
    };
    await onSave(payload);
    setSaving(false);
  };

  const eseguiEliminazione = async () => {
    setDeleting(true);
    try {
      const params = new URLSearchParams(cascadeOpts).toString();
      await axios.delete(`${API}/prodotti-vendita/${prodotto.id}/cascade?${params}`);
      onDelete(prodotto.id);
    } catch { toast.error("Errore durante eliminazione"); }
    setDeleting(false);
  };

  const TABS = [{ key: "interno", label: "Nostro" }, { key: "acquaviva", label: "Acquaviva" }, { key: "esterno", label: "Esterno" }];

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-[95vw] max-w-2xl max-h-[92vh] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="bg-gray-800 text-white px-6 py-4 flex items-center justify-between">
          <div>
            <h2 className="font-semibold text-lg">{isNew ? "Nuovo Prodotto" : "Modifica Prodotto"}</h2>
            {!isNew && <p className="text-gray-400 text-xs">{prodotto?.nome}</p>}
          </div>
          <div className="flex items-center gap-3">
            {!isNew && !showCascadeDialog && (
              <button data-testid="btn-delete-prodotto" onClick={() => setShowCascadeDialog(true)}
                className="text-red-400 hover:text-red-300 flex items-center gap-1 text-sm">
                <Trash2 size={15} /> Elimina
              </button>
            )}
            {showCascadeDialog && (
              <div className="fixed inset-0 bg-black/60 z-[60] flex items-center justify-center p-4" onClick={() => setShowCascadeDialog(false)}>
                <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6" onClick={e => e.stopPropagation()}>
                  <div className="flex items-center gap-3 mb-4">
                    <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center"><Trash2 size={18} className="text-red-600" /></div>
                    <div>
                      <h3 className="font-semibold text-gray-900">Elimina prodotto</h3>
                      <p className="text-xs text-gray-500 truncate max-w-[180px]">{prodotto?.nome}</p>
                    </div>
                  </div>
                  <p className="text-sm text-gray-600 mb-4">Scegli da dove eliminare il prodotto:</p>
                  <div className="space-y-2 mb-5">
                    {[
                      { key: "da_prodotti", label: "Catalogo prodotti in vendita", desc: "Rimuove il prodotto dal catalogo", required: true },
                      { key: "da_ricette", label: "Ingredienti nelle ricette", desc: "Rimuove da tutte le ricette che lo usano" },
                      { key: "da_magazzino", label: "Magazzino/Inventario", desc: "Rimuove la voce di magazzino" },
                      { key: "da_dizionario", label: "Dizionario prezzi", desc: "Rimuove il riferimento prezzi" },
                    ].map(opt => (
                      <label key={opt.key} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-all ${cascadeOpts[opt.key] ? "border-red-300 bg-red-50" : "border-gray-200 hover:border-gray-300"}`}>
                        <input type="checkbox" checked={cascadeOpts[opt.key]} disabled={opt.required}
                          onChange={e => setCascadeOpts(prev => ({ ...prev, [opt.key]: e.target.checked }))} className="mt-0.5" />
                        <div>
                          <p className="text-sm font-medium text-gray-800">{opt.label}</p>
                          <p className="text-xs text-gray-500">{opt.desc}</p>
                          {opt.required && <span className="text-xs text-red-500 font-medium">Obbligatorio</span>}
                        </div>
                      </label>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => setShowCascadeDialog(false)} className="flex-1 py-2 border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-gray-50">Annulla</button>
                    <button onClick={eseguiEliminazione} disabled={deleting}
                      className="flex-1 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 disabled:opacity-50">
                      {deleting ? "Eliminazione..." : "Conferma eliminazione"}
                    </button>
                  </div>
                </div>
              </div>
            )}
            <button onClick={onClose} className="text-gray-400 hover:text-white"><X size={20} /></button>
          </div>
        </div>

        {/* Tabs fonte */}
        <div className="flex bg-gray-100 border-b border-gray-200">
          {TABS.map(t => (
            <button key={t.key} onClick={() => cambiaTab(t.key)}
              className={`flex-1 py-2.5 text-sm font-medium transition-all ${tab === t.key ? "bg-white text-[#5b7a6b] border-b-2 border-[#5b7a6b]" : "text-gray-500 hover:text-gray-700"}`}>
              {t.label}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1 p-6 space-y-5">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">Nome *</label>
              <input data-testid="input-nome-prodotto"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#5b7a6b]"
                placeholder="es. Babà" value={form.nome} onChange={e => set("nome", e.target.value)} />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">Categoria</label>
              <CategoriaSelect value={form.categoria} onChange={v => set("categoria", v)} />
            </div>
          </div>

          {tab === "interno" && (
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">Ricetta collegata</label>
              <select data-testid="select-ricetta"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#5b7a6b]"
                value={form.ricetta_id || ""} onChange={e => onRicettaChange(e.target.value)}>
                <option value="">-- Nessuna --</option>
                {ricette.map(r => <option key={r.id} value={r.id}>{r.nome} {r.costo_totale ? `(€${(r.costo_totale).toFixed(4)})` : ""}</option>)}
              </select>
            </div>
          )}

          {(tab === "acquaviva" || tab === "esterno") && (
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">Fornitore</label>
              <input className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                placeholder="Nome fornitore" value={form.fornitore || ""} onChange={e => set("fornitore", e.target.value)} />
            </div>
          )}

          {/* Prezzi e Margini */}
          <div className="bg-gray-50 rounded-xl p-4">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Prezzi & Margini</h3>
            <div className="grid grid-cols-3 gap-3 mb-3">
              <div>
                <label className="text-xs text-gray-500 mb-1 block">Costo prod. (€)</label>
                <input data-testid="input-costo" type="number" step="0.0001"
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#5b7a6b]"
                  placeholder="0,0000" value={form.costo_produzione} onChange={e => set("costo_produzione", e.target.value)} />
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">
                  {ivaIsCompresa ? "Prezzo (IVA inclusa) (€)" : "Prezzo Vendita (€)"}
                </label>
                <input data-testid="input-prezzo-vendita" type="number" step="0.01"
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#5b7a6b]"
                  placeholder="0,00" value={form.prezzo_vendita} onChange={e => onPrezzoChange(e.target.value)} />
                {ivaIsCompresa && margini.prezzo_netto > 0 && (
                  <p className="text-xs text-gray-400 mt-0.5">Netto: €{margini.prezzo_netto.toFixed(2)} (esclusa IVA {ivaCompresaAliquota}%)</p>
                )}
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">IVA</label>
                <div className="w-full border border-green-200 rounded-lg px-3 py-2 text-sm bg-green-50 text-green-700 font-medium">
                  IVA 10% compresa
                </div>
              </div>
            </div>

            {/* Quick margine buttons */}
            <div className="mb-3">
              {(() => {
                const cpInput = parseFloat(form.costo_produzione) || 0;
                const cpPezzo = cpInput;
                return (
                  <>
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-xs text-gray-500">
                        Imposta da margine {ivaIsCompresa ? <span className="text-[#5b7a6b] font-medium">(prezzo IVA {ivaCompresaAliquota}% inclusa)</span> : ""}
                        <span className="ml-1 text-gray-400">— prezzo per pezzo</span>
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {[20, 25, 30, 35, 40, 50, 100, 150, 200, 250, 300].map(pct => {
                        let pvNetto;
                        if (pct < 100) {
                          pvNetto = cpPezzo > 0 ? cpPezzo / (1 - pct / 100) : 0;
                        } else {
                          pvNetto = cpPezzo * (1 + pct / 100);
                        }
                        const pvFinale = ivaIsCompresa ? pvNetto * (1 + ivaCompresaAliquota / 100) : pvNetto;
                        const pvRound = Math.round(pvFinale * 100) / 100;
                        const pvLabel = pvRound > 0 ? (pvRound < 0.05 ? `€${pvFinale.toFixed(4)}` : `€${pvRound.toFixed(2)}`) : "?";
                        const isMarkup = pct >= 100;
                        return (
                          <button key={pct} data-testid={`btn-margine-${pct}`}
                            title={isMarkup ? `Markup ${pct}% sul costo` : `Margine ${pct}% sul prezzo`}
                            onClick={() => { if (cpPezzo <= 0) { toast.error("Inserisci prima il costo produzione"); return; } set("prezzo_vendita", pvRound || pvFinale.toFixed(4)); }}
                            className={`px-3 py-1.5 border rounded-lg text-xs transition-all ${isMarkup ? "bg-amber-50 border-amber-200 hover:border-amber-500 hover:bg-amber-100 text-amber-800" : "bg-white border-gray-200 hover:border-[#b8d0c2] hover:bg-[#f2f6f3]"}`}>
                            {pct}% → {pvLabel}
                          </button>
                        );
                      })}
                    </div>
                  </>
                );
              })()}
            </div>

            {parseFloat(form.prezzo_vendita) > 0 && (
              <div className="flex gap-4 text-sm bg-white rounded-lg p-3 border border-gray-100">
                <div><span className="text-xs text-gray-400">Costo</span><p className="font-medium text-gray-600">€{(parseFloat(form.costo_produzione)||0).toFixed(4)}</p></div>
                <div className="border-l border-gray-100 pl-4"><span className="text-xs text-gray-400">Prezzo netto</span><p className="font-medium text-gray-700">€{margini.prezzo_netto.toFixed(2)}</p></div>
                <div><span className="text-xs text-gray-400">Margine €</span><p className={`font-semibold ${margini.margine_euro >= 0 ? "text-green-600" : "text-red-600"}`}>€{margini.margine_euro.toFixed(2)}</p></div>
                <div><span className="text-xs text-gray-400">Margine %</span><p className={`font-semibold ${margini.margine_pct >= 20 ? "text-green-600" : margini.margine_pct >= 10 ? "text-yellow-600" : "text-red-600"}`}>{margini.margine_pct.toFixed(1)}%</p></div>
                <div className="border-l border-gray-100 pl-4">
                  <span className="text-xs text-gray-400">{ivaIsCompresa ? "Prezzo (IVA incl.)" : form.iva === 0 ? "Esente IVA" : `c/IVA ${margini.aliquota_effettiva}%`}</span>
                  <p className="font-semibold text-[#5b7a6b]">€{margini.prezzo_ivato.toFixed(2)}</p>
                </div>
              </div>
            )}
          </div>

          {tab === "interno" && (
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Rese ricetta</h3>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-500 mb-1 block">Pz/Ricetta <span className="text-gray-400 font-normal ml-1">(pezzi totali da una ricetta)</span></label>
                  <input data-testid="input-pz-ricetta" type="number" min="1"
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#5b7a6b]"
                    placeholder="es. 12" value={form.pezzi_per_ricetta || ""} onChange={e => onPzRicettaChange(e.target.value)} />
                </div>
                <div>
                  <label className="text-xs text-gray-500 mb-1 block">Pz/Singolo <span className="text-gray-400 font-normal ml-1">(pezzi in una confezione singola)</span></label>
                  <input data-testid="input-pz-singolo" type="number" min="1"
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#5b7a6b]"
                    placeholder="es. 1" value={form.pezzi_singolo || ""} onChange={e => set("pezzi_singolo", e.target.value)} />
                </div>
              </div>
            </div>
          )}

          <div>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Dettagli confezione <span className="font-normal text-gray-400">(opzionale)</span></h3>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="text-xs text-gray-500 mb-1 block">Pz/Cartone</label>
                {tab === "acquaviva" && prodotto?.pezzi_cartone > 0 ? (
                  <div className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-gray-50 text-gray-700 font-medium">{prodotto.pezzi_cartone} pz</div>
                ) : (
                  <input data-testid="input-pz-cartone" type="number" min="1"
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                    placeholder="es. 30" value={form.pezzi_cartone != null && form.pezzi_cartone !== "" ? form.pezzi_cartone : ""}
                    onChange={e => set("pezzi_cartone", e.target.value)} />
                )}
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">Peso pezzo (g)</label>
                {tab === "acquaviva" && prodotto?.peso_pezzo_g > 0 ? (
                  <div className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-gray-50 text-gray-700 font-medium">{prodotto.peso_pezzo_g} g</div>
                ) : (
                  <input data-testid="input-peso-pezzo" type="number" step="0.1"
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                    placeholder="es. 70" value={form.peso_pezzo_g != null && form.peso_pezzo_g !== "" ? form.peso_pezzo_g : ""}
                    onChange={e => set("peso_pezzo_g", e.target.value)} />
                )}
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">Codice</label>
                <input data-testid="input-codice" className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                  placeholder="Codice articolo" value={form.codice_prodotto || ""} onChange={e => set("codice_prodotto", e.target.value)} />
              </div>
            </div>
          </div>

          <div>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Visibilità & Disponibilità</h3>
            <div className="grid grid-cols-2 gap-3">
              <label className="flex items-center gap-2 cursor-pointer bg-gray-50 rounded-lg px-3 py-2.5">
                <input type="checkbox" checked={form.visibile_tablet} onChange={e => set("visibile_tablet", e.target.checked)} className="rounded text-[#5b7a6b]" />
                <div><p className="text-sm font-medium text-gray-700">Visibile su Tablet</p><p className="text-xs text-gray-400">Nella vista comande/produzione</p></div>
              </label>
              <label className="flex items-center gap-2 cursor-pointer bg-gray-50 rounded-lg px-3 py-2.5">
                <input type="checkbox" checked={form.visibile_ricette} onChange={e => set("visibile_ricette", e.target.checked)} className="rounded text-[#5b7a6b]" />
                <div><p className="text-sm font-medium text-gray-700">Visibile in Ricette</p><p className="text-xs text-gray-400">Nella selezione ricette</p></div>
              </label>
              <label className="flex items-center gap-2 cursor-pointer bg-amber-50 rounded-lg px-3 py-2.5 border border-amber-200">
                <input type="checkbox" checked={form.stagionale} onChange={e => set("stagionale", e.target.checked)} className="rounded text-amber-500" />
                <div><p className="text-sm font-medium text-amber-700">Prodotto Stagionale</p><p className="text-xs text-amber-500">es. Panettone, Cassata, Mustaccioli</p></div>
              </label>
              <label className="flex items-center gap-2 cursor-pointer bg-gray-50 rounded-lg px-3 py-2.5">
                <input type="checkbox" checked={form.attivo} onChange={e => set("attivo", e.target.checked)} className="rounded text-green-600" />
                <div><p className="text-sm font-medium text-gray-700">Attivo</p><p className="text-xs text-gray-400">Disponibile alla produzione</p></div>
              </label>
            </div>
            {form.stagionale && (
              <input className="mt-2 w-full border border-amber-200 rounded-lg px-3 py-2 text-sm bg-amber-50"
                placeholder="Note stagionalità (es. Solo Natale, Solo Estate...)"
                value={form.stagione_note || ""} onChange={e => set("stagione_note", e.target.value)} />
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">Allergeni <span className="font-normal text-gray-400">(separati da virgola)</span></label>
              <textarea className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm resize-none" rows={2}
                placeholder="es. glutine, latte, uova" value={allergenInput} onChange={e => setAllergenInput(e.target.value)} />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">Descrizione</label>
              <textarea className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm resize-none" rows={2}
                placeholder="Descrizione per menu, etichette..." value={form.descrizione || ""} onChange={e => set("descrizione", e.target.value)} />
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-between bg-gray-50">
          <div className="text-xs text-gray-400">{prodotto?.id && <span>ID: {prodotto.id.slice(0, 8)}...</span>}</div>
          <div className="flex gap-3">
            <button onClick={onClose} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">Annulla</button>
            <button data-testid="btn-salva-prodotto" onClick={handleSave} disabled={saving}
              className="px-6 py-2 bg-[#5b7a6b] text-white rounded-lg text-sm font-medium hover:bg-[#4d6a5c] transition-all flex items-center gap-2 disabled:opacity-50">
              <Save size={14} /> {saving ? "Salvataggio..." : "Salva"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ModalProdotto;
