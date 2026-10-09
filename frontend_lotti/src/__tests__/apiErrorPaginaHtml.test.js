const { apiError } = require("../utils/apiError");

// Durante un riavvio il proxy di Render risponde con una pagina HTML: nella
// scheda ricetta compariva «<!DOCTYPE html>…» al posto di un messaggio.
test("una pagina HTML di errore diventa una frase leggibile", () => {
  const pagina = '<!DOCTYPE html> <html lang="en"> <head> <meta charset="utf-8"> </head></html>';
  expect(apiError({ response: { status: 502, data: pagina } })).toBe("Il server si sta riavviando: riprova tra un minuto.");
  expect(apiError({ response: { status: 404, data: pagina } })).toBe("Il server ha risposto con una pagina invece che con dei dati: riprova.");
});

test("il detail del backend resta il messaggio", () => {
  expect(apiError({ response: { status: 400, data: { detail: "La ricetta non ha ingredienti con dosi" } } }))
    .toBe("La ricetta non ha ingredienti con dosi");
});
