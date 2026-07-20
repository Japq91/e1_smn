#!/usr/bin/env python3
"""Control de calidad automatico (paso 06).

Verifica, por archivo homogeneizado, el rango fisico de SST y la
cobertura temporal esperada por experimento; escribe un reporte que
07_build_inventory_report.py usa para descartar del inventario final
los modelos que fallan.

NOTA: la version anterior de este chequeo exigia una longitud minima
de piControl (100 anios). piControl ya no es un experimento requerido
(ver config/periods.yaml), asi que ese chequeo se reemplazo por una
verificacion de que historical/ssp245/ssp585 cubran razonablemente el
periodo esperado (1850-2014 y 2015-2100, con 10% de tolerancia), en
vez de quedar como una condicion que nunca se evalua.
"""
import csv
import re
import subprocess
import sys
from pathlib import Path

MIN_SST, MAX_SST = -2.0, 39.0
EXPECTED_YEARS = {"historical": 165, "ssp245": 86, "ssp585": 86}
LENGTH_TOLERANCE = 0.9  # se acepta hasta 10% menos de lo esperado


def cdo_run(args: list[str]) -> str:
    return subprocess.run(["cdo", "-s", *args], capture_output=True, text=True, check=True).stdout


def field_minmax(path: str) -> tuple[float, float]:
    # 'output' debe ser el operador mas externo (el que imprime);
    # -fldmin/-fldmax y -timmin/-timmax reducen espacio y tiempo hasta
    # dejar un unico valor escalar.
    vmin = float(cdo_run(["output", "-fldmin", "-timmin", path]).split()[-1])
    vmax = float(cdo_run(["output", "-fldmax", "-timmax", path]).split()[-1])
    return vmin, vmax


def n_timesteps(path: str) -> int:
    return int(cdo_run(["ntime", path]).strip().splitlines()[-1])


def split_model_experiment(stem: str) -> tuple[str, str]:
    name = stem.replace("tos_", "", 1)
    for exp in EXPECTED_YEARS:
        suffix = f"_{exp}"
        if name.endswith(suffix):
            return name[: -len(suffix)], exp
    return name, "unknown"


def main(in_dir: str, out_csv: str) -> None:
    rows = []
    for f in sorted(Path(in_dir).glob("tos_*.nc")):
        model, exp = split_model_experiment(f.stem)
        try:
            vmin, vmax = field_minmax(str(f))
            ntime = n_timesteps(str(f))
        except subprocess.CalledProcessError as e:
            rows.append({
                "file": f.name, "model": model, "experiment": exp,
                "min_sst": "", "max_sst": "", "n_months": "",
                "ok_range": False, "ok_length": False,
                "status": "ERROR_CDO", "detail": str(e),
            })
            continue

        ok_range = MIN_SST <= vmin and vmax <= MAX_SST
        expected_years = EXPECTED_YEARS.get(exp)
        ok_length = (
            True if expected_years is None
            else ntime >= expected_years * 12 * LENGTH_TOLERANCE
        )
        rows.append({
            "file": f.name, "model": model, "experiment": exp,
            "min_sst": vmin, "max_sst": vmax, "n_months": ntime,
            "ok_range": ok_range, "ok_length": ok_length,
            "status": "PASS" if (ok_range and ok_length) else "FAIL",
            "detail": "",
        })

    if not rows:
        sys.exit(f"08_qc_checks.py: no se encontraron archivos tos_*.nc en {in_dir}")

    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    n_fail = sum(1 for r in rows if r["status"] != "PASS")
    print(f"QC escrito en {out_csv} ({len(rows)} archivos, {n_fail} con fallas)", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("uso: 06_qc_checks.py <dir_con_tos_*.nc> <out_qc.csv>")
    main(sys.argv[1], sys.argv[2])
