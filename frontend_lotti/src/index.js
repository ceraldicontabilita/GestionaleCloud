import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { avviaTabelleCard } from "../../frontend_shared/tabelleCard";
import { setupAxiosAuth, startTokenAutoRefresh } from "@/auth";
import LoginGate from "@/components/auth/LoginGate";
import ErrorBoundary from "@/components/ErrorBoundary";

setupAxiosAuth();
startTokenAutoRefresh();

/**
 * Patch DOM per React 19 — previene crash "removeChild" / "insertBefore"
 * causati da estensioni browser (Google Translate, Grammarly, etc.)
 * che modificano il DOM fuori dal controllo di React.
 * È il rimedio documentato in facebook/react#11538: la causa sta fuori
 * dall'app (l'estensione), quindi non si toglie; `translate="no"` in
 * index.html riduce i casi. Salta solo nodi che non sono figli del padre.
 */
if (typeof Node !== "undefined") {
  const origRemoveChild = Node.prototype.removeChild;
  Node.prototype.removeChild = function (child) {
    if (child.parentNode !== this) {
      console.warn("removeChild: node not a child — skipped", child);
      return child;
    }
    return origRemoveChild.call(this, child);
  };

  const origInsertBefore = Node.prototype.insertBefore;
  Node.prototype.insertBefore = function (newNode, refNode) {
    if (refNode && refNode.parentNode !== this) {
      console.warn("insertBefore: ref node not a child — skipped", refNode);
      return newNode;
    }
    return origInsertBefore.call(this, newNode, refNode);
  };
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    {/* Rete di radice: un errore fuori dalle pagine (testata, login, router)
        mostra un messaggio con «Riprova», non uno schermo bianco. */}
    <ErrorBoundary>
      <LoginGate>
        <App />
      </LoginGate>
    </ErrorBoundary>
  </React.StrictMode>,
);
avviaTabelleCard();
