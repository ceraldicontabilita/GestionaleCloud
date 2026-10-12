import React, { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import { toast } from "sonner";
import ProdottiVenditaView from "../components/haccp/ProdottiVenditaView";

jest.mock("axios", () => ({ get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("../components/haccp/BulkPrezziView", () => () => null);
jest.mock("../components/haccp/CatalogoFornitoreView", () => () => <div>Catalogo MEPA</div>);
jest.mock("../components/haccp/CatalogoGenericoView", () => () => null);
jest.mock("../components/haccp/SaimaRicettariView", () => () => null);
jest.mock("../components/haccp/CartelliIngredientiBarView", () => () => null);
jest.mock("../components/haccp/prodotti/ModalProdotto", () => () => null);
jest.mock("../components/haccp/prodotti/ProdottoCard", () => () => null);
jest.mock("../components/haccp/prodotti/SenzaPesoPanel", () => () => null);
jest.mock("../components/haccp/prodotti/VistaTabellaPrezzi", () => () => null);

global.IS_REACT_ACT_ENVIRONMENT = true;
let node, root;

beforeEach(() => {
  window.history.replaceState(null, "", "#prodotti/mepa");
  axios.get.mockReset();
  axios.post.mockReset();
  toast.success.mockReset();
  toast.error.mockReset();
  axios.get.mockImplementation(async url => {
    if (url.endsWith("/fonti-catalogo")) return { data: [] };
    if (url.includes("prodotti-senza-peso")) return { data: { total: 0 } };
    if (url.endsWith("/cataloghi/preferiti/mepa")) return { data: {
      fatture: 10,
      prodotti: [
        { id: "mandorle", gia_acquistato: true, prezzo_fattura: 10.1299 },
        { id: "omaggio", gia_acquistato: true, prezzo_fattura: 0 },
      ],
    } };
    return { data: [] };
  });
  node = document.createElement("div");
  document.body.appendChild(node);
  root = createRoot(node);
});

afterEach(async () => {
  await act(async () => root.unmount());
  node.remove();
});

test("Sync Fatture nella scheda MEPA rilegge le fatture canoniche e non Acquaviva", async () => {
  await act(async () => root.render(<ProdottiVenditaView defaultTab="mepa" />));
  const sync = [...node.querySelectorAll("button")].find(b => b.textContent.includes("Sync Fatture"));
  await act(async () => sync.click());

  expect(axios.get).toHaveBeenCalledWith(expect.stringContaining("/cataloghi/preferiti/mepa"));
  expect(axios.post).not.toHaveBeenCalledWith(expect.stringContaining("sync-acquaviva"));
  expect(toast.success).toHaveBeenCalledWith("Fatture lette: 10 · 2 prodotti · 1 prezzo · 1 senza prezzo in fattura");
});
