import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import PannelloLievito, { condizioniComplete } from "../components/haccp/shared/PannelloLievito";

global.IS_REACT_ACT_ENVIRONMENT = true;

const attendi = (ms) => act(async () => { await new Promise((r) => setTimeout(r, ms)); });

function scrivi(input, valore) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  setter.call(input, valore);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

async function monta(elemento) {
  const node = document.createElement("div");
  document.body.appendChild(node);
  const root = createRoot(node);
  await act(async () => root.render(elemento));
  return { node, smonta: async () => { await act(async () => root.unmount()); node.remove(); } };
}

afterEach(() => jest.restoreAllMocks());

test("condizioni complete solo con ore e temperatura, e il frigo vuole la sua temperatura", () => {
  expect(condizioniComplete({ ore_ambiente: "8", temperatura_c: "" })).toBeNull();
  expect(condizioniComplete({ ore_ambiente: "8", temperatura_c: "24" })).toEqual({ ore_ambiente: 8, temperatura_c: 24 });
  expect(condizioniComplete({ ore_ambiente: "2", temperatura_c: "22", ore_frigo: "24", temperatura_frigo_c: "" })).toBeNull();
  expect(condizioniComplete({ ore_ambiente: "2", temperatura_c: "22", ore_frigo: "24", temperatura_frigo_c: "4" }))
    .toEqual({ ore_ambiente: 2, temperatura_c: 22, ore_frigo: 24, temperatura_frigo_c: 4 });
});

test("una ricetta senza lievito di birra non mostra il pannello", async () => {
  jest.spyOn(axios, "post").mockResolvedValue({ data: { stato: "senza_lievito", righe: [] } });
  const { node, smonta } = await monta(<PannelloLievito ricetta={{ id: "r1" }} pezzi={10} />);
  await attendi(300);
  expect(node.textContent).toBe("");
  await smonta();
});

test("senza riferimento chiede per quale lievitazione vale la dose e lo salva nella ricetta", async () => {
  jest.spyOn(axios, "post").mockResolvedValue({ data: { stato: "manca_riferimento",
    righe: [{ nome: "Lievito", ricetta: 15, oggi: null, unita: "g" }] } });
  const patch = jest.spyOn(axios, "patch").mockResolvedValue({ data: { success: true } });
  const { node, smonta } = await monta(<PannelloLievito ricetta={{ id: "r1" }} pezzi={10} />);
  await attendi(300);
  expect(node.textContent).toContain("non dice per quale lievitazione");
  await act(async () => {
    scrivi(node.querySelector("#rif-r1-ore"), "8");
    scrivi(node.querySelector("#rif-r1-temp"), "24");
  });
  await act(async () => { [...node.querySelectorAll("button")].find((b) => b.textContent === "Salva nella ricetta").click(); });
  expect(patch).toHaveBeenCalledWith(expect.stringContaining("/ricette/r1"),
    { lievitazione_riferimento: { ore_ambiente: 8, temperatura_c: 24 } });
  await smonta();
});

test("con riferimento mostra il lievito di oggi e passa le condizioni al chiamante", async () => {
  const post = jest.spyOn(axios, "post").mockImplementation((url, corpo) => Promise.resolve({ data: corpo.lievitazione
    ? { stato: "ricalcolato", fattore: 0.435, riferimento: { ore_ambiente: 8, temperatura_c: 24 },
      righe: [{ nome: "Lievito di birra", ricetta: 40, oggi: 17.4, unita: "g" }], avvisi: [] }
    : { stato: "manca_condizioni", riferimento: { ore_ambiente: 8, temperatura_c: 24 },
      righe: [{ nome: "Lievito di birra", ricetta: 40, oggi: null, unita: "g" }] } }));
  const onCambia = jest.fn();
  const { node, smonta } = await monta(<PannelloLievito ricetta={{ id: "r2" }} pezzi={20} onCambia={onCambia} />);
  await attendi(300);
  expect(node.textContent).toContain("vale per 8 ore a 24 °C");
  await act(async () => {
    scrivi(node.querySelector("#oggi-r2-ore"), "16");
    scrivi(node.querySelector("#oggi-r2-temp"), "24");
  });
  await attendi(300);
  expect(onCambia).toHaveBeenLastCalledWith({ ore_ambiente: 16, temperatura_c: 24 });
  expect(post).toHaveBeenLastCalledWith(expect.stringContaining("/ricetta/r2/lievito"),
    { pezzi: 20, lievitazione: { ore_ambiente: 16, temperatura_c: 24 } });
  expect(node.textContent).toContain("17,4 g");
  await smonta();
});
