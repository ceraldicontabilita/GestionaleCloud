import React, { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import MagazzinoBarView from "../components/haccp/MagazzinoBarView";
import { saveToken } from "../auth";
import { clearTabletSession, saveTabletSession } from "../utils/tabletSession";

jest.mock("axios");
global.IS_REACT_ACT_ENVIRONMENT = true;

test("il prelievo usa il dipendente della sessione senza richiedere un secondo PIN", async () => {
  localStorage.clear();
  clearTabletSession();
  saveToken("token-di-test");
  saveTabletSession({ dipendente_id: "hr-1", nome: "Operatore Uno", ruolo: "operatore" }, "magazzino");
  axios.get.mockImplementation((url) => {
    if (url.includes("prodotti-unificati")) {
      return Promise.resolve({ data: [{ id: "p-1", nome: "Farina", source: "bar", stock: 10, unita: "kg" }] });
    }
    if (url.includes("richieste")) return Promise.resolve({ data: { richieste: [] } });
    return Promise.resolve({ data: [] });
  });
  axios.post.mockResolvedValue({ data: {} });
  const node = document.createElement("div");
  document.body.appendChild(node);
  const root = createRoot(node);
  try {
    await act(async () => root.render(<MagazzinoBarView onBack={() => {}} />));
    await act(async () => [...node.querySelectorAll("button")].find((b) => b.textContent.includes("Preleva")).click());
    await act(async () => [...node.querySelectorAll("button")].find((b) => b.textContent === "Scarica").click());
    expect(axios.post).toHaveBeenCalledWith(expect.stringContaining("/magazzino/scarico"),
      expect.objectContaining({ prodotto_id: "p-1", operatore_nome: "Operatore Uno" }),
      expect.any(Object));
    expect(node.textContent).not.toContain("Conferma il tuo PIN");
  } finally {
    await act(async () => root.unmount());
    node.remove();
    jest.clearAllMocks();
  }
});

test("prezzo e carrello si vedono solo al titolare", async () => {
  const prova = async (ruolo) => {
    localStorage.clear();
    clearTabletSession();
    saveToken("token-di-test");
    saveTabletSession({ dipendente_id: "hr-1", nome: "Operatore Uno", ruolo }, "magazzino");
    axios.get.mockImplementation((url) => {
      if (url.includes("prodotti-unificati")) {
        return Promise.resolve({ data: [{ id: "l-2", nome: "Farina", source: "fornitori", stock: 10, unita: "KG", fornitore: "Ditta Uno", lotti_ids: ["l-1", "l-2"] }] });
      }
      if (url.includes("prezzi-lotti")) {
        return Promise.resolve({ data: { prezzi: { "l-1": { prezzo: 1, fornitore: "Ditta Uno", data: "2026-01-01" }, "l-2": { prezzo: 1.25, fornitore: "Ditta Uno", data: "2026-08-01" } } } });
      }
      if (url.includes("richieste")) return Promise.resolve({ data: { richieste: [] } });
      return Promise.resolve({ data: [] });
    });
    axios.put.mockResolvedValue({ data: {} });
    const node = document.createElement("div");
    document.body.appendChild(node);
    const root = createRoot(node);
    await act(async () => root.render(<MagazzinoBarView onBack={() => {}} />));
    await act(async () => [...node.querySelectorAll("button")].find((b) => b.textContent.includes("Preleva")).click());
    const testo = node.textContent;
    const ordina = [...node.querySelectorAll("button")].find((b) => b.textContent.includes("Ordina"));
    await act(async () => root.unmount());
    node.remove();
    jest.clearAllMocks();
    return { testo, ordina };
  };
  const dip = await prova("operatore");
  expect(dip.testo).not.toContain("1,25");
  expect(dip.ordina).toBeUndefined();
  const tit = await prova("amministratore");
  expect(tit.testo).toContain("1,25");
  expect(tit.ordina).toBeDefined();
});
