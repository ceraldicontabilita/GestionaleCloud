import React, { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import BackofficeView from "../components/haccp/BackofficeView";
import GruppiProduzioneRicette, { categorieConGruppo } from "../components/haccp/GruppiProduzioneRicette";

jest.mock("../components/haccp/backoffice/toastBackoffice", () => ({ toast: jest.fn() }));
global.IS_REACT_ACT_ENVIRONMENT = true;

describe("gruppi di produzione dalla card ricetta", () => {
  let node, root, ricette;
  beforeEach(() => {
    node = document.createElement("div"); document.body.appendChild(node); root = createRoot(node);
    ricette = [{id:"r1",nome:"Montanara",reparto:"rosticceria",categorie_rapide:["colazioni","natale"],ingredienti:["Farina"]},
      {id:"r2",nome:"Babà",reparto:"pasticceria",categorie_rapide:["pasticceria_classica"]}];
    jest.spyOn(axios,"get").mockImplementation(url => Promise.resolve({data: url.includes("ricette-unificate") ? ricette : {}}));
    jest.spyOn(axios,"put").mockImplementation((url, data) => {
      const r = ricette.find(r => url.includes(`/${r.id}/`));
      r.categorie_rapide = data.categorie;
      return Promise.resolve({data:{id:r.id,categorie_rapide:data.categorie}});
    });
  });
  afterEach(async () => { await act(async () => root.unmount()); node.remove(); jest.restoreAllMocks(); });
  const render = () => act(async () => root.render(<BackofficeView initialTab="ricette" solo />));

  test("la spunta rosticceria sostituisce Colazione e sopravvive alla rilettura", async () => {
    await render();
    const gruppo = node.querySelector('[aria-label="Categorie rapide Montanara"]');
    const etichetta = [...gruppo.querySelectorAll("label")].find(l => l.textContent.includes("Rosticceria del giorno"));
    await act(async () => etichetta.querySelector("input").click());
    expect(axios.put).toHaveBeenCalledWith(expect.stringContaining("/ricette/r1/categorie-rapide"), {categorie:["natale","rosticceria_giorno"]});
    expect(gruppo.textContent).toContain("Pasticceria classica");
    expect([...gruppo.querySelectorAll("label")].find(l => l.textContent.includes("Colazione")).querySelector("input").checked).toBe(false);
    await act(async () => root.render(<BackofficeView key="ricaricata" initialTab="ricette" solo />));
    const schedaGruppo = [...node.querySelectorAll('[aria-label="Gruppi di produzione"] button')].find(b => b.textContent.includes("Rosticceria"));
    expect(schedaGruppo.textContent).toContain("1 ricette selezionate");
    await act(async () => schedaGruppo.click());
    expect(node.textContent).toContain("Montanara");
    expect(node.querySelector('[aria-label="Categorie rapide Babà"]')).toBeNull();
    expect(ricette[0].ingredienti).toEqual(["Farina"]);
  });
  test("errore API non fa apparire la spunta salvata", async () => {
    axios.put.mockRejectedValue(new Error("rete"));
    await render();
    const input = [...node.querySelectorAll('[aria-label="Categorie rapide Montanara"] label')].find(l => l.textContent.includes("Rosticceria del giorno")).querySelector("input");
    await act(async () => input.click());
    expect(input.checked).toBe(false);
    expect(ricette[0].categorie_rapide).toContain("colazioni");
  });
  test("Pasticceria classica filtra babà e torna a tutte con un secondo tocco", async () => {
    await render();
    const b = [...node.querySelectorAll('[aria-label="Gruppi di produzione"] button')].find(b => b.textContent.includes("Pasticceria classica"));
    await act(async () => b.click());
    expect(node.querySelector('[aria-label="Categorie rapide Montanara"]')).toBeNull();
    expect(node.querySelector('[aria-label="Categorie rapide Babà"]')).not.toBeNull();
    await act(async () => b.click());
    expect(node.querySelector('[aria-label="Categorie rapide Montanara"]')).not.toBeNull();
  });
  test("l'operatore consulta i gruppi ma non vede spunte di modifica", async () => {
    await act(async () => root.render(<BackofficeView initialTab="ricette" solo solaLetturaOperatore />));
    expect(node.querySelector('[aria-label="Gruppi di produzione"]')).not.toBeNull();
    expect(node.querySelector('[aria-label="Categorie rapide Babà"]')).toBeNull();
    expect(axios.put).not.toHaveBeenCalled();
  });
  test("in Produci ogni reparto mostra solo il proprio gruppo", async () => {
    await act(async () => root.render(<GruppiProduzioneRicette reparto="rosticceria" ricette={ricette} selezionato="tutte" onScegli={jest.fn()} />));
    expect(node.querySelectorAll("button")).toHaveLength(1);
    expect(node.textContent).toContain("Rosticceria");
    expect(node.textContent).not.toContain("Pasticceria classica");
  });
  test("i gruppi escludono solo le scelte incompatibili e sono reversibili", () => {
    expect(categorieConGruppo(["pasqua","pasticceria_classica","colazioni"],"rosticceria_giorno",true)).toEqual(["pasqua","rosticceria_giorno"]);
    expect(categorieConGruppo(["rosticceria_giorno","pasqua"],"pasticceria_classica",true)).toEqual(["pasqua","pasticceria_classica"]);
    expect(categorieConGruppo(["rosticceria_giorno","pasqua"],"colazioni",true)).toEqual(["pasqua","colazioni"]);
    expect(categorieConGruppo(["pasticceria_classica","pasqua"],"pasticceria_classica",false)).toEqual(["pasqua"]);
  });
});
