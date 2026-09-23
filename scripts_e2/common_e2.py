#!/usr/bin/env python3
"""Utilidades compartidas por los scripts p01_*.py, p02_*.py, etc. de
E2 -- mismo patron que scripts/plot_common.py en E1 (helpers
compartidos, cada script pXX sigue siendo ejecutable por separado, no
depende de que otro pXX haya corrido antes).

No define REF_INICIO/REF_FIN: cada script pXX tiene su propia
constante editable, a proposito (ver conversacion -- si un calculo
necesita otro periodo de referencia, se cambia solo ahi, sin afectar
a los demas).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parent.parent
MASKED = ROOT / "data/processed/masked"
E2_DIR = ROOT / "data/processed/e2"
MODEL_REGISTRY_E2 = E2_DIR / "model_registry_e2.csv"

sys.path.insert(0, str(ROOT / "scripts"))
import plot_common as pc  # reusa NINO34/NINO12 (config/domains.yaml) -- una sola fuente de verdad

NINO34 = pc.NINO34
NINO12 = pc.NINO12
# Banda tropical para la TSM media que necesita RONI (convencion NOAA
# CPC: 20S-20N, todas las cuencas).
TROPICAL = dict(lon1=0, lon2=360, lat1=-20, lat2=20)

BOXES = {"nino34": NINO34, "nino12": NINO12, "tropical": TROPICAL}
WEIGHTED = {"nino34": False, "nino12": False, "tropical": True}


def read_model_registry():
    """[{'number': 'M01', 'model': 'ACCESS-CM2', ...}, ...] -- ver
    data/processed/e2/README.md para las columnas."""
    if not MODEL_REGISTRY_E2.exists():
        sys.exit(f"Falta {MODEL_REGISTRY_E2}. Generarlo antes (ver data/processed/e2/README.md).")
    return pd.read_csv(MODEL_REGISTRY_E2).to_dict("records")


def model_path(model, exp="historical"):
    return MASKED / f"tos_{model}_{exp}.nc"


def obs_path():
    return MASKED / "ersstv5_region.nc"


def _select_box(da, box):
    sub = da.sel(lat=slice(box["lat1"], box["lat2"]), lon=slice(box["lon1"], box["lon2"]))
    if sub.lat.size == 0:  # lat descendente en el archivo: invertir el slice
        sub = da.sel(lat=slice(box["lat2"], box["lat1"]), lon=slice(box["lon1"], box["lon2"]))
    return sub


def _normalize_time(da):
    """Fuerza el tiempo a Timestamp de pandas, dia-1-del-mes, sin
    importar el calendario nativo del archivo (algunos modelos CMIP6
    usan noleap/360_day -- xarray los decodifica como CFTimeIndex, no
    comparable directamente contra ERSSTv5). Reconstruye la fecha
    desde .year/.month (atributos que cftime y pandas comparten)."""
    idx = da.indexes["time"]
    nuevas = pd.to_datetime([f"{t.year:04d}-{t.month:02d}-01" for t in idx])
    return da.assign_coords(time=nuevas)


def box_series(path, box, varname, weighted=False):
    """Serie temporal promediada espacialmente dentro de 'box'.
    weighted=True pondera por cos(lat) (banda TROPICAL, ancha);
    weighted=False (default) es el promedio simple (Nino3.4/Nino1+2,
    cajas angostas cerca del ecuador, mismo criterio que
    scripts/plot_common.box_mean)."""
    ds = xr.open_dataset(path)
    sub = _select_box(ds[varname], box)
    if not weighted:
        out = sub.mean(dim=("lat", "lon"))
    else:
        w = np.cos(np.deg2rad(sub.lat))
        out = sub.weighted(w).mean(dim=("lat", "lon"))
    return _normalize_time(out)


def field_time_mean(path, varname, y0, y1):
    """Media temporal del campo 2D COMPLETO (lat, lon) -- sin recortar
    a ninguna caja -- sobre [y0, y1]. Dominio igual al del archivo de
    entrada (data/processed/masked/*.nc: lat -30/30, lon global)."""
    ds = xr.open_dataset(path)
    da = _normalize_time(ds[varname])
    return da.sel(time=slice(f"{y0}", f"{y1}")).mean(dim="time")


def field_anomaly_std(path, varname, y0, y1):
    """Desviacion estandar de la ANOMALIA del campo 2D completo, sobre
    [y0, y1] -- climatologia propia del dataset calculada en ese mismo
    periodo, sin LS (mismo criterio que el resto de E2). Sobre la
    anomalia, no el valor crudo: si se usara el valor crudo, la
    diferencia de sigma quedaria dominada por el ciclo anual (que casi
    no difiere entre datasets), tapando la variabilidad interanual
    real que interesa comparar."""
    ds = xr.open_dataset(path)
    da = _normalize_time(ds[varname])
    ref = da.sel(time=slice(f"{y0}", f"{y1}"))
    clim = ref.groupby("time.month").mean("time")
    anom = ref.groupby("time.month") - clim
    return anom.std(dim="time", ddof=1)


def field_anomaly(path, varname, y0, y1):
    """Anomalia del campo 2D completo (time, lat, lon) sobre [y0, y1]
    -- climatologia propia del dataset en ese mismo periodo, sin LS.
    A diferencia de field_anomaly_std, devuelve el campo completo (no
    solo su sigma), para poder correlacionar punto a punto contra otro
    campo (ver p06_correlacion.py)."""
    ds = xr.open_dataset(path)
    da = _normalize_time(ds[varname])
    ref = da.sel(time=slice(f"{y0}", f"{y1}"))
    clim = ref.groupby("time.month").mean("time")
    return ref.groupby("time.month") - clim


def lag1_autocorr(da, dim="time"):
    """Autocorrelacion lag-1, por POSICION (no por etiqueta de fecha):
    xr.align(a, b) con a=da[:-1], b=da[1:] empareja por valor de
    coordenada de tiempo, y como casi todas las fechas de a tambien
    estan en b, terminaria comparando (casi) la serie consigo misma en
    la MISMA fecha, no con el paso anterior -- r1 saldria ~1 en todos
    lados (bug real, detectado en el notebook de pruebas al ver un
    mapa de significancia sin ningun punto marcado). Se opera sobre
    arrays numpy por indice, sin coordenadas."""
    vals = da.values
    a, b = vals[:-1], vals[1:]
    a_mean, b_mean = np.nanmean(a, axis=0), np.nanmean(b, axis=0)
    cov = np.nanmean((a - a_mean) * (b - b_mean), axis=0)
    r1 = cov / (np.nanstd(a, axis=0) * np.nanstd(b, axis=0))
    if da.ndim > 1:
        other_dims = [d for d in da.dims if d != dim]
        coords = {k: v for k, v in da.coords.items() if dim not in v.dims}
        return xr.DataArray(r1, dims=other_dims, coords=coords)
    return float(r1)


def climatology(da, ref_inicio, ref_fin):
    """C_m = media mensual multi-anual sobre [ref_inicio, ref_fin]."""
    ref = da.sel(time=slice(f"{ref_inicio}", f"{ref_fin}"))
    return ref.groupby("time.month").mean("time")


def anomaly(da, clim):
    """A(y,m) = X(y,m) - C_m. Sin correccion Linear Scaling -- LS se
    probo y se descarto (resta constante por mes que se cancela sola
    en cualquier anomalia, ver scripts_e2/README.md)."""
    return da.groupby("time.month") - clim


def pearson_r(model_da, obs_da):
    """Correlacion de Pearson, no Spearman: la identidad de Taylor
    (E'^2 = sigma_f^2 + sigma_r^2 - 2*sigma_f*sigma_r*r) se deriva de
    la covarianza -- solo vale para Pearson, Spearman (basado en
    rangos) no tiene esa relacion algebraica con la varianza de la
    diferencia (ver informe/borradores/marco_teorico_e2.txt)."""
    m, o = xr.align(model_da, obs_da, join="inner")
    return float(xr.corr(m, o))


def rolling3(da):
    return da.rolling(time=3, center=True).mean()


def oni_index(nino34_da, clim_da):
    """ONI = media movil de 3 meses de la anomalia (Trenberth, 1997)."""
    return rolling3(anomaly(nino34_da, clim_da))


def roni_index(oni_da, tropical_da, clim_tropical_da):
    """RONI = ONI - anomalia tropical (rolling 3m), reescalado para que
    su varianza iguale a la del ONI original (definicion oficial NOAA
    CPC; candidata academica: van Oldenborgh et al. 2021, ver
    informe/borradores/marco_teorico_e2.txt Seccion 8)."""
    a_trop = anomaly(tropical_da, clim_tropical_da)
    raw = oni_da - rolling3(a_trop)
    m_oni, m_raw = xr.align(oni_da, raw, join="inner")
    scale = float(m_oni.std(ddof=1) / m_raw.std(ddof=1))
    return raw * scale


def icen_index(nino12_da, clim_da):
    """ICEN = media movil de 3 meses de la anomalia en Nino1+2
    (Takahashi & Reupo, 2015)."""
    return rolling3(anomaly(nino12_da, clim_da))


def find_indices_csv(ref_inicio, ref_fin):
    """Ubica el CSV de indices que escribio p01_indices_enso.py para
    ese periodo de referencia (el nombre incluye ademas la ventana
    real de datos, que p01 calcula solo -- se busca por patron)."""
    import glob
    pattern = str(E2_DIR / f"indices_enso_*_ref{ref_inicio}-{ref_fin}.csv")
    matches = sorted(glob.glob(pattern))
    if not matches:
        sys.exit(f"Falta {pattern}. Correr antes p01_indices_enso.py con REF_INICIO={ref_inicio}, REF_FIN={ref_fin}.")
    return matches[-1]


def obs_indices(ref_inicio, ref_fin):
    """indices_enso_*.csv (p01) deliberadamente NO incluye ERSSTv5
    (columnas solo M01..M40, pedido explicito del usuario) -- se
    recalculan aca los 3 indices de obs, para poder comparar cada
    modelo contra obs (usado por p07_eventos.py y
    p08_taylor_compuesto.py)."""
    series = {k: box_series(obs_path(), box, "sst", weighted=WEIGHTED[k]) for k, box in BOXES.items()}
    clim = {k: climatology(v, ref_inicio, ref_fin) for k, v in series.items()}
    oni = oni_index(series["nino34"], clim["nino34"])
    roni = roni_index(oni, series["tropical"], clim["tropical"])
    icen = icen_index(series["nino12"], clim["nino12"])
    return pd.DataFrame({"OBS_ONI": oni.to_pandas(), "OBS_RONI": roni.to_pandas(), "OBS_ICEN": icen.to_pandas()})


def load_all_indices(ref_inicio, ref_fin):
    """Indices de los 40 modelos (CSV de p01) + OBS (recalculado aca) en
    un solo DataFrame, indexado por tiempo."""
    df = pd.read_csv(find_indices_csv(ref_inicio, ref_fin), index_col="time", parse_dates=True)
    return df.join(obs_indices(ref_inicio, ref_fin), how="left")


def taylor_stats_arrays(model_vals, obs_vals):
    """Igual que pearson_r/rmse pero sobre arrays numpy simples (no
    xarray con dim 'time') -- para comparar curvas compuestas
    (p08_taylor_compuesto.py), donde el eje ya no es fecha calendario
    sino 'meses relativos al pico'. Sin NaN esperado (los eventos con
    ventana incompleta se descartan antes, no se rellenan)."""
    m = np.asarray(model_vals, dtype=float)
    o = np.asarray(obs_vals, dtype=float)
    sigma_f = float(np.std(m, ddof=1))
    sigma_r = float(np.std(o, ddof=1))
    r = float(np.corrcoef(m, o)[0, 1])
    mc, oc = m - m.mean(), o - o.mean()
    rmse_c = float(np.sqrt(np.mean((mc - oc) ** 2)))
    return dict(sigma=sigma_f, r=r, rmse_centrado=rmse_c, sigma_norm=sigma_f / sigma_r)


def rmse(model_da, obs_da, centered=False):
    """centered=True: cada serie menos su propia media antes de
    comparar -- aisla el error de patron/variabilidad del error de
    sesgo medio (que se reporta aparte, ver p03_sesgo.py). Es el que
    entra en el diagrama de Taylor, no el RMSE total."""
    m, o = xr.align(model_da, obs_da, join="inner")
    if centered:
        m = m - m.mean()
        o = o - o.mean()
    return float(np.sqrt(((m - o) ** 2).mean()))
