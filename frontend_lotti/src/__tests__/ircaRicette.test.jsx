import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";

jest.mock("axios", () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

const axios = require("axios");
const IrcaSpuntiView = require("../components/haccp/IrcaSpuntiView").default;

global.IS_REACT_ACT_ENVIRONMENT = true;

const ricetta = {
  slug: "croissant-trial-thermotech",
  nome: "CROISSANT TRIAL THERMOTECH",
  categoria: "Lievitati",
  livello: "Intermedio",
  immagine_url: "https://example.test/croissant.jpg",
  url: "https://www.ircagroup.com/it/ricette/croissant-trial-thermotech",
  ingredienti: [{ nome: "TRIAL THERMOTECH", dose: "50g", prodotto_irca_url: "https://www.ircagroup.com/it/prodotti/trial-thermotech" }],
  fasi: [{ nome: "IMPASTO", ingredienti: [{ nome: "TRIAL THERMOTECH", dose: "50g", prodotto_irca_url: "https://www.ircagroup.com/it/prodotti/trial-thermotech" }], preparazione: "Impastare." }],
};

const distinta = {
  righe: [{ ingrediente: "TRIAL THERMOTECH", prodotto_irca_slug: "trial-thermotech", stato: "da_acquistare", fornitore: { prodotto_nome: "IRCA TRIAL THERMOTECH", codice: "MEPA-1" } }],
  totali: { pronti: 1, gia_acquistati: 0, da_acquistare: 1, da_verificare: 0 },
};

describe("sezione Ricette IRCA", () => {
  let container;
  let root;

  beforeEach(() => {
    axios.get.mockImplementation((url) => {
      if (url.includes("/irca/cataloghi")) return Promise.resolve({ data: { cataloghi: [] } });
      if (url.includes("/irca/stato")) return Promise.resolve({ data: { stato: "completato", ricette_nel_db: 1255 } });
      if (url.includes("/irca/ricette/croissant")) return Promise.resolve({ data: ricetta });
      return Promise.resolve({ data: { ricette: [ricetta], totale: 1255 } });
    });
    axios.post.mockImplementation((url) => {
      if (url.includes("/irca/distinta")) return Promise.resolve({ data: distinta });
      return Promise.resolve({ data: {} });
    });
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    jest.clearAllMocks();
  });

  test("apre la ricetta nel gestionale e mostra il prodotto MEPA da acquistare", async () => {
    await act(async () => {
      root.render(<IrcaSpuntiView />);
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    expect(container.textContent).toContain("Ricettario IRCA");
    expect(container.textContent).toContain("1255");

    const singole = Array.from(container.querySelectorAll("button")).find(b => b.textContent.includes("Singole ricette"));
    await act(async () => singole.click());

    const apri = Array.from(container.querySelectorAll("button")).find(b => b.textContent.includes("Apri nel gestionale"));
    await act(async () => {
      apri.click();
      await new Promise(resolve => setTimeout(resolve, 0));
    });

    expect(container.textContent).toContain("Prodotti collegati a MEPA");
    expect(container.textContent).toContain("IRCA TRIAL THERMOTECH · MEPA-1");
    expect(container.textContent).toContain("Da acquistare");
  });
});
