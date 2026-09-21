import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import CosaUsareOggiView from "../components/haccp/CosaUsareOggiView";

global.IS_REACT_ACT_ENVIRONMENT = true;

test("un lotto scaduto non propone Usa oggi o l'invio al banco", async () => {
  const lotti = {
    lotti: [{ id: "valido", prodotto: "Arancino", numero_lotto: "A-1", quantita: 2,
      stato_scadenza: { colore: "arancione", label: "Scade oggi", giorni_alla_scadenza: 0 } }],
    scaduti: [{ id: "scaduto", prodotto: "Babà", numero_lotto: "B-1", quantita: 1,
      stato_scadenza: { colore: "rosso", label: "Scaduto da 1gg", giorni_alla_scadenza: -1 } }],
    da_verificare: [],
  };
  jest.spyOn(axios, "get").mockImplementation((url) => Promise.resolve({
    data: url.includes("/cosa-usare-oggi") ? lotti : { frigoriferi: [], congelatori: [] },
  }));
  const node = document.createElement("div");
  document.body.appendChild(node);
  const root = createRoot(node);
  try {
    await act(async () => root.render(<CosaUsareOggiView />));
    const scaduti = node.querySelector('[aria-label="Lotti scaduti"]');
    expect(scaduti).toBeTruthy();
    expect(scaduti.textContent).toContain("Scaduti: non utilizzare");
    expect(scaduti.textContent).toContain("Smaltisci");
    expect(scaduti.textContent).not.toContain("Usa oggi");
    expect(scaduti.textContent).not.toContain("Manda al banco");
    expect([...node.querySelectorAll("button")].filter((b) => b.textContent.includes("Usa oggi"))).toHaveLength(1);
  } finally {
    await act(async () => root.unmount());
    node.remove();
    jest.restoreAllMocks();
  }
});
