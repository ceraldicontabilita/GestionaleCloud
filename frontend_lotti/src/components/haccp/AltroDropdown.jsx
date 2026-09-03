import { useState, useEffect, useRef, useLayoutEffect } from "react";
import { MoreHorizontal, ChevronDown } from "lucide-react";

/**
 * AltroDropdown — Dropdown per tab secondari nella navbar principale.
 * Il menu è renderizzato in posizione "fixed" calcolata dal bottone, perché
 * la navbar ha overflow-x:auto che altrimenti taglia un dropdown "absolute".
 */
export function AltroDropdown({ tabs, activeTab, onTabChange }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, right: 0 });
  const ref = useRef(null);
  const btnRef = useRef(null);
  const isActive = tabs.some((t) => t.id === activeTab);

  // Posiziona il menu sotto il bottone, ancorato al viewport (fixed)
  useLayoutEffect(() => {
    if (open && btnRef.current) {
      const r = btnRef.current.getBoundingClientRect();
      setPos({ top: r.bottom + 6, right: Math.max(8, window.innerWidth - r.right) });
    }
  }, [open]);

  useEffect(() => {
    const h = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    // pointerdown copre sia mouse che touch
    document.addEventListener("pointerdown", h);
    return () => document.removeEventListener("pointerdown", h);
  }, []);

  return (
    <div ref={ref} style={{ position: "relative", flexShrink: 0 }}>
      <button
        ref={btnRef}
        onClick={() => setOpen((o) => !o)}
        data-testid="altro-dropdown-btn"
        className={`g-nav-btn${isActive ? " active" : ""}`}
        style={{ display: "flex", alignItems: "center", gap: 4 }}
      >
        <MoreHorizontal size={13} />
        Altro
        <ChevronDown
          size={11}
          style={{ transition: "transform .15s", transform: open ? "rotate(180deg)" : "none" }}
        />
      </button>

      {open && (
        <>
          {/* overlay trasparente per chiudere al tap fuori (mobile) */}
          <div
            onClick={() => setOpen(false)}
            style={{ position: "fixed", inset: 0, zIndex: 1000 }}
          />
          <div
            className="g-dropdown"
            style={{
              position: "fixed",
              top: pos.top,
              right: pos.right,
              left: "auto",
              minWidth: 210,
              maxHeight: "70vh",
              overflowY: "auto",
              zIndex: 1001,
            }}
          >
            {tabs.map((tab, index) => {
              const showSection = tab.section && tab.section !== tabs[index - 1]?.section;
              return (
                <div key={tab.id}>
                  {showSection && (
                    <div className="g-dropdown-section" style={index === 0 ? { borderTop: "none", marginTop: 0 } : undefined}>
                      {tab.section}
                    </div>
                  )}
                  <button
                    onClick={() => { onTabChange(tab.id); setOpen(false); }}
                    data-testid={`altro-menu-${tab.id}`}
                    className={`g-dropdown-item${activeTab === tab.id ? " active" : ""}`}
                  >
                    <tab.icon size={15} />
                    {tab.label}
                  </button>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
