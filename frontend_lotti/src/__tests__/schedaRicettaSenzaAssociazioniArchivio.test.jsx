import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import SchedaRicettaChiaraModal from "../components/haccp/SchedaRicettaChiaraModal";

global.IS_REACT_ACT_ENVIRONMENT = true;

test("la scheda operativa non prende procedimento e provenienza da un archivio omonimo", async () => {
  const node = document.createElement("div");
  document.body.appendChild(node);
  const root = createRoot(node);
  try {
    await act(async () => root.render(<SchedaRicettaChiaraModal
      ricetta={{
        id: "cer-1", nome: "Biscotti savoiardi", procedimento_testo: "Procedimento operativo.",
        documentazione_archivio: {
          procedure: "Procedimento storico non verificato.", source: "Fonte omonima",
          provenance: { sheet: "Foglio storico", row: 23 },
        },
      }}
      onClose={() => {}}
    />));
    expect(node.textContent).toContain("Procedimento operativo.");
    expect(node.textContent).not.toContain("Procedimento storico non verificato.");
    expect(node.textContent).not.toContain("Fonte omonima");
    expect(node.textContent).not.toContain("Foglio storico");
  } finally {
    await act(async () => root.unmount());
    node.remove();
  }
});
