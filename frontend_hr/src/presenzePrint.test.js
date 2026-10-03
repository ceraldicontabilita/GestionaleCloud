import { describe, expect, it } from "vitest";
import { buildPresenzePrintHtml } from "./presenzePrint";

describe("stampa Presenze", () => {
  it("mantiene tutte le celle del mese e tutti i codici", () => {
    const celle = Array.from({ length: 31 }, (_, i) => i === 0 ? "P" : i === 15 ? "M" : i === 30 ? "RS" : "");
    const html = buildPresenzePrintHtml({
      anno: 2026,
      meseLabel: "Ottobre",
      giorni: 31,
      righe: [{ nome: "Dipendente Test", celle }],
    });

    expect((html.match(/<th>/g) || []).length).toBe(31);
    expect((html.match(/<td style=/g) || []).length).toBe(31);
    expect(html).toContain(">P</td>");
    expect(html).toContain(">M</td>");
    expect(html).toContain(">RS</td>");
  });
});

