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
});

