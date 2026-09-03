/**
 * Accesso alla pagina Turni dell'azienda per il responsabile turni.
 *
 * Il responsabile turni non e' un utente del gestionale: entra dal portale
 * dipendenti (PIN personale, token `pt_token` con ruolo `responsabile_turni`)
 * e puo' vedere SOLO la pagina Turni dell'area gestione. L'amministratore
 * invece usa la sessione unica del gestionale e arriva a /hr dal menu.
 */
import React from "react";
import { Navigate } from "react-router-dom";

function tokenValido(token) {
  if (!token) return false;
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return !payload.exp || payload.exp * 1000 > Date.now();
  } catch {
    return false;
  }
}

export default function HRGate({ roles, children }) {
  const hasWindow = typeof window !== "undefined";
  const role = hasWindow ? localStorage.getItem("pt_role") : null;
  const token = hasWindow ? localStorage.getItem("pt_token") : null;
  if (!roles.includes(role) || !tokenValido(token)) {
    if (hasWindow && !tokenValido(token)) {
      localStorage.removeItem("pt_token");
      localStorage.removeItem("pt_role");
      localStorage.removeItem("pt_name");
    }
    return <Navigate to="/portale" replace />;
  }
  return children;
}
