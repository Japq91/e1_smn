#!/usr/bin/env bash
# fix_giss_duplicado.sh -- Repara GISS-E2-1-G y GISS-E2-1-H: dos
# realizaciones (r1i1p1f2 y r1i1p3f1) quedaron mezcladas bajo el mismo
# grid_label (gn) y se fusionaron enteras en el paso 04, duplicando
# cada mes en los 4 experimentos de ambos modelos (n_months = 2x lo
# esperado en qc_report.csv). No se detecto en ningun otro modelo de
# los 40 (ver auditoria de n_months). Independiente de la ventana
# ampliada del Entregable 2 -- viene de una descarga previa que dejo
# dos realizaciones sin depurar.
#
# Borra todo lo relacionado a estos 2 modelos (crudo + catalogo + json
# de archivos + intermedios) y deja que el pipeline los re-resuelva
# desde cero contra ESGF (nodos alternativos incluidos), con una sola
# realizacion consistente. Se frena solo (set -e) si algo sale mal en
# cualquier paso, o si las verificaciones intermedias detectan que el
# problema persiste -- no sigue a ciegas.
#
# Uso, en la raiz del repo (local o HPC):
#   bash fix_giss_duplicado.sh
set -euo pipefail
cd "$(dirname "$0")"

# Mismo bloque de activacion de entorno conda que run.sh (ver ahi el
# detalle completo): prioriza "smn_toe", cae a "e1_smn" si ese no
# existe todavia, y antepone el PATH del entorno activo -- en algunos
# clusters HPC (Spack/OpenHPC) 'python3' del sistema se antepone igual
# aunque el entorno conda ya este activo, y termina resolviendo a un
# interprete sin 'requests'/'pyyaml' (necesarios para
# 02b_search_alt_esgf_nodes.py).
set +eu
if command -v conda >/dev/null 2>&1 && [ "$(basename "${CONDA_PREFIX:-}")" != "smn_toe" ]; then
    eval "$(conda shell.bash hook 2>/dev/null)" || true
    if conda env list 2>/dev/null | grep -qE '(^|[[:space:]])smn_toe([[:space:]]|$)'; then
        conda activate smn_toe 2>/dev/null || true
    elif conda env list 2>/dev/null | grep -qE '(^|[[:space:]])e1_smn([[:space:]]|$)'; then
        conda activate e1_smn 2>/dev/null || true
    fi
fi
set -eu
if [ -n "${CONDA_PREFIX:-}" ]; then
    export PATH="$CONDA_PREFIX/bin:$PATH"
fi

TARGET_MODELS=(GISS-E2-1-G GISS-E2-1-H)
CATALOG_CSV="data/interim/models_catalog_status.csv"
FILES_JSON="data/interim/esgf_file_urls.json"

echo "== 1/5: borrando datos crudos existentes (ambas realizaciones) =="
for m in "${TARGET_MODELS[@]}"; do
    echo "  data/raw/cmip6/$m"
    rm -rf "data/raw/cmip6/$m"
done

echo "== 2/5: sacando estos modelos del catalogo y del json de archivos =="
python3 - "$CATALOG_CSV" "${TARGET_MODELS[@]}" <<'PYEOF'
import csv, sys
path = sys.argv[1]
targets = set(sys.argv[2:])
rows = list(csv.DictReader(open(path, newline="")))
fields = list(rows[0].keys())
before = len(rows)
rows = [r for r in rows if r["model"] not in targets]
w = csv.DictWriter(open(path, "w", newline=""), fieldnames=fields)
w.writeheader()
w.writerows(rows)
print(f"  catalogo: {before} -> {len(rows)} filas")
PYEOF

python3 - "$FILES_JSON" "${TARGET_MODELS[@]}" <<'PYEOF'
import json, sys
path = sys.argv[1]
targets = sys.argv[2:]
d = json.load(open(path))
before = len(d)
for m in targets:
    d.pop(m, None)
json.dump(d, open(path, "w"))
print(f"  json de archivos: {before} -> {len(d)} modelos")
PYEOF

echo "== 3/5: re-resolviendo estos modelos desde cero contra ESGF (nodo principal + alternativos) =="
refetch_csv="data/interim/.giss_refetch_tmp.csv"
{ echo "model"; printf '%s\n' "${TARGET_MODELS[@]}"; } > "$refetch_csv"
python3 scripts/02b_search_alt_esgf_nodes.py "$refetch_csv" "$CATALOG_CSV" "$FILES_JSON"
rm -f "$refetch_csv"

echo "  Verificando que cada modelo quedo con una fila resuelta en el catalogo..."
fail=0
for m in "${TARGET_MODELS[@]}"; do
    row=$(grep "^$m," "$CATALOG_CSV" || true)
    if [ -z "$row" ]; then
        echo "  FALTA: $m no aparece en el catalogo tras la busqueda -- no se encontro en ningun nodo." >&2
        fail=1
    else
        echo "  $m -> $row"
    fi
done
if [ "$fail" -eq 1 ]; then
    echo "ABORTANDO: revisa los modelos faltantes arriba antes de continuar (no se descargo nada todavia)." >&2
    exit 1
fi

echo "== 4/5: descargando SOLO estos 2 modelos (con la lista ya depurada a una sola realizacion) =="
# NO se llama a scripts/02_download_cmip6_chunks.sh: ese script no
# admite filtrar por nombre de modelo (solo MAX_MODELS, un limite
# numerico) -- arma su propia lista leyendo TODO el catalogo
# (READY_MODELS), asi que descargaria de paso cualquier otro modelo con
# chunks pendientes. Se reimplementa aca, scopeado, la misma logica de
# descarga con reintentos/mirrors que usa ese script.
mapfile -t EXPERIMENTS < <(python3 scripts/pipeline_config.py experiments | tr ' ' '\n')
WGET_TIMEOUT=120
DOWNLOAD_RETRIES=3

download_with_mirrors () {
    local urls_csv="$1" outfile="$2"
    IFS=',' read -ra urls <<< "$urls_csv"
    for url in "${urls[@]}"; do
        local attempt=1
        while [ "$attempt" -le "$DOWNLOAD_RETRIES" ]; do
            if wget -q --timeout="$WGET_TIMEOUT" --tries=1 -O "$outfile" "$url"; then
                [ -s "$outfile" ] && return 0
            fi
            rm -f "$outfile"
            attempt=$((attempt + 1))
            [ "$attempt" -le "$DOWNLOAD_RETRIES" ] && sleep 3
        done
    done
    return 1
}

for m in "${TARGET_MODELS[@]}"; do
    for exp in "${EXPERIMENTS[@]}"; do
        dest_dir="data/raw/cmip6/$m/$exp"
        mkdir -p "$dest_dir"
        file_list=$(python3 -c "
import json
d = json.load(open('$FILES_JSON'))
entries = d.get('$m', {}).get('$exp', [])
for e in entries:
    print(e['filename'] + '\t' + ','.join(e['urls']))
")
        if [ -z "$file_list" ]; then
            echo "  $m $exp: sin archivos listados en $FILES_JSON, se omite"
            continue
        fi
        while IFS=$'\t' read -r filename urls_csv; do
            [ -z "$filename" ] && continue
            outfile="$dest_dir/$filename"
            if [ -s "$outfile" ]; then
                echo "  $m $exp: $filename ya existe, se omite"
                continue
            fi
            echo "  $m $exp: descargando $filename ..."
            if ! download_with_mirrors "$urls_csv" "$outfile"; then
                echo "  FALLO: $m $exp $filename (todos los mirrors)" >&2
            fi
        done <<< "$file_list"
    done
done

echo "  Verificando que no haya mas de una realizacion mezclada en los chunks crudos..."
fail=0
for m in "${TARGET_MODELS[@]}"; do
    for exp_dir in data/raw/cmip6/"$m"/*/; do
        [ -d "$exp_dir" ] || continue
        n_members=$(ls "$exp_dir" 2>/dev/null | grep -oP '(?<=_)r[0-9]+i[0-9]+p[0-9]+f[0-9]+(?=_)' | sort -u | wc -l)
        if [ "$n_members" -gt 1 ]; then
            echo "  AVISO: $exp_dir todavia tiene $n_members realizaciones distintas mezcladas." >&2
            fail=1
        fi
    done
done
if [ "$fail" -eq 1 ]; then
    echo "ABORTANDO antes de reprocesar -- revisa el aviso de arriba a mano." >&2
    exit 1
fi
echo "  OK: una sola realizacion por modelo/experimento."

echo "== 5/5: reprocesando estos modelos (pasos 04-07) =="
rm -f data/interim/.weights/GISS-E2-1-G*.nc data/interim/.weights/GISS-E2-1-H*.nc
MODELS_STR="${TARGET_MODELS[*]}"
MODELS="$MODELS_STR" bash run.sh 04 07

echo ""
echo "== Resultado final: n_months en QC (NO deberian estar duplicados) =="
for m in "${TARGET_MODELS[@]}"; do
    grep "^tos_${m}_" data/processed/qc_report.csv || echo "  $m: no aparece en qc_report.csv"
done

echo ""
echo "Listo -- revisa arriba que n_months sea el esperado (1980 historical, 1032 cada SSP), no el doble."
