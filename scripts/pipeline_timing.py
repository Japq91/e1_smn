#!/usr/bin/env python3
"""Registro y estimacion de tiempos del pipeline.

Dos logs, ambos append-only, en logs/ (no se versionan, son por
maquina -- ver .gitignore):

  - step_timings.csv: una fila por CADA corrida de run_step en run.sh
    (00, 00b, 01, 02, 03, 04, 05, 06, 07), con su duracion real. Un
    paso idempotente que ya tenia todo hecho tarda casi nada -- esas
    corridas NO se usan para estimar (ver MIN_MEANINGFUL_STEP_SECONDS),
    solo las que hicieron trabajo real.
  - download_timings.csv: una fila por combinacion modelo+experimento
    efectivamente descargada (nunca se registra un modelo que ya
    estaba en disco, ver 02_download_cmip6_chunks.sh). La duracion de
    descarga depende sobre todo del experimento (largo del periodo),
    no tanto del modelo puntual, asi que el estimado promedia POR
    EXPERIMENTO.

Uso desde Bash (run.sh, 02_download_cmip6_chunks.sh):
    python3 scripts/pipeline_timing.py record_step <paso> <segundos>
    python3 scripts/pipeline_timing.py record_download <modelo> <exp> <segundos>

Uso desde Python (preflight_report.py):
    import pipeline_timing as pt
    pt.estimate_step_seconds("00b")               # segundos o None
    pt.estimate_download_seconds(pendientes)      # ver mas abajo
    pt.format_duration(segundos)                  # "2h 15min"
    pt.backfill_download_timings_from_mtimes(...) # ver mas abajo
"""
import csv
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "logs"
STEP_TIMINGS_CSV = LOGS_DIR / "step_timings.csv"
DOWNLOAD_TIMINGS_CSV = LOGS_DIR / "download_timings.csv"

# Un paso que tarda menos que esto casi seguro fue un "skip" idempotente
# (ya estaba todo hecho), no trabajo real -- no sirve como muestra para
# estimar cuanto tarda la primera vez que se corre de verdad.
MIN_MEANINGFUL_STEP_SECONDS = 5.0


def _append_row(path: Path, fieldnames: list[str], row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def _read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def record_step(step: str, seconds: float) -> None:
    _append_row(STEP_TIMINGS_CSV, ["step", "seconds"], {"step": step, "seconds": f"{seconds:.1f}"})


def record_download(model: str, exp: str, seconds: float, source: str = "measured") -> None:
    _append_row(DOWNLOAD_TIMINGS_CSV, ["model", "experiment", "seconds", "source"],
                {"model": model, "experiment": exp, "seconds": f"{seconds:.1f}", "source": source})


def backfill_download_timings_from_mtimes(raw_dir: Path) -> int:
    """Reconstruye una duracion APROXIMADA para descargas que ya estan
    en disco de antes de que este log existiera (por ejemplo, la
    primera vez que se corre esto en una maquina que ya venia
    descargando modelos). Se usa solo si download_timings.csv todavia
    no existe -- una vez que hay aunque sea una medicion real, no se
    vuelve a intentar (para no pisar datos reales con aproximaciones).

    Idea: 02_download_cmip6_chunks.sh descarga secuencial, sin
    paralelismo, un chunk a la vez -- para un modelo+experimento con 2
    o mas archivos, la diferencia entre el mas viejo y el mas nuevo
    (fecha de modificacion) aproxima bien cuanto tardo esa descarga.
    Con un solo archivo no hay forma de inferir nada (no hay 'inicio'
    de referencia dentro de esa misma carpeta), se omite -- para esos
    la estimacion mejora sola a medida que se descarguen mas modelos
    nuevos (registro real, no aproximado).

    Devuelve cuantas combinaciones modelo+experimento se pudieron
    reconstruir asi."""
    if DOWNLOAD_TIMINGS_CSV.exists() or not raw_dir.exists():
        return 0

    n = 0
    for model_dir in sorted(p for p in raw_dir.iterdir() if p.is_dir()):
        for exp_dir in sorted(p for p in model_dir.iterdir() if p.is_dir()):
            files = list(exp_dir.glob("*.nc"))
            if len(files) < 2:
                continue
            mtimes = [f.stat().st_mtime for f in files]
            duration = max(mtimes) - min(mtimes)
            if duration <= 0:
                continue
            record_download(model_dir.name, exp_dir.name, duration, source="backfill_mtime")
            n += 1
    return n


def format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, s = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}min" + (f" {s}s" if s else "")
    hours, m = divmod(minutes, 60)
    return f"{hours}h" + (f" {m}min" if m else "")


def estimate_step_seconds(step: str) -> float | None:
    """Promedio de las corridas 'reales' (no idempotente-skip) de ese
    paso en ESTA maquina, o None si nunca corrio de verdad todavia."""
    rows = _read_rows(STEP_TIMINGS_CSV)
    samples = [float(r["seconds"]) for r in rows
               if r["step"] == step and float(r["seconds"]) >= MIN_MEANINGFUL_STEP_SECONDS]
    if not samples:
        return None
    return sum(samples) / len(samples)


def estimate_download_seconds(pending: list[tuple[str, str]]) -> tuple[float | None, dict[str, int]]:
    """(segundos_estimados_totales, {experimento: cantidad_sin_dato_historico})

    pending: lista de (modelo, experimento) que todavia faltan
    descargar. Usa el promedio observado POR EXPERIMENTO en esta
    maquina. Los experimentos sin ninguna muestra previa quedan afuera
    del estimado (no se puede promediar de la nada) y se cuentan
    aparte en el segundo valor devuelto."""
    rows = _read_rows(DOWNLOAD_TIMINGS_CSV)
    by_exp: dict[str, list[float]] = {}
    for r in rows:
        by_exp.setdefault(r["experiment"], []).append(float(r["seconds"]))
    avg_by_exp = {exp: sum(vals) / len(vals) for exp, vals in by_exp.items()}

    total = 0.0
    any_estimated = False
    missing_data: dict[str, int] = {}
    for _model, exp in pending:
        if exp in avg_by_exp:
            total += avg_by_exp[exp]
            any_estimated = True
        else:
            missing_data[exp] = missing_data.get(exp, 0) + 1

    return (total if any_estimated else None), missing_data


if __name__ == "__main__":
    usage = "uso: pipeline_timing.py {record_step <paso> <seg> | record_download <modelo> <exp> <seg>}"
    if len(sys.argv) < 2:
        sys.exit(usage)
    cmd = sys.argv[1]
    if cmd == "record_step" and len(sys.argv) == 4:
        record_step(sys.argv[2], float(sys.argv[3]))
    elif cmd == "record_download" and len(sys.argv) == 5:
        record_download(sys.argv[2], sys.argv[3], float(sys.argv[4]))
    else:
        sys.exit(usage)
