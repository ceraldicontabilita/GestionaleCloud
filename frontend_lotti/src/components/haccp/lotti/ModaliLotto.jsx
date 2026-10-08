import { Printer, FileText } from "lucide-react";
import { API } from "../../../utils/constants";
import { stampaDoc } from "../../../utils/stampa";
import { Modal, Button, Input } from "./uiLotti";

// I due modali "di servizio" della pagina Lotti — estratti 1:1 da
// LottiList.jsx (refactor 25/07/2026): Report HACCP mensile e Registro ASL.
// Stato e handler restano nel genitore.
// 25/07/2026 — rimosso "Genera nuovo lotto": il lotto nasce SEMPRE dalla
// produzione di una ricetta (tablet / registra produzione), che scarica gli
// ingredienti e ne eredita la tracciabilità. Crearlo a mano da qui generava un
// lotto senza provenienza; il bottone era già stato tolto dalla pagina e la
// finestra restava irraggiungibile (decisione Enzo 25/07/2026).

export function ModalReportHACCP({ isOpen, onClose, anno, setAnno, mese, setMese }) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Report HACCP Mensile PDF">
      <div className="space-y-4">
        <p className="text-sm text-gray-600">
          Genera un report PDF consolidato di tutte le attività HACCP del mese selezionato.
        </p>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm font-medium text-gray-700">Anno</label>
            <input type="number" value={anno} onChange={(e) => setAnno(parseInt(e.target.value))}
              min="2023" max="2030" className="w-full px-4 py-2.5 border border-gray-200 rounded-lg mt-1" />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">Mese</label>
            <select value={mese} onChange={(e) => setMese(parseInt(e.target.value))}
              className="w-full px-4 py-2.5 border border-gray-200 rounded-lg mt-1">
              {["Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno","Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"].map((m, i) => (
                <option key={i + 1} value={i + 1}>{m}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="p-3 bg-[#f2f6f3] border border-[#cfdfd5] rounded-lg text-sm">
          <p className="font-semibold text-[#3f5a4e] mb-1">Il report include:</p>
          <ul className="text-[#5b7a6b] space-y-1 text-xs">
            <li>• Temperature positive e negative (frigo e congelatori)</li>
            <li>• Piano di sanificazione eseguito</li>
            <li>• Anomalie e non conformità registrate</li>
            <li>• Lotti di produzione del mese</li>
            <li>• Spazio firme Responsabile HACCP e Titolare</li>
          </ul>
        </div>
        <div className="flex gap-3">
          <Button variant="secondary" onClick={onClose} className="flex-1">Annulla</Button>
          <Button onClick={() => {
            stampaDoc({
              categoria: "manuale",
              url: `${API}/report-haccp/mensile?anno=${anno}&mese=${mese}`,
              formato: "html",
              titolo: `Report HACCP ${mese}/${anno}`,
            }).catch(() => {});
            onClose();
          }} className="flex-1">
            <FileText size={18} /> Genera PDF
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export function ModalRegistroASL({
  isOpen, onClose, dataInizio, setDataInizio, dataFine, setDataFine,
  onStampaRegistro, onTracciabilitaCompleta,
}) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Stampa Registro Lotti per ASL">
      <div className="space-y-4">
        <p className="text-sm text-gray-600">
          Genera un registro di tracciabilità lotti conforme ai requisiti ASL (Reg. CE 178/2002).
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Input label="Data Inizio" type="date" value={dataInizio} onChange={(e) => setDataInizio(e.target.value)} />
          <Input label="Data Fine" type="date" value={dataFine} onChange={(e) => setDataFine(e.target.value)} />
        </div>
        <div className="flex flex-col gap-2">
          <Button onClick={onStampaRegistro} className="w-full justify-center">
            <Printer size={18} /> Registro Lotti PDF
          </Button>
          <Button onClick={onTracciabilitaCompleta} variant="secondary" className="w-full justify-center">
            <FileText size={18} /> Tracciabilità Completa
          </Button>
          <Button variant="secondary" onClick={onClose} className="w-full justify-center">
            Annulla
          </Button>
        </div>
      </div>
    </Modal>
  );
}
