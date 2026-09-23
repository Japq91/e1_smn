# Propuesta revisada — puntos (11.) y (12.)

Investigación en la literatura CMIP6/ENOS para dar un enfoque más
robusto que la versión ingenua prototipada en el notebook. Todas las
citas fueron verificadas por búsqueda web (no inventadas); donde no
pude confirmar un valor exacto lo marco explícitamente.

## Hallazgo central: un umbral absoluto fijo (ONI≥0.5°C) no es robusto entre 40 modelos

Ya sabemos (tabla de Taylor, `p05_taylor.py`) que `sigma_norm` varía
entre ~0.7 y ~1.6 según el modelo -- unos subestiman la variabilidad
del ENOS, otros la sobreestiman bastante. Si clasificamos "eventos
extremos" con el mismo umbral absoluto (+0.5°C) para los 40, un modelo
con varianza inflada va a mostrar sistemáticamente MÁS eventos
"extremos" que otro con varianza realista -- no porque su ENOS sea
mejor o peor, sino porque su escala es distinta. Esto sesgaría
cualquier selección de modelos basada en conteo/magnitud de eventos.

La literatura CMIP6 ya resuelve esto de dos formas, ambas citables:

**Opción A -- umbral relativo a la propia desviación estándar del modelo**
(Shin et al., 2022): eventos moderados/fuertes/extremos definidos como
SSTA > 0.5/1/2 desviaciones estándar **de la propia serie histórica
del dataset**, no un valor absoluto en °C.

> Shin, N.-Y., Kug, J.-S., Stuecker, M. F., Jin, F.-F., Timmermann, A.,
> & Kim, G.-I. (2022). More frequent central Pacific El Niño and
> stronger eastern Pacific El Niño in a warmer climate. *npj Climate
> and Atmospheric Science*, 5, 101. https://doi.org/10.1038/s41612-022-00324-9

**Opción B -- umbral por percentil de la distribución propia** (tradición
rENSOi): definir "extremo" como superar el percentil N (90/95/98) de
la distribución del propio dataset.

> van Oldenborgh, G. J., Hendon, H., Stockdale, T., L'Heureux, M.,
> Coughlan de Perez, E., Singh, R., & van Aalst, M. (2021). Defining El
> Niño indices in a warming climate. *Environmental Research Letters*,
> 16, 044003. https://doi.org/10.1088/1748-9326/abe9ed

Dato relevante: el índice rENSOi de van Oldenborgh et al. se define
EXACTAMENTE igual que nuestro RONI antes del reescalado de varianza
(Niño3.4 SSTA menos la SSTA media tropical) -- confirma que nuestra
elección de RONI ya está alineada con esta línea de literatura, no es
una construcción aislada.

### Recomendación para (11.)

No reemplazar los umbrales oficiales (ONI/ICEN, que es lo que
SENAMHI/IGP/ENFEN usa operacionalmente -- comparabilidad real importa
para el TdR) -- **complementarlos** con una clasificación relativa
(Shin et al., estilo 0.5/1/2 sigma, ya tenemos sigma por modelo en
`taylor_*.csv`) como diagnóstico aparte, específicamente para que la
comparación entre los 40 modelos sea justa. Dos tablas, no una.

### Tabla ONI oficial confirmada (NOAA CPC, verificada por búsqueda,
consistente en múltiples fuentes secundarias -- confirmar contra la
tabla primaria antes de citar en el informe, el sitio de IGP/NOAA no
respondió durante esta sesión de investigación):

| Categoría | ONI (°C) |
|---|---|
| Débil | 0.5 a 0.9 |
| Moderado | 1.0 a 1.4 |
| Fuerte | 1.5 a 1.9 |
| Muy fuerte | ≥ 2.0 |

Duración mínima: 5 estaciones consecutivas de 3 meses (confirmado,
múltiples fuentes NOAA CPC).

### ICEN -- cita confirmada, tabla de categorías con confianza media (verificar antes de citar en el informe)

> Takahashi, K., & Reupo, J. (2015). Índice Costero El Niño (ICEN) con
> nueva fuente de datos. Boletín Técnico "Generación de modelos
> climáticos para el pronóstico de la ocurrencia del Fenómeno El
> Niño", IGP, 2(6), 9-10.

Los servidores de IGP (met.igp.gob.pe, siofen.imarpe.gob.pe) y de
otras entidades (DHN, SENAMHI) rechazaron la conexión, dieron
verificación de seguridad, o el PDF pesaba demasiado para leer durante
esta sesión -- **no pude confirmar contra la tabla primaria de ENFEN**.
Sí encontré, via artículos secundarios sobre el evento de 2017 (fuente
de búsqueda web, no el PDF original), esta tabla -- consistente
internamente y con el umbral de inicio que ya teníamos:

| Categoría | ICEN (°C) |
|---|---|
| Inicio de evento (cualquier categoría) | > 0.4, sostenido ≥ 3 meses |
| Débil | 0.4 a 1.3 (inferido, no visto explícito) |
| Moderado | > 1.3 a 2.1 |
| Fuerte | > 2.1 a 3.5 |
| Extraordinario | > 3.5 |

**Antes de poner estos números en el informe final**: conseguir el PDF
`ICEN-Nota_Tecnica.pdf` o el boletín de Takahashi & Reupo (2015) a
mano y verificar contra la tabla primaria -- lo de arriba es de
confianza media, no primaria.

### RONI -- sin categorías oficiales propias confirmadas

Lo que encontré son las categorías del ONI/RONI unificadas (NOAA
adoptó RONI como índice oficial en 2026, reemplazando/conviviendo con
ONI -- confirmar cuál es el estado exacto vigente): Débil <1.0,
Moderado 1.0-1.5, Fuerte 1.5-2.0, Muy fuerte ≥2.0 -- pero estos números
salieron de una fuente secundaria (búsqueda), no verificados contra la
página oficial de NOAA CPC directamente. Tratar como preliminar.

## Punto (12.): hallazgo que cambia el enfoque completo

La literatura de referencia (Kaur et al. 2021; Kumar et al. 2023, ya
citados en el notebook) **no construye el diagrama de Taylor sobre la
serie continua completa del índice** -- construye un **diagrama de
Taylor sobre la evolución COMPUESTA de los eventos extremos**:

1. Identificar los eventos extremos de cada dataset (esto es
   literalmente el punto 11 -- (11.) deja de ser independiente de
   (12.), es su insumo directo).
2. Para cada evento, extraer una ventana fija centrada en el pico (los
   papers de referencia usan 24 meses).
3. Promediar esas ventanas -- se obtiene la "evolución típica" de un
   evento extremo para ese dataset (cómo se arma, qué tan alto llega,
   cómo decae).
4. Diagrama de Taylor comparando la evolución compuesta del modelo
   contra la evolución compuesta de ERSSTv5 (sigma, r, RMSE' de la
   FORMA, no de la serie completa).

**Por qué esto es mejor que lo que hicimos en el notebook** (correlación
de la serie completa, Sección 9/17): ya encontramos que la correlación
de fase entre un modelo *historical* libre y las observaciones es
practicamente nula (r~0.05, las simulaciones no reproducen El Niño en
el mismo año que la realidad -- esperable, no son corridas
inicializadas). Eso hace que el diagrama de Taylor sobre la serie
completa tenga muy poco poder para distinguir modelos buenos de malos
en la práctica (todos se agrupan cerca de r=0). El análisis compuesto
evita el problema de raíz: no pregunta "¿el evento pasó el mismo año?"
(imposible de acertar en una corrida libre), pregunta "cuando el
modelo SÍ genera un evento, ¿tiene la forma correcta?" -- una pregunta
que sí se puede responder con una corrida histórica libre, y que es
más fiel a lo que pide el TdR (representación de eventos extremos, no
de su cronología exacta).

## Cómo quedarían (11.) y (12.) encadenados

```
(11.) Deteccion de eventos               (12.) Taylor compuesto
  - umbral oficial (ONI/ICEN)              - ventana fija centrada en el pico
  - umbral relativo (Shin et al., sigma)   - promedio de ventanas -> "evento tipico"
  - lista de eventos por modelo/indice     - sigma, r, RMSE', sigma_norm del compuesto
         |                                          ^
         +------------------------------------------+
              (11.) es insumo directo de (12.)
```

## Decisiones pendientes para el usuario (no asumidas, no implementadas)

1. ¿Umbral oficial + relativo (dos tablas, mi recomendación) o solo
   uno de los dos?
2. Duración de la ventana compuesta en (12.) -- ¿24 meses como Kaur/
   Kumar, o algo ajustado a nuestro caso?
3. Conseguir la tabla exacta de categorías ICEN (°C) -- los servidores
   de IGP no respondieron, hace falta el PDF a mano o reintentar.
4. ¿RONI usa el mismo umbral que ONI, o necesita uno propio? (no
   encontré una fuente que lo trate por separado con autoridad)

Nada de esto está implementado todavía -- son scripts `p07`/`p08`
pendientes de que el usuario revise este enfoque.
