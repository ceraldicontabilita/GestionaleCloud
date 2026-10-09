// Il JWT non va mai in un URL: i documenti protetti (PDF, report, registri)
// si scaricano con l'header Authorization e si aprono come blob.
import fs from "fs";
import path from "path";
import axios from "axios";
import { apriDocumentoAutenticato, setupAxiosAuth } from "../auth";

jest.mock("sonner", () => ({ toast: { error: jest.fn(), info: jest.fn(), success: jest.fn() } }));

const SRC = path.join(__dirname, "..");

function sorgenti(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((d) => {
    const p = path.join(dir, d.name);
    if (d.isDirectory()) return d.name === "__tests__" ? [] : sorgenti(p);
    return /\.(js|jsx|ts|tsx)$/.test(d.name) ? [p] : [];
  });
}

const senzaCommenti = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

test("nessun sorgente mette il token in un URL", () => {
  const colpevoli = sorgenti(SRC).filter((f) => {
    const codice = senzaCommenti(fs.readFileSync(f, "utf8"));
    return /[?&]token=|withToken|access_token=/.test(codice);
  });
  expect(colpevoli.map((f) => path.relative(SRC, f))).toEqual([]);
});

describe("apriDocumentoAutenticato", () => {
  let finestra;
  let adapterOriginale;
  let richieste;

  beforeAll(() => setupAxiosAuth());

  beforeEach(() => {
    richieste = [];
    localStorage.setItem("lotti_token", "tok-segreto");
    finestra = { closed: false, opener: {}, document: { title: "", body: {} }, location: { href: "" }, close: jest.fn() };
    jest.spyOn(window, "open").mockImplementation(() => finestra);
    URL.createObjectURL = jest.fn(() => "blob:documento");
    URL.revokeObjectURL = jest.fn();
    adapterOriginale = axios.defaults.adapter;
  });

  afterEach(() => {
    axios.defaults.adapter = adapterOriginale;
    jest.restoreAllMocks();
    jest.useRealTimers();
    localStorage.removeItem("lotti_token");
  });

  const rispondi = (status, tipo = "application/pdf", corpo = "%PDF-1.4") => {
    axios.defaults.adapter = (config) => {
      richieste.push(config);
      const risposta = { data: new Blob([corpo], { type: tipo }), status, statusText: "", headers: { "content-type": tipo }, config };
      if (status >= 400) {
        const err = new Error(`HTTP ${status}`);
        err.response = risposta;
        return Promise.reject(err);
      }
      return Promise.resolve(risposta);
    };
  };

  test("apre la scheda subito, poi il blob; il token viaggia solo nell'header", async () => {
    jest.useFakeTimers();
    rispondi(200);
    const promessa = apriDocumentoAutenticato("/lotti/api/report-haccp/mensile?mese=9&anno=2026");
    // la finestra e' aperta in modo sincrono, dentro il gesto del clic
    expect(window.open).toHaveBeenCalledWith("", "_blank", undefined);
    expect(finestra.opener).toBeNull();
    await expect(promessa).resolves.toBe(true);
    expect(richieste).toHaveLength(1);
    expect(richieste[0].url).not.toMatch(/token/);
    expect(String(richieste[0].headers.Authorization)).toBe("Bearer tok-segreto");
    expect(richieste[0].responseType).toBe("blob");
    expect(finestra.location.href).toBe("blob:documento");
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
    jest.advanceTimersByTime(60000);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:documento");
  });

  test("popup bloccato: il documento si scarica invece di perdersi", async () => {
    window.open.mockImplementation(() => null);
    rispondi(200);
    const click = jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    await expect(apriDocumentoAutenticato("/lotti/api/disinfestazione/export-pdf/2026")).resolves.toBe(true);
    expect(click).toHaveBeenCalledTimes(1);
  });

  test("scarica: nessuna finestra, download con il nome indicato", async () => {
    rispondi(200, "application/zip", "PK");
    let nome = null;
    jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function () { nome = this.download; });
    await apriDocumentoAutenticato("/lotti/api/acquaviva/export-foto-zip", { scarica: true, nomeFile: "foto.zip" });
    expect(window.open).not.toHaveBeenCalled();
    expect(nome).toBe("foto.zip");
  });

  test("errore del server: la scheda vuota si chiude e l'esito e' false", async () => {
    rispondi(404, "application/json", "{}");
    await expect(apriDocumentoAutenticato("/lotti/api/fatture/x/visualizza")).resolves.toBe(false);
    expect(finestra.close).toHaveBeenCalled();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
});
