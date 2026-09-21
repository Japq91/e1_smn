#!/usr/bin/env bash
# Orquesta la descarga completa de CMIP6 encadenando las 3 fuentes en
# cascada: ESGF (nodo principal, 02_download_cmip6_chunks.sh) -> ESGF
# (nodos alternativos, 02b_search_alt_esgf_nodes.py) -> Copernicus CDS
# (02c_download_copernicus_cds.py, solo para los modelos de la lista
# blanca config/models_copernicus_available.csv).
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
# config/models_copernicus_available.csv es el listado de modelos que
# ofrece el selector del dataset 'projections-cmip6' en el sitio de
# Copernicus (confirma que el MODELO existe ahi, no que tenga
# necesariamente todos los experimentos requeridos -- eso lo resuelve
# 02c intentando la descarga real) -- evita gastar cuota/tiempo en
# modelos que sabemos que ni siquiera aparecen en CDS. Reemplaza a
# config/models_copernicus_ssp245_whitelist.csv (mas acotada, verificada
# a mano solo para ssp245; se conserva sin usar, como referencia
# historica del Entregable 1 -- ver informe/).
set -uo pipefail
cd "$(dirname "$0")/.."

CATALOG_CSV="data/interim/models_catalog_status.csv"
FILES_JSON="data/interim/esgf_file_urls.json"
COPERNICUS_WHITELIST="config/models_copernicus_available.csv"
# Tope de veces que se reintenta un modelo "no_encontrado" en corridas
# SUCESIVAS de run.sh (columna 'intentos_busqueda' del catalogo, un
# acumulado que persiste entre corridas). Al llegar al tope, se deja de
# intentar (02b/02c) para ese modelo -- ya se agoto en la practica (ver
# MIROC-ES2H: ESGF completo + Copernicus, sin exito). Para reintentarlo
# de nuevo hay que borrar $CATALOG_CSV a mano (arranca todo de cero).
MAX_SEARCH_ATTEMPTS=3

# Imprime (stdout) los modelos de CATALOG_CSV cuyo 'fuente' sea
# exactamente el valor pasado como argumento Y que todavia no llegaron
# al tope de intentos.
models_pendientes () {
    python3 -c "
import csv, sys
with open('$CATALOG_CSV') as f:
    rows = list(csv.DictReader(f))
for r in rows:
    if r.get('fuente') != sys.argv[1]:
        continue
    intentos = int(r.get('intentos_busqueda') or 0)
    if intentos < $MAX_SEARCH_ATTEMPTS:
        print(r['model'])
" "$1"
}

# Modelos 'no_encontrado' que YA llegaron al tope -- solo para avisar.
modelos_en_limite () {
    python3 -c "
with open('$CATALOG_CSV') as f:
    import csv
    rows = list(csv.DictReader(f))
for r in rows:
    if r.get('fuente') != 'no_encontrado':
        continue
    intentos = int(r.get('intentos_busqueda') or 0)
    if intentos >= $MAX_SEARCH_ATTEMPTS:
        print(f\"  - {r['model']} ({intentos} intentos)\")
"
}

en_limite="$(modelos_en_limite)"
if [ -n "$en_limite" ]; then
    echo "Modelos que ya agotaron $MAX_SEARCH_ATTEMPTS intentos de busqueda en corridas anteriores -- no se vuelven a intentar (borrar $CATALOG_CSV para reintentar de cero):"
    echo "$en_limite"
fi

echo "== 02a: descarga CMIP6 via ESGF (nodo principal) =="
bash scripts/02_download_cmip6_chunks.sh

no_encontrado_csv="data/interim/.no_encontrado_tmp.csv"
{ echo "model"; models_pendientes no_encontrado; } > "$no_encontrado_csv"
n_missing=$(($(wc -l < "$no_encontrado_csv") - 1))

# Confirmacion explicita antes de entrar a la cascada de fuentes
# alternativas (02b + 02c): a diferencia del nodo principal (02a, ya
# esperado en cualquier corrida), buscar en nodos alternativos y en
# Copernicus CDS puede tardar bastante para un lote grande de modelos
# no encontrados. Decision del usuario: preguntar, pero con un limite
# de 15s -- si no hay respuesta (corrida no interactiva, o el usuario
# se alejo), se continua igual que si hubiera dicho que si (nunca se
# bloquea una corrida desatendida por falta de respuesta).
TRY_ALT_SOURCES=1
if [ "$n_missing" -gt 0 ] && [ -t 0 ]; then
    echo "$n_missing modelo(s) no se encontraron en el nodo principal de ESGF."
    if read -r -t 15 -p "Buscar en nodos alternativos de ESGF (02b) y Copernicus CDS (02c)? [S/n, 15s, por defecto S] " respuesta; then
        case "$respuesta" in
            [nN]*) TRY_ALT_SOURCES=0 ;;
        esac
    else
        echo
        echo "(sin respuesta en 15s, se continua como si hubieras dicho que si)"
    fi
fi

if [ "$n_missing" -gt 0 ] && [ "$TRY_ALT_SOURCES" -eq 1 ]; then
    echo "== 02b: $n_missing modelos no encontrados en el nodo principal -- probando nodos alternativos de ESGF =="
    python3 scripts/02b_search_alt_esgf_nodes.py "$no_encontrado_csv" "$CATALOG_CSV" "$FILES_JSON" || true

    echo "== 02a (reintento): descarga lo que 02b haya resuelto =="
    bash scripts/02_download_cmip6_chunks.sh
elif [ "$n_missing" -gt 0 ]; then
    echo "== 02b: omitido por decision del usuario =="
else
    echo "== 02b: nada pendiente, se omite =="
fi

{ echo "model"; models_pendientes no_encontrado; } > "$no_encontrado_csv"
n_still_missing=$(($(wc -l < "$no_encontrado_csv") - 1))

if [ "$n_still_missing" -gt 0 ] && [ "$TRY_ALT_SOURCES" -eq 0 ]; then
    echo "== 02c: omitido por decision del usuario (misma respuesta que 02b) =="
elif [ "$n_still_missing" -gt 0 ] && [ -f "$HOME/.cdsapirc" ] && python3 -c "import cdsapi" 2>/dev/null; then
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

{ echo "model"; models_pendientes no_encontrado; } > "$no_encontrado_csv"
n_final_missing=$(($(wc -l < "$no_encontrado_csv") - 1))
if [ "$n_final_missing" -gt 0 ]; then
    python3 -c "
import csv, sys

with open('$CATALOG_CSV', newline='') as f:
    reader = csv.DictReader(f)
    fieldnames = list(reader.fieldnames or [])
    rows = list(reader)
if 'intentos_busqueda' not in fieldnames:
    fieldnames.append('intentos_busqueda')

with open('$no_encontrado_csv', newline='') as f:
    intentados = {row['model'] for row in csv.DictReader(f)}

for r in rows:
    if r['model'] in intentados:
        r['intentos_busqueda'] = str(int(r.get('intentos_busqueda') or 0) + 1)

with open('$CATALOG_CSV', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
    w.writeheader()
    w.writerows(rows)
print(f'{len(intentados)} modelo(s) siguen sin resolverse -- intentos_busqueda incrementado '
      f'(tope: $MAX_SEARCH_ATTEMPTS, borrar $CATALOG_CSV para reintentar de cero)', file=sys.stderr)
"
fi

rm -f "$no_encontrado_csv"
echo "Descarga completa (ESGF principal + alternativo + Copernicus segun disponibilidad y credenciales)."
