# Historial de cambios

Este proyecto sigue [Versionado Semántico](https://semver.org/lang/es/).

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
