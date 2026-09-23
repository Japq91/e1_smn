# data/processed/e2/

Salidas propias del Entregable 2: climatología, sesgo, ONI/RONI
(Niño 3.4), ICEN (Niño 1+2), diagrama de Taylor -- ver
`scripts_e2/README.md` para el contrato de entrada y
`informe/borradores/marco_teorico_e2.txt` para las ecuaciones. No usa
Índices C/E (Takahashi et al., 2011): reemplazados por ONI/RONI/ICEN,
decisión del usuario. No confundir con `data/processed/masked/` ni
`data/processed/models_inventory_final.csv`, que son insumo de solo
lectura del Entregable 1 (`run.sh`) y nunca se escriben desde acá.

## Scripts que generan estos archivos: `scripts_e2/pXX_*.py`

Un script por paso de cálculo (ver el listado numerado del marco
teórico/cálculos de E2), cada uno **ejecutable por separado**
(`python3 scripts_e2/pXX_*.py`, no depende de que otro `pXX` haya
corrido antes -- todos leen directo de `data/processed/masked/` y
`model_registry_e2.csv`). Comparten helpers en `scripts_e2/common_e2.py`
(mismo patrón que `scripts/plot_common.py` en E1), pero eso no los
acopla entre sí, solo evita duplicar `box_series`/climatología/etc.

Cada script tiene su **propio** `REF_INICIO`/`REF_FIN` como constante
editable al principio del archivo -- a propósito no centralizado en
`common_e2.py`, para poder cambiar el período de referencia de un
cálculo puntual sin afectar a los demás. El nombre del archivo de
salida se arma siempre a partir de esas constantes, nunca a mano:
cambiar `REF_INICIO`/`REF_FIN` en el script cambia el nombre del CSV
solo, en la próxima corrida.

- `p01_indices_enso.py` -- ONI/RONI/ICEN (ver `indices_enso_*.csv`
  abajo).
- `p02_climatologia.py` -- climatología y ciclo anual (ver
  `climatologia_*.csv` abajo).
- `p03_sesgo.py` -- sesgo por punto de grid (ver `sesgo_tsm_*.nc`
  abajo).
- `p04_variabilidad.py` -- sesgo de variabilidad por punto de grid
  (ver `variabilidad_tsm_*.nc` abajo).
- `p05_taylor.py` -- input del diagrama de Taylor, consolidando los
  pasos (5.)-(8.) del cálculo (ver `taylor_*.csv` abajo).
- `p06_correlacion.py` -- correlación y significancia por punto de
  grid, punto (13.), propuesta del usuario (ver `correlacion_tsm_*.nc`
  abajo).
- `p07_eventos.py` -- clasificación de eventos cálidos extremos, punto
  (11.) (ver `eventos_*.csv` abajo).
- `p08_taylor_compuesto.py` -- diagrama de Taylor sobre el evento
  compuesto, punto (12.) (ver `taylor_compuesto_*.csv` abajo).
- `p09_skill_score.py` -- score de habilidad S (Taylor, 2001) y
  ranking/selección final de los 40 modelos, punto (14.) (ver
  `skill_score_*.csv` abajo).

## `model_registry_e2.csv`

Los 40 modelos seleccionados (`data/processed/models_inventory_final.csv`,
`selected=True`), en orden alfabético, con numeración propia de E2:
columna `number` = `M01`...`M40` -- **deliberadamente distinta** del
`M001`...`M102` de `informe/model_registry.csv` (E1), que numera el
universo completo de 102 candidatos. Esta numeración `M01..M40` es el
identificador canónico para todo archivo/gráfico de E2 de acá en
adelante, no el nombre completo del modelo.

Columnas: `number, model, institution, country, member_id,
resolution_km` -- las últimas 4 reusadas tal cual de
`informe/model_registry.csv` (join por nombre de modelo), no
recalculadas.

## `indices_enso_<periodo>_ref<ref>.csv`

Una sola tabla: primera columna `time`, y 3 columnas por modelo usando
su `number`: `M01_ONI, M01_RONI, M01_ICEN, M02_ONI, ...` hasta
`M40_ICEN` (121 columnas para 40 modelos). El nombre de archivo
codifica dos períodos distintos, no confundir:
- `<periodo>` (ej. `1900-2014`): rango temporal real de los datos en
  el archivo (ver "Ventana temporal común" abajo).
- `ref<ref>` (ej. `ref1981-2014`): período de referencia de la
  climatología usada para las anomalías (`config/periods.yaml`,
  `referencia_historica`) -- fijo, no cambia aunque cambie la ventana
  de datos.

Calculado **sin corrección Linear Scaling (LS)**: se probó y se
descartó -- LS es una resta constante por mes calendario, y cualquier
anomalía (que es todo lo que alimenta ONI/RONI/ICEN) la cancela
algebraicamente sola. Los índices son la anomalía respecto a la
climatología **propia** de cada dataset (ERSSTv5 con la suya, cada
modelo con la suya), igual que se calcula ONI en la práctica real. El
sesgo (`C_m^modelo - C_m^obs`) se reporta aparte, como diagnóstico
independiente que no alimenta este cálculo.

### Ventana temporal común a los 40 modelos (recorte por disponibilidad)

`historical` no arranca el mismo año para todos los modelos: la
mayoría cubre 1850-2014, pero **IITM-ESM (M26) solo publica desde
1900** (mismo caso ya documentado en el pipeline de E1,
`scripts/06_qc_checks.py`, `HISTORICAL_MIN_LAST_YEAR` -- ahí se acepta
igual porque llega bien cerca del presente, no hace falta cubrir 1850
completo). En vez de dejar 40 columnas con distinto rango y NaN al
principio para las que arrancan después, el CSV se recorta a la
**intersección** de los 40: el inicio más tardío entre todos
(1900-02, por M26) hasta el fin más temprano (2014-11 -- uniforme en
los 40, es el borde del promedio móvil de 3 meses centrado del índice,
que pierde el último mes por no tener vecino siguiente).

El límite se calcula del propio resultado en cada corrida (no está
hardcodeado), así que se ajusta solo si la disponibilidad de algún
modelo cambia (ej. al resolver el bug de dos realizaciones mezcladas
en GISS-E2-1-G/H, ver conversación -- si eso cambia su rango temporal,
el próximo cálculo lo refleja solo).

**Para el `.tex` de E2**: mencionar explícitamente este recorte y su
causa (IITM-ESM) al describir el período de análisis -- evitar que
alguien note la ventana 1900-2014 en una figura y la lea como un error
o una elección arbitraria.

## `climatologia_<caja>_<ref>.csv`

Dos archivos, uno por caja (`nino34`, `nino12`) -- **filas = modelos**
(primera columna `number`, `M01`...`M40`), **columnas = mes** (`1`...`12`,
$C_m$ en grados C). Transpuesto respecto a `indices_enso_*.csv` (ahí
las filas son tiempo) porque acá no hay eje temporal, el ciclo anual
ya es la dimensión mes. El nombre de archivo codifica solo el período
de referencia (`<ref>`, ej. `1981-2014` -- no hay un `<periodo>` de
datos como en los índices, la climatología por definición se calcula
únicamente sobre la ventana de referencia).

Generado por `scripts_e2/p02_climatologia.py`. Calculado por separado
para cada dataset (sin LS, mismo criterio que `indices_enso_*.csv`).

## `sesgo_tsm_ref<ref>.nc`

NetCDF (no CSV -- es un campo 2D por modelo, no una tabla): dimensiones
`number` (1..40, mismo orden que `model_registry_e2.csv`), `lat`,
`lon`. Variable `bias(number, lat, lon)`, en grados C, más `model(number)`
como coordenada auxiliar (nombre del modelo, para no tener que cruzar
con `model_registry_e2.csv` solo para identificar una capa). Dominio:
el mismo de `data/processed/masked/*.nc` completo (lat -30/30, lon
global), sin recortar a ninguna caja.

Un solo valor de sesgo por punto de grid -- **no** 12 mapas por mes
calendario: se promedia toda la serie temporal del período de
referencia (12×34 = 408 meses para 1981-2014) antes de restar,
`B(lat,lon) = media_tiempo(modelo) - media_tiempo(ERSSTv5)`, no una
climatología mensual por separado. El nombre de archivo codifica el
período de referencia (`<ref>`, ej. `1981-2014`).

Generado por `scripts_e2/p03_sesgo.py`. Sin corrección Linear Scaling
(mismo criterio que el resto de E2). Complementa directamente a
`variabilidad_tsm_ref<ref>.nc` (abajo): este archivo es el sesgo del
**primer momento** (la media); el de variabilidad es el del **segundo
momento** (la dispersión) -- mismo dominio, misma estructura de
dimensiones, pensados para mostrarse como par en el informe.

## `variabilidad_tsm_ref<ref>.nc`

NetCDF con la misma estructura que `sesgo_tsm_ref<ref>.nc` (dimensiones
`number`, `lat`, `lon`, más `model(number)` auxiliar, mismo dominio
completo) pero para la **variabilidad** en vez de la media: diferencia
porcentual de desviación estándar,

$$D(lat,lon) = 100 \times \frac{\sigma_{modelo}-\sigma_{obs}}{\sigma_{obs}}$$

equivalente a $100\times(\sigma_{norm}-1)$, el mismo cociente
$\sigma_f/\sigma_r$ que ya se usa en el diagrama de Taylor (Secciones
8/17 del notebook de prueba) -- acá calculado punto a punto en todo el
dominio en vez de sobre el promedio de una caja, así que **no da
necesariamente el mismo número** que el $\sigma_{norm}$ de caja (el
promedio espacial de una serie y la dispersión espacial de esa misma
serie son cantidades distintas: "desviación del promedio" ≠ "promedio
de la desviación").

$\sigma$ se calcula sobre la **anomalía** (climatología propia de cada
dataset ya removida, mismo período de referencia), no sobre el valor
crudo -- si se usara el valor crudo la diferencia quedaría dominada
por el ciclo anual (que apenas difiere entre datasets), tapando la
variabilidad interanual real que interesa comparar. El nombre de
archivo codifica el período de referencia de esa anomalía (`<ref>`,
ej. `1981-2014`) -- el mismo período se usa para la climatología y
para calcular la $\sigma$, no son dos fechas distintas acá.

Generado por `scripts_e2/p04_variabilidad.py`. Sin corrección Linear
Scaling (mismo criterio que el resto de E2).

## `taylor_<caja>_ref<ref>.csv`

Dos archivos, uno por caja (`nino34`, `nino12`) -- **input completo
para el diagrama de Taylor**, consolidando en un solo par de archivos
lo que serían 4 cálculos por separado (variabilidad, RMSE centrado,
correlación, estadísticos de Taylor). Filas = modelos, **fila 1 =
`OBS`** (ERSSTv5, valores triviales por definición: `r=1`,
`rmse_centrado=0`, `sigma_norm=1`), filas 2-41 = `M01`...`M40`.
Columnas:

- `sigma` -- desviación estándar de la anomalía (°C).
- `r` -- correlación de **Pearson** (no Spearman) con la anomalía de
  ERSSTv5.
- `rmse_centrado` -- RMSE entre anomalías ya centradas (cada serie
  menos su propia media) contra ERSSTv5.
- `sigma_norm` -- `sigma / sigma_obs`, el radio del diagrama polar.

Las 4 columnas satisfacen la identidad de Taylor (2001):
$E'^2=\sigma_f^2+\sigma_r^2-2\sigma_f\sigma_r r$ -- por eso van juntas
en un solo archivo, no tiene sentido separarlas. El **por qué**
metodológico completo (por qué centrado y no total, por qué Pearson y
no Spearman, por qué normalizado) está en
`informe/borradores/marco_teorico_e2.txt`, no se repite acá.

Todo sobre la **anomalía** (climatología propia de cada dataset, sin
LS, mismo criterio que el resto de E2). El nombre de archivo codifica
el período de referencia de esa climatología (`<ref>`, ej.
`1981-2014`).

Generado por `scripts_e2/p05_taylor.py`.

## `correlacion_tsm_ref<ref>.nc`

NetCDF con la misma estructura que `sesgo_tsm_ref<ref>.nc` /
`variabilidad_tsm_ref<ref>.nc` (dimensiones `number`, `lat`, `lon`,
más `model(number)` auxiliar, mismo dominio completo), pero con
**2 variables**: `corr` (correlación de Pearson) y `sign` (p-value).

Ojo con la diferencia frente a la correlación espacial que se probó en
el notebook de pruebas (Sección 18 -- ahí se correlacionaba el campo
completo contra un índice fijo, ej. Niño3.4): acá es distinto, mismo
criterio que `sesgo_tsm_*.nc`, correlación **punto a punto**: en cada
`(lat,lon)`, la serie temporal del **modelo en ese punto** contra la
serie temporal de **ERSSTv5 en ese mismo punto** -- no contra un
índice de una caja. Sobre la anomalía (climatología propia, periodo de
referencia, sin LS), para que el ciclo anual compartido no infle la
correlación.

`sign` es el **p-value continuo** (no un flag booleano a un umbral
fijo -- el umbral, ej. 0.05, se aplica después, al graficar), de un
test-t **corregido por autocorrelación temporal** (Bretherton et al.,
1999): la TSM mensual está fuertemente autocorrelacionada, así que
tratar los ~N meses como observaciones independientes sobreestima
dónde es significativo -- mismo bug real que se encontró y corrigió en
el notebook de pruebas (Sección 18: la autocorrelación lag-1 hay que
calcularla por posición, no por fecha -- ver `lag1_autocorr()` en
`common_e2.py`).

> Bretherton, C. S., Widmann, M., Dymnikov, V. P., Wallace, J. M., &
> Bladé, I. (1999). The effective number of spatial degrees of freedom
> of a time-varying field. *Journal of Climate*, 12(7), 1990-2009.

Generado por `scripts_e2/p06_correlacion.py`. Sin corrección Linear
Scaling (mismo criterio que el resto de E2). Es la propuesta del
usuario, listada como punto (13.) del cálculo, no del listado original
de 12 puntos.

## `eventos_<INDICE>_ref<ref>.csv`

Tres archivos, uno por índice (`ONI`, `RONI`, `ICEN`) -- punto (11.)
del cálculo. A diferencia de todos los archivos anteriores, formato
**largo**: una fila **por evento detectado**, no una fila por modelo
(un modelo puede tener 0 o varios eventos en el período). Columnas:
`number, inicio, fin, fecha_pico, duracion_meses, magnitud_pico,
categoria_oficial, categoria_relativa`. `fecha_pico` (fecha del valor
máximo dentro del evento) la usa directamente
`p08_taylor_compuesto.py` para centrar la ventana del compuesto --
punto (12.), ver abajo. Incluye `OBS` (ERSSTv5) -- a diferencia de
`indices_enso_*.csv`, acá sí hace falta para poder comparar; se
recalcula vía `common_e2.load_all_indices()` (combina el CSV de
`p01_indices_enso.py`, que deliberadamente excluye OBS, con los
índices de OBS calculados aparte), sin tocar el formato de ese CSV.

**Dos clasificaciones sobre el mismo evento**, no dos listas de
eventos separadas (ver
`informe/borradores/propuesta_puntos_11_12.md` para la justificación
completa):

- `categoria_oficial` -- umbral fijo en °C, el mismo que usa
  SENAMHI/IGP/NOAA operacionalmente. ONI/RONI: débil 0.5-0.9,
  moderado 1.0-1.4, fuerte 1.5-1.9, muy fuerte ≥2.0 (confianza alta,
  NOAA CPC). RONI usa la misma tabla que ONI -- por construcción
  `std(RONI) == std(ONI)` (el reescalado de varianza de
  `p01_indices_enso.py::roni_index`), así que la tabla de ONI es
  directamente aplicable, no una elección arbitraria. ICEN: débil
  0.4-1.3, moderado 1.3-2.1, fuerte 2.1-3.5, extraordinario >3.5
  (confianza MEDIA -- fuente secundaria sobre el evento de 2017, no la
  tabla primaria de ENFEN; verificar antes de citar en el informe
  final).
- `categoria_relativa` -- umbral proporcional a la propia σ de cada
  dataset (Shin et al., 2022): moderado ≥0.5σ, fuerte ≥1σ, extremo
  ≥2σ, calculada sobre la MISMA serie del índice que se está
  clasificando (no la σ de `taylor_*.csv`, que es la de la anomalía
  cruda de caja, una cantidad distinta). Evita que un modelo con
  varianza inflada aparezca con "eventos más extremos" solo por su
  escala. Puede quedar vacía si el pico no llega a 0.5σ aunque haya
  superado el umbral oficial (dataset con σ grande) -- resultado
  válido, no un error.

> Shin, N.-Y., Kug, J.-S., Stuecker, M. F., Jin, F.-F., Timmermann, A.,
> & Kim, G.-I. (2022). More frequent central Pacific El Niño and
> stronger eastern Pacific El Niño in a warmer climate. *npj Climate
> and Atmospheric Science*, 5, 101. https://doi.org/10.1038/s41612-022-00324-9

Ambas categorías se calculan sobre la magnitud del **pico ya
redondeada a 1 decimal** -- las tablas oficiales se definieron sobre
el valor tal como se publica (1 decimal), y sin redondear el valor
continuo cae en huecos entre categorías (ej. 1.4179 no es ni
"moderado", 1.0-1.4, ni "fuerte", 1.5-1.9) -- bug real detectado y
corregido durante la construcción de este script.

Generado por `scripts_e2/p07_eventos.py`. Insumo directo del punto
(12.) (`p08_taylor_compuesto.py`, ver abajo) -- no independientes.

## `taylor_compuesto_<INDICE>_ref<ref>.csv`

Tres archivos, uno por índice (`ONI`, `RONI`, `ICEN`) -- punto (12.)
del cálculo, **no independiente**: consume directamente
`eventos_<INDICE>_ref<ref>.csv` (punto 11., arriba). Mismo formato de
4 columnas que `taylor_<caja>_ref<ref>.csv` (fila 1 = `OBS`, filas
2-41 = `M01`...`M40`, columnas `sigma, r, rmse_centrado, sigma_norm`,
mismas fórmulas y misma identidad de Taylor) -- pero calculado sobre
la **evolución compuesta** del evento cálido extremo, no sobre la
serie temporal completa del índice.

**Por qué un Taylor distinto del de `taylor_*.csv`**: `historical` es
una corrida libre (no inicializada), así que no hay razón física para
que un modelo produzca su Niño de 1997 el mismo año que ERSSTv5 --
`taylor_*.csv` (serie completa) penaliza esa diferencia de **fase**
igual que penalizaría un error real de forma, y por eso los 40 modelos
salen con $r$ cercano a 0 ahí (ver
`informe/borradores/propuesta_puntos_11_12.md`). El compuesto evita el
problema: en vez de "¿pasó el evento el mismo año?", compara "cuando
el modelo sí genera un evento, ¿tiene la **forma** correcta (arma,
pico, decaimiento)?" -- pregunta respondible con una corrida libre.
Confirma la hipótesis en la práctica: con los mismos 40 modelos, $r$
en `taylor_compuesto_ONI_ref1981-2014.csv` va de ~0.94 a ~0.99, contra
valores cercanos a 0 en `taylor_nino34_ref1981-2014.csv`.

Metodología (Kaur et al., 2021; Kumar et al., 2023): para cada evento
de `eventos_<INDICE>_ref<ref>.csv`, se extrae una ventana de **±12
meses (24 meses totales) centrada en `fecha_pico`**; los eventos cuya
ventana pediría meses fuera del rango disponible (bordes del registro,
ej. cerca de 1900 por IITM-ESM o cerca de 2014) se **descartan
enteros**, no se rellenan con NaN -- decisión explícita del usuario,
para no promediar compuestos con distinto número de observaciones por
mes relativo. Las ventanas válidas de cada dataset se promedian en una
sola curva de 25 puntos (mes relativo al pico, $t=-12..0..+12$): el
"evento típico" de ese dataset. Esa curva compuesta del modelo se
compara contra la curva compuesta de OBS con las mismas 4 métricas del
Taylor de caja.

> Kaur, S., Kumar, P., Min, S.-K., Patra, A., & Wang, X. L. (2021).
> CMIP5 model evaluation for extreme ocean wave height responses to
> ENSO. *Climate Dynamics*. https://doi.org/10.1007/s00382-021-06039-6

Generado por `scripts_e2/p08_taylor_compuesto.py`. Sin corrección
Linear Scaling (mismo criterio que el resto de E2). Sobre la anomalía
propia de cada dataset (mismos índices ONI/RONI/ICEN de
`indices_enso_*.csv`/`load_all_indices()`, no un recálculo aparte).

## `skill_score_ref<ref>.csv`

Punto (14.) del cálculo -- responde directamente a la actividad (b) del
TdR ("seleccionar los modelos con mejor capacidad de representación"),
que no fija un número ni un umbral. Una fila por modelo (`M01`...`M40`,
sin `OBS` -- $S_{obs}=1$ trivial, no es un modelo a evaluar), ordenada
descendente por `S_final`. Columnas:

- `S_nino34`, `S_nino12` -- skill score $S$ (ver fórmula abajo)
  calculado sobre `taylor_nino34_ref<ref>.csv` / `taylor_nino12_ref<ref>.csv`
  (serie completa). Se reportan solo como **referencia/diagnóstico** --
  **no entran en `S_final`** (ver por qué abajo).
- `S_ONI`, `S_RONI`, `S_ICEN` -- mismo $S$ calculado sobre
  `taylor_compuesto_<INDICE>_ref<ref>.csv` (evolución compuesta del
  evento extremo, ver arriba).
- `S_final` -- `mean(S_ONI, S_RONI, S_ICEN)`, el número usado para
  ordenar/seleccionar.
- `grupo` -- `"bueno"`/`"malo"` si el gap statistic confirmó una
  separación real en los datos (ver abajo); **vacío** si no la
  confirmó (resultado obtenido con `ref1981-2014`: vacío para los 40 --
  no hay un quiebre objetivamente distinguible, los modelos caen en un
  continuo de `S_final`).

**Fórmula ($S$, Taylor 2001)**, sobre `r` y `sigma_norm` ya presentes
en cada `taylor_*.csv` (no usa `rmse_centrado`, redundante dada la
identidad de Taylor; no usa sesgo, diagnóstico aparte por diseño):

$$S=\frac{4(1+R)^4}{(\hat\sigma+1/\hat\sigma)^2(1+R_0)^4}$$

con $R_0=1$ (correlación máxima alcanzable -- default estándar sin una
estimación propia de incertidumbre observacional de ERSSTv5), lo que
simplifica a $S=(1+R)^4/[4(\hat\sigma+1/\hat\sigma)^2]$. Acotado en
$[0,1]$, $S=1$ solo si $\hat\sigma=1$ y $R=1$.

**Por qué `S_final` usa SOLO los 3 índices compuestos, no las 5
tablas**: se probó primero un promedio 50/50 por bloque temático
(`S_serie`=mean(nino34,nino12) y `S_compuesto`=mean(ONI,RONI,ICEN)),
pero `S_nino34`/`S_nino12` salieron sistemáticamente bajos (0.04-0.14)
para los 40 modelos -- no por defecto de los modelos, sino porque
`historical` es una corrida libre sin inicializar (mismo argumento de
`taylor_compuesto_*.csv` arriba): con $R\approx0$ por el problema de
fase, el numerador $(1+R)^4$ colapsa $S$ a un techo bajo (~0.06)
**para cualquier modelo, bueno o malo**. Meter ese bloque en
`S_final` con peso 50% mezclaría ruido de fase con señal real de
habilidad, y en la práctica el bloque compuesto terminaba dominando
igual (0.35-0.98) pese al peso nominal igual -- decisión del usuario:
excluir el bloque de serie completa de `S_final`, dejarlo solo como
referencia.

**Gap statistic** (Tibshirani, Walther & Hastie, 2001), sobre los 40
valores de `S_final`: compara la dispersión intra-grupo real (K=1 vs
K=2, K-means) contra la esperada bajo una referencia sin estructura
(uniforme en el rango de `S_final`, 1000 datasets Monte Carlo,
semilla fija para reproducibilidad). Se elige K=1 (sin partición)
salvo que Gap(2) supere a Gap(1) por más que el margen de error de la
referencia. Con `ref1981-2014`: Gap(1)=0.601±0.153 vs.
Gap(2)=0.292±0.149 -- K=1 gana, **no hay separación real
"buenos/malos"**, resultado real (no forzado), reportado tal cual.

> Tibshirani, R., Walther, G., & Hastie, T. (2001). Estimating the
> number of clusters in a data set via the gap statistic. *Journal of
> the Royal Statistical Society: Series B*, 63(2), 411-423.
> https://doi.org/10.1111/1467-9868.00293

Si el gap statistic hubiera confirmado K=2, el punto de corte se
calcula con **Jenks natural breaks** (Fisher, 1958, búsqueda
exhaustiva del corte que minimiza la varianza intra-grupo -- exacto
para 40 puntos), reportando también el GVF (goodness of variance fit)
como medida de qué tan limpia es la partición.

Generado por `scripts_e2/p09_skill_score.py`. Sin corrección Linear
Scaling (mismo criterio que el resto de E2, por herencia de las tablas
`taylor_*.csv` que consume).
