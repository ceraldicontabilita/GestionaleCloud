import React from "react";
import { LockKeyhole, Delete, X } from "lucide-react";
import axios from "axios";
import { apiError } from "../../../utils/apiError";
import { API } from "../../../utils/constants";
import { saveToken, saveRuolo, saveOperatoreNome } from "@/auth";
import { createPinModal } from "../../../../../frontend_shared/PinModal";

const PinModal = createPinModal(React, { LockKeyhole, Delete, X });

export default function PinKeypad({
  titolo, sottotitolo, colore = "#5b7a6b", onSuccess, onCancel,
}) {
  const verify = async (pin) => {
    let data;
    try {
      const response = await axios.post(`${API}/tablet-operatori/login`, { pin });
      data = response.data;
    } catch (error) {
      throw new Error(apiError(error, "PIN non riconosciuto"));
    }
    const op = data?.operatore;
    if (!data?.token || !op) throw new Error("Risposta di accesso non valida");
    saveToken(data.token);
    saveRuolo(op.ruolo || "operatore");
    saveOperatoreNome(op.nome || "");
    onSuccess(op);
  };
  return <PinModal title={titolo} subtitle={sottotitolo} color={colore}
    onVerify={verify} onCancel={onCancel} />;
}
