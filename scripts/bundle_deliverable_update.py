#!/usr/bin/env python3
"""Empaqueta en un solo .tar.gz los artefactos dispersos (config/,
data/, informe/, logs/, figures/) que hacen falta para actualizar
informe/informe_e1_smnv2.tex y informe/presentacion_e1.html con
resultados reales de una corrida -- pensado para transferirlos de una
sola vez desde otra maquina (ej. HPC) en vez de archivo por archivo.

Se corre siempre al final de run.sh, sin importar STEP_FROM/STEP_TO
(mismo criterio que generate_status_report.py): empaqueta lo que YA
existe y, para cada archivo que todavia falta, avisa por consola
exactamente que correr para generarlo -- en vez de un error generico
de 'tar' o quedarse callado.

Uso:
    python3 bundle_deliverable_update.py [out.tar.gz]
"""
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# (ruta relativa al repo, como generarla si todavia no existe)
EXPECTED_FILES = [
    ("config/models_seed_cmip6.csv",
     "run.sh (paso 00b) -- si ya existe y quedo viejo, borralo primero para forzar un refresco"),
    ("data/interim/models_catalog_status.csv",
     "run.sh (paso 01)"),
    ("informe/model_availability_priority.csv",
     "run.sh (paso 00b) -- se genera junto con models_seed_cmip6.csv"),
    ("informe/model_registry.csv",
     "python3 scripts/build_model_registry.py (ya se corre solo al final de run.sh) -- "
     "numero M001..M102 por modelo, cruzado con el eje de figures/sst_QD_vf.png"),
    ("data/processed/qc_report.csv",
     "run.sh (paso 06) -- necesita 02-05 ya corridos (datos descargados y procesados)"),
    ("data/processed/models_inventory_final.csv",
     "run.sh (paso 07) -- necesita 06 ya corrido"),
    ("figures/sst_QD_vf.png",
     "python3 scripts/plot_qc_summary.py (ya se corre solo al final de run.sh)"),
    ("figures/sst_2d_ERSSTv5.png",
     "python3 scripts/plot_maps.py (ya se corre solo al final de run.sh) -- "
     "necesita data/processed/masked/ersstv5_region.nc (pasos 03-05) -- el observado"),
    # Los 3 modelos de grilla mas gruesa entre los seleccionados (ver
    # informe/model_registry.csv, columna resolution_km: ACCESS-CM2
    # (M001), ACCESS-ESM1-5 (M002) y GISS-E2-1-G (M057) empatan en 250 km,
    # se toman los 3 primeros en orden alfabetico/de codigo M -- mismo
    # criterio que el resto del proyecto) -- mapa 2D + series de caja de
    # cada uno. Nombre de archivo con el codigo M como primer segmento
    # (scripts/plot_common.py: sst_2d_filename/series_filename).
    ("figures/M001_sst_2d_ACCESS-CM2.png",
     "python3 scripts/plot_maps.py (ya se corre solo al final de run.sh) -- "
     "necesita que ACCESS-CM2 este descargado y procesado (pasos 02-05)"),
    ("figures/M002_sst_2d_ACCESS-ESM1-5.png",
     "python3 scripts/plot_maps.py (ya se corre solo al final de run.sh) -- "
     "necesita que ACCESS-ESM1-5 este descargado y procesado (pasos 02-05)"),
    ("figures/M057_sst_2d_GISS-E2-1-G.png",
     "python3 scripts/plot_maps.py (ya se corre solo al final de run.sh) -- "
     "necesita que GISS-E2-1-G este descargado y procesado (pasos 02-05)"),
    ("figures/M001_serie_ACCESS-CM2_sst_Nino3.4.png",
     "python3 scripts/plot_box_series.py (ya se corre solo al final de run.sh)"),
    ("figures/M001_serie_ACCESS-CM2_sst_Nino1+2.png",
     "python3 scripts/plot_box_series.py (ya se corre solo al final de run.sh)"),
    ("figures/M002_serie_ACCESS-ESM1-5_sst_Nino3.4.png",
     "python3 scripts/plot_box_series.py (ya se corre solo al final de run.sh)"),
    ("figures/M002_serie_ACCESS-ESM1-5_sst_Nino1+2.png",
     "python3 scripts/plot_box_series.py (ya se corre solo al final de run.sh)"),
    ("figures/M057_serie_GISS-E2-1-G_sst_Nino3.4.png",
     "python3 scripts/plot_box_series.py (ya se corre solo al final de run.sh)"),
    ("figures/M057_serie_GISS-E2-1-G_sst_Nino1+2.png",
     "python3 scripts/plot_box_series.py (ya se corre solo al final de run.sh)"),
    ("figures/boxplot_Nino3.4.png",
     "python3 scripts/plot_boxplot_comparison.py (ya se corre solo al final de run.sh)"),
    ("figures/boxplot_Nino1+2.png",
     "python3 scripts/plot_boxplot_comparison.py (ya se corre solo al final de run.sh)"),
    ("figures/region_nino_proj.png",
     "python3 scripts/plot_region_nino_orthographic.py (ya se corre solo al final de run.sh) -- "
     "no depende de datos descargados, requiere cartopy (esta en environment.yml)"),
]


def latest_run_report() -> Path | None:
    reports = sorted((BASE_DIR / "logs").glob("run_report_*.txt"))
    return reports[-1] if reports else None


def main(out_path: Path) -> None:
    present: list[str] = []
    missing: list[tuple[str, str]] = []

    for rel, how_to in EXPECTED_FILES:
        if (BASE_DIR / rel).exists():
            present.append(rel)
        else:
            missing.append((rel, how_to))

    run_report = latest_run_report()
    if run_report:
        present.append(str(run_report.relative_to(BASE_DIR)))
    else:
        missing.append(("logs/run_report_*.txt", "se genera solo al final de cualquier corrida de run.sh"))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if present:
        subprocess.run(["tar", "-czf", str(out_path), *present], cwd=BASE_DIR, check=True)
        print(f"\nPaquete armado en {out_path} ({len(present)} archivo(s)).", file=sys.stderr)
    else:
        out_path.unlink(missing_ok=True)
        print("\nTodavia no hay ningun archivo disponible -- no se genero el .tar.gz.", file=sys.stderr)

    if missing:
        print(f"Faltan {len(missing)} archivo(s) (no incluidos en el paquete):", file=sys.stderr)
        for rel, how_to in missing:
            print(f"  [FALTA] {rel}\n           -> generarlo con: {how_to}", file=sys.stderr)
    else:
        print("Estan todos los archivos esperados.", file=sys.stderr)


if __name__ == "__main__":
    out_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE_DIR / "informe" / "entregable_update.tar.gz"
    main(out_arg)
