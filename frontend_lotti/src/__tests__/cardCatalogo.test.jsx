import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import CardCatalogo, { rigaConfronto, GRIGLIA_CARD } from "../components/haccp/CardCatalogo";
import { prezzoDaMostrare } from "../components/haccp/CatalogoGenericoView";

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
    expect(prezzoDaMostrare({ giaAcquistato: true, prezzoFattura: 3 }).nota).toBe("ultima fattura");
    expect(prezzoDaMostrare({ prezzoFornitore: 2 }).nota).toBe("netto fornitore");
    expect(prezzoDaMostrare({}).prezzo).toBe("");
  });

  it("mostra solo nome, prezzo, confronto e i due gesti", () => {
    const onCarrello = jest.fn();
    const onRicetta = jest.fn();
    const onApri = jest.fn();
    render(<CardCatalogo nome="Amando cono" prezzo="€ 1,90" confronto={{ tipo: "altrove", testo: "Meglio da Alfa · € 0,910" }}
      onCarrello={onCarrello} onRicetta={onRicetta} onApri={onApri} />);
    expect(screen.getByText("Amando cono")).toBeTruthy();
    expect(screen.getByText("€ 1,90")).toBeTruthy();
    expect(screen.getByTestId("riga-confronto").textContent).toContain("Meglio da Alfa");
    fireEvent.click(screen.getByText("Acquista"));
    fireEvent.click(screen.getByText("Al ricettario"));
    expect(onCarrello).toHaveBeenCalledTimes(1);
    expect(onRicetta).toHaveBeenCalledTimes(1);
    expect(onApri).not.toHaveBeenCalled(); // i bottoni non aprono il dettaglio
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
  });
});
