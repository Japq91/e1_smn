#!/usr/bin/env python3
"""Genera un reporte de estado en texto plano al final de cada corrida
de run.sh (paso final, se ejecuta siempre, sin importar STEP_FROM/
STEP_TO). Deja constancia de que modelos ya estan descargados,
descargados-pero-sin-procesar, procesados, y pendientes via fuentes
alternativas -- para no tener que adivinar el estado del pipeline entre
corridas.

Uso:
    generate_status_report.py <catalog_csv> <raw_dir> <interim_dir>
        <masked_dir> <out_txt> <start_ts> <end_ts> [--downloading]
"""
import csv
import sys
from pathlib import Path

EXPS = ("historical", "ssp245", "ssp585")


def main() -> None:
    (catalog_csv, raw_dir, _interim_dir, masked_dir,
     out_txt, start_ts, end_ts) = sys.argv[1:8]
    downloading = "--downloading" in sys.argv[8:]

    with open(catalog_csv, newline="") as f:
        rows = list(csv.DictReader(f))

    complete_models = sorted(r["model"] for r in rows if r.get("complete") == "True")
    no_encontrado = sorted(r["model"] for r in rows if r.get("fuente") == "no_encontrado")
    copernicus_parcial = sorted(r["model"] for r in rows if r.get("fuente") == "copernicus_parcial")

    downloaded_full, downloaded_partial, not_downloaded = [], [], []
    for model in complete_models:
        model_dir = Path(raw_dir) / model
        n_present = sum(
            1 for exp in EXPS
            if (model_dir / exp).is_dir() and any((model_dir / exp).glob("*.nc"))
        )
        if n_present == len(EXPS):
            downloaded_full.append(model)
        elif n_present > 0:
            downloaded_partial.append(model)
        else:
            not_downloaded.append(model)

    masked_dir_path = Path(masked_dir)
    processed = []
    pending_process = []
    for model in downloaded_full:
        n_masked = sum(1 for exp in EXPS if (masked_dir_path / f"tos_{model}_{exp}.nc").exists())
        if n_masked == len(EXPS):
            processed.append(model)
        else:
            pending_process.append(model)

    def section(title: str, items: list[str]) -> list[str]:
        out = [f"{title}: {len(items)}"]
        out += [f"  {m}" for m in items]
        out.append("")
        return out

    lines = [
        "Reporte de estado -- run.sh",
        f"Inicio: {start_ts}",
        f"Fin:    {end_ts}",
        "",
        f"Descarga ya en curso en otro proceso al momento de esta corrida (no se lanzo otra): {'SI' if downloading else 'NO'}",
        "",
    ]
    lines += section("Modelos completamente descargados (3/3 experimentos)", downloaded_full)
    lines += section("Modelos con descarga parcial (1-2 de 3 experimentos)", downloaded_partial)
    lines += section("Modelos descargados y ya procesados (data/processed/masked)", processed)
    lines += section("Modelos descargados pero AUN sin procesar (se procesan en el proximo 04-07)", pending_process)
    lines += section("Modelos no encontrados en ESGF (candidatos a 02b/02c en la proxima corrida)", no_encontrado)
    lines += section("Modelos con descarga parcial via Copernicus CDS", copernicus_parcial)

    Path(out_txt).write_text("\n".join(lines) + "\n")
    print(f"Reporte de estado escrito en {out_txt}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 8:
        sys.exit(
            "uso: generate_status_report.py <catalog_csv> <raw_dir> <interim_dir> "
            "<masked_dir> <out_txt> <start_ts> <end_ts> [--downloading]"
        )
    main()
