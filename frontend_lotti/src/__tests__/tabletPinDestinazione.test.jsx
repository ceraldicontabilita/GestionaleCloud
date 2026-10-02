import React, { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import AppRouter from "../router/AppRouter";
import { getTabletSession } from "../utils/tabletSession";

jest.mock("../components/haccp/TabletView", () => ({
  TabletView: ({ reparto }) => <div data-testid="reparto-aperto">{reparto}</div>,
}));
jest.mock("../components/haccp/VenditaBancoView", () => ({ VenditaBancoView: () => null }));
jest.mock("../components/haccp/MagazzinoBarView", () => () => null);
jest.mock("../components/haccp/OrdiniView", () => () => null);

global.IS_REACT_ACT_ENVIRONMENT = true;

describe("destinazione dopo il PIN personale (risposte API simulate)", () => {
  let container;
  let root;

  beforeEach(() => {
    jest.useFakeTimers();
    localStorage.clear();
    sessionStorage.clear();
    jest.spyOn(axios, "get").mockResolvedValue({ data: {} });
    jest.spyOn(axios, "post").mockResolvedValue({ data: {
      token: "token-di-test",
      operatore: { dipendente_id: "hr-test", nome: "Operatore di test", ruolo: "operatore" },
    } });
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    jest.restoreAllMocks();
    jest.useRealTimers();
  });

  async function apri(hash) {
    window.location.hash = hash;
    await act(async () => root.render(<AppRouter AppComponent={() => <div>Ricette canoniche</div>} />));
  }

  async function premi(testo) {
    const button = [...container.querySelectorAll("button")].find(b => b.textContent.trim() === testo);
    expect(button).toBeDefined();
    await act(async () => button.click());
  }

  async function confermaPinDiTest() {
    for (const cifra of ["1", "2", "3", "4"]) await premi(cifra);
    await premi("Conferma");
    await act(async () => jest.advanceTimersByTime(200));
  }

  test.each([
    "tablet/pasticceria/colazione",
    "tablet/pasticceria/colazione/configura",
    "tablet/pasticceria/produci",
    "tablet/rosticceria/produci",
    "tablet/pasticceria",
  ])("il login conserva #%s e identifica l'operatore", async hash => {
    await apri(hash);
    expect(container.textContent).toContain("Inserisci il tuo PIN personale");
    await confermaPinDiTest();
    expect(window.location.hash).toBe(`#${hash}`);
    expect(container.querySelector('[data-testid="reparto-aperto"]')?.textContent).toBe(hash.split("/")[1]);
    expect(getTabletSession()).toMatchObject({ dipendente_id: "hr-test", reparto: hash.split("/")[1] });
    expect(container.textContent).not.toContain("Inserisci il tuo PIN personale");
  });

  test("scegliere un altro reparto non porta con sé la sottopagina Colazione", async () => {
    await apri("tablet/pasticceria/colazione");
    await premi("Annulla");
    const rosticceria = [...container.querySelectorAll("button")].find(b => b.textContent.includes("Rosticceria"));
    await act(async () => rosticceria.click());
    await confermaPinDiTest();
    expect(window.location.hash).toBe("#tablet/rosticceria");
    expect(getTabletSession()?.reparto).toBe("rosticceria");
  });

  test("la card Ricette continua ad aprire l'unica pagina canonica", async () => {
    await apri("tablet/home");
    const ricette = [...container.querySelectorAll("button")].find(b => b.textContent.includes("Ricette"));
    await act(async () => ricette.click());
    await confermaPinDiTest();
    expect(window.location.hash).toBe("#ricette");
    expect(container.textContent).toContain("Ricette canoniche");
  });

  test("un PIN rifiutato non apre la sezione e non crea un'identità", async () => {
    axios.post.mockRejectedValue({ response: { status: 401, data: { detail: "PIN non riconosciuto" } } });
    await apri("tablet/pasticceria/colazione");
    await confermaPinDiTest();
    expect(window.location.hash).toBe("#tablet/pasticceria/colazione");
    expect(getTabletSession()).toBeNull();
    expect(container.textContent).toContain("PIN non riconosciuto");
    expect(container.querySelector('[data-testid="reparto-aperto"]')).toBeNull();
  });
});
