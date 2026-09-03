// Layout KIOSK (tablet di reparto) — estratto da App.js (fase 2, 24/07/2026).
// Gestisce la sessione operatore (PIN) e instrada al reparto giusto.
// La persona resta identificata mentre passa tra i reparti. Le azioni di
// magazzino chiedono una conferma recente separata, senza chiudere il reparto.
import { TabletView } from "../components/haccp/TabletView";
import TabletHome, { REPARTI_SOLO_ADMIN } from "../components/haccp/TabletHome";
import { VenditaBancoView } from "../components/haccp/VenditaBancoView";
import MagazzinoBarView from "../components/haccp/MagazzinoBarView";
import OrdiniView from "../components/haccp/OrdiniView";
import DoseProduzioneView from "../components/haccp/tablet/DoseProduzioneView";
import { clearTabletSession, getTabletSession, moveTabletSessionTo } from "../utils/tabletSession";

export default function KioskLayout({ hash }) {
  const reparto = hash.split("/")[1] || "home";

  // Home kiosk — nessuna autenticazione richiesta, solo selezione reparto
  if (reparto === "home") {
    return <TabletHome onEntra={(rep) => { window.location.hash = `tablet/${rep}`; }} />;
  }

  // Tutti gli altri reparti richiedono sessione operatore
  let opObj = getTabletSession();

  // Reparti riservati al titolare (Enzo 25/07/2026: «il dipendente deve solo
  // produrre e vedere le ricette»). Il controllo non sta solo nel tastierino:
  // chi arriva col link diretto #tablet/ordini, o chi ha cambiato reparto con
  // una sessione da dipendente ancora valida, viene rimandato alle card.
  if (opObj && REPARTI_SOLO_ADMIN.includes(reparto) && opObj.ruolo !== "amministratore") {
    // Non cancellare l'identità del dipendente: se ha toccato per errore una
    // card riservata, può annullare e continuare negli altri reparti senza
    // reinserire il PIN.
    opObj = null;
  }

  // Il cambio reparto non è un cambio persona: aggiorna soltanto la sezione.
  if (opObj && opObj.reparto && opObj.reparto !== reparto) {
    opObj = moveTabletSessionTo(reparto);
  }

  if (!opObj) {
    // Nessuna sessione (o reparto diverso) → home con reparto pre-selezionato
    return <TabletHome onEntra={(rep) => { window.location.hash = `tablet/${rep}`; }} preselectReparto={reparto} />;
  }

  const esciGestionale = () => {
    clearTabletSession();
    window.location.hash = "dashboard";
    window.location.reload();
  };
  const tornaReparti = () => { window.location.hash = "tablet/home"; };

  if (reparto === "vendita") return <VenditaBancoView onBack={tornaReparti} />;
  if (reparto === "magazzino") return <MagazzinoBarView onBack={tornaReparti} />;
  // Card portate nel kiosk il 25/07/2026 (il gestionale è ora solo del
  // titolare): la Lavagna delle richieste e gli Ordini ai fornitori.
  if (reparto === "lavagna") return <MagazzinoBarView onBack={tornaReparti} soloLavagna />;
  // "Dose di oggi": il pasticciere decide quanto ingrediente base usa e tutte
  // le altre dosi si adeguano (Enzo 25/07/2026). Non modifica la ricetta.
  if (reparto === "dosi") return <DoseProduzioneView onBack={() => { window.location.hash = "tablet/home"; }} />;
  if (reparto === "ordini") {
    // OrdiniView è nata nel gestionale e non ha un "indietro": nel kiosk gliene
    // mettiamo uno sopra, altrimenti dal tablet non si tornerebbe alle card.
    const tornaHome = () => { window.location.hash = "tablet/home"; };
    return (
      <div style={{ minHeight: "100vh", background: "#faf7f0" }}>
        {/* sticky: OrdiniView scorre da sola all'apertura e la barra finiva
            subito fuori schermo — il ritorno ai reparti deve restare a portata. */}
        <div style={{
          display: "flex", alignItems: "center", gap: 12, padding: "12px 16px",
          background: "linear-gradient(135deg,#6f9180,#4f6d5f)", color: "#fff",
          boxShadow: "0 4px 16px rgba(0,0,0,.18)",
          position: "sticky", top: 0, zIndex: 40,
        }}>
          <button onClick={tornaHome} style={{
            background: "rgba(255,255,255,.18)", border: "none", borderRadius: 10,
            padding: "8px 14px", color: "#fff", fontWeight: 800, fontSize: 14,
            cursor: "pointer", fontFamily: "inherit",
          }}>← Reparti</button>
          <span style={{ fontWeight: 900, fontSize: 16 }}>Ordini</span>
        </div>
        <OrdiniView />
      </div>
    );
  }
  return <TabletView reparto={reparto} onBack={esciGestionale} />;
}
