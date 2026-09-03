import { useState, useEffect, useRef, useLayoutEffect } from "react";
import { ShieldCheck, ChevronDown } from "lucide-react";

/**
 * HACCPDropdown — menu "Conformità HACCP".
 * Renderizzato in posizione "fixed" calcolata dal bottone: l'header/navbar ha
 * overflow che altrimenti taglierebbe un dropdown "absolute" (stesso difetto
 * risolto in AltroDropdown).
 */
export function HACCPDropdown({ tabsHACCP, activeTab, onTabChange }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const ref = useRef(null);
  const btnRef = useRef(null);
  const isActive = tabsHACCP.some((t) => t.id === activeTab);

  useLayoutEffect(() => {
    if (open && btnRef.current) {
      const r = btnRef.current.getBoundingClientRect();
      const width = 230;
      let left = r.left;
      if (left + width > window.innerWidth - 8) left = window.innerWidth - width - 8;
      setPos({ top: r.bottom + 6, left: Math.max(8, left) });
    }
  }, [open]);

  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("pointerdown", h);
    return () => document.removeEventListener("pointerdown", h);
  }, []);

  return (
    <div ref={ref} style={{ position: "relative", flexShrink: 0 }}>
      <button
        ref={btnRef}
        onClick={() => setOpen((o) => !o)}
        data-testid="haccp-dropdown-btn"
        className="g-haccp-btn"
        style={isActive ? {
          background: "rgba(0,184,132,.15)",
          color: "#00B884",
          borderColor: "rgba(0,184,132,.35)",
        } : {}}
      >
        <ShieldCheck size={14} />
        Conformità HACCP
        <ChevronDown
          size={12}
          style={{ transition: "transform .15s", transform: open ? "rotate(180deg)" : "none" }}
        />
      </button>

      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 1000 }} />
          <div
            className="g-dropdown"
            style={{
              position: "fixed",
              top: pos.top,
              left: pos.left,
              minWidth: 230,
              maxHeight: "70vh",
              overflowY: "auto",
              zIndex: 1001,
            }}
          >
            <div className="g-dropdown-section" style={{ borderTop: "none", marginTop: 0 }}>
              Moduli HACCP
            </div>
            {tabsHACCP.map((tab) => (
              <button
                key={tab.id}
                onClick={() => { onTabChange(tab.id); setOpen(false); }}
                data-testid={`haccp-menu-${tab.id}`}
                className={`g-dropdown-item${activeTab === tab.id ? " active" : ""}`}
              >
                <tab.icon size={15} />
                {tab.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
