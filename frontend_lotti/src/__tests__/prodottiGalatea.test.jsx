import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import { ProdottiTab } from "../components/haccp/GelatiView";

global.IS_REACT_ACT_ENVIRONMENT = true;

test("il pannello mostra solo righe acquistate con la fattura di provenienza", async () => {
  const get = jest.spyOn(axios, "get").mockResolvedValue({ data: {
    fornitore: "GELINOVA GROUP SRL", fatture: 1, righe: 2,
    prodotti: [
      { id: "f1:1", descrizione: "SET_CORE VELLUTO 540 KG 2X8", codice_articolo: "71004", quantita: "32", unita_misura: "kg", prezzo_unitario: "13.2", fattura_id: "f1", numero_fattura: "001852/2", data_fattura: "14/05/2026" },
      { id: "f1:2", descrizione: "CARAFFA 5LT GALATEA", codice_articolo: "60407", quantita: "4", prezzo_unitario: "7.3", fattura_id: "f1", numero_fattura: "001852/2", data_fattura: "14/05/2026" },
    ],
  } });
  const node = document.createElement("div");
  document.body.appendChild(node);
  const root = createRoot(node);
  try {
    await act(async () => root.render(<ProdottiTab />));
    expect(get).toHaveBeenCalledWith(expect.stringContaining("/gelati/prodotti-galatea"));
    expect(node.textContent).toContain("SET_CORE VELLUTO 540");
    expect(node.textContent).toContain("CARAFFA 5LT GALATEA");
    expect(node.textContent).toContain("001852/2");
    expect(node.textContent).toContain("2 righe da 1 fattura");
    expect(node.textContent).toContain("Scorta residua non verificata");
    expect(node.querySelectorAll("article")).toHaveLength(2);
    expect(node.querySelector("table")).not.toBeNull();
    expect(node.querySelector("article dl").textContent).toContain("32 kg");
    expect(node.querySelector("article dl").textContent).toContain("13,2 €");
    expect(node.querySelector('button[aria-label="Apri fattura 001852/2"]')).not.toBeNull();
    const ricerca = node.querySelector('input[type="search"]');
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(ricerca, "71004");
      ricerca.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(node.textContent).toContain("SET_CORE VELLUTO 540");
    expect(node.textContent).not.toContain("CARAFFA 5LT GALATEA");
    expect(node.textContent).toContain("1 riga trovata");
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(ricerca, "inesistente");
      ricerca.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(node.textContent).toContain("Nessuna riga corrisponde alla ricerca");
    expect(node.querySelectorAll("article")).toHaveLength(0);
  } finally {
    await act(async () => root.unmount());
    node.remove();
    jest.restoreAllMocks();
  }
});
