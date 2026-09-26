import { useState, useCallback } from "react";
import axios from "axios";
import { API } from "../utils/constants";

export function useStats() {
  // null = non ancora letto o non disponibile: mai uno zero finto.
  const [stats, setStats] = useState({ materie_prime: null, ricette: null, lotti_totali: null, lotti_settimana: null });

  const fetchStats = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/stats`);
      setStats(res.data);
    } catch (e) {
      console.error("Errore stats:", e);
      setStats({ materie_prime: null, ricette: null, lotti_totali: null, lotti_settimana: null, errore: true });
    }
  // axios e API sono import module-level stabili — non causano stale closures
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { stats, fetchStats };
}
