const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");

jest.mock("lucide-react", () => ({ BookOpen: () => null, EyeOff: () => null }));

const CardProdotto = require("../components/haccp/tablet/CardProdotto").default;
const { usaCardTestuale } = require("../components/haccp/tablet/CardProdotto");

describe("foto nelle schede prodotto del tablet", () => {
  test("una ricetta base con varianti mostra la foto quando presente", () => {
    expect(usaCardTestuale({ foto_url: "/api/foto/abc" }, "pasticceria")).toBe(false);
  });

  test("una ricetta di pasticceria senza foto conserva la scheda testuale", () => {
    expect(usaCardTestuale({ foto_url: "" }, "pasticceria")).toBe(true);
  });

  test("una variante puo mostrare provvisoriamente la foto della ricetta base", () => {
    expect(usaCardTestuale({ foto_url: "", foto_fallback_url: "/api/foto/base" }, "pasticceria")).toBe(false);
  });

  test("il comando Escludi compare soltanto quando il chiamante lo autorizza", () => {
    const prodotto = { id: "r1", nome: "Baba", foto_url: "" };
    const senzaPermesso = renderToStaticMarkup(
      React.createElement(CardProdotto, { prodotto, reparto: "pasticceria", onTap: () => {} }),
    );
    const amministratore = renderToStaticMarkup(
      React.createElement(CardProdotto, { prodotto, reparto: "pasticceria", onTap: () => {}, onEscludi: () => {} }),
    );

    expect(senzaPermesso).not.toContain("Escludi");
    expect(amministratore).toContain("Escludi dalle card");
    expect(amministratore).toContain("Escludi Baba");
  });
});

describe("Apri scheda sulle card di reparto", () => {
  const prodotto = { id: "r1", nome: "Amaretti", foto_url: "/api/foto/a" };

  test("la card con foto e quella testuale offrono «Apri scheda» a tutta larghezza", () => {
    const conFoto = renderToStaticMarkup(
      React.createElement(CardProdotto, { prodotto, reparto: "pasticceria", onTap: () => {}, onVediRicetta: () => {} }),
    );
    const testuale = renderToStaticMarkup(
      React.createElement(CardProdotto, { prodotto: { ...prodotto, foto_url: "" }, reparto: "pasticceria", onTap: () => {}, onVediRicetta: () => {} }),
    );
    for (const html of [conFoto, testuale]) {
      expect(html).toContain("Apri scheda");
      expect(html).toContain("Apri la scheda di Amaretti");
      expect(html).toContain("min-height:44px");
    }
  });

  test("senza chi apre la scheda il bottone non compare", () => {
    const html = renderToStaticMarkup(
      React.createElement(CardProdotto, { prodotto, reparto: "pasticceria", onTap: () => {} }),
    );
    expect(html).not.toContain("Apri scheda");
  });
});
