import { preparaImportFotoRicette } from "../components/haccp/backoffice/pianoImportFotoRicette";

const manifest = [
  { ricetta_id: "a", nome: "Amaretti", file: "Amaretti.png" },
  { ricetta_id: "b", nome: "Baba", file: "Baba.png" },
  { ricetta_id: "c", nome: "Ricetta eliminata", file: "Eliminata.png" },
  { ricetta_id: "d", nome: "Nome vecchio", file: "Vecchio.png" },
];
const immagini = [
  { name: "Amaretti.png" }, { name: "Baba.png" },
  { name: "Eliminata.png" }, { name: "Vecchio.png" },
];

test("associa solo ID vivi invariati e non sovrascrive Storage", () => {
  const risultato = preparaImportFotoRicette(
    { images: manifest },
    immagini,
    [
      { id: "a", nome: "Amaretti", foto_drive_id: "vecchio" },
      { id: "b", nome: "Baba", foto_storage_path: "lotti/ricette/b.png" },
      { id: "d", nome: "Nome nuovo", foto_drive_id: "vecchio" },
    ],
  );
  expect(risultato.piano.map(x => x.id)).toEqual(["a"]);
  expect(risultato.giaCanoniche).toBe(1);
  expect(risultato.eliminate).toBe(1);
  expect(risultato.conflitti).toHaveLength(1);
});

test("rifiuta identità duplicate, senza inventare un abbinamento", () => {
  expect(() => preparaImportFotoRicette(
    [...manifest, { ricetta_id: "a", nome: "Altra", file: "Altra.png" }],
    immagini,
    [],
  )).toThrow("duplicate");
});

test("un'immagine mancante resta esplicita", () => {
  const r = preparaImportFotoRicette(
    [manifest[0]],
    [],
    [{ id: "a", nome: "Amaretti" }],
  );
  expect(r.piano).toHaveLength(0);
  expect(r.mancanti).toEqual([{ id: "a", nome: "Amaretti", file: "Amaretti.png" }]);
});
