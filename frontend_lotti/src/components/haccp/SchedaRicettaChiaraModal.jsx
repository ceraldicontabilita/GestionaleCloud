import { useEffect, useState } from "react";
import axios from "axios";
import { AlertTriangle, ChefHat, ExternalLink, Pencil, X } from "lucide-react";
import { API } from "../../utils/constants";
import { apiError } from "../../utils/apiError";
import DosiRicetta from "./shared/DosiRicetta";
import ModificaRicettaKiosk from "./tablet/ModificaRicettaKiosk";

const righe = (value) => String(value || "").split(/\r?\n/).map(x => x.trim()).filter(Boolean);

/**
 * L'unica scheda ricetta di Lotti: «Apri scheda» del ricettario e della card
 * di reparto aprono questa. Due modi di riceverla:
 * - `ricetta` gia' caricata (ricettario del backoffice);
 * - `ricettaId` (card di reparto): la scheda la legge da sola.
 * La modifica e' del chiamante (`onModifica`, form completo del backoffice)
 * oppure rapida qui dentro (`modificaRapida`, tablet), mai tutte e due.
 */
export default function SchedaRicettaChiaraModal({
  ricetta: ricettaData, ricettaId, nome, onClose, onProduci, onModifica,
  modificaRapida = false, onSalvato, onVisibilita, cambiandoVisibilita = false,
}) {
  const [caricata, setCaricata] = useState(null);
  const [errore, setErrore] = useState("");
  const [inModifica, setInModifica] = useState(false);
  const [confermato, setConfermato] = useState(false);
  const [confermando, setConfermando] = useState(false);
  const [erroreConferma, setErroreConferma] = useState("");
  const daCaricare = !ricettaData && Boolean(ricettaId);

  useEffect(() => {
    if (!daCaricare) return undefined;
    let vivo = true;
    setCaricata(null);
    setErrore("");
    axios.get(`${API}/ricette/${ricettaId}`)
      .then((r) => { if (vivo) setCaricata(r.data || null); })
      .catch((e) => { if (vivo) setErrore(apiError(e, "Ricetta non trovata")); });
    return () => { vivo = false; };
  }, [daCaricare, ricettaId]);

  const ricetta = ricettaData || caricata;
  const soloLettura = Boolean(ricetta && (ricetta.origine === "archivio" || ricetta.sola_lettura));
  const dallaFonte = righe(ricetta?.ingredienti_testo);
  const procedimento = soloLettura
    ? (ricetta?.procedimento_testo || "Procedimento non indicato nella fonte.")
    : (ricetta?.procedimento_testo || "Procedimento non ancora indicato.");
  const note = ricetta?.note || ricetta?.note_archivio || "";
  const fonte = ricetta?.fonte_archivio || "Ricetta Ceraldi";
  const provenienza = ricetta?.provenienza_archivio || {};
  const allergeni = Array.isArray(ricetta?.allergeni) ? ricetta.allergeni.filter(Boolean) : [];
  const fonteWeb = ricetta?.procedimento_origine === "web" ? (ricetta.procedimento_fonte || {}) : null;
  const daVerificare = Boolean(fonteWeb) && ricetta?.procedimento_da_verificare !== false && !confermato;
  const puoConfermare = Boolean(onModifica || modificaRapida);
  const confermaProcedimento = async () => {
    setConfermando(true);
    setErroreConferma("");
    try {
      await axios.post(`${API}/ricette/${ricetta.id}/procedimento/conferma`);
      setConfermato(true);
      onSalvato?.(ricetta);
    } catch (e) {
      setErroreConferma(apiError(e, "Conferma non riuscita"));
    } finally {
      setConfermando(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[500] flex items-end justify-center bg-black/55 p-2 md:items-center md:p-6" onClick={() => { if (!inModifica) onClose(); }}>
      <article className="max-h-[94vh] w-full max-w-5xl overflow-y-auto rounded-t-[28px] bg-[#fffdf8] shadow-2xl md:rounded-[28px]" onClick={e => e.stopPropagation()}>
        <header className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-[#ded4c7] bg-[#fffdf8]/95 px-5 py-4 backdrop-blur md:px-8">
          <div>
            <p className="m-0 text-xs font-black uppercase tracking-[.16em] text-[#5b7a6b]">{fonte}</p>
            <h2 className="m-0 mt-1 font-serif text-2xl font-bold text-stone-900 md:text-4xl">{ricetta?.nome || nome || "Ricetta"}</h2>
            <p className="m-0 mt-1 text-sm font-semibold text-stone-500">
              {inModifica ? "Modifica ricetta ufficiale"
                : soloLettura ? (ricetta.tipo_archivio === "component" ? "Preparazione base" : `Ricetta tecnica${ricetta.numero_archivio ? ` n. ${ricetta.numero_archivio}` : ""}`)
                : "Ricetta Ceraldi operativa"}
            </p>
          </div>
          <button onClick={onClose} aria-label="Chiudi" className="grid h-11 w-11 shrink-0 place-items-center rounded-full border border-stone-200 bg-white text-stone-600"><X size={19} /></button>
        </header>

        {!ricetta ? (
          <p role={errore ? "alert" : undefined} className={`m-0 p-8 text-center text-sm ${errore ? "text-[#8f3829]" : "text-stone-500"}`}>
            {errore || "Carico la ricetta…"}
          </p>
        ) : inModifica ? (
          <div className="p-5 md:p-8">
            <ModificaRicettaKiosk
              ricetta={ricetta}
              onAnnulla={() => setInModifica(false)}
              onSalvata={(aggiornata) => { setCaricata(aggiornata); setInModifica(false); onSalvato?.(aggiornata); }}
            />
          </div>
        ) : (
          <div className="grid gap-7 p-5 md:grid-cols-[.9fr_1.1fr] md:p-8">
            <section>
              <h3 className="mb-3 font-serif text-xl font-bold text-stone-900">Ingredienti</h3>
              {!soloLettura ? <DosiRicetta ricetta={ricetta} /> : dallaFonte.length ? (
                <ul className="m-0 space-y-2 rounded-2xl border border-[#e7ddd0] bg-white p-4 text-sm text-stone-700">
                  {dallaFonte.map((riga, i) => <li key={`${riga}-${i}`} className="border-b border-stone-100 pb-2 last:border-0 last:pb-0">{riga}</li>)}
                </ul>
              ) : <p className="rounded-2xl bg-stone-100 p-4 text-sm text-stone-500">Ingredienti non ancora indicati.</p>}

              {allergeni.length > 0 && (
                <div className="mt-5">
                  <h3 className="mb-2 font-serif text-lg font-bold text-stone-900">Allergeni</h3>
                  <div className="flex flex-wrap gap-2">
                    {allergeni.map((a) => (
                      <span key={a} className="inline-flex items-center gap-1 rounded-full border border-[#e8d5b0] bg-[#fdf4e6] px-3 py-1 text-xs font-extrabold text-[#8a6f47]">
                        <AlertTriangle size={12} /> {a}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </section>

            <section className="space-y-6">
              <div>
                <h3 className="mb-3 font-serif text-xl font-bold text-stone-900">Modo di preparazione</h3>
                {fonteWeb && (
                  <div className="mb-3 rounded-2xl border border-[#e8d5b0] bg-[#fdf4e6] p-3 text-sm leading-6 text-[#6b4a22]">
                    <strong>{daVerificare ? "Preso dal web, da verificare" : "Preso dal web, confermato"}</strong>
                    {" · "}
                    {fonteWeb.url ? (
                      <a href={fonteWeb.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-bold text-[#6b4a22] underline">
                        {fonteWeb.titolo || fonteWeb.sito || "fonte"} <ExternalLink size={13} />
                      </a>
                    ) : "fonte non indicata"}
                    {fonteWeb.compatibilita && <div className="mt-1 text-xs">Differenze con la nostra ricetta: {fonteWeb.compatibilita}</div>}
                    <div className="mt-1 text-xs">Le dosi sono quelle della scheda, non della fonte.</div>
                    {daVerificare && puoConfermare && (
                      <button type="button" disabled={confermando} onClick={confermaProcedimento}
                        className="mt-2 flex min-h-11 items-center justify-center rounded-xl border border-[#b9cec1] bg-white px-4 font-black text-[#3f5a4e] disabled:opacity-50">
                        {confermando ? "Confermo…" : "Confermo il procedimento"}
                      </button>
                    )}
                    {erroreConferma && <div role="alert" className="mt-1 text-[#8f3829]">{erroreConferma}</div>}
                  </div>
                )}
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
                  {!onModifica && modificaRapida && <button onClick={() => setInModifica(true)} className="flex min-h-12 items-center justify-center gap-2 rounded-2xl border border-[#b9cec1] bg-white px-5 py-3 font-black text-[#3f5a4e]"><Pencil size={17} /> Modifica ricetta</button>}
                  {onVisibilita && <button type="button" disabled={cambiandoVisibilita} onClick={() => onVisibilita(ricetta)} className="flex min-h-12 items-center justify-center gap-2 rounded-2xl border border-[#cfdfd5] bg-[#f2f6f3] px-5 py-3 font-black text-[#3f5a4e] disabled:opacity-50 sm:col-span-2">
                    {cambiandoVisibilita ? "Aggiorno…" : ricetta.visibile_tablet === false ? "↩ Ripristina nei reparti e nella pagina" : "⊘ Escludi dai reparti ed elimina dalla pagina"}
                  </button>}
                </>}
              </div>
            </section>
          </div>
        )}
      </article>
    </div>
  );
}
