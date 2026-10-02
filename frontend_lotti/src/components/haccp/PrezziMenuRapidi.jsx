import { useMemo, useRef, useState } from "react";
import axios from "axios";
import { Check, Image as ImageIcon, Search } from "lucide-react";
import { fotoRicetta, prezzoPerMenu, sottocategoriaPerReparto } from "../../utils/menuVetrina";
import { toast } from "./backoffice/toastBackoffice";
import "./PrezziMenuRapidi.css";

const API = process.env.REACT_APP_LOTTI_BACKEND_URL + "/api";
const BACKEND = process.env.REACT_APP_LOTTI_BACKEND_URL || "";

// Il campo accetta la virgola italiana, non esponenti, testo o frazioni di centesimo.
export function leggiPrezzoRapido(testo) {
  const s = String(testo ?? "").trim();
  if (!/^\d+(?:[.,]\d{1,2})?$/.test(s)) return null;
  const valore = Number(s.replace(",", "."));
  return Number.isFinite(valore) && valore > 0 && valore * 100 <= Number.MAX_SAFE_INTEGER ? valore : null;
}

export default function PrezziMenuRapidi({ ricette, onSalvato }) {
  const [ricerca, setRicerca] = useState("");
  const [reparto, setReparto] = useState("");
  const [bozze, setBozze] = useState({});
  const [errori, setErrori] = useState({});
  const [occupati, setOccupati] = useState({});
  const [salvati, setSalvati] = useState(0);
  const inVolo = useRef(new Set());
  const listaRef = useRef(null);
  const daCompletare = useMemo(() => ricette.filter(r =>
    prezzoPerMenu(r).origine !== "tavolo" || errori[r.id]), [ricette, errori]);
  const reparti = [...new Set(daCompletare.map(r => sottocategoriaPerReparto(r.reparto)))].sort();
  const visibili = daCompletare.filter(r =>
    (!reparto || sottocategoriaPerReparto(r.reparto) === reparto) &&
    String(r.nome || "").toLocaleLowerCase("it").includes(ricerca.trim().toLocaleLowerCase("it"))
  ).sort((a, b) => String(a.nome || "").localeCompare(String(b.nome || ""), "it"));

  const salva = async (event, ricetta) => {
    event.preventDefault();
    const prezzo = leggiPrezzoRapido(bozze[ricetta.id]);
    if (prezzo == null || inVolo.current.has(ricetta.id)) return;
    inVolo.current.add(ricetta.id);
    setOccupati(p => ({ ...p, [ricetta.id]: true }));
    try {
      // Endpoint canonico: cambia SOLO il prezzo al tavolo e usa il ponte Lotti -> Menu.
      const { data } = await axios.put(`${API}/ricette/${encodeURIComponent(ricetta.id)}/prezzo-tavolo`, null, { params: { prezzo } });
      if (!data?.ok || leggiPrezzoRapido(data.prezzo_tavolo) == null) throw new Error("Salvataggio non confermato dal server");
      onSalvato(ricetta.id, data.prezzo_tavolo);
      if (!["pubblicato", "aggiornato"].includes(data.menu_sync?.esito)) {
        setErrori(p => ({ ...p, [ricetta.id]: "Prezzo salvato nella ricetta, ma il Menu non è aggiornato. Riprova il salvataggio." }));
        return;
      }
      setErrori(p => { const n = { ...p }; delete n[ricetta.id]; return n; });
      setSalvati(n => n + 1);
      toast(`${ricetta.nome}: prezzo salvato e Menu aggiornato`);
      // Dopo la rimozione sposta il cursore al prossimo prezzo visibile.
      requestAnimationFrame(() => listaRef.current?.querySelector('input[data-prezzo-rapido]:not(:disabled)')?.focus());
    } catch (e) {
      setErrori(p => ({ ...p, [ricetta.id]: typeof e.response?.data?.detail === "string"
        ? e.response.data.detail : "Salvataggio non riuscito. Il prodotto resta in lista: riprova." }));
    } finally {
      inVolo.current.delete(ricetta.id);
      setOccupati(p => ({ ...p, [ricetta.id]: false }));
    }
  };

  return <section className="prezzi-menu" aria-labelledby="prezzi-menu-titolo">
    <header className="prezzi-menu-testata">
      <div><span className="prezzi-menu-occhiello">LISTINO AL TAVOLO</span>
        <h2 id="prezzi-menu-titolo">Prezzi da completare <span>{daCompletare.length}</span></h2>
        <p>Guarda il prodotto, inserisci il prezzo in euro e premi Invio o Salva. Dopo il salvataggio scompare da questa lista, non dal Menu.</p>
      </div>
      <div role="status" className="prezzi-menu-progresso"><Check size={18} aria-hidden="true" /> {salvati} completati in questa sessione</div>
    </header>
    <div className="prezzi-menu-filtri">
      <label><Search size={18} aria-hidden="true" /><input aria-label="Cerca prodotto da prezzare" placeholder="Cerca prodotto…" value={ricerca} onChange={e => setRicerca(e.target.value)} /></label>
      <select aria-label="Reparto dei prezzi da completare" value={reparto} onChange={e => setReparto(e.target.value)}>
        <option value="">Tutti i reparti</option>{reparti.map(r => <option key={r}>{r}</option>)}
      </select>
      {(ricerca || reparto) && <button type="button" onClick={() => { setRicerca(""); setReparto(""); }}>Togli filtri</button>}
    </div>
    <div className="prezzi-menu-lista" ref={listaRef}>
      {visibili.map(r => {
        const foto = fotoRicetta(r);
        const occupato = !!occupati[r.id];
        const prezzoBanco = prezzoPerMenu({ ...r, prezzo_tavolo: null }).prezzo;
        return <article key={r.id} className="prezzi-menu-prodotto" aria-label={r.nome}>
          {foto ? <img loading="lazy" src={/^https?:/.test(foto) ? foto : BACKEND + foto} alt={r.nome} />
            : <div className="prezzi-menu-senza-foto"><ImageIcon size={26} aria-hidden="true" /><span>Senza foto</span></div>}
          <div className="prezzi-menu-nome"><span>{sottocategoriaPerReparto(r.reparto)}</span><h3>{r.nome}</h3>
            {prezzoBanco != null && <small>Al banco: {prezzoBanco.toLocaleString("it-IT", { style: "currency", currency: "EUR" })} · non viene modificato</small>}
          </div>
          <form onSubmit={e => salva(e, r)}>
            <label>Prezzo al tavolo (€)<input data-prezzo-rapido aria-label={`Prezzo al tavolo di ${r.nome}`} type="text" inputMode="decimal" autoComplete="off"
              placeholder="0,00" disabled={occupato} value={bozze[r.id] ?? ""} onChange={e => setBozze(p => ({ ...p, [r.id]: e.target.value }))} /></label>
            <button type="submit" disabled={occupato || leggiPrezzoRapido(bozze[r.id]) == null}>{occupato ? "Salvo…" : errori[r.id] ? "Riprova" : "Salva"}</button>
            {bozze[r.id] && leggiPrezzoRapido(bozze[r.id]) == null && <small className="prezzi-menu-errore">Importo maggiore di zero, massimo due decimali.</small>}
            {errori[r.id] && <small role="alert" className="prezzi-menu-errore">{errori[r.id]}</small>}
          </form>
        </article>;
      })}
      {visibili.length === 0 && <p className="prezzi-menu-vuoto">{daCompletare.length === 0 ? "Tutti i prezzi al tavolo sono completati." : "Nessun prodotto con questi filtri. Togli i filtri per continuare."}</p>}
    </div>
  </section>;
}
