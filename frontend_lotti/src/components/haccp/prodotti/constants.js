/**
 * prodotti/constants.js — Costanti e utilità condivise per ProdottiVenditaView
 */
import React from "react";

// ─── Categorie gerarchiche ─────────────────────────────────────────────────
export const CATEGORIE = {
  "Pasticceria": [
    "Torte e Monoporzioni", "Mignon e Petit Fours", "Biscotti e Frolle",
    "Croissant e Viennoiserie", "Lievitati e Brioche", "Gelati e Semifreddi",
    "Cioccolatini e Praline", "Stagionale"
  ],
  "Salato": [
    "Pizze e Focacce", "Primi Piatti", "Secondi Piatti", "Antipasti",
    "Contorni", "Panini e Tramezzini"
  ],
  "Contorni": ["Verdure", "Legumi", "Patate", "Insalate"],
  "Secondi": ["Carni", "Pesce", "Uova"],
  "Bevande": ["Analcoliche", "Alcoliche", "Caffetteria"],
  "Già cotti": ["Soffici", "Donuts", "Roundy", "Muffin", "I Milanesi"],
  "Prelievitati": ["Tradizionali", "Superfarciti", "Bicolori", "Integrali", "Vegano", "Doramì", "Caruso", "Multicereali", "Fagotti", "Baby e Mini"],
  "Snack": ["Da scaldare", "Da friggere", "Da cuocere", "Già fritti", "Cornetti Salati"],
  "Pani e focacce": ["Focacce", "Pani Speciali", "Baguette", "Ciabatte", "Morbidi", "Toast e Tramezzini"],
  "Tipici": ["Specialità Napoletane", "Specialità Siciliane", "Calise"],
  "Dessert": ["Torte Pretagliate", "Torte Intere", "Al trancio", "Al cucchiaio"],
  "Biscotti": ["Biscotti Assortiti", "Monoporzioni"],
  "Sfoglie": [],
  "Monoporzioni": [],
  "Burger Buns": [],
  "Senza Glutine": [],
  "Semilavorati": [],
  "Piatti Pronti": ["Pasta", "Riso", "Carne", "Secondi"],
  "Esterno": ["Materia Prima", "Semilavorato", "Prodotto Finito"],
  "Salumi": ["Affettati", "Insaccati"],
  "Altro": ["Non Classificato"]
};

export const CATEGORIE_FLAT = Object.entries(CATEGORIE).flatMap(([parent, subs]) =>
  subs.map(sub => `${parent} > ${sub}`)
);

export const IVA_OPTIONS = [
  { label: "4%",         value: 4,  tipo: "pct" },
  { label: "10%",        value: 10, tipo: "pct" },
  { label: "22%",        value: 22, tipo: "pct" },
  { label: "Esente",     value: 0,  tipo: "esente" },
  { label: "IVA Compresa", value: -1, tipo: "compresa" }
];

// ─── Calcola margine ───────────────────────────────────────────────────────
// iva = 4|10|22 → prezzo è NETTO (si aggiunge IVA sopra)
// iva = -1      → prezzo è LORDO (già include IVA al 10%)
// iva = 0       → esente, nessuna IVA
export function calcolaMargine(pv, cp, iva, ivaCompresaAliquota = 10) {
  const pvF = parseFloat(pv) || 0;
  const cpF = parseFloat(cp) || 0;
  const ivaNum = parseFloat(iva);
  let prezzoNetto = pvF;
  let prezzoIvato = pvF;
  let aliquotaEffettiva = ivaNum;
  if (ivaNum === -1) {
    aliquotaEffettiva = ivaCompresaAliquota;
    prezzoNetto = pvF / (1 + ivaCompresaAliquota / 100);
    prezzoIvato = pvF;
  } else if (ivaNum === 0) {
    aliquotaEffettiva = 0;
    prezzoIvato = pvF;
  } else {
    prezzoIvato = pvF * (1 + ivaNum / 100);
  }
  const margineE = prezzoNetto - cpF;
  const margineP = prezzoNetto > 0 ? (margineE / prezzoNetto) * 100 : 0;
  return {
    margine_euro: Math.round(margineE * 100) / 100,
    margine_pct: Math.round(margineP * 10) / 10,
    prezzo_ivato: Math.round(prezzoIvato * 100) / 100,
    prezzo_netto: Math.round(prezzoNetto * 100) / 100,
    aliquota_effettiva: aliquotaEffettiva
  };
}

// ─── Componente Selettore Categoria Gerarchica ─────────────────────────────
export function CategoriaSelect({ value, onChange }) {
  const parts = (value || "").split(" > ");
  const parentVal = parts[0] || "";
  const subVal = parts[1] || "";
  const figli = parentVal ? CATEGORIE[parentVal] || [] : [];
  
  const handleParent = (e) => {
    const p = e.target.value;
    onChange(p); // Reset sottocategoria quando cambi macro
  };
  
  const handleSub = (e) => {
    const s = e.target.value;
    onChange(s ? `${parentVal} > ${s}` : parentVal);
  };

  return (
    <div className="relative">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="text-xs text-gray-500 mb-1 block">Macrocategoria</label>
          <select className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#5b7a6b]"
            value={parentVal}
            onChange={handleParent}>
            <option value="">-- Seleziona --</option>
            {Object.keys(CATEGORIE).map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-500 mb-1 block">Sottocategoria</label>
          <select className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#5b7a6b]"
            value={subVal}
            onChange={handleSub}
            disabled={!parentVal || figli.length === 0}>
            <option value="">-- Nessuna --</option>
            {figli.map(f => <option key={f} value={f}>{f}</option>)}
          </select>
        </div>
      </div>
      {value && <p className="text-xs text-[#5b7a6b] mt-1">Categoria: <strong>{value}</strong></p>}
    </div>
  );
}
