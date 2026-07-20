#!/usr/bin/env python3
"""Segunda opcion: descarga modelos via el Climate Data Store (CDS) de
Copernicus, usando las credenciales personales del usuario (paso 02c
-- NO forma parte de la secuencia automatica de run.sh; via
alternativa a ESGF, manual).

Parametros de la peticion verificados contra una descarga real exitosa
(NorCPM1, historical, 1850-2014: 1980 pasos de tiempo = 165 anios x 12
meses, variant_label=r1i1p1f1 -- exactamente lo esperado):
  - Sin 'level': no hace falta para una variable de superficie como
    'sea_surface_temperature'.
  - Sin 'ensemble_member': CDS entrega r1i1p1f1 por defecto (verificado
    para NorCPM1; el script avisa si algun modelo entrega otro miembro,
    sin detener la descarga).
  - La fecha se pide como 'year' (lista) + 'month' (lista), NO como
    'date': 'YYYY-MM-DD/YYYY-MM-DD' (ese formato no es el que acepta
    este dataset).
  - 'area' [Norte, Oeste, Sur, Este] SOLO recorta latitud (-20 a 20):
    en longitud se pide el rango completo (-180 a 180). Nuestra ventana
    real (100E-290E en formato 0-360, es decir 100E a -70E) cruza el
    antimeridiano al pasarla a -180/180, y una sola caja de CDS no
    expresa bien ese cruce (haria falta partirla en dos peticiones).
    Latitud no tiene ese problema (no hay "antimeridiano" en -90/90),
    asi que recortarla si reduce bastante el tamano sin ese riesgo. El
    recorte de longitud que falta queda a cargo del regrillado del
    paso 04 (la grilla objetivo de ERSSTv5 ya esta acotada a la
    ventana), igual que con ESGF.

Organiza la salida exactamente como 02_download_cmip6_chunks.sh
(data/raw/cmip6/<modelo>/<experimento>/*.nc), para que 04 la procese
sin distinguir de donde vino el dato.

Orden de descarga: TODOS los historicos primero, despues TODOS los
ssp245, despues TODOS los ssp585 -- no intercalado por modelo.

Requiere:
  - pip install cdsapi
  - archivo ~/.cdsapirc con tus credenciales de tu cuenta CDS
  - licencia del dataset 'projections-cmip6' aceptada en
    https://cds.climate.copernicus.eu/datasets/projections-cmip6

Uso:
    python3 02c_download_copernicus_cds.py <lista_modelos.csv> data/raw/cmip6

<lista_modelos.csv> solo necesita una columna 'model' (mismo formato
que config/models_missing_from_esgf.csv o config/models_seed_cmip6.csv).
"""
import csv
import re
import shutil
import sys
import zipfile
from pathlib import Path

try:
    import cdsapi
except ImportError:
    sys.exit(
        "Falta el paquete 'cdsapi' (pip install cdsapi). "
        "Tambien se necesita ~/.cdsapirc con las credenciales de tu cuenta Copernicus."
    )

try:
    import netCDF4 as nc
except ImportError:
    nc = None  # el chequeo de variant_label se omite si falta netCDF4, no es critico

CDS_DATASET = "projections-cmip6"
CDS_VARIABLE = "sea_surface_temperature"
# Verificado contra el archivo publico de restricciones del dataset
# (https://cds.climate.copernicus.eu/api/catalogue/v1/collections/projections-cmip6/constraints.json,
# sin gastar cuota de descarga): los escenarios SSP usan guion bajo
# entre digitos, NO el mismo nombre corto que ESGF.
CDS_EXPERIMENT_MAP = {"historical": "historical", "ssp245": "ssp2_4_5", "ssp585": "ssp5_8_5"}
CDS_YEAR_RANGE = {
    "historical": range(1850, 2015),
    "ssp245": range(2015, 2101),
    "ssp585": range(2015, 2101),
}
CDS_MONTHS = [f"{m:02d}" for m in range(1, 13)]
# [Norte, Oeste, Sur, Este]: longitud completa (evita el cruce del
# antimeridiano), latitud acotada a la ventana del proyecto (20S-20N).
CDS_AREA = [20, -180, -20, 180]
EXPECTED_MEMBER = "r1i1p1f1"

# Variantes de alta resolucion (sufijos -HR, -HR4, -VHR4, -XR, -MR1,
# -HH/-HM/-MH, etc.) se omiten por defecto: confirmado que CMCC-CM2-HR4
# (historical, ya con latitud acotada a -20/20) pesa 29.5 GB via
# Copernicus, ~80x mas que un modelo de resolucion estandar como
# NorCPM1 (370 MB) -- tardan horas y no hacen falta para este proyecto
# (que regrilla todo a la resolucion gruesa de ERSSTv5, ~2 grados).
HIGH_RES_PATTERN = re.compile(r"-(V?HR\d*|XR|MR1|HH|HM|MH)$", re.IGNORECASE)


def is_high_resolution(model: str) -> bool:
    return bool(HIGH_RES_PATTERN.search(model))


def cmip6_name_to_cds(model: str) -> str:
    """Convierte un source_id de CMIP6 (p.ej. 'CNRM-ESM2-1') al formato
    que usa CDS para el parametro 'model' (minusculas, guion bajo:
    'cnrm_esm2_1'). Verificado contra una descarga real (NorCPM1 ->
    'norcpm1')."""
    return model.lower().replace("-", "_").replace(".", "_")


def _check_variant_label(nc_path: Path, model: str, exp: str) -> None:
    if nc is None:
        return
    try:
        with nc.Dataset(nc_path) as ds:
            variant = getattr(ds, "variant_label", None)
    except Exception:
        return
    if variant and variant != EXPECTED_MEMBER:
        print(f"  AVISO: {model} {exp} entrego el miembro {variant}, no {EXPECTED_MEMBER} "
              "(revisar si es consistente con lo usado en el resto del pipeline)", file=sys.stderr)


def download_experiment(client: "cdsapi.Client", model: str, exp: str,
                         out_dir: Path, tmpdir: Path, fail_log: Path) -> bool:
    dest_dir = out_dir / model / exp
    if dest_dir.exists() and any(dest_dir.glob("*.nc")):
        return True  # idempotente: no re-descargar

    cds_model = cmip6_name_to_cds(model)
    zip_path = tmpdir / f"{model}_{exp}.zip"
    request = {
        "temporal_resolution": "monthly",
        "experiment": CDS_EXPERIMENT_MAP[exp],
        "variable": CDS_VARIABLE,
        "model": cds_model,
        "year": [str(y) for y in CDS_YEAR_RANGE[exp]],
        "month": CDS_MONTHS,
        "area": CDS_AREA,
    }

    try:
        client.retrieve(CDS_DATASET, request).download(str(zip_path))
    except Exception as e:  # cdsapi levanta excepciones genericas de la API remota
        with open(fail_log, "a") as f:
            f.write(f"FALLO CDS: {model} {exp} ({cds_model}): {e}\n")
        return False

    extract_dir = tmpdir / f"{model}_{exp}_extracted"
    extract_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)

    nc_files = sorted(extract_dir.glob("*.nc"))
    if not nc_files:
        with open(fail_log, "a") as f:
            f.write(f"FALLO CDS (zip sin .nc): {model} {exp}\n")
        shutil.rmtree(extract_dir, ignore_errors=True)
        zip_path.unlink(missing_ok=True)
        return False

    dest_dir.mkdir(parents=True, exist_ok=True)
    for f in nc_files:
        _check_variant_label(f, model, exp)
        shutil.move(str(f), str(dest_dir / f.name))

    # limpieza: el zip descargado y todo lo demas que traia adentro
    # (provenance.json, provenance.png, etc.)
    shutil.rmtree(extract_dir, ignore_errors=True)
    zip_path.unlink(missing_ok=True)

    print(f"  {model} {exp}: {len(nc_files)} archivo(s) -> {dest_dir}", file=sys.stderr)
    return True


def main(models_csv: str, outdir: str) -> None:
    with open(models_csv, newline="") as f:
        models = [row["model"] for row in csv.DictReader(f)]

    high_res = [m for m in models if is_high_resolution(m)]
    if high_res:
        print(f"Omitidos por ser variantes de alta resolucion (ver HIGH_RES_PATTERN): {high_res}",
              file=sys.stderr)
    models = [m for m in models if m not in high_res]

    if not models:
        sys.exit(f"{models_csv} no tiene modelos (tras filtrar variantes de alta resolucion)")

    out_path = Path(outdir)
    tmpdir = out_path / ".tmp_cds"
    tmpdir.mkdir(parents=True, exist_ok=True)
    fail_log = Path("logs/download_failures.log")
    fail_log.parent.mkdir(exist_ok=True)

    print(f"{len(models)} modelos via Copernicus CDS: {models}", file=sys.stderr)
    client = cdsapi.Client()

    # EXPERIMENTS (variable de entorno, opcional): lista separada por
    # espacios para restringir la corrida a esos experimentos (p.ej.
    # 'EXPERIMENTS=historical' para probar solo el periodo historico
    # antes de pedir los escenarios futuros, que pesan mas y tardan mas).
    import os
    all_exps = ("historical", "ssp245", "ssp585")
    exps = os.environ.get("EXPERIMENTS", "").split() or list(all_exps)
    exps = [e for e in all_exps if e in exps]  # mantiene el orden historical->ssp245->ssp585

    # Primero TODOS los historicos, despues TODOS los ssp245, despues
    # TODOS los ssp585 -- no intercalado por modelo. Las peticiones se
    # hacen en serie (un client.retrieve(...).download() a la vez, sin
    # paralelismo) para no saturar la cola de CDS con multiples
    # solicitudes simultaneas.
    for exp in exps:
        for model in models:
            print(f"Procesando {model} {exp} via Copernicus CDS ...", file=sys.stderr)
            download_experiment(client, model, exp, out_path, tmpdir, fail_log)

    shutil.rmtree(tmpdir, ignore_errors=True)
    print("\nRevisa logs/download_failures.log para lo que fallo.", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("uso: 02c_download_copernicus_cds.py <lista_modelos.csv> <outdir data/raw/cmip6>")
    main(sys.argv[1], sys.argv[2])
