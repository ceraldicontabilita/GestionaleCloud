import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { indicizzaCategorie } from "../utils/menuVetrina";

const API = process.env.REACT_APP_LOTTI_BACKEND_URL + "/api";

const messaggioErrore = (errore) => {
  const dettaglio = errore?.response?.data?.detail;
  if (typeof dettaglio === "string" && dettaglio) return dettaglio;
  if (errore?.response?.status === 503) return "Menu digitale non configurato su questo ambiente";
  return "Categorie del Menu non raggiungibili";
};

/** Categorie lette dal Menu per mostrare la vetrina; non sono editabili dalla ricetta. */
export function useCategorieMenu() {
  const [dati, setDati] = useState(null);
  const [caricando, setCaricando] = useState(true);
  const [errore, setErrore] = useState("");

  const carica = useCallback(async () => {
    setCaricando(true);
    try {
      const risposta = await axios.get(`${API}/menu-categorie`);
      setDati(risposta.data || { categorie: [] });
      setErrore("");
    } catch (e) {
      setDati({ categorie: [] });
      setErrore(messaggioErrore(e));
    } finally {
      setCaricando(false);
    }
  }, []);

  useEffect(() => { carica(); }, [carica]);
  const indice = useMemo(() => indicizzaCategorie(dati), [dati]);
  return { dati, indice, caricando, errore, ricarica: carica };
}
