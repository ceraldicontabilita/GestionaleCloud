import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import CardCatalogo, { rigaConfronto, GRIGLIA_CARD } from "../components/haccp/CardCatalogo";
import { prezzoDaMostrare } from "../components/haccp/CatalogoGenericoView";
import { datiPrezzoProdotto, riconciliaPrezziCarrello } from "../components/haccp/CatalogoFornitoreView";

global.IS_REACT_ACT_ENVIRONMENT = true;

const fmt = (v) => `€ ${v}`;

function render(el) {
  const node = document.createElement("div");
  document.body.appendChild(node);
  const root = createRoot(node);
  act(() => root.render(el));
  cont = node;
}
let cont;
const trova = (t) => Array.from(cont.querySelectorAll("*")).find((e) => e.tagName !== "svg" && Array.from(e.childNodes).some((n) => n.nodeType === 3) && e.textContent.trim() === t);
const screen = {
  getByText: (t) => { const e = trova(t); if (!e) throw new Error("manca " + t); return e; },
  queryByText: (re) => Array.from(cont.querySelectorAll("*")).find((e) => e.children.length === 0 && re.test(e.textContent)) || null,
  getByTestId: (id) => cont.querySelector(`[data-testid="${id}"]`),
};
const fireEvent = { click: (e) => act(() => { e.dispatchEvent(new MouseEvent("click", { bubbles: true })); }) };

describe("card unica dei cataloghi", () => {
  it("confronto: solo chi costa meno e a quanto", () => {
    expect(rigaConfronto(null, fmt)).toBeNull();
    expect(rigaConfronto({ migliore: null }, fmt)).toBeNull();
    expect(rigaConfronto({ migliore: "Alfa", questo_migliore: false, migliore_prezzo_pezzo: "0.91" }, fmt))
      .toEqual({ tipo: "altrove", testo: "Meglio da Alfa · € 0.91" });
    expect(rigaConfronto({ migliore: "Barone", questo_migliore: true, prezzo_pezzo: "1.20" }, fmt).tipo).toBe("qui");
  });

  it("prezzo: il listino prevale, poi fattura, netto fornitore, catalogo", () => {
    expect(prezzoDaMostrare({ prezzoListino: 12, unitaVendita: "12 PZ" }).nota).toContain("12 PZ");
    expect(prezzoDaMostrare({ giaAcquistato: true, prezzoFattura: 3 }).nota).toContain("ultima fattura");
    expect(prezzoDaMostrare({ prezzoFornitore: 2 }).nota).toContain("netto fornitore");
    expect(prezzoDaMostrare({}).prezzo).toBe("");
  });

  it("salva nel carrello lo stesso prezzo mostrato anche con i campi camelCase", () => {
    const prodotto = { id: "glf-002", nome: "Crema Rio", giaAcquistato: true, prezzoFattura: 4.23 };
    expect(datiPrezzoProdotto(prodotto)).toEqual(expect.objectContaining({ prezzo: 4.23, fonte: "fattura_xml" }));
    localStorage.setItem("ordini_smart_carrello", JSON.stringify([{ id: "glf-002", nome: "Crema Rio", prezzo: 0 }]));
    riconciliaPrezziCarrello([prodotto], false);
    expect(JSON.parse(localStorage.getItem("ordini_smart_carrello"))[0]).toEqual(expect.objectContaining({
      prezzo: 4.23, prezzo_fonte: "fattura_xml",
    }));
  });

  it("trasforma il prezzo al kg nel totale confezione e aggiunge l'IVA reale", () => {
    const prodotto = { id: "n031", giaAcquistato: true, prezzoFattura: 4.11,
      unitaFattura: "KG", unita_confezione: "13 KG", ivaPct: 10 };
    const dati = datiPrezzoProdotto(prodotto);
    expect(dati).toEqual(expect.objectContaining({ prezzoUnitario: 4.11, pesoKg: 13, prezzo: 53.43, ivaPct: 10, prezzoIvato: 58.77 }));
    expect(prezzoDaMostrare(prodotto).nota).toContain("€ 4,11/kg × 13 kg");
  });

  it("mostra dati utili reali, confronto e i gesti rapidi", () => {
    const onCarrello = jest.fn();
    const onRicetta = jest.fn();
    const onApri = jest.fn();
    const onPreferito = jest.fn();
    render(<CardCatalogo nome="Amando cono" prezzo="€ 1,90" codice="A12" categoria="Semilavorati"
      descrizione="Cono croccante per gelateria" confezione="12 pezzi" preferito
      confronto={{ tipo: "altrove", testo: "Meglio da Alfa · € 0,910" }}
      onCarrello={onCarrello} onRicetta={onRicetta} onPreferito={onPreferito} onApri={onApri} />);
    expect(screen.getByText("Amando cono")).toBeTruthy();
    expect(screen.getByText("€ 1,90")).toBeTruthy();
    expect(screen.getByTestId("riga-confronto").textContent).toContain("Meglio da Alfa");
    expect(cont.textContent).toContain("Semilavorati");
    expect(cont.textContent).toContain("Cod. A12 · 12 pezzi");
    expect(cont.textContent).toContain("Cono croccante per gelateria");
    expect(cont.textContent).toContain("Preferito");
    fireEvent.click(screen.getByText("Acquista"));
    fireEvent.click(screen.getByText("Al ricettario"));
    fireEvent.click(Array.from(cont.querySelectorAll("button")).find(b => b.textContent.trim() === "Preferito"));
    fireEvent.click(screen.getByText("Maggiori dettagli"));
    expect(onCarrello).toHaveBeenCalledTimes(1);
    expect(onRicetta).toHaveBeenCalledTimes(1);
    expect(onPreferito).toHaveBeenCalledTimes(1);
    expect(onApri).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/Dettagli tecnici/)).toBeNull();
    expect(screen.queryByText(/IVA/)).toBeNull();
  });

  it("stati attivi e prezzo mancante dichiarato", () => {
    render(<CardCatalogo nome="X" inCart inRicette />);
    expect(screen.getByText("Nel carrello")).toBeTruthy();
    expect(screen.getByText("Nel ricettario")).toBeTruthy();
    expect(screen.getByText("Prezzo non disponibile")).toBeTruthy();
  });

  it("una colonna sul telefono, piu' colonne sui monitor", () => {
    expect(GRIGLIA_CARD).toContain("grid-cols-1");
    expect(GRIGLIA_CARD).toContain("sm:grid-cols-2");
    expect(GRIGLIA_CARD).toContain("xl:grid-cols-4");
    expect(GRIGLIA_CARD).toContain("2xl:grid-cols-5");
  });
});
