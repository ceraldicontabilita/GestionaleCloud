import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { setupAxiosAuth, startTokenAutoRefresh } from "@/auth";
import LoginGate from "@/components/auth/LoginGate";

setupAxiosAuth();
startTokenAutoRefresh();

/**
 * Patch DOM per React 19 — previene crash "removeChild" / "insertBefore"
 * causati da estensioni browser (Google Translate, Grammarly, etc.)
 * che modificano il DOM fuori dal controllo di React.
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
    <LoginGate>
      <App />
    </LoginGate>
  </React.StrictMode>,
);
