import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";

jest.mock("axios", () => ({ get: jest.fn(), post: jest.fn(), put: jest.fn() }));
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
  fasi: [
    { nome: "IMPASTO", ingredienti: [{ nome: "TRIAL THERMOTECH", dose: "50g", prodotto_irca_url: "https://www.ircagroup.com/it/prodotti/trial-thermotech" }], preparazione: "Impastare." },
    { nome: "Composizione finale", ingredienti: [], preparazione: "Cuocere 15 minuti. AVVERTENZE: lasciare spazio tra i biscotti." },
  ],
};

const distinta = {
  righe: [{ ingrediente: "TRIAL THERMOTECH", prodotto_irca_slug: "trial-thermotech", stato: "da_acquistare", quantita_min: 50, quantita_max: 50, unita: "g", dosi_originali: ["50g"], codici_irca: ["01090613"], fornitore: { nome: "MEPA", prodotto_nome: "IRCA TRIAL THERMOTECH", codice: "MEPA-1" } }],
  totali: { pronti: 1, gia_acquistati: 0, da_acquistare: 1, da_verificare: 0 },
};

describe("sezione Ricette IRCA", () => {
  let container;
  let root;

  beforeEach(() => {
    axios.get.mockImplementation((url) => {
      if (url.includes("/irca/cataloghi")) return Promise.resolve({ data: { cataloghi: [{ id: "vegan", titolo: "IRCA - Pasticceria vegana", tipo: "Catalogo", url: "https://www.flipsnack.com/E89ED75569B/vegan-pastry-catalog-cm0xqq095e/full-view.html" }] } });
      if (url.includes("/irca/stato")) return Promise.resolve({ data: { stato: "completato", ricette_nel_db: 1255 } });
      if (url.includes("/irca/ricette/croissant")) return Promise.resolve({ data: ricetta });
      return Promise.resolve({ data: { ricette: [ricetta], totale: 1255 } });
    });
    axios.post.mockImplementation((url) => {
      if (url.includes("/irca/distinta/aggiungi-carrello")) return Promise.resolve({ data: { aggiunti: 1, gia_acquistati: 0, da_verificare: 0, da_verificare_aggiunti: 0 } });
      if (url.includes("/irca/distinta")) return Promise.resolve({ data: distinta });
      return Promise.resolve({ data: {} });
    });
    axios.put.mockResolvedValue({ data: { slug: ricetta.slug, preferito: true } });
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

    expect(container.textContent).toContain("Prodotti richiesti e stato ordine");
    expect(container.textContent).toContain("IRCA TRIAL THERMOTECH · MEPA-1");
    expect(container.textContent).toContain("Da acquistare");
    expect(container.textContent).toContain("Composizione finale");
    expect(container.textContent).toContain("Avvertenze");
    expect(container.textContent).not.toContain("Ricetta selezionata");
  });

  test("salva la spunta preferita e prepara l'ordine dei soli mancanti", async () => {
    await act(async () => {
      root.render(<IrcaSpuntiView />);
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    expect(container.textContent).toContain("CROISSANT TRIAL THERMOTECH");
    const preferita = container.querySelector('button[aria-label*="Aggiungi CROISSANT TRIAL THERMOTECH ai preferiti"]');
    await act(async () => {
      preferita.click();
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    expect(axios.put).toHaveBeenCalledWith(expect.stringContaining("/irca/ricette/croissant-trial-thermotech/preferito"), { preferito: true });

    const apri = Array.from(container.querySelectorAll("button")).find(b => b.textContent.includes("Apri nel gestionale"));
    await act(async () => {
      apri.click();
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    const prepara = Array.from(container.querySelectorAll("button")).find(b => b.textContent.includes("Produci questa ricetta"));
    await act(async () => {
      prepara.click();
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    expect(axios.post).toHaveBeenCalledWith(expect.stringContaining("/irca/distinta/aggiungi-carrello"), {
      ricette: [{ slug: "croissant-trial-thermotech", moltiplicatore: 1 }],
    });
  });

  test("distingue il catalogo vegano inglese dal percorso operativo delle ricette", async () => {
    await act(async () => {
      root.render(<IrcaSpuntiView />);
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    const cataloghi = Array.from(container.querySelectorAll("button")).find(b => b.textContent.includes("Ricettari e cataloghi"));
    await act(async () => cataloghi.click());
    expect(container.textContent).toContain("Vegan pastry catalog");
    expect(container.textContent).toContain("Lingua: Inglese");
    expect(container.textContent).toContain("Vai alle ricette da produrre");
  });
});
