import React, { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import Colazione from "../components/haccp/ColazioneAcquavivaView";
import Catalogo from "../components/haccp/CatalogoColazione";
import { categorieProdotto } from "../utils/categorieProdotti";

global.IS_REACT_ACT_ENVIRONMENT = true;
jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
describe("Colazione: reparti, fornitori e caricamento", () => {
  let node, root;
  beforeEach(() => { node=document.createElement("div");document.body.appendChild(node);root=createRoot(node);window.location.hash="tablet/pasticceria/colazione"; });
  afterEach(async () => { await act(async () => root.unmount());node.remove();jest.restoreAllMocks(); });
  test("un 401 non diventa zero prodotti o un menu salvabile", async () => {
    jest.spyOn(axios,"get").mockRejectedValue({response:{status:401}});
    await act(async () => root.render(<Colazione />));
    expect(node.textContent).toContain("Dati non disponibili");
    expect(node.textContent).not.toContain("0 prodotti");
    expect(node.querySelector('[role="alert"]')).not.toBeNull();
    expect(node.textContent).not.toContain("Nessun prodotto in questo menù");
  });
  test("le categorie distinguono basi, biscotti, colazione e dolci", () => {
    expect(categorieProdotto({nome:"Bagna alla vaniglia",reparto:"pasticceria"})).toContain("bagne");
    expect(categorieProdotto({nome:"Biscotti Savoiardi"})).toContain("biscotti");
    expect(categorieProdotto({nome:"Crema Pasticcera"})).toContain("creme");
    expect(categorieProdotto({nome:"Babà",reparto:"pasticceria"})).toContain("pasticceria_classica");
    expect(categorieProdotto({nome:"Montanara",reparto:"rosticceria"})).toContain("aperitivo");
  });
  test("i salati sono separati e Acquaviva ha la scelta delle quattro stagioni", async () => {
    const prodotti=[{id:"b",nome:"Babà",fonte:"casa",reparto:"pasticceria"},{id:"m",nome:"Montanara",fonte:"casa",reparto:"rosticceria"},{id:"a",nome:"Cornetto",fonte:"rivendita",fornitore:"acquaviva",gia_acquistato:true}];
    const tutti=jest.fn();
    await act(async () => root.render(<Catalogo prodotti={prodotti} template={{items:[]}} stagione="Autunnale" fotoSrc={()=>""} onToggle={jest.fn()} onTutteStagioni={tutti} />));
    expect(node.textContent).toContain("Babà");expect(node.textContent).not.toContain("Montanara");
    await act(async () => node.querySelector("#col-tab-rosticceria").click());
    expect(node.textContent).toContain("Montanara");expect(node.querySelector('[aria-label="Montanara: tutte le 4 stagioni"]')).toBeNull();
    await act(async () => node.querySelector("#col-tab-acquaviva").click());
    await act(async () => node.querySelector('[aria-label="Cornetto: tutte le 4 stagioni"]').click());
    expect(tutti).toHaveBeenCalledWith(prodotti[2]);
  });
});
