// La mappa è uno snapshot: solo l'ID operativo e il nome ancora invariato
// autorizzano l'associazione. Nessuna ricerca fuzzy o ricreazione dal cestino.
export function preparaImportFotoRicette(manifest, fileList, ricette) {
  const righe = Array.isArray(manifest) ? manifest : manifest?.images;
  if (!Array.isArray(righe) || !righe.length) {
    throw new Error("La mappa immagini non contiene ricette");
  }
  const perId = new Map();
  for (const ricetta of ricette || []) {
    if (ricetta?.id) perId.set(String(ricetta.id), ricetta);
  }
  const filePerNome = new Map();
  for (const file of Array.from(fileList || [])) {
    if (!file?.name?.toLowerCase().endsWith(".png")) continue;
    if (filePerNome.has(file.name)) {
      throw new Error(`Due immagini hanno lo stesso nome: ${file.name}`);
    }
    filePerNome.set(file.name, file);
  }
  const ids = new Set();
  const nomiFile = new Set();
  const piano = [];
  const conflitti = [];
  const mancanti = [];
  let eliminate = 0;
  let giaCanoniche = 0;
  for (const riga of righe) {
    const id = String(riga?.ricetta_id || riga?.id || "").trim();
    const nome = String(riga?.nome || "").trim();
    const file = String(riga?.file || "").trim();
    if (!id || !nome || !file || ids.has(id) || nomiFile.has(file)) {
      throw new Error("La mappa contiene righe incomplete o duplicate");
    }
    ids.add(id);
    nomiFile.add(file);
    const ricetta = perId.get(id);
    if (!ricetta) { eliminate += 1; continue; }
    if (String(ricetta.nome || "").trim() !== nome) {
      conflitti.push({ id, nomeMappa: nome, nomeAttuale: ricetta.nome });
      continue;
    }
    if (ricetta.foto_storage_path) { giaCanoniche += 1; continue; }
    const immagine = filePerNome.get(file);
    if (!immagine) { mancanti.push({ id, nome, file }); continue; }
    piano.push({ id, nome, file, immagine });
  }
  return { piano, conflitti, mancanti, eliminate, giaCanoniche, righe: righe.length };
}
