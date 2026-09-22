import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import { conferma } from "../utils/conferma";
import RicetteCestino from "../components/haccp/backoffice/RicetteCestino";

jest.mock("../utils/conferma", () => ({ conferma: jest.fn(() => Promise.resolve(true)) }));
global.IS_REACT_ACT_ENVIRONMENT = true;

test("l'amministratore recupera una ricetta dal cestino e la rivede fra le operative", async () => {
  conferma.mockResolvedValue(true);
  const get = jest.spyOn(axios, "get").mockImplementation((url) => {
    if (url.includes("/ricette-cestino")) return Promise.resolve({ data: [{ id: "voce-1", ricetta_id: "ric-1", nome: "Babà", motivo: "eliminazione manuale" }] });
    return Promise.resolve({ data: [] });
  });
  const post = jest.spyOn(axios, "post").mockResolvedValue({ data: { id: "ric-1", ripristinata: true } });
  const onRipristinata = jest.fn();
  const node = document.createElement("div");
  document.body.appendChild(node);
  const root = createRoot(node);
  try {
    await act(async () => root.render(<RicetteCestino onRipristinata={onRipristinata} />));
    expect(node.textContent).toContain("Babà");
    await act(async () => [...node.querySelectorAll("button")].find(button => button.textContent === "Ripristina").click());
    expect(conferma).toHaveBeenCalled();
    expect(await conferma.mock.results[0].value).toBe(true);
    expect(post).toHaveBeenCalledWith(expect.stringContaining("/ricette-cestino/voce-1/ripristina"));
    expect(onRipristinata).toHaveBeenCalledTimes(1);
    expect(node.textContent).toContain("Cestino vuoto");
    expect(get).toHaveBeenCalledWith(expect.stringContaining("/ricette-cestino"));
  } finally {
    await act(async () => root.unmount());
    node.remove();
    jest.restoreAllMocks();
  }
});
