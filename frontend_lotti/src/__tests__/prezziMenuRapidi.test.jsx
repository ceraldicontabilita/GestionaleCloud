import React, { act, useState } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import PrezziMenuRapidi, { leggiPrezzoRapido } from "../components/haccp/PrezziMenuRapidi";
import MenuVetrinaView from "../components/haccp/MenuVetrinaView";

global.IS_REACT_ACT_ENVIRONMENT = true;
jest.mock("../components/haccp/backoffice/toastBackoffice", () => ({ toast: jest.fn() }));
jest.mock("../auth", () => ({ isAdmin: jest.fn(() => true) }));
jest.mock("../hooks/useCategorieMenu", () => ({ useCategorieMenu: () => ({ indice: {}, ricarica: jest.fn() }) }));
const { isAdmin } = require("../auth");
const ricette = [
  { id: "r/1", nome: "Parigina", reparto: "rosticceria", menu_pubblico: true, prezzo_vendita: 2, foto_url: "https://example.test/parigina.jpg" },
  { id: "r2", nome: "Sfogliatella", reparto: "pasticceria", menu_pubblico: true },
  { id: "r3", nome: "Gia completato", reparto: "bar", menu_pubblico: true, prezzo_tavolo: 4 },
];
function ListaReale() {
  const [righe, setRighe] = useState(ricette);
  return <PrezziMenuRapidi ricette={righe} onSalvato={(id, prezzo) => setRighe(p => p.map(r => r.id === id ? { ...r, prezzo_tavolo: prezzo } : r))} />;
}

describe("prezzi rapidi nel Menu", () => {
  let node, root;
  beforeEach(() => {
    node = document.createElement("div"); document.body.appendChild(node); root = createRoot(node);
    isAdmin.mockReturnValue(true);
    jest.spyOn(axios, "get").mockResolvedValue({ data: ricette });
    jest.spyOn(axios, "put").mockResolvedValue({ data: { ok: true, prezzo_tavolo: 3.5, menu_sync: { esito: "aggiornato" } } });
  });
  afterEach(async () => { await act(async () => root.unmount()); node.remove(); jest.restoreAllMocks(); });
  const scrivi = async (input, value) => act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  const salva = async () => act(async () => node.querySelector("form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));

  test.each(["", "0", "-2", "1e2", "2 euro", "NaN", "Infinity", "1,234", "1.234", "1,2,3"])("rifiuta l'importo non valido %s", testo => {
    expect(leggiPrezzoRapido(testo)).toBeNull();
  });
  test("accetta euro con virgola, punto e due decimali", () => {
    expect(leggiPrezzoRapido(" 3,50 ")).toBe(3.5);
    expect(leggiPrezzoRapido("3.50")).toBe(3.5);
    expect(leggiPrezzoRapido("3")).toBe(3);
  });
  test("mostra la foto, non i prodotti completati, e salva SOLO il tavolo per ID", async () => {
    await act(async () => root.render(<ListaReale />));
    expect(node.querySelector("img").getAttribute("src")).toBe(ricette[0].foto_url);
    expect(node.textContent).not.toContain("Gia completato");
    expect(node.querySelectorAll("article")).toHaveLength(2);
    await scrivi(node.querySelector("input[data-prezzo-rapido]"), "3,50");
    await salva();
    expect(axios.put).toHaveBeenCalledWith(expect.stringContaining("/ricette/r%2F1/prezzo-tavolo"), null, { params: { prezzo: 3.5 } });
    expect(node.querySelectorAll("article")).toHaveLength(1);
    expect(node.textContent).not.toContain("Parigina");
    expect(node.textContent).toContain("1 completati in questa sessione");
  });
  test("non rimuove la riga prima della risposta e non invia due salvataggi", async () => {
    let termina;
    axios.put.mockImplementation(() => new Promise(resolve => { termina = resolve; }));
    await act(async () => root.render(<ListaReale />));
    await scrivi(node.querySelector("input[data-prezzo-rapido]"), "3,50");
    await salva(); await salva();
    expect(axios.put).toHaveBeenCalledTimes(1);
    expect(node.querySelectorAll("article")).toHaveLength(2);
    await act(async () => termina({ data: { ok: true, prezzo_tavolo: 3.5, menu_sync: { esito: "pubblicato" } } }));
    expect(node.querySelectorAll("article")).toHaveLength(1);
  });
  test("errore di rete mantiene il valore scritto e permette di riprovare", async () => {
    axios.put.mockRejectedValueOnce(new Error("rete"));
    await act(async () => root.render(<ListaReale />));
    await scrivi(node.querySelector("input[data-prezzo-rapido]"), "3,50"); await salva();
    expect(node.querySelector('[role="alert"]').textContent).toContain("Salvataggio non riuscito");
    expect(node.querySelector("input[data-prezzo-rapido]").value).toBe("3,50");
    await salva(); expect(node.querySelectorAll("article")).toHaveLength(1);
  });
  test("Menu non sincronizzato mantiene il prodotto, pur essendo salvato nella ricetta", async () => {
    axios.put.mockResolvedValueOnce({ data: { ok: true, prezzo_tavolo: 3.5, menu_sync: { esito: "errore" } } });
    await act(async () => root.render(<ListaReale />));
    await scrivi(node.querySelector("input[data-prezzo-rapido]"), "3,50"); await salva();
    expect(node.querySelectorAll("article")).toHaveLength(2);
    expect(node.querySelector('[role="alert"]').textContent).toContain("Prezzo salvato nella ricetta");
    await salva(); expect(node.querySelectorAll("article")).toHaveLength(1);
  });
  test("filtri di nome e reparto non modificano dati e si possono togliere", async () => {
    await act(async () => root.render(<ListaReale />));
    await scrivi(node.querySelector('input[aria-label="Cerca prodotto da prezzare"]'), "SFOGLIA");
    expect(node.querySelectorAll("article")).toHaveLength(1);
    expect(node.querySelector("article").textContent).toContain("Sfogliatella");
    await act(async () => { const select = node.querySelector("select"); select.value = "Rosticceria"; select.dispatchEvent(new Event("change", { bubbles: true })); });
    expect(node.querySelectorAll("article")).toHaveLength(0);
    await act(async () => Array.from(node.querySelectorAll("button")).find(b => b.textContent === "Togli filtri").click());
    expect(node.querySelectorAll("article")).toHaveLength(2);
    expect(axios.put).not.toHaveBeenCalled();
  });
  test("In menu apre la lista per admin e aggiorna conteggio e vetrina dopo il salvataggio", async () => {
    await act(async () => root.render(<MenuVetrinaView />));
    expect(node.textContent).toContain("Prezzi da completare (2)");
    await scrivi(node.querySelector("input[data-prezzo-rapido]"), "3,50"); await salva();
    expect(node.textContent).toContain("Prezzi da completare (1)");
    await act(async () => Array.from(node.querySelectorAll("button")).find(b => b.textContent.startsWith("Vetrina prodotti")).click());
    expect(node.textContent).toContain("Parigina");
    expect(node.textContent).toContain("3.50");
  });
  test("gli operatori non vedono controlli amministrativi dei prezzi", async () => {
    isAdmin.mockReturnValue(false);
    await act(async () => root.render(<MenuVetrinaView />));
    expect(node.querySelector("input[data-prezzo-rapido]")).toBeNull();
    expect(node.textContent).not.toContain("Prezzi da completare");
  });
});
