import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import fs from "fs";
import path from "path";
import axios from "axios";
import TabletHome from "../components/haccp/TabletHome";
import * as authLotti from "../auth";
import { saveRuolo, saveToken } from "../auth";
import { getTabletSession, saveTabletSession } from "../utils/tabletSession";

global.IS_REACT_ACT_ENVIRONMENT = true;

// Il PIN amministratore si digita solo nel login del Gestionale (26/09/2026):
// dentro Lotti non c'e' nessun tastierino da titolare. Il PIN personale resta
// per le card di reparto: identifica chi firma HACCP e produzioni.

const SRC = path.join(__dirname, "..");

function sorgenti(dir = SRC, out = []) {
  for (const voce of fs.readdirSync(dir, { withFileTypes: true })) {
    const pieno = path.join(dir, voce.name);
    if (voce.isDirectory()) {
      if (voce.name !== "__tests__") sorgenti(pieno, out);
    } else if (/\.(jsx?|json)$/.test(voce.name) && !/\.test\.jsx?$/.test(voce.name)) {
      out.push(pieno);
    }
  }
  return out;
}

describe("nessun tastierino amministratore dentro Lotti", () => {
  const file = sorgenti();

  test("nessun tastierino filtra il ruolo amministratore", () => {
    const colpevoli = file.filter((f) => {
      const testo = fs.readFileSync(f, "utf8");
      const tastierini = testo.match(/<PinKeypad[\s\S]*?\/>/g) || [];
      return /onlyAdmin/.test(testo) || tastierini.some((t) => /soloAdmin|amministratore/.test(t));
    });
    expect(colpevoli.map((f) => path.relative(SRC, f))).toEqual([]);
    // Il tastierino condiviso non conosce piu' un ruolo da pretendere.
    const condiviso = fs.readFileSync(path.join(SRC, "components/haccp/shared/PinKeypad.jsx"), "utf8");
    expect(condiviso).not.toMatch(/soloAdmin|amministratore/);
  });

  test("nessun testo chiede ancora il PIN amministratore o Google", () => {
    const frasi = /PIN o Google|\(o Google\)|PIN da amministratore|col PIN amministratore|serve il PIN amministratore|GoogleLoginButton|auth\/google/;
    const colpevoli = file.filter((f) => frasi.test(fs.readFileSync(f, "utf8")));
    expect(colpevoli.map((f) => path.relative(SRC, f))).toEqual([]);
  });
});

describe("card riservate al titolare e cambio reparto", () => {
  let node;
  let root;
  let login;

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    window.location.hash = "tablet/home";
    saveToken("token-di-test");
    node = document.createElement("div");
    document.body.appendChild(node);
    root = createRoot(node);
    login = jest.spyOn(authLotti, "vaiAlLoginGestionale").mockImplementation(() => {});
    jest.spyOn(axios, "get").mockResolvedValue({ data: { richieste: [] } });
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    node.remove();
    jest.restoreAllMocks();
  });

  const card = (nome) => [...node.querySelectorAll("button")].find((b) => b.textContent.includes(nome));
  const tastierino = () => node.textContent.includes("Inserisci il tuo PIN personale");

  test("con la sessione del Gestionale la card Ordini si apre subito", async () => {
    const entra = jest.spyOn(authLotti, "entraDalGestionale").mockResolvedValue({
      nome: "Titolare", ruolo: "amministratore", dipendente_id: "hr-titolare",
    });
    await act(async () => root.render(<TabletHome />));
    await act(async () => card("Ordini").click());
    expect(entra).toHaveBeenCalled();
    expect(window.location.hash).toBe("#tablet/ordini");
    expect(login).not.toHaveBeenCalled();
    expect(tastierino()).toBe(false);
    expect(getTabletSession()).toMatchObject({ dipendente_id: "hr-titolare", ruolo: "amministratore", reparto: "ordini" });
  });

  test("senza sessione del Gestionale la card Ordini rimanda al suo login, niente tastierino", async () => {
    jest.spyOn(authLotti, "entraDalGestionale").mockResolvedValue(false);
    await act(async () => root.render(<TabletHome />));
    await act(async () => card("Ordini").click());
    expect(login).toHaveBeenCalledWith("/lotti/#tablet/ordini");
    expect(window.location.hash).toBe("#tablet/home");
    expect(tastierino()).toBe(false);
  });

  test("il titolare entrato dal Gestionale non eredita l'identità del dipendente", async () => {
    saveTabletSession({ dipendente_id: "hr-mario", nome: "Mario", ruolo: "operatore" }, "pasticceria");
    jest.spyOn(authLotti, "entraDalGestionale").mockResolvedValue({ nome: "Titolare", ruolo: "amministratore", dipendente_id: null });
    await act(async () => root.render(<TabletHome />));
    await act(async () => card("Ordini").click());
    expect(window.location.hash).toBe("#tablet/ordini");
    expect(getTabletSession()).toBeNull();
  });

  test("tornando dal login senza sessione non si rimanda di nuovo al login", async () => {
    window.location.hash = "tablet/ordini";
    jest.spyOn(authLotti, "entraDalGestionale").mockResolvedValue(false);
    await act(async () => root.render(<TabletHome preselectReparto="ordini" />));
    expect(login).not.toHaveBeenCalled();
    expect(tastierino()).toBe(false);
    expect(node.textContent).toContain("riservata al titolare");
  });

  test("da Pasticceria a Rosticceria con lo stesso operatore non si chiede il PIN", async () => {
    saveTabletSession({ dipendente_id: "hr-mario", nome: "Mario", ruolo: "operatore" }, "pasticceria");
    saveRuolo("operatore");
    const entra = jest.spyOn(authLotti, "entraDalGestionale");
    await act(async () => root.render(<TabletHome />));
    await act(async () => card("Rosticceria").click());
    expect(window.location.hash).toBe("#tablet/rosticceria");
    expect(tastierino()).toBe(false);
    expect(entra).not.toHaveBeenCalled();
    expect(getTabletSession()).toMatchObject({ dipendente_id: "hr-mario", reparto: "rosticceria" });
  });

  test("senza operatore la card di reparto chiede il PIN personale", async () => {
    await act(async () => root.render(<TabletHome />));
    await act(async () => card("Pasticceria").click());
    expect(tastierino()).toBe(true);
  });
});
