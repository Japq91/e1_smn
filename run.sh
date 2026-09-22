#!/usr/bin/env bash
# Orquestador principal (entry point único).
# Uso: ./run.sh [STEP_FROM] [STEP_TO] [MAX_MODELS]
#   - Sin args: ejecuta 00-07 (incluye 00b) sin límite.
#   - Con args: rango específico (ej. 02 07 3: desde descarga, limitado a 3 modelos).
#   - MAX_MODELS: limita a modelos completos (historical + escenarios SSP de
#     config/periods.yaml) según orden en models_catalog_status.csv.
#
# Ejemplo (prueba rápida, de punta a punta salvo QC/inventario):
#   ./run.sh 00 04 2
#   Corre desde el entorno (00) hasta el procesamiento a grilla común (04),
#   limitado a los primeros 2 modelos "completos" del catálogo (MAX_MODELS=2).
#
# Rediseños implementados:
# - Orden interno: remapeo PRIMERO, fusión temporal DESPUÉS. Pesos calculados una sola vez
#   por modelo (gencon/genbil según malla nativa) y cacheados en data/interim/.weights/.
# - Paso 05 (máscara): reescrito a Python por bug en CDO (scripts/05_apply_ocean_mask.py).
# - Gráficos bajo demanda desde: graficos_exploratorios.ipynb sobre data/processed/masked/.
# - Idempotencia: cada paso salta el procesamiento si el archivo de salida ya existe.
# - Nota: paso 00b_build_model_list.py se ejecuta entre 00 y 01 (sin renombrar scripts).
#   Ademas de armar config/models_seed_cmip6.csv (solo modelos con historical +
#   TODOS los SSP configurados, exigidos bajo una misma grilla), 00b escribe
#   informe/model_availability_report.csv/.md con la disponibilidad real por
#   experimento de TODOS los modelos inspeccionados (no solo los seleccionados) --
#   asi se ve, por ejemplo, que un modelo tiene historical+ssp245 pero le falta
#   ssp370/ssp585. Para 'historical' especificamente, si el nodo principal de
#   ESGF (LLNL) no lo tiene indexado, 00b prueba nodos alternativos antes de
#   descartar el modelo (mismo fallback que 02b, ver mas abajo); para los SSP no
#   hay ese fallback. check_model_availability.py queda como herramienta manual
#   de segunda opinion (ya no es necesario correrla aparte).
# - Paso 02 ahora es scripts/02_download_all_sources.sh: encadena ESGF (nodo
#   principal) -> ESGF (nodos alternativos, 02b) -> Copernicus CDS (02c, solo
#   lista blanca config/models_copernicus_available.csv). 02b/02c ya
#   NO son pasos manuales -- un clone nuevo + run.sh los ejecuta solo.
# - Paso 02 se invoca via scripts/run_download_if_idle.sh: si YA hay una
#   descarga corriendo en otro proceso, no lanza otra (se puede correr
#   run.sh mientras una descarga anterior sigue en curso sin duplicarla).
# - Cada corrida de run.sh, sin importar STEP_FROM/STEP_TO, termina
#   escribiendo un reporte de estado en texto plano en
#   logs/run_report_<timestamp-de-esta-corrida>.txt (ver
#   generate_status_report.py): que modelos ya estan descargados, cuales
#   con descarga parcial, cuales procesados, cuales descargados-pero-sin-
#   procesar, y cuales pendientes via fuentes alternativas.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p logs

# Activa el entorno conda del pipeline (creado una vez con
# "conda env create -f environment.yml") sin que quien ejecuta tenga
# que saber que es un PATH ni acordarse de "conda activate": alcanza
# con correr ./run.sh. Si ya hay un entorno "e1_smn" activo se deja
# como esta; si no, y existe uno con ese nombre, se activa aca mismo.
# Si conda no esta instalado o el entorno todavia no se creo, esto no
# hace nada y 00_setup_env.sh (paso 00) va a reportar con claridad que
# falta.
# NOTA: 'conda shell.bash hook' puede correr activate.d/deactivate.d
# de OTROS paquetes instalados (verificado: un hook de geotiff referencia
# una variable sin definir) -- no estan pensados para 'set -u', asi que
# se relajan -eu justo para este bloque y se restauran despues.
set +eu
if command -v conda >/dev/null 2>&1 && [ "$(basename "${CONDA_PREFIX:-}")" != "e1_smn" ]; then
    eval "$(conda shell.bash hook 2>/dev/null)" || true
    if conda env list 2>/dev/null | grep -qE '(^|[[:space:]])e1_smn([[:space:]]|$)'; then
        conda activate e1_smn 2>/dev/null || true
    fi
fi
set -eu

# En algunos clusters HPC (verificado con un setup Spack/OpenHPC) el
# PATH del sistema antepone sus propios binarios (python3, cdo, etc.)
# incluso con el entorno conda ya activado -- 'python3' termina
# resolviendo a un interprete sin las dependencias del pipeline
# (requests, pyyaml, ...) en vez de al del entorno. Si detectamos un
# entorno conda activo (CONDA_PREFIX), anteponemos su bin al PATH de
# este proceso (y de todos los pasos que invoca) para no depender de
# que el PATH del sistema coopere.
if [ -n "${CONDA_PREFIX:-}" ]; then
    export PATH="$CONDA_PREFIX/bin:$PATH"
fi

RUN_TS="$(date +%Y%m%d_%H%M%S)"
RUN_START_HUMAN="$(date '+%Y-%m-%d %H:%M:%S')"

STEP_ORDER=(00 00b 01 02 03 04 05 06 07)

STEP_FROM="${1:-00}"
STEP_TO="${2:-07}"
MAX_MODELS="${3:-}"   # vacio = sin limite

if [ -n "$MAX_MODELS" ] && ! [[ "$MAX_MODELS" =~ ^[0-9]+$ ]]; then
    echo "MAX_MODELS debe ser un numero entero positivo, se recibio: '$MAX_MODELS'" >&2
    exit 1
fi
export MAX_MODELS

index_of () {
    local target="$1"
    for i in "${!STEP_ORDER[@]}"; do
        if [ "${STEP_ORDER[$i]}" = "$target" ]; then
            echo "$i"
            return
        fi
    done
    echo "-1"
}

FROM_IDX=$(index_of "$STEP_FROM")
TO_IDX=$(index_of "$STEP_TO")

if [ "$FROM_IDX" -lt 0 ] || [ "$TO_IDX" -lt 0 ]; then
    echo "Paso desconocido. Pasos validos: ${STEP_ORDER[*]}" >&2
    exit 1
fi

if [ -n "$MAX_MODELS" ]; then
    echo "Limite de modelos activo: MAX_MODELS=$MAX_MODELS"
fi

# Directorios y archivos clave (para acortar rutas)
MASKED_DIR="data/processed/masked"
CATALOG_FILE="data/interim/models_catalog_status.csv"
URLS_FILE="data/interim/esgf_file_urls.json"
QC_REPORT="data/processed/qc_report.csv"
INVENTORY_FILE="data/processed/models_inventory_final.csv"
LOG_FILE="logs/pipeline.log"

# Reporte preflight: que falta y cuanto se estima que tarde (segun
# corridas anteriores REALES en esta maquina), antes de correr nada.
# Siempre se muestra, sin importar STEP_FROM/STEP_TO -- igual criterio
# que el reporte de estado que se escribe al final (ver mas abajo).
python3 scripts/preflight_report.py "$MAX_MODELS"

run_step () {
    local name="$1"; shift
    local idx; idx=$(index_of "$name")
    if [ "$idx" -ge "$FROM_IDX" ] && [ "$idx" -le "$TO_IDX" ]; then
        echo "== Paso $name: $* ==" | tee -a $LOG_FILE
        local step_start; step_start=$(date +%s)
        "$@" 2>&1 | tee -a $LOG_FILE
        # Duracion real de este paso en esta maquina (logs/step_timings.csv,
        # no versionado): alimenta el estimado del reporte preflight de la
        # proxima corrida (ver scripts/pipeline_timing.py). Una corrida
        # casi instantanea (paso ya hecho, idempotente) no sirve como
        # muestra -- eso se filtra en pipeline_timing.py, no aca.
        python3 scripts/pipeline_timing.py record_step "$name" "$(( $(date +%s) - step_start ))" || true
    fi
}


run_step 00  bash    scripts/00_setup_env.sh
run_step 00b python3 scripts/00b_build_model_list.py config/models_seed_cmip6.csv
run_step 01  python3 scripts/01_query_esgf_catalog.py config/models_seed_cmip6.csv $CATALOG_FILE $URLS_FILE
run_step 02  bash    scripts/run_download_if_idle.sh
run_step 03  bash    scripts/03_download_ersstv5.sh
run_step 04  bash    scripts/04_process_to_common_grid.sh
run_step 05  python3 scripts/05_apply_ocean_mask.py
run_step 06  python3 scripts/06_qc_checks.py $MASKED_DIR $QC_REPORT
run_step 07  python3 scripts/07_build_inventory_report.py $QC_REPORT $MASKED_DIR $INVENTORY_FILE

echo "Pipeline completo." | tee -a logs/pipeline.log

# Registro de modelos (numero M001..M102 + institucion/realizacion/
# resolucion/disponibilidad en un solo CSV): siempre se intenta al
# final, igual que los graficos de abajo -- no fatal, usa lo que haya
# disponible de 00b/01 en ese momento.
echo "== Registro de modelos ==" | tee -a logs/pipeline.log
python3 scripts/build_model_registry.py 2>&1 | tee -a logs/pipeline.log \
    || echo "  (se omitio build_model_registry.py -- revisar el aviso arriba)" | tee -a logs/pipeline.log

# Graficos (GRAFICO 1-5 de graficos_exploratorios.ipynb, ver scripts/plot_*.py):
# siempre se intentan al final, sin importar STEP_FROM/STEP_TO -- cada uno es
# idempotente (salta las figuras que ya existen) y avisa sin abortar el resto
# si todavia le faltan datos de entrada (ej. si esta corrida no llego a
# descargar/procesar nada). No fatal: una figura que no se pudo generar no
# debe bloquear el paquete de abajo, que precisamente avisa que falta.
for plot_script in plot_qc_summary.py plot_boxplot_comparison.py \
                    plot_region_nino_orthographic.py plot_maps.py plot_box_series.py; do
    echo "== Graficos: $plot_script ==" | tee -a logs/pipeline.log
    python3 "scripts/$plot_script" 2>&1 | tee -a logs/pipeline.log \
        || echo "  (se omitio $plot_script -- revisar el aviso arriba)" | tee -a logs/pipeline.log
done

# Reporte de estado: siempre se genera, sin importar STEP_FROM/STEP_TO.
# No fatal si todavia falta un artefacto que necesita (ej. el catalogo,
# si esta corrida no llego al paso 01) -- no debe bloquear el paquete
# de abajo, que precisamente avisa que falta.
DOWNLOAD_FLAG_ARGS=()
[ -f data/interim/.download_running_flag ] && DOWNLOAD_FLAG_ARGS=(--downloading)
python3 scripts/generate_status_report.py \
    data/interim/models_catalog_status.csv data/raw/cmip6 data/interim/processed $MASKED_DIR \
    "logs/run_report_${RUN_TS}.txt" "$RUN_START_HUMAN" "$(date '+%Y-%m-%d %H:%M:%S')" \
    "${DOWNLOAD_FLAG_ARGS[@]}" \
    || echo "Aviso: no se pudo generar el reporte de estado todavia (probablemente falta un paso anterior)." | tee -a logs/pipeline.log

# Paquete con los artefactos dispersos para actualizar el informe/presentacion
# (config/, data/, informe/, logs/, figures/): siempre se intenta, sin
# importar STEP_FROM/STEP_TO. Empaqueta lo que ya existe y avisa, para
# lo que falta, que correr exactamente para generarlo.
python3 scripts/bundle_deliverable_update.py
