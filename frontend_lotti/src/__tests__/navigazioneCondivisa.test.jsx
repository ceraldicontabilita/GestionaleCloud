import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import PageHeader from "../components/haccp/shared/PageHeader";
import { AltroDropdown } from "../components/haccp/AltroDropdown";

global.IS_REACT_ACT_ENVIRONMENT = true;

test("l'intestazione comune espone titolo e sottotitolo senza annunciare due volte l'icona", async () => {
  const node = document.createElement("div");
  document.body.appendChild(node);
  const root = createRoot(node);
  try {
    await act(async () => root.render(
      <PageHeader titolo="Ricette" sottotitolo="Ricette operative" icona="🍰" />
    ));
    expect(node.querySelector("header h1")?.textContent).toBe("Ricette");
    expect(node.textContent).toContain("Ricette operative");
    expect(node.querySelector('[aria-hidden="true"]')?.textContent).toBe("🍰");
  } finally {
    await act(async () => root.unmount());
    node.remove();
  }
});

test("il menu comune indica pagina corrente e apertura, poi cambia pagina", async () => {
  const node = document.createElement("div");
  document.body.appendChild(node);
  const root = createRoot(node);
  const onTabChange = jest.fn();
  const tabs = [{ id: "ricette", label: "Ricette", icon: () => null }];
  try {
    await act(async () => root.render(
      <AltroDropdown tabs={tabs} activeTab="ricette" onTabChange={onTabChange} />
    ));
    const button = node.querySelector('[data-testid="altro-dropdown-btn"]');
    expect(button.getAttribute("aria-current")).toBe("page");
    expect(button.getAttribute("aria-expanded")).toBe("false");
    await act(async () => button.click());
    expect(button.getAttribute("aria-expanded")).toBe("true");
    const item = node.querySelector('[data-testid="altro-menu-ricette"]');
    expect(item.getAttribute("aria-current")).toBe("page");
    await act(async () => item.click());
    expect(onTabChange).toHaveBeenCalledWith("ricette");
    expect(button.getAttribute("aria-expanded")).toBe("false");
  } finally {
    await act(async () => root.unmount());
    node.remove();
  }
});
