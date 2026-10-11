import React, { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import RicetteDashboardView from "../components/haccp/RicetteDashboardView";
import { puo } from "../utils/permessiRuolo";

jest.mock("axios");
jest.mock("../utils/permessiRuolo", () => ({ puo: jest.fn(() => false) }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), warning: jest.fn() } }));

const RICETTE = [
  { id: "r-1", nome: "Babà al rum", reparto: "pasticceria", ingredienti: ["Farina"] },
  { id: "r-2", nome: "Frittatina", reparto: "rosticceria", ingredienti: ["Pasta"] },
];

describe("ID prodotto unico sulle ricette", () => {
  let node, root;
  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    axios.get.mockImplementation((url) => (url.endsWith("/prodotti-codici")
      ? Promise.resolve({ data: { "r-1": "PRD-1000001" } })
      : Promise.resolve({ data: {} })));
    node = document.createElement("div");
    document.body.appendChild(node);
    root = createRoot(node);
  });
  afterEach(async () => { await act(async () => root.unmount()); node.remove(); });

  test("la card mostra il codice assegnato dal Menu e la ricerca lo trova", async () => {
    await act(async () => { root.render(<RicetteDashboardView ricette={RICETTE} searchRicette="" setSearchRicette={() => {}} />); await new Promise((r) => setTimeout(r, 0)); });
    const codici = [...node.querySelectorAll('[data-testid="codice-prodotto"]')].map((n) => n.textContent);
    expect(codici).toEqual(["PRD-1000001"]);

    await act(async () => { root.render(<RicetteDashboardView ricette={RICETTE} searchRicette="prd-1000001" setSearchRicette={() => {}} />); await new Promise((r) => setTimeout(r, 0)); });
    expect(node.textContent).toContain("Babà al rum");
    expect(node.textContent).not.toContain("Frittatina");
  });

  test("il dipendente consulta ingredienti e allergeni, solo l'admin vede le modifiche", async () => {
    const apri = jest.fn();
    puo.mockReturnValue(false);
    await act(async () => root.render(<RicetteDashboardView ricette={RICETTE} onOpenRicetta={apri} />));
    const bottoni = () => [...node.querySelectorAll('button')].map(b => b.textContent);
    expect(bottoni()).toContain('Ingredienti');
    expect(bottoni()).toContain('Allergeni');
    expect(bottoni()).toContain('Stampa scheda');
    for (const azione of ['Clona', ' Compila', 'Scheda prodotto', ' Nuova ricetta', '📖 Dizionario nomi']) {
      expect(bottoni()).not.toContain(azione);
    }
    await act(async () => [...node.querySelectorAll('button')].find(b => b.textContent === 'Ingredienti').click());
    expect(apri).toHaveBeenCalledWith(RICETTE[0], 'ingredienti');
    puo.mockReturnValue(true);
    await act(async () => root.render(<RicetteDashboardView ricette={RICETTE} />));
    expect(bottoni()).toContain('Clona');
    expect(bottoni()).toContain('Scheda prodotto');
  });
});
