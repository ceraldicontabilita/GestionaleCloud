import { prodottiRichiedibili } from "../components/haccp/tablet/ModalRichiediMerce";

test("OLVA compare una volta e la lavagna usa solo prodotti del magazzino bar", () => {
  const prodotti = [
    {id:"lotto-1", nome:"OLVA THERMO QUICK", source:"fornitore"},
    {id:"bar-1", nome:"OLVA THERMO QUICK", source:"bar"},
    {id:"lotto-2", nome:"OLVA THERMO QUICK", source:"fornitore"},
    {id:"lotto-3", nome:"Farina speciale", source:"fornitore"},
  ];
  expect(prodottiRichiedibili(prodotti, "lavagna").map(p => p.id)).toEqual(["bar-1"]);
  expect(prodottiRichiedibili(prodotti, "carrello").map(p => p.id)).toEqual(["bar-1", "lotto-3"]);
});
