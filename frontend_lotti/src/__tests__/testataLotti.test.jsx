import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";

jest.mock("../components/haccp/SupervisoreBadge", () => ({ SupervisoreBadge: () => null }));
jest.mock("../components/haccp/RicercaGlobale", () => ({ RicercaGlobale: () => null }));
jest.mock("../components/haccp/HACCPPdfButton", () => () => null);
jest.mock("../components/haccp/Breadcrumb", () => () => null);
jest.mock("../components/shared/SelettoreSezioni", () => () => null);

const AppLayout = require("../layouts/AppLayout").default;
const { saveRuolo, saveToken } = require("../auth");

global.IS_REACT_ACT_ENVIRONMENT = true;

describe("testata di Lotti", () => {
  let node;
  let root;

  beforeEach(() => {
    localStorage.clear();
    saveToken("token-di-test");
    node = document.createElement("div");
    document.body.appendChild(node);
    root = createRoot(node);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    node.remove();
  });

  test("il titolare vede per primo «← Gestionale», il logo porta alla Home e l'ingranaggio le Impostazioni", async () => {
    saveRuolo("amministratore");
    const onTabChange = jest.fn();
    await act(async () => root.render(<AppLayout activeTab="lotti" onTabChange={onTabChange}>x</AppLayout>));
    const testata = node.querySelector("header.g-app-header");
    const primo = testata.querySelector("a, button");
    expect(primo.getAttribute("href")).toBe("/");
    expect(primo.textContent).toContain("Gestionale");
    expect(testata.querySelector('[data-testid="indicatore-amministratore"]').textContent).toContain("Amministratore");

    await act(async () => testata.querySelector('[data-testid="logo-home-lotti"]').click());
    expect(onTabChange).toHaveBeenCalledWith("dashboard");

    const ingranaggio = testata.querySelector('[data-testid="impostazioni-dropdown-btn"]');
    await act(async () => ingranaggio.click());
    await act(async () => node.querySelector('[data-testid="impostazioni-menu-backoffice"]').click());
    expect(onTabChange).toHaveBeenCalledWith("backoffice");
  });

  test("il Backoffice non sta più sotto «Altro»", async () => {
    saveRuolo("amministratore");
    await act(async () => root.render(<AppLayout activeTab="lotti" onTabChange={() => {}}>x</AppLayout>));
    await act(async () => node.querySelector('[data-testid="altro-dropdown-btn"]').click());
    expect(node.querySelector('[data-testid="altro-menu-backoffice"]')).toBeNull();
    expect(node.querySelector('[data-testid="altro-menu-guida"]')).not.toBeNull();
  });

  test("il dipendente non vede ingranaggio né indicatore amministratore", async () => {
    saveRuolo("operatore");
    await act(async () => root.render(<AppLayout activeTab="ricette" onTabChange={() => {}}>x</AppLayout>));
    expect(node.querySelector('[data-testid="impostazioni-dropdown-btn"]')).toBeNull();
    expect(node.querySelector('[data-testid="indicatore-amministratore"]')).toBeNull();
    expect(node.querySelector('[data-testid="btn-torna-gestionale"]')).toBeNull();
    expect(node.querySelector("header").textContent).toContain("Reparti");
  });
});
