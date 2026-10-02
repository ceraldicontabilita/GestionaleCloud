import { rasterizza, costruisciXml, spiegaErrore, getModoStampa, setModoStampa, MODI, ErroreStampaDiretta } from "../utils/stampaEpson";

describe("stampa diretta Epson", () => {
  test("rasterizza: nero = 1, bit 7 e' il primo pixel", () => {
    const px = (v) => [v, v, v, 255];
    // riga di 10 pixel: nero, bianco, nero, bianco x7
    const data = new Uint8ClampedArray([...px(0), ...px(255), ...px(0), ...Array(7).fill(px(255)).flat()]);
    const out = rasterizza(data, 10, 1);
    expect(out.length).toBe(2);
    expect(out[0]).toBe(0b10100000);
    expect(out[1]).toBe(0);
  });

  test("XML con immagine, avanzamento e taglio", () => {
    const xml = costruisciXml({ bytes: new Uint8Array([255, 0]), width: 8, height: 2 });
    expect(xml).toContain('<image width="8" height="2" color="color_1" mode="mono">/wA=</image>');
    expect(xml).toContain('<cut type="feed"/>');
  });

  test("XML di prova: solo testo e taglio, niente caratteri XML", () => {
    const xml = costruisciXml({ testo: "a<b>&" });
    expect(xml).toContain("<text>ab");
    expect(xml).not.toContain("<image");
  });

  test("errori spiegati in italiano", () => {
    expect(spiegaErrore(new TypeError("Failed to fetch"), "10.0.0.5")).toMatch(/certificato.*rete locale/s);
    expect(spiegaErrore(Object.assign(new Error("x"), { name: "AbortError" }), "10.0.0.5")).toMatch(/non risponde/);
    expect(spiegaErrore(new ErroreStampaDiretta("Carta finita"))).toBe("Carta finita");
  });

  test("modalita' per dispositivo, compatibile col vecchio stampa_auto", () => {
    localStorage.clear();
    expect(getModoStampa()).toBe(MODI.FINESTRA);
    localStorage.setItem("stampa_auto", "1");
    expect(getModoStampa()).toBe(MODI.AGENTE);
    setModoStampa(MODI.EPSON);
    expect(getModoStampa()).toBe(MODI.EPSON);
    expect(localStorage.getItem("stampa_auto")).toBe("0");
  });
});
