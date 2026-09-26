import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import { formatEuroD } from "../lib/utils";
import { aggregaCassaGiorno, dataOggiISO } from "../lib/situazioneOggiCassa";

export default function SituazioneOggiCassa({ giorno }) {
  const data = giorno || dataOggiISO();
  const [stato, setStato] = useState({ loading: true, errore: "", dati: null });

  useEffect(() => {
    let vivo = true;
    const anno = data.slice(0, 4);
    api.get(`/api/prima-nota/cassa?anno=${anno}&data_da=${data}&data_a=${data}&limit=500`)
      .then((res) => {
        if (!vivo) return;
        setStato({ loading: false, errore: "", dati: aggregaCassaGiorno(res.data, data) });
      })
      .catch((err) => {
        if (!vivo) return;
        setStato({
          loading: false,
          errore: err.response?.data?.detail || "Cassa di oggi non disponibile",
          dati: null,
        });
      });
    return () => { vivo = false; };
  }, [data]);

  const box = {
    background: "#faf7f0",
    border: "1px solid #d7e0d4",
    borderRadius: 12,
    padding: 14,
    marginBottom: 16,
  };

  if (stato.loading) {
    return <div data-testid="situazione-oggi" style={box}>Lettura cassa di oggi…</div>;
  }
  if (stato.errore) {
    return <div data-testid="situazione-oggi" role="alert" style={box}>{stato.errore}</div>;
  }

  const d = stato.dati;
  const cella = (etichetta, valore) => (
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7669", textTransform: "uppercase" }}>{etichetta}</div>
      <div style={{ fontSize: 16, fontWeight: 800, color: "#141413", fontFamily: "ui-monospace, Menlo, monospace" }}>
        {formatEuroD(valore)}
      </div>
    </div>
  );

  return (
    <section data-testid="situazione-oggi" style={box}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 10 }}>
        <strong style={{ color: "#141413" }}>Cassa di oggi</strong>
        <Link to="/prima-nota#sezione=cassa" style={{ color: "#5b7a6b", fontWeight: 700, fontSize: 13 }}>
          Apri registro
        </Link>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 10 }}>
        {cella("Corrispettivi", d.corrispettivi)}
        {cella("POS verso banca", d.posVersoBanca)}
        {cella("Altre uscite", d.altreUscite)}
        {cella("Netto giornata", d.saldoGiorno)}
      </div>
      <p style={{ margin: "10px 0 0", fontSize: 12, color: "#6b7669" }}>
        Stessi movimenti di Prima Nota Cassa. Qui non si scrive un secondo libro.
      </p>
    </section>
  );
}
