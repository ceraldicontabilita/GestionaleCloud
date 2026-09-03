// Test della configurazione di navigazione (fase 2, 24/07/2026):
// menu per ruolo, integrità del registro pagine, protezione admin.
// Le icone lucide vengono mockate: qui si testa la CONFIGURAZIONE, non il render.
jest.mock("lucide-react", () => new Proxy({}, { get: () => () => null }));

const { PRIMARY_TABS, SECONDARY_TABS, HACCP_TABS, VALID_TABS } = require("../config/navigation");
const { PAGE_NAMES, PAGE_META, TAB_HEADER_PROPRIO } = require("../config/pageMeta");
const { ADMIN_TABS, puoAprireTab, tabRiservataAdmin } = require("../config/permissions");
const {
  hashCatalogoProdotti,
  leggiCatalogoProdotti,
  risolviCatalogoProdotti,
  risolviSottoTabProdotti,
} = require("../router/prodottiRoute");

describe("registro di navigazione", () => {
  test("ogni tab di menu è tra le pagine valide", () => {
    [...PRIMARY_TABS, ...SECONDARY_TABS, ...HACCP_TABS].forEach((t) => {
      expect(VALID_TABS).toContain(t.id);
    });
  });

  test("ogni pagina valida ha un titolo (document.title / breadcrumb)", () => {
    VALID_TABS.forEach((id) => {
      expect(PAGE_NAMES[id]).toBeTruthy();
    });
  });

  test("nessun id duplicato tra i menu", () => {
    const ids = [...PRIMARY_TABS, ...SECONDARY_TABS, ...HACCP_TABS].map((t) => t.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  test("la barra principale mobile ha al massimo 5 voci", () => {
    expect(PRIMARY_TABS.length).toBeLessThanOrEqual(5);
  });

  test("le pagine con intestazione propria esistono nel registro", () => {
    TAB_HEADER_PROPRIO.forEach((id) => expect(PAGE_NAMES[id]).toBeTruthy());
  });

  test("ogni PAGE_META punta a una pagina reale", () => {
    Object.keys(PAGE_META).forEach((id) => expect(PAGE_NAMES[id]).toBeTruthy());
  });
});

describe("permessi di navigazione (menu in base al ruolo)", () => {
  test("le pagine admin sono bloccate per i dipendenti", () => {
    ADMIN_TABS.forEach((id) => {
      expect(puoAprireTab(id, false)).toBe(false);
      expect(puoAprireTab(id, true)).toBe(true);
    });
  });

  test("le pagine operative sono libere per tutti", () => {
    ["dashboard", "ricette", "lotti", "ordini", "temp_positive"].forEach((id) => {
      expect(tabRiservataAdmin(id)).toBe(false);
      expect(puoAprireTab(id, false)).toBe(true);
    });
  });

  test("le sezioni riservate includono backup, personale e configurazione", () => {
    ["backup", "personale", "configura", "controllo_dati", "stampanti"].forEach((id) =>
      expect(ADMIN_TABS).toContain(id));
  });

  test("il menu visibile a un dipendente non contiene pagine admin primarie", () => {
    const visibiliDipendente = [...PRIMARY_TABS, ...SECONDARY_TABS]
      .filter((t) => puoAprireTab(t.id, false))
      .map((t) => t.id);
    expect(visibiliDipendente).not.toContain("backup");
    expect(visibiliDipendente).toContain("lotti");
  });
});

describe("apertura route da hash (alias e fallback)", () => {
  // getInitialTab vive in hooks/useAppNavigation (importa sonner/axios via auth:
  // qui si replica il CONTRATTO sul confine: alias e fallback)
  const ALIAS = { ricettario: "ricette", food_cost: "ricette" };
  const risolvi = (hash) => {
    const h = hash.replace("#", "").split("/")[0];
    if (ALIAS[h]) return ALIAS[h];
    return VALID_TABS.includes(h) ? h : "dashboard";
  };

  test("hash valido apre la pagina giusta", () => {
    expect(risolvi("#lotti")).toBe("lotti");
    expect(risolvi("#gelati")).toBe("gelati");
    expect(risolvi("#prodotti/saima")).toBe("prodotti");
  });

  test("alias storici puntano a Ricette", () => {
    expect(risolvi("#ricettario")).toBe("ricette");
    expect(risolvi("#food_cost")).toBe("ricette");
  });

  test("hash sconosciuto ricade sulla dashboard", () => {
    expect(risolvi("#pagina-inesistente")).toBe("dashboard");
    expect(risolvi("")).toBe("dashboard");
  });

  test.each(["acquaviva", "saima", "mepa"])(
    "il deep-link %s apre il sotto-tab dei cataloghi",
    (fornitore) => {
      const hash = `#prodotti/${fornitore}`;
      expect(leggiCatalogoProdotti(hash)).toBe(fornitore);
      expect(risolviSottoTabProdotti(hash)).toBe("cataloghi");
      expect(hashCatalogoProdotti(fornitore)).toBe(`prodotti/${fornitore}`);
    }
  );

  test("la pagina prodotti senza fornitore resta sul Listino", () => {
    expect(leggiCatalogoProdotti("#prodotti")).toBeNull();
    expect(risolviSottoTabProdotti("#prodotti", "listino")).toBe("listino");
  });

  test("il contenitore riconosce anche una fonte catalogo dinamica", () => {
    expect(leggiCatalogoProdotti("#prodotti/sunset-cash")).toBe("sunset-cash");
    expect(risolviSottoTabProdotti("#prodotti/sunset-cash")).toBe("cataloghi");
    expect(risolviCatalogoProdotti("#prodotti/sunset-cash", ["sunset-cash"])).toBe("sunset-cash");
  });

  test("una fonte catalogo sconosciuta non apre una scheda inesistente", () => {
    expect(risolviCatalogoProdotti("#prodotti/sconosciuto")).toBe("acquaviva");
  });
});
