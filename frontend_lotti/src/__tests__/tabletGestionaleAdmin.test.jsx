import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import TabletHome from "../components/haccp/TabletHome";
import * as authLotti from "../auth";
import { saveToken, saveRuolo } from "../auth";
import { getTabletSession, saveTabletSession } from "../utils/tabletSession";

global.IS_REACT_ACT_ENVIRONMENT = true;

// Sessione unica (25/09/2026): l'amministratore non ha piu' un secondo
// tastierino. Col Gestionale aperto entra con un tocco; altrimenti va al
// login del Gestionale e torna qui.
describe("uscita dal tablet verso il gestionale", () => {
  let node;
  let root;
  let login;

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    window.location.hash = "tablet/home";
    saveToken("token-di-test");
    node = document.createElement("div");
    document.body.appendChild(node);
    root = createRoot(node);
    login = jest.spyOn(authLotti, "vaiAlLoginGestionale").mockImplementation(() => {});
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    node.remove();
    jest.restoreAllMocks();
  });

  const clicca = async () => {
    const button = [...node.querySelectorAll("button")].find((b) => b.textContent.includes("Gestionale"));
    await act(async () => button.click());
  };

  test("con la sessione del Gestionale si entra con un tocco", async () => {
    jest.spyOn(authLotti, "entraDalGestionale").mockResolvedValue(true);
    jest.spyOn(axios, "get").mockResolvedValue({ data: { richieste: [] } });
    await act(async () => root.render(<TabletHome />));
    await clicca();
    expect(window.location.hash).toBe("#dashboard");
    expect(login).not.toHaveBeenCalled();
    expect(node.textContent).not.toContain("PIN Amministratore");
  });

  test("la sessione admin del tablet verificata dal server apre il gestionale", async () => {
    jest.spyOn(authLotti, "entraDalGestionale").mockResolvedValue(false);
    saveTabletSession({ dipendente_id: "hr-admin", nome: "Amministratore", ruolo: "amministratore" }, "pasticceria");
    const get = jest.spyOn(axios, "get").mockImplementation((url) => Promise.resolve({
      data: url.endsWith("/auth/me")
        ? { user: { dipendente_id: "hr-admin", ruolo: "amministratore" } }
        : { richieste: [] },
    }));
    await act(async () => root.render(<TabletHome />));
    await clicca();
    expect(get).toHaveBeenCalledWith(expect.stringContaining("/auth/me"));
    expect(window.location.hash).toBe("#dashboard");
    expect(getTabletSession()).toMatchObject({ dipendente_id: "hr-admin", ruolo: "amministratore" });
  });

  test("un dipendente viene mandato al login del Gestionale, niente tastierino", async () => {
    jest.spyOn(authLotti, "entraDalGestionale").mockResolvedValue(false);
    saveTabletSession({ dipendente_id: "hr-dipendente", nome: "Dipendente", ruolo: "operatore" }, "pasticceria");
    saveRuolo("operatore");
    const get = jest.spyOn(axios, "get").mockResolvedValue({ data: { richieste: [] } });
    await act(async () => root.render(<TabletHome />));
    await clicca();
    expect(window.location.hash).toBe("#tablet/home");
    expect(login).toHaveBeenCalledWith("/lotti/#dashboard");
    expect(node.textContent).not.toContain("PIN Amministratore");
    expect(get).not.toHaveBeenCalledWith(expect.stringContaining("/auth/me"));
  });

  test("un token di altro dipendente non apre il gestionale", async () => {
    jest.spyOn(authLotti, "entraDalGestionale").mockResolvedValue(false);
    saveTabletSession({ dipendente_id: "hr-admin", nome: "Amministratore", ruolo: "amministratore" }, "pasticceria");
    jest.spyOn(axios, "get").mockImplementation((url) => Promise.resolve({
      data: url.endsWith("/auth/me")
        ? { user: { dipendente_id: "altro", ruolo: "operatore" } }
        : { richieste: [] },
    }));
    await act(async () => root.render(<TabletHome />));
    await clicca();
    expect(window.location.hash).toBe("#tablet/home");
    expect(login).toHaveBeenCalledWith("/lotti/#dashboard");
  });
});
