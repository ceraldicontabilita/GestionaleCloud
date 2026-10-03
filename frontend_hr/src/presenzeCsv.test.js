import { describe, expect, it } from "vitest";
import { buildPresenzeCsv } from "./presenzeCsv";

describe("CSV Presenze", () => {
  it("dichiara il separatore e include tutti i giorni del mese", () => {
    const csv = buildPresenzeCsv({
      giorni: 30,
      righe: [{ nome: "Rossi Mario", celle: ["P", "RS"] }],
    });
    const lines = csv.replace(/^\ufeff/, "").trim().split("\r\n");

    expect(lines[0]).toBe("sep=;");
    expect(lines[1].split(";")).toHaveLength(31);
    expect(lines[1]).toMatch(/^Dipendente;1;2;3;/);
    expect(lines[1]).toMatch(/;29;30$/);
    expect(lines[2].split(";")).toHaveLength(31);
  });
});
