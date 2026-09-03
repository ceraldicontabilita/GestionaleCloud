#!/usr/bin/env bash
# Compila il frontend del gestionale e quelli delle app portate pari pari
# (frontend_lotti, frontend_menu, frontend_hr, ...): ogni cartella
# frontend_*/ con un package.json viene installata e compilata con la propria
# toolchain (CRA o Vite). Cartelle assenti vengono saltate.
#
# Uso:
#   bash scripts/build_frontends.sh          # tutto: gestionale + app
#   bash scripts/build_frontends.sh --apps   # solo le app frontend_*/
#
# Su Render il Build Command del servizio (impostato in dashboard, che NON
# recepisce render.yaml) e' rimasto:
#   pip install -r backend/requirements.txt &&
#   npm --prefix frontend install --include=dev --legacy-peer-deps &&
#   npm --prefix frontend run build
# Per questo `npm --prefix frontend run build` (frontend/package.json)
# richiama questo script con --apps dopo `vite build`: le app vengono
# compilate senza toccare la dashboard.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ "${1:-}" != "--apps" ]; then
  echo "== frontend (gestionale)"
  npm --prefix frontend install --include=dev --legacy-peer-deps
  npm --prefix frontend run build
fi

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
