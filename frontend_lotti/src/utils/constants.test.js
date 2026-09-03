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
});
