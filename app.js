let appState = {
  platform: "iracing",
  league: { totalWeeks: 12, weeksCompleted: 6 },
  leagues: [],
  drivers: [],
  rounds: [],
  settings: {
    rankingMode: "weekly",
    minimumParticipation: 50,
    tiebreaker: "incidents",
    oauthStatus: "disconnected",
    importFolder: "",
    autoScanImports: false,
    telemetryFolder: "",
    autoScanTelemetry: false,
    ownerIracingId: ""
  },
  oauth: {
    configured: false,
    clientId: "",
    connected: false,
    profileName: null,
    profileCustId: null
  },
  demoMode: true,
  storage: { archiveCount: 0, raceCount: 0, importCount: 0, telemetryCount: 0, linkedTelemetryCount: 0, practiceTelemetryCount: 0, lastBackup: null }
};
let bootstrapState = null;

const pageTitles = {
  overview: "Resumen de temporada",
  rounds: "Sesiones y carreras",
  drivers: "Pilotos de la liga",
  rivals: "Comparativas y rivales",
  "mini-leagues": "Campeonatos GridScope",
  history: "Archivo global",
  settings: "Configuración"
};

const rankingBody = document.querySelector("#rankingBody");
const rankingButtons = document.querySelectorAll("[data-ranking]");
const rankingLabel = document.querySelector(".ranking-label");
const navButtons = document.querySelectorAll("[data-view]");
const directViewButtons = document.querySelectorAll("[data-view-target]");
const views = document.querySelectorAll(".view");
const pageTitle = document.querySelector("#pageTitle");
const toast = document.querySelector("#toast");
const activityIndicator = document.querySelector("#activityIndicator");
const simulatorGateway = document.querySelector("#simulatorGateway");
const simulatorChooser = document.querySelector("#simulatorChooser");
const simulatorSetup = document.querySelector("#simulatorSetup");
const appShell = document.querySelector("#appShell");
const sidebar = document.querySelector("#sidebar");
const mobileOverlay = document.querySelector("#mobileOverlay");
const driverDialog = document.querySelector("#driverDialog");
const importDialog = document.querySelector("#importDialog");
const resultFileInput = document.querySelector("#resultFileInput");
const importDropzone = document.querySelector("#importDropzone");
const importFileList = document.querySelector("#importFileList");
const confirmImportButton = document.querySelector("#confirmImportButton");
const raceDetailDialog = document.querySelector("#raceDetailDialog");
const sessionDetailDialog = document.querySelector("#sessionDetailDialog");
const sessionDriverDialog = document.querySelector("#sessionDriverDialog");
const rivalDetailDialog = document.querySelector("#rivalDetailDialog");
const championshipDialog = document.querySelector("#championshipDialog");
const detailDialogs = [
  raceDetailDialog,
  sessionDetailDialog,
  sessionDriverDialog,
  rivalDetailDialog
];

function showDetailDialogOnTop(dialog) {
  if (dialog.open) dialog.close();
  dialog.showModal();
}
let pendingImports = [];
let raceAnalysis = { ownerIracingId: "", races: [] };
let rivalAnalysis = { owner: null, summary: {}, rivals: [] };
let globalAnalysis = { totals: {}, seasons: [], recentRaces: [] };
let miniLeagueAnalysis = { ownerIracingId: "", leagues: {} };
let telemetryAnalysis = { files: [] };
let ownerSeasonAnalysis = null;
let activeMiniLeagueScope = "eternal";
let activeCustomChampionshipId = null;
let championshipSelectedDriverIds = new Set();
const activeMiniLeaguePeriods = {
  monthly: null,
  season: null,
  yearly: null,
  eternal: "eternal"
};
let miniLeagueSort = { key: "position", direction: "asc" };
let miniLeagueMinimumRaces = Math.min(
  999,
  Math.max(1, Number(localStorage.getItem("gridscope-mini-minimum-races")) || 2)
);
let currentSessionDetail = null;
let toastTimeout;
let automaticScanRunning = false;
let activitySequence = 0;
let activityDelay = null;
const activeActivities = new Map();

function renderActivityIndicator() {
  const activity = Array.from(activeActivities.values()).at(-1);
  if (!activity) {
    clearTimeout(activityDelay);
    activityDelay = null;
    activityIndicator.hidden = true;
    appShell?.removeAttribute("aria-busy");
    simulatorGateway?.removeAttribute("aria-busy");
    return;
  }
  document.querySelector("#activityTitle").textContent = activity.title;
  document.querySelector("#activityMessage").textContent = activity.message;
  activityIndicator.hidden = false;
  appShell?.setAttribute("aria-busy", "true");
  simulatorGateway?.setAttribute("aria-busy", "true");
}

function beginActivity(title, message, { delay = 180 } = {}) {
  const token = ++activitySequence;
  activeActivities.set(token, { title, message });
  if (!activityIndicator.hidden) {
    renderActivityIndicator();
  } else {
    clearTimeout(activityDelay);
    activityDelay = setTimeout(() => {
      activityDelay = null;
      if (activeActivities.size) renderActivityIndicator();
    }, delay);
  }
  return token;
}

function endActivity(token) {
  activeActivities.delete(token);
  if (activeActivities.size) {
    if (!activityIndicator.hidden) renderActivityIndicator();
    return;
  }
  renderActivityIndicator();
}

function dialogLoadingMarkup(title, message) {
  return `<div class="dialog-loading-state">
    <span class="activity-spinner" aria-hidden="true"></span>
    <strong>${escapeHtml(title)}</strong>
    <small>${escapeHtml(message)}</small>
  </div>`;
}

function setButtonBusy(button, busy, label = "Procesando…") {
  if (!button) return;
  if (busy) {
    if (!button.dataset.idleHtml) button.dataset.idleHtml = button.innerHTML;
    button.disabled = true;
    button.classList.add("is-busy");
    button.textContent = label;
  } else {
    button.disabled = false;
    button.classList.remove("is-busy");
    if (button.dataset.idleHtml) {
      button.innerHTML = button.dataset.idleHtml;
      delete button.dataset.idleHtml;
    }
  }
}

const simulatorCopy = {
  iracing: {
    name: "iRacing",
    mark: "iR",
    eyebrow: "Primera configuración · iRacing",
    title: "Conecta tu archivo de resultados.",
    description: "Esta versión lee las exportaciones JSON oficiales de iRacing porque la creación de nuevos Client ID de OAuth está pausada. La integración directa se añadirá cuando iRacing vuelva a habilitarlos.",
    ownerLabel: "Tu ID de piloto de iRacing",
    ownerHelp: "Es el número visible en tu perfil; no es un Client ID de OAuth.",
    folderLabel: "Carpeta donde descargas los JSON",
    folderHelp: "Normalmente es la carpeta Descargas. Puedes cambiarla más adelante.",
    steps: [
      ["Exporta resultados", "Descarga el JSON completo desde la página de cada carrera."],
      ["GridScope los organiza", "Serie, temporada, semana y pilotos se detectan automáticamente."],
      ["Conserva el histórico", "La base local evita depender de resultados antiguos en la web."]
    ]
  },
  "assetto-corsa": {
    name: "Assetto Corsa",
    mark: "AC",
    eyebrow: "Primera configuración · Assetto Corsa original",
    title: "Tu historial ya está en el ordenador.",
    description: "Content Manager guarda las sesiones automáticamente. GridScope separa carreras, clasificación y prácticas para construir estadísticas y comparativas.",
    ownerLabel: "Nombre con el que apareces en Assetto Corsa",
    ownerHelp: "Debe coincidir con tu nombre de piloto. Los prefijos de parrilla de LFM se eliminan automáticamente.",
    folderLabel: "Carpeta Sessions de Content Manager",
    folderHelp: "Suele estar dentro de AppData\\Local\\AcTools Content Manager\\Progress\\Sessions.",
    steps: [
      ["Content Manager guarda", "Cada sesión terminada genera un archivo JSON local."],
      ["Solo puntúan carreras", "Prácticas y clasificaciones se reconocen, pero no alteran los campeonatos."],
      ["Analiza cada vuelta", "Se importan posiciones, coches, circuitos, mejores vueltas, sectores e incidentes."]
    ]
  }
};

async function apiRequest(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {})
    }
  });

  if (!response.ok) {
    let message = "No se ha podido completar la operación";
    try {
      const payload = await response.json();
      message = payload.error || message;
    } catch {
      // The generic message is enough when the response is not JSON.
    }
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }

  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : response;
}

async function loadBootstrap() {
  bootstrapState = await apiRequest("/api/bootstrap");
  return bootstrapState;
}

function openSimulatorChooser() {
  appShell.hidden = true;
  simulatorGateway.hidden = false;
  simulatorChooser.hidden = false;
  simulatorSetup.hidden = true;
  window.scrollTo({ top: 0, behavior: "auto" });
}

function openSimulatorSetup(simulator) {
  const copy = simulatorCopy[simulator];
  const saved = bootstrapState?.simulators?.[simulator] || {};
  document.querySelector("#setupSimulator").value = simulator;
  document.querySelector("#setupEyebrow").textContent = copy.eyebrow;
  document.querySelector("#setupTitle").textContent = copy.title;
  document.querySelector("#setupDescription").textContent = copy.description;
  document.querySelector("#setupOwnerLabel").textContent = copy.ownerLabel;
  document.querySelector("#setupOwnerHelp").textContent = copy.ownerHelp;
  document.querySelector("#setupFolderLabel").textContent = copy.folderLabel;
  document.querySelector("#setupFolderHelp").textContent = copy.folderHelp;
  document.querySelector("#setupOwnerIdentity").value = saved.ownerIdentity || "";
  document.querySelector("#setupOwnerIdentity").inputMode = simulator === "iracing" ? "numeric" : "text";
  document.querySelector("#setupAliasesField").hidden = simulator !== "assetto-corsa";
  document.querySelector("#setupOwnerAliases").value =
    simulator === "assetto-corsa" ? (saved.ownerAliases || saved.suggestedOwnerAliases || []).join("\n") : "";
  document.querySelector("#setupFolder").value = saved.folder || saved.suggestedFolder || "";
  document.querySelector("#setupInstallFolderField").hidden = simulator !== "assetto-corsa";
  document.querySelector("#setupInstallFolder").value =
    simulator === "assetto-corsa" ? (saved.installFolder || saved.suggestedInstallFolder || "") : "";
  document.querySelector("#setupAutoScan").checked = saved.autoScan !== false;
  document.querySelector("#setupSteps").innerHTML = copy.steps.map((step, index) => `
    <article><span>${index + 1}</span><div><strong>${escapeHtml(step[0])}</strong><small>${escapeHtml(step[1])}</small></div></article>
  `).join("");
  const detection = document.querySelector("#setupDetection");
  if (simulator === "assetto-corsa" && saved.suggestedFolderExists) {
    detection.className = "setup-detection detected";
    const aliasCount = (saved.ownerAliases || saved.suggestedOwnerAliases || []).length;
    detection.textContent = aliasCount > 1
      ? `Content Manager detectado. Se han encontrado ${aliasCount} nombres de piloto que puedes revisar antes de importar.`
      : "Content Manager detectado en este ordenador. La carpeta propuesta contiene su historial de sesiones.";
  } else {
    detection.className = "setup-detection";
    detection.textContent = simulator === "iracing"
      ? "La conexión directa no está disponible para nuevos clientes OAuth. GridScope revisará únicamente los JSON que descargues en esta carpeta."
      : "Si Content Manager está instalado en otra ubicación, pega aquí la ruta completa de su carpeta Sessions.";
  }
  simulatorChooser.hidden = true;
  simulatorSetup.hidden = false;
}

async function enterSimulator(simulator, { scan = true } = {}) {
  const simulatorName = simulatorCopy[simulator]?.name || "el simulador";
  const activity = beginActivity(
    `Abriendo ${simulatorName}…`,
    "Preparando la base local y las estadísticas guardadas."
  );
  try {
    await apiRequest("/api/simulators/active", {
      method: "PUT",
      body: JSON.stringify({ simulator })
    });
    simulatorGateway.hidden = true;
    appShell.hidden = false;
    await loadState({ quiet: true });
    if (!scan) return;
    if (simulator === "assetto-corsa" && appState.settings.autoScanAssettoCorsa) {
      await scanAssettoCorsaFolder({ quiet: true });
    } else if (simulator === "iracing" && appState.settings.autoScanImports) {
      await scanImportFolder({ quiet: true });
    }
  } finally {
    endActivity(activity);
  }
}

async function chooseSimulator(simulator) {
  const saved = bootstrapState?.simulators?.[simulator];
  if (!saved?.configured) {
    openSimulatorSetup(simulator);
    return;
  }
  try {
    await enterSimulator(simulator);
  } catch (error) {
    showToast("No se ha podido abrir el simulador", error.message);
  }
}

function formatDecimal(value) {
  return Number(value || 0).toFixed(2).replace(".", ",");
}

function driverIdentityText(driverId) {
  return (appState.settings.platform || appState.league.platform) === "assetto-corsa"
    ? "Piloto de Assetto Corsa"
    : `ID ${driverId}`;
}

function aliasesFromField(selector) {
  return document.querySelector(selector).value
    .split(/[\r\n,;]+/)
    .map((value) => value.trim())
    .filter(Boolean);
}

function formatInteger(value) {
  return Number(value || 0).toLocaleString("es-ES");
}

function formatLapTime(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds <= 0) return "—";
  const minutes = Math.floor(seconds / 60);
  const remainder = (seconds % 60).toFixed(3).padStart(6, "0");
  return `${minutes}:${remainder}`;
}

function formatSigned(value, suffix = "") {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return `${number > 0 ? "+" : ""}${number.toLocaleString("es-ES", { maximumFractionDigits: 2 })}${suffix}`;
}

function formatRaceDate(value) {
  if (!value) return "Fecha desconocida";
  return new Date(value).toLocaleString("es-ES", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function shortSeason(value) {
  const match = String(value || "").match(/(\d{4})\s+Season\s+(\d+)/i);
  return match ? `${match[1]} S${match[2]}` : String(value || "Temporada");
}

function seriesInitials(value) {
  const ignored = new Set(["iracing", "by", "the", "de", "la"]);
  const initials = String(value || "Serie")
    .replace(/[^a-záéíóúüñ0-9 ]/gi, " ")
    .split(/\s+/)
    .filter((word) => word && !ignored.has(word.toLowerCase()))
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();
  return initials || "IR";
}

function seriesTheme(value) {
  const palette = [
    { hex: "#ff7a2f", rgb: "255, 122, 47" },
    { hex: "#4e91ff", rgb: "78, 145, 255" },
    { hex: "#9f7aea", rgb: "159, 122, 234" },
    { hex: "#4dcc86", rgb: "77, 204, 134" },
    { hex: "#e16f85", rgb: "225, 111, 133" },
    { hex: "#d5ad4f", rgb: "213, 173, 79" }
  ];
  const hash = Array.from(String(value || "")).reduce(
    (total, character) => ((total * 31) + character.charCodeAt(0)) >>> 0,
    0
  );
  return palette[hash % palette.length];
}

function setLeagueMenuOpen(open) {
  const button = document.querySelector("#leagueMenuButton");
  const menu = document.querySelector("#leagueMenu");
  button.setAttribute("aria-expanded", String(open));
  menu.hidden = !open;
}

async function selectLeague(leagueId) {
  await apiRequest("/api/leagues/active", {
    method: "PUT",
    body: JSON.stringify({ leagueId: Number(leagueId) })
  });
  setLeagueMenuOpen(false);
  await loadState({ quiet: true });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function trackImageUrl(trackName, layout = "") {
  const platform = appState.settings?.platform || appState.league?.platform || "iracing";
  return `/api/assets/track?name=${encodeURIComponent(String(trackName || "Circuito"))}&layout=${encodeURIComponent(String(layout || ""))}&platform=${encodeURIComponent(platform)}`;
}

function seriesLogoUrl(logo, seriesName) {
  const platform = appState.settings?.platform || appState.league?.platform || "iracing";
  const fallbackName = platform === "assetto-corsa" ? "Serie de Assetto Corsa" : "Serie iRacing";
  return `/api/assets/series?logo=${encodeURIComponent(String(logo || ""))}&name=${encodeURIComponent(String(seriesName || fallbackName))}&platform=${encodeURIComponent(platform)}`;
}

function trackMapUrl(trackId, trackName, layout = "") {
  const platform = appState.settings?.platform || appState.league?.platform || "iracing";
  return `/api/assets/track-map?id=${encodeURIComponent(String(trackId || 0))}&name=${encodeURIComponent(String(trackName || "Circuito"))}&layout=${encodeURIComponent(String(layout || ""))}&platform=${encodeURIComponent(platform)}`;
}

function metricHelp(label, explanation) {
  return `${escapeHtml(label)}<button class="metric-help" type="button" data-tooltip="${escapeHtml(explanation)}" aria-label="Explicación de ${escapeHtml(label)}">?</button>`;
}

function gridScoreFormulaExplanation(platform = appState.settings?.platform || appState.league?.platform) {
  return platform === "assetto-corsa"
    ? "GridScore = Rendimiento × 75% + Limpieza × 25%. Rendimiento combina: resultado dentro de la parrilla 40%, posiciones ganadas o perdidas 15%, percentil de mejor vuelta 15%, regularidad de las vueltas 10%, porcentaje de carrera completada 10% y porcentaje de rivales recurrentes superados 10%. Si el JSON no contiene un componente, se excluye y los pesos disponibles se reajustan proporcionalmente."
    : "GridScore = Rendimiento × 75% + Limpieza × 25%. Rendimiento combina: resultado dentro de la parrilla 35%, posiciones ganadas o perdidas 15%, percentil de mejor vuelta 15%, porcentaje de carrera completada 10%, porcentaje de rivales recurrentes superados 10% y dificultad del SoF 15%. Si falta un componente, se excluye y los pesos disponibles se reajustan proporcionalmente. No modifica el iRating ni el Safety Rating oficiales.";
}

function gridRatingExplanation(platform = appState.settings?.platform || appState.league?.platform) {
  return `Media ponderada de hasta las 10 carreras más recientes. Cada carrera se calcula así: ${gridScoreFormulaExplanation(platform)} Las carreras con más duración y datos más completos tienen más peso. La variación compara el valor inicial, calculado con las primeras tres carreras disponibles, con el valor reciente.`;
}

function cleanlinessFormulaExplanation(platform = appState.settings?.platform || appState.league?.platform) {
  return platform === "assetto-corsa"
    ? "Primero se normaliza el contador de incidentes a una carrera equivalente de 30 minutos: incidentes ÷ minutos conducidos × 30. Después: Limpieza = máximo entre 0 y 100 − (incidentes por 30 minutos × 12,5). Ejemplos: 0 incidentes/30 min = 100 puntos; 4 = 50; 8 o más = 0. Content Manager proporciona el contador, pero el historial no permite asegurar que todos sus valores sean exclusivamente salidas de pista."
    : "Cuando el circuito incluye sus curvas: incidentes por 1.000 curvas = incidentes ÷ (vueltas completadas × curvas por vuelta) × 1.000; después, Limpieza = máximo entre 0 y 100 − (tasa × 1,5). Si faltan las curvas se usan incidentes por 30 minutos y se resta tasa × 8. Es una métrica de GridScope y no sustituye al Safety Rating.";
}

function cleanlinessRatingExplanation(platform = appState.settings?.platform || appState.league?.platform) {
  return `Media ponderada de la limpieza en hasta las 10 carreras más recientes. ${cleanlinessFormulaExplanation(platform)} Las carreras con más duración y datos más completos tienen más peso. La variación compara las primeras tres carreras disponibles con el valor reciente.`;
}

function confidenceExplanation() {
  return "Indica cuánta información respalda el GridScore; no mide velocidad. En cada carrera aumenta cuando existen más componentes de la fórmula, se completa más tiempo y la parrilla es mayor. En el periodo es baja con pocos datos, media desde 4 carreras y 60 minutos con cobertura suficiente, y alta desde 10 carreras y 180 minutos con buena cobertura.";
}

function raceCountExplanation() {
  return "Cuenta únicamente carreras válidas del periodo y simulador seleccionados en las que coincidieron al menos dos miembros del campeonato. Las prácticas, clasificaciones, carreras sin otro miembro y resultados ignorados durante la importación no suman.";
}

function duelExplanation() {
  return "En cada carrera, el piloto se compara por separado con todos los demás miembros del campeonato presentes. Terminar delante suma un duelo ganado y terminar detrás, uno perdido. Por ejemplo, coincidir con otros 5 miembros genera 5 duelos en esa carrera. El porcentaje ganado es victorias ÷ duelos totales × 100.";
}

function fieldContactExplanation(platform = appState.settings?.platform || appState.league?.platform, period = "el periodo indicado") {
  return platform === "assetto-corsa"
    ? `Suma del contador de incidentes guardado por Content Manager para todos los pilotos de todas las carreras válidas de ${period}. Es un total de parrilla y no representa únicamente al piloto de referencia. El historial no permite separar con certeza cada tipo de incidente.`
    : `Suma de los puntos de incidente registrados por iRacing para todos los pilotos de todas las carreras válidas de ${period}. Es un total de parrilla: no representa únicamente al piloto de referencia.`;
}

function personalContactExplanation(platform = appState.settings?.platform || appState.league?.platform) {
  return platform === "assetto-corsa"
    ? "Suma del contador de incidentes que Content Manager atribuye al piloto de referencia en sus carreras válidas. La media inferior se calcula como incidentes totales ÷ carreras y no incluye a los demás pilotos. El historial no permite separar con certeza cada tipo de incidente."
    : "Suma de los puntos de incidente que iRacing atribuye al piloto de referencia en sus carreras válidas. La media inferior se calcula como incidentes totales ÷ carreras; no incluye los incidentes de los demás pilotos.";
}

function gridScoreMarkup(result) {
  if (result?.gridScore == null) return "—";
  const components = result.scoreComponents || {};
  const isAssetto = (appState.settings?.platform || appState.league?.platform) === "assetto-corsa";
  const definitions = {
    finish: ["Resultado", isAssetto ? 40 : 35],
    progress: ["Progreso", 15],
    pace: ["Ritmo", 15],
    consistency: ["Regularidad", 10],
    completion: ["Carrera completada", 10],
    recurrent: ["Rivales recurrentes", 10],
    sof: ["Dificultad SoF", 15]
  };
  const breakdown = Object.entries(definitions)
    .filter(([key]) => components[key] != null)
    .map(([key, [label, weight]]) => `${label} ${formatDecimal(components[key])} × ${weight}%`)
    .join(" · ");
  const formula = `GridScore ${formatDecimal(result.gridScore)} = Rendimiento ${formatDecimal(result.performanceScore)} × 75% + Limpieza ${formatDecimal(result.cleanlinessScore)} × 25%. El rendimiento es la media ponderada de: ${breakdown}. Los componentes ausentes se excluyen y los pesos restantes se reajustan.`;
  return `<span class="assetto-score-stack"><strong>${formatDecimal(result.gridScore)}</strong><small>Rend. ${formatDecimal(result.performanceScore)}</small><button class="metric-help" type="button" data-tooltip="${escapeHtml(formula)}" aria-label="Desglose del GridScore">?</button></span>`;
}

function cleanlinessMarkup(result) {
  if (result?.cleanlinessScore == null) return "—";
  const isAssetto = (appState.settings?.platform || appState.league?.platform) === "assetto-corsa";
  const normalizedIncidents = result.incidentsPer1000Corners != null
    ? `${formatDecimal(result.incidentsPer1000Corners)}x / 1.000 curvas`
    : result.incidentsPer30Minutes != null
      ? `${formatDecimal(result.incidentsPer30Minutes)}x / 30 min`
      : result.cutsPer30Minutes != null
        ? `${formatDecimal(result.cutsPer30Minutes)}x / 30 min`
        : result.incidents != null
          ? `${formatDecimal(result.incidents)}x · sin distancia`
          : "normalización no disponible";
  let calculation;
  if (isAssetto && result.cutsPer30Minutes != null) {
    const minutes = result.drivingTimeMinutes != null ? formatDecimal(result.drivingTimeMinutes) : "—";
    calculation = `Limpieza ${formatDecimal(result.cleanlinessScore)} = máximo entre 0 y 100 − (${formatDecimal(result.cutsPer30Minutes)} incidentes por 30 min × 12,5). La tasa sale de ${formatDecimal(result.incidents)} incidentes ÷ ${minutes} minutos × 30. Content Manager proporciona el contador, pero no permite distinguir con certeza el tipo de cada incidente.`;
  } else if (result.incidentsPer1000Corners != null) {
    calculation = `Limpieza ${formatDecimal(result.cleanlinessScore)} = máximo entre 0 y 100 − (${formatDecimal(result.incidentsPer1000Corners)} incidentes por 1.000 curvas × 1,5). La tasa usa los incidentes, las vueltas completadas y las curvas por vuelta del circuito.`;
  } else if (result.incidentsPer30Minutes != null) {
    calculation = `Limpieza ${formatDecimal(result.cleanlinessScore)} = máximo entre 0 y 100 − (${formatDecimal(result.incidentsPer30Minutes)} incidentes por 30 min × 8). Se usa esta alternativa porque el JSON no incluye las curvas del circuito.`;
  } else {
    calculation = `Limpieza ${formatDecimal(result.cleanlinessScore)} calculada con ${formatDecimal(result.incidents)} incidentes. No hay distancia suficiente para normalizar el resultado.`;
  }
  return `<span class="assetto-score-stack cleanliness"><strong>${formatDecimal(result.cleanlinessScore)}</strong><small>${normalizedIncidents}</small><button class="metric-help" type="button" data-tooltip="${escapeHtml(calculation)}" aria-label="Desglose de la limpieza">?</button></span>`;
}

const metricGlossaryEntries = [
  [["pos", "posicion"], "Puesto del piloto dentro de este campeonato. Solo entran en el orden numerado quienes alcanzan el mínimo de carreras elegido; el resto permanece visible como provisional."],
  [["piloto", "rival"], "Persona identificada en los resultados importados. En Assetto Corsa se usa el nombre guardado por Content Manager; los alias configurados se unen como un mismo piloto."],
  [["media semanal"], "Media de las posiciones obtenidas en cada semana. Primero se calcula cada semana y después se promedian, por lo que todas pesan lo mismo."],
  [["media", "pos media", "posicion media", "meta media"], "Posición final media = suma de las posiciones de llegada ÷ número de carreras válidas. Un valor más bajo es mejor: P3,00 significa que el piloto terminó tercero de media."],
  [["indice"], "Media de los puntos internos obtenidos en las carreras del periodo. En cada carrera, entre los miembros del campeonato presentes, el primero recibe 100 puntos, el último 0 y los demás una cantidad proporcional a su posición. No es GridScore."],
  [["carrera", "carreras", "carreras analizadas", "carreras puntuables", "tus carreras"], "Número de carreras válidas incluidas después de aplicar el simulador, periodo y serie seleccionados. Las prácticas y clasificaciones no cuentan."],
  [["semanas"], "Número de semanas distintas de competición con al menos una carrera registrada."],
  [["serie", "series", "series combinadas"], "Número de campeonatos o grupos de carreras diferentes en los que participó el piloto durante este periodo. En Assetto Corsa se detectan a partir del servidor y de los datos guardados por Content Manager."],
  [["temporada", "temporadas"], "Periodo al que pertenecen los resultados importados. En iRacing corresponde a la temporada oficial; en Assetto Corsa se organiza a partir de las fechas del historial."],
  [["duelos g p", "duelos", "duelos disputados"], "Cada pareja de miembros presente en una carrera genera un duelo. G significa que el piloto terminó delante y P que terminó detrás. Ejemplo: con 10 miembros en una carrera, cada piloto disputa 9 duelos; por eso puede haber muchos más duelos que carreras."],
  [["ganado"], "Porcentaje de duelos ganados: duelos ganados ÷ total de duelos × 100. No es el porcentaje de carreras ganadas."],
  [["frente a ti", "comparacion"], "Balance directo contra el piloto de referencia configurado. El primer número son las veces que el piloto de referencia terminó delante; el segundo, las veces que este rival terminó delante."],
  [["coincidencias"], "Carreras en las que el piloto seleccionado y el piloto de referencia aparecen juntos."],
  [["participaciones"], "Número de carreras válidas del periodo en las que aparece el piloto. Una carrera suma una sola participación por piloto, aunque el archivo contenga más sesiones asociadas."],
  [["participantes", "pilotos", "pilotos unicos", "rivales distintos"], "Cantidad de pilotos diferentes que aparecen en las carreras válidas del periodo. Un mismo piloto solo se cuenta una vez."],
  [["miembros por carrera"], "Promedio de miembros del campeonato presentes por carrera: suma de miembros detectados en todas las carreras ÷ número de carreras puntuables."],
  [["referencia"], "Puesto real del piloto configurado como referencia. Su fila se fija arriba y se resalta para localizarla fácilmente, pero conserva aquí su posición verdadera en la clasificación."],
  [["comparacion historica"], "Compara el periodo seleccionado con el periodo anterior que tenga carreras puntuables. Se muestran ambos valores y, debajo, cuánto sube o baja el dato."],
  [["recurrentes", "rivales recurrentes"], "Pilotos que aparecen en al menos dos carreras del periodo junto al piloto de referencia. Una sola coincidencia no basta para considerarlo recurrente."],
  [["inc", "incidentes", "incidentes totales"], "Puntos de incidente registrados por iRacing en las carreras válidas. Si el dato aparece en una fila de piloto es personal; si indica «parrilla», suma a todos los participantes. GridScope muestra el valor del JSON y no lo estima."],
  [["tus incidentes", "incidentes personales"], "Suma de los puntos de incidente del piloto de referencia en sus propias carreras. No incluye los incidentes de los demás pilotos."],
  [["incidentes de parrilla", "inc. parrilla"], "Suma de los puntos de incidente de todos los pilotos incluidos en la carrera, sesión o archivo indicado."],
  [["inc media", "inc carrera", "inc sem"], "Media = suma de puntos de incidente ÷ número de carreras o semanas indicado por la etiqueta. El cálculo usa únicamente resultados válidos con el dato disponible."],
  [["incidentes medios"], "Puntos de incidente acumulados por todos los miembros ÷ total de participaciones de esos miembros en las carreras válidas. No es el total personal del piloto de referencia."],
  [["inc tu rival"], "Promedio de incidentes del piloto de referencia y del rival en sus carreras compartidas."],
  [["victorias", "mas victorias"], "Número de carreras válidas finalizadas en P1. Se usa la posición final del resultado, no la posición de salida ni la vuelta rápida."],
  [["top top"], "El primer valor cuenta llegadas entre P1 y P5; el segundo, llegadas entre P1 y P10. Una llegada en P4 suma en ambos grupos."],
  [["salida", "salida media", "tu salida", "salida rival"], "Posición ocupada en la parrilla al comenzar. Cuando se muestra la media: suma de posiciones de salida ÷ carreras con ese dato; un número más bajo indica una salida media más adelantada."],
  [["meta", "tu meta", "meta rival", "resultado"], "Posición final guardada en el resultado de carrera después de aplicar el orden de llegada disponible. P1 es la victoria; un número menor representa un mejor resultado."],
  [["posiciones"], "Posiciones ganadas = posición de salida − posición final. Salir P10 y acabar P6 produce +4; salir P3 y acabar P7 produce −4. Los valores del periodo son la suma de todas las carreras válidas."],
  [["mejor"], "Mejor posición final del periodo: se toma el número de llegada más bajo entre las carreras válidas. Por ejemplo, entre P8, P3 y P5, el mejor resultado es P3."],
  [["ganador"], "Piloto que figura en P1 en el resultado final de la carrera. Se usa la clasificación de llegada importada, no el mejor tiempo de vuelta."],
  [["lider actual", "cambios de lider", "lideradas"], "Las vueltas lideradas cuentan las vueltas completadas en P1; los cambios de líder indican cuántas veces cambió el primer puesto durante la carrera cuando el archivo contiene ese dato."],
  [["sof", "sof medio", "sof destacado"], "Strength of Field: estimación de la competitividad de la parrilla basada en el iRating de sus participantes."],
  [["split"], "División de la sesión asignada por iRacing cuando hay más inscritos de los que admite una única parrilla."],
  [["parrilla"], "Número de pilotos incluidos en el resultado final importado. Sirve como tamaño de referencia para normalizar la posición de llegada y no es el número de inscritos que no llegaron a participar."],
  [["irating", "irating actual", "irating actual en esta sesion"], "Valor oficial de habilidad competitiva que iRacing guarda para el piloto en ese resultado. GridScope solo lo muestra; no lo recalcula ni lo modifica."],
  [["irating inicial final"], "Primer iRating disponible del periodo → último iRating disponible. La variación es valor final − valor inicial; solo se usan carreras cuyo JSON contiene ambos datos."],
  [["sr", "safety rating", "safety rating actual", "safety rating actual en esta sesion"], "Safety Rating oficial que iRacing guarda para el piloto en ese resultado. GridScope solo lo muestra y mantiene separada su propia puntuación de Limpieza."],
  [["sr inicial final"], "Primer Safety Rating disponible del periodo → último Safety Rating disponible. La variación es valor final − valor inicial; no se estima cuando el JSON no incluye el dato."],
  [["gridscore", "gridscore actual", "gridscore medio"], "Valor propio de GridScope entre 0 y 100. Combina 75% de rendimiento y 25% de limpieza. En Assetto Corsa, el rendimiento usa resultado, posiciones ganadas, ritmo, regularidad, distancia completada y resultados frente a rivales recurrentes."],
  [["limpieza", "limpieza actual"], "Valor propio entre 0 y 100. En Assetto Corsa parte de los incidentes equivalentes por cada 30 minutos: 0 equivalen a 100 puntos, 4 a 50 y 8 o más a 0. Así se pueden comparar carreras de distinta duración."],
  [["confianza"], confidenceExplanation()],
  [["mejor vuelta", "vuelta rapida"], "Menor tiempo de vuelta válido guardado para el piloto o la sesión. Las vueltas sin tiempo, inválidas o no incluidas en el JSON no participan en la comparación."],
  [["vueltas"], "Número de vueltas que el resultado marca como completadas. Se utiliza junto con las vueltas previstas para calcular el porcentaje de carrera completada del GridScore."],
  [["intervalo"], "Diferencia de tiempo guardada por el resultado respecto al ganador o al piloto precedente, según la fuente. No se reconstruye si el archivo no contiene tiempos suficientes."],
  [["temperatura"], "Temperatura de pista o ambiente incluida en el archivo de la sesión. GridScope muestra el valor recibido y no lo estima cuando falta."],
  [["puntos"], "Puntos oficiales que iRacing asigna a ese resultado según su sistema de campeonato. Son independientes del Índice de GridScope y del GridScore."],
  [["ventaja media"], "En cada carrera compartida se calcula la diferencia entre ambas posiciones finales; después se suman esas diferencias y se dividen entre las coincidencias. El signo indica quién terminó delante de media."],
  [["por delante", "tu delante", "rival delante", "delante", "detras"], "Reparto de las carreras compartidas según qué piloto terminó en mejor posición."],
  [["circuitos"], "Número de combinaciones distintas de circuito y trazado presentes en las carreras válidas. Dos layouts del mismo circuito pueden contar como configuraciones diferentes."],
  [["archivos"], "Cantidad de archivos que la aplicación ha procesado y registrado. Un archivo repetido puede detectarse sin crear una carrera nueva, por lo que archivos revisados y carreras añadidas no siempre coinciden."],
  [["telemetria"], "Archivos IBT detectados y, cuando es posible, vinculados con una carrera importada mediante su identificador de subsesión."],
  [["canales"], "Variables de telemetría disponibles dentro del archivo IBT."],
  [["practicas"], "Sesiones de práctica detectadas. No se incluyen en clasificaciones ni estadísticas de carrera."],
  [["con carrera"], "Telemetrías vinculadas correctamente con un resultado de carrera importado."],
  [["progreso reciente"], "Diferencia entre el rendimiento del tramo inicial y el de las carreras más recientes del periodo. Un valor positivo indica mejora; necesita suficientes carreras comparables para mostrarse."]
];

const metricGlossary = new Map(
  metricGlossaryEntries.flatMap(([labels, explanation]) =>
    labels.map((label) => [label, explanation])
  )
);

const platformMetricGlossaries = {
  "assetto-corsa": new Map([
    ["inc", "Contador de incidentes guardado por Content Manager para el piloto y la carrera indicados. GridScope muestra el dato disponible sin atribuirlo únicamente a salidas de pista."],
    ["incidentes", "Contador de incidentes guardado por Content Manager. El historial no permite distinguir con certeza qué parte corresponde a cada tipo de incidente; la pantalla indica si el valor es personal o de toda la parrilla."],
    ["incidentes totales", "Suma del contador de incidentes guardado por Content Manager en todas las carreras válidas del conjunto mostrado."],
    ["incidentes medios", "Media de incidentes por piloto y carrera = incidentes acumulados de todos los participantes ÷ total de participaciones incluidas."],
    ["inc media", "Media de incidentes = incidentes acumulados ÷ carreras válidas del periodo seleccionado."],
    ["inc carrera", "Media de incidentes = incidentes acumulados ÷ carreras válidas del periodo seleccionado."],
    ["inc sem", "Media semanal de incidentes: primero se suman los incidentes de cada semana y después se promedian las semanas con carreras válidas."],
    ["temporada", "Agrupación histórica creada por GridScope a partir de las fechas de las carreras de Assetto Corsa."],
    ["temporadas", "Agrupaciones históricas creadas por GridScope a partir de las fechas de las carreras de Assetto Corsa."],
    ["serie", "Campeonato o grupo detectado mediante el servidor y los datos guardados por Content Manager."],
    ["series", "Campeonatos o grupos detectados mediante el servidor y los datos guardados por Content Manager."],
    ["series combinadas", "Cantidad de campeonatos o grupos distintos de Assetto Corsa reunidos en este Campeonato GridScope."],
    ["gridscore", gridScoreFormulaExplanation("assetto-corsa")],
    ["gridscore actual", gridRatingExplanation("assetto-corsa")],
    ["gridscore medio", `Promedio de los GridScore de los pilotos valorados en este periodo. Para cada piloto se usa su media ponderada reciente: ${gridRatingExplanation("assetto-corsa")}`],
    ["limpieza", cleanlinessFormulaExplanation("assetto-corsa")],
    ["limpieza actual", cleanlinessRatingExplanation("assetto-corsa")],
  ]),
  iracing: new Map([
    ["gridscore", gridScoreFormulaExplanation("iracing")],
    ["gridscore medio", `Promedio del GridScore de los pilotos valorados en este periodo. Para cada piloto se usa su media ponderada reciente: ${gridRatingExplanation("iracing")}`],
    ["limpieza", cleanlinessFormulaExplanation("iracing")],
  ])
};

function normalizeMetricLabel(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[↑↓↕±%./→·]/g, " ")
    .replace(/\b\d+(?:[.,]\d+)?\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function findMetricExplanation(label) {
  const normalized = normalizeMetricLabel(label);
  const platform = appState?.settings?.platform || appState?.league?.platform || "iracing";
  const platformGlossary = platformMetricGlossaries[platform];
  if (platformGlossary?.has(normalized)) return platformGlossary.get(normalized);
  if (metricGlossary.has(normalized)) return metricGlossary.get(normalized);
  const singular = normalized.endsWith("s") ? normalized.slice(0, -1) : normalized;
  return platformGlossary?.get(singular) || metricGlossary.get(singular) || null;
}

function createMetricHelpButton(label, explanation, automatic = false) {
  const button = document.createElement("button");
  button.className = "metric-help";
  button.type = "button";
  button.dataset.tooltip = explanation;
  if (automatic) {
    button.dataset.autoMetricHelp = "true";
    button.dataset.metricLabel = label;
  }
  button.setAttribute("aria-label", `Explicación de ${label}`);
  button.setAttribute("aria-expanded", "false");
  button.textContent = "?";
  return button;
}

function decorateMetricHelp(root = document) {
  const selector = "small, th, dt, .ranking-label";
  const candidates = [
    ...(root.matches?.(selector) ? [root] : []),
    ...(root.querySelectorAll?.(selector) || [])
  ];
  candidates.forEach((element) => {
    if (element.closest(".app-tooltip") || element.querySelector(".metric-help")) return;
    if (element.matches("small") && element.closest("td, .assetto-score-stack, .repeat-rating")) return;
    const label = element.textContent.trim();
    const explanation = findMetricExplanation(label);
    if (explanation) element.append(createMetricHelpButton(label, explanation, true));
  });
}

function refreshMetricHelp(root = document) {
  root.querySelectorAll?.('.metric-help[data-auto-metric-help="true"]').forEach((button) => button.remove());
  decorateMetricHelp(root);
}

const appTooltip = document.createElement("div");
appTooltip.className = "app-tooltip";
appTooltip.id = "appMetricTooltip";
appTooltip.setAttribute("role", "tooltip");
const metricTooltipSupportsPopover = typeof appTooltip.showPopover === "function";
if (metricTooltipSupportsPopover) {
  appTooltip.setAttribute("popover", "manual");
} else {
  appTooltip.hidden = true;
}
document.body.append(appTooltip);
let activeMetricHelp = null;

function positionMetricTooltip(button) {
  const buttonRect = button.getBoundingClientRect();
  const tooltipRect = appTooltip.getBoundingClientRect();
  const margin = 10;
  let left = buttonRect.left + buttonRect.width / 2 - tooltipRect.width / 2;
  left = Math.max(8, Math.min(left, window.innerWidth - tooltipRect.width - 8));
  let top = buttonRect.top - tooltipRect.height - margin;
  const below = top < 8;
  if (below) top = buttonRect.bottom + margin;
  appTooltip.classList.toggle("below", below);
  appTooltip.style.left = `${left}px`;
  appTooltip.style.top = `${top}px`;
}

function showMetricTooltip(button) {
  if (button?.dataset.autoMetricHelp === "true") {
    button.dataset.tooltip = findMetricExplanation(button.dataset.metricLabel) || button.dataset.tooltip;
  }
  if (!button?.dataset.tooltip) return;
  if (activeMetricHelp && activeMetricHelp !== button) {
    activeMetricHelp.setAttribute("aria-expanded", "false");
    activeMetricHelp.removeAttribute("aria-describedby");
  }
  activeMetricHelp = button;
  button.setAttribute("aria-expanded", "true");
  button.setAttribute("aria-describedby", appTooltip.id);
  appTooltip.textContent = button.dataset.tooltip;
  if (metricTooltipSupportsPopover) {
    if (!appTooltip.matches(":popover-open")) appTooltip.showPopover();
  } else {
    const dialog = button.closest("dialog");
    const tooltipHost = dialog?.open ? dialog : document.body;
    if (appTooltip.parentElement !== tooltipHost) tooltipHost.append(appTooltip);
    appTooltip.hidden = false;
  }
  appTooltip.classList.add("visible");
  requestAnimationFrame(() => positionMetricTooltip(button));
}

function hideMetricTooltip(button = activeMetricHelp) {
  if (button && button !== activeMetricHelp) return;
  activeMetricHelp?.setAttribute("aria-expanded", "false");
  activeMetricHelp?.removeAttribute("aria-describedby");
  activeMetricHelp = null;
  appTooltip.classList.remove("visible");
  if (metricTooltipSupportsPopover) {
    if (appTooltip.matches(":popover-open")) appTooltip.hidePopover();
  } else {
    appTooltip.hidden = true;
  }
}

decorateMetricHelp();
new MutationObserver((mutations) => {
  if (activeMetricHelp && !activeMetricHelp.isConnected) hideMetricTooltip();
  mutations.forEach((mutation) => {
    mutation.addedNodes.forEach((node) => {
      if (node.nodeType === Node.ELEMENT_NODE) decorateMetricHelp(node);
    });
  });
}).observe(document.body, { childList: true, subtree: true });

document.addEventListener("pointerover", (event) => {
  const button = event.target.closest?.(".metric-help");
  if (button) showMetricTooltip(button);
});
document.addEventListener("pointerout", (event) => {
  const button = event.target.closest?.(".metric-help");
  if (button && !button.contains(event.relatedTarget)) hideMetricTooltip(button);
});
document.addEventListener("focusin", (event) => {
  const button = event.target.closest?.(".metric-help");
  if (button) showMetricTooltip(button);
});
document.addEventListener("focusout", (event) => {
  const button = event.target.closest?.(".metric-help");
  if (button) hideMetricTooltip(button);
});
document.addEventListener("click", (event) => {
  const button = event.target.closest?.(".metric-help");
  if (!button) {
    hideMetricTooltip();
    return;
  }
  event.preventDefault();
  event.stopPropagation();
  showMetricTooltip(button);
}, true);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && activeMetricHelp) hideMetricTooltip();
});
window.addEventListener("resize", () => activeMetricHelp && positionMetricTooltip(activeMetricHelp));
window.addEventListener("scroll", () => activeMetricHelp && positionMetricTooltip(activeMetricHelp), true);

function requiredWeeks() {
  const completed = appState.league.weeksCompleted || 0;
  const percentage = appState.settings.minimumParticipation || 50;
  return Math.max(1, Math.ceil((completed * percentage) / 100));
}

function rankDrivers(mode = "weekly") {
  const key = mode === "weekly" ? "weekly" : "races";
  const minimum = requiredWeeks();
  const eligible = appState.drivers
    .filter((driver) => driver.weeks >= minimum)
    .sort((a, b) => a[key] - b[key] || a.incidents - b.incidents);
  const provisional = appState.drivers
    .filter((driver) => driver.weeks < minimum)
    .sort((a, b) => {
      if (!a.weeks && b.weeks) return 1;
      if (a.weeks && !b.weeks) return -1;
      return a[key] - b[key];
    });
  return [...eligible, ...provisional];
}

function movementMarkup(value) {
  if (value > 0) return `<span class="movement up" title="Sube ${value}">↑${value}</span>`;
  if (value < 0) return `<span class="movement down" title="Baja ${Math.abs(value)}">↓${Math.abs(value)}</span>`;
  return '<span class="movement">—</span>';
}

function renderRanking(mode = appState.settings.rankingMode || "weekly") {
  rankingLabel.textContent = mode === "weekly" ? "Media semanal" : "Media / carrera";
  const minimum = requiredWeeks();
  let officialPosition = 0;

  rankingBody.innerHTML = rankDrivers(mode).map((driver) => {
    const provisional = driver.weeks < minimum;
    if (!provisional) officialPosition += 1;
    const metric = mode === "weekly" ? driver.weekly : driver.races;
    const hasResults = driver.racesCount > 0;
    return `
      <tr class="${provisional ? "provisional-row" : ""}">
        <td><span class="position ${officialPosition <= 3 && !provisional ? "medal" : ""}">${provisional ? "—" : officialPosition}</span></td>
        <td>
          <div class="driver-cell">
            <i class="avatar ${driver.color}">${driver.initials}</i>
            <span><strong>${driver.name}</strong><small>ID ${driver.id}</small></span>
            ${provisional ? '<em class="provisional">Provisional</em>' : ""}
          </div>
        </td>
        <td class="numeric metric-strong">${hasResults ? formatDecimal(metric) : "—"}</td>
        <td class="numeric">${hasResults ? `${formatDecimal(driver.incidents)}x` : "—"}</td>
        <td class="numeric">${driver.weeks} / ${appState.league.weeksCompleted}</td>
        <td class="numeric">${driver.racesCount}</td>
        <td class="numeric">${driver.wins}</td>
        <td class="numeric">${driver.sof ? formatInteger(driver.sof) : "—"}</td>
        <td>${movementMarkup(driver.move)}</td>
      </tr>`;
  }).join("");

  if (!appState.drivers.length) {
    rankingBody.innerHTML = '<tr><td colspan="9">Todavía no hay pilotos en esta liga.</td></tr>';
  }
}

function renderRounds() {
  const roundList = document.querySelector("#roundList");
  roundList.innerHTML = appState.rounds.slice().reverse().map((round) => `
    <article class="round-card" data-session-week="${round.week}" tabindex="0" role="button" aria-label="Abrir detalle de la semana ${round.week}">
      <div class="round-week">S${String(round.week).padStart(2, "0")}</div>
      <img class="track-thumbnail" src="${trackImageUrl(round.track, round.layout)}" alt="" loading="lazy">
      <div class="round-track"><strong>${round.track}</strong><small>${round.layout}</small></div>
      <div class="round-stat"><small>Carreras</small><strong>${round.races}</strong></div>
      <div class="round-stat"><small>Pos. media</small><strong>${formatDecimal(round.average)}</strong></div>
      <div class="round-stat"><small>Incidentes</small><strong>${Number(round.incidents).toFixed(1).replace(".", ",")}x</strong></div>
      <div class="round-stat"><small>SoF destacado</small><strong>${formatInteger(round.sof)}</strong></div>
      <button class="icon-button" type="button" aria-label="Ver jornada ${round.week}"><svg viewBox="0 0 20 20"><path d="m7 4 6 6-6 6" /></svg></button>
    </article>
  `).join("");
}

function positionChangeMarkup(value) {
  if (value > 0) return `<span class="result-change gained">+${value}</span>`;
  if (value < 0) return `<span class="result-change lost">${value}</span>`;
  return '<span class="result-change">0</span>';
}

function renderRaceExplorer() {
  const container = document.querySelector("#raceExplorer");
  if (!raceAnalysis.races.length) {
    container.innerHTML = `
      <article class="empty-archive">
        <div><svg viewBox="0 0 24 24"><path d="M4 19V5m0 2h12l-2 3 2 3H4" /></svg></div>
        <h3>Todavía no hay carreras</h3>
        <p>Importa archivos eventresult para crear el historial detallado.</p>
      </article>`;
    return;
  }
  container.innerHTML = raceAnalysis.races.map((race) => {
    const owner = race.ownerResult;
    const split = race.splitNumber
      ? `Split ${race.splitNumber}${race.splitTotal ? ` / ${race.splitTotal}` : ""}`
      : "Split no indicado";
    return `
      <button class="race-card" type="button" data-race-id="${race.id}">
        <div class="race-card-week"><small>SEM.</small><strong>${String(race.week).padStart(2, "0")}</strong></div>
        <img class="track-thumbnail race-track-thumbnail" src="${trackImageUrl(race.track, race.layout)}" alt="" loading="lazy">
        <div class="race-card-main">
          <strong>${escapeHtml(race.track)}</strong>
          <span>${escapeHtml(race.layout || "Trazado principal")} · ${formatRaceDate(race.startTime)}</span>
          <small>${split} · SoF ${formatInteger(race.strengthOfField)} · ${race.fieldSize} pilotos</small>
        </div>
        <div class="race-card-result">
          <small>Tu resultado</small>
          <strong>${owner ? `P${owner.finishPosition}` : "—"}</strong>
          <span>${owner ? `${positionChangeMarkup(owner.positionChange)} · ${owner.incidents}x` : "No participaste"}</span>
        </div>
        <div class="race-card-winner"><small>Ganador</small><strong>${escapeHtml(race.winnerName || "—")}</strong></div>
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m7 4 6 6-6 6" /></svg>
      </button>`;
  }).join("");
}

function renderRivals() {
  const summary = rivalAnalysis.summary || {};
  const owner = rivalAnalysis.owner;
  document.querySelector("#rivalIntro").textContent = owner
    ? `${owner.name}: rendimiento frente a los pilotos con los que has compartido carrera.`
    : "Configura tu ID de iRacing para activar las comparativas.";
  document.querySelector("#comparisonSummary").innerHTML = `
    <article class="comparison-stat"><small>Carreras analizadas</small><strong>${summary.races || 0}</strong><span>con tu piloto presente</span></article>
    <article class="comparison-stat"><small>Rivales distintos</small><strong>${summary.uniqueRivals || 0}</strong><span>pilotos coincidentes</span></article>
    <article class="comparison-stat"><small>Rivales recurrentes</small><strong>${summary.recurrentRivals || 0}</strong><span>coincidiste en más de una carrera</span></article>
  `;
  const progressBody = document.querySelector("#raceProgressBody");
  const ownerRaces = raceAnalysis.races.filter((race) => race.ownerResult);
  progressBody.innerHTML = ownerRaces.length
    ? ownerRaces.slice().reverse().map((race) => `
      <tr>
        <td><strong>${escapeHtml(race.track)}</strong><small class="table-subline">S${race.week} · ${formatRaceDate(race.startTime)}</small></td>
        <td class="numeric">${formatInteger(race.strengthOfField)}</td>
        <td class="numeric">${race.splitNumber || "—"}${race.splitTotal ? ` / ${race.splitTotal}` : ""}</td>
        <td class="numeric">${race.ownerResult.startPosition ?? "—"}</td>
        <td class="numeric metric-strong">P${race.ownerResult.finishPosition}</td>
        <td class="numeric">${positionChangeMarkup(race.ownerResult.positionChange)}</td>
        <td class="numeric">${race.ownerResult.incidents}x</td>
        <td class="numeric">${formatSigned(race.ownerResult.iratingChange)}</td>
        <td class="numeric">${formatSigned(race.ownerResult.safetyRatingChange)}</td>
      </tr>`).join("")
    : '<tr><td colspan="9">Tu ID no aparece en las carreras de esta serie.</td></tr>';
  const body = document.querySelector("#rivalsBody");
  if (!rivalAnalysis.rivals.length) {
    body.innerHTML = '<tr><td colspan="9">No hay coincidencias para el piloto de referencia en esta serie.</td></tr>';
    return;
  }
  body.innerHTML = rivalAnalysis.rivals.map((rival) => `
    <tr class="rival-row" data-rival-id="${rival.iracingId}" tabindex="0">
      <td>
        <div class="driver-cell">
          <i class="avatar ${rival.color}">${escapeHtml(rival.initials)}</i>
          <span><strong>${escapeHtml(rival.name)}</strong><small>${escapeHtml(driverIdentityText(rival.iracingId))}</small></span>
        </div>
      </td>
      <td class="numeric">${rival.meetings}</td>
      <td class="numeric comparison-win">${rival.ownerAhead}</td>
      <td class="numeric comparison-loss">${rival.rivalAhead}</td>
      <td class="numeric metric-strong">${formatDecimal(rival.winRate)}%</td>
      <td class="numeric">${formatSigned(rival.averagePositionAdvantage, " pos.")}</td>
      <td class="numeric">${formatDecimal(rival.averageOwnerIncidents)}x / ${formatDecimal(rival.averageRivalIncidents)}x</td>
      <td class="numeric">${rival.trend > 0
        ? `<span class="trend positive">↑ ${formatDecimal(rival.trend)}%</span>`
        : rival.trend < 0
          ? `<span class="trend negative">↓ ${formatDecimal(Math.abs(rival.trend))}%</span>`
          : '<span class="trend neutral">Estable</span>'}</td>
      <td><button class="icon-button small" type="button" aria-label="Ver coincidencias con ${escapeHtml(rival.name)}"><svg viewBox="0 0 20 20"><path d="m7 4 6 6-6 6" /></svg></button></td>
    </tr>
  `).join("");
}

function openRivalDetail(iracingId) {
  const rival = rivalAnalysis.rivals.find((item) => item.iracingId === String(iracingId));
  if (!rival) return;
  rivalDetailDialog.dataset.rivalId = rival.iracingId;
  document.querySelector("#rivalDetailTitle").textContent = rival.name;
  document.querySelector("#rivalDetailContent").innerHTML = `
    <div class="rival-headline">
      <article><small>Coincidencias</small><strong>${rival.meetings}</strong></article>
      <article><small>Tú delante</small><strong class="comparison-win">${rival.ownerAhead}</strong></article>
      <article><small>Rival delante</small><strong class="comparison-loss">${rival.rivalAhead}</strong></article>
      <article><small>% por delante</small><strong>${formatDecimal(rival.winRate)}%</strong></article>
      <article><small>Ventaja media</small><strong>${formatSigned(rival.averagePositionAdvantage, " pos.")}</strong></article>
      <article><small>Incidentes</small><strong>${formatDecimal(rival.averageOwnerIncidents)}x / ${formatDecimal(rival.averageRivalIncidents)}x</strong></article>
    </div>
    <div class="table-wrap rival-meetings-wrap">
      <table class="rival-meetings-table">
        <thead>
          <tr>
            <th>Carrera</th><th class="numeric">SoF</th><th class="numeric">Split</th>
            <th class="numeric">Tu salida</th><th class="numeric">Tu meta</th>
            <th class="numeric">Salida rival</th><th class="numeric">Meta rival</th>
            <th>Resultado</th><th class="numeric">Incidentes</th><th></th>
          </tr>
        </thead>
        <tbody>
          ${rival.meetingDetails.map((meeting) => {
            const ownerWon = meeting.ownerPosition < meeting.rivalPosition;
            const rivalWon = meeting.ownerPosition > meeting.rivalPosition;
            return `
              <tr data-shared-race-id="${meeting.eventId}" tabindex="0" role="button" aria-label="Abrir carrera compartida en ${escapeHtml(meeting.track)}">
                <td><strong>${escapeHtml(meeting.track)}</strong><small class="table-subline">S${meeting.week} · ${escapeHtml(meeting.layout || "")} · ${formatRaceDate(meeting.startTime)}</small></td>
                <td class="numeric">${formatInteger(meeting.strengthOfField)}</td>
                <td class="numeric">${meeting.splitNumber || "—"}${meeting.splitTotal ? ` / ${meeting.splitTotal}` : ""}</td>
                <td class="numeric">${meeting.ownerStartPosition ?? "—"}</td>
                <td class="numeric metric-strong">P${meeting.ownerPosition}</td>
                <td class="numeric">${meeting.rivalStartPosition ?? "—"}</td>
                <td class="numeric">P${meeting.rivalPosition}</td>
                <td><span class="head-to-head-result ${ownerWon ? "won" : rivalWon ? "lost" : "tied"}">${ownerWon ? "Terminaste delante" : rivalWon ? "Terminó delante" : "Empate"}</span></td>
                <td class="numeric">${meeting.ownerIncidents}x / ${meeting.rivalIncidents}x</td>
                <td><button class="text-button open-shared-race" type="button" data-shared-race-id="${meeting.eventId}">Abrir carrera</button></td>
              </tr>`;
          }).join("")}
        </tbody>
      </table>
    </div>`;
  rivalDetailDialog.showModal();
}

function miniLeaguePeriodsFor(scope) {
  if (String(scope).startsWith("custom:")) {
    const championshipId = Number(String(scope).split(":")[1]);
    const championship = (miniLeagueAnalysis.customChampionships || []).find(
      (item) => Number(item.id) === championshipId
    );
    return championship?.league ? [championship.league] : [];
  }
  const periods = miniLeagueAnalysis.periods?.[scope];
  if (Array.isArray(periods) && periods.length) {
    return scope === "monthly"
      ? periods.filter((period) => Number(period.summary?.races || 0) > 0)
      : periods;
  }
  const legacyLeague = miniLeagueAnalysis.leagues?.[scope];
  if (
    legacyLeague
    && (
      scope !== "monthly"
      || Number(legacyLeague.summary?.races || 0) > 0
    )
  ) {
    return [legacyLeague];
  }
  return [];
}

function selectedMiniLeague(scope = activeMiniLeagueScope) {
  const periods = miniLeaguePeriodsFor(scope);
  if (!periods.length) return null;
  const selectedKey = activeMiniLeaguePeriods[scope];
  const selected = periods.find((period) => period.periodKey === selectedKey) || periods[0];
  activeMiniLeaguePeriods[scope] = selected.periodKey || scope;
  return selected;
}

function miniLeagueClassification(league) {
  const classified = league.participants
    .filter((participant) => participant.races >= miniLeagueMinimumRaces)
    .slice()
    .sort((participantA, participantB) =>
      participantB.score - participantA.score ||
      participantB.races - participantA.races ||
      participantA.averageIncidents - participantB.averageIncidents ||
      participantA.name.localeCompare(participantB.name, "es", { sensitivity: "base" })
    );
  return {
    classified,
    positions: new Map(
      classified.map((participant, index) => [String(participant.iracingId), index + 1])
    )
  };
}

function renderMiniPeriodComparison(league) {
  const container = document.querySelector("#miniLeaguePeriodComparison");
  const isAssetto = (appState.settings.platform || appState.league.platform) === "assetto-corsa";
  const periods = miniLeaguePeriodsFor(activeMiniLeagueScope);
  const currentIndex = periods.indexOf(league);
  const previous = currentIndex >= 0 ? periods[currentIndex + 1] : null;
  if (!previous || activeMiniLeagueScope === "eternal" || activeMiniLeagueScope.startsWith("custom:")) {
    container.hidden = true;
    container.innerHTML = "";
    return;
  }
  const current = league.summary || {};
  const prior = previous.summary || {};
  const averageGridScore = (period) => {
    const rated = (period.participants || []).filter(
      (participant) => participant.gridRating?.gridScore != null
    );
    return rated.length
      ? rated.reduce((total, participant) => total + participant.gridRating.gridScore, 0) / rated.length
      : 0;
  };
  const comparisonMetric = (
    label,
    value,
    oldValue,
    { decimals = 0, suffix = "", unit = "" } = {}
  ) => {
    const currentValue = Number(value || 0);
    const previousValue = Number(oldValue || 0);
    const difference = currentValue - previousValue;
    const format = (number) => number.toLocaleString("es-ES", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    });
    const unitLabel = Array.isArray(unit)
      ? unit[Math.abs(difference) === 1 ? 0 : 1]
      : unit;
    const change = Math.abs(difference) < 10 ** -(decimals + 1)
      ? "Sin cambios"
      : `${format(Math.abs(difference))}${suffix}${unitLabel ? ` ${unitLabel}` : ""} ${difference > 0 ? "más" : "menos"}`;
    return `
      <span>
        <small>${escapeHtml(label)} · seleccionado / anterior</small>
        <strong>${format(currentValue)}${suffix} <i>frente a</i> ${format(previousValue)}${suffix}</strong>
        <em>${change}</em>
      </span>`;
  };
  container.hidden = false;
  container.innerHTML = `
    <div>
      <small>Comparación con el periodo puntuable anterior</small>
      <strong>${escapeHtml(league.label)} frente a ${escapeHtml(previous.label)}</strong>
      <em>Primero aparece el periodo seleccionado y después el anterior.</em>
    </div>
    ${comparisonMetric("Carreras", current.races, prior.races, { unit: ["carrera", "carreras"] })}
    ${comparisonMetric("Participantes", current.participants, prior.participants, { unit: ["participante", "participantes"] })}
    ${comparisonMetric("Recurrentes", current.recurrentRivals, prior.recurrentRivals, { unit: ["rival", "rivales"] })}
    ${isAssetto
      ? comparisonMetric("GridScore medio", averageGridScore(league), averageGridScore(previous), { decimals: 2, unit: ["punto", "puntos"] })
      : comparisonMetric("SoF medio", current.averageSof, prior.averageSof, { unit: ["punto", "puntos"] })}
    ${comparisonMetric(isAssetto ? "Incidentes medios" : "Inc. media", current.averageIncidents, prior.averageIncidents, { decimals: 2, suffix: "x" })}
  `;
}

function renderMiniLeagues() {
  const isAssetto = (appState.settings.platform || appState.league.platform) === "assetto-corsa";
  const ratingSortButton = document.querySelector("#miniRatingSort");
  const safetySortButton = document.querySelector("#miniSafetySort");
  const incidentsSortButton = document.querySelector("#miniIncidentsSort");
  ratingSortButton.dataset.miniSort = isAssetto ? "gridScore" : "iratingEnd";
  ratingSortButton.innerHTML = `${isAssetto ? "GridScore" : "iRating"}<span class="sort-indicator">↕</span>`;
  safetySortButton.dataset.miniSort = isAssetto ? "cleanlinessScore" : "safetyRatingEnd";
  safetySortButton.innerHTML = `${isAssetto ? "Limpieza" : "SR"}<span class="sort-indicator">↕</span>`;
  incidentsSortButton.innerHTML = `Inc./carrera<span class="sort-indicator">↕</span>`;
  document.querySelector("#miniGridScoreColumn").hidden = isAssetto;
  document.querySelector("#miniCleanlinessColumn").hidden = isAssetto;
  if (isAssetto && miniLeagueSort.key === "iratingEnd") miniLeagueSort.key = "gridScore";
  if (isAssetto && miniLeagueSort.key === "safetyRatingEnd") miniLeagueSort.key = "cleanlinessScore";
  if (!isAssetto && miniLeagueSort.key === "gridScore") miniLeagueSort.key = "iratingEnd";
  if (!isAssetto && miniLeagueSort.key === "cleanlinessScore") miniLeagueSort.key = "safetyRatingEnd";
  const scopes = [
    ["yearly", "Anual", "Clasificación por año"],
    ["season", "Temporada", "Clasificación por season"],
    ["monthly", "Mensual", "Clasificación por mes"],
    ["eternal", "Eterna", "Todo el historial"]
  ];
  const customChampionships = miniLeagueAnalysis.customChampionships || [];
  const customSection = document.querySelector("#customChampionshipsSection");
  const customList = document.querySelector("#customChampionshipList");
  customSection.hidden = !customChampionships.length;
  customList.innerHTML = customChampionships.map((championship) => {
    const league = championship.league || { summary: {} };
    const details = [
      championship.seriesNames?.length
        ? `${championship.seriesNames.length} serie${championship.seriesNames.length === 1 ? "" : "s"}`
        : "Todas las series",
      championship.startDate || championship.endDate
        ? `${championship.startDate || "Inicio"} → ${championship.endDate || "Hoy"}`
        : "Todo el historial",
      championship.participantMode === "selected"
        ? `${championship.driverIds.length}${championship.includeOwner ? " + tú" : ""} seleccionados`
        : championship.participantMode === "all"
          ? "Todos los coincidentes"
          : "Rivales recurrentes"
    ];
    return `
      <button class="custom-championship-card ${activeMiniLeagueScope === `custom:${championship.id}` ? "active" : ""}" type="button" data-custom-championship="${championship.id}">
        <span><strong>${escapeHtml(championship.name)}</strong><small>${details.map(escapeHtml).join(" · ")}</small></span>
        <b>${league.summary?.participants || 0}</b>
      </button>`;
  }).join("");
  if (!miniLeaguePeriodsFor(activeMiniLeagueScope).length) {
    activeCustomChampionshipId = null;
    activeMiniLeagueScope = miniLeaguePeriodsFor("eternal").length
      ? "eternal"
      : scopes.find(([scope]) => miniLeaguePeriodsFor(scope).length)?.[0] || "eternal";
  }
  document.querySelector("#miniLeagueTabs").innerHTML = scopes.map(([scope, title, description]) => {
    const league = selectedMiniLeague(scope) || { label: "Sin datos", summary: {} };
    return `
      <button class="mini-league-tab ${scope === activeMiniLeagueScope ? "active" : ""}" type="button" data-mini-scope="${scope}">
        <span><small>${title}</small><strong>${escapeHtml(league.label)}</strong><em>${description}</em></span>
        <b>${league.summary?.participants || 0}</b>
      </button>`;
  }).join("");
  const league = selectedMiniLeague();
  if (!league) return;
  const isCustom = activeMiniLeagueScope.startsWith("custom:");
  activeCustomChampionshipId = isCustom
    ? Number(activeMiniLeagueScope.split(":")[1])
    : null;
  document.querySelector("#customChampionshipToolbar").hidden = !isCustom;
  if (isCustom) miniLeagueMinimumRaces = Number(league.minimumRaces || 2);
  const periods = miniLeaguePeriodsFor(activeMiniLeagueScope);
  const periodToolbar = document.querySelector("#miniLeaguePeriodToolbar");
  const periodSelect = document.querySelector("#miniLeaguePeriodSelect");
  periodToolbar.hidden = isCustom || activeMiniLeagueScope === "eternal" || periods.length < 2;
  periodSelect.innerHTML = periods.map((period) => {
    const raceCount = Number(period.summary?.races || 0);
    const raceLabel = `${raceCount} ${raceCount === 1 ? "carrera" : "carreras"}`;
    return `<option value="${escapeHtml(period.periodKey || activeMiniLeagueScope)}" ${(period.periodKey || activeMiniLeagueScope) === activeMiniLeaguePeriods[activeMiniLeagueScope] ? "selected" : ""}>${escapeHtml(period.label)} · ${raceLabel}</option>`;
  }).join("");
  const summary = league.summary || {};
  const classification = miniLeagueClassification(league);
  const ownerParticipant = league.participants.find((participant) => participant.isOwner);
  const ownerOfficialPosition = ownerParticipant
    ? classification.positions.get(String(ownerParticipant.iracingId))
    : null;
  const leader = classification.classified[0] || null;
  const ratedParticipants = league.participants.filter(
    (participant) => participant.gridRating?.gridScore != null
  );
  const averageGridScore = ratedParticipants.length
    ? ratedParticipants.reduce(
        (total, participant) => total + participant.gridRating.gridScore,
        0
      ) / ratedParticipants.length
    : null;
  document.querySelector("#miniLeagueMinimumRaces").value = miniLeagueMinimumRaces;
  document.querySelector("#miniLeagueMinimumRaces").disabled = isCustom;
  document.querySelector("#miniLeagueMinimumHelp").textContent =
    `${classification.classified.length} de ${league.participants.length} pilotos clasificados; el resto sigue visible como provisional.`;
  const weightingExplanation = league.rankingMode === "weekly"
    ? "Primero se calcula la media de cada semana y después la media general, de modo que todas las semanas pesan lo mismo."
    : "Cada carrera puntuable pesa lo mismo en la media general.";
  document.querySelector("#miniLeagueCalculationHelp").textContent = `${isCustom ? "Este campeonato utiliza únicamente las series, fechas y pilotos configurados. " : ""}Una carrera puntúa cuando coinciden al menos dos miembros. El mejor clasificado entre ellos recibe 100 puntos, el último 0 y el resto una cantidad proporcional. ${weightingExplanation} Cada pareja de miembros genera además un duelo.${isAssetto ? " Los datos proceden de los JSON de Content Manager." : " iRating, SR y SoF conservan sus valores oficiales."}`;
  document.querySelector("#miniLeaguePeriod").textContent = league.label;
  document.querySelector("#miniLeagueRankingTitle").textContent =
    isCustom ? "Clasificación del campeonato" : "Clasificación de recurrentes";
  document.querySelector("#miniLeagueSummary").innerHTML = `
    <article><small>Carreras puntuables</small><strong>${summary.races || 0}</strong><span>con miembros coincidentes</span></article>
    <article><small>Participantes</small><strong>${summary.participants || 0}</strong><span>${classification.classified.length} cumplen el mínimo</span></article>
    <article><small>${isCustom ? "Rivales incluidos" : "Rivales recurrentes"}</small><strong>${summary.recurrentRivals || 0}</strong><span>${isCustom ? "según la configuración" : "mínimo dos coincidencias"}</span></article>
    <article><small>Series combinadas</small><strong>${summary.series || 0}</strong><span>${isAssetto ? "campeonatos o servidores distintos" : "campeonatos oficiales distintos"}</span></article>
    <article><small>Circuitos</small><strong>${summary.tracks || 0}</strong><span>configuraciones diferentes</span></article>
    <article><small>Duelos disputados</small><strong>${formatInteger(summary.duels || 0)}</strong><span>comparaciones entre miembros</span></article>
    <article><small>Miembros por carrera</small><strong>${formatDecimal(summary.averageMembers || 0)}</strong><span>participación media puntuable</span></article>
    <article><small>${isAssetto ? "GridScore medio" : "SoF medio"}</small><strong>${isAssetto ? averageGridScore == null ? "—" : formatDecimal(averageGridScore) : summary.averageSof ? formatInteger(summary.averageSof) : "—"}</strong><span>${isAssetto ? "media de los miembros valorados" : "nivel de las parrillas"}</span></article>
    <article><small>Incidentes medios</small><strong>${formatDecimal(summary.averageIncidents || 0)}x</strong><span>por miembro y carrera</span></article>
    <article><small>Referencia</small><strong>${ownerOfficialPosition ? `P${ownerOfficialPosition}` : "Provisional"}</strong><span>${leader ? `líder: ${escapeHtml(leader.name)}` : "sin pilotos clasificados"}</span></article>
  `;
  renderMiniPeriodComparison(league);
  const body = document.querySelector("#miniLeagueBody");
  const sortValue = (participant, key) => {
    const values = {
      position: participant.position,
      name: participant.name,
      score: participant.score,
      races: participant.races,
      duels: participant.duels,
      duelWinRate: participant.duelWinRate,
      seriesCount: participant.seriesCount,
      averageIncidents: participant.averageIncidents,
      iratingEnd: participant.iratingEnd,
      safetyRatingEnd: participant.safetyRatingEnd,
      gridScore: participant.gridRating?.gridScore,
      cleanlinessScore: participant.gridRating?.cleanlinessScore,
      headToHead: participant.ownerAhead + participant.rivalAhead
    };
    return values[key];
  };
  const sortedParticipants = league.participants.slice().sort((participantA, participantB) => {
    if (participantA.isOwner !== participantB.isOwner) {
      return participantA.isOwner ? -1 : 1;
    }
    const classifiedA = classification.positions.has(String(participantA.iracingId));
    const classifiedB = classification.positions.has(String(participantB.iracingId));
    if (classifiedA !== classifiedB) return classifiedA ? -1 : 1;
    const valueA = sortValue(participantA, miniLeagueSort.key);
    const valueB = sortValue(participantB, miniLeagueSort.key);
    if (valueA == null && valueB == null) return participantA.position - participantB.position;
    if (valueA == null) return 1;
    if (valueB == null) return -1;
    const comparison = typeof valueA === "string"
      ? valueA.localeCompare(valueB, "es", { sensitivity: "base" })
      : valueA - valueB;
    return (miniLeagueSort.direction === "asc" ? comparison : -comparison) ||
      participantA.position - participantB.position;
  });
  document.querySelectorAll("[data-mini-sort]").forEach((button) => {
    const active = button.dataset.miniSort === miniLeagueSort.key;
    button.classList.toggle("active", active);
    button.querySelector(".sort-indicator").textContent = active
      ? miniLeagueSort.direction === "asc" ? "↑" : "↓"
      : "↕";
  });
  body.innerHTML = league.participants.length
    ? sortedParticipants.map((participant) => {
      const officialPosition = classification.positions.get(String(participant.iracingId));
      const classified = officialPosition != null;
      const displayedPosition = participant.isOwner
        ? officialPosition ?? participant.position
        : officialPosition;
      return `
      <tr class="${classified ? "" : "mini-provisional"} ${participant.isOwner ? "mini-owner-row" : ""}" data-mini-driver-id="${participant.iracingId}" tabindex="0">
        <td><span class="position ${classified && officialPosition <= 3 ? "medal" : ""}">${displayedPosition ?? "—"}</span></td>
        <td><div class="driver-cell"><i class="avatar ${participant.color}">${escapeHtml(participant.initials)}</i><span><strong>${escapeHtml(participant.name)}${classified ? "" : ' <em class="mini-provisional-badge">Provisional</em>'}</strong><small>${participant.isOwner ? "Piloto de referencia" : escapeHtml(driverIdentityText(participant.iracingId))} · ${participant.races}/${miniLeagueMinimumRaces} carreras mínimas</small></span></div></td>
        <td class="numeric mini-score">${formatDecimal(participant.score)}</td>
        <td class="numeric">${participant.races}</td>
        <td class="numeric"><span class="comparison-win">${participant.wins}</span> / <span class="comparison-loss">${participant.losses}</span></td>
        <td class="numeric">${formatDecimal(participant.duelWinRate)}%</td>
        <td class="numeric">${participant.seriesCount}</td>
        <td class="numeric">${formatDecimal(participant.averageIncidents)}x</td>
        <td class="numeric">${isAssetto ? participant.gridRating == null ? "—" : `${formatDecimal(participant.gridRating.gridScore)} <small>Variación ${formatSigned(participant.gridRating.gridScoreChange)}</small>` : participant.iratingEnd == null ? "—" : `${formatInteger(participant.iratingEnd)} <small>${formatSigned(participant.iratingChange)}</small>`}</td>
        <td class="numeric">${isAssetto ? participant.gridRating == null ? "—" : `${formatDecimal(participant.gridRating.cleanlinessScore)} <small>Confianza ${participant.gridRating.confidence}</small>` : participant.safetyRatingEnd == null ? "—" : `${formatDecimal(participant.safetyRatingEnd)} <small>${formatSigned(participant.safetyRatingChange)}</small>`}</td>
        ${isAssetto ? "" : `<td class="numeric">${participant.gridRating == null ? "—" : `${formatDecimal(participant.gridRating.gridScore)} <small>GridScope</small>`}</td>
        <td class="numeric">${participant.gridRating == null ? "—" : `${formatDecimal(participant.gridRating.cleanlinessScore)} <small>${participant.gridRating.confidence}</small>`}</td>`}
        <td class="numeric">${participant.isOwner ? "Referencia" : `${participant.ownerAhead}-${participant.rivalAhead}`}</td>
        <td><button class="icon-button small" type="button" aria-label="Ver campeonato de ${escapeHtml(participant.name)}"><svg viewBox="0 0 20 20"><path d="m7 4 6 6-6 6" /></svg></button></td>
      </tr>`;
    }).join("")
    : `<tr><td colspan="${isAssetto ? 12 : 14}">${isCustom ? "No hay carreras con al menos dos de los pilotos configurados." : "Todavía no hay suficientes coincidencias recurrentes en este periodo."}</td></tr>`;
  document.querySelector("#miniLeagueEvents").innerHTML = league.events.length
    ? league.events.map((race) => `
      <button type="button" data-mini-race-id="${race.eventId}">
        <span class="mini-event-date">${formatRaceDate(race.startTime)}</span>
        <span class="mini-event-main"><strong>${escapeHtml(race.track)}</strong><small>${escapeHtml(race.seriesName)} · ${escapeHtml(race.layout || "Trazado principal")}</small></span>
        <span><small>Miembros</small><strong>${race.participants}</strong></span>
        <span><small>${isAssetto ? "Parrilla" : "SoF"}</small><strong>${isAssetto ? formatInteger(race.fieldSize || race.participants) : formatInteger(race.strengthOfField)}</strong></span>
        <svg viewBox="0 0 20 20"><path d="m7 4 6 6-6 6" /></svg>
      </button>`).join("")
    : `<article class="empty-archive"><h3>Sin carreras puntuables</h3><p>${isCustom ? "Revisa las series, las fechas y los pilotos seleccionados." : "Se necesitan al menos dos coincidencias con un mismo rival."}</p></article>`;
  refreshMetricHelp(document.querySelector("#mini-leagues"));
}

function customChampionshipById(championshipId = activeCustomChampionshipId) {
  return (miniLeagueAnalysis.customChampionships || []).find(
    (championship) => Number(championship.id) === Number(championshipId)
  ) || null;
}

function renderChampionshipFormChoices(championship = null) {
  const selectedSeries = new Set(championship?.seriesNames || []);
  championshipSelectedDriverIds = new Set(
    (championship?.driverIds || []).map(String)
  );
  document.querySelector("#championshipSeriesList").innerHTML =
    (miniLeagueAnalysis.options?.series || []).map((seriesName) => `
      <label><input type="checkbox" name="championshipSeries" value="${escapeHtml(seriesName)}" ${selectedSeries.has(seriesName) ? "checked" : ""}><span title="${escapeHtml(seriesName)}">${escapeHtml(seriesName)}</span></label>
    `).join("") || '<p class="dialog-help">Todavía no hay series importadas en este simulador.</p>';
  updateChampionshipSeriesCount();
  renderChampionshipDriverChoices();
}

function updateChampionshipSeriesCount() {
  const allSeries = document.querySelectorAll('[name="championshipSeries"]');
  const selectedSeries = document.querySelectorAll('[name="championshipSeries"]:checked');
  const counter = document.querySelector("#championshipSeriesCount");
  if (!allSeries.length) {
    counter.textContent = "Sin series disponibles";
  } else if (!selectedSeries.length) {
    counter.textContent = `Todas por defecto · ${allSeries.length}`;
  } else if (selectedSeries.length === allSeries.length) {
    counter.textContent = `Todas seleccionadas · ${allSeries.length}`;
  } else {
    counter.textContent = `${selectedSeries.length} de ${allSeries.length}`;
  }
}

function renderChampionshipDriverChoices(query = "") {
  const normalizedQuery = query.trim().toLocaleLowerCase("es");
  const availableDrivers = miniLeagueAnalysis.options?.drivers || [];
  const matchingDrivers = availableDrivers.filter(
    (driver) =>
      championshipSelectedDriverIds.has(String(driver.iracingId))
      || !normalizedQuery
      || driver.name.toLocaleLowerCase("es").includes(normalizedQuery)
  );
  const visibleDrivers = [
    ...matchingDrivers.filter((driver) =>
      championshipSelectedDriverIds.has(String(driver.iracingId))
    ),
    ...matchingDrivers.filter((driver) =>
      !championshipSelectedDriverIds.has(String(driver.iracingId))
    ).slice(0, 250)
  ];
  document.querySelector("#championshipDriverList").innerHTML =
    visibleDrivers.map((driver) => `
      <label data-championship-driver-name="${escapeHtml(driver.name.toLocaleLowerCase("es"))}">
        <input type="checkbox" name="championshipDriver" value="${escapeHtml(driver.iracingId)}" ${championshipSelectedDriverIds.has(String(driver.iracingId)) ? "checked" : ""}>
        <span title="${escapeHtml(driver.name)}">${escapeHtml(driver.name)}${driver.isOwner ? " · Referencia" : ""}</span>
      </label>
    `).join("") || '<p class="dialog-help">No hay pilotos que coincidan con esta búsqueda.</p>';
  if (matchingDrivers.length > visibleDrivers.length) {
    document.querySelector("#championshipDriverList").insertAdjacentHTML(
      "beforeend",
      `<p class="driver-choice-limit">Mostrando los primeros 250 de ${formatInteger(matchingDrivers.length)}. Escribe parte del nombre para concretar.</p>`
    );
  }
}

function updateChampionshipDriverVisibility() {
  const selectedMode = document.querySelector("#championshipParticipantMode").value;
  document.querySelector("#championshipDriversSection").hidden = selectedMode !== "selected";
}

function openChampionshipEditor(championshipId = null) {
  const championship = championshipId == null
    ? null
    : customChampionshipById(championshipId);
  document.querySelector("#championshipForm").reset();
  document.querySelector("#championshipId").value = championship?.id || "";
  document.querySelector("#championshipDialogTitle").textContent =
    championship ? "Editar campeonato" : "Crear campeonato";
  document.querySelector("#championshipName").value = championship?.name || "";
  document.querySelector("#championshipStartDate").value = championship?.startDate || "";
  document.querySelector("#championshipEndDate").value = championship?.endDate || "";
  document.querySelector("#championshipRankingMode").value =
    championship?.rankingMode || "all-races";
  document.querySelector("#championshipMinimumRaces").value =
    championship?.minimumRaces || 2;
  document.querySelector("#championshipParticipantMode").value =
    championship?.participantMode || "recurrent";
  document.querySelector("#championshipIncludeOwner").checked =
    championship?.includeOwner !== false;
  document.querySelector("#deleteChampionshipButton").hidden = !championship;
  document.querySelector("#championshipDriverSearch").value = "";
  renderChampionshipFormChoices(championship);
  updateChampionshipDriverVisibility();
  showDetailDialogOnTop(championshipDialog);
}

async function refreshCustomChampionships(preferredId = null) {
  miniLeagueAnalysis = await apiRequest("/api/mini-leagues");
  if (preferredId != null) {
    activeCustomChampionshipId = Number(preferredId);
    activeMiniLeagueScope = `custom:${preferredId}`;
  }
  renderMiniLeagues();
}

function openMiniLeagueDriverDetail(iracingId) {
  const league = selectedMiniLeague();
  const participant = league?.participants.find(
    (item) => String(item.iracingId) === String(iracingId)
  );
  if (!participant) return;
  const officialPosition = miniLeagueClassification(league).positions.get(
    String(participant.iracingId)
  );
  const isAssetto = (appState.settings.platform || appState.league.platform) === "assetto-corsa";
  const gridRating = participant.gridRating;
  sessionDriverDialog.dataset.driverId = participant.iracingId;
  sessionDriverDialog.dataset.miniLeagueScope = activeMiniLeagueScope;
  sessionDriverDialog.dataset.miniLeaguePeriod = league.periodKey || activeMiniLeagueScope;
  const scopeLabels = {
    eternal: "eterna",
    yearly: "anual",
    season: "de temporada",
    monthly: "mensual"
  };
  document.querySelector("#sessionDriverKicker").textContent =
    activeMiniLeagueScope.startsWith("custom:")
      ? `${league.label} · Campeonato GridScope`
      : `${league.label} · Campeonato ${scopeLabels[activeMiniLeagueScope] || activeMiniLeagueScope}`;
  document.querySelector("#sessionDriverTitle").textContent = participant.name;
  document.querySelector("#sessionDriverContent").innerHTML = `
    ${gridRating ? `<div class="driver-rating-highlights assetto-rating-highlights">
      <article class="gridscope-highlight">
        <div><small>${metricHelp("GridScore en el periodo", gridRatingExplanation())}</small><strong>${formatDecimal(gridRating.gridScore)}</strong></div>
        <span class="${Number(gridRating.gridScoreChange) > 0 ? "positive" : Number(gridRating.gridScoreChange) < 0 ? "negative" : "neutral"}">${formatDecimal(gridRating.gridScoreStart)} → ${formatDecimal(gridRating.gridScore)} · ${formatSigned(gridRating.gridScoreChange)}</span>
      </article>
      <article class="safety-highlight">
        <div><small>${metricHelp("Limpieza en el periodo", cleanlinessRatingExplanation())}</small><strong>${formatDecimal(gridRating.cleanlinessScore)}</strong></div>
        <span>Confianza ${gridRating.confidence.toLowerCase()} · ${gridRating.ratedRaces} carreras</span>
      </article>
    </div>` : ""}${isAssetto ? "" : `<div class="driver-rating-highlights">
      <article class="irating-highlight">
        <div><small>${metricHelp("iRating en el periodo", "Valor al finalizar la última carrera registrada del periodo. La línea inferior muestra el valor inicial, el final y la variación.")}</small><strong>${participant.iratingEnd == null ? "—" : formatInteger(participant.iratingEnd)}</strong></div>
        <span class="${Number(participant.iratingChange) > 0 ? "positive" : Number(participant.iratingChange) < 0 ? "negative" : "neutral"}">${participant.iratingEnd == null ? "No disponible" : `${participant.iratingStart == null ? "—" : formatInteger(participant.iratingStart)} → ${formatInteger(participant.iratingEnd)} · ${formatSigned(participant.iratingChange)}`}</span>
      </article>
      <article class="safety-highlight">
        <div><small>${metricHelp("Safety Rating en el periodo", "Safety Rating al finalizar la última carrera registrada. La línea inferior muestra el valor inicial, el final y la variación.")}</small><strong>${participant.safetyRatingEnd == null ? "—" : formatDecimal(participant.safetyRatingEnd)}</strong></div>
        <span class="${Number(participant.safetyRatingChange) > 0 ? "positive" : Number(participant.safetyRatingChange) < 0 ? "negative" : "neutral"}">${participant.safetyRatingEnd == null ? "No disponible" : `${participant.safetyRatingStart == null ? "—" : formatDecimal(participant.safetyRatingStart)} → ${formatDecimal(participant.safetyRatingEnd)} · ${formatSigned(participant.safetyRatingChange)}`}</span>
      </article>
    </div>`}
    <div class="driver-season-stats mini-driver-stats">
      <article><small>${metricHelp("Posición", `Puesto dentro del campeonato según el índice medio. Se necesitan al menos ${miniLeagueMinimumRaces} carreras; en caso de empate se priorizan más carreras y después menos incidentes por carrera.`)}</small><strong>${officialPosition ? `P${officialPosition}` : "Provisional"}</strong><span>${officialPosition ? "clasificación del campeonato" : `${participant.races} de ${miniLeagueMinimumRaces} carreras mínimas`}</span></article>
      <article><small>${metricHelp("Índice", "En cada carrera, entre los miembros presentes, el primero recibe 100 puntos, el último 0 y el resto una puntuación proporcional a su puesto. El Índice es la media de esas puntuaciones y cada carrera pesa lo mismo.")}</small><strong>${formatDecimal(participant.score)}</strong><span>media normalizada</span></article>
      <article><small>${metricHelp("Carreras", raceCountExplanation())}</small><strong>${participant.races}</strong><span>${participant.seriesCount} series</span></article>
      <article><small>${metricHelp("Duelos", duelExplanation())}</small><strong>${participant.wins}-${participant.losses}</strong><span>${formatDecimal(participant.duelWinRate)}% ganado</span></article>
      <article><small>${metricHelp("Incidentes", isAssetto ? personalContactExplanation("assetto-corsa") : "Suma de puntos de incidente de todas las carreras puntuables. Debajo aparece el total dividido entre el número de carreras.")}</small><strong>${participant.incidents}x</strong><span>${formatDecimal(participant.averageIncidents)}x/carrera</span></article>
      <article><small>${metricHelp("Posiciones", "Suma de las posiciones ganadas o perdidas entre la salida y la meta en todas las carreras del periodo.")}</small><strong>${formatSigned(participant.positionsGained)}</strong><span>ganadas en pista</span></article>
      <article><small>${metricHelp("Frente al piloto de referencia", "Cara a cara exclusivamente contra el piloto configurado como referencia. El primer número indica sus resultados por delante y el segundo, los del rival.")}</small><strong>${participant.isOwner ? "Referencia" : `${participant.ownerAhead}-${participant.rivalAhead}`}</strong><span>cara a cara</span></article>
    </div>
    <div class="driver-detail-explainer"><strong>Series compartidas:</strong> ${participant.seriesNames.map(escapeHtml).join(" · ")}</div>
    <div class="table-wrap season-driver-races-wrap">
      <table class="session-driver-races-table mini-driver-races-table">
        <thead><tr><th>Carrera</th><th>Serie</th><th class="numeric">Posición interna</th><th class="numeric">Posición en carrera</th><th class="numeric">Índice</th>${isAssetto ? `<th class="numeric">${metricHelp("GridScore", gridScoreFormulaExplanation())}</th><th class="numeric">${metricHelp("Limpieza", cleanlinessFormulaExplanation())}</th>` : '<th class="numeric">SoF</th>'}<th class="numeric">Inc.</th><th class="numeric">Frente a ti</th><th></th></tr></thead>
        <tbody>
          ${participant.raceDetails.map((race) => `
            <tr data-driver-race-id="${race.eventId}" tabindex="0" role="button">
              <td><strong>${escapeHtml(race.track)}</strong><small class="table-subline">${formatRaceDate(race.startTime)} · ${escapeHtml(race.layout || "")}</small></td>
              <td>${escapeHtml(race.seriesName)}</td>
              <td class="numeric metric-strong">P${race.leaguePosition} / ${race.leagueParticipants}</td>
              <td class="numeric">P${race.finishPosition}</td>
              <td class="numeric mini-score">${formatDecimal(race.score)}</td>
              ${isAssetto ? `<td class="numeric">${gridScoreMarkup(race)}</td><td class="numeric">${cleanlinessMarkup(race)}</td>` : `<td class="numeric">${formatInteger(race.strengthOfField)}</td>`}
              <td class="numeric">${race.incidents}x</td>
              <td class="numeric">${participant.isOwner ? "Referencia" : race.ownerPosition == null ? "—" : `P${race.finishPosition} / tú P${race.ownerPosition}`}</td>
              <td><button class="text-button" type="button" data-driver-race-id="${race.eventId}">Abrir</button></td>
            </tr>`).join("")}
        </tbody>
      </table>
    </div>`;
  showDetailDialogOnTop(sessionDriverDialog);
}

async function loadRaceAnalytics() {
  try {
    [raceAnalysis, rivalAnalysis, globalAnalysis, miniLeagueAnalysis, telemetryAnalysis, ownerSeasonAnalysis] = await Promise.all([
      apiRequest("/api/races"),
      apiRequest("/api/rivals"),
      apiRequest("/api/overview/global"),
      apiRequest("/api/mini-leagues"),
      apiRequest("/api/telemetry"),
      apiRequest(`/api/drivers/${encodeURIComponent(appState.settings.ownerIracingId)}`).catch(() => null)
    ]);
    renderRaceExplorer();
    renderRivals();
    renderGlobalOverview();
    renderMiniLeagues();
    renderTelemetrySettings();
    renderOwnerSeasonOverview();
  } catch (error) {
    document.querySelector("#raceExplorer").innerHTML =
      `<article class="empty-archive"><h3>No se pudo cargar el análisis</h3><p>${escapeHtml(error.message)}</p></article>`;
  }
}

function ratingJourney(start, end, change, decimals = false) {
  if (start == null && end == null) return '<span class="rating-unavailable">—</span>';
  const format = decimals ? formatDecimal : formatInteger;
  const startLabel = start == null ? "—" : format(start);
  const endLabel = end == null ? "—" : format(end);
  const changeClass = Number(change) > 0 ? "positive" : Number(change) < 0 ? "negative" : "neutral";
  return `
    <span class="rating-stack">
      <strong>${startLabel} → ${endLabel}</strong>
      <small class="${changeClass}">${formatSigned(change)}</small>
    </span>`;
}

async function openSessionDetail(week) {
  document.querySelector("#sessionDetailKicker").textContent = `Semana ${week}`;
  document.querySelector("#sessionDetailTitle").textContent = "Cargando análisis semanal…";
  document.querySelector("#sessionDetailContent").innerHTML = dialogLoadingMarkup(
    "Preparando la sesión…",
    "Estamos reuniendo sus carreras, pilotos recurrentes, resultados y comparativas."
  );
  sessionDetailDialog.showModal();
  const activity = beginActivity(
    "Preparando la sesión…",
    `Analizando las carreras y coincidencias de la semana ${week}.`
  );
  try {
    const detail = await apiRequest(`/api/sessions/${week}`);
    currentSessionDetail = detail;
    const session = detail.session;
    const isAssetto = (appState.settings.platform || appState.league.platform) === "assetto-corsa";
    const repeated = detail.drivers.filter((driver) => driver.repeated);
    const ownerSessionDriver = detail.drivers.find((driver) => driver.isOwner);
    document.querySelector("#sessionDetailKicker").textContent =
      `${shortSeason(session.season)} · Semana ${session.week}`;
    document.querySelector("#sessionDetailTitle").textContent =
      `${session.track} · ${session.layout || "Trazado principal"}`;
    document.querySelector("#sessionDetailContent").innerHTML = `
      <div class="track-detail-hero">
        <img src="${trackImageUrl(session.track, session.layout)}" alt="${escapeHtml(session.track)}">
        <div><small>Semana ${session.week}</small><strong>${escapeHtml(session.track)}</strong><span>${escapeHtml(session.layout || "Trazado principal")} · ${escapeHtml(session.seriesName)}</span></div>
      </div>
      <div class="session-detail-meta">
        <article><small>Carreras</small><strong>${session.raceCount}</strong></article>
        <article><small>Pilotos únicos</small><strong>${session.uniqueDrivers}</strong></article>
        <article><small>Recurrentes</small><strong>${session.repeatedDrivers}</strong></article>
        <article><small>${isAssetto ? "Tu GridScore" : "SoF medio"}</small><strong>${isAssetto ? ownerSessionDriver?.gridRating ? formatDecimal(ownerSessionDriver.gridRating.gridScore) : "—" : session.averageSof ? formatInteger(session.averageSof) : "—"}</strong></article>
        ${isAssetto ? "" : `<article><small>${metricHelp("Tu GridScore", gridRatingExplanation())}</small><strong>${ownerSessionDriver?.gridRating ? formatDecimal(ownerSessionDriver.gridRating.gridScore) : "—"}</strong></article>`}
        <article><small>${metricHelp("Incidentes de parrilla", fieldContactExplanation(isAssetto ? "assetto-corsa" : "iracing", "esta semana"))}</small><strong>${formatInteger(session.totalIncidents)}x</strong></article>
        <article><small>Tus carreras</small><strong>${session.ownerRaces}</strong></article>
      </div>

      <section class="session-block">
        <div class="session-block-heading">
          <div><p class="eyebrow">Coincidencias de la semana</p><h3>Pilotos que se repiten</h3></div>
          <span>${repeated.length} de ${detail.drivers.length} pilotos · Pulsa uno para ver sus carreras</span>
        </div>
        <div class="repeat-driver-strip">
          ${repeated.length ? repeated.slice(0, 8).map((driver) => `
            <article class="${driver.isOwner ? "owner-repeat-card" : ""}" data-session-driver-id="${driver.iracingId}" tabindex="0" role="button" aria-label="Ver detalle de ${escapeHtml(driver.name)}">
              <div class="repeat-driver-name">
                <i class="avatar ${driver.color}">${escapeHtml(driver.initials)}</i>
                <span><strong>${escapeHtml(driver.name)}</strong><small>${driver.appearances} carreras · media P${formatDecimal(driver.averageFinish)}</small></span>
              </div>
              <div class="repeat-driver-stats">
                <span><small>Mejor</small><strong>P${driver.bestFinish}</strong></span>
                <span><small>Inc.</small><strong>${formatDecimal(driver.averageIncidents)}x</strong></span>
                <span class="repeat-rating"><small>${isAssetto ? "GridScore" : "iRating"}</small><strong>${isAssetto ? driver.gridRating ? formatDecimal(driver.gridRating.gridScore) : "—" : driver.iratingEnd == null ? "—" : formatInteger(driver.iratingEnd)}</strong><em>${isAssetto ? driver.gridRating ? formatSigned(driver.gridRating.gridScoreChange) : "" : driver.iratingEnd == null ? "" : formatSigned(driver.iratingChange)}</em></span>
                <span class="repeat-rating"><small>${isAssetto ? "Limpieza" : "Safety Rating"}</small><strong>${isAssetto ? driver.gridRating ? formatDecimal(driver.gridRating.cleanlinessScore) : "—" : driver.safetyRatingEnd == null ? "—" : formatDecimal(driver.safetyRatingEnd)}</strong><em>${isAssetto ? driver.gridRating?.confidence || "" : driver.safetyRatingEnd == null ? "" : formatSigned(driver.safetyRatingChange)}</em></span>
                ${isAssetto ? "" : `<span class="repeat-rating"><small>GridScore</small><strong>${driver.gridRating ? formatDecimal(driver.gridRating.gridScore) : "—"}</strong><em>GridScope</em></span>
                <span class="repeat-rating"><small>Limpieza</small><strong>${driver.gridRating ? formatDecimal(driver.gridRating.cleanlinessScore) : "—"}</strong><em>${driver.gridRating?.confidence || ""}</em></span>`}
                <span><small>Frente a ti</small><strong>${driver.isOwner ? "Referencia" : driver.meetingsWithOwner ? `${driver.ownerAhead}-${driver.rivalAhead}` : "—"}</strong></span>
              </div>
            </article>`).join("") : '<p class="session-empty">En esta semana ningún piloto aparece en más de una carrera importada.</p>'}
        </div>
      </section>

      <section class="session-block">
        <div class="session-block-heading">
          <div><p class="eyebrow">Resultados importados</p><h3>Carreras de la sesión</h3></div>
          <span>Pulsa para abrir el desglose completo</span>
        </div>
        <div class="session-race-strip">
          ${detail.races.map((race) => `
            <button type="button" data-session-race-id="${race.id}">
              <span><strong>${formatRaceDate(race.startTime)}</strong><small>${isAssetto ? `${race.fieldSize} pilotos` : `Split ${race.splitNumber || "—"}${race.splitTotal ? ` / ${race.splitTotal}` : ""} · SoF ${formatInteger(race.strengthOfField)} · ${race.fieldSize} pilotos`}</small></span>
              <span class="session-owner-result"><small>Tu resultado</small><strong>${race.ownerResult ? `P${race.ownerResult.finishPosition} · ${race.ownerResult.incidents}x${race.ownerResult.gridScore != null ? ` · GS ${formatDecimal(race.ownerResult.gridScore)}` : ""}` : "No participaste"}</strong></span>
              <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m7 4 6 6-6 6" /></svg>
            </button>`).join("")}
        </div>
      </section>

      <section class="session-block session-driver-block">
        <div class="session-block-heading">
          <div><p class="eyebrow">Estadísticas acumuladas</p><h3>Todos los pilotos de la semana</h3></div>
          <span>${isAssetto ? "Pulsa una fila para abrir su ficha · GridScore calculado con los JSON" : "Pulsa una fila para abrir su ficha · datos oficiales y métricas GridScope"}</span>
        </div>
        <div class="table-wrap session-drivers-wrap">
          <table class="session-driver-table">
            <thead>
              <tr>
                <th>Piloto</th><th class="numeric">Carreras</th>
                <th class="numeric rating-column">${isAssetto ? "GridScore" : "iRating inicial → final"}</th><th class="numeric rating-column">${isAssetto ? "Limpieza" : "SR inicial → final"}</th>
                ${isAssetto ? "" : `<th class="numeric rating-column">${metricHelp("GridScore", gridRatingExplanation())}</th><th class="numeric rating-column">${metricHelp("Limpieza", cleanlinessRatingExplanation())}</th>`}
                <th class="numeric">Meta media</th>
                <th class="numeric">Mejor</th><th class="numeric">Salida media</th><th class="numeric">± Pos.</th>
                <th class="numeric">Incidentes</th><th class="numeric">Vueltas</th><th class="numeric">Mejor vuelta</th>
                <th class="numeric">Frente a ti</th>
              </tr>
            </thead>
            <tbody>
              ${detail.drivers.map((driver) => `
                <tr class="${driver.isOwner ? "owner-result" : ""}" data-session-driver-id="${driver.iracingId}" tabindex="0">
                  <td>
                    <div class="driver-cell">
                      <i class="avatar ${driver.color}">${escapeHtml(driver.initials)}</i>
                      <span><strong>${escapeHtml(driver.name)}</strong><small>${escapeHtml(driverIdentityText(driver.iracingId))}${driver.repeated ? ' · <em class="repeat-badge">RECURRENTE</em>' : ""}</small></span>
                    </div>
                  </td>
                  <td class="numeric metric-strong">${driver.appearances}</td>
                  <td class="numeric rating-cell">${isAssetto ? driver.gridRating ? `${formatDecimal(driver.gridRating.gridScore)} <small>${formatSigned(driver.gridRating.gridScoreChange)}</small>` : "—" : ratingJourney(driver.iratingStart, driver.iratingEnd, driver.iratingChange)}</td>
                  <td class="numeric rating-cell">${isAssetto ? driver.gridRating ? `${formatDecimal(driver.gridRating.cleanlinessScore)} <small>${driver.gridRating.confidence}</small>` : "—" : ratingJourney(driver.safetyRatingStart, driver.safetyRatingEnd, driver.safetyRatingChange, true)}</td>
                  ${isAssetto ? "" : `<td class="numeric rating-cell">${driver.gridRating ? `${formatDecimal(driver.gridRating.gridScore)} <small>${formatSigned(driver.gridRating.gridScoreChange)}</small>` : "—"}</td>
                  <td class="numeric rating-cell">${driver.gridRating ? `${formatDecimal(driver.gridRating.cleanlinessScore)} <small>${driver.gridRating.confidence}</small>` : "—"}</td>`}
                  <td class="numeric">P${formatDecimal(driver.averageFinish)}</td>
                  <td class="numeric">P${driver.bestFinish}${driver.wins ? ` · ${driver.wins}V` : ""}</td>
                  <td class="numeric">${driver.averageStart == null ? "—" : `P${formatDecimal(driver.averageStart)}`}</td>
                  <td class="numeric">${positionChangeMarkup(driver.positionsGained)}</td>
                  <td class="numeric">${driver.totalIncidents}x <small>${formatDecimal(driver.averageIncidents)}x/carrera</small></td>
                  <td class="numeric">${formatInteger(driver.lapsComplete)}</td>
                  <td class="numeric">${formatLapTime(driver.bestLapTime)}</td>
                  <td class="numeric head-to-head-cell">${driver.isOwner
                    ? '<span class="owner-reference">Referencia</span>'
                    : driver.meetingsWithOwner
                      ? `<strong>${driver.ownerAhead}-${driver.rivalAhead}</strong><small>${driver.meetingsWithOwner} coincidencias</small>`
                      : "—"}</td>
                </tr>`).join("")}
            </tbody>
          </table>
        </div>
      </section>`;
  } catch (error) {
    document.querySelector("#sessionDetailTitle").textContent = "No se pudo abrir la sesión";
    document.querySelector("#sessionDetailContent").innerHTML =
      `<p class="dialog-help">${escapeHtml(error.message)}</p>`;
  } finally {
    endActivity(activity);
  }
}

function openSessionDriverDetail(iracingId) {
  const driver = currentSessionDetail?.drivers.find(
    (item) => String(item.iracingId) === String(iracingId)
  );
  if (!driver) return;
  delete sessionDriverDialog.dataset.miniLeagueScope;
  const session = currentSessionDetail.session;
  const isAssetto = (appState.settings.platform || appState.league.platform) === "assetto-corsa";
  const gridRating = driver.gridRating;
  document.querySelector("#sessionDriverKicker").textContent =
    `${shortSeason(session.season)} · Semana ${session.week} · ${driver.appearances} carrera${driver.appearances === 1 ? "" : "s"}`;
  document.querySelector("#sessionDriverTitle").textContent = driver.name;
  sessionDriverDialog.dataset.driverId = driver.iracingId;
  document.querySelector("#sessionDriverContent").innerHTML = `
    ${gridRating ? `<div class="driver-rating-highlights assetto-rating-highlights">
      <article class="gridscope-highlight">
        <div><small>${metricHelp("GridScore en la sesión", gridRatingExplanation())}</small><strong>${formatDecimal(gridRating.gridScore)}</strong></div>
        <span>${gridRating.ratedRaces} carrera${gridRating.ratedRaces === 1 ? "" : "s"} valorada${gridRating.ratedRaces === 1 ? "" : "s"} · confianza ${gridRating.confidence.toLowerCase()}</span>
      </article>
      <article class="safety-highlight">
        <div><small>${metricHelp("Limpieza en la sesión", cleanlinessRatingExplanation())}</small><strong>${formatDecimal(gridRating.cleanlinessScore)}</strong></div>
        <span>${formatInteger(Math.round(gridRating.drivingMinutes))} min analizados</span>
      </article>
    </div>` : ""}${isAssetto ? "" : `<div class="driver-rating-highlights">
      <article class="irating-highlight">
        <div><small>iRating actual en esta sesión</small><strong>${driver.iratingEnd == null ? "—" : formatInteger(driver.iratingEnd)}</strong></div>
        <span class="${Number(driver.iratingChange) > 0 ? "positive" : Number(driver.iratingChange) < 0 ? "negative" : "neutral"}">
          ${driver.iratingEnd == null ? "No incluido en el JSON" : `${driver.iratingStart == null ? "—" : formatInteger(driver.iratingStart)} → ${formatInteger(driver.iratingEnd)} · ${formatSigned(driver.iratingChange)}`}
        </span>
      </article>
      <article class="safety-highlight">
        <div><small>Safety Rating actual en esta sesión</small><strong>${driver.safetyRatingEnd == null ? "—" : formatDecimal(driver.safetyRatingEnd)}</strong></div>
        <span class="${Number(driver.safetyRatingChange) > 0 ? "positive" : Number(driver.safetyRatingChange) < 0 ? "negative" : "neutral"}">
          ${driver.safetyRatingEnd == null ? "No incluido en el JSON" : `${driver.safetyRatingStart == null ? "—" : formatDecimal(driver.safetyRatingStart)} → ${formatDecimal(driver.safetyRatingEnd)} · ${formatSigned(driver.safetyRatingChange)}`}
        </span>
      </article>
    </div>`}
    <div class="driver-detail-summary">
      <article><small>Participaciones</small><strong>${driver.appearances}</strong><span>${driver.repeated ? "Piloto recurrente" : "Una aparición"}</span></article>
      <article><small>Posición media</small><strong>P${formatDecimal(driver.averageFinish)}</strong><span>Mejor: P${driver.bestFinish}</span></article>
      <article><small>Salida media</small><strong>${driver.averageStart == null ? "—" : `P${formatDecimal(driver.averageStart)}`}</strong><span>${formatSigned(driver.positionsGained, " posiciones")}</span></article>
      <article><small>Incidentes</small><strong>${driver.totalIncidents}x</strong><span>${formatDecimal(driver.averageIncidents)}x por carrera</span></article>
      <article><small>Frente a ti</small><strong>${driver.isOwner ? "Referencia" : driver.meetingsWithOwner ? `${driver.ownerAhead}-${driver.rivalAhead}` : "—"}</strong><span>${driver.isOwner ? "Tu piloto configurado" : `${driver.meetingsWithOwner} coincidencia${driver.meetingsWithOwner === 1 ? "" : "s"}`}</span></article>
    </div>
    <div class="driver-detail-explainer">
      ${driver.isOwner
        ? "Estas son tus carreras importadas durante esta semana."
        : driver.meetingsWithOwner
          ? `<strong>Balance directo:</strong> terminaste delante en ${driver.ownerAhead} y ${escapeHtml(driver.name)} terminó delante en ${driver.rivalAhead}.`
          : "Tu piloto configurado no aparece en las mismas carreras de esta semana."}
    </div>
    <div class="table-wrap session-driver-races-wrap">
      <table class="session-driver-races-table">
        <thead>
          <tr>
            <th>Carrera</th>${isAssetto ? "" : '<th class="numeric">SoF</th><th class="numeric">Split</th>'}
            <th class="numeric">Salida</th><th class="numeric">Meta</th><th class="numeric">± Pos.</th>
            <th class="numeric">Inc.</th><th class="numeric">Vueltas</th><th class="numeric">Mejor vuelta</th>
            ${isAssetto ? `<th class="numeric">${metricHelp("GridScore", gridScoreFormulaExplanation())}</th><th class="numeric">${metricHelp("Limpieza", cleanlinessFormulaExplanation())}</th>` : `<th class="numeric">iRating</th><th class="numeric">SR</th><th class="numeric">${metricHelp("GridScore", gridScoreFormulaExplanation())}</th><th class="numeric">${metricHelp("Limpieza", cleanlinessFormulaExplanation())}</th>`}<th>Comparación</th><th></th>
          </tr>
        </thead>
        <tbody>
          ${driver.raceDetails.map((race) => {
            const ownerWon = !driver.isOwner && race.ownerPosition != null && race.ownerPosition < race.finishPosition;
            const rivalWon = !driver.isOwner && race.ownerPosition != null && race.ownerPosition > race.finishPosition;
            const comparison = driver.isOwner
              ? '<span class="head-to-head-result tied">Tu carrera</span>'
              : race.ownerPosition == null
                ? '<span class="head-to-head-result tied">Sin coincidencia</span>'
                : `<span class="head-to-head-result ${ownerWon ? "won" : rivalWon ? "lost" : "tied"}">${ownerWon ? `Tú P${race.ownerPosition} · rival P${race.finishPosition}` : rivalWon ? `Rival P${race.finishPosition} · tú P${race.ownerPosition}` : `Ambos P${race.finishPosition}`}</span>`;
            return `
              <tr data-driver-race-id="${race.eventId}" tabindex="0" role="button" aria-label="Abrir carrera en ${escapeHtml(race.track)}">
                <td><strong>${escapeHtml(race.track)}</strong><small class="table-subline">${escapeHtml(race.layout || "Trazado principal")} · ${formatRaceDate(race.startTime)}</small></td>
                ${isAssetto ? "" : `<td class="numeric">${formatInteger(race.strengthOfField)}</td>
                <td class="numeric">${race.splitNumber || "—"}${race.splitTotal ? ` / ${race.splitTotal}` : ""}</td>`}
                <td class="numeric">${race.startPosition ?? "—"}</td>
                <td class="numeric metric-strong">P${race.finishPosition}</td>
                <td class="numeric">${race.positionChange == null ? "—" : positionChangeMarkup(race.positionChange)}</td>
                <td class="numeric">${race.incidents}x</td>
                <td class="numeric">${race.lapsComplete}</td>
                <td class="numeric">${formatLapTime(race.bestLapTime)}</td>
                ${isAssetto ? `<td class="numeric">${gridScoreMarkup(race)}</td><td class="numeric">${cleanlinessMarkup(race)}</td>` : `<td class="numeric">${race.newIRating == null ? "—" : `${formatInteger(race.newIRating)} <small>${formatSigned(race.iratingChange)}</small>`}</td>
                <td class="numeric">${race.newSafetyRating == null ? "—" : `${formatDecimal(race.newSafetyRating)} <small>${formatSigned(race.safetyRatingChange)}</small>`}</td>
                <td class="numeric">${gridScoreMarkup(race)}</td><td class="numeric">${cleanlinessMarkup(race)}</td>`}
                <td>${comparison}</td>
                <td><button class="text-button" type="button" data-driver-race-id="${race.eventId}">Abrir carrera</button></td>
              </tr>`;
          }).join("")}
        </tbody>
      </table>
    </div>`;
  showDetailDialogOnTop(sessionDriverDialog);
}

async function openSeasonDriverDetail(iracingId, scope = "active") {
  delete sessionDriverDialog.dataset.miniLeagueScope;
  sessionDriverDialog.dataset.driverId = iracingId;
  document.querySelector("#sessionDriverKicker").textContent =
    scope === "global"
      ? "Historial compartido · Todas las series"
      : `${shortSeason(appState.league.season)} · Perfil de temporada`;
  document.querySelector("#sessionDriverTitle").textContent = "Cargando piloto…";
  document.querySelector("#sessionDriverContent").innerHTML = dialogLoadingMarkup(
    "Calculando el perfil…",
    "Estamos reuniendo sus carreras, circuitos, enfrentamientos y evolución."
  );
  showDetailDialogOnTop(sessionDriverDialog);
  const activity = beginActivity(
    "Calculando el perfil del piloto…",
    scope === "global"
      ? "Reuniendo todas las coincidencias de este simulador."
      : "Reuniendo carreras, circuitos y comparativas del periodo seleccionado."
  );
  try {
    const detail = await apiRequest(
      `/api/drivers/${encodeURIComponent(iracingId)}?scope=${encodeURIComponent(scope)}`
    );
    const driver = detail.driver;
    const summary = detail.summary;
    const isAssetto = (appState.settings.platform || appState.league.platform) === "assetto-corsa";
    const isGlobal = detail.scope === "global";
    const gridRating = summary.gridRating;
    sessionDriverDialog.dataset.driverId = driver.iracingId;
    document.querySelector("#sessionDriverKicker").textContent =
      isGlobal
        ? `Historial compartido · ${summary.races} carrera${summary.races === 1 ? "" : "s"} · ${summary.series} serie${summary.series === 1 ? "" : "s"}`
        : `${shortSeason(detail.season)} · ${detail.seriesName}`;
    document.querySelector("#sessionDriverTitle").textContent = driver.name;
    document.querySelector("#sessionDriverContent").innerHTML = `
      <div class="driver-profile-identity">
        <div class="driver-cell">
          <i class="avatar ${driver.color}">${escapeHtml(driver.initials)}</i>
          <span><strong>${escapeHtml(driver.name)}</strong><small>${escapeHtml(driverIdentityText(driver.iracingId))}${driver.countryCode ? ` · ${escapeHtml(driver.countryCode)}` : ""}${driver.division ? ` · ${escapeHtml(driver.division)}` : ""}</small></span>
        </div>
        <span>${summary.races} carreras · ${isGlobal ? `${summary.sessions} sesiones · ${summary.seasons} periodos` : `${summary.weeks} semanas`} · ${detail.tracks.length} circuitos</span>
      </div>
      ${gridRating ? `<div class="driver-rating-highlights assetto-rating-highlights">
        <article class="gridscope-highlight">
          <div><small>${metricHelp("GridScore actual", gridRatingExplanation())}</small><strong>${formatDecimal(gridRating.gridScore)}</strong></div>
          <span class="${Number(gridRating.gridScoreChange) > 0 ? "positive" : Number(gridRating.gridScoreChange) < 0 ? "negative" : "neutral"}">
            ${formatDecimal(gridRating.gridScoreStart)} → ${formatDecimal(gridRating.gridScore)} · ${formatSigned(gridRating.gridScoreChange)}
          </span>
        </article>
        <article class="safety-highlight">
          <div><small>${metricHelp("Limpieza actual", cleanlinessRatingExplanation())}</small><strong>${formatDecimal(gridRating.cleanlinessScore)}</strong></div>
          <span class="${Number(gridRating.cleanlinessChange) > 0 ? "positive" : Number(gridRating.cleanlinessChange) < 0 ? "negative" : "neutral"}">
            ${formatDecimal(gridRating.cleanlinessStart)} → ${formatDecimal(gridRating.cleanlinessScore)} · ${formatSigned(gridRating.cleanlinessChange)}
          </span>
        </article>
      </div>
      <div class="assetto-rating-explainer">
        <strong>Índice propio de GridScope · no es una valoración oficial</strong>
        <span>${isAssetto
          ? "Resultado 40% · progreso 15% · ritmo 15% · consistencia 10% · carrera completada 10% · rivales recurrentes 10%."
          : "Resultado 35% · progreso 15% · ritmo 15% · carrera completada 10% · rivales recurrentes 10% · dificultad SoF 15%."} Después, GridScore combina 75% rendimiento y 25% limpieza.</span>
        <em>${metricHelp("Confianza", confidenceExplanation())} ${gridRating.confidence} · ${gridRating.ratedRaces} carreras · ${formatInteger(Math.round(gridRating.drivingMinutes))} min analizados</em>
      </div>` : ""}${isAssetto ? "" : `<div class="driver-rating-highlights">
        <article class="irating-highlight">
          <div><small>iRating actual</small><strong>${summary.iratingEnd == null ? "—" : formatInteger(summary.iratingEnd)}</strong></div>
          <span class="${Number(summary.iratingChange) > 0 ? "positive" : Number(summary.iratingChange) < 0 ? "negative" : "neutral"}">
            ${summary.iratingEnd == null ? "No disponible" : `${summary.iratingStart == null ? "—" : formatInteger(summary.iratingStart)} → ${formatInteger(summary.iratingEnd)} · ${formatSigned(summary.iratingChange)}`}
          </span>
        </article>
        <article class="safety-highlight">
          <div><small>Safety Rating actual</small><strong>${summary.safetyRatingEnd == null ? "—" : formatDecimal(summary.safetyRatingEnd)}</strong></div>
          <span class="${Number(summary.safetyRatingChange) > 0 ? "positive" : Number(summary.safetyRatingChange) < 0 ? "negative" : "neutral"}">
            ${summary.safetyRatingEnd == null ? "No disponible" : `${summary.safetyRatingStart == null ? "—" : formatDecimal(summary.safetyRatingStart)} → ${formatDecimal(summary.safetyRatingEnd)} · ${formatSigned(summary.safetyRatingChange)}`}
          </span>
        </article>
      </div>`}
      <div class="driver-season-stats">
        <article><small>${isGlobal && !driver.isOwner ? "Coincidencias" : "Carreras"}</small><strong>${summary.races}</strong><span>${isGlobal ? `${summary.sessions} sesiones` : `${summary.weeks} semanas`}</span></article>
        <article><small>Posición media</small><strong>P${formatDecimal(summary.averageFinish)}</strong><span>P${summary.bestFinish} mejor · P${summary.worstFinish} peor</span></article>
        <article><small>Victorias</small><strong>${summary.wins}</strong><span>${summary.topFive} top 5 · ${summary.topTen} top 10</span></article>
        <article><small>Salida media</small><strong>${summary.averageStart == null ? "—" : `P${formatDecimal(summary.averageStart)}`}</strong><span>${formatSigned(summary.positionsGained, " posiciones")}</span></article>
        <article><small>Incidentes</small><strong>${summary.totalIncidents}x</strong><span>${formatDecimal(summary.averageIncidents)}x por carrera</span></article>
        <article><small>Vueltas</small><strong>${formatInteger(summary.lapsComplete)}</strong><span>${summary.lapsLed} lideradas</span></article>
        <article><small>Mejor vuelta</small><strong>${formatLapTime(summary.bestLapTime)}</strong><span>mejor registro de la temporada</span></article>
        ${isAssetto ? `<article><small>Circuitos</small><strong>${detail.tracks.length}</strong><span>trazados diferentes</span></article>` : `<article><small>SoF medio</small><strong>${summary.averageSof ? formatInteger(summary.averageSof) : "—"}</strong><span>nivel de las parrillas</span></article>`}
        <article><small>Frente a ti</small><strong>${driver.isOwner ? "Referencia" : summary.meetingsWithOwner ? `${summary.ownerAhead}-${summary.rivalAhead}` : "—"}</strong><span>${driver.isOwner ? "Tu piloto configurado" : `${summary.meetingsWithOwner} coincidencias`}</span></article>
      </div>

      ${isGlobal ? `<section class="driver-profile-section">
        <div class="session-block-heading">
          <div><p class="eyebrow">Dónde habéis coincidido</p><h3>Series y temporadas compartidas</h3></div>
          <span>${summary.seasons} periodo${summary.seasons === 1 ? "" : "s"} · ordenados del más reciente al más antiguo</span>
        </div>
        <div class="driver-track-grid driver-period-grid">
          ${detail.periods.map((period) => `
            <article>
              <div><strong>${escapeHtml(period.seriesName)}</strong><small>${escapeHtml(shortSeason(period.season))}</small></div>
              <dl>
                <div><dt>Carreras</dt><dd>${period.races}</dd></div>
                <div><dt>Sesiones</dt><dd>${period.sessions}</dd></div>
                <div><dt>Circuitos</dt><dd>${period.tracks}</dd></div>
                <div><dt>Frente a ti</dt><dd>${driver.isOwner ? "Referencia" : `${period.ownerAhead}-${period.rivalAhead}`}</dd></div>
              </dl>
            </article>`).join("")}
        </div>
      </section>` : ""}

      <section class="driver-profile-section">
        <div class="session-block-heading">
          <div><p class="eyebrow">Rendimiento por trazado</p><h3>${isGlobal ? "Circuitos compartidos" : "Circuitos de la temporada"}</h3></div>
          <span>Ordenados por número de participaciones</span>
        </div>
        <div class="driver-track-grid">
          ${detail.tracks.map((track) => `
            <article>
              <div><strong>${escapeHtml(track.track)}</strong><small>${escapeHtml(track.layout || "Trazado principal")}</small></div>
              <dl>
                <div><dt>Carreras</dt><dd>${track.races}</dd></div>
                <div><dt>Media</dt><dd>P${formatDecimal(track.averageFinish)}</dd></div>
                <div><dt>Mejor</dt><dd>P${track.bestFinish}</dd></div>
                <div><dt>Inc.</dt><dd>${formatDecimal(track.averageIncidents)}x</dd></div>
                ${isAssetto ? "" : `<div><dt>SoF</dt><dd>${track.averageSof ? formatInteger(track.averageSof) : "—"}</dd></div>`}
                <div><dt>GridScore</dt><dd>${track.averageGridScore == null ? "—" : formatDecimal(track.averageGridScore)}</dd></div>
              </dl>
            </article>`).join("")}
        </div>
      </section>

      <section class="driver-profile-section">
        <div class="session-block-heading">
          <div><p class="eyebrow">Historial completo</p><h3>${isGlobal && !driver.isOwner ? "Todas vuestras coincidencias" : "Todas sus carreras"}</h3></div>
          <span>${isGlobal ? "Cada fila indica serie, temporada y sesión · " : ""}Pulsa cualquier fila para abrir el resultado completo</span>
        </div>
        <div class="table-wrap season-driver-races-wrap">
          <table class="session-driver-races-table season-driver-races-table">
            <thead>
              <tr>
                ${isGlobal ? "<th>Serie / temporada</th><th>Sesión</th>" : ""}
                <th>Carrera</th>${isAssetto ? "" : '<th class="numeric">SoF</th><th class="numeric">Split</th>'}
                <th class="numeric">Salida</th><th class="numeric">Meta</th><th class="numeric">± Pos.</th>
                <th class="numeric">Inc.</th><th class="numeric">Vueltas</th><th class="numeric">Lideradas</th>
                <th class="numeric">Mejor vuelta</th>${isAssetto ? `<th class="numeric">${metricHelp("GridScore", gridScoreFormulaExplanation())}</th><th class="numeric">${metricHelp("Limpieza", cleanlinessFormulaExplanation())}</th>` : `<th class="numeric">iRating</th><th class="numeric">SR</th><th class="numeric">${metricHelp("GridScore", gridScoreFormulaExplanation())}</th><th class="numeric">${metricHelp("Limpieza", cleanlinessFormulaExplanation())}</th>`}
                <th>Frente a ti</th><th></th>
              </tr>
            </thead>
            <tbody>
              ${detail.races.map((race) => {
                const ownerWon = !driver.isOwner && race.ownerPosition != null && race.ownerPosition < race.finishPosition;
                const rivalWon = !driver.isOwner && race.ownerPosition != null && race.ownerPosition > race.finishPosition;
                const comparison = driver.isOwner
                  ? '<span class="head-to-head-result tied">Tu carrera</span>'
                  : race.ownerPosition == null
                    ? '<span class="head-to-head-result tied">Sin coincidencia</span>'
                    : `<span class="head-to-head-result ${ownerWon ? "won" : rivalWon ? "lost" : "tied"}">${ownerWon ? `Tú P${race.ownerPosition} · rival P${race.finishPosition}` : rivalWon ? `Rival P${race.finishPosition} · tú P${race.ownerPosition}` : `Ambos P${race.finishPosition}`}</span>`;
                return `
                  <tr data-driver-race-id="${race.eventId}" tabindex="0" role="button" aria-label="Abrir carrera en ${escapeHtml(race.track)}">
                    ${isGlobal ? `<td><strong>${escapeHtml(race.seriesName)}</strong><small class="table-subline">${escapeHtml(shortSeason(race.season))}</small></td>
                    <td><strong>Semana ${race.week}</strong><small class="table-subline">${formatRaceDate(race.startTime)}</small></td>` : ""}
                    <td><strong>${escapeHtml(race.track)}</strong><small class="table-subline">${isGlobal ? "" : `S${race.week} · `}${escapeHtml(race.layout || "Trazado principal")}${isGlobal ? "" : ` · ${formatRaceDate(race.startTime)}`}</small></td>
                    ${isAssetto ? "" : `<td class="numeric">${formatInteger(race.strengthOfField)}</td>
                    <td class="numeric">${race.splitNumber || "—"}${race.splitTotal ? ` / ${race.splitTotal}` : ""}</td>`}
                    <td class="numeric">${race.startPosition ?? "—"}</td>
                    <td class="numeric metric-strong">P${race.finishPosition}</td>
                    <td class="numeric">${race.positionChange == null ? "—" : positionChangeMarkup(race.positionChange)}</td>
                    <td class="numeric">${race.incidents}x</td>
                    <td class="numeric">${race.lapsComplete}</td>
                    <td class="numeric">${race.lapsLed ?? 0}</td>
                    <td class="numeric">${formatLapTime(race.bestLapTime)}</td>
                    ${isAssetto ? `<td class="numeric">${gridScoreMarkup(race)}</td><td class="numeric">${cleanlinessMarkup(race)}</td>` : `<td class="numeric">${race.newIRating == null ? "—" : `${formatInteger(race.newIRating)} <small>${formatSigned(race.iratingChange)}</small>`}</td>
                    <td class="numeric">${race.newSafetyRating == null ? "—" : `${formatDecimal(race.newSafetyRating)} <small>${formatSigned(race.safetyRatingChange)}</small>`}</td>
                    <td class="numeric">${gridScoreMarkup(race)}</td><td class="numeric">${cleanlinessMarkup(race)}</td>`}
                    <td>${comparison}</td>
                    <td><button class="text-button" type="button" data-driver-race-id="${race.eventId}">Abrir</button></td>
                  </tr>`;
              }).join("")}
            </tbody>
          </table>
        </div>
      </section>`;
  } catch (error) {
    document.querySelector("#sessionDriverTitle").textContent =
      "No se pudo abrir el perfil";
    document.querySelector("#sessionDriverContent").innerHTML =
      `<p class="dialog-help">${escapeHtml(error.message)}</p>`;
  } finally {
    endActivity(activity);
  }
}

function miniLeagueMemberIdsForRace(eventId, scope = activeMiniLeagueScope) {
  const league = selectedMiniLeague(scope);
  if (!league) return [];
  return league.participants
    .filter((participant) =>
      participant.raceDetails.some((race) => Number(race.eventId) === Number(eventId))
    )
    .map((participant) => String(participant.iracingId));
}

async function openRaceDetail(eventId, highlightedDriverId = null, leagueMemberIds = []) {
  document.querySelector("#raceDetailTitle").textContent = "Cargando carrera…";
  document.querySelector("#raceDetailContent").innerHTML = dialogLoadingMarkup(
    "Preparando el resultado…",
    "Estamos calculando la clasificación, los duelos y las métricas de todos los pilotos."
  );
  raceDetailDialog.showModal();
  const activity = beginActivity(
    "Preparando el resultado de carrera…",
    "Calculando posiciones, comparativas, GridScore y limpieza."
  );
  try {
    const detail = await apiRequest(`/api/races/${eventId}`);
    const event = detail.event;
    const summary = detail.summary;
    const isAssetto = event.platform === "assetto-corsa";
    document.querySelector("#raceDetailKicker").textContent =
      `Semana ${event.week} · ${formatRaceDate(event.startTime)}`;
    document.querySelector("#raceDetailTitle").textContent =
      `${event.track} · ${event.layout || "Trazado principal"}`;
    const weather = event.weather || {};
    const fastest = summary.fastestLapTime;
    const leagueMemberSet = new Set(leagueMemberIds.map(String));
    const leaguePositionMap = new Map(
      detail.results
        .filter((result) => leagueMemberSet.has(String(result.iracingId)))
        .map((result, index) => [String(result.iracingId), index + 1])
    );
    const raceMeta = isAssetto
      ? [
          [event.aiDriversExcluded ? "Parrilla total" : "Parrilla", event.fieldSize],
          ...(event.aiDriversExcluded ? [["Pilotos visibles", detail.results.length]] : []),
          ["Vueltas", event.eventLapsComplete || "—"],
          ["Vuelta rápida", formatLapTime(fastest)],
          [metricHelp("Incidentes de parrilla", fieldContactExplanation("assetto-corsa", "esta carrera")), `${summary.totalIncidents}x`],
          [event.aiDriversExcluded ? "IA excluida" : "Finalistas", event.aiDriversExcluded ? event.aiDriversExcluded : `${summary.finishers} / ${event.fieldSize}`],
          ["Duración", event.sessionDurationMinutes ? `${event.sessionDurationMinutes} min` : "—"],
          ...(summary.ownerResult?.gridScore != null
            ? [
                [metricHelp("Tu GridScore", gridScoreFormulaExplanation("assetto-corsa")), formatDecimal(summary.ownerResult.gridScore)],
                [metricHelp("Tu limpieza", cleanlinessFormulaExplanation("assetto-corsa")), formatDecimal(summary.ownerResult.cleanlinessScore)]
              ]
            : []),
          ["Sesión", escapeHtml(event.sessionName || "Race")],
          ["Servidor", escapeHtml(event.serverName || "Local")],
        ]
      : [
          ["Split", `${event.splitNumber || "—"}${event.splitTotal ? ` / ${event.splitTotal}` : ""}`],
          ["SoF", formatInteger(event.strengthOfField)],
          ["Parrilla", event.fieldSize],
          ["Vueltas", event.eventLapsComplete || "—"],
          ["Vuelta rápida", formatLapTime(fastest)],
          [metricHelp("Inc. parrilla", fieldContactExplanation("iracing", "esta carrera")), `${summary.totalIncidents}x`],
          ["Cambios de líder", event.leadChanges ?? "—"],
          ["Temperatura", weather.temperature != null ? `${weather.temperature}°C` : "—"],
          ["Telemetría", event.telemetryFiles?.length ? "Disponible" : "—"],
          ...(summary.ownerResult?.gridScore != null
            ? [
                [metricHelp("Tu GridScore", gridScoreFormulaExplanation("iracing")), formatDecimal(summary.ownerResult.gridScore)],
                [metricHelp("Tu limpieza", cleanlinessFormulaExplanation("iracing")), formatDecimal(summary.ownerResult.cleanlinessScore)]
              ]
            : []),
        ];
    document.querySelector("#raceDetailContent").innerHTML = `
      <div class="track-detail-hero race-track-hero">
        <img src="${trackImageUrl(event.track, event.layout)}" alt="${escapeHtml(event.track)}">
        <div><small>${isAssetto ? "Historial de Content Manager" : "Resultado oficial"}</small><strong>${escapeHtml(event.track)}</strong><span>${escapeHtml(event.layout || "Trazado principal")} · ${escapeHtml(event.seriesName)}</span></div>
      </div>
      <div class="race-detail-meta">
        ${raceMeta.map(([label, value]) => `<article><small>${label}</small><strong>${value}</strong></article>`).join("")}
      </div>
      <div class="race-extra-line">
        ${isAssetto
          ? `<span>${escapeHtml(event.rawTrackId || event.track)}</span><span>Los incidentes proceden del contador guardado por Content Manager</span>`
          : `<span>Subsession ${escapeHtml(event.externalEventId)}</span>
             <span>${event.cautions || 0} cautions · ${event.cautionLaps || 0} vueltas bajo caution</span>
             <span>${weather.humidity != null ? `Humedad ${weather.humidity}%` : "Clima no disponible"}</span>
             ${event.telemetryFiles?.length ? `<span class="telemetry-race-note">${event.telemetryFiles.length} IBT · ${event.telemetryFiles[0].channelCount} canales · ${event.telemetryFiles[0].tickRate} Hz</span>` : ""}`}
      </div>
      ${leaguePositionMap.size ? `
        <div class="race-highlight-legend">
          <strong>${leaguePositionMap.size} miembros del campeonato en esta carrera</strong>
          <span><i class="owner-dot"></i>Piloto de referencia</span>
          ${highlightedDriverId != null ? '<span><i class="selected-dot"></i>Piloto consultado</span>' : ""}
          <span><i class="member-dot"></i>Otros miembros</span>
        </div>` : ""}
      <div class="table-wrap race-results-wrap">
        <table class="race-results-table">
          <thead>
            <tr>
              <th>Pos.</th><th>Piloto</th><th class="numeric">Salida</th><th class="numeric">± Pos.</th>
              <th class="numeric">Inc.</th><th class="numeric">Vueltas</th>${isAssetto ? '<th class="numeric">Válidas</th>' : '<th class="numeric">Lideradas</th>'}
              <th class="numeric">Mejor vuelta</th><th class="numeric">Media</th>${isAssetto ? `<th class="numeric">Consistencia</th><th class="numeric">${metricHelp("GridScore", gridScoreFormulaExplanation("assetto-corsa"))}</th><th class="numeric">${metricHelp("Limpieza", cleanlinessFormulaExplanation("assetto-corsa"))}</th><th>Neumáticos</th><th>Coche</th>` : `<th class="numeric">Intervalo</th><th class="numeric">iRating</th><th class="numeric">SR</th><th class="numeric">${metricHelp("GridScore", gridScoreFormulaExplanation("iracing"))}</th><th class="numeric">${metricHelp("Limpieza", cleanlinessFormulaExplanation("iracing"))}</th><th class="numeric">Puntos</th>`}<th>Estado</th>
            </tr>
          </thead>
          <tbody>
            ${detail.results.map((result) => {
              const resultId = String(result.iracingId);
              const isSelected = highlightedDriverId != null && resultId === String(highlightedDriverId) && !result.isOwner;
              const leaguePosition = leaguePositionMap.get(resultId);
              const isOtherMember = leaguePosition != null && !result.isOwner && !isSelected;
              return `
              <tr class="${result.isOwner ? "owner-result" : ""} ${isSelected ? "highlighted-rival" : ""} ${isOtherMember ? "league-member-result" : ""}">
                <td><span class="position ${result.finishPosition <= 3 ? "medal" : ""}">${result.finishPosition}</span></td>
                <td><div class="driver-cell"><i class="avatar ${result.color}">${escapeHtml(result.initials)}</i><span><strong><button class="race-driver-profile-link" type="button" data-race-driver-profile="${result.iracingId}" aria-label="Abrir perfil de ${escapeHtml(result.name)}">${escapeHtml(result.name)}</button>${isSelected ? ' <em class="race-rival-badge">RIVAL SELECCIONADO</em>' : ""}${leaguePosition != null ? ` <em class="race-league-badge">CAMPEONATO P${leaguePosition}</em>` : ""}</strong><small>${escapeHtml(result.countryCode || result.division || driverIdentityText(result.iracingId))}${result.carNumber ? ` · #${escapeHtml(result.carNumber)}` : ""}</small></span></div></td>
                <td class="numeric">${result.startPosition ?? "—"}</td>
                <td class="numeric">${result.positionChange != null ? positionChangeMarkup(result.positionChange) : "—"}</td>
                <td class="numeric">${result.incidents}x</td>
                <td class="numeric">${result.lapsComplete}</td>
                <td class="numeric">${isAssetto ? (result.validLapCount ?? "—") : (result.lapsLed ?? 0)}</td>
                <td class="numeric ${result.bestLapTime === fastest ? "fastest-lap" : ""}">${formatLapTime(result.bestLapTime)}</td>
                <td class="numeric">${formatLapTime(result.averageLapTime)}</td>
                ${isAssetto
                  ? `<td class="numeric" title="Desviación de sus tiempos de vuelta; cuanto menor, mayor regularidad">${result.lapTimeDeviation == null ? "—" : `±${result.lapTimeDeviation.toFixed(3)} s`}</td>
                     <td class="numeric">${gridScoreMarkup(result)}</td>
                     <td class="numeric">${cleanlinessMarkup(result)}</td>
                     <td>${result.tyreCompounds?.length ? escapeHtml(result.tyreCompounds.join(", ")) : "—"}</td>
                     <td>${escapeHtml(result.carName || "—")}</td>`
                  : `<td class="numeric">${result.intervalSeconds == null ? "—" : result.intervalSeconds === 0 ? "Líder" : `+${result.intervalSeconds.toFixed(3)}`}</td>
                     <td class="numeric">${result.newIRating ? `${formatInteger(result.newIRating)} <small>${formatSigned(result.iratingChange)}</small>` : formatSigned(result.iratingChange)}</td>
                     <td class="numeric">${result.newSafetyRating ? `${formatDecimal(result.newSafetyRating)} <small>${formatSigned(result.safetyRatingChange)}</small>` : formatSigned(result.safetyRatingChange)}</td>
                     <td class="numeric">${gridScoreMarkup(result)}</td>
                     <td class="numeric">${cleanlinessMarkup(result)}</td>
                     <td class="numeric">${result.championshipPoints ?? "—"}</td>`}
                <td>${escapeHtml(result.status || "—")}</td>
              </tr>`;
            }).join("")}
          </tbody>
        </table>
      </div>`;
  } catch (error) {
    document.querySelector("#raceDetailTitle").textContent = "No se pudo abrir la carrera";
    document.querySelector("#raceDetailContent").innerHTML = `<p class="dialog-help">${escapeHtml(error.message)}</p>`;
  } finally {
    endActivity(activity);
  }
}

function driverColorVariable(color) {
  const map = { orange: "accent", teal: "green", slate: "muted" };
  return map[color] || color;
}

function renderDrivers() {
  const minimum = requiredWeeks();
  const isAssetto = (appState.settings.platform || appState.league.platform) === "assetto-corsa";
  let officialPosition = 0;
  document.querySelector("#driverGrid").innerHTML = rankDrivers("weekly").map((driver) => {
    const eligible = driver.weeks >= minimum;
    if (eligible) officialPosition += 1;
    const position = eligible ? `#${officialPosition}` : "PROVISIONAL";
    const isOwner = String(driver.id) === String(appState.settings.ownerIracingId);
    const participation = appState.league.weeksCompleted
      ? Math.round((driver.weeks / appState.league.weeksCompleted) * 100)
      : 0;
    return `
      <article class="driver-card" style="--driver-color: var(--${driverColorVariable(driver.color)})" data-driver-profile-id="${driver.id}" tabindex="0" role="button" aria-label="Abrir perfil completo de ${escapeHtml(driver.name)}">
        <div class="driver-card-head">
          <i class="avatar ${driver.color}">${driver.initials}</i>
          <div><h3>${driver.name}</h3><p>${escapeHtml(driverIdentityText(driver.id))}</p></div>
          <span class="driver-rank ${eligible ? "" : "provisional"}" title="${eligible ? `Posición ${officialPosition} de la clasificación` : `Aún no alcanza el mínimo de ${minimum} semana${minimum === 1 ? "" : "s"}`}">${position}</span>
        </div>
        <div class="driver-card-stats">
          <div><small>Media semanal</small><strong>${driver.racesCount ? formatDecimal(driver.weekly) : "—"}</strong></div>
          <div><small>Carreras</small><strong>${driver.racesCount}</strong></div>
          <div><small>Coincidencias</small><strong>${isOwner ? "Referencia" : driver.meetingsWithOwner || 0}</strong></div>
          <div><small>Inc. media</small><strong>${driver.racesCount ? `${formatDecimal(driver.incidents)}x` : "—"}</strong></div>
          <div><small>Victorias</small><strong>${driver.wins}</strong></div>
          <div><small>Semanas</small><strong>${driver.weeks} / ${appState.league.weeksCompleted}</strong></div>
        </div>
        <div class="participation-bar" title="${participation}% de participación"><i style="width:${Math.min(participation, 100)}%"></i></div>
        <div class="driver-card-link">Ver perfil completo <svg viewBox="0 0 20 20"><path d="m7 4 6 6-6 6" /></svg></div>
      </article>`;
  }).join("");
}

function renderLeagueContext() {
  const isAssetto = (appState.settings.platform || appState.league.platform) === "assetto-corsa";
  const leagues = appState.leagues?.length ? appState.leagues : [appState.league];
  const theme = seriesTheme(appState.league.seriesName);
  document.documentElement.style.setProperty("--series-accent", theme.hex);
  document.documentElement.style.setProperty("--series-accent-rgb", theme.rgb);
  document.querySelector(".league-dot").textContent = seriesInitials(appState.league.seriesName);
  document.querySelector("#sidebarSeriesName").textContent = appState.league.seriesName;
  document.querySelector("#sidebarSeasonName").textContent =
    `${shortSeason(appState.league.season)} · ${appState.league.isCurrent ? "Actual" : "Histórica"}`;
  document.querySelector("#topbarSeriesName").textContent = appState.league.seriesName;
  document.querySelector("#topbarSeasonName").textContent =
    `${shortSeason(appState.league.season)} · ${appState.league.isCurrent ? "Temporada actual" : "Histórica"}`;
  const leaguesBySeries = new Map();
  leagues.forEach((league) => {
    if (!leaguesBySeries.has(league.seriesName)) {
      leaguesBySeries.set(league.seriesName, []);
    }
    leaguesBySeries.get(league.seriesName).push(league);
  });
  document.querySelector("#leagueMenuCount").textContent =
    `${leaguesBySeries.size} serie${leaguesBySeries.size === 1 ? "" : "s"} · ${leagues.length} temporada${leagues.length === 1 ? "" : "s"}`;
  document.querySelector("#leagueMenuList").innerHTML = Array.from(leaguesBySeries.entries())
    .map(([seriesName, seriesLeagues]) => {
      const itemTheme = seriesTheme(seriesName);
      const containsSelected = seriesLeagues.some((league) => league.id === appState.league.id);
      const containsCurrent = seriesLeagues.some((league) => league.isCurrent);
      const totalRaces = seriesLeagues.reduce((total, league) => total + (league.raceCount || 0), 0);
      return `
        <details class="league-series-group ${containsSelected ? "selected" : ""}" data-context-key="${escapeHtml(`league:${seriesName}`)}" style="--item-accent:${itemTheme.hex}" ${containsSelected ? "open" : ""}>
          <summary class="league-series-summary">
            <span class="league-menu-icon">${seriesInitials(seriesName)}</span>
            <span class="league-menu-copy">
              <strong>${escapeHtml(seriesName)}</strong>
              <small>${seriesLeagues.length} temporada${seriesLeagues.length === 1 ? "" : "s"} · ${totalRaces} carrera${totalRaces === 1 ? "" : "s"}</small>
            </span>
            <span class="league-series-status">
              ${containsCurrent ? '<em>ACTUAL</em>' : ""}
              <svg viewBox="0 0 20 20"><path d="m6 8 4 4 4-4" /></svg>
            </span>
          </summary>
          <div class="league-season-list">
            ${seriesLeagues.map((league) => `
              <button class="league-season-item ${league.id === appState.league.id ? "selected" : ""}" type="button" data-menu-league="${league.id}">
                <i></i>
                <span class="league-menu-copy">
                  <strong>${escapeHtml(shortSeason(league.season))}</strong>
                  <small>${league.raceCount || 0} carreras · ${league.driverCount || 0} pilotos</small>
                </span>
                <span class="league-menu-tags">
                  ${league.isCurrent ? '<span class="current">ACTUAL</span>' : '<span>HIST.</span>'}
                  ${league.id === appState.league.id ? "<span>ABIERTA</span>" : ""}
                </span>
              </button>`).join("")}
          </div>
        </details>`;
    }).join("");
  document.title = `GridScope — ${appState.league.seriesName}`;
  const seasonBadge = document.querySelector("#seasonStatusBadge");
  seasonBadge.classList.toggle("historical", !appState.league.isCurrent);
  seasonBadge.innerHTML = appState.league.isCurrent
    ? `<span></span> ${isAssetto ? "AÑO ACTUAL" : "TEMPORADA ACTUAL"}`
    : `<span></span> ${isAssetto ? "AÑO HISTÓRICO" : "TEMPORADA HISTÓRICA"}`;

  document.querySelector("#heroSeries").textContent = appState.league.seriesName;
  const heroSeriesLogo = document.querySelector("#heroSeriesLogo");
  heroSeriesLogo.src = seriesLogoUrl(
    appState.league.seriesLogo,
    appState.league.seriesName
  );
  heroSeriesLogo.alt = `Logotipo de ${appState.league.seriesName}`;
  document.querySelector("#heroCar").textContent = `${appState.league.car} · ${appState.league.setupType}`;
  document.querySelector("#heroSeason").textContent = shortSeason(appState.league.season);
  document.querySelector("#roundsSeason").textContent = appState.league.season;
  document.querySelector("#heroPeriodLabel").textContent =
    appState.league.isCurrent ? (isAssetto ? "Semana más reciente" : "Jornada actual") : "Carreras importadas";
  document.querySelector("#heroWeek").innerHTML = appState.league.isCurrent
    ? `${String(appState.league.weeksCompleted).padStart(2, "0")} <em>/ ${appState.league.totalWeeks}</em>`
    : `${String(appState.storage.raceCount).padStart(2, "0")} <em>registradas</em>`;
  document.querySelector("#heroDrivers").textContent = String(appState.drivers.length).padStart(2, "0");

  const latestRound = appState.rounds.at(-1);
  document.querySelector(".hero").style.setProperty(
    "--hero-image",
    `url("${trackImageUrl(latestRound?.track || appState.league.seriesName, latestRound?.layout)}")`
  );
  const heroTrackMap = document.querySelector("#heroTrackMap");
  heroTrackMap.src = trackMapUrl(latestRound?.trackId, latestRound?.track, latestRound?.layout);
  heroTrackMap.alt = latestRound
    ? `Trazado oficial de ${latestRound.track}, ${latestRound.layout || "configuración principal"}`
    : "Trazado de circuito";
  document.querySelector("#heroTrack").textContent = latestRound?.track || "Sin resultados";
  document.querySelector("#heroTrackDetail").textContent = latestRound
    ? `${latestRound.layout || "Trazado principal"} · Semana ${latestRound.week}`
    : "Importa el primer JSON de esta serie";

  const ranked = rankDrivers("weekly").filter((driver) => driver.racesCount > 0);
  const leader = ranked[0];
  const cleanest = ranked.slice().sort((a, b) => a.incidents - b.incidents)[0];
  const winner = ranked.slice().sort((a, b) => b.wins - a.wins || a.weekly - b.weekly)[0];
  const sofRounds = appState.rounds.filter((round) => round.sof > 0);
  const averageSof = sofRounds.length
    ? Math.round(sofRounds.reduce((total, round) => total + round.sof, 0) / sofRounds.length)
    : 0;

  document.querySelector("#leaderLabel").textContent =
    appState.league.isCurrent ? "Líder actual" : "Líder de la temporada";
  document.querySelector("#leaderName").textContent = leader?.name || "Sin clasificación";
  document.querySelector("#leaderDetail").textContent = leader ? `${formatDecimal(leader.weekly)} pos. media` : "Sin carreras";
  document.querySelector("#leaderTrend").textContent = leader ? `${leader.weeks} sem.` : "—";
  document.querySelector("#cleanName").textContent = cleanest?.name || "Sin datos";
  document.querySelector("#cleanDetail").textContent = cleanest ? `${formatDecimal(cleanest.incidents)}x por semana` : "Sin carreras";
  document.querySelector("#cleanTrend").textContent = cleanest ? `${cleanest.racesCount} carreras` : "—";
  document.querySelector("#winnerName").textContent = winner?.name || "Sin datos";
  document.querySelector("#winnerDetail").textContent = winner
    ? `${winner.wins} victoria${winner.wins === 1 ? "" : "s"}`
    : "Sin carreras";
  document.querySelector("#winnerTrend").textContent = winner ? `${winner.racesCount} carreras` : "—";
  document.querySelector("#sofValue").textContent = isAssetto
    ? formatInteger(appState.drivers.length)
    : averageSof ? formatInteger(averageSof) : "—";
  document.querySelector("#sofDetail").textContent = isAssetto
    ? `${appState.storage.raceCount} carrera${appState.storage.raceCount === 1 ? "" : "s"} guardada${appState.storage.raceCount === 1 ? "" : "s"}`
    : `${appState.storage.raceCount} carrera${appState.storage.raceCount === 1 ? "" : "s"} analizada${appState.storage.raceCount === 1 ? "" : "s"}`;
  document.querySelector("#sofTrend").textContent = isAssetto
    ? `${appState.rounds.length} semanas`
    : `${sofRounds.length} jornadas`;

  const seasonParts = shortSeason(appState.league.season).split(" ");
  document.querySelector("#archiveYear").textContent = seasonParts[0] || "—";
  document.querySelector("#archiveSeason").textContent = seasonParts[1] || "";
  document.querySelector("#archiveSeries").textContent = appState.league.seriesName;
  document.querySelector("#archiveSummary").textContent =
    `${appState.league.weeksCompleted} de ${appState.league.totalWeeks} jornadas · ` +
    `${appState.storage.raceCount} carreras · ${appState.drivers.length} pilotos`;
}

function renderOwnerSeasonOverview() {
  const stats = document.querySelector("#ownerSeasonStats");
  const tracks = document.querySelector("#ownerTrackBreakdown");
  const races = document.querySelector("#ownerSeasonRaces");
  const isAssetto = (appState.settings.platform || appState.league.platform) === "assetto-corsa";
  const racesHead = document.querySelector(".owner-season-races-table thead");
  racesHead.innerHTML = `<tr>
    <th>Carrera</th>${isAssetto ? "" : '<th class="numeric">Split</th><th class="numeric">SoF</th>'}
    <th class="numeric">Salida</th><th class="numeric">Meta</th><th class="numeric">± Pos.</th>
    <th class="numeric">Tus inc.</th>
    ${isAssetto ? `<th class="numeric">${metricHelp("GridScore", gridScoreFormulaExplanation())}</th><th class="numeric">${metricHelp("Limpieza", cleanlinessFormulaExplanation())}</th>` : `<th class="numeric">iRating</th><th class="numeric">SR</th><th class="numeric">${metricHelp("GridScore", gridScoreFormulaExplanation())}</th><th class="numeric">${metricHelp("Limpieza", cleanlinessFormulaExplanation())}</th>`}<th></th>
  </tr>`;
  document.querySelector("#ownerSeasonKicker").textContent =
    appState.league.isCurrent ? "Piloto de referencia · Temporada actual" : "Piloto de referencia · Temporada histórica";
  if (!ownerSeasonAnalysis) {
    document.querySelector("#ownerSeasonTitle").textContent =
      "Sin carreras del piloto de referencia";
    document.querySelector("#ownerSeasonDescription").textContent =
      "La temporada contiene resultados importados, pero el piloto configurado no aparece en ellos.";
    stats.innerHTML = '<article><small>Carreras</small><strong>0</strong><span>sin resultados personales</span></article>';
    tracks.innerHTML = "";
    races.innerHTML = '<tr><td colspan="10">No hay carreras del piloto de referencia en esta temporada.</td></tr>';
    document.querySelector("#ownerProgressContent").innerHTML =
      '<p class="session-empty">No hay resultados personales para calcular la progresión.</p>';
    document.querySelector("#ownerLatestTitle").textContent = "Sin carreras personales";
    document.querySelector("#ownerLatestWeek").textContent = "—";
    document.querySelector("#ownerLatestContent").innerHTML =
      '<p class="session-empty">No existe un último resultado para el piloto de referencia.</p>';
    return;
  }

  const summary = ownerSeasonAnalysis.summary;
  const gridRating = summary.gridRating;
  const driver = ownerSeasonAnalysis.driver;
  document.querySelector("#ownerSeasonTitle").textContent =
    `${driver.name} · ${shortSeason(ownerSeasonAnalysis.season)}`;
  document.querySelector("#ownerSeasonDescription").textContent =
    `${summary.races} carrera${summary.races === 1 ? "" : "s"} en ${summary.weeks} semana${summary.weeks === 1 ? "" : "s"} · ${ownerSeasonAnalysis.seriesName}`;
  stats.innerHTML = `
    <article><small>Carreras</small><strong>${summary.races}</strong><span>${summary.weeks} semanas registradas</span></article>
    <article><small>Posición media</small><strong>P${formatDecimal(summary.averageFinish)}</strong><span>mejor P${summary.bestFinish} · peor P${summary.worstFinish}</span></article>
    <article><small>Top 5 / Top 10</small><strong>${summary.topFive} / ${summary.topTen}</strong><span>${summary.wins} victoria${summary.wins === 1 ? "" : "s"}</span></article>
    <article><small>Salida media</small><strong>${summary.averageStart == null ? "—" : `P${formatDecimal(summary.averageStart)}`}</strong><span>${formatSigned(summary.positionsGained, " posiciones")}</span></article>
    <article><small>${metricHelp("Tus incidentes", personalContactExplanation(isAssetto ? "assetto-corsa" : "iracing"))}</small><strong>${summary.totalIncidents}x</strong><span>${formatDecimal(summary.averageIncidents)}x de media personal por carrera</span></article>
    <article><small>Vueltas</small><strong>${formatInteger(summary.lapsComplete)}</strong><span>${formatInteger(summary.lapsLed)} lideradas</span></article>
    <article><small>${isAssetto ? metricHelp("GridScore", gridRatingExplanation()) : "SoF medio"}</small><strong>${isAssetto ? gridRating ? formatDecimal(gridRating.gridScore) : "—" : summary.averageSof ? formatInteger(summary.averageSof) : "—"}</strong><span>${isAssetto && gridRating ? `${formatDecimal(gridRating.gridScoreStart)} → ${formatDecimal(gridRating.gridScore)} · ${formatSigned(gridRating.gridScoreChange)}` : isAssetto ? "sin valoración disponible" : "nivel medio de las parrillas"}</span></article>
    <article><small>${isAssetto ? metricHelp("Limpieza", cleanlinessRatingExplanation()) : "iRating"}</small><strong>${isAssetto ? gridRating ? formatDecimal(gridRating.cleanlinessScore) : "—" : summary.iratingEnd == null ? "—" : formatInteger(summary.iratingEnd)}</strong><span>${isAssetto && gridRating ? `${formatDecimal(gridRating.cleanlinessStart)} → ${formatDecimal(gridRating.cleanlinessScore)} · ${formatSigned(gridRating.cleanlinessChange)}` : isAssetto ? "sin valoración disponible" : summary.iratingStart == null || summary.iratingEnd == null ? "evolución no disponible" : `${formatInteger(summary.iratingStart)} → ${formatInteger(summary.iratingEnd)} · ${formatSigned(summary.iratingChange)}`}</span></article>
    <article><small>${isAssetto ? metricHelp("Confianza", confidenceExplanation()) : "Safety Rating"}</small><strong>${isAssetto ? gridRating?.confidence || "—" : summary.safetyRatingEnd == null ? "—" : formatDecimal(summary.safetyRatingEnd)}</strong><span>${isAssetto && gridRating ? `${gridRating.ratedRaces} carreras · ${formatInteger(Math.round(gridRating.drivingMinutes))} min` : isAssetto ? "sin valoración disponible" : summary.safetyRatingStart == null || summary.safetyRatingEnd == null ? "evolución no disponible" : `${formatDecimal(summary.safetyRatingStart)} → ${formatDecimal(summary.safetyRatingEnd)} · ${formatSigned(summary.safetyRatingChange)}`}</span></article>
    ${isAssetto ? "" : `
      <article><small>${metricHelp("GridScore", gridRatingExplanation())}</small><strong>${gridRating ? formatDecimal(gridRating.gridScore) : "—"}</strong><span>${gridRating ? `${formatDecimal(gridRating.gridScoreStart)} → ${formatDecimal(gridRating.gridScore)} · ${formatSigned(gridRating.gridScoreChange)}` : "sin valoración disponible"}</span></article>
      <article><small>${metricHelp("Limpieza GridScope", cleanlinessRatingExplanation())}</small><strong>${gridRating ? formatDecimal(gridRating.cleanlinessScore) : "—"}</strong><span>${gridRating ? `${formatDecimal(gridRating.cleanlinessStart)} → ${formatDecimal(gridRating.cleanlinessScore)} · ${formatSigned(gridRating.cleanlinessChange)}` : "sin valoración disponible"}</span></article>
      <article><small>${metricHelp("Confianza GridScope", confidenceExplanation())}</small><strong>${gridRating?.confidence || "—"}</strong><span>${gridRating ? `${gridRating.ratedRaces} carreras · ${formatInteger(Math.round(gridRating.drivingMinutes))} min` : "sin valoración disponible"}</span></article>
    `}
    <article><small>Mejor vuelta</small><strong>${formatLapTime(summary.bestLapTime)}</strong><span>mejor registro disponible</span></article>
  `;
  tracks.innerHTML = ownerSeasonAnalysis.tracks.length
    ? `
      <div class="owner-track-heading"><small>Análisis por circuito</small><strong>${ownerSeasonAnalysis.tracks.length} configuraciones · pulsa una para ampliar</strong></div>
      <div class="owner-track-card-grid">
        ${ownerSeasonAnalysis.tracks.map((track, index) => `
          <button class="owner-track-card" type="button" data-owner-track-index="${index}" aria-label="Abrir estadísticas de ${escapeHtml(track.track)}, ${escapeHtml(track.layout || "Trazado principal")}">
            <div class="owner-track-card-visual">
              <img class="owner-track-photo" src="${trackImageUrl(track.track, track.layout)}" alt="" loading="lazy">
              <span class="owner-track-photo-shade"></span>
              <img class="owner-track-map" src="${trackMapUrl(0, track.track, track.layout)}" alt="" loading="lazy">
              <span class="owner-track-race-count">${track.races} carrera${track.races === 1 ? "" : "s"}</span>
            </div>
            <div class="owner-track-card-copy">
              <div><strong>${escapeHtml(track.track)}</strong><small>${escapeHtml(track.layout || "Trazado principal")}</small></div>
              <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m7 4 6 6-6 6" /></svg>
            </div>
            <div class="owner-track-card-stats">
              <span><small>Media</small><strong>P${formatDecimal(track.averageFinish)}</strong></span>
              <span><small>± Pos.</small><strong>${formatSigned(track.positionsGained)}</strong></span>
              <span><small>${isAssetto ? "GridScore" : "SoF"}</small><strong>${isAssetto ? track.averageGridScore == null ? "—" : formatDecimal(track.averageGridScore) : track.averageSof ? formatInteger(track.averageSof) : "—"}</strong></span>
              <span><small>Inc./carrera</small><strong>${formatDecimal(track.averageIncidents)}x</strong></span>
            </div>
          </button>`).join("")}
      </div>`
    : "";
  races.innerHTML = ownerSeasonAnalysis.races.map((race) => `
    <tr data-owner-season-race="${race.eventId}" tabindex="0" role="button">
      <td><strong>${escapeHtml(race.track)}</strong><small class="table-subline">${formatRaceDate(race.startTime)} · ${escapeHtml(race.layout || "Trazado principal")}</small></td>
      ${isAssetto ? "" : `<td class="numeric">${race.splitNumber || "—"}${race.splitTotal ? ` / ${race.splitTotal}` : ""}</td>
      <td class="numeric">${race.strengthOfField ? formatInteger(race.strengthOfField) : "—"}</td>`}
      <td class="numeric">${race.startPosition == null ? "—" : `P${race.startPosition}`}</td>
      <td class="numeric metric-strong">P${race.finishPosition}</td>
      <td class="numeric">${race.positionChange == null ? "—" : positionChangeMarkup(race.positionChange)}</td>
      <td class="numeric">${race.incidents}x</td>
      ${isAssetto ? `<td class="numeric">${gridScoreMarkup(race)}</td><td class="numeric">${cleanlinessMarkup(race)}</td>` : `<td class="numeric">${race.newIRating == null ? "—" : `${formatInteger(race.newIRating)} <small>${formatSigned(race.iratingChange)}</small>`}</td>
      <td class="numeric">${race.newSafetyRating == null ? "—" : `${formatDecimal(race.newSafetyRating)} <small>${formatSigned(race.safetyRatingChange)}</small>`}</td>
      <td class="numeric">${gridScoreMarkup(race)}</td><td class="numeric">${cleanlinessMarkup(race)}</td>`}
      <td><button class="text-button" type="button" data-owner-season-race="${race.eventId}">Abrir</button></td>
    </tr>`).join("");

  const chronologicalRaces = ownerSeasonAnalysis.races.slice().reverse();
  const topFiveRate = summary.races ? summary.topFive / summary.races * 100 : 0;
  document.querySelector("#ownerProgressContent").innerHTML = `
    <div class="owner-progress-summary">
      <span><small>Top 5</small><strong>${formatDecimal(topFiveRate)}%</strong></span>
      <span><small>Posiciones</small><strong>${formatSigned(summary.positionsGained)}</strong></span>
      <span><small>Inc./carrera</small><strong>${formatDecimal(summary.averageIncidents)}x</strong></span>
    </div>
    <div class="owner-result-strip">
      ${chronologicalRaces.map((race, index) => `
        <button type="button" data-overview-owner-race="${race.eventId}" class="${race.finishPosition <= 5 ? "top-five" : race.positionChange > 0 ? "gained" : ""}" aria-label="Abrir carrera ${index + 1}, posición ${race.finishPosition}">
          <small>C${index + 1}</small>
          <strong>P${race.finishPosition}</strong>
          <span>${race.positionChange == null ? "—" : formatSigned(race.positionChange)}</span>
        </button>`).join("")}
    </div>
  `;

  const latest = ownerSeasonAnalysis.races[0];
  document.querySelector("#ownerLatestTitle").textContent = latest.track;
  document.querySelector("#ownerLatestWeek").textContent = `S${String(latest.week).padStart(2, "0")}`;
  document.querySelector("#ownerLatestContent").innerHTML = `
    <div class="owner-latest-meta">${formatRaceDate(latest.startTime)} · ${escapeHtml(latest.layout || "Trazado principal")}</div>
    <div class="owner-latest-grid">
      <span><small>Salida</small><strong>${latest.startPosition == null ? "—" : `P${latest.startPosition}`}</strong></span>
      <span><small>Meta</small><strong>P${latest.finishPosition}</strong></span>
      <span><small>Tus incidentes</small><strong>${latest.incidents}x</strong></span>
      <span><small>${isAssetto ? "GridScore" : "SoF"}</small><strong>${isAssetto ? latest.gridScore == null ? "—" : formatDecimal(latest.gridScore) : latest.strengthOfField ? formatInteger(latest.strengthOfField) : "—"}</strong></span>
      <span><small>${isAssetto ? "Limpieza" : "iRating"}</small><strong>${isAssetto ? latest.cleanlinessScore == null ? "—" : formatDecimal(latest.cleanlinessScore) : latest.newIRating == null ? "—" : `${formatInteger(latest.newIRating)} ${formatSigned(latest.iratingChange)}`}</strong></span>
      <span><small>${isAssetto ? "Confianza" : "Safety Rating"}</small><strong>${isAssetto ? gridRating?.confidence || "—" : latest.newSafetyRating == null ? "—" : `${formatDecimal(latest.newSafetyRating)} ${formatSigned(latest.safetyRatingChange)}`}</strong></span>
      ${isAssetto ? "" : `<span><small>GridScore</small><strong>${latest.gridScore == null ? "—" : formatDecimal(latest.gridScore)}</strong></span>
      <span><small>Limpieza GridScope</small><strong>${latest.cleanlinessScore == null ? "—" : formatDecimal(latest.cleanlinessScore)}</strong></span>`}
    </div>
    <button class="text-button owner-latest-open" type="button" data-overview-owner-race="${latest.eventId}">Abrir resultado completo <svg viewBox="0 0 20 20"><path d="m7 4 6 6-6 6" /></svg></button>
  `;
}

function openOwnerTrackDetail(trackIndex) {
  const track = ownerSeasonAnalysis?.tracks?.[Number(trackIndex)];
  if (!track) return;
  const isAssetto = (appState.settings.platform || appState.league.platform) === "assetto-corsa";
  const trackRaces = ownerSeasonAnalysis.races.filter(
    (race) =>
      race.track === track.track
      && String(race.layout || "") === String(track.layout || "")
  );
  const duelTotal = track.duelWins + track.duelLosses + track.duelTies;
  const duelRate = duelTotal
    ? (track.duelWins + track.duelTies * 0.5) / duelTotal * 100
    : null;
  delete sessionDriverDialog.dataset.miniLeagueScope;
  sessionDriverDialog.dataset.driverId = ownerSeasonAnalysis.driver.iracingId;
  document.querySelector("#sessionDriverKicker").textContent =
    `${shortSeason(ownerSeasonAnalysis.season)} · Estadísticas por circuito`;
  document.querySelector("#sessionDriverTitle").textContent =
    `${track.track} · ${track.layout || "Trazado principal"}`;
  document.querySelector("#sessionDriverContent").innerHTML = `
    <div class="owner-track-detail-hero">
      <img class="owner-track-detail-photo" src="${trackImageUrl(track.track, track.layout)}" alt="${escapeHtml(track.track)}">
      <span class="owner-track-detail-shade"></span>
      <div>
        <p class="eyebrow">Tu rendimiento en este trazado</p>
        <h3>${escapeHtml(track.track)}</h3>
        <span>${escapeHtml(track.layout || "Trazado principal")} · ${track.races} carrera${track.races === 1 ? "" : "s"} · ${formatRaceDate(track.firstStart)} → ${formatRaceDate(track.lastStart)}</span>
      </div>
      <img class="owner-track-detail-map" src="${trackMapUrl(0, track.track, track.layout)}" alt="Mapa de ${escapeHtml(track.track)}">
    </div>

    <div class="driver-season-stats owner-track-detail-stats">
      <article><small>Carreras</small><strong>${track.races}</strong><span>${track.uniqueRivals} rivales distintos</span></article>
      <article><small>Posición media</small><strong>P${formatDecimal(track.averageFinish)}</strong><span>mejor P${track.bestFinish} · peor P${track.worstFinish}</span></article>
      <article><small>Salida media</small><strong>${track.averageStart == null ? "—" : `P${formatDecimal(track.averageStart)}`}</strong><span>${formatSigned(track.positionsGained, " posiciones")}</span></article>
      <article><small>Top 5 / Top 10</small><strong>${track.topFive} / ${track.topTen}</strong><span>${track.wins} victoria${track.wins === 1 ? "" : "s"}</span></article>
      <article><small>Incidentes</small><strong>${track.totalIncidents}x</strong><span>${formatDecimal(track.averageIncidents)}x por carrera</span></article>
      <article><small>Vueltas</small><strong>${formatInteger(track.lapsComplete)}</strong><span>${formatInteger(track.validLaps)} válidas · ${formatInteger(track.lapsLed)} lideradas</span></article>
      <article><small>Mejor vuelta</small><strong>${formatLapTime(track.bestLapTime)}</strong><span>media ${formatLapTime(track.averageLapTime)}</span></article>
      ${isAssetto ? `<article><small>Vuelta teórica</small><strong>${formatLapTime(track.theoreticalBestLapTime)}</strong><span>mejores sectores disponibles</span></article>` : ""}
      <article><small>${metricHelp("GridScore medio", gridScoreFormulaExplanation(isAssetto ? "assetto-corsa" : "iracing"))}</small><strong>${track.averageGridScore == null ? "—" : formatDecimal(track.averageGridScore)}</strong><span>${track.bestGridScore == null ? "sin datos" : `mejor ${formatDecimal(track.bestGridScore)}`}</span></article>
      <article><small>Rendimiento</small><strong>${track.averagePerformance == null ? "—" : formatDecimal(track.averagePerformance)}</strong><span>componente deportivo del GridScore</span></article>
      <article><small>${metricHelp("Limpieza media", cleanlinessFormulaExplanation(isAssetto ? "assetto-corsa" : "iracing"))}</small><strong>${track.averageCleanliness == null ? "—" : formatDecimal(track.averageCleanliness)}</strong><span>${track.drivingMinutes ? `${formatInteger(Math.round(track.drivingMinutes))} min analizados` : "duración no disponible"}</span></article>
      ${isAssetto ? `<article><small>Consistencia</small><strong>${track.averageConsistency == null ? "—" : formatDecimal(track.averageConsistency)}</strong><span>regularidad de vueltas disponible</span></article>` : `<article><small>SoF medio</small><strong>${track.averageSof ? formatInteger(track.averageSof) : "—"}</strong><span>nivel medio de las parrillas</span></article>`}
      <article><small>Tamaño de parrilla</small><strong>${track.averageFieldSize == null ? "—" : formatDecimal(track.averageFieldSize)}</strong><span>pilotos de media</span></article>
      <article><small>Duelos de parrilla</small><strong>${track.duelWins}-${track.duelLosses}${track.duelTies ? `-${track.duelTies}` : ""}</strong><span>${duelRate == null ? "sin comparaciones" : `${formatDecimal(duelRate)}% superados`}</span></article>
      ${isAssetto ? `<article><small>Coches</small><strong>${track.cars.length || "—"}</strong><span>${track.cars.length ? track.cars.map(escapeHtml).join(" · ") : "no disponibles"}</span></article>
      <article><small>Neumáticos</small><strong>${track.tyreCompounds.length || "—"}</strong><span>${track.tyreCompounds.length ? track.tyreCompounds.map(escapeHtml).join(" · ") : "no disponibles"}</span></article>` : ""}
    </div>

    <section class="driver-profile-section">
      <div class="session-block-heading">
        <div><p class="eyebrow">Historial del trazado</p><h3>Tus carreras en ${escapeHtml(track.track)}</h3></div>
        <span>Pulsa cualquier fila para abrir el resultado completo</span>
      </div>
      <div class="table-wrap season-driver-races-wrap">
        <table class="session-driver-races-table owner-track-races-table">
          <thead><tr>
            <th>Carrera</th><th class="numeric">Salida</th><th class="numeric">Meta</th><th class="numeric">± Pos.</th>
            <th class="numeric">Inc.</th><th class="numeric">Vueltas</th><th class="numeric">Mejor vuelta</th>
            ${isAssetto ? `<th class="numeric">${metricHelp("GridScore", gridScoreFormulaExplanation("assetto-corsa"))}</th><th class="numeric">${metricHelp("Limpieza", cleanlinessFormulaExplanation("assetto-corsa"))}</th>` : `<th class="numeric">SoF</th><th class="numeric">iRating</th><th class="numeric">SR</th><th class="numeric">${metricHelp("GridScore", gridScoreFormulaExplanation("iracing"))}</th><th class="numeric">${metricHelp("Limpieza", cleanlinessFormulaExplanation("iracing"))}</th>`}<th></th>
          </tr></thead>
          <tbody>${trackRaces.map((race) => `
            <tr data-driver-race-id="${race.eventId}" tabindex="0" role="button">
              <td><strong>${formatRaceDate(race.startTime)}</strong><small class="table-subline">Semana ${race.week} · ${escapeHtml(race.status || "Resultado guardado")}</small></td>
              <td class="numeric">${race.startPosition == null ? "—" : `P${race.startPosition}`}</td>
              <td class="numeric metric-strong">P${race.finishPosition}</td>
              <td class="numeric">${race.positionChange == null ? "—" : positionChangeMarkup(race.positionChange)}</td>
              <td class="numeric">${race.incidents}x</td>
              <td class="numeric">${race.lapsComplete}</td>
              <td class="numeric">${formatLapTime(race.bestLapTime)}</td>
              ${isAssetto ? `<td class="numeric">${gridScoreMarkup(race)}</td><td class="numeric">${cleanlinessMarkup(race)}</td>` : `<td class="numeric">${race.strengthOfField ? formatInteger(race.strengthOfField) : "—"}</td><td class="numeric">${race.newIRating == null ? "—" : formatInteger(race.newIRating)}</td><td class="numeric">${race.newSafetyRating == null ? "—" : formatDecimal(race.newSafetyRating)}</td><td class="numeric">${gridScoreMarkup(race)}</td><td class="numeric">${cleanlinessMarkup(race)}</td>`}
              <td><button class="text-button" type="button" data-driver-race-id="${race.eventId}">Abrir</button></td>
            </tr>`).join("")}</tbody>
        </table>
      </div>
    </section>`;
  showDetailDialogOnTop(sessionDriverDialog);
  refreshMetricHelp(document.querySelector("#sessionDriverContent"));
}

function renderGlobalOverview() {
  const totals = globalAnalysis.totals || {};
  const isAssetto = (appState.settings?.platform || appState.league?.platform) === "assetto-corsa";
  document.querySelector("#globalStatGrid").innerHTML = `
    <article><small>Temporadas</small><strong>${totals.seasons || 0}</strong><span>series y temporadas</span></article>
    <article><small>Carreras</small><strong>${totals.races || 0}</strong><span>resultados completos</span></article>
    <article><small>Pilotos únicos</small><strong>${totals.drivers || 0}</strong><span>en todo el archivo</span></article>
    <article><small>Circuitos</small><strong>${totals.tracks || 0}</strong><span>trazados distintos</span></article>
    <article><small>SoF medio</small><strong>${totals.averageSof ? formatInteger(totals.averageSof) : "—"}</strong><span>todas las carreras</span></article>
    <article><small>${metricHelp("Incidentes de parrilla", fieldContactExplanation(isAssetto ? "assetto-corsa" : "iracing", "todo el archivo guardado"))}</small><strong>${formatInteger(totals.totalIncidents || 0)}x</strong><span>${formatDecimal(totals.averageIncidents || 0)}x por piloto y carrera</span></article>
  `;
  const container = document.querySelector("#seasonOverviewGrid");
  if (!globalAnalysis.seasons.length) {
    container.innerHTML = '<article class="empty-archive"><h3>Sin temporadas importadas</h3></article>';
    return;
  }
  const seasonCard = (season) => `
    <button class="season-overview-card ${season.selected ? "selected" : ""}" type="button" data-overview-league="${season.id}" style="--season-accent:${seriesTheme(season.seriesName).hex}">
      <div class="season-card-head">
        <span class="season-status ${season.isCurrent ? "current" : "historical"}">${season.isCurrent ? "ACTUAL" : "HISTÓRICA"}</span>
        ${season.selected ? '<span class="season-selected">SELECCIONADA</span>' : ""}
      </div>
      <p class="eyebrow">${escapeHtml(shortSeason(season.season))}</p>
      <h3>${escapeHtml(season.seriesName)}</h3>
      <span class="season-car">${escapeHtml(season.car)} · ${escapeHtml(season.setupType)}</span>
      <div class="season-card-stats">
        <div><small>Carreras</small><strong>${season.raceCount}</strong></div>
        <div><small>Pilotos</small><strong>${season.driverCount}</strong></div>
        <div><small>Circuitos</small><strong>${season.trackCount}</strong></div>
        <div><small>SoF</small><strong>${season.averageSof ? formatInteger(season.averageSof) : "—"}</strong></div>
      </div>
      <div class="season-owner-summary">
        <span>Tus carreras <strong>${season.ownerRaces}</strong></span>
        <span>Media <strong>${season.ownerAverageFinish ? formatDecimal(season.ownerAverageFinish) : "—"}</strong></span>
        <span>Mejor <strong>${season.ownerBestFinish ? `P${season.ownerBestFinish}` : "—"}</strong></span>
        <span>iRating <strong>${formatSigned(season.ownerIRatingChange)}</strong></span>
      </div>
      <footer>
        <span>${season.weeksCompleted} / ${season.totalWeeks} semanas · ${formatDecimal(season.averageIncidents)}x por piloto y carrera</span>
        <strong>Abrir temporada →</strong>
      </footer>
    </button>`;
  const groupedSeries = new Map();
  globalAnalysis.seasons.forEach((season) => {
    if (!groupedSeries.has(season.seriesName)) groupedSeries.set(season.seriesName, []);
    groupedSeries.get(season.seriesName).push(season);
  });
  const seriesEntries = Array.from(groupedSeries.entries()).sort(([nameA, seasonsA], [nameB, seasonsB]) => {
    const selectedDifference = Number(seasonsB.some((season) => season.selected)) -
      Number(seasonsA.some((season) => season.selected));
    return selectedDifference || nameA.localeCompare(nameB, "es");
  });
  container.innerHTML = seriesEntries.map(([seriesName, seasons], seriesIndex) => {
    const yearGroups = new Map();
    seasons.forEach((season) => {
      const yearMatch = String(season.season || "").match(/\b(20\d{2})\b/);
      const year = yearMatch ? yearMatch[1] : "Sin año";
      if (!yearGroups.has(year)) yearGroups.set(year, []);
      yearGroups.get(year).push(season);
    });
    const years = Array.from(yearGroups.entries()).sort(([yearA], [yearB]) =>
      yearB.localeCompare(yearA, "es", { numeric: true })
    );
    const selectedSeries = seasons.some((season) => season.selected);
    const totalRaces = seasons.reduce((total, season) => total + season.raceCount, 0);
    return `
      <details class="archive-series-group" data-context-key="${escapeHtml(`archive-series:${seriesName}`)}" ${selectedSeries || (!globalAnalysis.seasons.some((season) => season.selected) && seriesIndex === 0) ? "open" : ""}>
        <summary>
          <span class="archive-series-icon" style="--archive-accent:${seriesTheme(seriesName).hex}">${seriesInitials(seriesName)}</span>
          <span class="archive-series-copy">
            <strong>${escapeHtml(seriesName)}</strong>
            <small>${seasons.length} temporada${seasons.length === 1 ? "" : "s"} · ${years.length} año${years.length === 1 ? "" : "s"} · ${totalRaces} carreras</small>
          </span>
          ${selectedSeries ? '<span class="archive-open-badge">ABIERTA</span>' : ""}
          <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m6 8 4 4 4-4" /></svg>
        </summary>
        <div class="archive-series-content">
          ${years.map(([year, yearSeasons]) => {
            const selectedYear = yearSeasons.some((season) => season.selected);
            return `
              <details class="archive-year-group" data-context-key="${escapeHtml(`archive-year:${seriesName}:${year}`)}" ${selectedYear ? "open" : ""}>
                <summary>
                  <span>${escapeHtml(year)}</span>
                  <small>${yearSeasons.length} temporada${yearSeasons.length === 1 ? "" : "s"}</small>
                  <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m6 8 4 4 4-4" /></svg>
                </summary>
                <div class="archive-year-grid">
                  ${yearSeasons
                    .sort((seasonA, seasonB) => String(seasonB.season).localeCompare(String(seasonA.season), "es", { numeric: true }))
                    .map(seasonCard)
                    .join("")}
                </div>
              </details>`;
          }).join("")}
        </div>
      </details>`;
  }).join("");
}

function renderPlatformContext() {
  const platform = appState.settings.platform || appState.league.platform || "iracing";
  const isAssetto = platform === "assetto-corsa";
  const copy = simulatorCopy[platform] || simulatorCopy.iracing;
  document.body.dataset.simulator = platform;
  document.querySelectorAll("[data-simulator-only]").forEach((element) => {
    element.hidden = element.dataset.simulatorOnly !== platform;
  });
  document.querySelectorAll("[data-iracing-only]").forEach((element) => {
    element.hidden = isAssetto;
  });
  document.querySelector("#simulatorSwitchMark").textContent = copy.mark;
  document.querySelector("#simulatorSwitchName").textContent = copy.name;
  document.querySelector("#settingsTitle").textContent = `Configuración de ${copy.name}`;
  document.querySelector("#settingsDescription").textContent = isAssetto
    ? "Reglas, carpeta de Content Manager y conservación del historial local."
    : "Reglas, resultados oficiales, OAuth y telemetrías locales.";
  document.querySelector("#ownerIdentityLabel").textContent = isAssetto
    ? "Mi nombre en Assetto Corsa"
    : "Mi ID de iRacing";
  document.querySelector("#ownerIdentityHelp").textContent = isAssetto
    ? "Este será el nombre principal que se mostrará en tus estadísticas."
    : "Se utiliza para las comparativas y para destacar tus resultados.";
  document.querySelector("#ownerIracingIdSetting").inputMode = isAssetto ? "text" : "numeric";
  document.querySelector("#ownerAliasesSettingField").hidden = !isAssetto;
  document.querySelector('#tiebreakerSetting option[value="incidents"]').textContent =
    "Menor media de incidentes";
  document.querySelector("#syncRoundsButton").innerHTML = isAssetto
    ? '<svg viewBox="0 0 24 24"><path d="M20 12a8 8 0 1 1-2.3-5.7L20 8m0-5v5h-5" /></svg>Buscar en Content Manager'
    : '<svg viewBox="0 0 24 24"><path d="M20 12a8 8 0 1 1-2.3-5.7L20 8m0-5v5h-5" /></svg>Buscar resultados';

  const cleanCardLabel = document.querySelector("#cleanName")?.parentElement?.querySelector("small");
  const fieldCardLabel = document.querySelector("#sofValue")?.parentElement?.querySelector("small");
  if (cleanCardLabel) cleanCardLabel.textContent = isAssetto ? "Menos incidentes" : "Más limpio";
  if (fieldCardLabel) fieldCardLabel.textContent = isAssetto ? "Pilotos registrados" : "SoF medio";
}

function renderSettings() {
  renderPlatformContext();
  const isAssetto = (appState.settings.platform || appState.league.platform) === "assetto-corsa";
  document.querySelector("#rankingModeSetting").value = appState.settings.rankingMode;
  document.querySelector("#minimumParticipationSetting").value = appState.settings.minimumParticipation;
  document.querySelector("#tiebreakerSetting").value = appState.settings.tiebreaker;
  document.querySelector("#ownerIracingIdSetting").value =
    appState.settings.ownerDisplayName || appState.settings.ownerIracingId || "";
  document.querySelector("#ownerAliasesSetting").value =
    isAssetto ? (appState.settings.ownerAliases || []).join("\n") : "";
  document.querySelector("#archiveCount").textContent = appState.storage.archiveCount;
  document.querySelector("#storedRaceCount").textContent = appState.storage.raceCount;
  document.querySelector("#importedFileCount").textContent = appState.storage.importCount || 0;
  document.querySelector("#storedTelemetryCount").textContent = appState.storage.telemetryCount || 0;
  document.querySelector("#telemetryFileCount").textContent = appState.storage.telemetryCount || 0;
  document.querySelector("#linkedTelemetryCount").textContent = appState.storage.linkedTelemetryCount || 0;
  document.querySelector("#practiceTelemetryCount").textContent = appState.storage.practiceTelemetryCount || 0;
  document.querySelector("#lastBackup").textContent = appState.storage.lastBackup
    ? new Date(appState.storage.lastBackup).toLocaleString("es-ES", { dateStyle: "short", timeStyle: "short" })
    : "Sin copias";
  document.querySelector("#archiveStatus").textContent = appState.storage.archiveCount ? "COPIA GUARDADA" : "EN CURSO";
  document.querySelector("#importFolderSetting").value = appState.settings.importFolder || "";
  document.querySelector("#autoScanImportSetting").checked = Boolean(appState.settings.autoScanImports);
  document.querySelector("#telemetryFolderSetting").value = appState.settings.telemetryFolder || "";
  document.querySelector("#autoScanTelemetrySetting").checked = Boolean(appState.settings.autoScanTelemetry);
  document.querySelector("#assettoFolderSetting").value = appState.settings.assettoCorsaFolder || "";
  document.querySelector("#assettoInstallFolderSetting").value =
    appState.settings.assettoCorsaInstallFolder || "";
  document.querySelector("#autoScanAssettoSetting").checked = Boolean(appState.settings.autoScanAssettoCorsa);
  const demoPill = document.querySelector(".demo-pill");
  demoPill.innerHTML = appState.demoMode
    ? "<span></span> Datos de demostración"
    : `<span></span> ${isAssetto ? "Assetto Corsa" : `${appState.storage.importCount} archivo${appState.storage.importCount === 1 ? "" : "s"} importado${appState.storage.importCount === 1 ? "" : "s"}`}`;

  const oauth = appState.oauth || {};
  const oauthInput = document.querySelector("#oauthClientId");
  const oauthIcon = document.querySelector("#oauthIcon");
  const oauthDot = document.querySelector("#oauthStatusDot");
  const disconnectButton = document.querySelector("#disconnectButton");
  oauthInput.value = oauth.clientId || "";
  oauthIcon.classList.toggle("connected", Boolean(oauth.connected));
  oauthIcon.classList.toggle("disconnected", !oauth.connected);
  oauthDot.classList.toggle("warning", !oauth.connected);
  disconnectButton.hidden = !oauth.connected;
  document.querySelector("#connectButton").textContent = oauth.connected ? "Volver a conectar" : "Guardar y conectar";
  document.querySelector("#oauthStatusTitle").textContent = oauth.connected
    ? oauth.profileName || "Cuenta conectada"
    : oauth.configured
      ? "Cliente configurado"
      : "No conectado";
  document.querySelector("#oauthStatusDetail").textContent = oauth.connected
    ? `iRacing ID ${oauth.profileCustId || "validado"} · Tokens cifrados por Windows`
    : oauth.configured
      ? "Listo para iniciar sesión en la web oficial de iRacing."
      : "Configura un cliente público de iRacing.";

  const minimum = requiredWeeks();
  document.querySelector("#qualificationNote").innerHTML = `
    <svg viewBox="0 0 24 24"><path d="M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Zm0-6v-4m0-4h.01" /></svg>
    Se requieren ${minimum} de ${appState.league.weeksCompleted} semanas con carreras para entrar en la clasificación${isAssetto ? "" : " oficial"}.
  `;

  rankingButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.ranking === appState.settings.rankingMode);
  });
}

function renderTelemetrySettings() {
  const container = document.querySelector("#telemetryFileList");
  const files = telemetryAnalysis.files || [];
  if (!files.length) {
    container.innerHTML = '<p class="telemetry-empty">Todavía no se ha indexado ninguna telemetría.</p>';
    return;
  }
  container.innerHTML = files.slice(0, 5).map((file) => {
    const practice = String(file.sessionType).toLowerCase() === "practice";
    const size = file.fileSize >= 1024 * 1024
      ? `${formatDecimal(file.fileSize / (1024 * 1024))} MB`
      : `${formatInteger(file.fileSize / 1024)} KB`;
    return `
      <article>
        <span class="telemetry-type ${practice ? "practice" : file.linkedEventId ? "linked" : ""}">${practice ? "PRÁCTICA" : file.linkedEventId ? "VINCULADA" : escapeHtml(file.sessionType || "IBT")}</span>
        <div><strong>${escapeHtml(file.filename)}</strong><small>${escapeHtml(file.trackName || "Circuito no identificado")} · ${escapeHtml(file.carName || "Coche no identificado")}</small></div>
        <span>${size}<small>${file.channelCount} canales</small></span>
      </article>`;
  }).join("");
}

function renderAll() {
  renderLeagueContext();
  renderRanking();
  renderRounds();
  renderDrivers();
  renderSettings();
  refreshMetricHelp(document);
}

function captureInterfaceContext() {
  return {
    scrollX: window.scrollX,
    scrollY: window.scrollY,
    openDetails: Array.from(document.querySelectorAll("details[data-context-key][open]"))
      .map((detail) => detail.dataset.contextKey),
    dialogs: Array.from(document.querySelectorAll("dialog")).map((dialog) => ({
      id: dialog.id,
      open: dialog.open,
      scrollTop: dialog.scrollTop,
      innerScrolls: Array.from(dialog.querySelectorAll(".table-wrap")).map((element) => ({
        left: element.scrollLeft,
        top: element.scrollTop
      }))
    }))
  };
}

function restoreInterfaceContext(context) {
  if (!context) return;
  document.querySelectorAll("details[data-context-key]").forEach((detail) => {
    detail.open = context.openDetails.includes(detail.dataset.contextKey);
  });
  context.dialogs.forEach((saved) => {
    const dialog = document.getElementById(saved.id);
    if (!dialog) return;
    if (saved.open && !dialog.open) dialog.showModal();
    dialog.scrollTop = saved.scrollTop;
    Array.from(dialog.querySelectorAll(".table-wrap")).forEach((element, index) => {
      const position = saved.innerScrolls[index];
      if (position) {
        element.scrollLeft = position.left;
        element.scrollTop = position.top;
      }
    });
  });
  requestAnimationFrame(() => window.scrollTo(context.scrollX, context.scrollY));
}

async function loadState({ quiet = false, preserveContext = false, showActivity = !preserveContext } = {}) {
  const interfaceContext = preserveContext ? captureInterfaceContext() : null;
  const activity = showActivity
    ? beginActivity("Actualizando estadísticas…", "Leyendo carreras, pilotos, comparativas y campeonatos de la base local.")
    : null;
  try {
    appState = await apiRequest("/api/state");
    document.querySelector("#backendStatus").textContent = "Base local activa";
    document.querySelector("#backendDetail").textContent = "SQLite · Solo este ordenador";
    renderAll();
    await loadRaceAnalytics();
    restoreInterfaceContext(interfaceContext);
    if (!quiet) showToast("Datos actualizados", "La información se ha leído desde la base de datos local.");
  } catch (error) {
    restoreInterfaceContext(interfaceContext);
    document.querySelector("#backendStatus").textContent = "Servidor no disponible";
    document.querySelector("#backendDetail").textContent = "Usa abrir-aplicacion.ps1";
    if (!quiet) showToast("No se puede conectar", error.message);
  } finally {
    if (activity != null) endActivity(activity);
  }
}

function switchView(viewId) {
  views.forEach((view) => view.classList.toggle("active", view.id === viewId));
  navButtons.forEach((button) => button.classList.toggle("active", button.dataset.view === viewId));
  pageTitle.textContent = pageTitles[viewId] || "GridScope";
  localStorage.setItem("apex-active-view", viewId);
  closeMobileMenu();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function showToast(title, message, { subtle = false, duration = 3200 } = {}) {
  document.querySelector("#toastTitle").textContent = title;
  document.querySelector("#toastMessage").textContent = message;
  toast.classList.toggle("subtle", subtle);
  toast.classList.add("show");
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => toast.classList.remove("show"), duration);
}

function closeMobileMenu() {
  sidebar.classList.remove("open");
  mobileOverlay.classList.remove("show");
  setLeagueMenuOpen(false);
}

rankingButtons.forEach((button) => {
  button.addEventListener("click", () => {
    rankingButtons.forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    renderRanking(button.dataset.ranking);
  });
});

navButtons.forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
directViewButtons.forEach((button) => button.addEventListener("click", () => switchView(button.dataset.viewTarget)));

document.querySelector("#menuButton").addEventListener("click", () => {
  sidebar.classList.add("open");
  mobileOverlay.classList.add("show");
});
mobileOverlay.addEventListener("click", closeMobileMenu);

document.querySelector("#refreshButton").addEventListener("click", async () => {
  const button = document.querySelector("#refreshButton");
  setButtonBusy(button, true, "Actualizando…");
  try {
    await loadState();
  } finally {
    setButtonBusy(button, false);
  }
});
document.querySelector("#syncRoundsButton").addEventListener("click", async () => {
  const button = document.querySelector("#syncRoundsButton");
  setButtonBusy(button, true, "Buscando resultados…");
  try {
    if ((appState.settings.platform || appState.league.platform) === "assetto-corsa") {
      await scanAssettoCorsaFolder();
    } else {
      await scanImportFolder();
    }
    await loadState({ quiet: true });
  } finally {
    setButtonBusy(button, false);
  }
});
document.querySelector("#seasonOverviewGrid").addEventListener("click", async (event) => {
  const card = event.target.closest("[data-overview-league]");
  if (!card) return;
  try {
    await selectLeague(card.dataset.overviewLeague);
    switchView("overview");
    showToast(
      appState.league.isCurrent ? "Temporada actual abierta" : "Temporada histórica abierta",
      `${appState.league.seriesName} · ${shortSeason(appState.league.season)}`
    );
  } catch (error) {
    showToast("No se ha podido abrir la temporada", error.message);
  }
});
document.querySelector("#raceExplorer").addEventListener("click", (event) => {
  const card = event.target.closest("[data-race-id]");
  if (card) openRaceDetail(Number(card.dataset.raceId));
});
document.querySelector("#ownerSeasonRaces").addEventListener("click", (event) => {
  const row = event.target.closest("[data-owner-season-race]");
  if (row) openRaceDetail(Number(row.dataset.ownerSeasonRace));
});
document.querySelector("#ownerSeasonRaces").addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  if (event.target.closest("button")) return;
  const row = event.target.closest("[data-owner-season-race]");
  if (row) {
    event.preventDefault();
    openRaceDetail(Number(row.dataset.ownerSeasonRace));
  }
});
document.querySelector("#ownerTrackBreakdown").addEventListener("click", (event) => {
  const card = event.target.closest("[data-owner-track-index]");
  if (card) openOwnerTrackDetail(card.dataset.ownerTrackIndex);
});
document.querySelector(".right-column").addEventListener("click", (event) => {
  const race = event.target.closest("[data-overview-owner-race]");
  if (race) openRaceDetail(Number(race.dataset.overviewOwnerRace));
});
document.querySelector("#miniLeagueTabs").addEventListener("click", (event) => {
  const tab = event.target.closest("[data-mini-scope]");
  if (!tab) return;
  activeCustomChampionshipId = null;
  miniLeagueMinimumRaces = Math.min(
    999,
    Math.max(1, Number(localStorage.getItem("gridscope-mini-minimum-races")) || 2)
  );
  activeMiniLeagueScope = tab.dataset.miniScope;
  renderMiniLeagues();
});
document.querySelector("#customChampionshipList").addEventListener("click", (event) => {
  const card = event.target.closest("[data-custom-championship]");
  if (!card) return;
  activeCustomChampionshipId = Number(card.dataset.customChampionship);
  activeMiniLeagueScope = `custom:${activeCustomChampionshipId}`;
  renderMiniLeagues();
});
document.querySelector("#createChampionshipButton").addEventListener("click", () => {
  openChampionshipEditor();
});
document.querySelector("#editChampionshipButton").addEventListener("click", () => {
  if (activeCustomChampionshipId != null) {
    openChampionshipEditor(activeCustomChampionshipId);
  }
});
document.querySelector("#closeChampionshipDialog").addEventListener("click", () => {
  championshipDialog.close();
});
document.querySelector("#cancelChampionshipButton").addEventListener("click", () => {
  championshipDialog.close();
});
document.querySelector("#championshipParticipantMode").addEventListener(
  "change",
  updateChampionshipDriverVisibility
);
document.querySelector("#championshipSeriesList").addEventListener("change", (event) => {
  if (event.target.matches('[name="championshipSeries"]')) {
    updateChampionshipSeriesCount();
  }
});
document.querySelector("#selectAllChampionshipSeries").addEventListener("click", () => {
  document.querySelectorAll('[name="championshipSeries"]').forEach((input) => {
    input.checked = true;
  });
  updateChampionshipSeriesCount();
});
document.querySelector("#clearChampionshipSeries").addEventListener("click", () => {
  document.querySelectorAll('[name="championshipSeries"]').forEach((input) => {
    input.checked = false;
  });
  updateChampionshipSeriesCount();
});
document.querySelector("#championshipDriverSearch").addEventListener("input", (event) => {
  renderChampionshipDriverChoices(event.target.value);
});
document.querySelector("#championshipDriverList").addEventListener("change", (event) => {
  const input = event.target.closest('[name="championshipDriver"]');
  if (!input) return;
  if (input.checked) championshipSelectedDriverIds.add(String(input.value));
  else championshipSelectedDriverIds.delete(String(input.value));
});
document.querySelector("#championshipForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const championshipId = document.querySelector("#championshipId").value;
  const payload = {
    name: document.querySelector("#championshipName").value,
    startDate: document.querySelector("#championshipStartDate").value,
    endDate: document.querySelector("#championshipEndDate").value,
    rankingMode: document.querySelector("#championshipRankingMode").value,
    minimumRaces: Number(document.querySelector("#championshipMinimumRaces").value),
    participantMode: document.querySelector("#championshipParticipantMode").value,
    includeOwner: document.querySelector("#championshipIncludeOwner").checked,
    seriesNames: Array.from(
      document.querySelectorAll('[name="championshipSeries"]:checked'),
      (input) => input.value
    ),
    driverIds: Array.from(championshipSelectedDriverIds)
  };
  const submitButton = event.submitter;
  setButtonBusy(submitButton, true, "Guardando…");
  try {
    const saved = await apiRequest(
      championshipId ? `/api/championships/${championshipId}` : "/api/championships",
      {
        method: championshipId ? "PUT" : "POST",
        body: JSON.stringify(payload)
      }
    );
    championshipDialog.close();
    await refreshCustomChampionships(saved.id);
    showToast(
      championshipId ? "Campeonato actualizado" : "Campeonato creado",
      `${saved.name} ya aparece en Campeonatos GridScope.`
    );
  } catch (error) {
    showToast("No se ha podido guardar", error.message);
  } finally {
    setButtonBusy(submitButton, false);
  }
});
document.querySelector("#deleteChampionshipButton").addEventListener("click", async () => {
  const championshipId = Number(document.querySelector("#championshipId").value);
  const championship = customChampionshipById(championshipId);
  if (!championship) return;
  if (!window.confirm(`¿Eliminar el campeonato "${championship.name}"? Las carreras originales se conservarán.`)) return;
  try {
    await apiRequest(`/api/championships/${championshipId}`, { method: "DELETE" });
    championshipDialog.close();
    activeCustomChampionshipId = null;
    activeMiniLeagueScope = "eternal";
    await refreshCustomChampionships();
    showToast("Campeonato eliminado", "Las carreras y estadísticas originales no se han modificado.");
  } catch (error) {
    showToast("No se ha podido eliminar", error.message);
  }
});
document.querySelector("#miniLeaguePeriodSelect").addEventListener("change", (event) => {
  activeMiniLeaguePeriods[activeMiniLeagueScope] = event.target.value;
  renderMiniLeagues();
});
document.querySelector("#miniLeagueMinimumRaces").addEventListener("change", (event) => {
  miniLeagueMinimumRaces = Math.min(
    999,
    Math.max(1, Number.parseInt(event.target.value, 10) || 1)
  );
  localStorage.setItem(
    "gridscope-mini-minimum-races",
    String(miniLeagueMinimumRaces)
  );
  renderMiniLeagues();
});
document.querySelector(".mini-league-table thead").addEventListener("click", (event) => {
  const button = event.target.closest("[data-mini-sort]");
  if (!button) return;
  const key = button.dataset.miniSort;
  if (miniLeagueSort.key === key) {
    miniLeagueSort.direction = miniLeagueSort.direction === "asc" ? "desc" : "asc";
  } else {
    miniLeagueSort = {
      key,
      direction: ["position", "name", "averageIncidents"].includes(key) ? "asc" : "desc"
    };
  }
  renderMiniLeagues();
});
document.querySelector("#miniLeagueBody").addEventListener("click", (event) => {
  const row = event.target.closest("[data-mini-driver-id]");
  if (row) openMiniLeagueDriverDetail(row.dataset.miniDriverId);
});
document.querySelector("#miniLeagueBody").addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const row = event.target.closest("[data-mini-driver-id]");
  if (row) {
    event.preventDefault();
    openMiniLeagueDriverDetail(row.dataset.miniDriverId);
  }
});
document.querySelector("#miniLeagueEvents").addEventListener("click", (event) => {
  const race = event.target.closest("[data-mini-race-id]");
  if (race) {
    const eventId = Number(race.dataset.miniRaceId);
    openRaceDetail(
      eventId,
      null,
      miniLeagueMemberIdsForRace(eventId, activeMiniLeagueScope)
    );
  }
});
document.querySelector("#driverGrid").addEventListener("click", (event) => {
  const card = event.target.closest("[data-driver-profile-id]");
  if (card) openSeasonDriverDetail(card.dataset.driverProfileId);
});
document.querySelector("#driverGrid").addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const card = event.target.closest("[data-driver-profile-id]");
  if (card) {
    event.preventDefault();
    openSeasonDriverDetail(card.dataset.driverProfileId);
  }
});
document.querySelector("#roundList").addEventListener("click", (event) => {
  const card = event.target.closest("[data-session-week]");
  if (card) openSessionDetail(Number(card.dataset.sessionWeek));
});
document.querySelector("#roundList").addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const card = event.target.closest("[data-session-week]");
  if (card) {
    event.preventDefault();
    openSessionDetail(Number(card.dataset.sessionWeek));
  }
});
document.querySelector("#closeRaceDetail").addEventListener("click", () => raceDetailDialog.close());
document.querySelector("#raceDetailContent").addEventListener("click", (event) => {
  const driverLink = event.target.closest("[data-race-driver-profile]");
  if (driverLink) openSeasonDriverDetail(driverLink.dataset.raceDriverProfile, "global");
});
document.querySelector("#closeSessionDetail").addEventListener("click", () => sessionDetailDialog.close());
document.querySelector("#sessionDetailContent").addEventListener("click", (event) => {
  const raceButton = event.target.closest("[data-session-race-id]");
  if (raceButton) {
    openRaceDetail(Number(raceButton.dataset.sessionRaceId));
    return;
  }
  const driver = event.target.closest("[data-session-driver-id]");
  if (driver) openSeasonDriverDetail(driver.dataset.sessionDriverId, "global");
});
document.querySelector("#sessionDetailContent").addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const driver = event.target.closest("[data-session-driver-id]");
  if (driver) {
    event.preventDefault();
    openSeasonDriverDetail(driver.dataset.sessionDriverId, "global");
  }
});
document.querySelector("#closeSessionDriver").addEventListener("click", () => sessionDriverDialog.close());
document.querySelector("#sessionDriverContent").addEventListener("click", (event) => {
  const race = event.target.closest("[data-driver-race-id]");
  if (race) {
    const eventId = Number(race.dataset.driverRaceId);
    const miniScope = sessionDriverDialog.dataset.miniLeagueScope;
    openRaceDetail(
      eventId,
      sessionDriverDialog.dataset.driverId,
      miniScope ? miniLeagueMemberIdsForRace(eventId, miniScope) : []
    );
  }
});
document.querySelector("#sessionDriverContent").addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const race = event.target.closest("[data-driver-race-id]");
  if (race) {
    event.preventDefault();
    const eventId = Number(race.dataset.driverRaceId);
    const miniScope = sessionDriverDialog.dataset.miniLeagueScope;
    openRaceDetail(
      eventId,
      sessionDriverDialog.dataset.driverId,
      miniScope ? miniLeagueMemberIdsForRace(eventId, miniScope) : []
    );
  }
});
document.querySelector("#rivalsBody").addEventListener("click", (event) => {
  const row = event.target.closest("[data-rival-id]");
  if (row) openRivalDetail(row.dataset.rivalId);
});
document.querySelector("#rivalsBody").addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const row = event.target.closest("[data-rival-id]");
  if (row) {
    event.preventDefault();
    openRivalDetail(row.dataset.rivalId);
  }
});
document.querySelector("#closeRivalDetail").addEventListener("click", () => rivalDetailDialog.close());
document.querySelectorAll("[data-close-all-details]").forEach((button) => {
  button.addEventListener("click", () => {
    [...detailDialogs].reverse().forEach((dialog) => {
      if (dialog?.open) dialog.close();
    });
  });
});
document.querySelector("#rivalDetailContent").addEventListener("click", (event) => {
  const race = event.target.closest("[data-shared-race-id]");
  if (!race) return;
  openRaceDetail(
    Number(race.dataset.sharedRaceId),
    rivalDetailDialog.dataset.rivalId
  );
});
document.querySelector("#rivalDetailContent").addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const race = event.target.closest("[data-shared-race-id]");
  if (race) {
    event.preventDefault();
    openRaceDetail(
      Number(race.dataset.sharedRaceId),
      rivalDetailDialog.dataset.rivalId
    );
  }
});
document.querySelector("#leagueMenuButton").addEventListener("click", () => {
  const expanded = document.querySelector("#leagueMenuButton").getAttribute("aria-expanded") === "true";
  setLeagueMenuOpen(!expanded);
});
document.querySelector("#leagueMenuList").addEventListener("click", async (event) => {
  const item = event.target.closest("[data-menu-league]");
  if (!item) return;
  try {
    await selectLeague(item.dataset.menuLeague);
    showToast(
      appState.league.isCurrent ? "Temporada actual abierta" : "Temporada histórica abierta",
      `${appState.league.seriesName} · ${shortSeason(appState.league.season)}`
    );
  } catch (error) {
    showToast("No se ha podido cambiar de serie", error.message);
  }
});
document.querySelector("#topbarSeasonContext").addEventListener("click", () => {
  if (window.innerWidth <= 900) {
    sidebar.classList.add("open");
    mobileOverlay.classList.add("show");
  }
  setLeagueMenuOpen(true);
});
document.addEventListener("click", (event) => {
  if (!event.target.closest(".league-switcher") && !event.target.closest("#topbarSeasonContext")) {
    setLeagueMenuOpen(false);
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") setLeagueMenuOpen(false);
});

function resetImportDialog() {
  pendingImports = [];
  resultFileInput.value = "";
  importFileList.innerHTML = "";
  confirmImportButton.disabled = true;
  confirmImportButton.textContent = "Importar resultados";
}

function renderImportFiles() {
  importFileList.innerHTML = pendingImports.map((item) => {
    if (item.error) {
      return `
        <div class="import-file error">
          <span><svg viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18" /></svg></span>
          <div><strong>${escapeHtml(item.filename)}</strong><small>${escapeHtml(item.error)}</small></div>
          <em>Error</em>
        </div>`;
    }
    const event = item.preview.event;
    return `
      <div class="import-file">
        <span><svg viewBox="0 0 24 24"><path d="m5 12 4 4L19 6" /></svg></span>
        <div>
          <strong>${escapeHtml(item.filename)}</strong>
          <small>S${String(event.raceWeek).padStart(2, "0")} · ${escapeHtml(event.track)} · ${event.fieldSize} pilotos · SoF ${formatInteger(event.strengthOfField)}</small>
        </div>
        <em>Válido</em>
      </div>`;
  }).join("");
  confirmImportButton.disabled = !pendingImports.some((item) => !item.error);
}

async function prepareImportFiles(files) {
  const selectedFiles = Array.from(files);
  if (!selectedFiles.length) return;
  pendingImports = [];
  confirmImportButton.disabled = true;
  importFileList.innerHTML = '<div class="qualification-note">Validando archivos JSON…</div>';

  for (const file of selectedFiles) {
    if (!file.name.toLowerCase().endsWith(".json")) {
      pendingImports.push({ filename: file.name, error: "El archivo no tiene extensión .json" });
      continue;
    }
    if (file.size > 12_000_000) {
      pendingImports.push({ filename: file.name, error: "El archivo supera el límite de 12 MB" });
      continue;
    }
    try {
      const text = (await file.text()).replace(/^\uFEFF/, "");
      const content = JSON.parse(text);
      const preview = await apiRequest("/api/import/iracing/preview", {
        method: "POST",
        body: JSON.stringify({ filename: file.name, content })
      });
      pendingImports.push({ filename: file.name, content, preview });
    } catch (error) {
      pendingImports.push({ filename: file.name, error: error.message });
    }
  }
  renderImportFiles();
}

document.querySelector("#importResultsButton").addEventListener("click", () => {
  resetImportDialog();
  importDialog.showModal();
});
document.querySelectorAll("[data-close-import]").forEach((button) => {
  button.addEventListener("click", () => importDialog.close());
});
importDropzone.addEventListener("click", () => resultFileInput.click());
resultFileInput.addEventListener("change", () => prepareImportFiles(resultFileInput.files));
["dragenter", "dragover"].forEach((eventName) => {
  importDropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    importDropzone.classList.add("dragging");
  });
});
["dragleave", "drop"].forEach((eventName) => {
  importDropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    importDropzone.classList.remove("dragging");
  });
});
importDropzone.addEventListener("drop", (event) => {
  prepareImportFiles(event.dataTransfer.files);
});

confirmImportButton.addEventListener("click", async () => {
  const validImports = pendingImports.filter((item) => !item.error);
  if (!validImports.length) return;
  confirmImportButton.disabled = true;
  confirmImportButton.textContent = `Importando 0 / ${validImports.length}`;
  let imported = 0;
  let duplicates = 0;
  let failed = 0;

  for (let index = 0; index < validImports.length; index += 1) {
    const item = validImports[index];
    confirmImportButton.textContent = `Importando ${index + 1} / ${validImports.length}`;
    try {
      const result = await apiRequest("/api/import/iracing", {
        method: "POST",
        body: JSON.stringify({
          filename: item.filename,
          content: item.content,
          includeAllDrivers: document.querySelector("#includeAllDrivers").checked,
          replaceDemo: document.querySelector("#replaceDemoData").checked
        })
      });
      if (result.duplicate) duplicates += 1;
      else imported += 1;
    } catch {
      failed += 1;
    }
  }

  await loadState({ quiet: true });
  confirmImportButton.textContent = "Importar resultados";
  if (!failed) importDialog.close();
  const details = [
    `${imported} importada${imported === 1 ? "" : "s"}`,
    duplicates ? `${duplicates} repetida${duplicates === 1 ? "" : "s"}` : null,
    failed ? `${failed} con error` : null
  ].filter(Boolean).join(" · ");
  showToast("Importación terminada", details);
  if (failed) confirmImportButton.disabled = false;
});

document.querySelector("#saveSettingsButton").addEventListener("click", async () => {
  try {
    const settings = {
      rankingMode: document.querySelector("#rankingModeSetting").value,
      minimumParticipation: Number(document.querySelector("#minimumParticipationSetting").value),
      tiebreaker: document.querySelector("#tiebreakerSetting").value,
      ownerIdentity: document.querySelector("#ownerIracingIdSetting").value.trim(),
      ownerAliases: aliasesFromField("#ownerAliasesSetting")
    };
    await apiRequest("/api/settings", { method: "PUT", body: JSON.stringify(settings) });
    await loadState({ quiet: true });
    showToast("Preferencias guardadas", "Las reglas se conservarán al cerrar la aplicación.");
  } catch (error) {
    showToast("No se han guardado", error.message);
  }
});

async function scanImportFolder({ quiet = false, background = false } = {}) {
  const status = document.querySelector("#folderScanStatus");
  const scanButton = document.querySelector("#scanImportFolderButton");
  const activity = background
    ? null
    : beginActivity("Buscando resultados de iRacing…", "Revisando los archivos JSON y descartando duplicados o sesiones que no son carrera.");
  if (!background) setButtonBusy(scanButton, true, "Buscando JSON…");
  if (!quiet) status.textContent = "Buscando archivos JSON…";
  try {
    const result = await apiRequest("/api/import/folder/scan", { method: "POST" });
    if (result.imported) {
      await loadState({ quiet: true, preserveContext: background });
    }
    const summary = `${result.scanned} revisado${result.scanned === 1 ? "" : "s"} · ${result.imported} nuevo${result.imported === 1 ? "" : "s"} · ${result.duplicates} repetido${result.duplicates === 1 ? "" : "s"} · ${result.ignored} ignorado${result.ignored === 1 ? "" : "s"}`;
    const firstError = result.errors?.[0];
    status.textContent = firstError
      ? `Última búsqueda: ${summary}. ${firstError.filename}: ${firstError.error}`
      : `Última búsqueda: ${summary}`;
    if (background && result.imported) {
      showToast(
        `${result.imported} carrera${result.imported === 1 ? "" : "s"} nueva${result.imported === 1 ? "" : "s"}`,
        "Datos actualizados en segundo plano.",
        { subtle: true, duration: 1800 }
      );
    } else if (!quiet || result.imported) {
      showToast(
        result.imported ? "Resultados nuevos importados" : firstError ? "Carpeta revisada con avisos" : "Carpeta revisada",
        firstError ? `${summary} · Revisa el aviso en Configuración.` : summary
      );
    }
    return result;
  } catch (error) {
    const message = error.status === 404
      ? "El servidor estaba abierto desde una versión anterior. Cierra su ventana y vuelve a ejecutar abrir-aplicacion.ps1."
      : error.message;
    status.textContent = message;
    if (!quiet) showToast("No se ha podido revisar la carpeta", message);
    return null;
  } finally {
    if (!background) setButtonBusy(scanButton, false);
    if (activity != null) endActivity(activity);
  }
}

async function saveImportFolderSettings({ scanAfterSave = true } = {}) {
  const folder = document.querySelector("#importFolderSetting").value.trim();
  const autoScan = document.querySelector("#autoScanImportSetting").checked;
  try {
    const saved = await apiRequest("/api/import/folder", {
      method: "PUT",
      body: JSON.stringify({ folder, autoScan })
    });
    appState.settings.importFolder = saved.folder;
    appState.settings.autoScanImports = saved.autoScan;
    document.querySelector("#importFolderSetting").value = saved.folder;
    showToast("Carpeta guardada", "GridScope buscará resultados JSON en esa ubicación.");
    if (scanAfterSave) await scanImportFolder({ quiet: true });
    return true;
  } catch (error) {
    showToast("Carpeta no válida", error.message);
    return false;
  }
}

document.querySelector("#saveImportFolderButton").addEventListener("click", () => {
  saveImportFolderSettings();
});

document.querySelector("#autoScanImportSetting").addEventListener("change", async (event) => {
  const saved = await saveImportFolderSettings({ scanAfterSave: event.target.checked });
  if (!saved) {
    event.target.checked = Boolean(appState.settings.autoScanImports);
  }
});
document.querySelector("#scanImportFolderButton").addEventListener("click", () => scanImportFolder());

async function scanAssettoCorsaFolder({ quiet = false, background = false } = {}) {
  const status = document.querySelector("#assettoScanStatus");
  const scanButton = document.querySelector("#scanAssettoFolderButton");
  const activity = background
    ? null
    : beginActivity("Leyendo el historial de Assetto Corsa…", "Revisando los JSON de Content Manager, separando carreras y descartando sesiones de práctica o IA.");
  if (!background) setButtonBusy(scanButton, true, "Leyendo historial…");
  if (!quiet) status.textContent = "Leyendo el historial de Content Manager…";
  try {
    const result = await apiRequest("/api/assetto-corsa/folder/scan", { method: "POST" });
    if (result.imported || result.aiDriversRemoved) {
      await loadState({ quiet: true, preserveContext: background });
    }
    const aiSummary = result.aiDriversRemoved
      ? ` · ${result.aiDriversRemoved} resultado${result.aiDriversRemoved === 1 ? "" : "s"} de IA eliminado${result.aiDriversRemoved === 1 ? "" : "s"}`
      : "";
    const summary = `${result.scanned} archivos · ${result.raceSessions} carreras detectadas · ${result.imported} nuevas · ${result.duplicates} guardadas${aiSummary}`;
    const firstError = result.errors?.[0];
    status.textContent = firstError
      ? `Última búsqueda: ${summary}. ${firstError.filename}: ${firstError.error}`
      : `Última búsqueda: ${summary}. Las sesiones que no son carrera no puntúan.`;
    if (background && result.imported) {
      showToast(
        `${result.imported} carrera${result.imported === 1 ? "" : "s"} nueva${result.imported === 1 ? "" : "s"}`,
        "Historial de Assetto Corsa actualizado.",
        { subtle: true, duration: 1800 }
      );
    } else if (!quiet || result.imported || result.aiDriversRemoved) {
      showToast(
        result.imported
          ? "Carreras de Assetto Corsa importadas"
          : result.aiDriversRemoved
            ? "Rivales de IA retirados"
            : "Historial revisado",
        summary
      );
    }
    return result;
  } catch (error) {
    status.textContent = error.message;
    if (!quiet) showToast("No se ha podido leer Content Manager", error.message);
    return null;
  } finally {
    if (!background) setButtonBusy(scanButton, false);
    if (activity != null) endActivity(activity);
  }
}

async function saveAssettoFolderSettings({ scanAfterSave = true } = {}) {
  const folder = document.querySelector("#assettoFolderSetting").value.trim();
  const installFolder = document.querySelector("#assettoInstallFolderSetting").value.trim();
  const ownerIdentity = document.querySelector("#ownerIracingIdSetting").value.trim();
  const ownerAliases = aliasesFromField("#ownerAliasesSetting");
  const autoScan = document.querySelector("#autoScanAssettoSetting").checked;
  try {
    const saved = await apiRequest("/api/simulators/config", {
      method: "PUT",
      body: JSON.stringify({
        simulator: "assetto-corsa",
        folder,
        installFolder,
        ownerIdentity,
        ownerAliases,
        autoScan
      })
    });
    appState.settings.assettoCorsaFolder = saved.folder;
    appState.settings.assettoCorsaInstallFolder = saved.installFolder || installFolder;
    appState.settings.autoScanAssettoCorsa = saved.autoScan;
    appState.settings.ownerAliases = saved.ownerAliases || ownerAliases;
    document.querySelector("#assettoFolderSetting").value = saved.folder;
    document.querySelector("#assettoInstallFolderSetting").value = saved.installFolder || installFolder;
    if (scanAfterSave) await scanAssettoCorsaFolder({ quiet: true });
    showToast("Configuración guardada", "GridScope vigilará el historial de Content Manager.");
    return true;
  } catch (error) {
    showToast("Configuración no válida", error.message);
    return false;
  }
}

document.querySelector("#saveAssettoFolderButton").addEventListener("click", () => {
  saveAssettoFolderSettings();
});
document.querySelector("#scanAssettoFolderButton").addEventListener("click", () => {
  scanAssettoCorsaFolder();
});
document.querySelector("#autoScanAssettoSetting").addEventListener("change", async (event) => {
  const saved = await saveAssettoFolderSettings({ scanAfterSave: event.target.checked });
  if (!saved) event.target.checked = Boolean(appState.settings.autoScanAssettoCorsa);
});

async function scanTelemetryFolder({ quiet = false, background = false } = {}) {
  const status = document.querySelector("#telemetryScanStatus");
  const scanButton = document.querySelector("#scanTelemetryFolderButton");
  const activity = background
    ? null
    : beginActivity("Leyendo telemetrías…", "Indexando los archivos IBT y vinculándolos con las carreras disponibles.");
  if (!background) setButtonBusy(scanButton, true, "Leyendo IBT…");
  if (!quiet) status.textContent = "Leyendo archivos IBT…";
  try {
    const result = await apiRequest("/api/telemetry/folder/scan", { method: "POST" });
    const changed = result.added + result.updated;
    if (changed) {
      await loadState({ quiet: true, preserveContext: background });
    }
    const summary = `${result.scanned} revisado${result.scanned === 1 ? "" : "s"} · ${result.added} nuevo${result.added === 1 ? "" : "s"} · ${result.linked} vinculado${result.linked === 1 ? "" : "s"} · ${result.practice} práctica${result.practice === 1 ? "" : "s"}`;
    const firstError = result.errors?.[0];
    status.textContent = firstError
      ? `Última búsqueda: ${summary}. ${firstError.filename}: ${firstError.error}`
      : `Última búsqueda: ${summary}`;
    if (background && changed) {
      showToast(
        `${changed} telemetría${changed === 1 ? "" : "s"} actualizada${changed === 1 ? "" : "s"}`,
        "Indexación completada en segundo plano.",
        { subtle: true, duration: 1800 }
      );
    } else if (!quiet || changed) {
      showToast(
        changed ? "Telemetrías indexadas" : firstError ? "Telemetrías revisadas con avisos" : "Telemetrías revisadas",
        firstError ? `${summary} · Revisa el aviso en Configuración.` : summary
      );
    }
    return result;
  } catch (error) {
    status.textContent = error.message;
    if (!quiet) showToast("No se han podido revisar las telemetrías", error.message);
    return null;
  } finally {
    if (!background) setButtonBusy(scanButton, false);
    if (activity != null) endActivity(activity);
  }
}

async function saveTelemetryFolderSettings({ scanAfterSave = true } = {}) {
  const folder = document.querySelector("#telemetryFolderSetting").value.trim();
  const autoScan = document.querySelector("#autoScanTelemetrySetting").checked;
  try {
    const saved = await apiRequest("/api/telemetry/folder", {
      method: "PUT",
      body: JSON.stringify({ folder, autoScan })
    });
    appState.settings.telemetryFolder = saved.folder;
    appState.settings.autoScanTelemetry = saved.autoScan;
    document.querySelector("#telemetryFolderSetting").value = saved.folder;
    showToast("Carpeta de telemetrías guardada", "GridScope buscará archivos IBT en esa ubicación.");
    if (scanAfterSave) await scanTelemetryFolder({ quiet: true });
    return true;
  } catch (error) {
    showToast("Carpeta de telemetrías no válida", error.message);
    return false;
  }
}

document.querySelector("#saveTelemetryFolderButton").addEventListener("click", () => {
  saveTelemetryFolderSettings();
});
document.querySelector("#autoScanTelemetrySetting").addEventListener("change", async (event) => {
  const saved = await saveTelemetryFolderSettings({ scanAfterSave: event.target.checked });
  if (!saved) event.target.checked = Boolean(appState.settings.autoScanTelemetry);
});
document.querySelector("#scanTelemetryFolderButton").addEventListener("click", () => scanTelemetryFolder());

document.querySelector("#archiveButton").addEventListener("click", async () => {
  try {
    const archive = await apiRequest("/api/archive", { method: "POST" });
    await loadState({ quiet: true });
    showToast("Temporada guardada", `Instantánea local creada para ${archive.season}.`);
  } catch (error) {
    showToast("No se ha podido archivar", error.message);
  }
});

document.querySelector("#exportButton").addEventListener("click", () => {
  window.location.assign("/api/export/standings.csv");
  showToast("Exportación iniciada", "La clasificación se descargará en formato CSV.");
});

document.querySelector("#backupButton").addEventListener("click", async () => {
  try {
    const backup = await apiRequest("/api/backup", { method: "POST" });
    await loadState({ quiet: true });
    showToast("Copia creada", `${backup.filename} se ha guardado en la carpeta backups.`);
  } catch (error) {
    showToast("No se ha creado la copia", error.message);
  }
});

document.querySelector("#connectButton").addEventListener("click", async () => {
  const clientId = document.querySelector("#oauthClientId").value.trim();
  if (!clientId) {
    showToast("Falta el Client ID", "Introduce el identificador emitido por iRacing.");
    return;
  }
  try {
    await apiRequest("/api/oauth/config", {
      method: "PUT",
      body: JSON.stringify({ clientId })
    });
    const authorization = await apiRequest("/api/oauth/start");
    window.location.assign(authorization.authorizationUrl);
  } catch (error) {
    showToast("No se puede iniciar la conexión", error.message);
  }
});
document.querySelector("#disconnectButton").addEventListener("click", async () => {
  try {
    await apiRequest("/api/oauth/disconnect", { method: "POST" });
    await loadState({ quiet: true });
    showToast("Cuenta desconectada", "Los tokens cifrados se han eliminado de este ordenador.");
  } catch (error) {
    showToast("No se ha podido desconectar", error.message);
  }
});
document.querySelector("#addDriverButton").addEventListener("click", () => driverDialog.showModal());
document.querySelectorAll("[data-close-dialog]").forEach((button) => {
  button.addEventListener("click", () => driverDialog.close());
});
document.querySelector("#driverForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.querySelector("#driverIdInput");
  const id = input.value.trim();
  if (!id) return;

  try {
    await apiRequest("/api/drivers", {
      method: "POST",
      body: JSON.stringify({ iracingId: id })
    });
    driverDialog.close();
    event.target.reset();
    await loadState({ quiet: true });
    showToast("Piloto guardado", `El ID ${id} queda pendiente de validación con iRacing.`);
  } catch (error) {
    showToast("No se ha añadido el piloto", error.message);
  }
});

document.querySelector(".page-kicker").textContent = new Intl.DateTimeFormat("es-ES", {
  weekday: "long",
  day: "numeric",
  month: "long"
}).format(new Date());

const savedView = localStorage.getItem("apex-active-view");
if (savedView && document.getElementById(savedView)) switchView(savedView);

document.querySelectorAll("[data-select-simulator]").forEach((button) => {
  button.addEventListener("click", () => chooseSimulator(button.dataset.selectSimulator));
});
document.querySelector("#gatewayBackButton").addEventListener("click", openSimulatorChooser);
document.querySelector("#simulatorSwitchButton").addEventListener("click", async () => {
  await loadBootstrap();
  openSimulatorChooser();
});
document.querySelector("#simulatorSetupForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const simulator = document.querySelector("#setupSimulator").value;
  const submitButton = document.querySelector("#setupSubmitButton");
  const detection = document.querySelector("#setupDetection");
  submitButton.disabled = true;
  submitButton.innerHTML = "Guardando configuración… <span>→</span>";
  try {
    await apiRequest("/api/simulators/config", {
      method: "PUT",
      body: JSON.stringify({
        simulator,
        ownerIdentity: document.querySelector("#setupOwnerIdentity").value.trim(),
        ownerAliases: aliasesFromField("#setupOwnerAliases"),
        folder: document.querySelector("#setupFolder").value.trim(),
        installFolder: document.querySelector("#setupInstallFolder").value.trim(),
        autoScan: document.querySelector("#setupAutoScan").checked
      })
    });
    await loadBootstrap();
    detection.className = "setup-detection detected";
    detection.textContent = "Configuración correcta. Preparando tu historial…";
    await enterSimulator(simulator, { scan: false });
    if (simulator === "assetto-corsa") {
      showToast("Analizando Content Manager", "La primera importación puede tardar unos segundos.");
      await scanAssettoCorsaFolder({ quiet: true });
    } else {
      await scanImportFolder({ quiet: true });
    }
    await loadState({ quiet: true });
    showToast("Simulador preparado", `${simulatorCopy[simulator].name} ya está listo en GridScope.`);
  } catch (error) {
    detection.className = "setup-detection error";
    detection.textContent = error.message;
  } finally {
    submitButton.disabled = false;
    submitButton.innerHTML = "Guardar y analizar resultados <span>→</span>";
  }
});

async function initializeApplication() {
  const parameters = new URLSearchParams(window.location.search);
  const oauthResult = parameters.get("oauth");
  const activity = beginActivity(
    "Iniciando GridScope…",
    "Comprobando la configuración y la conexión con la base local."
  );
  try {
    await loadBootstrap();
  } catch (error) {
    document.querySelector("#setupDetection").textContent = error.message;
    endActivity(activity);
    return;
  }
  try {
    if (oauthResult === "success") {
      await enterSimulator("iracing", { scan: false });
      switchView("settings");
      showToast("iRacing conectado", "La cuenta se ha autorizado y los tokens están cifrados en Windows.");
    } else if (oauthResult === "error") {
      await enterSimulator("iracing", { scan: false });
      switchView("settings");
      showToast("Conexión rechazada", parameters.get("message") || "iRacing no ha autorizado la conexión.");
    } else {
      openSimulatorChooser();
    }
    if (oauthResult) {
      window.history.replaceState({}, "", window.location.pathname);
    }
  } finally {
    endActivity(activity);
  }
}

async function runAutomaticScans() {
  if (automaticScanRunning) return;
  automaticScanRunning = true;
  try {
    const platform = appState.settings.platform || appState.league.platform;
    if (platform === "assetto-corsa" && appState.settings.autoScanAssettoCorsa) {
      await scanAssettoCorsaFolder({ quiet: true, background: true });
    } else if (platform === "iracing" && appState.settings.autoScanImports) {
      await scanImportFolder({ quiet: true, background: true });
    }
    if (platform === "iracing" && appState.settings.autoScanTelemetry) {
      await scanTelemetryFolder({ quiet: true, background: true });
    }
  } finally {
    automaticScanRunning = false;
  }
}

initializeApplication();
setInterval(runAutomaticScans, 60_000);
