import { useState, useCallback } from "react";
import axios from "axios";
import { API } from "../utils/constants";

export function useStats() {
  const [stats, setStats] = useState({ materie_prime: 0, ricette: 0, lotti_totali: 0, lotti_settimana: 0 });

  const fetchStats = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/stats`);
      setStats(res.data);
    } catch (e) {
      console.error("Errore stats:", e);
    }
  // axios e API sono import module-level stabili — non causano stale closures
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { stats, fetchStats };
}
