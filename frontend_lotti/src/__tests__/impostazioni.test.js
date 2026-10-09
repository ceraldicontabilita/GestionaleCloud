import { SEZIONI_IMPOSTAZIONI } from "../components/haccp/ImpostazioniView";
import { VALID_TABS } from "../config/navigation";
import { ADMIN_TABS } from "../config/permissions";

describe("pagina Impostazioni", () => {
  test("ha le nove sezioni del piano", () => {
    expect(SEZIONI_IMPOSTAZIONI.map((s) => s.id)).toEqual([
      "azienda", "operatori", "ruoli", "reparti", "frigoriferi", "stampanti", "cataloghi", "sicurezza", "backup",
    ]);
  });

  test("ogni sezione porta a una pagina che esiste", () => {
    SEZIONI_IMPOSTAZIONI.forEach((s) => {
      expect(VALID_TABS).toContain(s.vai);
      (s.altri || []).forEach((a) => expect(VALID_TABS).toContain(a.vai));
    });
  });

  test("è una pagina riservata all'amministratore", () => {
    expect(VALID_TABS).toContain("impostazioni");
    expect(ADMIN_TABS).toContain("impostazioni");
  });
});
