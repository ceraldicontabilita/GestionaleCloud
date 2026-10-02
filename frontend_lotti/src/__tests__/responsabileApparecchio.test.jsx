import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import AttrezzatureView, { ID_TITOLARE } from "../components/haccp/AttrezzatureView";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("../components/haccp/shared/SegnalaGuasto", () => () => null);

const RISPOSTE = {
  "/attrezzature/": {
    frigoriferi: [
      { tipo: "frigo", numero: 1, nome: "Frigorifero N°1", operatore_id: ID_TITOLARE, operatore_nome: "Ceraldi Vincenzo", responsabile_predefinito: true },
      { tipo: "frigo", numero: 2, nome: "Frigorifero N°2", operatore_id: "hr-7", operatore_nome: "Pocci Salvatore", responsabile_predefinito: false },
    ],
    congelatori: [],
  },
  "/tablet-operatori": [
    { dipendente_id: "hr-7", nome: "Pocci Salvatore", in_carico: true, ruolo: "operatore" },
    { dipendente_id: "hr-9", nome: "Moscato Antonio", in_carico: true, ruolo: "operatore" },
    { dipendente_id: "hr-1", nome: "Ceraldi Vincenzo", in_carico: true, ruolo: "amministratore" },
    { dipendente_id: null, nome: "Cessato", in_carico: false, ruolo: "operatore" },
  ],
  "/azienda": { responsabile_haccp: "Ceraldi Vincenzo" },
};

describe("responsabile per apparecchio", () => {
  let node;
  let root;

  beforeEach(() => {
    node = document.createElement("div");
    document.body.appendChild(node);
    root = createRoot(node);
    jest.spyOn(axios, "get").mockImplementation((url) => {
      const chiave = Object.keys(RISPOSTE).find((k) => url.endsWith(k));
      return Promise.resolve({ data: RISPOSTE[chiave] });
    });
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    node.remove();
    jest.restoreAllMocks();
  });

  test("ogni apparecchio ha una tendina con il titolare e i dipendenti in carico", async () => {
    await act(async () => root.render(<AttrezzatureView />));
    const tendine = node.querySelectorAll("select[aria-label^='Responsabile']");
    expect(tendine).toHaveLength(2);
    const opzioni = Array.from(tendine[0].options).map((o) => o.textContent);
    expect(opzioni).toEqual(["Titolare (Ceraldi Vincenzo)", "Pocci Salvatore", "Moscato Antonio"]);
    expect(tendine[0].value).toBe(ID_TITOLARE);
    expect(tendine[1].value).toBe("hr-7");
    expect(parseInt(tendine[0].style.minHeight, 10)).toBeGreaterThanOrEqual(44);
  });

  test("la scelta scrive PUT /attrezzature/{tipo}/{numero}/responsabile", async () => {
    const put = jest.spyOn(axios, "put").mockResolvedValue({ data: { success: true, message: "Responsabile: Moscato Antonio" } });
    await act(async () => root.render(<AttrezzatureView />));
    const tendina = node.querySelector("select[aria-label='Responsabile frigorifero numero 1']");
    const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, "value").set;
    await act(async () => {
      setter.call(tendina, "hr-9");
      tendina.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(put).toHaveBeenCalledTimes(1);
    expect(put.mock.calls[0][0]).toMatch(/\/attrezzature\/frigo\/1\/responsabile$/);
    expect(put.mock.calls[0][1]).toEqual({ operatore_id: "hr-9" });
  });
});
