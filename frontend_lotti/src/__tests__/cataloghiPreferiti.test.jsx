import React, { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import CatalogoFornitoreView from "../components/haccp/CatalogoFornitoreView";
import CatalogoGenericoView from "../components/haccp/CatalogoGenericoView";

jest.mock("axios", () => ({ get: jest.fn(), put: jest.fn(), post: jest.fn() }));
global.IS_REACT_ACT_ENVIRONMENT = true;
const mapItem = p => ({ ...p, raw: p });
const p = { id: "p1", nome: "Mozzarella già comprata", codice_articolo: "M001", prezzo_fattura: 4, gia_acquistato: true };
let node, root;
const button = text => [...node.querySelectorAll("button")].find(b => b.textContent.includes(text));
const input = () => node.querySelector('input[type="search"]');
async function digita(value) {
  await act(async () => {
    input().focus();
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input(), value);
    input().dispatchEvent(new Event("input", { bubbles: true }));
  });
}
async function clock(ms) { await act(async () => jest.advanceTimersByTime(ms)); }
const mepa = () => <CatalogoFornitoreView fornitore="mepa" nome="Me.Pa" colore="mepa" />;
const catalogoFornitore = sourceKey => <CatalogoFornitoreView fornitore={sourceKey} nome={sourceKey} />;

beforeEach(() => {
  jest.useFakeTimers(); sessionStorage.clear(); localStorage.clear();
  window.history.replaceState(null, "", "#prodotti/mepa");
  axios.get.mockReset();
  axios.get.mockImplementation(async url => {
    if (url.includes("cataloghi/preferiti/")) return { data: { prodotti: [p] } };
    if (url.endsWith("scraping/stato")) return { data: { stato: "in_corso", prodotti_nel_db: 3000 } };
    if (url.endsWith("categorie")) return { data: ["Latticini"] };
    if (url.endsWith("mepa/prodotti")) return { data: { prodotti: [p] } };
    if (url.endsWith("carrello-sospesi")) return { data: { righe: [] } };
    return { data: [] };
  });
  axios.put.mockResolvedValue({ data: {} });
  node = document.createElement("div"); document.body.appendChild(node); root = createRoot(node);
});
afterEach(async () => { await act(async () => root.unmount()); node.remove(); jest.useRealTimers(); });

test("scraping e tastiera non cancellano ricerca o carrello; ripristino dopo cambio pagina", async () => {
  localStorage.setItem("ordini_smart_carrello", JSON.stringify([{ id: "ordine", nome: "Riga in corso", quantita: 2 }]));
  await act(async () => root.render(mepa()));
  expect(button("Acquistati prima (1)").getAttribute("aria-pressed")).toBe("true");
  expect(node.textContent).not.toContain("Preferito colazione");
  expect(node.textContent).not.toContain("Segna come preferito colazione");
  await digita("mozzarella"); await clock(15000);
  expect(input().value).toBe("mozzarella"); expect(document.activeElement).toBe(input());
  expect(node.textContent).toContain(p.nome);
  await act(async () => button("Nascondi tastiera").click());
  expect(document.activeElement).not.toBe(input()); expect(input().value).toBe("mozzarella");
  expect(JSON.parse(localStorage.getItem("ordini_smart_carrello"))[0].quantita).toBe(2);
  await act(async () => root.render(null)); await act(async () => root.render(mepa()));
  expect(input().value).toBe("mozzarella"); expect(node.textContent).toContain(p.nome);
});

test("una risposta vecchia della ricerca non sostituisce quella nuova", async () => {
  sessionStorage.setItem("catalogo:mepa:preferiti", "false");
  let first, second;
  const standard = axios.get.getMockImplementation();
  axios.get.mockImplementation((url, config) => {
    if (url.endsWith("mepa/prodotti") && config.params.q === "mo") return new Promise(r => { first = r; });
    if (url.endsWith("mepa/prodotti") && config.params.q === "mozzarella") return new Promise(r => { second = r; });
    return standard(url, config);
  });
  await act(async () => root.render(mepa()));
  await digita("mo"); await clock(450); await digita("mozzarella"); await clock(450);
  await act(async () => second({ data: { prodotti: [p] } }));
  await act(async () => first({ data: { prodotti: [] } }));
  expect(node.textContent).toContain(p.nome); expect(input().value).toBe("mozzarella");
  expect(document.activeElement).toBe(input());
});

test.each(["bindi", "tremarie", "fornitore-personalizzato"])("%s usa i preferiti da fattura e consente il catalogo completo", async sourceKey => {
  const standard = axios.get.getMockImplementation();
  axios.get.mockImplementation((url, cfg) => url.endsWith("/tutti")
    ? Promise.resolve({ data: [{ id: "nuovo", nome: "Articolo mai acquistato" }] }) : standard(url, cfg));
  await act(async () => root.render(<CatalogoGenericoView sourceKey={sourceKey} titolo={sourceKey} fetchUrl="/tutti" mapItem={mapItem} />));
  expect(axios.get).toHaveBeenCalledWith(expect.stringContaining(`/cataloghi/preferiti/${sourceKey}`));
  expect(node.textContent).toContain(p.nome); expect(node.textContent).not.toContain("Articolo mai acquistato");
  expect(node.textContent).not.toContain("Preferito colazione");
  expect(node.textContent).not.toContain("Segna come preferito colazione");
  await act(async () => button("Tutto il catalogo").click());
  expect(node.textContent).toContain("Articolo mai acquistato");
  await act(async () => button("Acquistati prima").click()); await digita("mozzarella");
  await act(async () => input().dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
  expect(document.activeElement).not.toBe(input()); expect(node.textContent).toContain(p.nome);
});

test("articolo originale fattura è ordinabile anche quando manca dal catalogo", async () => {
  const standard = axios.get.getMockImplementation();
  axios.get.mockImplementation((url, cfg) => url.includes("cataloghi/preferiti/")
    ? Promise.resolve({ data: { prodotti: [{ ...p, id: "acquisto_1", da_fattura_senza_catalogo: true }] } }) : standard(url, cfg));
  await act(async () => root.render(mepa()));
  expect(button("Acquista")).toBeTruthy(); expect(button("Al ricettario")).toBeUndefined();
});

test.each(["mepa", "saima", "acquaviva"])("%s non usa più i preferiti delle quattro stagioni", async sourceKey => {
  await act(async () => root.render(catalogoFornitore(sourceKey)));
  expect(axios.get).not.toHaveBeenCalledWith(expect.stringContaining("colazione-acquaviva/preferiti"));
  expect([...node.querySelectorAll("button")].some(b => /preferito colazione/i.test(b.getAttribute("aria-label") || b.textContent))).toBe(false);
  expect(node.textContent).toContain("I prodotti già acquistati compaiono subito");
});
