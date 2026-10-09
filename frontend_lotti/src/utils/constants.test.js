import { BACKEND_URL, fotoSrc } from "./constants";

describe("fotoSrc", () => {
  test("indirizza al backend le foto persistenti dell'applicazione", () => {
    expect(fotoSrc("/api/foto/ricetta_123?v=1")).toBe(
      `${BACKEND_URL}/api/foto/ricetta_123?v=1`
    );
  });

  test("mantiene sul frontend gli asset statici SAIMA", () => {
    expect(fotoSrc("/saima/ricette/ciambelline.webp")).toBe(
      "/saima/ricette/ciambelline.webp"
    );
  });

  test("non modifica gli URL esterni", () => {
    expect(fotoSrc("https://example.com/foto.webp")).toBe(
      "https://example.com/foto.webp"
    );
  });

  test("normalizza un asset statico senza slash iniziale", () => {
    expect(fotoSrc("saima/ricette/ciambelline.webp")).toBe(
      "/saima/ricette/ciambelline.webp"
    );
  });

  test("dentro GestionaleCloud aggiunge il prefisso /lotti agli asset statici", () => {
    // Regressione [FIX 05/09/2026]: con PUBLIC_URL=/lotti (com'è in produzione
    // dentro GestionaleCloud) le foto SAIMA vanno cercate sotto /lotti, non
    // alla radice del sito — altrimenti il browser prende un 404.
    jest.resetModules();
    process.env.PUBLIC_URL = "/lotti";
    const { fotoSrc: fotoSrcConPrefisso } = require("./constants");
    expect(fotoSrcConPrefisso("/saima/ricette/ciambelline.webp")).toBe(
      "/lotti/saima/ricette/ciambelline.webp"
    );
    delete process.env.PUBLIC_URL;
    jest.resetModules();
  });
});
