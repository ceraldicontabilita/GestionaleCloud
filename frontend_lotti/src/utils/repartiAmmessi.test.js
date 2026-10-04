import { describe, expect, it } from "vitest";
import { repartiAmmessi } from "./tabletSession";

describe("repartiAmmessi", () => {
  it("il titolare e chi non ha una mansione riconosciuta non hanno restrizioni", () => {
    expect(repartiAmmessi({ ruolo: "amministratore", reparti_ammessi: ["bar"] })).toBeNull();
    expect(repartiAmmessi({ ruolo: "operatore", reparti_ammessi: [] })).toBeNull();
    expect(repartiAmmessi(null)).toBeNull();
  });

  it("l'operatore vede le card della sua mansione", () => {
    const s = { ruolo: "operatore", reparti_ammessi: ["magazzino", "ordini"], reparto_pin: "magazzino" };
    expect(repartiAmmessi(s)).toEqual(["magazzino", "ordini"]);
  });

  it("un PIN dato su un altro reparto apre solo quello", () => {
    const s = { ruolo: "operatore", reparti_ammessi: ["pasticceria"], reparto_pin: "rosticceria" };
    expect(repartiAmmessi(s)).toEqual(["rosticceria"]);
  });

  it("il responsabile HACCP conserva la card dei registri", () => {
    const s = { ruolo: "operatore", reparti_ammessi: ["pasticceria"], reparto_pin: "pasticceria", profilo: { permessi: ["haccp_registri"] } };
    expect(repartiAmmessi(s)).toEqual(["pasticceria", "haccp"]);
  });
});
