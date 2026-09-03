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
jest.mock("../components/haccp/tablet/DoseProduzioneView", () => () => <div>Dosi</div>);

const KioskLayout = require("../layouts/KioskLayout").default;
const {
  clearTabletSession,
  getTabletSession,
  saveTabletSession,
} = require("../utils/tabletSession");

global.IS_REACT_ACT_ENVIRONMENT = true;

describe("navigazione kiosk senza richieste PIN inutili", () => {
  let container;
  let root;

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    clearTabletSession();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
  });

  test("un reparto operativo riutilizza l'operatore già identificato", async () => {
    saveTabletSession({ id: "op-1", nome: "Mario", ruolo: "operatore" }, "bar");

    await act(async () => root.render(<KioskLayout hash="tablet/pasticceria" />));

    expect(container.querySelector('[data-testid="tablet-view"]')?.textContent).toBe("pasticceria");
    expect(getTabletSession()).toMatchObject({ nome: "Mario", reparto: "pasticceria" });
  });

  test("una card riservata non cancella la sessione del dipendente", async () => {
    saveTabletSession({ id: "op-1", nome: "Mario", ruolo: "operatore" }, "bar");

    await act(async () => root.render(<KioskLayout hash="tablet/ordini" />));

    expect(container.querySelector('[data-testid="tablet-home"]')?.dataset.preselect).toBe("ordini");
    expect(getTabletSession()).toMatchObject({ id: "op-1", nome: "Mario" });
  });
});

