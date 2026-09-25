import { ricordaPaginaRichiesta, prendiPaginaRichiesta } from "../auth";

// Un link diretto a una pagina riservata, aperto prima del PIN
// amministratore, deve portare li' dopo il PIN e non sulla dashboard.
describe("pagina chiesta prima del PIN amministratore", () => {
  beforeEach(() => sessionStorage.clear());

  test("il link viene ripreso una volta sola dopo il PIN", () => {
    window.location.hash = "attendibilita_haccp";
    ricordaPaginaRichiesta();
    expect(prendiPaginaRichiesta()).toBe("attendibilita_haccp");
    expect(prendiPaginaRichiesta()).toBe("dashboard");
  });

  test("le pagine del tablet non si ricordano", () => {
    window.location.hash = "tablet/home";
    ricordaPaginaRichiesta();
    expect(prendiPaginaRichiesta()).toBe("dashboard");
  });
});
