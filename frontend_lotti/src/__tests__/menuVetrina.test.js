// Logica della vetrina «In menu» (19/09/2026): quale prezzo il Menu espone,
// dove finisce la ricetta e quali sono le ricette «da sistemare».
// Le regole devono coincidere con il ponte backend (menu_bridge.py):
// prezzo_per_menu e _destinazione_menu.
const {
  CATEGORIA_PREDEFINITA,
  destinazioneMenu,
  indicizzaCategorie,
  ordinaPerUrgenza,
  prezzoPerMenu,
  problemiRicettaMenu,
  ricetteInMenu,
  riepilogoProblemi,
  sottocategoriaPerReparto,
} = require("../utils/menuVetrina");

// Due categorie di Lotti (selezionabili) e una di Qromo (non agganciabile).
const CATEGORIE = indicizzaCategorie({
  categorie: [
    {
      id: 1000001, name: "Ceraldi Production", name_it: "Produzione Ceraldi",
      origine: "lotti", selezionabile: true, motivo: null,
      sottocategorie: [
        { id: 1000002, category_id: 1000001, name: "Pastry", name_it: "Pasticceria", origine: "lotti", selezionabile: true },
        { id: 1000003, category_id: 1000001, name: "Bar", name_it: "Bar", origine: "lotti", selezionabile: true },
      ],
    },
    {
      id: 1000010, name: "Breakfast", name_it: "Colazioni",
      origine: "lotti", selezionabile: true, motivo: null,
      sottocategorie: [
        { id: 1000011, category_id: 1000010, name: "Pastry", name_it: "Sfogliate", origine: "lotti", selezionabile: true },
      ],
    },
    {
      id: 7, name: "Drinks", name_it: "Bevande", origine: null,
      selezionabile: false, motivo: "Categoria importata da Qromo: crea qui una categoria di Lotti.",
      sottocategorie: [],
    },
  ],
});

const sfogliatella = (extra = {}) => ({
  id: "r1", nome: "Sfogliatella riccia", reparto: "pasticceria",
  menu_pubblico: true, foto_url: "/api/foto/sfogliatella",
  descrizione: "Pasta sfoglia croccante, ricotta e canditi",
  prezzo_vendita: 1.8, prezzo_tavolo: 2.5,
  allergeni: ["Cereali contenenti glutine", "Latte", "Uova"],
  ...extra,
});

describe("prezzo che il Menu espone", () => {
  test("con il prezzo al tavolo deciso, il Menu mostra quello", () => {
    expect(prezzoPerMenu(sfogliatella())).toEqual({ prezzo: 2.5, origine: "tavolo" });
  });

  test("senza prezzo al tavolo si ripiega sul banco, e il ripiego resta visibile", () => {
    expect(prezzoPerMenu(sfogliatella({ prezzo_tavolo: null })))
      .toEqual({ prezzo: 1.8, origine: "banco" });
  });

  test("zero non è un prezzo deciso (stessa regola di prezzo_menu nel ponte)", () => {
    expect(prezzoPerMenu({ prezzo_tavolo: 0, prezzo_vendita: 0 }).origine).toBe("assente");
  });

  test("un prezzo scritto all'italiana con la virgola viene letto", () => {
    expect(prezzoPerMenu({ prezzo_tavolo: "2,50" })).toEqual({ prezzo: 2.5, origine: "tavolo" });
  });
});

describe("dove finisce la ricetta nel Menu", () => {
  test("la destinazione deriva sempre dal reparto", () => {
    expect(destinazioneMenu(sfogliatella(), CATEGORIE)).toEqual({
      origine: "automatica", categoria: CATEGORIA_PREDEFINITA, sottocategoria: "Pasticceria",
    });
  });

  test("i vecchi campi manuali non cambiano la destinazione", () => {
    expect(destinazioneMenu(sfogliatella({ menu_category_id: 7, menu_subcategory_id: 1000002 }), CATEGORIE))
      .toEqual({ origine: "automatica", categoria: CATEGORIA_PREDEFINITA, sottocategoria: "Pasticceria" });
  });

  test("un reparto sconosciuto finisce nella sezione Altro", () => {
    expect(sottocategoriaPerReparto("gastronomia")).toBe("Altro");
    expect(sottocategoriaPerReparto("Pasticceria")).toBe("Pasticceria");
  });
});

describe("cosa c'è da sistemare", () => {
  test("una scheda completa non ha problemi", () => {
    expect(problemiRicettaMenu(sfogliatella(), CATEGORIE)).toEqual([]);
  });

  test("senza prezzo al tavolo si segnala il ripiego sul banco", () => {
    expect(problemiRicettaMenu(sfogliatella({ prezzo_tavolo: null }), CATEGORIE))
      .toEqual(["prezzo_banco"]);
  });

  test("senza alcun prezzo il problema è più grave del semplice ripiego", () => {
    expect(problemiRicettaMenu(sfogliatella({ prezzo_tavolo: null, prezzo_vendita: null }), CATEGORIE))
      .toEqual(["senza_prezzo"]);
  });

  test("descrizione vuota o di soli spazi conta come mancante", () => {
    expect(problemiRicettaMenu(sfogliatella({ descrizione: "   " }), CATEGORIE))
      .toEqual(["senza_descrizione"]);
  });

  test("foto, prezzo e descrizione mancanti si sommano", () => {
    const rotta = sfogliatella({ foto_url: "", menu_category_id: 7, prezzo_tavolo: null, descrizione: "" });
    expect(problemiRicettaMenu(rotta, CATEGORIE))
      .toEqual(["prezzo_banco", "senza_descrizione", "senza_foto"]);
  });
});

describe("elenco e riepilogo della vetrina", () => {
  const ricette = [
    sfogliatella(),
    sfogliatella({ id: "r2", nome: "Babà", prezzo_tavolo: null }),
    sfogliatella({ id: "r3", nome: "Arancino", foto_url: "", descrizione: "" }),
    { id: "r4", nome: "Crema pasticcera", menu_pubblico: false, prezzo_tavolo: 1 },
    { id: "r5", nome: "Impasto base" },
  ];

  test("in vetrina ci vanno solo le ricette spuntate per il Menu pubblico", () => {
    expect(ricetteInMenu(ricette).map((r) => r.id)).toEqual(["r1", "r2", "r3"]);
  });

  test("il riepilogo conta ogni problema e quante ricette sono da sistemare", () => {
    const { conteggio, daSistemare, totale } = riepilogoProblemi(ricetteInMenu(ricette), CATEGORIE);
    expect(totale).toBe(3);
    expect(daSistemare).toBe(2);
    expect(conteggio.prezzo_banco).toBe(1);
    expect(conteggio.senza_descrizione).toBe(1);
    expect(conteggio.senza_foto).toBe(1);
    expect(conteggio.senza_prezzo).toBe(0);
  });

  test("le ricette da sistemare vengono prima, le complete in fondo", () => {
    const ordinate = ordinaPerUrgenza(ricetteInMenu(ricette), CATEGORIE);
    expect(ordinate.map((r) => r.nome)).toEqual(["Babà", "Arancino", "Sfogliatella riccia"]);
  });
});
