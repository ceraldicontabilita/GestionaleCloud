import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
jest.mock("@/auth", () => ({
  saveToken: jest.fn(), saveRuolo: jest.fn(), setAdminGateOk: jest.fn(),
  adminGateStillValid: () => false, setGateOk: jest.fn(),
}), { virtual: true });
import TabletHome from "../components/haccp/TabletHome";
import { clearTabletSession, saveTabletSession } from "../utils/tabletSession";
import { saveToken } from "../auth";

global.IS_REACT_ACT_ENVIRONMENT = true;

test("la card Ricette apre #ricette senza pagina Dosi e senza nuovo PIN", async () => {
  localStorage.clear();
  clearTabletSession();
  window.location.hash = "tablet/home";
  saveToken("token-di-test");
  saveTabletSession({ dipendente_id: "hr-1", nome: "Mario", ruolo: "operatore" }, "pasticceria");
  const node = document.createElement("div");
  document.body.appendChild(node);
  const root = createRoot(node);
  try {
    await act(async () => root.render(<TabletHome />));
    const ricette = [...node.querySelectorAll("button")].find((button) => button.textContent === "📖Ricette");
    expect(ricette).toBeTruthy();
    await act(async () => ricette.click());
    expect(window.location.hash).toBe("#ricette");
    expect(node.textContent).not.toContain("Inserisci il tuo PIN personale");
  } finally {
    await act(async () => root.unmount());
    node.remove();
  }
});
