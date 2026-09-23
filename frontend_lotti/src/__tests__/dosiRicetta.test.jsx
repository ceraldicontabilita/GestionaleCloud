import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import DosiRicetta from "../components/haccp/shared/DosiRicetta";

global.IS_REACT_ACT_ENVIRONMENT = true;

test("il moltiplicatore nella scheda #ricette mostra le dosi calcolate dal server", async () => {
  const post = jest.spyOn(axios, "post").mockResolvedValue({ data: {
    base: "Farina", fattore: 2, porzioni_stimate: 40,
    ingredienti: [{ nome: "Farina", quantita: 2, unita: "kg" }, { nome: "Burro", quantita: 500, unita: "g" }],
  } });
  const node = document.createElement("div");
  document.body.appendChild(node);
  const root = createRoot(node);
  try {
    await act(async () => root.render(<DosiRicetta ricetta={{ id: "ricetta-1", ingredienti_dettaglio: [
      { nome: "Farina", quantita: 1, unita_misura: "kg" }, { nome: "Burro", quantita: 250, unita_misura: "g" },
    ] }} />));
    await act(async () => {
      node.querySelector('[aria-label="Aumenta dose"]').click();
    });
    await act(async () => {
      node.querySelector('[aria-label="Aumenta dose"]').click();
      await new Promise((resolve) => setTimeout(resolve, 250));
    });
    expect(post).toHaveBeenCalledWith(expect.stringContaining("/ricetta/ricetta-1/dose-produzione"), { moltiplicatore: 2, normalizza_1kg: true });
    expect(node.textContent).toContain("500 g");
  } finally {
    await act(async () => root.unmount());
    node.remove();
    jest.restoreAllMocks();
  }
});
