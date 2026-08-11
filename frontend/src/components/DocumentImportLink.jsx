import React from 'react';

/**
 * Compatibilita temporanea per i vecchi punti di ingresso documentali.
 *
 * Regola applicativa: l'utente acquisisce file esclusivamente da
 * Documenti > Carica documenti. Le pagine specialistiche non devono piu
 * mostrare scorciatoie "Importa" che duplicano il punto unico di ingresso.
 *
 * Il componente resta per non obbligare una rimozione atomica di tutti i
 * riferimenti legacy: durante il consolidamento rende intenzionalmente nulla.
 * I riferimenti residui vengono eliminati pagina per pagina dall'audit.
 */
export default function DocumentImportLink() {
  return null;
}
