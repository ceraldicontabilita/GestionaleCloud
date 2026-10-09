import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import { CalcoloTab, RICETTE } from "../components/haccp/GelatiView";
import { scalaIngredienti } from "../components/haccp/gelati/calcoloProduzione";

global.IS_REACT_ACT_ENVIRONMENT = true;

test("il sorbetto Limone Easy scala la formula documentata senza inventare succo o gradi", async () => {
  const ricetta = RICETTE["Sorbetto Limone Easy Galatea"];
  expect(ricetta.base).toBe(5000);
  expect(ricetta.fonte).toContain("p. 4");
  expect(ricetta.fonte).toContain("76001");
  expect(ricetta.prep).toContain("temperatura in °C");
  expect(ricetta.prep).toContain("succo di limone fresco");
  expect(scalaIngredienti(ricetta.ing, ricetta.base, 1000).map(({ q }) => q)).toEqual([300, 700]);
  expect(scalaIngredienti(ricetta.ing, ricetta.base, 2500).map(({ q }) => q)).toEqual([750, 1750]);
  expect(scalaIngredienti(ricetta.ing, ricetta.base, 10000).map(({ q }) => q)).toEqual([3000, 7000]);

  const get = jest.spyOn(axios, "get").mockResolvedValue({ data: { disponibili: [], gusti: [] } });
  const node = document.createElement("div");
  document.body.appendChild(node);
  const root = createRoot(node);
  try {
    await act(async () => root.render(<CalcoloTab />));
    const ricette = node.querySelector("select");
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set.call(ricette, "Sorbetto Limone Easy Galatea");
      ricette.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(node.textContent).toContain("Easy Limone Libera (76001)");
    expect(node.textContent).toContain("Acqua calda");
    expect(node.textContent).toContain("Misura l'acqua: 3,5 L calda");
    expect(node.textContent).toContain("Fonte: Galatea, brochure Core_Inside Frutta");
    expect(node.textContent).toContain("non una produzione o una giacenza registrata");
    await act(async () => node.querySelector('button[aria-label^="Peso totale da produrre."]').click());
    const rapidi = node.querySelector('[aria-label="Quantità rapide"]');
    expect([...rapidi.querySelectorAll("button")].map((b) => Number(b.textContent.replace(/\D/g, "")))).toEqual([1000, 2500, 5000, 10000]);
  } finally {
    await act(async () => root.unmount());
    node.remove();
    get.mockRestore();
  }
});
