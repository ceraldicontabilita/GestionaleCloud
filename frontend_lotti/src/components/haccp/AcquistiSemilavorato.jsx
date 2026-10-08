import { useEffect, useState } from "react";
import axios from "axios";
import { API } from "../../utils/constants";
import { apiError } from "../../utils/apiError";

const annoERP = () => {
  const saved = Number(localStorage.getItem("annoGlobale"));
  const corrente = new Date().getFullYear();
  return Number.isInteger(saved) && saved >= 2018 && saved <= corrente + 5 ? saved : corrente;
};
const euro = value => value == null ? "Non indicato" : Number(value).toLocaleString("it-IT", { style: "currency", currency: "EUR" });

export default function AcquistiSemilavorato({ ricetta }) {
  const [anno, setAnno] = useState(annoERP);
  const [stato, setStato] = useState({ loading: true });
  const [tentativo, setTentativo] = useState(0);
  useEffect(() => {
    const aggiorna = () => setAnno(annoERP());
    window.addEventListener("storage", aggiorna);
    window.addEventListener("focus", aggiorna);
    return () => { window.removeEventListener("storage", aggiorna); window.removeEventListener("focus", aggiorna); };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setStato({ loading: true });
    axios.get(`${API}/ricette/${encodeURIComponent(ricetta.id)}/fatture-acquisto`, { params: { anno }, signal: controller.signal })
      .then(r => setStato({ dati: r.data }))
      .catch(e => { if (!controller.signal.aborted) setStato({ errore: apiError(e, "Fatture non disponibili") }); });
    return () => controller.abort();
  }, [ricetta.id, ricetta.fornitore_partita_iva, ricetta.codice_articolo_fornitore, anno, tentativo]);
  return <section className="rounded-xl border border-[#ded4c7] bg-white p-4 md:col-span-2">
    <h3 className="m-0 font-bold">Acquisti dal gestionale · {anno}</h3>
    <p className="my-2 text-sm text-stone-600">{ricetta.fornitore_rivendita || "Fornitore da indicare"} · {ricetta.confezione || "Confezione da indicare"}</p>
    <p className="my-2 text-xs text-stone-500">Anno selezionato nel gestionale. Le fatture da verificare non attestano ancora l’acquisto.</p>
    {stato.loading ? <p role="status">Carico gli acquisti…</p> : stato.errore ? <div role="alert">
      <p>{stato.errore}</p><button type="button" className="min-h-11 underline" onClick={() => setTentativo(v => v + 1)}>Riprova</button>
    </div> : <>
      {!stato.dati?.fatture?.length && <p className="text-sm">{stato.dati?.messaggio || "Nessuna fattura collegata a questo articolo nell’anno selezionato."}</p>}
      {stato.dati?.fatture?.map(f => <div key={f.id} className="border-t border-stone-200 py-3 text-sm">
        <a href={`/fatture?invoice_id=${encodeURIComponent(f.id)}`} onClick={() => localStorage.setItem("annoGlobale", String(anno))} className="inline-flex min-h-11 items-center font-bold text-[#3f5a4e] underline">
          Apri {f.tipo_documento === "TD04" ? "nota di credito" : "fattura"} {f.numero || "senza numero"} · {f.data}
        </a>
        {f.righe.map((r, i) => <p key={`${r.numero_linea}-${i}`} className="my-1 break-words">
          {r.descrizione || "Articolo"} · {r.quantita ?? "Quantità non indicata"} {r.unita_misura || ""} · Totale riga {euro(r.prezzo_totale)}
        </p>)}
      </div>)}
    </>}
    <a href="/fatture" className="inline-flex min-h-11 items-center text-sm font-semibold text-[#3f5a4e] underline">Apri archivio fatture e anno del gestionale</a>
  </section>;
}
