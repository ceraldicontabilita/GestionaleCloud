export function testoOrdineFornitore(ordine, righe) {
  const fornitore = righe[0]?.fornitore || ordine.fornitore || "Fornitore";
  const prodotti = righe.map((r) => `- ${r.nome}: ${r.quantita} ${r.unita || "pz"}`);
  return [`Buongiorno ${fornitore},`, "", "Confermiamo il seguente ordine:", ...prodotti,
    "", `Riferimento: ORD-${String(ordine.id || "").slice(0, 8).toUpperCase()}`,
    "Grazie, Ceraldi Group"].join("\n");
}

export function linkEmailOrdine(destinatario, ordine, righe) {
  const email = String(destinatario || "").trim();
  if (!email || !email.includes("@")) throw new Error("Inserisci l'email del fornitore");
  const oggetto = `Ordine Ceraldi Group ORD-${String(ordine.id || "").slice(0, 8).toUpperCase()}`;
  return `mailto:${email}?subject=${encodeURIComponent(oggetto)}&body=${encodeURIComponent(testoOrdineFornitore(ordine, righe))}`;
}

export function linkWhatsAppOrdine(destinatario, ordine, righe) {
  let numero = String(destinatario || "").replace(/\D/g, "");
  if (numero.startsWith("00")) numero = numero.slice(2);
  if (numero.length === 10) numero = `39${numero}`;
  if (numero.length < 11) throw new Error("Inserisci il cellulare WhatsApp del fornitore");
  return `https://wa.me/${numero}?text=${encodeURIComponent(testoOrdineFornitore(ordine, righe))}`;
}
