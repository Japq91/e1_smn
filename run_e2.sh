#!/usr/bin/env bash
# Orquestador del Entregable 2 (climatología, sesgos, diagrama de
# Taylor, Índices C/E -- ver informe/informe_e1_smnv3.tex, sección
# "Entregable 2: próximos pasos"). Mismo criterio que run.sh (E1):
# único punto de entrada, pasos numerados, log propio.
#
# Uso: ./run_e2.sh [STEP_FROM] [STEP_TO]
#
# Este script NO descarga ni reprocesa nada de CMIP6/ERSSTv5 -- lee
# únicamente lo que el Entregable 1 ya dejó en data/processed/
# (ver scripts_e2/README.md para el contrato de entrada exacto).
# Si esos archivos no existen todavía, corré primero ./run.sh (E1).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

INVENTORY_FILE="data/processed/models_inventory_final.csv"
MASKED_DIR="data/processed/masked"

if [ ! -f "$INVENTORY_FILE" ]; then
    echo "Falta $INVENTORY_FILE -- corré ./run.sh (Entregable 1) primero." >&2
    exit 1
fi

STEP_ORDER=()  # todavía sin pasos: se agregan a medida que se definan
STEP_FROM="${1:-00}"
STEP_TO="${2:-99}"

mkdir -p logs
echo "== run_e2.sh: $(date '+%Y-%m-%d %H:%M:%S') ==" | tee -a logs/pipeline_e2.log

if [ "${#STEP_ORDER[@]}" -eq 0 ]; then
    echo "Todavía no hay pasos definidos en scripts_e2/ -- agregalos en STEP_ORDER." | tee -a logs/pipeline_e2.log
fi
