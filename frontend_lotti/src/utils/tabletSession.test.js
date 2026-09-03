import {
  actionAuthorizationStillValid,
  clearTabletSession,
  getTabletSession,
  markTabletActionAuthorized,
  moveTabletSessionTo,
  saveTabletSession,
  TABLET_ACTION_AUTH_MS,
} from "./tabletSession";

describe("tabletSession", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    clearTabletSession();
  });

  test("mantiene la persona quando cambia reparto", () => {
    saveTabletSession({ id: "op-1", nome: "Operatore Uno", ruolo: "operatore" }, "pasticceria");
    const moved = moveTabletSessionTo("magazzino");
    expect(moved.nome).toBe("Operatore Uno");
    expect(getTabletSession().reparto).toBe("magazzino");
  });

  test("la conferma delle azioni vale dieci minuti senza chiudere la sessione", () => {
    markTabletActionAuthorized({ id: "op-1", nome: "Operatore Uno", ruolo: "operatore" }, "magazzino");
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
    saveTabletSession({ id: "op-1", nome: "Operatore Uno", ruolo: "operatore" }, "pasticceria");
    sessionStorage.clear();

    expect(getTabletSession()).toMatchObject({
      id: "op-1",
      nome: "Operatore Uno",
      reparto: "pasticceria",
    });
  });

  test("migra una sessione legacy senza richiedere un altro PIN", () => {
    const now = Date.now();
    sessionStorage.setItem("tablet_operatore", JSON.stringify({
      id: "op-legacy",
      nome: "Operatore Legacy",
      reparto: "bar",
      startedAt: now,
      expiresAt: now + 60_000,
    }));

    expect(getTabletSession()?.nome).toBe("Operatore Legacy");
    expect(localStorage.getItem("tablet_operatore")).toContain("Operatore Legacy");
    expect(sessionStorage.getItem("tablet_operatore")).toBeNull();
  });

  test("l'uscita esplicita cancella memoria nuova e legacy", () => {
    saveTabletSession({ id: "op-1", nome: "Operatore Uno", ruolo: "operatore" }, "pasticceria");
    sessionStorage.setItem("tablet_operatore", JSON.stringify({ id: "vecchio", nome: "Vecchio" }));
    clearTabletSession();

    expect(getTabletSession()).toBeNull();
    expect(localStorage.getItem("tablet_operatore")).toBeNull();
    expect(sessionStorage.getItem("tablet_operatore")).toBeNull();
  });
});
