import {
  clearTabletSession,
  getTabletSession,
  moveTabletSessionTo,
  saveTabletSession,
  allineaSessioneTitolare,
  ripristinaSessioneTitolare,
} from "./tabletSession";
import { getToken, saveToken, saveRuolo, logout } from "../auth";
import axios from "axios";

describe("tabletSession", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    clearTabletSession();
    saveToken("token-di-test");
  });
  afterEach(() => jest.restoreAllMocks());

  const titolare = { actor_id: "erp:admin-1", dipendente_id: null, nome: "Titolare", ruolo: "amministratore", via: "sessione_erp" };

  test("il titolare senza scheda HR resta identificato cambiando reparto", () => {
    saveRuolo("amministratore");
    allineaSessioneTitolare(titolare, "home");
    moveTabletSessionTo("magazzino");
    expect(getTabletSession()).toMatchObject({ ...titolare, reparto: "magazzino" });
    moveTabletSessionTo("ordini");
    expect(getTabletSession().reparto).toBe("ordini");
  });

  test("il titolare non eredita identità o limiti del precedente operatore", () => {
    saveTabletSession({ dipendente_id: "hr-1", nome: "Mario", ruolo: "operatore", reparto_pin: "bar", reparti_ammessi: ["bar"] }, "bar");
    saveRuolo("amministratore");
    allineaSessioneTitolare(titolare, "magazzino");
    expect(getTabletSession()).toMatchObject(titolare);
    expect(getTabletSession()).not.toHaveProperty("reparto_pin");
    expect(getTabletSession()).not.toHaveProperty("reparti_ammessi");
  });

  test("un dipendente non usa un'identità ERP senza scheda HR", () => {
    saveRuolo("operatore");
    expect(() => saveTabletSession(titolare, "magazzino")).toThrow();
  });

  test("recupera l'identità del token amministratore esistente dal server", async () => {
    saveRuolo("amministratore");
    jest.spyOn(axios, "get").mockResolvedValue({ data: { user: titolare } });
    await ripristinaSessioneTitolare();
    expect(getTabletSession()).toMatchObject(titolare);
  });

  test("una risposta in ritardo non annulla il logout", async () => {
    saveRuolo("amministratore");
    let rispondi;
    jest.spyOn(axios, "get").mockReturnValue(new Promise(resolve => { rispondi = resolve; }));
    const richiesta = ripristinaSessioneTitolare();
    logout();
    rispondi({ data: { user: titolare } });
    await expect(richiesta).rejects.toThrow("Sessione cambiata");
    expect(getTabletSession()).toBeNull();
    expect(getToken()).toBe("");
  });

  test("mantiene la persona quando cambia reparto", () => {
    saveTabletSession({ dipendente_id: "hr-1", nome: "Operatore Uno", ruolo: "operatore" }, "pasticceria");
    const moved = moveTabletSessionTo("magazzino");
    expect(moved.nome).toBe("Operatore Uno");
    expect(getTabletSession().reparto).toBe("magazzino");
  });

  test("il cambio reparto elimina il vecchio timer del PIN sulle azioni", () => {
    localStorage.setItem("tablet_operatore", JSON.stringify({
      dipendente_id: "hr-1", nome: "Operatore Uno", reparto: "bar", actionVerifiedAt: 1,
    }));
    moveTabletSessionTo("magazzino");
    expect(getTabletSession()).toMatchObject({
      dipendente_id: "hr-1", nome: "Operatore Uno", reparto: "magazzino",
    });
    expect(getTabletSession()).not.toHaveProperty("actionVerifiedAt");
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
