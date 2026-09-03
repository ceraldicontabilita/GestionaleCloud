import React from "react";
import { useNavigate } from "react-router-dom";
import {
  Users, Briefcase, ChevronRight, Clock, Palmtree, PiggyBank,
  Wallet, CalendarClock, FolderOpen, CheckCircle2,
} from "lucide-react";

const SAGE = "#5b7a6b";
const SAGE_DARK = "#3f5a4e";
const CREAM = "#faf7f0";
const CARD = "#fffefb";
const INK = "#2a3329";
const MUTED = "#6b7669";
const SAND = "#e6e0d4";

const FEATURES = [
  {
    icon: Palmtree,
    title: "Ferie & permessi",
    text: "Residui calcolati in automatico per ogni dipendente, aggiornati mese per mese — niente più tabelle da ricontrollare a mano.",
    to: "/dipendenti/ferie-permessi",
  },
  {
    icon: PiggyBank,
    title: "TFR progressivo",
    text: "Accantonamento anno per anno tenuto in automatico dal sistema, sempre allineato a cedolini e 13ª/14ª.",
    to: "/dipendenti/tfr",
  },
  {
    icon: Clock,
    title: "Timbrature geolocalizzate",
    text: "Entrata e uscita dal telefono, solo dalla sede. Atteso (da turno) e ore effettive a confronto in un colpo d'occhio.",
    to: "/dipendenti/timbrature",
  },
  {
    icon: CalendarClock,
    title: "Turni automatici",
    text: "Rotazioni, giorno di riposo, Lunga e onomastici generati in un clic, sempre modificabili a mano.",
    to: "/dipendenti/turni",
  },
  {
    icon: Wallet,
    title: "Buste paga & Prima Nota",
    text: "Cedolini, voci di busta e saldo progressivo per dipendente, con ricerca su qualsiasi codice.",
    to: "/dipendenti/buste-paga",
  },
  {
    icon: FolderOpen,
    title: "Documenti & contratti",
    text: "Fascicolo digitale, firma dei contratti e archivio documenti classificato automaticamente.",
    to: "/dipendenti/documenti",
  },
];

const wrap = {
  minHeight: "100vh", background: CREAM,
  fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif", color: INK,
};
const hero = {
  padding: "56px 24px 40px", textAlign: "center", maxWidth: 720, margin: "0 auto",
};
const logo = {
  width: 64, height: 64, borderRadius: 18, margin: "0 auto 16px",
  background: `linear-gradient(135deg, ${SAGE}, ${SAGE_DARK})`, display: "flex",
  alignItems: "center", justifyContent: "center", color: "#fff",
};
const kicker = {
  display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12.5, fontWeight: 700,
  color: SAGE_DARK, background: "#eef1ea", border: `1px solid ${SAND}`, borderRadius: 999,
  padding: "5px 12px", marginBottom: 14,
};
const h1 = {
  fontFamily: "'Fraunces', serif", fontWeight: 700, fontSize: "clamp(26px, 4vw, 36px)",
  lineHeight: 1.15, marginBottom: 10,
};
const sub = { color: MUTED, fontSize: 15.5, lineHeight: 1.55, maxWidth: 560, margin: "0 auto" };

const ctaRow = {
  maxWidth: 900, margin: "8px auto 48px", padding: "0 24px",
  display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 14,
};
const card = {
  background: CARD, border: `1px solid ${SAND}`, borderRadius: 16,
  boxShadow: "0 4px 18px rgba(63,90,78,.10)", padding: 18, cursor: "pointer",
  display: "flex", alignItems: "center", gap: 14,
};
const iconBox = (grad) => ({
  width: 46, height: 46, borderRadius: 12, background: grad, display: "flex",
  alignItems: "center", justifyContent: "center", color: "#fff", flexShrink: 0,
});

const section = { maxWidth: 1000, margin: "0 auto", padding: "0 24px 64px" };
const sectionTitle = {
  fontFamily: "'Fraunces', serif", fontWeight: 600, fontSize: 22, textAlign: "center",
  marginBottom: 6, color: SAGE_DARK,
};
const sectionSub = { textAlign: "center", color: MUTED, fontSize: 14.5, marginBottom: 30 };
const grid = {
  display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 16,
};
const featCard = {
  background: CARD, border: `1px solid ${SAND}`, borderRadius: 14, padding: "18px 18px 20px",
};
const featIcon = {
  width: 40, height: 40, borderRadius: 10, background: "#eef1ea", color: SAGE_DARK,
  display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 12,
};
const footer = {
  textAlign: "center", color: MUTED, fontSize: 12.5, padding: "0 24px 36px",
};

export default function Landing() {
  const nav = useNavigate();
  return (
    <div style={wrap}>
      <div style={hero}>
        <div style={logo}><Users size={30} /></div>
        <div style={kicker}><CheckCircle2 size={14} /> Al posto del foglio Excel</div>
        <h1 style={h1}>Dipendenti Ceraldi</h1>
        <p style={sub}>
          Ferie, TFR, presenze, turni e buste paga in un'unica app, sempre aggiornata
          e accessibile da telefono o computer — niente più fogli Excel da tenere allineati a mano.
        </p>
      </div>

      <div style={ctaRow}>
        <div style={card} onClick={() => nav("/portale")}>
          <div style={iconBox(`linear-gradient(135deg, ${SAGE}, ${SAGE_DARK})`)}><Users size={24} /></div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: 16 }}>Portale dipendente</div>
            <div style={{ color: MUTED, fontSize: 13 }}>Turni, buste paga, richieste, avvisi — accesso con PIN</div>
          </div>
          <ChevronRight size={20} color={MUTED} />
        </div>

        <div style={card} onClick={() => nav("/dipendenti")}>
          <div style={iconBox(`linear-gradient(135deg, ${SAGE_DARK}, ${SAGE})`)}><Briefcase size={24} /></div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: 16 }}>Gestione ufficio</div>
            <div style={{ color: MUTED, fontSize: 13 }}>Anagrafica, presenze, ferie, turni, buste, missioni, documenti</div>
          </div>
          <ChevronRight size={20} color={MUTED} />
        </div>
      </div>

      <div style={section}>
        <div style={sectionTitle}>Tutto quello che oggi è sparso tra più fogli</div>
        <div style={sectionSub}>Un solo posto per ogni calcolo, sempre coerente tra i moduli</div>
        <div style={grid}>
          {FEATURES.map(({ icon: Icon, title, text, to }) => (
            <div
              style={{ ...featCard, cursor: "pointer" }}
              key={title}
              onClick={() => nav(to)}
              role="link"
              title={`Apri ${title}`}
            >
              <div style={featIcon}><Icon size={20} /></div>
              <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 6, display: "flex", alignItems: "center", gap: 6 }}>
                {title} <ChevronRight size={15} color={MUTED} />
              </div>
              <div style={{ color: MUTED, fontSize: 13.5, lineHeight: 1.5 }}>{text}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={footer}>Ceraldi Group S.r.l. — Ceraldi Caffè, Piazza Carità 14, Napoli</div>
    </div>
  );
}
