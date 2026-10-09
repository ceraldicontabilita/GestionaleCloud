import { sogliaGiorni } from "../components/haccp/MerceFermaView";
import { PAGE_NAMES } from "../config/pageMeta";
import { tabRiservataAdmin } from "../config/permissions";

test("la soglia della merce ferma e' una data ISO nel passato", () => {
  expect(sogliaGiorni(60, new Date(2026, 8, 27))).toBe("2026-07-29");
  expect(sogliaGiorni(30, new Date(2026, 0, 15))).toBe("2025-12-16");
});

test("la pagina e' nel menu ed e' riservata al titolare", () => {
  expect(PAGE_NAMES.merce_ferma).toBe("Merce ferma e dosi");
  expect(tabRiservataAdmin("merce_ferma")).toBe(true);
});
