# Historia de la descarga de CMIP6 — pipeline SST (Niño 1+2 / Niño 3.4)

Este documento reconstruye, con el mayor detalle posible, cómo se obtuvo el dato crudo de CMIP6 usado en este proyecto: qué modelos se consiguieron por la vía regular (ESGF, nodo principal, primer mirror listado), cuáles necesitaron mirrors alternativos dentro de la misma federación ESGF, cuáles requirieron un miembro de ensamble distinto al preferido, qué bugs de procesamiento aparecieron y cómo se resolvieron, y qué caminos se probaron (Copernicus CDS, nodos de búsqueda alternativos) sin llegar a aportar un modelo nuevo al inventario final.

**Estado final: 48 modelos completos (historical + ssp245 + ssp585), 47 seleccionados tras control de calidad**, de un universo de 102 modelos candidatos (46 de la semilla original de vocabulario CMIP6 + 56 citados en la literatura del proyecto).

---

## 1. Línea de tiempo

| Fecha | Evento |
|---|---|
| **19–20 jul** | Desarrollo original del pipeline (pasos 00–07, `run.sh`). Primeras corridas de prueba (`test_run2` a `test_run18`). Se identifica y corrige el bug de duplicación de miembros de ensamble sin fijar `variant_label`. |
| **20 jul, tarde** | Primer intento sistemático de Copernicus CDS (`copernicus_batch1.log`): bloqueado inicialmente por licencia no aceptada (`projections-cmip6`); se resuelve manualmente y se logra descargar `HadGEM3-GC31-MM` (historical, 15.6 GB) y avanzar en otros modelos antes de que el lote se interrumpiera en `SAM0-UNICON` (`404` al consultar el job). |
| **22 jul, 12:10** | Corrida completa de ESGF (nodo principal) reportada como `Entregable 1 completo` — 127 GB descargados, la mayoría de los 47 modelos "completos" del catálogo ya presentes, con huecos puntuales en 9 modelos (ver §3). |
| **22 jul, tarde** | Se verifica el estado de la descarga y se identifican los primeros huecos: `download_failures.log` acumulaba cientos de fallos, la mayoría de corridas de prueba anteriores ya resueltas; el análisis fino (comparando `esgf_file_urls.json` contra disco) deja **298 archivos realmente faltantes** en 5 modelos (`EC-Earth3`, `EC-Earth3-CC`, `EC-Earth3-Veg`, `EC-Earth3-Veg-LR`, `TaiESM1`). |
| **22 jul, noche** | Segundo lote de Copernicus CDS (14 modelos, lista blanca verificada a mano contra el sitio para `ssp245`): solo 2 historicals (`IPSL-CM5A2-INCA`, `SAM0-UNICON`) y 1 ssp245 (`CESM2`) tienen éxito; el resto falla con `RoocsValueError` — CDS no espeja esos modelos/experimentos. |
| **23 jul** | Se descubre que el nodo `esgf-data04.diasjp.net` (Japón), único mirror guardado para la mayoría de los 298 archivos faltantes, está **completamente caído** (timeout TCP, no solo error HTTP). Se consultan 6 nodos ESGF adicionales y se agregan **10.867 URLs de mirrors nuevos**. Reintento dirigido: **286 de 289 archivos recuperados**. Se ejecuta `02b_search_alt_esgf_nodes.py` sobre los 44 modelos `no_encontrado`: **0 resueltos** (ningún nodo alternativo los tiene tampoco, con excepción de un nodo, IPSL, que respondió `500` en las 44 consultas). |
| **23 jul** | Se identifican y corrigen dos bugs de procesamiento (paso 04): `IPSL-CM6A-LR` (variable auxiliar `area` sin atributo `coordinates`, malla curvilínea tripolar — fix: `selvar,tos` como primer paso) y `KIOST-ESM` (malla nativa distinta entre `historical` y `ssp245`/`ssp585` — fix: pesos de regrilla propios por periodo como *fallback*). |
| **24 jul** | Se automatiza la cascada de descarga (`02_download_all_sources.sh`: ESGF principal → ESGF alternativo → Copernicus, esta última acotada a una lista blanca de 28 modelos). Se agrega reporte de estado por corrida y guardia contra descargas duplicadas. Un refresco completo del catálogo (`00b`+`01`, disparado fuera de esta sesión) borra accidentalmente el enriquecimiento de horas de trabajo; se restaura desde respaldo y se corrige `01_query_esgf_catalog.py` para fusionar en vez de sobreescribir. |
| **24 jul, tarde** | A partir de evidencia externa (búsqueda del usuario en el sitio de ESGF/Copernicus), se descubre que **`CESM2`** sí tiene los 3 experimentos disponibles bajo el miembro `r4i1p1f1` (el preferido, `r1i1p1f1`, publica `historical` en malla `gn` pero `ssp245`/`ssp585` en `gr` — inconsistencia real de ESGF). Se resuelve, descarga y procesa. |
| **24 jul, noche** | Se identifica que **`KACE-1-0-G`** tenía el mismo problema del nodo DIAS caído (único mirror para su archivo `historical`, más un segundo mirror coreano también caído). Se localizan mirrors vivos en CEDA/NCI/DKRZ y se completa la descarga. |

---

## 2. Modelos descargados por la vía regular

Estos **39 modelos** se encontraron completos en el nodo principal de ESGF (LLNL) desde la primera consulta, con el primer mirror listado funcionando sin intervención adicional:

| Modelo | Grid | Miembro |
|---|---|---|
| ACCESS-CM2 | gn | r1i1p1f1 |
| ACCESS-ESM1-5 | gn | r1i1p1f1 |
| AWI-CM-1-1-MR | gn | r1i1p1f1 |
| BCC-CSM2-MR | gn | r1i1p1f1 |
| CAMS-CSM1-0 | gn | r1i1p1f1 |
| CAS-ESM2-0 | gn | r1i1p1f1 |
| CESM2-WACCM | gn | r1i1p1f1 |
| CMCC-CM2-SR5 | gn | r1i1p1f1 |
| CMCC-ESM2 | gn | r1i1p1f1 |
| CNRM-CM6-1 | gn | r1i1p1f2 |
| CNRM-CM6-1-HR | gn | r1i1p1f2 |
| CNRM-ESM2-1 | gn | r1i1p1f2 |
| CanESM5 | gn | r1i1p1f1 |
| CanESM5-CanOE | gn | r1i1p2f1 |
| FGOALS-f3-L | gn | r1i1p1f1 |
| FGOALS-g3 | gn | r1i1p1f1 |
| FIO-ESM-2-0 | gn | r1i1p1f1 |
| GFDL-CM4 | gn | r1i1p1f1 |
| GFDL-ESM4 | gn | r1i1p1f1 |
| GISS-E2-1-G | gn | r1i1p5f1 |
| GISS-E2-1-H | gn | r1i1p3f1 |
| GISS-E2-2-G | gn | r1i1p3f1 |
| HadGEM3-GC31-LL | gn | r1i1p1f3 |
| IITM-ESM | gn | r1i1p1f1 |
| INM-CM4-8 | gr1 | r1i1p1f1 |
| INM-CM5-0 | gr1 | r1i1p1f1 |
| IPSL-CM6A-LR* | gn | r1i1p1f1 |
| KIOST-ESM* | gr1 | r1i1p1f1 |
| MCM-UA-1-0 | gn | r1i1p1f2 |
| MIROC-ES2H | gn | r1i1p4f2 |
| MIROC-ES2L | gn | r1i1p1f2 |
| MIROC6 | gn | r1i1p1f1 |
| MPI-ESM1-2-HR | gn | r1i1p1f1 |
| MPI-ESM1-2-LR | gn | r1i1p1f1 |
| MRI-ESM2-0 | gn | r1i1p1f1 |
| NESM3 | gn | r1i1p1f1 |
| NorESM2-LM | gn | r1i1p1f1 |
| NorESM2-MM | gn | r1i1p1f1 |
| UKESM1-0-LL | gn | r1i1p1f2 |

`*` `IPSL-CM6A-LR` y `KIOST-ESM` se descargaron sin problema, pero **fallaron en el paso 04** (regrillado) por bugs de procesamiento — ver §4. No tuvieron que buscarse en otro lugar, el archivo crudo siempre estuvo bien.

Nota: casi todos publican bajo `gn` (malla nativa del modelo, "grid native"); `INM-CM4-8`, `INM-CM5-0` y `KIOST-ESM` publican en `gr1` (grilla regular remallada por el propio centro de modelado, variante 1). El miembro de ensamble varía bastante entre instituciones — varios (GISS, CNRM, HadGEM3, UKESM1, MIROC-ES2*, CanESM5-CanOE, MCM-UA-1-0) no usan el más común `r1i1p1f1` porque ese miembro específico no publicó los 3 experimentos a la vez; el paso 01 los detecta automáticamente probando la intersección de miembros disponible en `historical` ∩ `ssp245` ∩ `ssp585`.

---

## 3. Modelos que requirieron mirrors alternativos (dentro de ESGF)

Estos modelos **sí están en ESGF y bajo el mismo miembro preferido**, pero el único mirror que nuestro catálogo tenía guardado para algunos de sus archivos estaba caído. La causa raíz común: **`esgf-data04.diasjp.net` / `esgf-data02.diasjp.net`** (nodo DIAS, Japón) no respondía (timeout de conexión TCP, no un error HTTP — el servidor simplemente no contestaba), y para varios archivos era el **único** mirror registrado.

| Modelo | Grid | Miembro | Archivos afectados | Mirror que funcionó |
|---|---|---|---|---|
| `EC-Earth3` | gn | r1i1p1f1 | 20 de 285 (historical+ssp245+ssp585) | `esg-dn2.nsc.liu.se` (NSC, Suecia) |
| `EC-Earth3-CC` | gn | r1i1p1f1 | 30 de 301 | NSC, CEDA |
| `EC-Earth3-Veg` | gn | r1i1p1f1 | 188 de 433 (el más golpeado) | NSC, CEDA, ORNL |
| `EC-Earth3-Veg-LR` | gn | r1i1p1f1 | 24 de 341 | NSC, CEDA |
| `TaiESM1` | gn | r1i1p1f1 | 32 de 306 | `esgf.rcec.sinica.edu.tw` (Taiwán, institución dueña del modelo) |
| `CIESM` | gn | r1i1p1f1 | 1 (historical, chunk único) | `cmip.dess.tsinghua.edu.cn` (Tsinghua) → luego `esgf.ceda.ac.uk` (el de Tsinghua también se volvió lento/inestable en un reintento posterior) |
| `KACE-1-0-G` | gr | r1i1p1f1 | 1 (historical, chunk único, 1850–2014, ~530 MB) | `esgf.ceda.ac.uk`; también probado `esgf.nci.org.au` y `esgf3.dkrz.de` (ambos vivos, no usados por ser más lentos en la prueba de velocidad) — el mirror coreano original (`esgf-nimscmip6.apcc21.org`, institución dueña, NIMS-KMA) también estaba caído |
| `CanESM5-1` | gn | r1i1p1f1 | 1 | Se resolvió en el primer reintento sin necesitar búsqueda adicional |

**Proceso de recuperación (mismo para todos):**
1. Detectar que el archivo faltaba comparando `esgf_file_urls.json` (catálogo de URLs) contra los archivos realmente presentes en `data/raw/cmip6/`.
2. Confirmar que el mirror guardado estaba genuinamente caído (no solo lento): `curl --max-time 15` sin respuesta / timeout de conexión.
3. Consultar en vivo el índice de búsqueda ESGF (`esg-search`) de nodos alternativos (CEDA, DKRZ, IPSL, NSC, NCI) para el archivo exacto (mismo `source_id`+`experiment_id`+`variant_label`+nombre de archivo), obteniendo así URLs de otros nodos que sí replican ese mismo dato.
4. Probar el mirror candidato con una petición parcial (`curl -r 0-1000`) antes de lanzar la descarga completa.
5. Reordenar la lista de URLs guardada para ese archivo, dejando el mirror muerto al final (nunca eliminado del todo, por si vuelve a estar disponible en el futuro).
6. Descargar con el mirror que respondió.

Para los 298 archivos de la familia EC-Earth3 + TaiESM1 se automatizó este proceso (script de reintento dirigido) tras consultar 6 nodos de golpe y agregar **10.867 URLs nuevas** al catálogo; resultado: **286 de 289 recuperados** en el primer pase, y los 3 restantes (`KACE-1-0-G` 1 archivo, `MIROC-ES2H` 2 archivos) se dejaron para revisión puntual — `KACE-1-0-G` ya resuelto (este documento), `MIROC-ES2H` sigue pendiente.

---

## 4. Casos especiales: metadatos/malla inconsistentes

### CESM2 — miembro de ensamble con malla distinta por experimento

El miembro preferido `r1i1p1f1` publica:
- `historical`: malla `gn` y `gr` disponibles.
- `ssp245`/`ssp585`: **solo malla `gr`**.

Como el pipeline fija una única malla por modelo (tomada de `historical`), el filtro `grid_label=gn` dejaba a `ssp245`/`ssp585` sin archivos bajo ese miembro — el modelo se marcaba incorrectamente como incompleto (`complete=False`) desde la primera corrida de `01_query_esgf_catalog.py`.

Se encontró (a partir de una búsqueda externa del usuario, que mostró `ssp245` sí disponible para CESM2) que el miembro `r4i1p1f1` sí publica malla `gn` de forma consistente en los 3 experimentos:

| Experimento | Archivos (r4i1p1f1, gn) |
|---|---|
| historical | 1 (`185001-201412.nc`, 490 MB) |
| ssp245 | 2 (`201501-206412.nc` 150 MB, `206501-210012.nc` 63 MB) |
| ssp585 | 2 (`201501-206412.nc` 150 MB, `206501-210012.nc` 108 MB) |

Esto reveló además un bug real en `01_query_esgf_catalog.py`: el catálogo, una vez marcado `esgf_principal` con `complete=False`, nunca se reintentaba en corridas posteriores (solo se reintentaban los `no_encontrado`). Se corrigió para que cualquier modelo incompleto se vuelva a intentar en cada refresco, sin perder nunca un modelo ya resuelto por otra vía.

### IPSL-CM6A-LR — variable auxiliar sin coordenadas

Malla curvilínea tripolar (NEMO, 362×332 celdas). El archivo trae una variable `area(y,x)` (área de celda, `cell_measures`) que **no declara el atributo `coordinates`** hacia `nav_lat`/`nav_lon`. Al generar los pesos de regrillado, CDO escanea todas las variables del archivo y aborta con `Unsupported generic coordinates (Variable: area)` al toparse con `area` sin saber a qué malla pertenece.

**Fix:** `selvar,tos` como primer paso del procesamiento (antes de calcular pesos o regrillar), descartando toda variable auxiliar salvo `tos` y las coordenadas que de verdad usa.

### KIOST-ESM — malla nativa distinta entre `historical` y `ssp245`/`ssp585`

A diferencia de CESM2 (mismo miembro, mismo dato, distinta malla *publicada*), aquí la malla nativa del modelo **realmente cambia** de un experimento a otro. El regrillado con los pesos calculados a partir de `historical` fallaba (`Size of source grid and weights differ`) al aplicarse a `ssp245`/`ssp585`.

**Fix:** cálculo de pesos de regrilla propio por periodo, como *mecanismo de verificación y respaldo* — se usan los pesos compartidos del modelo por defecto (más rápido, un solo cálculo), y solo si el regrillado falla se recalculan pesos específicos para ese periodo puntual. Confirmó que el fallback era necesario exactamente en este caso (y en ningún otro modelo del inventario final).

---

## 5. Caminos explorados que NO aportaron modelos al inventario final

### Copernicus CDS (`02c_download_copernicus_cds.py`)

Se intentó como última vía para 14 modelos (lista verificada a mano contra el sitio de Copernicus para `ssp245`), más 1 modelo adicional (`HadGEM3-GC31-MM`, exitoso en un lote anterior). Resultado:

- **Historical**: 2 de 14 exitosos (`IPSL-CM5A2-INCA`, `SAM0-UNICON`).
- **ssp245**: 1 de 14 exitoso (`CESM2` — aunque el archivo resultante nunca llegó a usarse: se re-obtuvo directamente de ESGF con el fix del miembro `r4i1p1f1`, ver §4).
- El resto falló con `RoocsValueError` — el motor de subsetting de CDS (ROOCS/clisops) reporta que ese dataset específico no está replicado en Copernicus, no es un problema de nuestra petición.

**Ningún modelo llegó a completar sus 3 experimentos solo vía Copernicus.** Los datos parciales que sí se obtuvieron (`E3SM-1-0`, `E3SM-1-1`, `E3SM-1-1-ECA`, `EC-Earth3-AerChem`, `HadGEM3-GC31-MM`, `IPSL-CM5A2-INCA`, `NorCPM1`, `SAM0-UNICON`, y el ya resuelto `CESM2`) quedan en disco pero **no se procesan** (el paso 04 solo toma modelos `complete=True` del catálogo) y no forman parte del inventario final. Se confirmó además, para varios de ellos, que ninguna combinación de miembro tiene los 3 experimentos disponibles en ESGF — no es un problema de nuestra búsqueda, el dato no existe.

### Nodos ESGF alternativos para modelos no encontrados (`02b_search_alt_esgf_nodes.py`)

Se probaron los 44 modelos marcados `no_encontrado` contra 5 índices de búsqueda alternativos (CEDA, DKRZ, IPSL, NSC, NCI). **Resultado: 0 resueltos.** El nodo de IPSL respondió error `500` en las 44 consultas (posible caída puntual de ese nodo); los otros 4 respondieron correctamente pero ninguno tiene los 3 experimentos bajo un miembro común para ninguno de los 44.

Se investigó modelo por modelo el motivo real (no solo "no se encontró"):
- **Modelos DECK/PMIP-only** (nunca corrieron ScenarioMIP): `AWI-ESM-1-1-LR`, `CESM2-FV2`, `CESM2-WACCM-FV2`, `EC-Earth3-LR`, `NorESM1-F`, `GISS-E2-2-H`, `GISS-E3-G`, `ICON-ESM-LR`, entre otros.
- **Modelos HighResMIP** (variantes de alta resolución, no corren `ssp245`/`ssp585` estándar): `AWI-CM-1-1-HR/LR`, `BCC-CSM2-HR`, `CMCC-CM2-VHR4`, `EC-Earth3-HR/P/P-HR`, `ECMWF-IFS-*`, `HadGEM3-GC31-HH/HM/MH`, `MPI-ESM1-2-XR`, `IPSL-CM6A-MR1`, `CESM1-CAM5-SE-HR/LR` — **excluidos deliberadamente de cualquier intento futuro** por preferencia explícita (ver `feedback_no_highres_e1_smn` en memoria).
- **Modelos con ScenarioMIP pero el SSP equivocado**: `MPI-ESM-1-2-HAM` (solo `ssp370`), `UKESM1-1-LL` (solo `ssp126`/`ssp370`) — no sirven para esta comparación (`ssp245`/`ssp585`).
- **Otros MIPs especializados**: `ACCESS-OM2` (OMIP), `CESM1-1-CAM5-CMIP5` (DCPP), `GFDL-ESM2M` (FAFMIP), `UKESM1-ice-LL` (ISMIP6).

Estos 44 quedan descartados de forma estructural (confirmado por evidencia directa en ESGF, no por fallo de búsqueda) — no hay más "atajos" automatizables con las fuentes disponibles hoy.

---

## 6. Resumen numérico

| Categoría | Cantidad |
|---|---|
| Universo total de modelos candidatos (semilla + literatura) | 102 |
| Descargados completos (3/3 experimentos) | **48** |
| — vía regular (primer mirror, sin intervención) | 39 |
| — requirieron mirror alternativo dentro de ESGF | 8 (`EC-Earth3`, `EC-Earth3-CC`, `EC-Earth3-Veg`, `EC-Earth3-Veg-LR`, `TaiESM1`, `CIESM`, `KACE-1-0-G`, `CanESM5-1`) |
| — requirieron cambio de miembro de ensamble por malla inconsistente | 1 (`CESM2`) |
| — con bug de procesamiento resuelto (dato ya estaba bien, el bug era del paso 04) | 2 (`IPSL-CM6A-LR`, `KIOST-ESM`) |
| Seleccionados tras control de calidad (paso 06/07) | 47 (queda fuera `FGOALS-f3-L`, artefacto de regrillado costero pendiente de revisión manual) |
| No encontrados en ninguna fuente (descarte estructural confirmado) | 44 |
| Con descarga parcial, sin poder completar los 3 experimentos | ~10 (vía Copernicus, ver §5) |

---

*Generado a partir de los logs de la sesión (`logs/*.log`, `logs/download_failures.log`, `logs/retry_*`, `logs/refresh_mirrors_*`), `data/interim/models_catalog_status.csv`, `data/interim/esgf_file_urls.json`, y las verificaciones directas contra ESGF (esg-search API) hechas durante la investigación.*
