import React, { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import VenditaBancoView from "../components/haccp/VenditaBancoView";
import { saveToken } from "../auth";
import { clearTabletSession, saveTabletSession } from "../utils/tabletSession";

jest.mock("axios");
jest.mock("date-fns", () => ({ format: () => "21 settembre 2026", subDays: (date) => date, parseISO: (value) => new Date(value) }));
jest.mock("date-fns/locale", () => ({ it: {} }));
jest.mock("../components/haccp/shared/PinKeypad", () => ({ onSuccess }) => (
  <button onClick={() => onSuccess({ dipendente_id: "hr-1", nome: "Operatore Uno", ruolo: "operatore" })}>
    Verifica PIN serale
  </button>
));
global.IS_REACT_ACT_ENVIRONMENT = true;

test("gli invenduti chiedono il PIN al primo salvataggio, poi usano la stessa identità", async () => {
  localStorage.clear();
  clearTabletSession();
  saveToken("token-di-test");
  saveTabletSession({ dipendente_id: "hr-1", nome: "Operatore Uno", ruolo: "operatore" }, "vendita");
  const vendite = ["v-1", "v-2"].map((id, i) => ({
    id, prodotto_nome: `Prodotto ${i + 1}`, pezzi_prodotti: 5, pezzi_invenduto: null, stato: "aperto",
  }));
  axios.get.mockImplementation((url) => Promise.resolve({ data: url.includes("/vendita-banco/oggi") ? vendite : [] }));
  axios.put.mockResolvedValue({ data: { success: true } });
  const node = document.createElement("div");
  document.body.appendChild(node);
  const root = createRoot(node);
  try {
    await act(async () => root.render(<VenditaBancoView onBack={() => {}} />));
    const salva = () => [...node.querySelectorAll("button")].filter((b) => b.textContent.includes("Salva"));
    expect(node.textContent).not.toContain("Verifica PIN serale");
    await act(async () => salva()[0].click());
    expect(axios.put).not.toHaveBeenCalled();
    expect(node.textContent).toContain("Verifica PIN serale");
    await act(async () => [...node.querySelectorAll("button")].find((b) => b.textContent.includes("Verifica PIN serale")).click());
    expect(axios.put).toHaveBeenCalledTimes(1);
    expect(node.textContent).not.toContain("Verifica PIN serale");
    await act(async () => salva()[1].click());
    expect(axios.put).toHaveBeenCalledTimes(2);
    expect(node.textContent).not.toContain("Verifica PIN serale");
  } finally {
    await act(async () => root.unmount());
    node.remove();
    jest.clearAllMocks();
  }
});
