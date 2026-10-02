jest.mock("axios", () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
jest.mock("../auth", () => ({ apriDocumentoAutenticato: jest.fn() }));

const { bytesToBase64, urlRawbt } = require("../utils/stampa");

describe("stampa diretta RawBT", () => {
  it("codifica i byte ESC/POS in base64", () => {
    expect(bytesToBase64(new Uint8Array([0x1b, 0x40, 0x41]).buffer)).toBe("G0BB");
  });
  it("costruisce l'intent verso l'app RawBT", () => {
    expect(urlRawbt(new Uint8Array([0x1b, 0x40, 0x41]).buffer)).toBe(
      "intent:base64,G0BB#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
    );
  });
});
