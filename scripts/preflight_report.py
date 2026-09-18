#!/usr/bin/env python3
"""Reporte preflight (paso 00 de run.sh, siempre, sin importar
STEP_FROM/STEP_TO): antes de correr nada, muestra que artefactos ya
existen y cuales faltan, con una estimacion de cuanto puede tardar
completarlos -- basada en corridas anteriores REALES en esta misma
maquina (logs/step_timings.csv, logs/download_timings.csv, ver
scripts/pipeline_timing.py). Si todavia no hay corridas previas, avisa
que no hay estimado en vez de inventar un numero.

Uso:
    python3 preflight_report.py [MAX_MODELS]
"""
import csv
import sys
from pathlib import Path

import pipeline_config
import pipeline_timing as pt

BASE_DIR = Path(__file__).resolve().parent.parent
SEED_CSV = BASE_DIR / "config/models_seed_cmip6.csv"
CATALOG_CSV = BASE_DIR / "data/interim/models_catalog_status.csv"
ERSSTV5 = BASE_DIR / "data/raw/ersstv5/ersstv5_region.nc"
MASKED_DIR = BASE_DIR / "data/processed/masked"
QC_CSV = BASE_DIR / "data/processed/qc_report.csv"
INVENTORY_CSV = BASE_DIR / "data/processed/models_inventory_final.csv"
RAW_DIR = BASE_DIR / "data/raw/cmip6"


def status_line(step: str, label: str, exists: bool) -> str:
    if exists:
        return f"[OK]    {step:<5} {label}"
    est = pt.estimate_step_seconds(step)
    hint = (f"~{pt.format_duration(est)} (promedio de corridas anteriores en esta maquina)"
            if est is not None else "sin corridas previas en esta maquina, no se puede estimar")
    return f"[FALTA] {step:<5} {label} -- {hint}"


def complete_models() -> list[str]:
    if not CATALOG_CSV.exists():
        return []
    with open(CATALOG_CSV, newline="") as f:
        return [r["model"] for r in csv.DictReader(f) if r.get("complete") == "True"]


def pending_downloads(models: list[str], experiments: list[str]) -> list[tuple[str, str]]:
    pending = []
    for model in models:
        for exp in experiments:
            exp_dir = RAW_DIR / model / exp
            if not (exp_dir.is_dir() and any(exp_dir.glob("*.nc"))):
                pending.append((model, exp))
    return pending


def main(max_models: int | None) -> None:
    lines = ["", "=== Estado antes de esta corrida (run.sh) ==="]

    lines.append(status_line("00b", "config/models_seed_cmip6.csv (lista de modelos)", SEED_CSV.exists()))
    lines.append(status_line("01", "data/interim/models_catalog_status.csv (catalogo ESGF)", CATALOG_CSV.exists()))

    models = complete_models()
    if max_models is not None:
        models = models[:max_models]
    experiments = pipeline_config.experiments()
    total_pairs = len(models) * len(experiments)

    if not CATALOG_CSV.exists():
        lines.append("[FALTA] 02    Descarga CMIP6 -- depende del catalogo (paso 01)")
        lines.append("[FALTA] 04/05 Grilla comun + mascara -- depende de la descarga (paso 02)")
    else:
        # Si esta maquina ya tenia modelos descargados de antes de que
        # existiera este log de tiempos, se reconstruye una aproximacion
        # a partir de las fechas de los archivos -- para no arrancar
        # de cero pudiendo estimar con lo que ya hay en disco.
        n_backfilled = pt.backfill_download_timings_from_mtimes(RAW_DIR)
        if n_backfilled:
            lines.append(f"(sin registro de tiempos de descarga todavia -- se reconstruyeron "
                         f"{n_backfilled} duraciones aproximadas a partir de descargas previas en disco)")

        pending = pending_downloads(models, experiments)
        done_pairs = total_pairs - len(pending)
        if not pending:
            lines.append(f"[OK]    02    Descarga CMIP6: {done_pairs}/{total_pairs} combinaciones modelo x experimento")
        else:
            by_exp_count: dict[str, int] = {}
            for _m, exp in pending:
                by_exp_count[exp] = by_exp_count.get(exp, 0) + 1
            breakdown = ", ".join(f"{exp}: {n}" for exp, n in by_exp_count.items())
            lines.append(f"[FALTA] 02    Descarga CMIP6: {done_pairs}/{total_pairs} combinaciones "
                         f"({breakdown} pendientes)")
            est_seconds, missing_by_exp = pt.estimate_download_seconds(pending)
            if est_seconds is not None:
                extra = ""
                if missing_by_exp:
                    faltantes = ", ".join(f"{exp} ({n})" for exp, n in missing_by_exp.items())
                    extra = f" -- sin estimado todavia para: {faltantes} (nunca se descargo ninguno de esos aca)"
                lines.append(f"          Estimado para completar lo pendiente: ~{pt.format_duration(est_seconds)}{extra}")
            else:
                lines.append("          Sin descargas previas en esta maquina, no se puede estimar cuanto falta")

        n_masked = len(list(MASKED_DIR.glob("tos_*.nc"))) if MASKED_DIR.exists() else 0
        if total_pairs and n_masked >= total_pairs:
            lines.append(f"[OK]    04/05 Grilla comun + mascara: {n_masked}/{total_pairs} archivos")
        else:
            lines.append(status_line("04/05", f"Grilla comun + mascara: {n_masked}/{total_pairs} archivos", False))

    lines.append(status_line("03", "data/raw/ersstv5/ersstv5_region.nc (observado)", ERSSTV5.exists()))
    lines.append(status_line("06", "data/processed/qc_report.csv (control de calidad)", QC_CSV.exists()))
    lines.append(status_line("07", "data/processed/models_inventory_final.csv (inventario final)", INVENTORY_CSV.exists()))
    lines.append("=" * 46)
    lines.append("")

    print("\n".join(lines), file=sys.stderr)


if __name__ == "__main__":
    max_models_arg = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] else None
    main(max_models_arg)
