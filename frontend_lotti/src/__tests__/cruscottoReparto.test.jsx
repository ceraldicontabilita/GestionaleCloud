import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import DashboardReparto from "../components/haccp/tablet/DashboardReparto";

global.IS_REACT_ACT_ENVIRONMENT = true;

// Il cruscotto mostra solo dati letti dal backend; una lettura fallita e'
// «non disponibile», mai uno zero che sembrerebbe un reparto in regola.
const RISPOSTE = {
  "/produzioni/per-oggi": [
    { ricetta: "Babà", reparto: "pasticceria", pezzi: 12, operatore_nome: "Mario" },
    { ricetta: "Arancino", reparto: "rosticceria", pezzi: 30 },
  ],
  "/supervisor/lotti-in-scadenza": { lotti: [{ prodotto: "Crema", data_scadenza: "25/09/2026", giorni_alla_scadenza: -1 }], totale: 1 },
  "/haccp-auto/turno-oggi": { da_rilevare: [{ tipo: "frigo", numero: 2, nome: "Frigorifero N°2", operatore_nome: "Mario" }], quante_da_rilevare: 1 },
  "/magazzino-bar/richieste": { richieste: [{ prodotto_nome: "Farina", quantita: 1, unita_movimento: "collo" }], totale: 1 },
  "/anomalie/lista?stato=Aperta": [{ attrezzatura: "Forno", tipo: "Guasto", priorita: "Alta" }],
  "/anomalie/lista?stato=In%20corso": [],
};

function rispondi(url, guasti = []) {
  const chiave = Object.keys(RISPOSTE).find((k) => url.includes(k));
  if (url.includes("/sanificazione/scadute") || guasti.some((g) => url.includes(g))) {
    return Promise.reject(new Error("rete"));
  }
  return Promise.resolve({ data: RISPOSTE[chiave] });
}

describe("cruscotto del reparto", () => {
  let node;
  let root;

  beforeEach(() => {
    localStorage.clear();
    node = document.createElement("div");
    document.body.appendChild(node);
    root = createRoot(node);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    node.remove();
    jest.restoreAllMocks();
  });

  const monta = async (props = {}) => {
    await act(async () => root.render(
      <DashboardReparto reparto="pasticceria" label="Pasticceria" colore="#c2410c"
        operatore={{ nome: "Mario" }} onProduci={() => {}} onRicette={() => {}}
        onRichiediMerce={() => {}} onCambiaOperatore={() => {}} onReparti={() => {}} {...props} />,
    ));
  };
  const blocco = (id) => node.querySelector(`[data-testid="${id}"]`).textContent;

  test("mostra operatore, produzioni del reparto e stati delle anomalie", async () => {
    jest.spyOn(axios, "get").mockImplementation((url) => rispondi(url));
    await monta();
    expect(node.querySelector('[data-testid="operatore-attivo"]').textContent).toBe("Mario");
    // Solo le produzioni di Pasticceria.
    expect(blocco("blocco-produzioni")).toContain("Babà");
    expect(blocco("blocco-produzioni")).not.toContain("Arancino");
    expect(blocco("blocco-produzioni")).toContain("12 pezzi");
    expect(blocco("blocco-anomalie")).toContain("1 priorità alta");
    expect(blocco("blocco-scadenze")).toContain("1 già scaduti");
    expect(blocco("blocco-temperature")).toContain("Frigorifero N°2");
    expect(blocco("blocco-richieste")).toContain("Farina");
  });

  test("una lettura fallita è «non disponibile», non zero", async () => {
    jest.spyOn(axios, "get").mockImplementation((url) => rispondi(url));
    await monta();
    expect(blocco("blocco-sanificazioni")).toContain("Non disponibile");
    expect(blocco("blocco-sanificazioni")).not.toMatch(/\b0\b/);
  });

  test("azioni grandi del reparto, Colazione e Senza glutine solo se previste", async () => {
    jest.spyOn(axios, "get").mockImplementation((url) => rispondi(url));
    const produci = jest.fn();
    await monta({ onProduci: produci });
    expect(node.querySelector('[data-testid="azione-colazione"]')).toBeNull();
    await act(async () => node.querySelector('[data-testid="azione-produci"]').click());
    expect(produci).toHaveBeenCalled();
    await act(async () => node.querySelector('[data-testid="azione-haccp"]').click());
    expect(node.querySelector('[data-testid="pannello-haccp"]').textContent).toContain("Frigorifero N°2");
  });
});
