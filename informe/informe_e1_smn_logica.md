# Lógica del informe `informe_e1_smn.tex`

Nota de origen: este documento resume la lógica argumental del Entregable 1
sección por sección (qué hace cada parte y por qué existe dentro del informe).
Es un complemento de lectura, no reemplaza al `.tex`, y se actualiza cada vez
que el `.tex` cambia de versión.

## Historial de auditorías sobre este `.tex`

**1. Redundancia/perfumería + coherencia interna.** Se agregaron 8 comentarios
`% REVISAR:` en los puntos donde se detectó redundancia o relleno retórico;
ningún párrafo fue borrado, solo comentado. Se corrigió además un bug de
find-replace (Sección 3.2: "corpus" mal reemplazado por "referencias" en 9
lugares, generando frases sin sentido gramatical) usando "bibliografía",
"estado del arte" o "referencias" según el contexto, más un typo de título.

**2. Renumeración a 4 entregables.** El contrato pasó de 5 a 4 entregables
(lo que era E4+E5 ahora es un único E4). Se ajustaron todas las referencias
"Entregable~5" / "Entregables~2--5" a "Entregable~4" / "Entregables~2--4"
(Resumen, Alcance, tabla de roadmap fusionada, Conclusiones, Recomendaciones),
sin explicar el cambio de contrato dentro del informe.

**3. Auditoría contra `scripts/`, `config/`, `logs/` y `data/` del repositorio.**
Se detectó que MIROC-ES2H figuraba como uno de los "48 modelos completos"
pese a tener descarga parcial (solo `historical`; confirmado en
`informe/descarga_story.md` y en la propia Figura `fig:qc` del informe, que
ya lo mostraba con dos fallos de descarga) — causa raíz: `07_build_inventory_report.py`
marca `selected=True` sin exigir `experiments_total==3`. El `.tex` se
corrigió a "47 modelos completos + 1 (MIROC-ES2H) con descarga parcial" en
todas las menciones relevantes (Resumen, Datos, Resultados, Conclusiones,
Recomendaciones). También se corrigió una frase contradictoria sobre
`config/models_seed_bruno2023.csv` (archivo que ya no existe en el
repositorio; se verificó por cruce de nombres que de los 52 modelos de
Bruno Ramírez, 34 están en `models_seed_cmip6.csv`, 16 en
`models_missing_from_esgf.csv`, y 37 llegaron al inventario final) y se
documentó `config/models_no_encontrado_44.csv` en el árbol de archivos.

**4. Verificación contra el TdR final (`input_files/TDR_COSTA_NORTE_p1_completado_4meses.docx`).**
El Entregable~1 sí cumple lo que exige el TdR final (de hecho lo excede).
Se detectaron dos tipos de desalineación con el `.tex`, que se corrigieron:
(a) números de entregable mal atribuidos que ya no coinciden con el TdR
final -- la partición de incertidumbre (V,M,S) es Entregable~4 (no~3), la
determinación de sesgos de TSM es Entregable~2 (no~1), y los índices ONI/ICEN
pertenecen a Entregable~3, no a Entregable~2 (se reubicaron en la tabla de
roadmap y en el alcance negativo); (b) afirmaciones que atribuían al TdR
detalles literales (el DOI de Szabó, los umbrales $\kappa=1,2$, la frase
"otras metodologías del TOE") que en realidad solo están en un documento de
trabajo anterior de 5 entregables (`input_files/tdr_senamhi.txt`, sin
condición de anexo oficial -- el TdR final dice explícitamente "ANEXOS: No
corresponde"). Esas afirmaciones se reescribieron para atribuir la decisión
metodológica al equipo técnico, en línea con el mandato general (más
genérico) del TdR final, sin eliminar el contenido técnico.

**5. Estilo (negrita) y aclaración de nodos ESGF.** Se retiró `\textbf{}` de
todo el documento (38 instancias) salvo: menciones directas a "Niño" (Niño
costero, Niño 3.4, Niño 1+2, y la conclusión de asimetría de la Sección
3.3) y los encabezados de tabla (Cuadros de referencias, métodos TOE,
modelos y roadmap), que se mantienen en negrita por necesidad estructural.
Los rótulos en negrita que encabezaban cada antecedente ("Aplicación de
Szabó.", "Tesis de Bruno Ramírez.", etc.) perdieron el énfasis pero
conservan su texto y función de párrafo introductorio. Además, se agregó el
país de cada nodo alternativo de ESGF en la Sección 6 (Paso 02): CEDA
(Reino Unido), DKRZ (Alemania), IPSL (Francia), NSC (Suecia), NCI
(Australia).

## Idea central del documento

El Entregable 1 **no produce resultados científicos** (desempeño de modelos,
proyecciones, TOE); su único objetivo es dejar **construida, verificada y
documentada** la base de datos CMIP6 + ERSSTv5 sobre la que se apoyarán los
Entregables 2 a 4, y dejar **justificado por literatura** el marco teórico
(partición de incertidumbre, métodos de TOE) que esos entregables aplicarán
después. Todo el informe está organizado alrededor de esa doble entrega:
(a) un *pipeline* reproducible de datos, y (b) una revisión bibliográfica que
sostiene decisiones metodológicas futuras.

## Resumen
Adelanta, en tres párrafos, los tres resultados verificables del entregable:
el pipeline (`run.sh`), la cifra clave (47/102 modelos completos, 141/141
combinaciones, más MIROC-ES2H con descarga parcial) y el marco teórico revisado (autores citados + los dos
métodos de TOE elegidos). Existe para que un lector que no siga el resto del
documento ya se lleve la conclusión operativa.

## Alcance — informe 1 (`sec:alcance`)
Cita textualmente la actividad (a) del TdR final para el Entregable 1, y
explica que el equipo técnico la descompone en cinco tareas concretas (i–v)
— esa descomposición es propia del equipo, no una cita literal del TdR
(que solo da un mandato general por entregable, sin itemizar). También
precisa, explícitamente, lo que el Entregable 1 **no** cubre (desempeño →
E2, proyección/ONI-ICEN → E3, incertidumbre/TOE → E4). Es la sección de
control: fija el criterio contra el cual se puede juzgar si el resto del
informe se excedió o se quedó corto de alcance (ver comentario en el `.tex`
sobre la Sección 3.4, que sí roza ese límite).

## Revisión científica (`sec:marco`)
Cumple la tarea (i) del alcance: revisión bibliográfica exigida por el TdR.
Se divide en cuatro bloques con roles distintos:

- **Antecedentes** (`sec:antecedentes`): presenta, uno por uno, los autores
  que el TdR cita por nombre (Hawkins-Sutton, Szabó, Bruno Ramírez, Álvarez
  Sánchez, Takahashi) y por qué cada uno es relevante para *este* proyecto
  (marco teórico, aplicación directa a CMIP6/Sudamérica, antecedente
  institucional, justificación de tratar Niño 1+2 y Niño 3.4 por separado).
  Es la base obligatoria de la que se derivan las otras tres subsecciones.

- **Literatura sobre *Time of Emergence*** (`sec:referencias`): amplía la
  revisión más allá de los autores citados por el TdR ("otras metodologías
  del TOE"), en una tabla-bibliografía de 13 referencias. Existe para
  demostrar cobertura bibliográfica sistemática, no solo citar lo mínimo
  obligatorio.

- **Similitudes y diferencias entre Niño 3.4 y Niño 1+2** (`sec:similitudes`):
  usa siete referencias de esa bibliografía para construir una hipótesis de
  trabajo propia (Niño 1+2 emergerá más tarde/incierto que Niño 3.4) que no
  estaba en ningún paper individual. Es el único tramo del informe que hace
  síntesis original en vez de solo reportar lo que dice cada fuente; por eso
  es también donde más se repite la misma conclusión (ver comentario en el
  `.tex`).

- **Elección de los dos métodos de TOE** (`sec:toe_metodos`): justifica por
  qué se usarán M1 (Szabó, obligatorio por el TdR) y ToD (Gopika,
  complementario) en el Entregable 4. Es la sección donde el informe más se
  acerca a invadir el alcance de E4 (desarrolla las ecuaciones completas de
  ambos métodos), aunque el propio texto aclara que el cálculo efectivo no
  es parte de este entregable.

## Datos (`sec:datos`)
Cumple las tareas (ii)–(iii) del alcance: identifica las dos fuentes de datos
(CMIP6 vía ESGF/Copernicus, ERSSTv5 vía NOAA) y documenta el resultado de
consolidar el universo de modelos.

- **Modelos CMIP6 descargados** (`sec:tabla_modelos`): tabla de los 48
  modelos del inventario técnico (47 completos + MIROC-ES2H con descarga
  parcial) con institución, país y resolución nominal — el inventario que
  consumirán directamente los Entregables 2–4.
- **Selección inicial de modelos** (`sec:desviacion`): explica y justifica
  una decisión de diseño real (ampliar el universo de candidatos más allá de
  la lista de Bruno Ramírez, de 46/56 a 102 candidatos) en vez de restringir
  la búsqueda a una lista pensada para otras variables.
- **Dominios oceanográficos y periodos** (`sec:dominios_periodos`): cumple la
  tarea (iv) del alcance, fijando en `config/*.yaml` las cajas Niño 3.4 /
  Niño 1+2, la ventana de descarga y los periodos de referencia/proyección
  que usarán todos los entregables posteriores.

## Arquitectura del pipeline (`sec:arquitectura`)
Describe la tarea (v) del alcance a nivel de diseño (no de script por
script): estructura de carpetas del repo, los tres principios que gobiernan
el pipeline (idempotencia, verificación por valor y no por metadato, cascada
de fuentes con degradación explícita) y el flujograma. Existe para que un
lector entienda el *porqué* de las decisiones de ingeniería antes de leer el
detalle de cada script en la sección siguiente. La subsección `run.sh`
documenta el único punto de entrada y su contrato de uso (rango de pasos,
límite de modelos, reporte de estado por corrida).

## *Pipeline* (`sec:scripts`)
Es el nivel de detalle script por script (00 a 07 + reporte de estado) de la
tarea (v) del alcance. Cada subsección documenta qué hace el script, y en
los casos donde hubo un bug real (Paso 04: unidades Kelvin mal declaradas;
Paso 05: máscara oceánica y filtro de contaminación numérica de
FGOALS-f3-L) explica el problema encontrado y la solución, porque son los
puntos que sostienen la afirmación central del Resumen ("verificación por
valor, no por metadato").

## Resultados del Entregable 1 (`sec:resultados`)
Reporta el resultado numérico final (47/102 modelos completos, 141/141
combinaciones aprobadas, más MIROC-ES2H con descarga parcial) y las figuras de verificación (matriz de disponibilidad/QC, mapas
2D, boxplot). Insiste, en cada pie de figura, en que estas gráficas son
verificaciones exploratorias de homogeneización y no resultados científicos
— la misma idea ya fijada en el Alcance, repetida aquí por figura.

## Entregable 2: próximos pasos (`sec:roadmap`)
Tabla-puente hacia el resto del proyecto: por cada entregable (E2–E4), qué
gráficas y comparaciones exige el TdR. Existe para dejar explícito que la
ausencia de resultados analíticos en E1 es una decisión de alcance, no un
vacío, y para que el lector sepa qué esperar de los siguientes informes.

## Conclusiones (`sec:conclusiones`)
Cierra el informe con cinco conclusiones que corresponden, en orden, a los
cinco bloques anteriores: pipeline completo y verificado, cambios de diseño
respecto al plan original, profundidad de la revisión científica, ampliación
del universo de modelos, y reproducibilidad total. Es, en esencia, un
resumen ejecutivo del propio informe — de ahí que repita cifras ya dadas en
el Resumen y en Resultados (ver comentario en el `.tex`).

## Recomendaciones (`sec:recomendaciones`)
Dos recomendaciones operativas para quien ejecute el Entregable 2: no asumir
que "pasar el control de calidad de E1" equivale a "ser representativo del
ENOS", y calcular M1/ToD siempre en paralelo. Son advertencias dirigidas a
evitar que el lector reinterprete mal el alcance ya fijado en la Sección
`sec:alcance`.
