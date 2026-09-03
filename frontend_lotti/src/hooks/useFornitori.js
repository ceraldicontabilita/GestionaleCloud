import { useState, useCallback } from "react";
import axios from "axios";
import { API } from "../utils/constants";

export function useFornitori() {
  const [fornitori, setFornitori] = useState([]);

  const fetchFornitori = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/fornitori`);
      setFornitori(res.data);
    } catch (e) {
      console.error("Errore fornitori:", e);
    }
  }, []);

  return { fornitori, fetchFornitori };
}
