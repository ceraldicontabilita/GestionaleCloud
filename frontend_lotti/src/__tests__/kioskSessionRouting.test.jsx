import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";

jest.mock("../components/haccp/TabletHome", () => {
  const Home = ({ preselectReparto }) => (
    <div data-testid="tablet-home" data-preselect={preselectReparto || ""}>Home</div>
  );
  return { __esModule: true, default: Home, REPARTI_SOLO_ADMIN: ["ordini"] };
});
jest.mock("../components/haccp/TabletView", () => ({
  TabletView: ({ reparto }) => <div data-testid="tablet-view">{reparto}</div>,
}));
jest.mock("../components/haccp/VenditaBancoView", () => ({
  VenditaBancoView: () => <div>Vendita</div>,
}));
jest.mock("../components/haccp/MagazzinoBarView", () => () => <div>Magazzino</div>);
jest.mock("../components/haccp/OrdiniView", () => () => <div>Ordini</div>);

const KioskLayout = require("../layouts/KioskLayout").default;
const AppRouter = require("../router/AppRouter").default;
const {
  clearTabletSession,
  getTabletSession,
  saveTabletSession,
} = require("../utils/tabletSession");
const { saveRuolo, saveToken } = require("../auth");
const axios = require("axios");

global.IS_REACT_ACT_ENVIRONMENT = true;

describe("navigazione kiosk senza richieste PIN inutili", () => {
  let container;
  let root;

  beforeEach(() => {
    jest.spyOn(axios, "get").mockResolvedValue({ data: {} });
    window.location.hash = "";
    localStorage.clear();
    sessionStorage.clear();
    clearTabletSession();
    saveToken("token-di-test");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    jest.restoreAllMocks();
  });

  test("un reparto operativo riutilizza l'operatore già identificato", async () => {
    saveTabletSession({ dipendente_id: "hr-1", nome: "Mario", ruolo: "operatore" }, "bar");

    await act(async () => root.render(<KioskLayout hash="tablet/pasticceria" />));

    expect(container.querySelector('[data-testid="tablet-view"]')?.textContent).toBe("pasticceria");
    expect(getTabletSession()).toMatchObject({ nome: "Mario", reparto: "pasticceria" });
  });

  test("la pagina canonica #ricette usa la sessione dipendente esistente", async () => {
    saveTabletSession({ dipendente_id: "hr-1", nome: "Mario", ruolo: "operatore" }, "pasticceria");
    saveRuolo("operatore");
    window.location.hash = "ricette";
    await act(async () => root.render(<AppRouter AppComponent={() => <div data-testid="ricette-canoniche">Ricette</div>} />));
    expect(container.querySelector('[data-testid="ricette-canoniche"]')).not.toBeNull();
    expect(window.location.hash).toBe("#ricette");
    expect(getTabletSession()).toMatchObject({ dipendente_id: "hr-1" });
  });

  test("una card riservata non cancella la sessione del dipendente", async () => {
    saveTabletSession({ dipendente_id: "hr-1", nome: "Mario", ruolo: "operatore" }, "bar");

    await act(async () => root.render(<KioskLayout hash="tablet/ordini" />));

    expect(container.querySelector('[data-testid="tablet-home"]')?.dataset.preselect).toBe("ordini");
    expect(getTabletSession()).toMatchObject({ dipendente_id: "hr-1", nome: "Mario" });
  });

  test("il titolare entrato dal Gestionale apre la card riservata anche senza operatore", async () => {
    saveRuolo("amministratore");
    axios.get.mockResolvedValue({ data: { user: { actor_id: "erp:1", nome: "Titolare", ruolo: "amministratore", via: "sessione_erp" } } });

    await act(async () => root.render(<KioskLayout hash="tablet/ordini" />));

    expect(container.querySelector('[data-testid="tablet-home"]')).toBeNull();
    expect(container.textContent).toContain("Ordini");
  });

  test("Lotti → Magazzino recupera la sessione amministrativa senza aprire il PIN personale", async () => {
    saveRuolo("amministratore");
    let rispondi;
    axios.get.mockReturnValue(new Promise(resolve => { rispondi = resolve; }));
    await act(async () => root.render(<KioskLayout hash="tablet/magazzino" />));
    expect(container.querySelector('[data-testid="tablet-home"]')).toBeNull();
    expect(container.textContent).toContain("Apertura del reparto");
    await act(async () => rispondi({ data: { user: { actor_id: "erp:1", dipendente_id: null, nome: "Titolare", ruolo: "amministratore", via: "sessione_erp" } } }));
    expect(container.textContent).toContain("Magazzino");
    expect(container.textContent).toContain("Titolare");
    expect(container.querySelector('[data-testid="tablet-home"]')).toBeNull();
    expect(getTabletSession()).toMatchObject({ actor_id: "erp:1", dipendente_id: null });
    await act(async () => root.render(<KioskLayout hash="tablet/home" />));
    await act(async () => root.render(<KioskLayout hash="tablet/magazzino" />));
    expect(axios.get.mock.calls.filter(([url]) => url.endsWith("/auth/me"))).toHaveLength(1);
  });

  test("un errore di rete offre Riprova senza chiedere il PIN dipendente all'amministratore", async () => {
    saveRuolo("amministratore");
    axios.get.mockRejectedValue(new Error("rete"));
    await act(async () => root.render(<KioskLayout hash="tablet/magazzino" />));
    expect(container.querySelector('[data-testid="tablet-home"]')).toBeNull();
    expect(container.textContent).toContain("Riprova");
    axios.get.mockResolvedValue({ data: { user: { actor_id: "erp:1", nome: "Titolare", ruolo: "amministratore", via: "sessione_erp" } } });
    await act(async () => container.querySelector("button").click());
    expect(container.textContent).toContain("Magazzino");
  });

  test("senza sessione Magazzino continua a richiedere l'identificazione personale", async () => {
    await act(async () => root.render(<KioskLayout hash="tablet/magazzino" />));
    expect(container.querySelector('[data-testid="tablet-home"]')?.dataset.preselect).toBe("magazzino");
    expect(axios.get).not.toHaveBeenCalled();
  });
});

