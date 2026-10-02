import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import TurnoHaccpOggi from "../components/haccp/shared/TurnoHaccpOggi";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
const permessi = { lista: ["haccp_registri", "haccp_conformita"] };
jest.mock("../utils/permessiRuolo", () => ({
  puo: (p) => permessi.lista.includes(p),
}));

const TURNO = {
  data: "2026-10-02", quante_da_rilevare: 3, gia_rilevate: 1,
  senza_casella: [], quante_senza_casella: 0, controllo_visivo_attivo: true,
  da_rilevare: [],
};

describe("turno HACCP di oggi: dichiarazione e apertura delle caselle", () => {
  let node;
  let root;

  beforeEach(() => {
    permessi.lista = ["haccp_registri", "haccp_conformita"];
    node = document.createElement("div");
    document.body.appendChild(node);
    root = createRoot(node);
    window.confirm = jest.fn(() => true);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    node.remove();
    jest.restoreAllMocks();
  });

  const monta = async (turno = TURNO, props = {}) => {
    jest.spyOn(axios, "get").mockResolvedValue({ data: turno });
    await act(async () => root.render(<TurnoHaccpOggi {...props} />));
  };
  const bottone = (testo) => Array.from(node.querySelectorAll("button")).find((b) => b.textContent.includes(testo));

  test("dice quante caselle aperte verranno dichiarate, chiede conferma e mostra l'esito", async () => {
    const post = jest.spyOn(axios, "post").mockResolvedValue({ data: { success: true, dichiarate: 3, firmate: 1, firmato_da: "Ceraldi Vincenzo" } });
    const onAggiornato = jest.fn();
    await monta(TURNO, { onAggiornato });

    expect(node.querySelector('[data-testid="turno-haccp-riepilogo"]').textContent).toContain("3 caselle aperte da dichiarare");
    const dichiara = bottone("Dichiaro conformi i controlli di oggi");
    expect(dichiara).toBeTruthy();
    expect(dichiara.disabled).toBe(false);
    expect(bottone("Apri le caselle di oggi")).toBeUndefined();

    await act(async () => dichiara.click());

    expect(window.confirm).toHaveBeenCalledTimes(1);
    expect(window.confirm.mock.calls[0][0]).toContain("3 caselle aperte");
    expect(post).toHaveBeenCalledTimes(1);
    expect(post.mock.calls[0][0]).toMatch(/\/haccp-auto\/dichiara-conformi-oggi$/);
    expect(node.textContent).toContain("Confermate 3 caselle aperte e firmati 1 controllo registrato, da Ceraldi Vincenzo");
    expect(onAggiornato).toHaveBeenCalled();
  });

  test("con zero caselle aperte firma le temperature già rilevate", async () => {
    const post = jest.spyOn(axios, "post").mockResolvedValue({
      data: { success: true, dichiarate: 0, firmate: 14, firmato_da: "Ceraldi Vincenzo" },
    });
    await monta({ ...TURNO, quante_da_rilevare: 0, gia_rilevate: 14, da_firmare: 14 });

    const dichiara = bottone("Dichiaro conformi i controlli di oggi");
    expect(dichiara.disabled).toBe(false);
    expect(node.textContent).toContain("14 controlli da firmare");
    await act(async () => dichiara.click());

    expect(post).toHaveBeenCalledTimes(1);
    expect(window.confirm.mock.calls[0][0]).toContain("14 controlli già registrati");
    expect(node.textContent).toContain("firmati 14 controlli registrati");
  });

  test("senza conferma non chiama il backend", async () => {
    window.confirm = jest.fn(() => false);
    const post = jest.spyOn(axios, "post");
    await monta();
    await act(async () => bottone("Dichiaro conformi i controlli di oggi").click());
    expect(post).not.toHaveBeenCalled();
  });

  test("il 409 del controllo visivo spento arriva con le parole del backend", async () => {
    const { toast } = require("sonner");
    jest.spyOn(axios, "post").mockRejectedValue({ response: { status: 409, data: { detail: "Il controllo visivo del responsabile non e' attivo nelle Impostazioni." } } });
    await monta();
    await act(async () => bottone("Dichiaro conformi i controlli di oggi").click());
    expect(toast.error).toHaveBeenCalledWith("Il controllo visivo del responsabile non e' attivo nelle Impostazioni.");
  });

  test("con il controllo visivo spento il bottone non compare e la pagina lo dice", async () => {
    await monta({ ...TURNO, controllo_visivo_attivo: false });
    expect(bottone("Dichiaro conformi i controlli di oggi")).toBeUndefined();
    expect(node.textContent).toContain("non è attivo nelle Impostazioni");
  });

  test("un apparecchio senza casella fa comparire «Apri le caselle di oggi»", async () => {
    const post = jest.spyOn(axios, "post").mockResolvedValue({ data: { success: true, aperte: 1 } });
    await monta({ ...TURNO, quante_da_rilevare: 0, senza_casella: ["Cella nuova"], quante_senza_casella: 1 });

    expect(node.textContent).toContain("1 apparecchio senza casella: Cella nuova");
    expect(bottone("Dichiaro conformi i controlli di oggi").disabled).toBe(true);
    await act(async () => bottone("Apri le caselle di oggi").click());
    expect(post.mock.calls[0][0]).toMatch(/\/haccp-auto\/apri-rilevazioni-oggi$/);
    expect(node.textContent).toContain("Aperte 1 casella di oggi");
  });

  test("senza permessi non compare niente", async () => {
    permessi.lista = [];
    await monta();
    expect(node.querySelector('[data-testid="turno-haccp-oggi"]')).toBeNull();
  });

  test("niente emoji nel testo", async () => {
    await monta({ ...TURNO, senza_casella: ["Cella nuova"], quante_senza_casella: 1 });
    expect(node.textContent).not.toMatch(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u);
  });
});
