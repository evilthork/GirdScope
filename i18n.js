(() => {
  const SUPPORTED = new Set(["es", "en"]);
  const stored = localStorage.getItem("gridscope-language");
  let language = SUPPORTED.has(stored)
    ? stored
    : String(navigator.language || "es").toLowerCase().startsWith("en") ? "en" : "es";

  const EN = new Map(Object.entries({
    "Tu archivo de competición": "Your racing archive",
    "Elige dónde corres.": "Choose where you race.",
    "GridScope organiza el resto.": "GridScope organizes the rest.",
    "Importa tus resultados locales, descubre rivales recurrentes y conserva un historial que no depende de servicios externos.": "Import your local results, discover recurring rivals, and keep a history that does not depend on external services.",
    "Series oficiales, splits, SoF, iRating, Safety Rating y resultados completos.": "Official series, splits, SoF, iRating, Safety Rating, and complete results.",
    "Historial de Content Manager, vueltas, sectores, coches, circuitos y rivales.": "Content Manager history, laps, sectors, cars, circuits, and rivals.",
    "Rating, reputación, incidentes, posiciones y rivales de todas tus carreras ranked.": "Rating, reputation, incidents, positions, and rivals from all your ranked races.",
    "Entrar": "Enter",
    "Base de datos local.": "Local database.",
    "Tus resultados y ajustes se guardan únicamente en este ordenador.": "Your results and settings are stored only on this computer.",
    "← Volver a simuladores": "← Back to simulators",
    "Primera configuración": "First-time setup",
    "Configurar simulador": "Configure simulator",
    "Piloto de referencia": "Reference driver",
    "Todos los nombres con los que corres": "All the names you race under",
    "GridScope los unirá como un solo piloto. Puedes añadir o quitar alias cuando quieras.": "GridScope will merge them into one driver. You can add or remove aliases at any time.",
    "Carpeta de resultados": "Results folder",
    "Carpeta de instalación de Assetto Corsa": "Assetto Corsa installation folder",
    "Se utiliza para mostrar las imágenes y los trazados originales, incluidos los circuitos mod.": "Used to display original images and track maps, including mod tracks.",
    "Distancia mínima para puntuar": "Minimum distance to score",
    "El piloto aparece como coincidencia desde que toma la salida, pero solo puntúa si completa este porcentaje de las vueltas del ganador.": "A driver appears as a match after starting, but only scores after completing this percentage of the winner's laps.",
    "Actualizar automáticamente": "Update automatically",
    "GridScope comprobará la carpeta cada minuto mientras esté abierto.": "GridScope will check the folder every minute while it is open.",
    "Guardar y analizar resultados": "Save and analyze results",
    "La carpeta original nunca se modifica ni se elimina. GridScope solo lee los archivos compatibles.": "The original folder is never changed or deleted. GridScope only reads compatible files.",
    "Campeonato": "Championship",
    "Mis campeonatos": "My championships",
    "Todas": "All",
    "Actuales": "Current",
    "Históricas": "Historical",
    "Resumen": "Overview",
    "Sesiones": "Sessions",
    "Pilotos": "Drivers",
    "Comparativas": "Comparisons",
    "Campeonatos": "Championships",
    "Archivo global": "Global archive",
    "Simulador activo": "Active simulator",
    "Configuración": "Settings",
    "Base local activa": "Local database active",
    "SQLite · Solo este ordenador": "SQLite · This computer only",
    "Resumen de temporada": "Season overview",
    "Datos de demostración": "Demo data",
    "Resultados importados": "Imported results",
    "Actualizar": "Refresh",
    "Nueva versión disponible": "New version available",
    "Puedes instalarla desde Configuración.": "You can install it from Settings.",
    "Ver actualización": "View update",
    "Temporada": "Season",
    "Tu resumen y circuitos": "Your overview and circuits",
    "Clasificación": "Standings",
    "General de pilotos": "Overall driver standings",
    "Evolución": "Progress",
    "Valoraciones y rendimiento": "Ratings and performance",
    "TEMPORADA ACTUAL": "CURRENT SEASON",
    "Road · Clase C": "Road · Class C",
    "Jornada actual": "Current round",
    "ÚLTIMO RESULTADO": "LATEST RESULT",
    "Estadísticas personales de la temporada": "Personal season statistics",
    "Resultados registrados en la serie y temporada seleccionadas.": "Results recorded in the selected series and season.",
    "Ver todas las sesiones": "View all sessions",
    "Carreras": "Races",
    "Cargando datos": "Loading data",
    "Carrera": "Race",
    "Salida": "Start",
    "Meta": "Finish",
    "Tus inc.": "Your inc.",
    "Líder actual": "Current leader",
    "Más victorias": "Most wins",
    "Piloto más limpio": "Cleanest driver",
    "SoF medio": "Average SoF",
    "Media semanal": "Weekly average",
    "Todas las carreras": "All races",
    "Pos.": "Pos.",
    "Piloto": "Driver",
    "Inc. / sem.": "Inc. / week",
    "Semanas": "Weeks",
    "Victorias": "Wins",
    "Ver clasificación completa": "View full standings",
    "Evolución carrera a carrera": "Race-by-race progress",
    "Tu rendimiento": "Your performance",
    "Valores registrados después de cada carrera.": "Values recorded after each race.",
    "Rendimiento personal": "Personal performance",
    "Progresión de resultados": "Results progression",
    "Última carrera personal": "Latest personal race",
    "Sesiones de temporada": "Season sessions",
    "Cada semana, circuito y bloque de carreras importadas.": "Every week, circuit, and block of imported races.",
    "Importar JSON": "Import JSON",
    "Buscar resultados": "Find results",
    "Jornadas": "Rounds",
    "Series": "Series",
    "Tu historial organizado": "Your organized history",
    "Series y temporadas": "Series and seasons",
    "Encuentra rápidamente qué has corrido y abre la temporada que quieras consultar.": "Quickly find what you raced and open the season you want to review.",
    "Buscar serie, coche o temporada…": "Search series, car, or season…",
    "Actuales": "Current",
    "Históricas": "Historical",
    "Tu participación en iRacing": "Your iRacing participation",
    "Todas las series oficiales importadas, agrupadas con sus temporadas y resultados.": "All imported official series, grouped with their seasons and results.",
    "Campeonatos y servidores detectados": "Detected championships and servers",
    "Series de Assetto Corsa": "Assetto Corsa series",
    "Agrupadas por campeonato o servidor a partir del historial de Content Manager.": "Grouped by championship or server from Content Manager history.",
    "Historial ranked organizado": "Organized ranked history",
    "Campeonatos de RaceRoom": "RaceRoom championships",
    "Campeonatos ranked agrupados para consultar sus periodos y resultados.": "Ranked championships grouped to review their periods and results.",
    "En curso": "In progress",
    "agrupaciones diferentes": "different groups",
    "periodos guardados": "saved periods",
    "resultados importados": "imported results",
    "con temporada actual": "with a current season",
    "todo es histórico": "all history is archived",
    "No se han encontrado series": "No series found",
    "Prueba otro nombre, coche o temporada.": "Try another name, car, or season.",
    "ACTUAL": "CURRENT",
    "HISTÓRICA": "HISTORICAL",
    "Actual": "Current",
    "Abrir": "Open",
    "Archivo de sesiones": "Session archive",
    "Carreras importadas": "Imported races",
    "Abre una carrera para consultar la parrilla completa y todas sus estadísticas.": "Open a race to view the full grid and all its statistics.",
    "Semana": "Week",
    "Orden": "Order",
    "Más recientes": "Newest",
    "Más antiguas": "Oldest",
    "Mejor resultado": "Best result",
    "Parrilla": "Grid",
    "Participación, rendimiento y limpieza de cada piloto.": "Participation, performance, and cleanliness for each driver.",
    "Añadir piloto": "Add driver",
    "Recurrentes": "Recurring",
    "Una coincidencia": "One match",
    "Mostrando todos los pilotos": "Showing all drivers",
    "Rendimiento frente a frente": "Head-to-head performance",
    "Coincidencias y evolución contra los mismos pilotos.": "Matches and progress against the same drivers.",
    "Tu progreso": "Your progress",
    "Carrera a carrera": "Race by race",
    "Gráficas": "Charts",
    "Evolución y duelos": "Progress and duels",
    "Rivales recurrentes": "Recurring rivals",
    "Incidentes": "Incidents",
    "Lectura visual de las coincidencias": "Visual match overview",
    "Resultados personales y balance contra los rivales recurrentes.": "Personal results and record against recurring rivals.",
    "Rivales frecuentes": "Frequent rivals",
    "Historial compartido": "Shared history",
    "Rival": "Rival",
    "Coincidencias": "Matches",
    "Delante": "Ahead",
    "Detrás": "Behind",
    "% por delante": "% ahead",
    "Ventaja media": "Average advantage",
    "Inc. tú / rival": "Inc. you / rival",
    "Progreso reciente": "Recent progress",
    "Encuentros aislados": "Single encounters",
    "Rivales de una sola carrera": "One-race rivals",
    "Ventaja": "Advantage",
    "Competiciones construidas con tu historial": "Competitions built from your history",
    "Campeonatos GridScope": "GridScope Championships",
    "Utiliza los periodos automáticos o crea una clasificación con las series, fechas y pilotos que tú elijas.": "Use automatic periods or create standings with the series, dates, and drivers you choose.",
    "Crear campeonato": "Create championship",
    "Configuraciones guardadas": "Saved configurations",
    "Se guardan únicamente en este ordenador.": "Stored only on this computer.",
    "Campeonatos automáticos": "Automatic championships",
    "Se actualizan al importar nuevas carreras": "Updated when new races are imported",
    "Editar configuración": "Edit configuration",
    "Periodo histórico": "Historical period",
    "Datos principales": "Key data",
    "Cómo se calcula": "How it is calculated",
    "Periodo": "Period",
    "Clasificación de recurrentes": "Recurring drivers standings",
    "Carreras mínimas para clasificarse": "Minimum races to qualify",
    "Todos aparecen; quien no alcance el mínimo queda provisional.": "Everyone is shown; drivers below the minimum remain provisional.",
    "Índice": "Index",
    "Duelos G/P": "Duels W/L",
    "% ganado": "% won",
    "Series": "Series",
    "Inc./carrera": "Inc./race",
    "Limpieza": "Cleanliness",
    "Frente a ti": "Against you",
    "Anterior": "Previous",
    "Siguiente": "Next",
    "Calendario combinado": "Combined calendar",
    "Carreras puntuables": "Scoring races",
    "Todo el archivo local": "Entire local archive",
    "Resumen global": "Global overview",
    "Estadísticas combinadas de todas las series y temporadas importadas.": "Combined statistics from all imported series and seasons.",
    "Guardar temporada actual": "Save current season",
    "Historial": "History",
    "Series y temporadas": "Series and seasons",
    "Guardar y exportar": "Save and export",
    "Temporada seleccionada": "Selected season",
    "Conservación y exportación": "Retention and export",
    "Guarda sus resultados para no depender de futuras consultas a iRacing.": "Save its results so they do not depend on future iRacing queries.",
    "EN CURSO": "IN PROGRESS",
    "Temporada actual": "Current season",
    "Abrir": "Open",
    "Exportar": "Export",
    "Tu histórico empieza aquí": "Your history starts here",
    "Al archivar una temporada conservaremos sus carreras, cálculos y clasificación final en este ordenador.": "Archiving a season keeps its races, calculations, and final standings on this computer.",
    "Preferencias": "Preferences",
    "Reglas, fuentes de resultados y almacenamiento local.": "Rules, result sources, and local storage.",
    "Guardar cambios": "Save changes",
    "General": "General",
    "Identidad y reglas": "Identity and rules",
    "Fuentes de datos": "Data sources",
    "Importación y sincronización": "Import and synchronization",
    "Aplicación": "Application",
    "Actualizaciones y copias": "Updates and backups",
    "Reglas de clasificación": "Standings rules",
    "Clasificación principal": "Main standings",
    "Media de todas las carreras": "All-race average",
    "Participación mínima": "Minimum participation",
    "Primer desempate": "First tiebreaker",
    "Menor media de incidentes": "Lowest average incidents",
    "Más semanas participadas": "Most weeks participated",
    "Más victorias": "Most wins",
    "Mi ID de iRacing": "My iRacing ID",
    "Se utiliza para las comparativas y para destacar tus resultados.": "Used for comparisons and to highlight your results.",
    "Mis alias de Assetto Corsa": "My Assetto Corsa aliases",
    "Todos estos nombres se consideran el mismo piloto en estadísticas y comparativas.": "All these names are treated as the same driver in statistics and comparisons.",
    "API OAuth de iRacing": "iRacing OAuth API",
    "Opcional": "Optional",
    "Piloto de referencia configurado": "Reference driver configured",
    "La identidad se utiliza localmente para reconocer tus resultados y comparativas.": "The identity is used locally to recognize your results and comparisons.",
    "Conexión con iRacing pendiente": "iRacing connection pending",
    "La importación mediante JSON continúa disponible.": "JSON import remains available.",
    "Conectar con iRacing": "Connect to iRacing",
    "Volver a conectar": "Reconnect",
    "Desconectar": "Disconnect",
    "Integración preparada por GridScope": "Integration managed by GridScope",
    "La conexión se autoriza en la web oficial de iRacing. No necesitas configurar identificadores ni secretos.": "Authorization takes place on the official iRacing website. You do not need to configure identifiers or secrets.",
    "La creación de nuevos Client ID continúa pausada por iRacing. La conexión se activará automáticamente en una actualización cuando GridScope reciba su identificador oficial.": "iRacing is still pausing new Client IDs. The connection will be enabled automatically in an update when GridScope receives its official identifier.",
    "Consultar estado oficial": "View official status",
    "Redirect registrado:": "Registered redirect:",
    "Tu contraseña nunca se guardará en esta aplicación.": "Your password is never stored in this application.",
    "Ruta de los JSON": "JSON folder path",
    "Buscar automáticamente": "Search automatically",
    "Comprueba la carpeta cada minuto mientras la web está abierta.": "Checks the folder every minute while GridScope is open.",
    "Guardar carpeta": "Save folder",
    "Buscar ahora": "Search now",
    "Solo se revisan archivos `.json` de esta carpeta, sin entrar en subcarpetas.": "Only `.json` files in this folder are checked; subfolders are not scanned.",
    "¿Puedo borrar los JSON?": "Can I delete the JSON files?",
    "Sí. Después de importarlos correctamente puedes eliminarlos y liberar espacio; las carreras y estadísticas ya están guardadas en GridScope. No necesitas acumular los archivos originales.": "Yes. After a successful import, you can delete them to free up space; the races and statistics are already stored in GridScope. You do not need to keep the original files.",
    "Carpeta de telemetrías": "Telemetry folder",
    "Ruta de los archivos IBT": "IBT file path",
    "Archivos": "Files",
    "Con carrera": "Linked to race",
    "Prácticas": "Practice",
    "Historial de Content Manager": "Content Manager history",
    "Instalación de Assetto Corsa": "Assetto Corsa installation",
    "Cómo funciona": "How it works",
    "Guardar configuración": "Save configuration",
    "Historial ranked de RaceRoom": "RaceRoom ranked history",
    "Perfil público o usuario": "Public profile or username",
    "Carpeta de resultados locales": "Local results folder",
    "Sincronizar 25 carreras": "Sync 25 races",
    "Qué se importa y cómo puntúa": "What is imported and how it scores",
    "Historial ranked": "Ranked history",
    "Coincidir no significa puntuar": "A match does not always score",
    "Sincronización reanudable": "Resumable synchronization",
    "No ranked": "Unranked",
    "Actualizaciones de GridScope": "GridScope updates",
    "Consulta las versiones publicadas en GitHub. La instalación siempre requiere tu confirmación.": "Check versions published on GitHub. Installation always requires your confirmation.",
    "Versión instalada": "Installed version",
    "Canal de actualizaciones": "Update channel",
    "Beta · nuevas funciones": "Beta · new features",
    "Estable · solo versiones finales": "Stable · final releases only",
    "Mientras GridScope esté en beta, el canal Beta recibe las versiones 0.x.": "While GridScope is in beta, the Beta channel receives 0.x releases.",
    "Comprobar al iniciar": "Check on startup",
    "Solo consulta el número de versión; nunca descarga ni instala sin permiso.": "Only the version number is checked; nothing is downloaded or installed without permission.",
    "Buscar actualizaciones": "Check for updates",
    "Descargar e instalar": "Download and install",
    "Novedades": "What's new",
    "Datos locales": "Local data",
    "Temporadas guardadas": "Saved seasons",
    "Carreras almacenadas": "Stored races",
    "Archivos importados": "Imported files",
    "Telemetrías indexadas": "Indexed telemetry files",
    "Última copia": "Latest backup",
    "Sin copias": "No backups",
    "Crear copia de seguridad": "Create backup",
    "Idioma": "Language",
    "Idioma de la aplicación": "Application language",
    "Apariencia": "Appearance",
    "Elige el estilo visual que prefieras.": "Choose your preferred visual style.",
    "Tema visual": "Visual theme",
    "El diseño original": "The original design",
    "Oscuro, neutro y compacto": "Dark, neutral, and compact",
    "Claro": "Light",
    "Alta legibilidad con luz": "High readability in bright environments",
    "Español": "Spanish",
    "Inglés": "English",
    "El cambio se aplica a toda la interfaz y queda guardado en este ordenador.": "The change applies to the entire interface and is saved on this computer.",
    "Cancelar": "Cancel",
    "Cerrar esta": "Close this",
    "Cerrar todas": "Close all",
    "Eliminar": "Delete",
    "Guardar campeonato": "Save championship"
  }));

  const originals = new WeakMap();
  let applying = false;

  function translated(value) {
    if (language !== "en") return value;
    const leading = value.match(/^\s*/)?.[0] || "";
    const trailing = value.match(/\s*$/)?.[0] || "";
    const core = value.trim();
    return EN.has(core) ? `${leading}${EN.get(core)}${trailing}` : value;
  }

  function applyTextNode(node, refreshOriginal = false) {
    if (!node.data.trim()) return;
    if (!originals.has(node) || refreshOriginal) originals.set(node, node.data);
    const source = originals.get(node);
    const next = language === "es" ? source : translated(source);
    if (node.data !== next) node.data = next;
  }

  function apply(root = document) {
    applying = true;
    try {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
          const tag = node.parentElement?.tagName;
          return tag && !["SCRIPT", "STYLE", "CODE", "PRE"].includes(tag) && node.data.trim()
            ? NodeFilter.FILTER_ACCEPT
            : NodeFilter.FILTER_REJECT;
        }
      });
      let node;
      while ((node = walker.nextNode())) applyTextNode(node);
      const elements = root.querySelectorAll ? root.querySelectorAll("[placeholder], [title], [aria-label]") : [];
      elements.forEach((element) => {
        ["placeholder", "title", "aria-label"].forEach((attribute) => {
          if (!element.hasAttribute(attribute)) return;
          const storage = `i18n${attribute.replace(/(^|-)(\w)/g, (_m, _p, c) => c.toUpperCase())}`;
          if (!element.dataset[storage]) element.dataset[storage] = element.getAttribute(attribute);
          const source = element.dataset[storage];
          element.setAttribute(attribute, language === "es" ? source : translated(source));
        });
      });
      document.documentElement.lang = language;
    } finally {
      applying = false;
    }
  }

  const observer = new MutationObserver((mutations) => {
    if (applying) return;
    applying = true;
    try {
      mutations.forEach((mutation) => {
        if (mutation.type === "characterData") {
          const source = originals.get(mutation.target);
          const expected = source == null
            ? null
            : language === "es" ? source : translated(source);
          if (expected === mutation.target.data) return;
          applyTextNode(mutation.target, true);
        } else {
          mutation.addedNodes.forEach((node) => {
            if (node.nodeType === Node.TEXT_NODE) applyTextNode(node);
            else if (node.nodeType === Node.ELEMENT_NODE) apply(node);
          });
        }
      });
    } finally {
      applying = false;
    }
  });

  function setLanguage(nextLanguage) {
    language = SUPPORTED.has(nextLanguage) ? nextLanguage : "es";
    localStorage.setItem("gridscope-language", language);
    apply(document);
  }

  window.GridScopeI18n = {
    apply,
    setLanguage,
    getLanguage: () => language,
    locale: () => language === "en" ? "en-US" : "es-ES",
    translate: (value) => translated(String(value ?? ""))
  };

  apply(document);
  observer.observe(document.body, { childList: true, subtree: true, characterData: true });
})();

