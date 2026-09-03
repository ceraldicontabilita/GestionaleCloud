// Normalizza testo per la ricerca: minuscolo, senza accenti, solo alfanumerico.
// Cosi' "caffe" (query senza accento) trova "Caffe' Kimbo" nei filtri lato client.
export const norm = (s) =>
  String(s || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(new RegExp("[\\u0300-\\u036f]", "g"), "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
