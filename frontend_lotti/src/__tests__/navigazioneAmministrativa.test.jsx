import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";

jest.mock("axios", () => ({ get: jest.fn(() => Promise.reject(new Error("offline nel test"))) }));
jest.mock("date-fns", () => ({ format: () => "" }));
jest.mock("date-fns/locale", () => ({ it: {} }));
jest.mock("../auth", () => ({ isAdmin: () => true, logout: jest.fn() }));
jest.mock("../components/shared/SelettoreSezioni", () => () => null);
jest.mock("../components/haccp/Breadcrumb", () => () => null);
jest.mock("../components/haccp/HACCPPdfButton", () => () => null);
jest.mock("../components/haccp/HACCPDropdown", () => ({ HACCPDropdown: () => null }));
jest.mock("../components/haccp/AltroDropdown", () => ({ AltroDropdown: () => null }));
jest.mock("../components/haccp/SupervisoreBadge", () => ({ SupervisoreBadge: () => null }));
jest.mock("../components/haccp/RicercaGlobale", () => ({ RicercaGlobale: () => null }));
jest.mock("../components/haccp/StatoSistemaWidget", () => () => null);
jest.mock("../components/haccp/HACCPHomeCard", () => () => null);
jest.mock("../components/haccp/PesceTraceabilityCard", () => () => null);

const DashboardView = require("../components/haccp/DashboardView").default;
const AppLayout = require("../layouts/AppLayout").default;
const guidaContenuti = require("../data/guidaContenuti.json");
const axios = require("axios");

global.IS_REACT_ACT_ENVIRONMENT = true;

describe("navigazione amministrativa sempre comprensibile", () => {
  let container;
  let root;

  beforeEach(() => {
    axios.get.mockRejectedValue(new Error("offline nel test"));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
  });

  test("Impostazioni e Controllo dati non sono nascosti nel pannello chiuso", async () => {
    await act(async () => {
      root.render(<DashboardView stats={{}} onNavigate={jest.fn()} />);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(Array.from(container.querySelectorAll("button")).some((b) => b.textContent.includes("Impostazioni"))).toBe(true);
    expect(Array.from(container.querySelectorAll("button")).some((b) => b.textContent.includes("Controllo dati"))).toBe(true);
  });

  test("ogni pagina dell'app espone il ritorno al Gestionale", async () => {
    await act(async () => root.render(
      <AppLayout activeTab="dashboard" onTabChange={jest.fn()} ordiniPendenti={0}>
        <div>contenuto</div>
      </AppLayout>
    ));

    const link = container.querySelector('[data-testid="btn-torna-gestionale"]');
    expect(link).not.toBeNull();
    expect(link.getAttribute("href")).toBe("/");
    expect(link.getAttribute("aria-label")).toBe("Torna al Gestionale");
  });

  test("la guida non descrive piu una scadenza autonoma di due ore", () => {
    const testo = JSON.stringify(guidaContenuti).toLowerCase();
    expect(testo).not.toMatch(/cancello delle 2 ore|sessione.{0,30}(?:2|due) ore/);
  });
});
