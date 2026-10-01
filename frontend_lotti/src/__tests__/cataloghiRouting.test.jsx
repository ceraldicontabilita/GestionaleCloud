import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";

jest.mock("axios", () => ({
  get: jest.fn(() => Promise.reject(new Error("offline nel test"))),
}));
jest.mock("date-fns", () => ({ format: () => "" }));
jest.mock("date-fns/locale", () => ({ it: {} }));
jest.mock("../components/haccp/ProdottiVenditaView", () => () => (
  <div data-testid="vista-cataloghi">Cataloghi fornitori</div>
));
jest.mock("../components/haccp/GestioneProdottiView", () => () => (
  <div data-testid="vista-magazzino-prodotti">Magazzino prodotti</div>
));
jest.mock("../components/haccp/ListinoView", () => () => (
  <div data-testid="vista-listino">Listino</div>
));
jest.mock("../components/haccp/ScontiMerceView", () => () => (
  <div data-testid="vista-sconti">Sconti merce</div>
));
jest.mock("../auth", () => ({ isAdmin: () => false }));
jest.mock("../components/haccp/StatoSistemaWidget", () => () => null);
jest.mock("../components/haccp/HACCPHomeCard", () => () => null);
jest.mock("../components/haccp/PesceTraceabilityCard", () => () => null);

const ProdottiConTabFornitore = require("../components/haccp/ProdottiHubView").default;
const DashboardView = require("../components/haccp/DashboardView").default;
const axios = require("axios");

global.IS_REACT_ACT_ENVIRONMENT = true;

describe("navigazione reale dei cataloghi fornitori", () => {
  let container;
  let root;

  beforeEach(() => {
    axios.get.mockRejectedValue(new Error("offline nel test"));
    window.history.replaceState(null, "", "#");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
  });

  test.each(["acquaviva", "saima", "mepa"])(
    "#prodotti/%s monta davvero la vista cataloghi",
    async (fornitore) => {
      window.history.replaceState(null, "", `#prodotti/${fornitore}`);
      await act(async () => root.render(<ProdottiConTabFornitore />));

      expect(container.querySelector('[data-testid="vista-cataloghi"]')).not.toBeNull();
      expect(container.querySelector('[data-testid="vista-listino"]')).toBeNull();
      expect(container.querySelector('[data-testid="prodotti-sub-cataloghi"]').getAttribute("aria-selected")).toBe("true");
    }
  );

  test("Indietro/Avanti sincronizza cataloghi e Listino", async () => {
    window.history.replaceState(null, "", "#prodotti/saima");
    await act(async () => root.render(<ProdottiConTabFornitore />));
    expect(container.querySelector('[data-testid="vista-cataloghi"]')).not.toBeNull();

    await act(async () => {
      window.history.replaceState(null, "", "#prodotti");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(container.querySelector('[data-testid="vista-listino"]')).not.toBeNull();

    await act(async () => {
      window.history.replaceState(null, "", "#prodotti/mepa");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(container.querySelector('[data-testid="vista-cataloghi"]')).not.toBeNull();
  });

  test("la Home raccoglie i cataloghi nell'area ufficio", async () => {
    await act(async () => {
      root.render(<DashboardView stats={{}} onNavigate={jest.fn()} />);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(container.textContent).not.toContain("Cataloghi fornitori");
    const ufficio = Array.from(container.querySelectorAll("button"))
      .find((button) => button.textContent.includes("Ufficio e archivio"));
    expect(ufficio).toBeTruthy();
    await act(async () => ufficio.click());
    expect(container.textContent).toContain("Listini e cataloghi");
    expect(container.textContent).not.toContain("Acquaviva");
    expect(container.textContent).not.toContain("SAIMA");
    expect(container.textContent).not.toContain("MEPA");
  });
});
