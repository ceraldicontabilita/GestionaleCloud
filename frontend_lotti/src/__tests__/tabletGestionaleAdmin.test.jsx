import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import TabletHome from "../components/haccp/TabletHome";
import { saveToken, saveRuolo } from "../auth";
import { getTabletSession, saveTabletSession } from "../utils/tabletSession";

global.IS_REACT_ACT_ENVIRONMENT = true;

describe("uscita dal tablet verso il gestionale", () => {
  let node;
  let root;

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    window.location.hash = "tablet/home";
    saveToken("token-di-test");
    node = document.createElement("div");
    document.body.appendChild(node);
    root = createRoot(node);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    node.remove();
    jest.restoreAllMocks();
  });

  test("la sessione admin verificata dal server apre il gestionale senza tastierino", async () => {
    saveTabletSession({ dipendente_id: "hr-admin", nome: "Amministratore", ruolo: "amministratore" }, "pasticceria");
    const get = jest.spyOn(axios, "get").mockImplementation((url) => Promise.resolve({
      data: url.endsWith("/auth/me")
        ? { user: { dipendente_id: "hr-admin", ruolo: "amministratore" } }
        : { richieste: [] },
    }));
    await act(async () => root.render(<TabletHome />));
    const button = [...node.querySelectorAll("button")].find((b) => b.textContent.includes("Gestionale"));
    await act(async () => button.click());
    expect(get).toHaveBeenCalledWith(expect.stringContaining("/auth/me"));
    expect(window.location.hash).toBe("#dashboard");
    expect(getTabletSession()).toMatchObject({ dipendente_id: "hr-admin", ruolo: "amministratore" });
    expect(node.textContent).not.toContain("PIN Amministratore");
  });

  test("la sessione dipendente non apre il gestionale e richiede l'amministratore", async () => {
    saveTabletSession({ dipendente_id: "hr-dipendente", nome: "Dipendente", ruolo: "operatore" }, "pasticceria");
    saveRuolo("operatore");
    const get = jest.spyOn(axios, "get");
    await act(async () => root.render(<TabletHome />));
    const button = [...node.querySelectorAll("button")].find((b) => b.textContent.includes("Gestionale"));
    await act(async () => button.click());
    expect(window.location.hash).toBe("#tablet/home");
    expect(node.textContent).toContain("PIN Amministratore");
    expect(get).not.toHaveBeenCalledWith(expect.stringContaining("/auth/me"));
  });

  test("un token di altro dipendente non apre il gestionale", async () => {
    saveTabletSession({ dipendente_id: "hr-admin", nome: "Amministratore", ruolo: "amministratore" }, "pasticceria");
    jest.spyOn(axios, "get").mockImplementation((url) => Promise.resolve({
      data: url.endsWith("/auth/me")
        ? { user: { dipendente_id: "altro", ruolo: "operatore" } }
        : { richieste: [] },
    }));
    await act(async () => root.render(<TabletHome />));
    const button = [...node.querySelectorAll("button")].find((b) => b.textContent.includes("Gestionale"));
    await act(async () => button.click());
    expect(window.location.hash).toBe("#tablet/home");
    expect(node.textContent).toContain("PIN Amministratore");
  });
});
