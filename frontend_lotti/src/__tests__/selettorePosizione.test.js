const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const SelettorePosizione = require("../components/haccp/tablet/registraLotto/SelettorePosizione").default;

const frigo = Array.from({ length: 12 }, (_, i) => `Frigorifero N°${i + 1}`);
const congelatori = Array.from({ length: 12 }, (_, i) => `Congelatore N°${i + 1}`);

const mostra = (extra = {}) => renderToStaticMarkup(React.createElement(SelettorePosizione, {
  reparto: "pasticceria", destinazione: "", setDestinazione: () => {}, frigo: "", setFrigo: () => {},
  opzioniFrigo: frigo, opzioniCongelatori: congelatori, posizioneMancante: true, ...extra,
}));

describe("posizione del lotto", () => {
  test("24 apparecchi stanno in un menu a scomparsa, non in 24 card", () => {
    const html = mostra();
    expect((html.match(/<button/g) || []).length).toBe(1); // solo «Subito al banco»
    expect((html.match(/<option/g) || []).length).toBe(1 + 24);
    expect(html).toContain('<optgroup label="Frigoriferi">');
    expect(html).toContain('<optgroup label="Congelatori">');
  });

  test("l'apparecchio scelto resta selezionato nel menu", () => {
    const html = mostra({ destinazione: "abbattitore", frigo: "Congelatore N°3", posizioneMancante: false });
    expect(html).toMatch(/<option value="abbattitore:Congelatore N°3" selected/);
    expect(html).not.toContain("Scegli “Subito al banco”");
  });

  test("nel bar non c'e' il banco", () => {
    const html = mostra({ reparto: "bar" });
    expect(html).not.toContain("Subito al banco");
  });
});
