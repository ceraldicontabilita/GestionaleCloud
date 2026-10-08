// Layout KIOSK (tablet di reparto) — estratto da App.js (fase 2, 24/07/2026).
// Gestisce la sessione operatore (PIN) e instrada al reparto giusto.
// La persona resta identificata mentre passa tra i reparti. Le azioni di
// magazzino chiedono una conferma recente separata, senza chiudere il reparto.
import { TabletView } from "../components/haccp/TabletView";
import TabletHome, { REPARTI_SOLO_ADMIN } from "../components/haccp/TabletHome";
import { VenditaBancoView } from "../components/haccp/VenditaBancoView";
import MagazzinoBarView from "../components/haccp/MagazzinoBarView";
import OrdiniView from "../components/haccp/OrdiniView";
import { clearTabletSession, getTabletSession, moveTabletSessionTo, repartiAmmessi, sessioneTitolareAttiva } from "../utils/tabletSession";
import BarraReparto from "../components/haccp/tablet/BarraReparto";
import ErrorBoundary from "../components/ErrorBoundary";
import RegistriHaccpTablet from "../components/haccp/tablet/RegistriHaccpTablet";

const TITOLI = {
  pasticceria: "Pasticceria", rosticceria: "Rosticceria", bar: "Bar",
  vendita: "Produzioni al banco", magazzino: "Magazzino", lavagna: "Lavagna richieste", ordini: "Ordini",
  haccp: "Registri HACCP",
};

// Ogni reparto: la stessa barra fissa sopra, e un errore di una pagina non
// spegne il tablet (resta la barra per tornare ai reparti).
function ConBarra({ reparto, children }) {
  return (
    <>
      <BarraReparto titolo={TITOLI[reparto] || ""} />
      <ErrorBoundary>{children}</ErrorBoundary>
    </>
  );
}

export default function KioskLayout({ hash }) {
  const reparto = hash.split("/")[1] || "home";

  // Home kiosk — nessuna autenticazione richiesta, solo selezione reparto
  if (reparto === "home") {
    return <TabletHome />;
  }

  // Tutti gli altri reparti richiedono sessione operatore
  let opObj = getTabletSession();

  // Reparti riservati al titolare (Enzo 25/07/2026: «il dipendente deve solo
  // produrre e vedere le ricette»). Il titolare si riconosce dalla sessione
  // del Gestionale (token amministratore) o dalla sua identità sul tablet;
  // chi arriva col link diretto #tablet/ordini senza, torna alle card, che
  // provano la sessione del Gestionale o rimandano al suo login.
  // L'identità del dipendente non si cancella: può continuare negli altri
  // reparti senza reinserire il PIN.
  // Chi non e' il titolare apre solo le card della sua mansione: un indirizzo
  // diretto verso un altro reparto riporta alle sue card.
  const ammessi = repartiAmmessi(opObj);
  if (ammessi && !ammessi.includes(reparto)) {
    return <TabletHome />;
  }

  if (REPARTI_SOLO_ADMIN.includes(reparto) && !ammessi?.includes(reparto)) {
    // Con una persona identificata sul tablet conta la sua identità, non il
    // ruolo salvato nel browser.
    const titolare = opObj ? opObj.ruolo === "amministratore" : sessioneTitolareAttiva();
    if (!titolare) {
      return <TabletHome preselectReparto={reparto} hashRichiesto={hash} />;
    }
  }

  // Il cambio reparto non è un cambio persona: aggiorna soltanto la sezione.
  if (opObj && opObj.reparto && opObj.reparto !== reparto) {
    opObj = moveTabletSessionTo(reparto);
  }

  if (!opObj && !sessioneTitolareAttiva() && !REPARTI_SOLO_ADMIN.includes(reparto)) {
    // Nessuna sessione (o reparto diverso) → home con reparto pre-selezionato
    return <TabletHome preselectReparto={reparto} hashRichiesto={hash} />;
  }

  const esciGestionale = () => {
    clearTabletSession();
    window.location.hash = "dashboard";
    window.location.reload();
  };
  const tornaReparti = () => { window.location.hash = "tablet/home"; };

  if (reparto === "vendita") return <ConBarra reparto={reparto}><VenditaBancoView onBack={tornaReparti} /></ConBarra>;
  if (reparto === "haccp") return <ConBarra reparto={reparto}><RegistriHaccpTablet /></ConBarra>;
  if (reparto === "magazzino") return <ConBarra reparto={reparto}><MagazzinoBarView onBack={tornaReparti} /></ConBarra>;
  // Card portate nel kiosk il 25/07/2026 (il gestionale è ora solo del
  // titolare): la Lavagna delle richieste e gli Ordini ai fornitori.
  if (reparto === "lavagna") return <ConBarra reparto={reparto}><MagazzinoBarView onBack={tornaReparti} soloLavagna /></ConBarra>;
  if (reparto === "ordini") {
    // OrdiniView è nata nel gestionale e non ha un "indietro": la barra fissa
    // del reparto glielo dà (sticky, resta a portata anche scorrendo).
    return (
      <ConBarra reparto={reparto}>
        <div style={{ minHeight: "100vh", background: "#faf7f0" }}>
          <OrdiniView />
        </div>
      </ConBarra>
    );
  }
  // key: cambiando reparto il cruscotto riparte da capo, senza stato vecchio.
  return <ConBarra reparto={reparto}><TabletView key={reparto} reparto={reparto} onBack={esciGestionale} /></ConBarra>;
}
