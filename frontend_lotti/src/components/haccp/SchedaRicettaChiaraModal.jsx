import { ChefHat, Pencil, X } from "lucide-react";
import DosiRicetta from "./shared/DosiRicetta";

const righe = (value) => String(value || "").split(/\r?\n/).map(x => x.trim()).filter(Boolean);

export default function SchedaRicettaChiaraModal({ ricetta, onClose, onProduci, onModifica, onVisibilita, cambiandoVisibilita = false }) {
  if (!ricetta) return null;
  const soloLettura = ricetta.origine === "archivio" || ricetta.sola_lettura;
  const dallaFonte = righe(ricetta.ingredienti_testo);
  const procedimento = soloLettura
    ? (ricetta.procedimento_testo || "Procedimento non indicato nella fonte.")
    : (ricetta.procedimento_testo || "Procedimento non ancora indicato.");
  const note = ricetta.note || ricetta.note_archivio || "";
  const fonte = ricetta.fonte_archivio || "Ricetta Ceraldi";
  const provenienza = ricetta.provenienza_archivio || {};

  return (
    <div className="fixed inset-0 z-[150] flex items-end justify-center bg-black/55 p-2 md:items-center md:p-6" onClick={onClose}>
      <article className="max-h-[94vh] w-full max-w-5xl overflow-y-auto rounded-t-[28px] bg-[#fffdf8] shadow-2xl md:rounded-[28px]" onClick={e => e.stopPropagation()}>
        <header className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-[#ded4c7] bg-[#fffdf8]/95 px-5 py-4 backdrop-blur md:px-8">
          <div>
            <p className="m-0 text-xs font-black uppercase tracking-[.16em] text-[#5b7a6b]">{fonte}</p>
            <h2 className="m-0 mt-1 font-serif text-2xl font-bold text-stone-900 md:text-4xl">{ricetta.nome}</h2>
            <p className="m-0 mt-1 text-sm font-semibold text-stone-500">
              {soloLettura ? (ricetta.tipo_archivio === "component" ? "Preparazione base" : `Ricetta tecnica${ricetta.numero_archivio ? ` n. ${ricetta.numero_archivio}` : ""}`) : "Ricetta Ceraldi operativa"}
            </p>
          </div>
          <button onClick={onClose} aria-label="Chiudi" className="grid h-11 w-11 shrink-0 place-items-center rounded-full border border-stone-200 bg-white text-stone-600"><X size={19} /></button>
        </header>

        <div className="grid gap-7 p-5 md:grid-cols-[.9fr_1.1fr] md:p-8">
          <section>
            <h3 className="mb-3 font-serif text-xl font-bold text-stone-900">Ingredienti</h3>
            {!soloLettura ? <DosiRicetta ricetta={ricetta} /> : dallaFonte.length ? (
              <ul className="m-0 space-y-2 rounded-2xl border border-[#e7ddd0] bg-white p-4 text-sm text-stone-700">
                {dallaFonte.map((riga, i) => <li key={`${riga}-${i}`} className="border-b border-stone-100 pb-2 last:border-0 last:pb-0">{riga}</li>)}
              </ul>
            ) : <p className="rounded-2xl bg-stone-100 p-4 text-sm text-stone-500">Ingredienti non ancora indicati.</p>}

          </section>

          <section className="space-y-6">
            <div>
              <h3 className="mb-3 font-serif text-xl font-bold text-stone-900">Modo di preparazione</h3>
              <p className="m-0 whitespace-pre-line rounded-2xl border border-[#e7ddd0] bg-white p-5 text-[15px] leading-7 text-stone-700">{procedimento}</p>
            </div>
            {note && <div><h3 className="mb-2 font-serif text-lg font-bold">Note</h3><p className="m-0 whitespace-pre-line rounded-2xl bg-[#f2eee6] p-4 text-sm leading-6 text-stone-700">{note}</p></div>}
            {provenienza.sheet && (
              <div className="rounded-2xl border border-dashed border-[#b9a994] p-4 text-xs leading-5 text-stone-500">
                <strong className="text-stone-700">Provenienza:</strong> {provenienza.sheet}{provenienza.row ? `, riga ${provenienza.row}` : ""}<br />
                {provenienza.sourceSheet && <>Foglio fonte: {provenienza.sourceSheet}{provenienza.sourceRow ? `, riga ${provenienza.sourceRow}` : ""}<br /></>}
              </div>
            )}

            <div className="grid gap-2 sm:grid-cols-2">
              {!soloLettura && <>
                {onProduci && <button onClick={() => onProduci(ricetta)} className="flex min-h-12 items-center justify-center gap-2 rounded-2xl bg-[#5b7a6b] px-5 py-3 font-black text-white"><ChefHat size={18} /> Produci</button>}
                {onModifica && <button onClick={() => onModifica(ricetta)} className="flex min-h-12 items-center justify-center gap-2 rounded-2xl border border-[#b9cec1] bg-white px-5 py-3 font-black text-[#3f5a4e]"><Pencil size={17} /> Modifica nome e ingredienti</button>}
                {onVisibilita && <button type="button" disabled={cambiandoVisibilita} onClick={() => onVisibilita(ricetta)} className="flex min-h-12 items-center justify-center gap-2 rounded-2xl border border-[#cfdfd5] bg-[#f2f6f3] px-5 py-3 font-black text-[#3f5a4e] disabled:opacity-50 sm:col-span-2">
                  {cambiandoVisibilita ? "Aggiorno…" : ricetta.visibile_tablet === false ? "↩ Ripristina nei reparti e nella pagina" : "⊘ Escludi dai reparti ed elimina dalla pagina"}
                </button>}
              </>}
            </div>
          </section>
        </div>
      </article>
    </div>
  );
}
