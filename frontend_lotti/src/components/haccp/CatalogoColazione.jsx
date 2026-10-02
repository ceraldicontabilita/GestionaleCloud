import { useState } from "react";
import { CakeSlice, Check, CookingPot, ImageOff, Package, Star } from "lucide-react";
import { CATEGORIE_PRODOTTI, filtraProdotti } from "../../utils/categorieProdotti";
import "./CatalogoColazione.css";

export default function CatalogoColazione({ prodotti, template, stagione, fotoSrc, onToggle, onTutteStagioni, busy, onNavigate }) {
  const [scheda, setScheda] = useState("pasticceria");
  const [categoria, setCategoria] = useState("tutte");
  const [search, setSearch] = useState("");
  const [mostraTutti, setMostraTutti] = useState(false);
  const schede = [
    { id: "pasticceria", label: "Pasticceria", Icon: CakeSlice },
    { id: "rosticceria", label: "Rosticceria", Icon: CookingPot },
    { id: "acquaviva", label: "Acquaviva", Icon: Package },
  ];
  if (prodotti.some(p => p.fonte !== "casa" && !/acquaviva/i.test(p.fornitore || ""))) schede.push({ id: "fornitori", label: "Altri fornitori", Icon: Package });
  const vaiRosticceria = (e) => {
    if (onNavigate) { e.preventDefault(); onNavigate("tablet/rosticceria/produci"); }
  };
  const visibili = filtraProdotti(prodotti, { scheda, categoria, search, mostraTutti });
  const salati = scheda === "rosticceria";
  return <section className="col-catalogo" aria-label="Scegli prodotti per la colazione">
    <div role="tablist" aria-label="Origine e reparto prodotti" className="col-schede">
      {schede.map(({ id, label, Icon }) => <button key={id} type="button" role="tab" id={`col-tab-${id}`} aria-controls="col-prodotti" aria-selected={scheda === id} onClick={() => { setScheda(id); setCategoria("tutte"); }}>
        <Icon size={20} aria-hidden="true" />{label}
      </button>)}
    </div>
    <p className="col-aiuto">{salati
      ? "I salati si preparano in Rosticceria: non vengono aggiunti alla colazione dolce."
      : `Scegli i prodotti per ${stagione}. “Tutte le 4 stagioni” aggiunge solo quel prodotto, senza sostituire i menu esistenti.`}</p>
    {salati && <a className="col-produci" href="#tablet/rosticceria/produci" onClick={vaiRosticceria}><CookingPot size={18} />Apri produzione del giorno · Rosticceria</a>}
    <div className="col-filtri">
      <label>Cerca in questa scheda<input type="search" placeholder="Cerca prodotto…" value={search} onChange={e => setSearch(e.target.value)} /></label>
      {!['pasticceria', 'rosticceria'].includes(scheda) && <label className="col-checkbox"><input type="checkbox" checked={mostraTutti} onChange={e => setMostraTutti(e.target.checked)} />Mostra anche mai acquistati</label>}
    </div>
    <div role="group" aria-label="Categorie prodotti" className="col-categorie">
      {[{ id: "tutte", label: "Tutte" }, ...CATEGORIE_PRODOTTI].map(c => <button type="button" key={c.id} aria-pressed={categoria === c.id} onClick={() => setCategoria(c.id)}>{c.label}</button>)}
    </div>
    <p className="col-conteggio" role="status">{visibili.length} prodotti · {schede.find(s => s.id === scheda)?.label} · {categoria === "tutte" ? "Tutte le categorie" : CATEGORIE_PRODOTTI.find(c => c.id === categoria)?.label}</p>
    <div id="col-prodotti" role="tabpanel" aria-labelledby={`col-tab-${scheda}`} className="col-griglia">
      {visibili.map(prod => {
        const scelto = template.items.some(i => i.prodotto_id === prod.id);
        return <article key={prod.id} className={`col-prodotto${scelto ? " scelto" : ""}`}>
          <div className="col-foto">{fotoSrc(prod.foto_url) ? <img src={fotoSrc(prod.foto_url)} alt={prod.nome} loading="lazy" /> : <ImageOff aria-label="Foto non disponibile" />}</div>
          <div className="col-prodotto-testo"><small>{prod.fonte === "casa" ? "Fatto in casa" : prod.fornitore || "Acquistato"}</small><h3>{prod.nome}</h3>
            {prod.fonte !== "casa" && prod.gia_acquistato === false && <p>Mai acquistato</p>}
            {!salati && <>
              <button type="button" aria-pressed={scelto} disabled={!!busy} onClick={() => onToggle(prod)} aria-label={`${scelto ? "Rimuovi" : "Aggiungi"} ${prod.nome} ${stagione}`}><Check size={17} aria-hidden="true" />{scelto ? `In ${stagione}` : `Aggiungi a ${stagione}`}</button>
              <button className="col-tutte" type="button" disabled={!!busy} onClick={() => onTutteStagioni(prod)} aria-label={`${prod.nome}: tutte le 4 stagioni`}><Star size={17} aria-hidden="true" />{busy === prod.id ? "Salvataggio…" : "Tutte le 4 stagioni"}</button>
            </>}
            {salati && <a href="#tablet/rosticceria/produci" onClick={vaiRosticceria}>Vai alla produzione</a>}
          </div>
        </article>;
      })}
    </div>
    {!visibili.length && <p className="col-vuoto">Nessun prodotto con questi filtri. Prova un’altra categoria o cancella la ricerca.</p>}
  </section>;
}
