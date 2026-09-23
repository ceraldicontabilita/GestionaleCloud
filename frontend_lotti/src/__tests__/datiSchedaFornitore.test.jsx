import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { DatiScheda } from "../components/haccp/SchedeTecnicheView";

global.IS_REACT_ACT_ENVIRONMENT = true;

function monta(s) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  act(() => root.render(<DatiScheda s={s} />));
  return { el, chiudi: () => { act(() => root.unmount()); el.remove(); } };
}

test("mostra allergeni per nome, tracce e valori per 100 g scritti nella scheda", () => {
  const { el, chiudi } = monta({
    allergeni_stato: "letti", allergeni: ["latte", "frutta_guscio"], allergeni_tracce: ["soia"],
    valori_nutrizionali_100g: { energia_kcal: "394", grassi_g: "12.5", fibre_g: null },
  });
  expect(el.textContent).toContain("latte, frutta a guscio");
  expect(el.textContent).toContain("tracce di soia");
  expect(el.textContent).toContain("Energia 394 kcal · Grassi 12.5 g");
  expect(el.textContent).not.toContain("Fibre");
  chiudi();
});

test("scheda illeggibile: da verificare, nessun valore inventato", () => {
  const { el, chiudi } = monta({ allergeni_stato: "da_verificare", allergeni: [], valori_nutrizionali_100g: {} });
  expect(el.textContent).toContain("da verificare sul PDF");
  expect(el.textContent).toContain("Valori nutrizionali da verificare sul PDF");
  expect(el.textContent).not.toContain("nessuno dichiarato");
  chiudi();
});

test("il link al PDF del fornitore porta il token, un link esterno no", async () => {
  const axios = (await import("axios")).default;
  localStorage.setItem("lotti_token", "tok123");
  const get = jest.spyOn(axios, "get").mockImplementation((url) => Promise.resolve({ data:
    url.includes("/prodotti") ? { prodotti: [{ prodotto_key: "k", nome: "WHITE CREAM", fornitore: "ME.PA.", ha_scheda: true,
      schede: [{ tipo: "tecnica", fonte: "email_fornitore", url: "/lotti/api/schede-tecniche/pdf/d1", allergeni_stato: "letti", allergeni: ["latte"] },
               { tipo: "sicurezza", fonte: "produttore.it", url: "https://produttore.it/s.pdf" }] }] }
    : {} }));
  const SchedeTecnicheView = (await import("../components/haccp/SchedeTecnicheView")).default;
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  await act(async () => { root.render(<SchedeTecnicheView />); });
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  const hrefs = [...el.querySelectorAll("a")].map((a) => a.getAttribute("href"));
  expect(hrefs).toContain("/lotti/api/schede-tecniche/pdf/d1?token=tok123");
  expect(hrefs).toContain("https://produttore.it/s.pdf");
  expect(el.textContent).toContain("PDF del fornitore");
  expect(el.querySelectorAll('[aria-label="Elimina scheda"]').length).toBe(1);
  act(() => root.unmount());
  el.remove();
  get.mockRestore();
  localStorage.removeItem("lotti_token");
});
