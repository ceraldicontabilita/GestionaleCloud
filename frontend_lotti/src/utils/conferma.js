// Conferma UNICA e coerente per tutta l'app (prima: alcune pagine usavano il
// popup grezzo del browser window.confirm, brutto e non controllabile su
// Android; Lotti usava un modale custom tutto suo). Ora una sola funzione:
//
//   import { conferma } from "../../utils/conferma";
//   if (await conferma("Eliminare il lotto?", { pericolo: true })) { ... }
//
// Il modale vero è renderizzato una sola volta da <ConfermaHost/> in App.js.
// Se per qualsiasi motivo l'host non è montato, si ricade su window.confirm
// così una conferma non va mai persa.

let _handler = null;

export function _registraConfermaHandler(fn) {
  _handler = fn;
}

export function conferma(messaggio, opzioni = {}) {
  if (typeof _handler === "function") {
    return _handler({
      messaggio,
      titolo: opzioni.titolo || "Conferma",
      ok: opzioni.ok || "Conferma",
      annulla: opzioni.annulla || "Annulla",
      pericolo: !!opzioni.pericolo,
    });
  }
  // fallback: comportamento di prima, mai perso
  return Promise.resolve(window.confirm(messaggio));
}

// Dialogo di INSERIMENTO TESTO coerente (sostituisce window.prompt).
// Ritorna la stringa inserita, o null se l'utente annulla.
//   const motivo = await chiediTesto("Motivo del richiamo:", { titolo: "Richiamo lotto" });
export function chiediTesto(messaggio, opzioni = {}) {
  if (typeof _handler === "function") {
    return _handler({
      messaggio,
      titolo: opzioni.titolo || "Inserisci",
      ok: opzioni.ok || "Conferma",
      annulla: opzioni.annulla || "Annulla",
      pericolo: !!opzioni.pericolo,
      input: true,
      valore: opzioni.valore || "",
      placeholder: opzioni.placeholder || "",
    });
  }
  return Promise.resolve(window.prompt(messaggio, opzioni.valore || ""));
}
