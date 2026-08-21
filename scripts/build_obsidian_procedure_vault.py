"""Build a safe, reproducible Obsidian Procedure vault from tracked docs."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path


def _tracked_markdown(repo_root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "docs"], cwd=repo_root, check=True,
        capture_output=True, text=True, encoding="utf-8",
    )
    return sorted(
        Path(line) for line in result.stdout.splitlines()
        if line.strip().lower().endswith(".md")
    )


def _status(content: str) -> str:
    for line in content.splitlines()[:12]:
        if line.strip().startswith("status:"):
            return line.split(":", 1)[1].strip()
    return "unclassified"


def build_vault(repo_root: Path, output_dir: Path, zip_path: Path) -> dict[str, object]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"output non vuoto: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / ".obsidian").mkdir()
    (output_dir / ".obsidian" / "app.json").write_text(
        json.dumps({"attachmentFolderPath": "Allegati"}, indent=2) + "\n",
        encoding="utf-8",
    )

    entries: list[dict[str, str]] = []
    index_lines = [
        "# GestionaleCloud — Procedure", "",
        "> Proiezione ricostruibile dei documenti pubblici del repository. ",
        "> Non contiene originali fiscali, bancari o del personale.", "",
    ]
    for relative in _tracked_markdown(repo_root):
        content = (repo_root / relative).read_text(encoding="utf-8")
        target_relative = relative.relative_to("docs")
        target = output_dir / target_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        status = _status(content)
        entries.append({"path": target_relative.as_posix(), "sha256": digest, "status": status})
        link = target_relative.with_suffix("").as_posix()
        index_lines.append(f"- [[{link}]] — `{status}`")

    (output_dir / "00-INDICE.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "source": "ceraldicontabilita/GestionaleCloud:docs",
        "files": entries,
        "excluded": [
            "documenti originali", "cedolini completi", "estratti conto",
            "PEC complete", "password, token e credenziali",
        ],
    }
    (output_dir / "MANIFEST_SHA256.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(p for p in output_dir.rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(path.relative_to(output_dir).as_posix(), (1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
        if archive.testzip() is not None:
            raise RuntimeError("ZIP Obsidian non valido")
    return {"documents": len(entries), "zip": str(zip_path), "manifest": manifest}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip", dest="zip_path", type=Path, required=True)
    args = parser.parse_args()
    result = build_vault(args.repo_root.resolve(), args.output_dir.resolve(), args.zip_path.resolve())
    print(json.dumps({"documents": result["documents"], "zip": result["zip"]}))


if __name__ == "__main__":
    main()
