#!/usr/bin/env bash
# Orquesta la descarga completa de CMIP6 encadenando las 3 fuentes en
# cascada: ESGF (nodo principal, 02_download_cmip6_chunks.sh) -> ESGF
# (nodos alternativos, 02b_search_alt_esgf_nodes.py) -> Copernicus CDS
# (02c_download_copernicus_cds.py, solo para los modelos de la lista
# blanca config/models_copernicus_ssp245_whitelist.csv).
#
# A diferencia de versiones anteriores del pipeline, 02b y 02c ya NO
# son pasos manuales: este script los ejecuta automaticamente como
# fallback, en ese orden, solo para lo que la fuente anterior no haya
# resuelto. Pensado para que un 'git clone' + 'run.sh' en una maquina
# nueva obtenga todo lo posible sin intervencion manual.
#
# Copernicus CDS requiere credenciales personales (~/.cdsapirc) y la
# licencia del dataset 'projections-cmip6' aceptada en
# https://cds.climate.copernicus.eu/datasets/projections-cmip6 . Si no
# estan disponibles, el paso 02c se omite con un aviso -- no aborta el
# resto del pipeline.
#
# La lista blanca de Copernicus existe porque CDS no espeja el
# catalogo completo de ESGF: para muchos modelos "de cola larga" el
# job falla con RoocsValueError (el dataset no esta replicado ahi).
# La lista se construyo verificando a mano, en el sitio de Copernicus,
# que modelo+ssp245 si existe -- evita gastar cuota/tiempo en jobs que
# sabemos que van a fallar.
set -uo pipefail
cd "$(dirname "$0")/.."

CATALOG_CSV="data/interim/models_catalog_status.csv"
FILES_JSON="data/interim/esgf_file_urls.json"
COPERNICUS_WHITELIST="config/models_copernicus_ssp245_whitelist.csv"

# Imprime (stdout) los modelos de CATALOG_CSV cuyo 'fuente' sea
# exactamente el valor pasado como argumento.
models_with_status () {
    python3 -c "
import csv, sys
with open('$CATALOG_CSV') as f:
    rows = list(csv.DictReader(f))
for r in rows:
    if r.get('fuente') == sys.argv[1]:
        print(r['model'])
" "$1"
}

echo "== 02a: descarga CMIP6 via ESGF (nodo principal) =="
bash scripts/02_download_cmip6_chunks.sh

no_encontrado_csv="data/interim/.no_encontrado_tmp.csv"
{ echo "model"; models_with_status no_encontrado; } > "$no_encontrado_csv"
n_missing=$(($(wc -l < "$no_encontrado_csv") - 1))

if [ "$n_missing" -gt 0 ]; then
    echo "== 02b: $n_missing modelos no encontrados en el nodo principal -- probando nodos alternativos de ESGF =="
    python3 scripts/02b_search_alt_esgf_nodes.py "$no_encontrado_csv" "$CATALOG_CSV" "$FILES_JSON" || true

    echo "== 02a (reintento): descarga lo que 02b haya resuelto =="
    bash scripts/02_download_cmip6_chunks.sh
else
    echo "== 02b: nada pendiente, se omite =="
fi

{ echo "model"; models_with_status no_encontrado; } > "$no_encontrado_csv"
n_still_missing=$(($(wc -l < "$no_encontrado_csv") - 1))

if [ "$n_still_missing" -gt 0 ] && [ -f "$HOME/.cdsapirc" ] && python3 -c "import cdsapi" 2>/dev/null; then
    copernicus_csv="data/interim/.copernicus_tmp.csv"
    python3 -c "
import csv, sys
whitelist = set()
with open('$COPERNICUS_WHITELIST') as f:
    for row in csv.DictReader(f):
        whitelist.add(row['model'])
with open('$no_encontrado_csv') as f:
    missing = [row['model'] for row in csv.DictReader(f)]
target = [m for m in missing if m in whitelist]
with open('$copernicus_csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['model'])
    for m in target:
        w.writerow([m])
print(f'{len(target)} de {len(missing)} modelos aun sin encontrar estan en la lista blanca de Copernicus', file=sys.stderr)
"
    if [ "$(($(wc -l < "$copernicus_csv") - 1))" -gt 0 ]; then
        echo "== 02c: probando Copernicus CDS (solo lista blanca, ver arriba) =="
        python3 scripts/02c_download_copernicus_cds.py "$copernicus_csv" data/raw/cmip6 || true
    else
        echo "== 02c: ninguno de los modelos faltantes esta en la lista blanca de Copernicus, se omite =="
    fi
else
    if [ "$n_still_missing" -gt 0 ]; then
        echo "== 02c: omitido -- falta ~/.cdsapirc o el paquete cdsapi (pip install cdsapi) =="
    else
        echo "== 02c: nada pendiente, se omite =="
    fi
fi

rm -f "$no_encontrado_csv"
echo "Descarga completa (ESGF principal + alternativo + Copernicus segun disponibilidad y credenciales)."
