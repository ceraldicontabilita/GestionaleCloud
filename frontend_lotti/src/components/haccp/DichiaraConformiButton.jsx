import { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { CheckCheck } from "lucide-react";
import Button from "../ui/Button";
import { API } from "../../utils/constants";
import { apiError } from "../../utils/apiError";

/**
 * Il responsabile, finito il giro, dichiara conformi le caselle di oggi ancora
 * aperte su frigoriferi e congelatori. Firma chi tocca il pulsante, all'ora in
 * cui lo tocca: il sistema non lo fa piu' da solo alle 07:00.
 */
export default function DichiaraConformiButton({ onFatto }) {
  const [invio, setInvio] = useState(false);
  const dichiara = async () => {
    if (!window.confirm("Confermi di aver controllato ora frigoriferi e congelatori e che sono entro soglia?")) return;
    setInvio(true);
    try {
      const res = await axios.post(`${API}/haccp-auto/dichiara-conformi-oggi`);
      toast.success(`${res.data.dichiarate} apparecchi dichiarati conformi da ${res.data.firmato_da}`);
      onFatto?.();
    } catch (err) {
      toast.error(apiError(err, "Dichiarazione non registrata"));
    }
    setInvio(false);
  };
  return (
    <Button onClick={dichiara} disabled={invio} variant="secondary" size="sm" data-testid="dichiara-conformi-btn">
      <CheckCheck size={16} /> Giro fatto: tutto conforme
    </Button>
  );
}
