# Historial de cambios

Este proyecto sigue [Versionado Semántico](https://semver.org/lang/es/).

## [0.8.7] - 2026-10-12

- La consola de GridScope muestra claramente la versión que se está ejecutando.
- El mensaje inicial presenta de forma más limpia la dirección del servidor
  local y cómo cerrar la aplicación.
- Se elimina el aviso técnico sobre la reutilización de la pestaña después de
  actualizar; ese proceso continúa realizándose silenciosamente.

## [0.8.6] - 2026-10-12

- El selector de campeonatos incorpora búsqueda por serie o temporada y filtros
  para consultar únicamente temporadas actuales o históricas.
- La página de sesiones resume semanas, carreras, circuitos y mejor media antes
  de mostrar cada jornada en tarjetas más claras y comparables.
- Las carreras se agrupan por semana y pueden buscarse por circuito, trazado o
  ganador, filtrarse por semana y ordenarse por fecha o mejor resultado.
- La página de Pilotos permite buscar por nombre o ID dentro de recurrentes,
  rivales de una coincidencia o la lista completa.
- Las nuevas vistas reducen el desplazamiento y se adaptan a pantallas estrechas.

## [0.8.5] - 2026-10-11

- El primer arranque manual después de actualizar reutiliza la pestaña que ya
  estaba esperando y evita abrir una segunda ventana del navegador.
- La supresión de apertura se consume una sola vez: los siguientes arranques
  normales vuelven a abrir GridScope en el navegador como siempre.
- El resultado de cada actualización identifica la versión instalada para que
  esta detección sea precisa en las próximas versiones.

## [0.8.4] - 2026-10-11

- Las carreras multiclase de iRacing muestran la posición de clase como
  resultado principal y la posición general como referencia secundaria.
- La tabla identifica expresamente la clase del piloto y diferencia la salida
  de clase de la salida general.
- GridScore compara el resultado, el ritmo y el SoF contra la clase del piloto
  en lugar de utilizar el tamaño completo de una parrilla multiclase.
- El actualizador reconoce compilaciones de prueba con sufijo de letra para
  validar el nuevo proceso de reapertura manual.

## [0.8.3] - 2026-10-11

- El actualizador deja de intentar iniciar GridScope desde el proceso auxiliar
  de Windows después de sustituir el ejecutable.
- Al terminar muestra un mensaje de confirmación que pide volver a abrir la
  aplicación manualmente.
- La pestaña que permanece abierta comprueba cuándo vuelve el servidor local y
  se recarga automáticamente al detectar la nueva versión.
- Se elimina el falso error provocado cuando Windows impedía al asistente
  iniciar el ejecutable recién actualizado.

## [0.8.2] - 2026-10-11

- La configuración distingue claramente el Customer ID del piloto y el
  Client ID utilizado por la conexión OAuth.
- El Customer ID guardado se muestra de forma explícita para evitar que una
  API todavía no conectada parezca una pérdida de la identidad del usuario.
- Se aclara que OAuth es opcional y que su estado no afecta a las carreras
  importadas, las estadísticas ni las comparativas existentes.

## [0.8.1] - 2026-10-11

- El actualizador reinicia GridScope indicando explícitamente la dirección y
  el puerto del servidor local.
- Si un intento de arranque falla, cierra únicamente los procesos de esa
  instalación y realiza un nuevo intento real.
- La comprobación de salud espera al servidor y verifica que la versión
  iniciada coincide con la recién instalada.
- El registro de actualización conserva cada intento y explica el motivo
  concreto si el reinicio no puede completarse.
- Se añade una prueba aislada que sustituye el ejecutable, reinicia el servidor
  y comprueba su respuesta sin utilizar los datos del usuario.

## [0.8.0] - 2026-10-11

- La aplicación reorganiza sus páginas principales mediante pestañas para
  reducir el desplazamiento y separar mejor resúmenes, clasificaciones,
  carreras y configuraciones.
- Las listas extensas incorporan paginación y distinguen entre rivales
  recurrentes, pilotos de una sola coincidencia y el historial completo.
- El Resumen añade una vista de evolución con gráficas interactivas de las
  métricas oficiales disponibles y de GridScore, Limpieza, salida y llegada.
- Comparativas incorpora gráficas de posiciones, incidentes, duelos directos
  y ventaja media frente a rivales recurrentes.
- Los filtros de las gráficas permiten consultar 5, 10, 20 o todas las
  carreras; cada punto abre el resultado y cada rival su historial compartido.
- Las métricas y explicaciones se adaptan a iRacing, Assetto Corsa y RaceRoom,
  sin presentar valores propios como si fueran oficiales.
- El diseño de las nuevas vistas se adapta a pantallas estrechas y conserva
  las tablas detalladas para consultar los valores exactos.

## [0.7.9] - 2026-07-26

- La interfaz vuelve a abrirse de forma visible después de instalar una
  actualización.
- El ejecutable espera a que el servidor local esté preparado antes de abrir
  la página en el navegador predeterminado.
- El asistente de futuras actualizaciones inicia el servidor sin duplicar
  pestañas y abre el navegador después de verificar la versión instalada.

## [0.7.8] - 2026-07-26

- La configuración y la importación manual explican claramente que los JSON
  pueden eliminarse después de importarlos correctamente.
- Las carreras y estadísticas ya importadas permanecen guardadas en la base
  local; no es necesario acumular los archivos originales.
- Se aclara que conservar los JSON solo es una copia adicional y que el límite
  de resultados de Content Manager es opcional.
- La sección de privacidad utiliza una explicación directa sobre la ubicación
  de la base de datos y la configuración local.

## [0.7.7] - 2026-07-26

- El actualizador espera ahora a que terminen todos los procesos de la
  instalación anterior antes de sustituir y volver a ejecutar GridScope.
- Después del reinicio comprueba que el servidor local responde y que ejecuta
  exactamente la versión recién instalada.
- Si la aplicación no llega a abrirse, el registro distingue ese problema de
  la instalación de archivos y muestra un mensaje específico.
- El asistente actualizado se conserva en la carpeta de instalación para las
  siguientes versiones.

## [0.7.6] - 2026-07-26

- Los Campeonatos GridScope de RaceRoom agrupan ahora cada campeonato ranked
  por año, en lugar de mostrar una temporada vacía basada en el formato de
  seasons de iRacing.
- Se ocultan automáticamente los periodos sin carreras puntuables.
- Las ayudas, tarjetas y tablas de RaceRoom utilizan Rating, Reputation,
  Incident Points y tamaño de parrilla, sin mezclar iRating, Safety Rating,
  SoF ni splits de iRacing.
- Los detalles de pilotos y carreras conservan las métricas propias GridScore
  y Limpieza, claramente separadas de las valoraciones oficiales de RaceRoom.
- Las comparativas frente a frente adaptan sus columnas a cada simulador. En
  Assetto Corsa se eliminan SoF y Split, se muestran parrilla y mejores vueltas
  y se omiten las posiciones de salida cuando Content Manager no las guardó.
- Las filas de «Tu progreso» en Comparativas abren ahora el resultado completo
  de la carrera mediante ratón o teclado.

## [0.7.5] - 2026-07-26

- Nuevo sistema de actualizaciones desde las versiones publicadas en GitHub.
- Comprobación automática opcional y búsqueda manual desde Configuración.
- Canales Beta y Estable independientes.
- Las instalaciones con `GridScope.exe` pueden descargar e instalar una versión
  confirmada por el usuario; las instalaciones desde código abren la descarga.
- Cada paquete se valida por nombre, origen, tamaño y huella SHA-256 antes de
  sustituir el ejecutable.
- Antes de actualizar se conserva `GridScope.previous.exe`; la base de datos y
  la configuración local no se modifican.

## [0.7.4] - 2026-07-26

- El piloto de referencia permanece destacado al principio de los Campeonatos
  GridScope y también aparece en su posición real dentro de la clasificación.
- Se corrige la apertura de una carrera desde un perfil de piloto cuando el
  detalle de esa carrera ya estaba abierto en una capa anterior.
- El selector inicial utiliza símbolos gráficos propios para cada simulador y
  elimina textos que podían sugerir una afiliación oficial.
- El mensaje de almacenamiento inicial se simplifica para indicar claramente
  que GridScope utiliza una base de datos local.

## [0.7.3] - 2026-07-25

- Se aceptan las URL públicas de RaceRoom con formato `/users/usuario/career`
  además de la variante interna `/r3e/users/usuario/career`.
- La configuración explica dónde cambiar posteriormente el perfil vinculado.

## [0.7.2] - 2026-07-25

- RaceRoom se incorpora como tercer simulador independiente.
- Configuración mediante URL o usuario del perfil público, sin contraseña.
- Sincronización ranked progresiva y reanudable en lotes de 25 carreras.
- Importación de posiciones, vueltas, incidentes, Rating y Reputation.
- Distancia mínima configurable: el piloto conserva la coincidencia desde que
  toma la salida, pero el resultado solo puntúa si alcanza el porcentaje
  exigido respecto a las vueltas del ganador.
- Carpeta local de resultados preparada para la futura importación de carreras
  no ranked.
- Textos, ayudas y etiquetas específicas de RaceRoom.

## [0.7.1] - 2026-07-25

- Se aclara que la importación de iRacing utiliza archivos JSON mientras la
  creación de nuevos Client ID de OAuth permanezca pausada, y que la integración
  directa llegará en una versión posterior cuando iRacing vuelva a habilitarlos.
- Primera beta pública de GridScope bajo PolyForm Noncommercial 1.0.0.

### Incluye

- Historial local independiente para iRacing y Assetto Corsa.
- Importación de resultados JSON y detección automática de series.
- Estadísticas por temporada, sesión, carrera, piloto y circuito.
- Comparativas, rivales recurrentes y perfiles globales.
- GridScore y Limpieza de GridScope.
- Campeonatos automáticos y campeonatos personalizados.
- Selección de series, periodos y pilotos para cada campeonato.
- Archivo histórico, telemetrías de iRacing y copias de seguridad.
- Imágenes y mapas locales de circuitos de Assetto Corsa.

### Estado beta

- La interfaz y el formato de la base pueden evolucionar antes de la versión
  1.0.0.
- La integración OAuth de iRacing depende de la disponibilidad de Client IDs.
- El ejecutable de Windows todavía no dispone de firma digital.
