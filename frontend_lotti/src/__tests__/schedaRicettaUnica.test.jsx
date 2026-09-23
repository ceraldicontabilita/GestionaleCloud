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
