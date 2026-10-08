import { useEffect, useState } from "react";
import axios from "axios";
import { API } from "./constants";

// L'elenco delle categorie del Dizionario sta SOLO nel backend
// (app/lotti/servizi/dizionario_ingredienti.py): qui si legge, non si copia.
let _cache = null;

export function useCategorieDizionario() {
  const [categorie, setCategorie] = useState(_cache || []);
  useEffect(() => {
    if (_cache) return;
    axios.get(`${API}/food-cost/dizionario/categorie`)
      .then((r) => {
        _cache = Array.isArray(r.data?.categorie) ? r.data.categorie : [];
        setCategorie(_cache);
      })
      .catch(() => { /* non bloccante: la tendina mostra la categoria della riga */ });
  }, []);
  return categorie;
}
