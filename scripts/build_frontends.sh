#!/usr/bin/env bash
# Compila il frontend del gestionale e quelli delle app portate pari pari
# (frontend_lotti, frontend_menu, frontend_hr, ...): ogni cartella
# frontend_*/ con un package.json viene installata e compilata con la propria
# toolchain (CRA o Vite). Cartelle assenti vengono saltate, cosi' il comando di
# build su Render resta lo stesso mentre le app entrano una alla volta.
#
# Render (dashboard -> Settings -> Build Command):
#   pip install -r backend/requirements.txt && bash scripts/build_frontends.sh
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== frontend (gestionale)"
npm --prefix frontend install --include=dev --legacy-peer-deps
npm --prefix frontend run build

for dir in frontend_*/; do
  dir="${dir%/}"
  [ -f "$dir/package.json" ] || continue
  echo "== $dir"
  if [ -f "$dir/package-lock.json" ]; then
    npm --prefix "$dir" ci --legacy-peer-deps
  else
    npm --prefix "$dir" install --legacy-peer-deps
  fi
  # CI=false: le build CRA non devono fallire per i warning ESLint (stessa
  # scelta della CI originale di Lotti); per Vite la variabile e' innocua.
  CI=false npm --prefix "$dir" run build
done
