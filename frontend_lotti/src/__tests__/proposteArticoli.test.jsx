import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import ProposteArticoliPanel from "../components/haccp/ProposteArticoliPanel";

global.IS_REACT_ACT_ENVIRONMENT = true;

const proposte = [
  {
    descrizione_key: "olva thermo crema gateaux",
    descrizione_originale: "OLVA THERMO CREMA GATEAUX",
    fornitore: "RONDINELLA MARKET S.R.L.",
    nome_canc: "Margarina",
    ingredienti_ricetta: ["margarina", "burro"],
    cosa_e: "Margarina vegetale per creme e impasti",
    fonte_url: "https://esempio.it/olva",
    confidenza: "alta",
    alimentare: true,
  },
  {
    descrizione_key: "borsa tnt sole365",
    descrizione_originale: "BORSA TNT SOLE365",
    nome_canc: "Non alimentare",
    alimentare: false,
    confidenza: "alta",
  },
];

async function monta() {
  const node = document.createElement("div");
  document.body.appendChild(node);
  const root = createRoot(node);
  await act(async () => root.render(<ProposteArticoliPanel canonici={["Margarina"]} />));
  return { node, root };
}

afterEach(() => jest.restoreAllMocks());

test("conferma la proposta togliendo un ingrediente con un tocco", async () => {
  jest.spyOn(axios, "get").mockResolvedValue({ data: { voci: proposte } });
  const post = jest.spyOn(axios, "post").mockResolvedValue({ data: { lotti_aggiornati: 5 } });
  const { node, root } = await monta();
  try {
    expect(node.textContent).toContain("OLVA THERMO CREMA GATEAUX");
    expect(node.textContent).toContain("Margarina vegetale per creme e impasti");
    expect(node.textContent).toContain("sicura");
    const burro = [...node.querySelectorAll("button")].find((b) => b.textContent === "burro ×");
    await act(async () => burro.click());
    const conferma = [...node.querySelectorAll("button")].find((b) => b.textContent.includes("Conferma"));
    await act(async () => conferma.click());
    expect(post).toHaveBeenCalledWith(expect.stringContaining("/normalizzazione/conferma-articolo"), {
      descrizione: "olva thermo crema gateaux",
      nome_canc: "Margarina",
      ingredienti_ricetta: ["margarina"],
      alimentare: true,
    });
    expect(node.textContent).not.toContain("OLVA THERMO CREMA GATEAUX");
  } finally {
    await act(async () => root.unmount());
    node.remove();
  }
});

test("una riga non alimentare si conferma come tale", async () => {
  jest.spyOn(axios, "get").mockResolvedValue({ data: { voci: [proposte[1]] } });
  const post = jest.spyOn(axios, "post").mockResolvedValue({ data: { lotti_aggiornati: 0 } });
  const { node, root } = await monta();
  try {
    expect(node.textContent).toContain("Proposta: non è un ingrediente");
    const conferma = [...node.querySelectorAll("button")].find((b) => b.textContent.includes("Conferma"));
    await act(async () => conferma.click());
    expect(post.mock.calls[0][1]).toMatchObject({ descrizione: "borsa tnt sole365", alimentare: false });
  } finally {
    await act(async () => root.unmount());
    node.remove();
  }
});

test("errore di caricamento con Riprova", async () => {
  jest.spyOn(axios, "get").mockRejectedValue(new Error("rete"));
  const { node, root } = await monta();
  try {
    expect(node.querySelector('[role="alert"]')).not.toBeNull();
    expect(node.textContent).toContain("Riprova");
  } finally {
    await act(async () => root.unmount());
    node.remove();
  }
});
