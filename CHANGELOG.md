# Historial de cambios

Este proyecto sigue [Versionado Semántico](https://semver.org/lang/es/).

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
