// I 14 allergeni del Reg. UE 1169/2011 e le parole chiave con cui vengono
// riconosciuti nel testo di ingredienti/etichette.
// Estratti da LottiList.jsx (refactor 25/07/2026) senza modifiche: stesse
// voci, stesse parole chiave — cambiare questi elenchi cambia le etichette
// stampate, quindi si toccano solo su richiesta esplicita.

export const ALLERGENI_EU_LIST = [
  "Cereali contenenti glutine","Crostacei","Uova","Pesce","Arachidi",
  "Soia","Latte","Frutta a guscio","Sedano","Senape","Semi di sesamo",
  "Anidride solforosa e solfiti","Lupino","Molluschi"
];

export const ALLERGENI_KEYWORDS_MAP = {
  "Cereali contenenti glutine": ["glutine","grano","frumento","orzo","segale","avena","farro","kamut","semola"],
  "Uova": ["uov","uova"],
  "Latte": ["latte","lattosio","caseina","panna","burro","formaggio","mozzarella","ricotta","fior di latte","parmigiano","pecorino"],
  "Arachidi": ["arachide","arachidi"],
  "Soia": ["soia","soy"],
  "Pesce": ["pesce","acciughe","alici","tonno","salmone","merluzzo","baccalà"],
  "Crostacei": ["gamberi","aragoste","astici","granchi"],
  "Frutta a guscio": ["noci","mandorle","nocciole","pistacchio","pinoli","anacardi","pecan","macadamia"],
  "Sedano": ["sedano","celeriac"],
  "Senape": ["senape","mostarda"],
  "Semi di sesamo": ["sesamo"],
  "Anidride solforosa e solfiti": ["solfiti","anidride solforosa","so2"],
  "Lupino": ["lupino","lupini"],
  "Molluschi": ["molluschi","cozze","vongole","polpo","calamari","seppie","lumache"]
};

// Allergeni riconosciuti in un testo libero — stessa identica logica che era
// inline nel modale Dettaglio Lotto.
export const allergeniDaTesto = (testo) => {
  const t = (testo || "").toLowerCase();
  return ALLERGENI_EU_LIST.filter((a) => {
    const kws = ALLERGENI_KEYWORDS_MAP[a] || [a.toLowerCase()];
    return kws.some((k) => t.includes(k));
  });
};
