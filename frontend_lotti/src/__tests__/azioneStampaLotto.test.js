const { testoAzioneRegistrazione } = require("../components/haccp/tablet/ModalRegistraLotto");

const base = {
  loading: false,
  stepRegistrazione: "base",
  bloccatoDaGiacenza: false,
  bloccatoDaPosizioneMancante: false,
  haComponenti: false,
  stampare: true,
};

describe("azione principale del modale lotto", () => {
  test("mostra la stampa senza confonderla con frigo o congelatore", () => {
    expect(testoAzioneRegistrazione(base)).toBe("🖨️ Stampa etichetta");
  });

  test("distingue la registrazione senza stampa", () => {
    expect(testoAzioneRegistrazione({ ...base, stampare: false })).toBe("Registra senza stampare");
  });

  test("prima dei componenti mostra avanti", () => {
    expect(testoAzioneRegistrazione({ ...base, haComponenti: true })).toBe("Avanti →");
  });
});
