import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import SanificazioneView from "../components/haccp/SanificazioneView";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), warning: jest.fn() } }));
jest.mock("../auth", () => ({ apriDocumentoAutenticato: jest.fn() }));

describe("sanificazione apparecchi con nomi centralizzati", () => {
  let node;
  let root;

  beforeEach(() => {
    node = document.createElement("div");
    document.body.appendChild(node);
    root = createRoot(node);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    node.remove();
    jest.restoreAllMocks();
  });

  test("mostra i nomi canonici invece delle etichette generiche", async () => {
    jest.spyOn(axios, "get").mockImplementation((url) => {
      if (url.includes("/sanificazione/scheda/")) {
        return Promise.resolve({ data: { azienda: "Ceraldi Group S.R.L.", area: "Sala e Servizi", registrazioni: {} } });
      }
      if (url.endsWith("/sanificazione/attrezzature")) {
        return Promise.resolve({ data: [] });
      }
      return Promise.resolve({ data: {
        apparecchi_frigoriferi: [
          { numero: 5, nome: "FRIGO PASTICCERIA 5" },
          { numero: 13, nome: "FRIGO ROSTICCERIA 13" },
        ],
        apparecchi_congelatori: [
          { numero: 1, nome: "CONGELATORE PASTICCERIA 1" },
          { numero: 7, nome: "CONGELATORE SAMMONTANA" },
        ],
        registrazioni_frigoriferi: {},
        registrazioni_congelatori: {},
      } });
    });

    await act(async () => root.render(<SanificazioneView />));
    const tab = Array.from(node.querySelectorAll("button")).find((b) => b.textContent.includes("Apparecchi Refrigeranti"));
    await act(async () => tab.click());

    expect(node.textContent).toContain("FRIGO PASTICCERIA 5");
    expect(node.textContent).toContain("FRIGO ROSTICCERIA 13");
    expect(node.textContent).toContain("CONGELATORE PASTICCERIA 1");
    expect(node.textContent).toContain("CONGELATORE SAMMONTANA");
    expect(node.textContent).not.toContain("Frigo1");
    expect(node.textContent).not.toContain("Cong1");
  });
});
