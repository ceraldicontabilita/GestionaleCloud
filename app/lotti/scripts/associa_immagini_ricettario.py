"""Associa in modo conservativo immagini locali alle ricette di Lotti.

Esegue prima una simulazione. Con ``--apply`` scarica un backup JSON dei
collegamenti, carica solo immagini con corrispondenza forte e lascia intatte le
foto manuali già presenti. Il PIN arriva esclusivamente da ``LOTTI_ADMIN_PIN``.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import unicodedata

import requests


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".jfif", ".avif", ".gif"}
EXTENSION_PRIORITY = {".webp": 0, ".jpg": 1, ".jpeg": 2, ".png": 3, ".avif": 4, ".jfif": 5, ".gif": 6}
STOPWORDS = {"di", "del", "della", "delle", "dei", "degli", "al", "alla", "alle", "ai", "agli", "con", "e"}
ALIASES = {
    "codina": "coda",
    "sfogliata": "sfogliatella",
    "rostatina": "crostatina",
    "profitterol": "profiterole",
    "ciccolato": "cioccolato",
    "fragole": "fragola",
    "fragoline": "fragola",
    "piccolo": "mignon",
    "baba": "baba",
    "rhum": "rum",
}
GUSTI_DISTINTIVI = {
    "cioccolato", "pistacchio", "fragola", "limone", "nocciola", "amarena",
    "albicocca", "nutella", "caramello", "mandorla",
}


def normalizza_nome(value: str) -> str:
    text = value or ""
    # Gli import Excel aggiungono annotazioni gestionali che non fanno parte
    # del nome commerciale della ricetta. Vanno ignorate per cercare la foto,
    # mantenendo invece il nome specifico della variante. Esempio:
    # "Sfogliatella riccia (variante di: sfogliatella frolla)" deve cercare
    # "sfogliatella riccia", mai la foto generica della frolla.
    text = re.sub(
        r"\s*\((?:base|variante\s+di\s*:[^)]*|lievitazione\s+ritardata)\)\s*",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    text = re.sub(r"\.(?:jpg|jpeg|png|webp|jfif|avif|gif)$", "", text)
    text = re.sub(r"(?<=\D)\d+$", "", text.strip())
    tokens = re.findall(r"[a-z0-9]+", text)
    tokens = [ALIASES.get(token, token) for token in tokens]
    return " ".join(tokens)


def token_significativi(value: str) -> set[str]:
    return {token for token in normalizza_nome(value).split() if token not in STOPWORDS and len(token) > 1}


@dataclass(frozen=True)
class Immagine:
    path: Path
    nome_norm: str
    tokens: frozenset[str]
    sha256: str
    size: int = 0


def indicizza_immagini(directory: Path) -> list[Immagine]:
    immagini = []
    viste = set()
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix.casefold() not in IMAGE_EXTENSIONS:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        chiave = (normalizza_nome(path.stem), digest)
        if chiave in viste:
            continue
        viste.add(chiave)
        immagini.append(Immagine(
            path, normalizza_nome(path.stem), frozenset(token_significativi(path.stem)),
            digest, path.stat().st_size,
        ))
    return immagini


def punteggio_associazione(nome_ricetta: str, immagine: Immagine) -> float:
    ricetta_norm = normalizza_nome(nome_ricetta)
    ricetta_tokens = token_significativi(nome_ricetta)
    if not ricetta_tokens or not immagine.tokens:
        return 0.0
    if ricetta_norm == immagine.nome_norm:
        return 1.0
    # Un'immagine generica della base non deve diventare automaticamente la
    # foto di una variante: ogni parola distintiva della ricetta deve esserci.
    if not ricetta_tokens.issubset(immagine.tokens):
        mancanti = ricetta_tokens - immagine.tokens
        gusti_comuni = (ricetta_tokens & immagine.tokens) & GUSTI_DISTINTIVI
        # "Babà panna e pistacchio" può essere archiviato come "babà al
        # pistacchio": manca solo la farcitura generica, ma gusto e prodotto
        # coincidono. Non estendere questa tolleranza ad altre parole.
        if not (gusti_comuni and mancanti.issubset({"panna", "crema"})):
            return 0.0
        return 0.94
    extra = immagine.tokens - ricetta_tokens
    if extra and not extra.issubset({"foto", "ricetta", "prodotto", "ceraldi", "classico"}):
        return 0.0
    if ricetta_tokens == immagine.tokens:
        return 0.99
    if extra:
        return 0.96
    return SequenceMatcher(None, ricetta_norm, immagine.nome_norm).ratio()


def scegli_immagine(nome_ricetta: str, immagini: list[Immagine]):
    candidati = [(punteggio_associazione(nome_ricetta, image), image) for image in immagini]
    candidati = [(score, image) for score, image in candidati if score >= 0.90]
    if not candidati:
        return None, "nessuna corrispondenza forte"
    candidati.sort(key=lambda item: (
        -item[0], EXTENSION_PRIORITY.get(item[1].path.suffix.casefold(), 99), -item[1].size
    ))
    migliore = candidati[0]
    alternative = [item for item in candidati[1:] if item[0] == migliore[0] and item[1].nome_norm != migliore[1].nome_norm]
    if alternative:
        return None, "più immagini equivalenti da verificare"
    return migliore[1], "nome esatto" if migliore[0] == 1 else f"nome compatibile {migliore[0]:.2f}"


class LottiClient:
    def __init__(self, api: str, pin: str, operator_name: str):
        self.api = api.rstrip("/")
        self.session = requests.Session()
        login = self.session.post(f"{self.api}/auth/login", json={"pin": pin}, timeout=30)
        login.raise_for_status()
        payload = login.json()
        if payload.get("scelta_operatore"):
            operators = payload.get("operatori") or []
            selected = next((op for op in operators if operator_name.casefold() in (op.get("nome") or "").casefold()), None)
            selected = selected or next((op for op in operators if op.get("ruolo") == "amministratore"), None)
            if not selected:
                raise RuntimeError("Nessun amministratore associato al PIN")
            login = self.session.post(
                f"{self.api}/auth/login",
                json={"pin": pin, "operatore_id": selected["id"]},
                timeout=30,
            )
            login.raise_for_status()
            payload = login.json()
        self.session.headers["Authorization"] = f"Bearer {payload['token']}"

    def get_json(self, path: str):
        response = self.session.get(f"{self.api}{path}", timeout=60)
        response.raise_for_status()
        return response.json()

    def post_json(self, path: str):
        response = self.session.post(f"{self.api}{path}", timeout=120)
        response.raise_for_status()
        return response.json()

    def backup(self, destination: Path) -> Path:
        response = self.session.get(f"{self.api}/backup/export-json", timeout=180)
        response.raise_for_status()
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / f"ricette_prima_foto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path.write_bytes(response.content)
        return path

    def upload(self, recipe_id: str, image: Immagine):
        mime = mimetypes.guess_type(image.path.name)[0] or "image/jpeg"
        with image.path.open("rb") as stream:
            response = self.session.post(
                f"{self.api}/ricette/{recipe_id}/upload-foto",
                files={"file": (image.path.name, stream, mime)},
                timeout=180,
            )
        response.raise_for_status()
        return response.json()


def costruisci_piano(recipes: list[dict], images: list[Immagine]) -> dict:
    matches, skipped, unresolved = [], [], []
    for recipe in sorted(recipes, key=lambda item: (item.get("reparto") or "", item.get("nome") or "")):
        if recipe.get("foto_url"):
            skipped.append({"id": recipe.get("id"), "nome": recipe.get("nome"), "motivo": "foto già presente"})
            continue
        image, reason = scegli_immagine(recipe.get("nome") or "", images)
        if image:
            matches.append({
                "id": recipe["id"], "nome": recipe.get("nome"), "reparto": recipe.get("reparto"),
                "file": str(image.path), "motivo": reason,
            })
        else:
            unresolved.append({"id": recipe.get("id"), "nome": recipe.get("nome"), "reparto": recipe.get("reparto"), "motivo": reason})
    return {"associazioni": matches, "gia_con_foto": skipped, "non_associate": unresolved}


def applica_mappature_esplicite(
    piano: dict,
    recipes: list[dict],
    images: list[Immagine],
    mapping_file: Path | None,
) -> dict:
    """Integra il piano con associazioni manualmente verificate e tracciabili.

    Il file e' una lista di oggetti con ``id`` e ``file``. Il percorso deve
    appartenere all'indice appena costruito e la ricetta deve esistere e non
    avere gia' una foto. In questo modo una mappatura obsoleta non puo'
    sovrascrivere una modifica fatta dall'utente nell'applicazione.
    """
    if not mapping_file:
        return piano

    mappings = json.loads(mapping_file.read_text(encoding="utf-8"))
    if not isinstance(mappings, list):
        raise ValueError("Il file di mappatura deve contenere una lista JSON")

    recipes_by_id = {str(recipe.get("id")): recipe for recipe in recipes}
    images_by_path = {str(image.path.resolve()).casefold(): image for image in images}
    matches_by_id = {str(match["id"]): match for match in piano["associazioni"]}
    unresolved_by_id = {str(item["id"]): item for item in piano["non_associate"]}
    explicit_ids = set()

    for mapping in mappings:
        recipe_id = str(mapping.get("id") or "")
        if not recipe_id or recipe_id in explicit_ids:
            raise ValueError(f"ID ricetta mancante o duplicato nella mappatura: {recipe_id!r}")
        explicit_ids.add(recipe_id)
        recipe = recipes_by_id.get(recipe_id)
        if not recipe:
            raise ValueError(f"Ricetta inesistente nella mappatura: {recipe_id}")
        if recipe.get("foto_url"):
            continue

        requested_path = Path(str(mapping.get("file") or "")).resolve()
        image = images_by_path.get(str(requested_path).casefold())
        if not image:
            raise ValueError(f"Immagine non presente nella cartella indicizzata: {requested_path}")

        matches_by_id[recipe_id] = {
            "id": recipe_id,
            "nome": recipe.get("nome"),
            "reparto": recipe.get("reparto"),
            "file": str(image.path),
            "motivo": mapping.get("motivo") or "mappatura esplicita verificata",
        }
        unresolved_by_id.pop(recipe_id, None)

    piano["associazioni"] = sorted(
        matches_by_id.values(), key=lambda item: (item.get("reparto") or "", item.get("nome") or "")
    )
    piano["non_associate"] = sorted(
        unresolved_by_id.values(), key=lambda item: (item.get("reparto") or "", item.get("nome") or "")
    )
    return piano


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="https://lotti-backend-f2fg.onrender.com/api")
    parser.add_argument("--images-dir", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, default=Path("backup_ricette"))
    parser.add_argument("--operator-name", default="Vincenzo")
    parser.add_argument("--mapping-file", type=Path)
    parser.add_argument(
        "--apply-departments",
        action="store_true",
        help="Applica anche la riclassificazione dei reparti (mai implicita)",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    pin = os.environ.get("LOTTI_ADMIN_PIN", "")
    if not pin:
        raise SystemExit("Imposta LOTTI_ADMIN_PIN nell'ambiente")
    images = indicizza_immagini(args.images_dir)
    client = LottiClient(args.api, pin, args.operator_name)
    recipes = client.get_json("/ricette")
    plan = applica_mappature_esplicite(
        costruisci_piano(recipes, images), recipes, images, args.mapping_file
    )
    report = {
        "modalita": "applica" if args.apply else "anteprima",
        "immagini_valide": len(images),
        "ricette": len(recipes),
        **plan,
    }

    if args.apply:
        report["backup"] = str(client.backup(args.backup_dir))
        uploads = []
        image_by_path = {str(image.path): image for image in images}
        for match in plan["associazioni"]:
            result = client.upload(match["id"], image_by_path[match["file"]])
            uploads.append({**match, "foto_url": result.get("foto_url")})
        report["caricate"] = uploads
        report["varianti_separate"] = client.post_json("/ricette/separa-foto-varianti?applica=true")
        if args.apply_departments:
            category_plan = client.post_json("/ricette/auto-assegna-reparti?applica=false")
            report["reparti_anteprima"] = category_plan
            if category_plan.get("spostate"):
                report["reparti_applicati"] = client.post_json("/ricette/auto-assegna-reparti?applica=true")

    args.backup_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.backup_dir / f"report_associazione_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "modalita": report["modalita"],
        "immagini_valide": len(images),
        "associazioni": len(plan["associazioni"]),
        "gia_con_foto": len(plan["gia_con_foto"]),
        "non_associate": len(plan["non_associate"]),
        "report": str(report_path),
        "backup": report.get("backup"),
        "varianti_separate": (report.get("varianti_separate") or {}).get("aggiornate", 0),
        "reparti_spostati": (report.get("reparti_applicati") or {}).get("aggiornate", 0),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
