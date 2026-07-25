# GridScope

GridScope es una aplicación local de estadísticas para **iRacing**,
**Assetto Corsa original** y **RaceRoom**. Organiza resultados, temporadas, rivales,
comparativas y Campeonatos GridScope sin subir el historial del usuario a
ningún servidor.

> Versión actual: **0.7.2 Beta**

## Funciones principales

- Importación de resultados JSON de iRacing. La integración directa con su API
  se añadirá en una versión posterior cuando iRacing vuelva a permitir crear
  nuevos clientes OAuth.
- Lectura automática del historial de Content Manager para Assetto Corsa.
- Sincronización progresiva del historial ranked público de RaceRoom, con
  Rating, Reputation, incidentes y distancia completada.
- Separación completa de los datos de cada simulador.
- Resúmenes por temporada, semana, carrera, circuito y piloto.
- Comparativas frente a rivales recurrentes.
- GridScore y Limpieza como métricas propias y claramente diferenciadas de
  iRating y Safety Rating.
- Campeonatos automáticos mensuales, por temporada, anuales e históricos.
- Campeonatos personalizados por series, fechas, pilotos y participación
  mínima.
- Clasificación por todas las carreras o mediante media semanal.
- Archivo histórico local y copias de seguridad.
- Uso de imágenes y mapas de circuitos desde la instalación local de Assetto
  Corsa cuando están disponibles.

## Privacidad

GridScope funciona en el ordenador del usuario y escucha únicamente en
`127.0.0.1`. Los resultados, configuraciones y credenciales no se envían a
GridScope ni a servicios propios.

En una instalación pública nueva, los datos se guardan en:

```text
%LOCALAPPDATA%\GridScope
```

Las instalaciones antiguas que ya tengan `data\apex-local.db` junto al código
continúan utilizando esa base para no perder su historial.

## Instalar en Windows

### Versión preparada

1. Descarga `GridScope-0.7.2-Windows.zip` desde GitHub Releases.
2. Descomprime el archivo.
3. Ejecuta `GridScope.exe`.
4. Mantén abierta la ventana del servidor mientras utilizas la aplicación.

Windows puede mostrar una advertencia al tratarse de una aplicación nueva sin
firma digital. El código fuente completo está disponible en este repositorio
para su revisión.

### Desde el código fuente

Requiere Python 3.11 o posterior:

```powershell
python server.py --open-browser
```

También puedes ejecutar `abrir-aplicacion.ps1`. Después, GridScope estará
disponible en `http://127.0.0.1:4173`.

No abras `index.html` directamente: la persistencia local necesita el servidor
Python.

## Primera configuración

Al abrir GridScope por primera vez se elige el simulador.

### iRacing

Indica tu Customer ID y la carpeta donde guardas los resultados JSON. La API de
datos de iRacing existe, pero actualmente iRacing mantiene pausada la creación
de nuevos Client ID de OAuth para aplicaciones de terceros. Por ese motivo,
esta versión importa los resultados manualmente o los lee desde una carpeta
configurable. Cuando iRacing vuelva a habilitar las altas, GridScope añadirá la
integración directa en una versión posterior.

Puedes consultar el
[estado oficial de los Client ID de OAuth](https://support.iracing.com/support/solutions/articles/31000177790-oauth-client-credentials).

### Assetto Corsa

Indica los nombres o alias con los que apareces y revisa la carpeta de sesiones
de Content Manager. Su ubicación habitual es:

```text
%LOCALAPPDATA%\AcTools Content Manager\Progress\Sessions
```

La carpeta correcta contiene archivos `.json` generados al terminar sesiones.
GridScope reconoce prácticas y clasificaciones, pero solo las carreras puntúan.
En sesiones locales excluye los rivales identificados como IA.

### RaceRoom

Pega la URL pública de tu perfil o tu nombre de usuario de RaceRoom. GridScope
consulta el apartado Career sin pedir contraseña y guarda el historial ranked
en lotes de 25 carreras. Si la operación se interrumpe, la siguiente
sincronización omite lo ya guardado y continúa con lo pendiente.

Todos los pilotos que toman la salida cuentan como coincidencia. Para puntuar
en clasificaciones y duelos deben completar el porcentaje mínimo configurable
de las vueltas del ganador; el valor inicial recomendado es el 50%. La carpeta
local de resultados queda configurada para incorporar carreras no ranked en una
fase posterior.

## Campeonatos GridScope

Los campeonatos automáticos se actualizan al importar resultados. También
puedes crear campeonatos propios configurando:

- una, varias o todas las series;
- un intervalo de fechas;
- rivales recurrentes, todos los coincidentes o pilotos concretos;
- inclusión del piloto de referencia;
- carreras mínimas;
- peso idéntico por carrera o media semanal.

Una carrera puntúa cuando coinciden al menos dos miembros. El primero entre los
miembros presentes recibe 100 puntos, el último 0 y el resto una puntuación
proporcional.

## Desarrollo

La aplicación utiliza exclusivamente la biblioteca estándar de Python en
tiempo de ejecución. Para ejecutar las pruebas:

```powershell
python -m unittest discover -s tests -v
```

Para generar un paquete público limpio:

```powershell
.\scripts\crear-version-publica.ps1
```

El paquete nunca incluye bases SQLite, copias de seguridad, registros,
credenciales, rutas personales ni cachés locales.

## Versionado

GridScope utiliza [Versionado Semántico](https://semver.org/lang/es/):

- `0.7.x`: correcciones compatibles de esta beta.
- `0.8.0`: siguiente grupo de funciones importantes.
- `1.0.0`: primera versión estable para uso general.

Consulta [CHANGELOG.md](CHANGELOG.md) para conocer los cambios de cada versión.

## Proyecto independiente

GridScope es un proyecto comunitario independiente y no está afiliado,
patrocinado ni respaldado por iRacing.com Motorsport Simulations, Kunos
Simulazioni, Low Fuel Motorsport ni Content Manager. Las marcas pertenecen a
sus respectivos propietarios.

## Licencia

Distribuido bajo la
[PolyForm Noncommercial License 1.0.0](LICENSE).
