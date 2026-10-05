import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import axios from "axios";
import SchedaProdottoModal from "../components/haccp/SchedaProdottoModal";

jest.mock("axios");
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), warning: jest.fn() } }));
jest.mock("qrcode.react", () => ({ QRCodeSVG: ({ value }) => <i data-testid="qr" data-v={value} /> }));

const SCHEDA = {
  codice_prodotto: "PRD-000007",
  piatto: { id: "r1", nome: "Babà" },
  prezzo: { banco: "3.50", tavolo: "4.00" },
  reparto: "pasticceria",
  ingredienti: [{ nome: "Rum" }, { nome: "Farina" }],
  allergeni: ["glutine"],
  varianti: [],
  aggiunte: [{ nome: "Panna", prezzo: "0.50" }],
  rimozioni: ["Rum"],
  costo_ingredienti_e_food_cost: { costo_porzione: "1.00", food_cost_percentuale: "28.6", motivo: null },
  disponibilita: { esaurito: false, ingredienti_in_giacenza: true, ingredienti_mancanti: [] },
  foto: null,
  valori_nutrizionali: { per_porzione: { kcal: 300, prot: 5, carb: 40, grassi: 8 }, ingredienti_coperti: 2, ingredienti_totali: 2 },
  vendita: { sala: true, delivery: true },
  qr: { scheda: "https://x.it/menu/carta/?p=PRD-000007", sala: "https://x.it/menu/carta/?p=PRD-000007&canale=sala", delivery: "https://x.it/menu/carta/?p=PRD-000007&canale=delivery", motivo: null },
};

describe("Scheda prodotto", () => {
  let node, root;
  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    axios.get.mockResolvedValue({ data: SCHEDA });
    axios.put.mockResolvedValue({ data: { ok: true } });
    node = document.createElement("div");
    document.body.appendChild(node);
    root = createRoot(node);
  });
  afterEach(async () => { await act(async () => root.unmount()); node.remove(); });

  const apri = async () => act(async () => { root.render(<SchedaProdottoModal ricetta={{ id: "r1", nome: "Babà" }} onClose={() => {}} />); await new Promise((r) => setTimeout(r, 0)); });

  test("mostra l'ID prodotto, la catena e i tre QR", async () => {
    await apri();
    expect(node.querySelector('[data-testid="scheda-codice"]').textContent).toBe("PRD-000007");
    expect(node.textContent).toContain("Food cost 28,6%");
    expect(node.textContent).toContain("Panna");
    expect(node.querySelectorAll('[data-testid="qr"]').length).toBe(3);
  });

  test("salva canali, esaurito, aggiunte e rimozioni con i valori scelti", async () => {
    await apri();
    await act(async () => node.querySelector('[data-testid="canale-delivery"]').click());
    await act(async () => node.querySelector('[data-testid="esaurito"]').click());
    await act(async () => node.querySelector('[data-testid="salva-scheda"]').click());
    expect(axios.put).toHaveBeenCalledWith(
      expect.stringContaining("/ricette/r1/scheda-vendita"),
      { vendita_sala: true, vendita_delivery: false, esaurito: true, aggiunte: [{ nome: "Panna", prezzo: 0.5 }], rimozioni: ["Rum"] },
      expect.anything(),
    );
  });

  test("senza indirizzo pubblico del menu il QR dice perché non c'è", async () => {
    axios.get.mockResolvedValue({ data: { ...SCHEDA, qr: { scheda: null, sala: null, delivery: null, motivo: "indirizzo pubblico del menu non ancora scelto" } } });
    await apri();
    expect(node.querySelectorAll('[data-testid="qr"]').length).toBe(0);
    expect(node.textContent).toContain("indirizzo pubblico del menu non ancora scelto");
  });
});
