import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import SchedaRicettaChiaraModal from "../components/haccp/SchedaRicettaChiaraModal";

jest.mock("axios");
global.IS_REACT_ACT_ENVIRONMENT = true;

// La card di reparto apre la stessa scheda del ricettario passando solo l'id.
test("la scheda si carica per id e mostra allergeni e modo di preparazione", async () => {
  axios.get.mockResolvedValue({ data: {
    id: "r1", nome: "Amaretti cioccolata", ingredienti: ["Mandorle dolci", "Zucchero"],
    allergeni: ["Frutta a guscio"], procedimento_testo: "",
  } });
  axios.post.mockResolvedValue({ data: {} });
  const node = document.createElement("div");
  document.body.appendChild(node);
  const root = createRoot(node);
  try {
    await act(async () => root.render(<SchedaRicettaChiaraModal ricettaId="r1" nome="Amaretti cioccolata" onClose={() => {}} modificaRapida />));
    expect(axios.get).toHaveBeenCalledWith(expect.stringMatching(/\/ricette\/r1$/));
    expect(node.textContent).toContain("Amaretti cioccolata");
    expect(node.textContent).toContain("Frutta a guscio");
    // Un procedimento mancante si dice, non si nasconde la sezione.
    expect(node.textContent).toContain("Procedimento non ancora indicato.");
    expect(node.textContent).toContain("Modifica ricetta");
  } finally {
    await act(async () => root.unmount());
    node.remove();
  }
});

test("un errore di lettura si mostra senza pagine HTML", async () => {
  axios.get.mockRejectedValue({ response: { status: 503, data: "<!DOCTYPE html><html></html>" } });
  const node = document.createElement("div");
  document.body.appendChild(node);
  const root = createRoot(node);
  try {
    await act(async () => root.render(<SchedaRicettaChiaraModal ricettaId="r2" onClose={() => {}} />));
    expect(node.textContent).toContain("Il server si sta riavviando");
    expect(node.textContent).not.toContain("DOCTYPE");
  } finally {
    await act(async () => root.unmount());
    node.remove();
  }
});

test("un procedimento preso dal web mostra la fonte e si conferma", async () => {
  axios.get.mockResolvedValue({ data: {
    id: "r3", nome: "Pan di Spagna", ingredienti: ["Uova"], procedimento_testo: "1. Montare le uova.",
    procedimento_origine: "web", procedimento_da_verificare: true,
    procedimento_fonte: { url: "https://esempio.it/pan-di-spagna", titolo: "Pan di Spagna classico", compatibilita: "la fonte usa la fecola" },
  } });
  axios.post.mockResolvedValue({ data: {} });
  const node = document.createElement("div");
  document.body.appendChild(node);
  const root = createRoot(node);
  try {
    await act(async () => root.render(<SchedaRicettaChiaraModal ricettaId="r3" onClose={() => {}} modificaRapida />));
    expect(node.textContent).toContain("Preso dal web, da verificare");
    expect(node.querySelector('a[href="https://esempio.it/pan-di-spagna"]')).toBeTruthy();
    expect(node.textContent).toContain("la fonte usa la fecola");
    const conferma = [...node.querySelectorAll("button")].find(b => b.textContent.includes("Confermo il procedimento"));
    await act(async () => conferma.click());
    expect(axios.post).toHaveBeenCalledWith(expect.stringMatching(/\/ricette\/r3\/procedimento\/conferma$/));
    expect(node.textContent).toContain("Preso dal web, confermato");
  } finally {
    await act(async () => root.unmount());
    node.remove();
  }
});

test("chi non puo' modificare vede la fonte ma non il bottone di conferma", async () => {
  axios.get.mockResolvedValue({ data: {
    id: "r4", nome: "X", procedimento_testo: "1. Passo.", procedimento_origine: "web", procedimento_da_verificare: true,
    procedimento_fonte: { url: "https://esempio.it/x", titolo: "X" },
  } });
  const node = document.createElement("div");
  document.body.appendChild(node);
  const root = createRoot(node);
  try {
    await act(async () => root.render(<SchedaRicettaChiaraModal ricettaId="r4" onClose={() => {}} />));
    expect(node.textContent).toContain("Preso dal web, da verificare");
    expect(node.textContent).not.toContain("Confermo il procedimento");
  } finally {
    await act(async () => root.unmount());
    node.remove();
  }
});
