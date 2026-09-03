import { useEffect, useState } from "react";
import GestioneProdottiView from "./GestioneProdottiView";
import ListinoView from "./ListinoView";
import ProdottiVenditaView from "./ProdottiVenditaView";
import ScontiMerceView from "./ScontiMerceView";
import {
  CATALOGO_PRODOTTI_DEFAULT,
  hashCatalogoProdotti,
  leggiCatalogoProdotti,
  risolviSottoTabProdotti,
} from "../../router/prodottiRoute";

// Hub unico "Listini e cataloghi": riunisce sotto un'unica pagina i componenti
// esistenti. I deep-link #prodotti/<fornitore> aprono direttamente i cataloghi.
export default function ProdottiHubView({ initialSub = "listino" }) {
  const [sub, setSub] = useState(() => risolviSottoTabProdotti(window.location.hash, initialSub));

  useEffect(() => {
    const sincronizzaHash = () => {
      setSub(risolviSottoTabProdotti(window.location.hash, initialSub));
    };
    sincronizzaHash();
    window.addEventListener("hashchange", sincronizzaHash);
    return () => window.removeEventListener("hashchange", sincronizzaHash);
  }, [initialSub]);

  const selezionaSub = (id) => {
    if (id === "cataloghi") {
      const catalogo = leggiCatalogoProdotti(window.location.hash) || CATALOGO_PRODOTTI_DEFAULT;
      window.location.hash = hashCatalogoProdotti(catalogo);
      setSub("cataloghi");
      return;
    }

    const destinazioni = {
      listino: "prodotti",
      gestione: "magazzino_prodotti",
      sconti: "sconti_merce",
    };
    if (destinazioni[id]) window.location.hash = destinazioni[id];
    setSub(id);
  };

  const tBtn = (id, label) => (
    <button id={`prodotti-tab-${id}`} role="tab" aria-selected={sub === id}
      aria-controls={`prodotti-panel-${id}`} data-testid={`prodotti-sub-${id}`}
      onClick={() => selezionaSub(id)} style={{
        padding: "8px 16px", borderRadius: 9, fontWeight: 600, fontSize: 14, cursor: "pointer",
        border: "1px solid #d9cfbb", fontFamily: "inherit",
        background: sub === id ? "#3f5a4e" : "transparent", color: sub === id ? "#fff" : "#3f5a4e",
      }}>{label}</button>
  );

  return (
    <div>
      <div role="tablist" aria-label="Listini, prodotti e cataloghi" style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        {tBtn("listino", "🏷️ Listino")}
        {tBtn("cataloghi", "📚 Prodotti e cataloghi")}
        {tBtn("gestione", "🗂️ Magazzino prodotti")}
        {tBtn("sconti", "🎁 Sconti merce")}
        <button onClick={() => { window.location.hash = "ordini"; }} style={{
          padding: "8px 16px", borderRadius: 9, fontWeight: 600, fontSize: 14, cursor: "pointer",
          border: "1px dashed #a8c0b3", fontFamily: "inherit", background: "transparent", color: "#5b7a6b",
        }}>📦 Acquisti: catalogo, confronto e ordini →</button>
      </div>
      <div id={`prodotti-panel-${sub}`} role="tabpanel" aria-labelledby={`prodotti-tab-${sub}`}>
        {sub === "cataloghi" && <ProdottiVenditaView />}
        {sub === "gestione" && <GestioneProdottiView />}
        {sub === "listino" && <ListinoView />}
        {sub === "sconti" && <ScontiMerceView />}
      </div>
    </div>
  );
}
