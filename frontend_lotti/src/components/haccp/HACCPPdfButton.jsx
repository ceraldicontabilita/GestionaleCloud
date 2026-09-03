import { useMemo, useState } from "react";
import { FileText, X } from "lucide-react";
import { API, withToken } from "../../utils/constants";

const MESI = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"];

const HACCPPdfButton = () => {
  const now = new Date();
  const [mese, setMese] = useState(now.getMonth() + 1);
  const [anno, setAnno] = useState(now.getFullYear());
  const [open, setOpen] = useState(false);

  const anni = useMemo(() => {
    const current = new Date().getFullYear();
    return Array.from({ length: 7 }, (_, i) => current - 3 + i);
  }, []);

  const reportUrl = `${API}/report-haccp/mensile?mese=${mese}&anno=${anno}`;

  const apriReport = () => {
    window.open(withToken(reportUrl), "_blank", "noopener,noreferrer");
    setOpen(false);
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        data-testid="btn-scarica-pdf-haccp"
        className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 text-white rounded-lg text-xs font-semibold hover:bg-red-700 transition-colors shadow-sm whitespace-nowrap ml-auto flex-shrink-0"
      >
        <FileText size={13} />
        Report PDF
      </button>

      {open && (
        <div style={{ position: "fixed", inset: 0, zIndex: 99999, background: "rgba(15,23,42,0.55)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
          <div style={{ background: "#fff", borderRadius: 14, width: 340, boxShadow: "0 22px 70px rgba(15,23,42,0.35)", overflow: "hidden" }}>
            <div style={{ padding: "14px 16px", borderBottom: "1px solid #e2e8f0", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ fontSize: 16, fontWeight: 800, color: "#1e293b" }}>Report HACCP Mensile</div>
              <button onClick={() => setOpen(false)} style={{ border: 0, background: "transparent", color: "#64748b", cursor: "pointer", padding: 4 }}><X size={18} /></button>
            </div>

            <div style={{ padding: 16 }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 110px", gap: 10, marginBottom: 16 }}>
                <select value={mese} onChange={e => setMese(Number(e.target.value))} style={{ padding: "9px 11px", borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 14, background: "#fff" }}>
                  {MESI.map((m, i) => <option key={i + 1} value={i + 1}>{m}</option>)}
                </select>
                <select value={anno} onChange={e => setAnno(Number(e.target.value))} style={{ padding: "9px 11px", borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 14, background: "#fff" }}>
                  {anni.map(a => <option key={a} value={a}>{a}</option>)}
                </select>
              </div>

              <div style={{ display: "flex", gap: 10 }}>
                <button onClick={() => setOpen(false)} style={{ flex: 1, padding: "10px 0", borderRadius: 9, border: "1px solid #cbd5e1", background: "#f8fafc", fontWeight: 700, color: "#475569", cursor: "pointer" }}>Annulla</button>
                <button onClick={apriReport} data-testid="btn-apri-report-confirm" style={{ flex: 2, padding: "10px 0", borderRadius: 9, border: 0, background: "#dc2626", color: "#fff", fontWeight: 800, cursor: "pointer" }}>Apri report</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default HACCPPdfButton;
