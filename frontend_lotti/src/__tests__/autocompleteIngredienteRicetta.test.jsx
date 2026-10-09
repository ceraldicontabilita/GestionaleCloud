import React, { useState } from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import {
  nomeProdottoConInizialiMaiuscole,
  RigaIngrediente,
} from "../components/haccp/backoffice/FormRicetta";

jest.mock("axios");
global.IS_REACT_ACT_ENVIRONMENT = true;

function RigaDiProva() {
  const [ingrediente, setIngrediente] = useState({ nome: "", quantita: "", unita: "g" });
  return (
    <RigaIngrediente
      ing={ingrediente}
      idx={0}
      onChange={(_indice, campo, valore) => setIngrediente((corrente) => ({ ...corrente, [campo]: valore }))}
      onRemove={() => {}}
    />
  );
}

test("i nomi dei prodotti hanno tutte le iniziali maiuscole", () => {
  expect(nomeProdottoConInizialiMaiuscole("POMODORO già CONDITO")).toBe("Pomodoro Già Condito");
  expect(nomeProdottoConInizialiMaiuscole("farina 0/man. caputo")).toBe("Farina 0/Man. Caputo");
});

test("digitando il nome propone i prodotti reali e permette di selezionarli", async () => {
  jest.useFakeTimers();
  axios.get.mockResolvedValue({ data: [{
    nome_canonico: "POMODORO PELATO",
    nome_normalizzato: "pomodoro pelato 3 kg",
    fornitore: "Fornitore reale",
    prezzo_kg: 1.75,
  }] });
  const node = document.createElement("div");
  document.body.appendChild(node);
  const root = createRoot(node);

  try {
    await act(async () => root.render(<RigaDiProva />));
    const input = node.querySelector('input[placeholder^="Ingrediente"]');
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, "pomodoro");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      jest.advanceTimersByTime(250);
      await Promise.resolve();
    });

    expect(axios.get).toHaveBeenCalledWith(
      expect.stringContaining("/food-cost/dizionario/search"),
      { params: { q: "pomodoro" } },
    );
    expect(node.textContent).toContain("Pomodoro Pelato");
    expect(node.textContent).toContain("Fornitore reale");

    const suggerimento = [...node.querySelectorAll("button")]
      .find((button) => button.textContent.includes("Pomodoro Pelato"));
    await act(async () => suggerimento.click());
    expect(input.value).toBe("Pomodoro Pelato");
  } finally {
    await act(async () => root.unmount());
    node.remove();
    jest.useRealTimers();
  }
});
