import json
import subprocess
import zipfile
from pathlib import Path

from scripts.build_obsidian_procedure_vault import build_vault


def test_build_vault_exports_only_tracked_docs_and_manifest(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "docs").mkdir()
    (repo / "docs" / "CURRENT.md").write_text(
        "<!-- gestionalecloud-doc\nstatus: current\n-->\n# Corrente\n", encoding="utf-8"
    )
    (repo / "docs" / "segreto.txt").write_text("non esportare", encoding="utf-8")
    subprocess.run(["git", "add", "docs/CURRENT.md", "docs/segreto.txt"], cwd=repo, check=True)

    output = tmp_path / "vault"
    archive = tmp_path / "vault.zip"
    result = build_vault(repo, output, archive)

    assert result["documents"] == 1
    assert (output / "CURRENT.md").exists()
    assert not (output / "segreto.txt").exists()
    manifest = json.loads((output / "MANIFEST_SHA256.json").read_text(encoding="utf-8"))
    assert manifest["files"][0]["status"] == "current"
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        assert "00-INDICE.md" in bundle.namelist()
