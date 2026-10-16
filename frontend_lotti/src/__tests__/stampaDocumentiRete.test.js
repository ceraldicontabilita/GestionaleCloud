jest.mock("axios", () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock("../auth", () => ({ apriDocumentoAutenticato: jest.fn() }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

const axios = require("axios");
const { apriDocumentoAutenticato } = require("../auth");
const { stampaDoc } = require("../utils/stampa");

describe("instradamento documenti alla stampante di rete", () => {
  beforeEach(() => {
    localStorage.clear();
    jest.clearAllMocks();
    localStorage.setItem("stampa_modo", "epson");
  });

  test("la scheda ricetta va alla categoria ricette e non alla stampante etichette", async () => {
    axios.post.mockResolvedValue({ data: {
      instradato: true,
      stampante: { nome: "Stampante documenti di rete", categorie: ["ricette"] },
    } });

    const esito = await stampaDoc({
      categoria: "ricette",
      url: "/lotti/api/ricette/r1/pdf-scheda",
      formato: "html",
      titolo: "Scheda Girella con Scarole",
    });

    expect(axios.post).toHaveBeenCalledWith(expect.stringContaining("/stampanti/coda"), expect.objectContaining({
      categoria: "ricette",
      formato: "html",
    }));
    expect(esito).toMatchObject({ accodato: true, stampante: { nome: "Stampante documenti di rete" } });
    expect(apriDocumentoAutenticato).not.toHaveBeenCalled();
  });

  test("senza una stampante documenti configurata apre la scheda e non usa le etichette", async () => {
    axios.post.mockResolvedValue({ data: { instradato: false, stampante: null } });
    await stampaDoc({ categoria: "ricette", url: "/lotti/api/ricette/r1/pdf-scheda", formato: "html" });
    expect(apriDocumentoAutenticato).toHaveBeenCalledWith("/lotti/api/ricette/r1/pdf-scheda");
  });

  test("se la coda di rete non risponde apre comunque la scheda stampabile", async () => {
    axios.post.mockRejectedValue(new Error("rete non disponibile"));
    const esito = await stampaDoc({ categoria: "ricette", url: "/lotti/api/ricette/r1/pdf-scheda" });
    expect(esito).toMatchObject({ accodato: false, instradato: false });
    expect(apriDocumentoAutenticato).toHaveBeenCalledWith("/lotti/api/ricette/r1/pdf-scheda");
  });
});
