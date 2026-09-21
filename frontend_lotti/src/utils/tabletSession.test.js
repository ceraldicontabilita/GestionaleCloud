import {
  actionAuthorizationStillValid,
  clearTabletSession,
  getTabletSession,
  markTabletActionAuthorized,
  moveTabletSessionTo,
  saveTabletSession,
  TABLET_ACTION_AUTH_MS,
} from "./tabletSession";
import { getToken, saveToken } from "../auth";

describe("tabletSession", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    clearTabletSession();
    saveToken("token-di-test");
  });

  test("mantiene la persona quando cambia reparto", () => {
    saveTabletSession({ dipendente_id: "hr-1", nome: "Operatore Uno", ruolo: "operatore" }, "pasticceria");
    const moved = moveTabletSessionTo("magazzino");
    expect(moved.nome).toBe("Operatore Uno");
    expect(getTabletSession().reparto).toBe("magazzino");
  });

  test("la conferma delle azioni vale dieci minuti senza chiudere la sessione", () => {
    markTabletActionAuthorized({ dipendente_id: "hr-1", nome: "Operatore Uno", ruolo: "operatore" }, "magazzino");
    expect(actionAuthorizationStillValid()).toBe(true);

    const stored = getTabletSession();
    localStorage.setItem("tablet_operatore", JSON.stringify({
      ...stored,
      actionVerifiedAt: Date.now() - TABLET_ACTION_AUTH_MS - 1,
    }));
    expect(actionAuthorizationStillValid()).toBe(false);
    expect(getTabletSession().nome).toBe("Operatore Uno");
  });

  test("la sessione operatore sopravvive al cambio di scheda", () => {
    saveTabletSession({ dipendente_id: "hr-1", nome: "Operatore Uno", ruolo: "operatore" }, "pasticceria");
    sessionStorage.clear();

    expect(getTabletSession()).toMatchObject({
      dipendente_id: "hr-1",
      nome: "Operatore Uno",
      reparto: "pasticceria",
    });
  });

  test("una sessione con ID della proiezione richiede un nuovo login", () => {
    const now = Date.now();
    saveToken("token-legacy");
    sessionStorage.setItem("tablet_operatore", JSON.stringify({
      id: "op-legacy",
      nome: "Operatore Legacy",
      reparto: "bar",
      startedAt: now,
      expiresAt: now + 60_000,
    }));

    expect(getTabletSession()).toBeNull();
    expect(localStorage.getItem("tablet_operatore")).toBeNull();
    expect(sessionStorage.getItem("tablet_operatore")).toBeNull();
    expect(getToken()).toBe("");
  });

  test("non richiede di nuovo il PIN dopo due ore se il token è ancora presente", () => {
    saveTabletSession({ dipendente_id: "hr-1", nome: "Operatore Uno", ruolo: "operatore" }, "pasticceria");
    const stored = getTabletSession();
    localStorage.setItem("tablet_operatore", JSON.stringify({ ...stored, expiresAt: Date.now() - 1 }));
    expect(getTabletSession()).toMatchObject({ dipendente_id: "hr-1", nome: "Operatore Uno" });
  });

  test("senza token la sessione tablet non apre i reparti", () => {
    saveTabletSession({ dipendente_id: "hr-1", nome: "Operatore Uno", ruolo: "operatore" }, "pasticceria");
    localStorage.removeItem("lotti_token");
    expect(getTabletSession()).toBeNull();
  });

  test("la vecchia sessione persistita cancella anche il token", () => {
    saveToken("token-legacy");
    localStorage.setItem("tablet_operatore", JSON.stringify({
      id: "op-legacy", nome: "Operatore Legacy", expiresAt: Date.now() + 60_000,
    }));

    expect(getTabletSession()).toBeNull();
    expect(getToken()).toBe("");
  });

  test("non salva una nuova sessione senza ID dipendente", () => {
    expect(() => saveTabletSession({ id: "op-1", nome: "Operatore" }, "bar"))
      .toThrow("ID dipendente obbligatorio");
    expect(localStorage.getItem("tablet_operatore")).toBeNull();
  });

  test("l'uscita esplicita cancella memoria nuova e legacy", () => {
    saveTabletSession({ dipendente_id: "hr-1", nome: "Operatore Uno", ruolo: "operatore" }, "pasticceria");
    sessionStorage.setItem("tablet_operatore", JSON.stringify({ id: "vecchio", nome: "Vecchio" }));
    clearTabletSession();

    expect(getTabletSession()).toBeNull();
    expect(localStorage.getItem("tablet_operatore")).toBeNull();
    expect(sessionStorage.getItem("tablet_operatore")).toBeNull();
  });
});
