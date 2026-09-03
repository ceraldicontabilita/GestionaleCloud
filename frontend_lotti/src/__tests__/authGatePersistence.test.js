jest.mock("@/utils/constants", () => ({ API: "http://localhost/api" }), { virtual: true });

const {
  adminGateStillValid,
  clearAdminGate,
  setAdminGateOk,
} = require("../auth");

describe("persistenza temporanea del PIN amministratore", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    clearAdminGate();
  });

  test("resta valido cambiando scheda del browser", () => {
    setAdminGateOk();
    sessionStorage.clear();

    expect(adminGateStillValid()).toBe(true);
  });

  test("una scadenza passata viene rimossa", () => {
    localStorage.setItem("tablet_admin_until", String(Date.now() - 1));

    expect(adminGateStillValid()).toBe(false);
    expect(localStorage.getItem("tablet_admin_until")).toBeNull();
  });
});
