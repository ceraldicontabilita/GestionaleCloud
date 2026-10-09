import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import axios from "axios";
import ImpostazioniPersonaleView from "../components/haccp/ImpostazioniPersonaleView";

jest.mock("axios");
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), warning: jest.fn() } }));

const OPERATORE = { nome: "Capezzuto Alessandro", cognome: "Capezzuto", dipendente_id: "hr-1", in_carico: true, pin_impostato: true, ruolo_lotti: "operatore" };

describe("attestati di formazione nel Personale", () => {
  let node, root;
  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    axios.get.mockImplementation((url) => {
      if (url.endsWith("/tablet-operatori")) return Promise.resolve({ data: [OPERATORE] });
      if (url.endsWith("/attestati/elenco")) return Promise.resolve({ data: { "hr-1": [{ id: "a1", titolo: "Attestato formazione alimentarista (corso di 8 ore)", data_attestato: "2026-06-10", nome_file: "x.pdf" }] } });
      return Promise.resolve({ data: {} });
    });
    axios.post.mockResolvedValue({ data: {} });
    node = document.createElement("div");
    document.body.appendChild(node);
    root = createRoot(node);
  });
  afterEach(async () => { await act(async () => root.unmount()); node.remove(); });

  test("l'attestato compare nella scheda del dipendente con la data in gg/mm/aaaa", async () => {
    await act(async () => { root.render(<ImpostazioniPersonaleView />); await new Promise((r) => setTimeout(r, 0)); });
    const riga = node.querySelector('[data-testid="attestati-hr-1"]');
    expect(riga).not.toBeNull();
    expect(riga.textContent).toContain("10/06/2026");
    // Il caricamento è del dipendente (portale) e dell'amministratore (HR): in Lotti si guarda soltanto.
    expect(riga.textContent).not.toContain("Allega attestato");
    expect(node.querySelector('[data-testid="importa-attestati"]')).toBeNull();
    expect(node.textContent).not.toContain("Codice destinatario SDI");
  });
});
