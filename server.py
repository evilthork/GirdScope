from __future__ import annotations

import argparse
import base64
import csv
import ctypes
import difflib
import hashlib
import html
import io
import json
import math
import os
import re
import secrets
import sqlite3
import struct
import sys
import unicodedata
import webbrowser
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen


BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
INSTALL_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
APP_VERSION = "0.7.3"
LEGACY_DB_PATH = INSTALL_DIR / "data" / "apex-local.db"
LOCAL_APP_DATA = Path(
    os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
)
USER_DATA_DIR = LOCAL_APP_DATA / "GridScope"
DEFAULT_DB_PATH = (
    LEGACY_DB_PATH
    if LEGACY_DB_PATH.exists()
    else USER_DATA_DIR / "data" / "apex-local.db"
)
BACKUP_DIR = (
    INSTALL_DIR / "backups"
    if LEGACY_DB_PATH.exists()
    else USER_DATA_DIR / "backups"
)
TRACK_IMAGE_CACHE_DIR = DEFAULT_DB_PATH.parent / "image-cache" / "tracks"
SERIES_LOGO_CACHE_DIR = DEFAULT_DB_PATH.parent / "image-cache" / "series"
TRACK_MAP_CACHE_DIR = DEFAULT_DB_PATH.parent / "image-cache" / "track-maps"
OAUTH_AUTHORIZE_URL = "https://oauth.iracing.com/oauth2/authorize"
OAUTH_TOKEN_URL = "https://oauth.iracing.com/oauth2/token"
OAUTH_PROFILE_URL = "https://oauth.iracing.com/oauth2/iracing/profile"
RACEROOM_BASE_URL = "https://game.raceroom.com"


TRACK_SLUG_ALIASES = {
    "autodromo internazionale enzo e dino ferrari": "autodromo-enzo-e-dino-ferrari",
    "autodromo jose carlos pace": "autodromo-jose-carlos-pace",
    "brands hatch circuit": "brands-hatch",
    "circuit de barcelona catalunya": "circuit-de-barcelona-catalunya",
    "circuit des 24 heures du mans": "circuit-de-la-sarthe",
    "circuit park zandvoort": "circuit-park-zandvoort",
    "circuit zandvoort": "circuit-park-zandvoort",
    "charlotte motor speedway": "charlotte-roval",
    "hockenheimring baden wurttemberg": "hockenheimring-baden-wurttemberg",
    "mobility resort motegi": "twin-ring-motegi",
    "nurburgring grand prix strecke": "nurburgring-grand-prix-strecke",
    "road atlanta": "road-atlanta",
    "suzuka international racing course": "suzuka-international-racing-course",
}

TRACK_MAP_URL_OVERRIDES = {
    343: (
        "https://members-assets.iracing.com/public/track-maps/"
        "tracks_silverstone_2019/343-silverstone-2019-national/active.svg"
    ),
}


DEMO_DRIVERS = [
    ("418219", "Álex Romero", "AR", "orange", 3.42, 4.08, 2.17, 6, 14, 4, 2574, 0),
    ("587304", "Diego Lara", "DL", "teal", 4.17, 4.63, 1.67, 6, 11, 2, 2491, 1),
    ("392671", "Marc Vidal", "MV", "blue", 4.83, 5.21, 3.33, 6, 15, 1, 2388, 2),
    ("640182", "Jordi Serra", "JS", "red", 5.58, 5.88, 2.83, 6, 9, 1, 2302, -1),
    ("516903", "Sergio Núñez", "SN", "violet", 6.24, 6.41, 4.17, 5, 10, 0, 2411, 1),
    ("708415", "Pau Ferrer", "PF", "gold", 7.06, 6.91, 2.60, 5, 8, 0, 2198, -2),
    ("483276", "Iván Costa", "IC", "slate", 5.75, 6.03, 3.50, 2, 4, 1, 2256, 0),
    ("731940", "Nil Torres", "NT", "green", 8.00, 7.67, 2.00, 1, 3, 0, 2079, 0),
]

DEMO_ROUNDS = [
    (1, "Sebring International Raceway", "International", 3, 5.24, 3.1, 2184),
    (2, "Hockenheimring Baden-Württemberg", "Grand Prix", 2, 4.86, 2.8, 2236),
    (3, "Autódromo José Carlos Pace", "Grand Prix", 4, 5.02, 3.5, 2312),
    (4, "Circuit de Spa-Francorchamps", "Grand Prix Pits", 3, 4.71, 2.6, 2405),
    (5, "Circuit de Barcelona-Catalunya", "Historic", 3, 4.55, 2.9, 2552),
    (6, "Watkins Glen International", "Boot", 3, 4.38, 2.4, 2612),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pick_value(mapping: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalized_track_key(track_name: str) -> str:
    clean_name = re.sub(r"^\s*\[retired\]\s*", "", track_name, flags=re.IGNORECASE)
    ascii_name = unicodedata.normalize("NFKD", clean_name).encode(
        "ascii", "ignore"
    ).decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_name.lower()).strip()


def official_track_slug(track_name: str) -> str:
    track_key = normalized_track_key(track_name)
    return TRACK_SLUG_ALIASES.get(track_key, track_key.replace(" ", "-"))


def generic_track_svg(track_name: str) -> bytes:
    safe_name = (
        track_name.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    initials = "".join(
        word[0] for word in normalized_track_key(track_name).split()[:3]
    ).upper() or "TRK"
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop stop-color="#22272d"/><stop offset=".62" stop-color="#111418"/><stop offset="1" stop-color="#2a1b14"/>
  </linearGradient>
  <radialGradient id="glow"><stop stop-color="#ff7a2f" stop-opacity=".34"/><stop offset="1" stop-color="#ff7a2f" stop-opacity="0"/></radialGradient>
</defs>
<rect width="1280" height="720" fill="url(#bg)"/>
<circle cx="1050" cy="120" r="440" fill="url(#glow)"/>
<g fill="none" stroke-linecap="round" stroke-linejoin="round">
  <path d="M225 455c38-133 155-230 291-214 78 9 104 72 183 75 99 4 171-113 273-70 87 36 100 165 22 225-71 55-165 7-239 50-80 46-122 130-234 119-124-12-334-57-296-185Z" stroke="#3c4249" stroke-width="34"/>
  <path d="M225 455c38-133 155-230 291-214 78 9 104 72 183 75 99 4 171-113 273-70 87 36 100 165 22 225-71 55-165 7-239 50-80 46-122 130-234 119-124-12-334-57-296-185Z" stroke="#d9dde0" stroke-width="5" opacity=".7"/>
</g>
<text x="74" y="110" fill="#ff8b46" font-family="Arial,sans-serif" font-size="30" font-weight="700" letter-spacing="7">GRIDSCOPE</text>
<text x="75" y="175" fill="#f4f5f6" font-family="Arial,sans-serif" font-size="46" font-weight="700">{safe_name}</text>
<text x="1090" y="645" fill="#ffffff" fill-opacity=".12" font-family="Arial,sans-serif" font-size="110" font-weight="800" text-anchor="middle">{initials}</text>
</svg>"""
    return svg.encode("utf-8")


def iracing_result_root(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    root = payload
    for wrapper in ("data", "result", "event"):
        candidate = root.get(wrapper)
        if isinstance(candidate, dict) and any(
            key in candidate
            for key in ("subsession_id", "session_results", "results", "series_name")
        ):
            return candidate
    return root


def extract_series_logo(raw_json: str) -> str:
    try:
        root = iracing_result_root(json.loads(raw_json))
    except (json.JSONDecodeError, TypeError):
        return ""
    logo = str(pick_value(root, "series_logo", "seriesLogo", default="")).strip()
    return logo if re.fullmatch(r"[A-Za-z0-9_.-]+\.(?:png|webp|jpg|jpeg)", logo) else ""


def extract_track_id(raw_json: str) -> int:
    try:
        root = iracing_result_root(json.loads(raw_json))
    except (json.JSONDecodeError, TypeError):
        return 0
    track = pick_value(root, "track", "track_info", "trackInfo", default={})
    if not isinstance(track, dict):
        return 0
    return as_int(pick_value(track, "track_id", "trackId"), 0)


def generic_series_svg(series_name: str, platform: str = "iracing") -> bytes:
    safe_name = (
        series_name.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    is_assetto = platform == "assetto-corsa"
    is_raceroom = platform == "raceroom"
    category = (
        "ASSETTO CORSA"
        if is_assetto
        else "RACEROOM"
        if is_raceroom
        else "iRACING SERIES"
    )
    accent = "#d9b245" if is_assetto or is_raceroom else "#ff7a2f"
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="720" height="260" viewBox="0 0 720 260">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#282d33"/><stop offset="1" stop-color="#15181c"/></linearGradient></defs>
<rect width="720" height="260" rx="28" fill="url(#g)"/>
<path d="M45 193h630" stroke="{accent}" stroke-width="5"/>
<text x="45" y="70" fill="{accent}" font-family="Arial,sans-serif" font-size="22" font-weight="700" letter-spacing="5">{category}</text>
<text x="45" y="133" fill="#f4f5f6" font-family="Arial,sans-serif" font-size="30" font-weight="700">{safe_name}</text>
</svg>"""
    return svg.encode("utf-8")


def resolve_series_logo(
    logo: str, series_name: str, platform: str = "iracing"
) -> tuple[bytes, str, str]:
    if platform in {"assetto-corsa", "raceroom"}:
        return (
            generic_series_svg(series_name, platform),
            "image/svg+xml; charset=utf-8",
            f"generic-{platform}",
        )
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.(?:png|webp|jpg|jpeg)", logo):
        return (
            generic_series_svg(series_name, platform),
            "image/svg+xml; charset=utf-8",
            "generic",
        )
    SERIES_LOGO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.sha256(logo.lower().encode("utf-8")).hexdigest()[:24]
    for suffix, content_type in (
        (".png", "image/png"),
        (".webp", "image/webp"),
        (".jpg", "image/jpeg"),
    ):
        cached_path = SERIES_LOGO_CACHE_DIR / f"{cache_key}{suffix}"
        if cached_path.exists():
            return cached_path.read_bytes(), content_type, "official-cache"
    try:
        request = Request(
            f"https://images-static.iracing.com/img/logos/series/{logo}",
            headers={
                "Accept": "image/avif,image/webp,image/png,image/jpeg",
                "User-Agent": f"GridScope/{APP_VERSION}",
            },
        )
        with urlopen(request, timeout=15) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"image/jpeg", "image/png", "image/webp"}:
                raise ValueError("El recurso oficial no es una imagen compatible")
            content = response.read(2_000_001)
        if not content or len(content) > 2_000_000:
            raise ValueError("El logotipo oficial supera el límite permitido")
        suffix = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
        }[content_type]
        (SERIES_LOGO_CACHE_DIR / f"{cache_key}{suffix}").write_bytes(content)
        return content, content_type, "official"
    except (HTTPError, URLError, OSError, TimeoutError, ValueError):
        return (
            generic_series_svg(series_name, platform),
            "image/svg+xml; charset=utf-8",
            "generic",
        )


def generic_track_map_svg(track_name: str) -> bytes:
    safe_name = (
        track_name.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="420" height="180" viewBox="0 0 420 180">
<path d="M24 111c39-5 54 28 99 17 39-10 17-65 61-76 33-8 48 27 80 34 39 8 50-42 89-21 31 17 42 51 20 72-20 19-54-1-80 5-33 7-40 21-75 12-43-11-68-18-109-8-42 10-66-4-85-35Z" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
<text x="210" y="174" fill="#a5abb2" font-family="Arial,sans-serif" font-size="12" text-anchor="middle">{safe_name}</text>
</svg>"""
    return svg.encode("utf-8")


def detect_assetto_corsa_installation(preferred: str = "") -> Path | None:
    candidates: list[Path] = []
    if preferred:
        candidates.append(Path(preferred).expanduser())
    steam_roots = [
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Steam",
        Path(os.environ.get("PROGRAMFILES", "")) / "Steam",
        Path.home() / ".local" / "share" / "Steam",
    ]
    for drive in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        steam_roots.extend(
            [Path(f"{drive}:\\Steam"), Path(f"{drive}:\\SteamLibrary")]
        )
    library_roots: list[Path] = []
    for steam_root in steam_roots:
        if not str(steam_root).strip() or not steam_root.is_dir():
            continue
        library_roots.append(steam_root)
        library_file = steam_root / "steamapps" / "libraryfolders.vdf"
        if library_file.is_file():
            try:
                text = library_file.read_text(encoding="utf-8", errors="replace")
                library_roots.extend(
                    Path(value.replace("\\\\", "\\"))
                    for value in re.findall(
                        r'"path"\s+"([^"]+)"', text, flags=re.IGNORECASE
                    )
                )
            except OSError:
                pass
    candidates.extend(
        root / "steamapps" / "common" / "assettocorsa"
        for root in library_roots
    )
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).casefold()
        if key in seen:
            continue
        seen.add(key)
        if (
            candidate.is_dir()
            and (candidate / "content" / "tracks").is_dir()
        ):
            return candidate.resolve()
    return None


def assetto_identifier_match_score(left: str, right: str) -> float:
    left_key = normalized_person_key(left)
    right_key = normalized_person_key(right)
    if not left_key or not right_key:
        return 0.0
    left_compact = left_key.replace(" ", "")
    right_compact = right_key.replace(" ", "")
    if left_key == right_key or left_compact == right_compact:
        return 3.0
    if (
        left_key in right_key
        or right_key in left_key
        or left_compact in right_compact
        or right_compact in left_compact
    ):
        return 2.0
    left_tokens = {token for token in left_key.split() if len(token) >= 3}
    right_tokens = {token for token in right_key.split() if len(token) >= 3}
    if left_tokens & right_tokens:
        return 1.0
    return difflib.SequenceMatcher(None, left_compact, right_compact).ratio()


def find_assetto_track_directory(
    install_root: Path, track_name: str, layout: str = ""
) -> Path | None:
    tracks_root = install_root / "content" / "tracks"
    if not tracks_root.is_dir():
        return None
    target = normalized_person_key(track_name)
    try:
        directories = [item for item in tracks_root.iterdir() if item.is_dir()]
    except OSError:
        return None
    aliases = {
        "20 brazil gp": ("interlagos",),
        "montreal": ("gilles villeneuve",),
    }
    alias_targets = aliases.get(target, ())
    ranked: list[tuple[float, float, Path]] = []
    for directory in directories:
        raw_key = normalized_person_key(directory.name)
        display_key = normalized_person_key(
            humanize_assetto_identifier(directory.name, directory.name)
        )
        if target in {raw_key, display_key}:
            track_score = 4.0
        elif target and (
            target in raw_key
            or raw_key in target
            or target in display_key
            or display_key in target
        ):
            track_score = 3.0
        else:
            target_tokens = {
                token for token in target.split() if len(token) >= 4
            }
            directory_tokens = {
                token for token in raw_key.split() if len(token) >= 4
            }
            if target_tokens & directory_tokens or any(
                alias in raw_key or alias in display_key
                for alias in alias_targets
            ):
                track_score = 2.0
            else:
                track_score = max(
                    difflib.SequenceMatcher(None, target, raw_key).ratio(),
                    difflib.SequenceMatcher(None, target, display_key).ratio(),
                )
        if track_score < 0.68:
            continue
        layout_score = 0.0
        ui_root = directory / "ui"
        if layout and ui_root.is_dir():
            try:
                for candidate in ui_root.iterdir():
                    if not candidate.is_dir():
                        continue
                    layout_score = max(
                        layout_score,
                        assetto_identifier_match_score(layout, candidate.name),
                        assetto_identifier_match_score(
                            layout,
                            humanize_assetto_identifier(
                                candidate.name, candidate.name
                            ),
                        ),
                    )
            except OSError:
                pass
        ranked.append((track_score + layout_score, track_score, directory))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2].name.lower()))
    return ranked[0][2] if ranked else None


def resolve_assetto_track_asset(
    track_name: str,
    layout: str,
    install_root: Path | None,
    asset_kind: str,
) -> tuple[bytes, str, str] | None:
    if install_root is None:
        return None
    track_directory = find_assetto_track_directory(
        install_root, track_name, layout
    )
    if track_directory is None:
        return None
    ui_root = track_directory / "ui"
    layout_key = normalized_person_key(layout)
    layout_directories: list[Path] = []
    other_layout_directories: list[Path] = []
    if layout_key and ui_root.is_dir():
        try:
            for candidate in ui_root.iterdir():
                if not candidate.is_dir():
                    continue
                match_score = max(
                    assetto_identifier_match_score(layout, candidate.name),
                    assetto_identifier_match_score(
                        layout,
                        humanize_assetto_identifier(
                            candidate.name, candidate.name
                        ),
                    ),
                )
                if match_score >= 1.0:
                    layout_directories.append(candidate)
                else:
                    other_layout_directories.append(candidate)
        except OSError:
            pass
    elif ui_root.is_dir():
        try:
            other_layout_directories = sorted(
                [item for item in ui_root.iterdir() if item.is_dir()],
                key=lambda item: item.name.lower(),
            )
        except OSError:
            pass
    layout_directories.sort(
        key=lambda candidate: (
            -max(
                assetto_identifier_match_score(layout, candidate.name),
                assetto_identifier_match_score(
                    layout,
                    humanize_assetto_identifier(
                        candidate.name, candidate.name
                    ),
                ),
            ),
            candidate.name.lower(),
        )
    )
    search_roots = [*layout_directories]
    if asset_kind == "outline":
        search_roots.extend(
            track_directory / candidate.name
            for candidate in layout_directories
            if (track_directory / candidate.name).is_dir()
        )
    search_roots.append(ui_root)
    if asset_kind == "outline":
        search_roots.append(track_directory)
    search_roots.extend(other_layout_directories)
    if asset_kind == "outline":
        search_roots.extend(
            track_directory / candidate.name
            for candidate in other_layout_directories
            if (track_directory / candidate.name).is_dir()
        )
    filenames = (
        ("preview.png", "preview.jpg", "preview.jpeg")
        if asset_kind == "preview"
        else ("outline.png", "map.png", "outline_cropped.png")
    )
    for root in search_roots:
        for filename in filenames:
            candidate = root / filename
            try:
                file_size = candidate.stat().st_size
                if (
                    not candidate.is_file()
                    or file_size > 12_000_000
                    or (
                        filename == "outline_cropped.png"
                        and file_size <= 512
                    )
                ):
                    continue
                content_type = (
                    "image/png"
                    if candidate.suffix.lower() == ".png"
                    else "image/jpeg"
                )
                return candidate.read_bytes(), content_type, "assetto-local"
            except OSError:
                continue
    return None


def read_shared_binary(path: Path, maximum_size: int = 64_000_000) -> bytes:
    if os.name != "nt":
        return path.read_bytes()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    create_file.restype = ctypes.c_void_p
    handle = create_file(
        str(path),
        0x80000000,
        0x1 | 0x2 | 0x4,
        None,
        3,
        0x80,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle in (None, invalid_handle):
        raise OSError(ctypes.get_last_error(), f"No se puede leer {path}")
    try:
        size = ctypes.c_longlong()
        if not kernel32.GetFileSizeEx(handle, ctypes.byref(size)):
            raise OSError(ctypes.get_last_error(), f"No se puede medir {path}")
        if size.value < 0 or size.value > maximum_size:
            raise OSError(f"El archivo de caché supera {maximum_size} bytes")
        chunks: list[bytes] = []
        remaining = size.value
        while remaining:
            chunk_size = min(remaining, 4_000_000)
            buffer = ctypes.create_string_buffer(chunk_size)
            bytes_read = ctypes.c_uint32()
            if not kernel32.ReadFile(
                handle,
                buffer,
                chunk_size,
                ctypes.byref(bytes_read),
                None,
            ):
                raise OSError(ctypes.get_last_error(), f"No se puede leer {path}")
            if bytes_read.value == 0:
                break
            chunks.append(buffer.raw[: bytes_read.value])
            remaining -= bytes_read.value
        return b"".join(chunks)
    finally:
        kernel32.CloseHandle(handle)


def discover_official_track_map_url(track_id: int) -> str:
    if track_id <= 0:
        return ""
    if track_id in TRACK_MAP_URL_OVERRIDES:
        return TRACK_MAP_URL_OVERRIDES[track_id]
    cache_root = (
        Path.home()
        / "AppData"
        / "Roaming"
        / "iracing-electron"
        / "Cache"
        / "Cache_Data"
    )
    if not cache_root.exists():
        return ""
    track_bytes = str(track_id).encode("ascii")
    pattern = re.compile(
        rb"https://members-assets\.iracing\.com/public/track-maps/"
        rb"[^\x00\s\"'<>\\]+/"
        + track_bytes
        + rb"-[^\x00\s\"'<>\\]+/active\.svg"
    )
    for cache_file in cache_root.glob("data_*"):
        try:
            content = read_shared_binary(cache_file)
        except OSError:
            continue
        match = pattern.search(content)
        if match:
            return match.group(0).decode("ascii")
    return ""


def resolve_track_map(
    track_id: int,
    track_name: str,
    platform: str = "iracing",
    layout: str = "",
    assetto_install_root: Path | None = None,
) -> tuple[bytes, str, str]:
    if platform == "assetto-corsa":
        local_asset = resolve_assetto_track_asset(
            track_name, layout, assetto_install_root, "outline"
        )
        if local_asset is not None:
            return local_asset
    TRACK_MAP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if track_id > 0:
        cached_path = TRACK_MAP_CACHE_DIR / f"{track_id}.svg"
        if cached_path.exists():
            return cached_path.read_bytes(), "image/svg+xml; charset=utf-8", "official-cache"
        map_url = discover_official_track_map_url(track_id)
        if map_url:
            try:
                request = Request(
                    map_url,
                    headers={
                        "Accept": "image/svg+xml",
                        "User-Agent": f"GridScope/{APP_VERSION}",
                    },
                )
                with urlopen(request, timeout=15) as response:
                    content = response.read(2_000_001)
                if (
                    content
                    and len(content) <= 2_000_000
                    and b"<svg" in content[:1000].lower()
                ):
                    cached_path.write_bytes(content)
                    return content, "image/svg+xml; charset=utf-8", "official"
            except (HTTPError, URLError, OSError, TimeoutError, ValueError):
                pass
    return generic_track_map_svg(track_name), "image/svg+xml; charset=utf-8", "generic"


def resolve_track_image(
    track_name: str,
    platform: str = "iracing",
    layout: str = "",
    assetto_install_root: Path | None = None,
) -> tuple[bytes, str, str]:
    normalized_name = normalized_track_key(track_name)
    cache_key = hashlib.sha256(
        f"{platform}|{normalized_name}|{normalized_person_key(layout)}".encode("utf-8")
    ).hexdigest()[:24]
    TRACK_IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for suffix, content_type in (
        (".jpg", "image/jpeg"),
        (".png", "image/png"),
        (".webp", "image/webp"),
    ):
        cached_path = TRACK_IMAGE_CACHE_DIR / f"{cache_key}{suffix}"
        if cached_path.exists():
            return cached_path.read_bytes(), content_type, f"{platform}-cache"

    if platform == "assetto-corsa":
        local_asset = resolve_assetto_track_asset(
            track_name, layout, assetto_install_root, "preview"
        )
        if local_asset is not None:
            return local_asset

    fallback_path = TRACK_IMAGE_CACHE_DIR / f"{cache_key}.fallback.svg"
    if fallback_path.exists():
        age = datetime.now(timezone.utc).timestamp() - fallback_path.stat().st_mtime
        if age < 24 * 60 * 60:
            return fallback_path.read_bytes(), "image/svg+xml; charset=utf-8", "generic"

    try:
        slug = official_track_slug(track_name)
        if not slug:
            raise ValueError("Nombre de circuito vacío")
        page_request = Request(
            f"https://www.iracing.com/tracks/{slug}/",
            headers={
                "Accept": "text/html",
                        "User-Agent": f"GridScope/{APP_VERSION}",
            },
        )
        with urlopen(page_request, timeout=12) as response:
            page = response.read(3_000_000).decode("utf-8", errors="replace")
        image_urls = re.findall(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            page,
            flags=re.IGNORECASE,
        )
        image_urls.extend(
            re.findall(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
                page,
                flags=re.IGNORECASE,
            )
        )
        preferred_urls = [
            image_url
            for image_url in image_urls
            if not re.search(r"\d+x\d+\.", image_url)
        ] or image_urls
        if not preferred_urls:
            raise ValueError("La ficha oficial no contiene imágenes")
        image_url = preferred_urls[-1]
        image_host = (urlparse(image_url).hostname or "").lower()
        if not (
            image_host == "iracing.com"
            or image_host.endswith(".iracing.com")
        ):
            raise ValueError("La imagen no pertenece a iRacing")
        image_request = Request(
            image_url,
            headers={
                "Accept": "image/avif,image/webp,image/png,image/jpeg",
                        "User-Agent": f"GridScope/{APP_VERSION}",
            },
        )
        with urlopen(image_request, timeout=15) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"image/jpeg", "image/png", "image/webp"}:
                raise ValueError("El recurso oficial no es una imagen compatible")
            content = response.read(8_000_001)
        if not content or len(content) > 8_000_000:
            raise ValueError("La imagen oficial supera el límite permitido")
        suffix = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
        }[content_type]
        (TRACK_IMAGE_CACHE_DIR / f"{cache_key}{suffix}").write_bytes(content)
        fallback_path.unlink(missing_ok=True)
        return content, content_type, "official"
    except (HTTPError, URLError, OSError, TimeoutError, ValueError):
        fallback = generic_track_svg(track_name)
        fallback_path.write_bytes(fallback)
        return fallback, "image/svg+xml; charset=utf-8", "generic"


def display_position(result: dict[str, Any], *keys: str) -> int:
    for key in keys:
        if key not in result or result[key] is None:
            continue
        position = as_int(result[key], -1)
        if position < 0:
            return 0
        if key in {
            "finish_position",
            "finish_position_in_class",
            "finishPosition",
            "finishPositionInClass",
            "starting_position",
            "starting_position_in_class",
            "startingPosition",
            "startingPositionInClass",
        }:
            return position + 1
        return position
    return 0


def driver_initials(name: str) -> str:
    parts = [part for part in name.replace("-", " ").split() if part]
    if not parts:
        return "ID"
    return "".join(part[0] for part in parts[:2]).upper()


def season_coordinates(value: str) -> tuple[int, int]:
    text = str(value or "")
    year_match = re.search(r"\b(20\d{2})\b", text)
    season_match = re.search(r"(?:Season|Temporada)\s*(\d+)", text, re.IGNORECASE)
    return (
        int(year_match.group(1)) if year_match else 0,
        int(season_match.group(1)) if season_match else 0,
    )


def normalized_person_key(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", str(name or "")).encode(
        "ascii", "ignore"
    ).decode("ascii")
    compact = re.sub(r"[^a-z0-9]+", " ", ascii_name.lower()).strip()
    return compact


def assetto_driver_id(name: str) -> str:
    normalized = normalized_person_key(clean_assetto_driver_name(name))
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"ac:{digest}"


def clean_assetto_driver_name(name: str) -> str:
    return re.sub(r"^\s*#?\d+\s*\|\s*", "", str(name or "")).strip()


def humanize_assetto_identifier(value: str, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    text = re.sub(r"^(?:ks|rt|vhe|acf|ac)[_-]", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"(?:[_-](?:lfm|nodrs|standing|rollstart))+$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(r"[_-]+", " ", text).strip().title() or fallback


def assetto_ini_value(raw_ini: Any, key: str) -> str:
    if not isinstance(raw_ini, str):
        return ""
    match = re.search(
        rf"^[ \t]*{re.escape(key)}[ \t]*=[ \t]*(.*?)[ \t]*$",
        raw_ini,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    return match.group(1).strip() if match else ""


def assetto_remote_driver_name(raw_ini: Any) -> str:
    if not isinstance(raw_ini, str):
        return ""
    section = re.search(
        r"\[REMOTE\](.*?)(?=\r?\n\[[^\]]+\]|\Z)",
        raw_ini,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return assetto_ini_value(section.group(1), "NAME") if section else ""


def assetto_is_online_session(raw_ini: Any) -> bool:
    return bool(
        isinstance(raw_ini, str)
        and re.search(
            r"^\s*\[REMOTE\]\s*$",
            raw_ini,
            flags=re.IGNORECASE | re.MULTILINE,
        )
    )


def normalize_assetto_owner_aliases(
    primary_name: str, aliases: Any = None
) -> list[str]:
    raw_aliases: list[str] = []
    if isinstance(aliases, list):
        raw_aliases = [str(value) for value in aliases]
    elif isinstance(aliases, str):
        raw_aliases = re.split(r"[\r\n,;]+", aliases)
    names = [primary_name, *raw_aliases]
    normalized: list[str] = []
    seen: set[str] = set()
    for value in names:
        name = clean_assetto_driver_name(value)
        key = normalized_person_key(name)
        if (
            len(name) < 2
            or len(name) > 100
            or not key
            or "=" in name
            or key in seen
        ):
            continue
        seen.add(key)
        normalized.append(name)
    return normalized


def detect_assetto_owner_aliases(folder: Path) -> list[str]:
    if not folder.is_dir():
        return []
    counts: Counter[str] = Counter()
    display_names: dict[str, str] = {}
    files = sorted(
        folder.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True
    )
    for file_path in files[:2500]:
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8-sig"))
            name = clean_assetto_driver_name(
                assetto_remote_driver_name(payload.get("__raceIni", ""))
            )
            aliases = normalize_assetto_owner_aliases(name)
            if aliases:
                key = normalized_person_key(aliases[0])
                counts[key] += 1
                display_names.setdefault(key, aliases[0])
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
    return [
        display_names[key]
        for key, _ in sorted(
            counts.items(), key=lambda item: (-item[1], display_names[item[0]].lower())
        )
    ]


def assetto_aliases_from_settings(settings: dict[str, str]) -> list[str]:
    aliases: Any = []
    try:
        aliases = json.loads(settings.get("owner_assetto_corsa_aliases", "[]"))
    except (TypeError, json.JSONDecodeError):
        aliases = []
    return normalize_assetto_owner_aliases(
        settings.get("owner_assetto_corsa_name", ""), aliases
    )


def assetto_session_datetime(filename: str) -> datetime:
    match = re.search(r"(\d{6})-(\d{6})", Path(filename).stem)
    if match:
        try:
            return datetime.strptime(
                f"{match.group(1)}-{match.group(2)}", "%y%m%d-%H%M%S"
            ).astimezone()
        except ValueError:
            pass
    return datetime.now().astimezone()


def normalize_assetto_corsa_export(
    payload: Any, filename: str
) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("El archivo de Content Manager no contiene una sesión válida")
    players = payload.get("players")
    sessions = payload.get("sessions")
    if not isinstance(players, list) or not isinstance(sessions, list):
        raise ValueError("No es un resultado de Assetto Corsa guardado por Content Manager")

    raw_ini = payload.get("__raceIni", "")
    is_online_session = assetto_is_online_session(raw_ini)
    server_name = assetto_ini_value(raw_ini, "SERVER_NAME")
    server_ip = assetto_ini_value(raw_ini, "SERVER_IP")
    if "lowfuelmotorsport" in server_name.lower():
        series_name = "Low Fuel Motorsport"
    elif server_name:
        series_name = re.sub(r"\s*\|\s*\d+(?:\|\d+)*\s*$", "", server_name).strip()
    elif server_ip:
        series_name = "Servidor online de Assetto Corsa"
    else:
        series_name = "Carreras locales de Assetto Corsa"

    event_time = assetto_session_datetime(filename)
    year = event_time.year
    iso_week = event_time.isocalendar().week
    raw_track = str(payload.get("track") or "")
    if "-" in raw_track:
        track_id, layout_id = raw_track.split("-", 1)
    else:
        track_id, layout_id = raw_track, ""
    track_name = humanize_assetto_identifier(track_id, "Circuito de Assetto Corsa")
    layout_name = humanize_assetto_identifier(layout_id, "Trazado principal")
    cars = {
        str(player.get("car") or "").strip()
        for player in players
        if isinstance(player, dict) and player.get("car")
    }
    car_name = (
        humanize_assetto_identifier(next(iter(cars)), "Coche de Assetto Corsa")
        if len(cars) == 1
        else f"Multiclase · {len(cars)} coches"
    )
    series_key = re.sub(
        r"[^a-z0-9]+",
        "-",
        unicodedata.normalize("NFKD", series_name)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower(),
    ).strip("-") or "assetto-corsa"

    named_player_indices = {
        player_index
        for player_index, player in enumerate(players)
        if isinstance(player, dict)
        and clean_assetto_driver_name(str(player.get("name") or "").strip())
    }
    qualifying_positions: dict[int, int] = {}
    for session in sessions:
        if not isinstance(session, dict) or as_int(session.get("type"), 0) != 2:
            continue
        valid_laps = [
            entry
            for entry in session.get("bestLaps", [])
            if isinstance(entry, dict)
            and as_int(entry.get("time"), 0) > 0
            and as_int(entry.get("car"), -1) in named_player_indices
        ]
        for position, entry in enumerate(
            sorted(valid_laps, key=lambda item: as_int(item.get("time"), 0)),
            start=1,
        ):
            qualifying_positions[as_int(entry.get("car"), -1)] = position

    normalized_events: list[dict[str, Any]] = []
    race_index = 0
    for session_index, session in enumerate(sessions):
        if not isinstance(session, dict) or as_int(session.get("type"), 0) != 3:
            continue
        race_index += 1
        finish_order = [
            as_int(value, -1)
            for value in session.get("raceResult", [])
            if as_int(value, -1) in named_player_indices
        ]
        if not finish_order:
            lap_totals = list(session.get("lapstotal") or [])
            finish_order = sorted(
                named_player_indices,
                key=lambda index: (
                    -(as_int(lap_totals[index], 0) if index < len(lap_totals) else 0),
                    index,
                ),
            )
        lap_totals = list(session.get("lapstotal") or [])
        laps = [lap for lap in session.get("laps", []) if isinstance(lap, dict)]
        best_laps = {
            as_int(entry.get("car"), -1): as_int(entry.get("time"), 0)
            for entry in session.get("bestLaps", [])
            if isinstance(entry, dict) and as_int(entry.get("time"), 0) > 0
        }
        max_laps = max(
            [
                as_int(lap_totals[index], 0)
                for index in named_player_indices
                if index < len(lap_totals)
            ]
            or [0]
        )
        results: list[dict[str, Any]] = []
        seen_driver_ids: set[str] = set()
        for player_index in finish_order:
            player = players[player_index]
            if not isinstance(player, dict):
                continue
            name = clean_assetto_driver_name(str(player.get("name") or "").strip())
            if not name:
                continue
            driver_id = assetto_driver_id(name)
            if driver_id in seen_driver_ids:
                continue
            seen_driver_ids.add(driver_id)
            finish_position = len(results) + 1
            driver_laps = [
                lap for lap in laps if as_int(lap.get("car"), -1) == player_index
            ]
            completed_laps = (
                as_int(lap_totals[player_index], 0)
                if player_index < len(lap_totals)
                else len(driver_laps)
            )
            cuts = sum(max(0, as_int(lap.get("cuts"), 0)) for lap in driver_laps)
            best_lap_ms = best_laps.get(player_index, 0)
            player_car = str(player.get("car") or "")
            results.append(
                {
                    "customerId": driver_id,
                    "name": name,
                    "finishPosition": finish_position,
                    "startPosition": qualifying_positions.get(player_index),
                    "incidents": cuts,
                    "lapsComplete": completed_laps,
                    "bestLapTime": best_lap_ms / 1000 if best_lap_ms else None,
                    "iratingChange": None,
                    "safetyRatingChange": None,
                    "status": "Finalizada"
                    if not max_laps or completed_laps >= max_laps
                    else "No finalizó",
                    "classId": player_car,
                    "className": humanize_assetto_identifier(
                        player_car, "Coche de Assetto Corsa"
                    ),
                    "isAi": not is_online_session and player_index != 0,
                }
            )
        if not results:
            continue
        normalized_events.append(
            {
                "platform": "assetto-corsa",
                "source": "assetto-corsa-cm",
                "externalEventId": f"{Path(filename).stem}-race-{session_index + 1}",
                "seriesId": f"ac:{series_key}",
                "seasonId": f"ac:{series_key}:{year}",
                "seriesName": series_name,
                "seasonName": str(year),
                "seasonYear": year,
                "seasonQuarter": 0,
                "carName": car_name,
                "setupType": "Online" if is_online_session else "Local",
                "totalWeeks": 53,
                "raceWeek": iso_week,
                "startTime": event_time.isoformat(timespec="seconds"),
                "track": track_name,
                "layout": layout_name,
                "splitNumber": None,
                "splitTotal": None,
                "strengthOfField": 0,
                "fieldSize": len(results),
                "official": True,
                "results": results,
                "assetto": {
                    "serverName": server_name,
                    "rawTrack": raw_track,
                    "sessionName": str(session.get("name") or "Race"),
                    "durationMinutes": as_int(session.get("duration"), 0),
                    "raceNumber": race_index,
                },
            }
        )
    if not normalized_events:
        raise ValueError("El archivo no contiene ninguna sesión de carrera")
    return normalized_events


def windows_documents_folder() -> Path:
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "Personal")
                return Path(os.path.expandvars(str(value)))
        except (OSError, ImportError):
            pass
    return Path.home() / "Documents"


def suggested_raceroom_results_folder() -> Path:
    return windows_documents_folder() / "My Games" / "SimBin" / (
        "RaceRoom Racing Experience"
    ) / "UserData" / "Log" / "Results"


def raceroom_profile_slug(value: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return ""
    parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
    if parsed.netloc.lower().endswith("raceroom.com"):
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0].lower() == "users":
            candidate = parts[1]
        elif (
            len(parts) >= 3
            and parts[0].lower() == "r3e"
            and parts[1].lower() == "users"
        ):
            candidate = parts[2]
    return unquote(candidate).strip().strip("/")


def fetch_json_url(url: str, timeout: float = 20) -> Any:
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": f"GridScope/{APP_VERSION}"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code == 404:
            raise ValueError("No se ha encontrado ese perfil o resultado de RaceRoom") from error
        raise ValueError(f"RaceRoom ha respondido con el error HTTP {error.code}") from error
    except (URLError, TimeoutError) as error:
        raise ValueError(
            "No se ha podido conectar con RaceRoom. Comprueba Internet y vuelve a intentarlo."
        ) from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("RaceRoom ha devuelto una respuesta que no se puede leer") from error


def fetch_raceroom_profile(slug_or_url: str) -> dict[str, Any]:
    slug = raceroom_profile_slug(slug_or_url)
    if not slug or len(slug) > 120:
        raise ValueError("Indica la URL pública de tu perfil de RaceRoom o su usuario")
    url = f"{RACEROOM_BASE_URL}/r3e/users/{quote(slug)}/career"
    request = Request(url, headers={"User-Agent": f"GridScope/{APP_VERSION}"})
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as error:
        if error.code == 404:
            raise ValueError("No se ha encontrado ese perfil público de RaceRoom") from error
        raise ValueError(f"RaceRoom ha respondido con el error HTTP {error.code}") from error
    except (URLError, TimeoutError) as error:
        raise ValueError(
            "No se ha podido conectar con RaceRoom. Comprueba Internet y vuelve a intentarlo."
        ) from error
    profile_tag = re.search(r"<[^>]*\bprofile-page\b[^>]*>", body, re.IGNORECASE)
    user_id_match = (
        re.search(r'data-user-id=["\'](\d+)', profile_tag.group(0))
        if profile_tag
        else None
    )
    name_match = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.IGNORECASE | re.DOTALL)
    if not user_id_match:
        raise ValueError("La página no parece un perfil público válido de RaceRoom")
    display_name = slug
    if name_match:
        display_name = (
            re.sub(r"<[^>]+>", "", html.unescape(name_match.group(1))).strip() or slug
        )
    return {
        "slug": slug,
        "userId": user_id_match.group(1),
        "displayName": display_name,
        "profileUrl": url,
    }


def normalize_raceroom_result(
    payload: dict[str, Any], owner_user_id: str, minimum_distance: int
) -> dict[str, Any]:
    race_hash = str(payload.get("RaceHash") or "").strip()
    race_rows = payload.get("RaceResult") or []
    if not race_hash or not isinstance(race_rows, list) or not race_rows:
        raise ValueError("El resultado de RaceRoom no contiene una carrera válida")
    starters = [
        row for row in race_rows if isinstance(row, dict) and row.get("Starter", True)
    ] or [row for row in race_rows if isinstance(row, dict)]
    def completed_laps(row: dict[str, Any]) -> int:
        laps = row.get("Laps")
        return len(laps) if isinstance(laps, list) else as_int(laps, 0)

    leader_laps = max((completed_laps(row) for row in starters), default=0)
    finish_timestamp = as_int(payload.get("RaceFinishTime"), 0)
    event_time = (
        datetime.fromtimestamp(finish_timestamp, timezone.utc)
        if finish_timestamp > 0
        else datetime.now(timezone.utc)
    )
    layout_record = payload.get("TrackLayoutId")
    track_record = payload.get("TrackId")
    track = (
        payload.get("Track")
        or payload.get("TrackName")
        or (
            track_record.get("Name")
            if isinstance(track_record, dict)
            else ""
        )
        or (
            layout_record.get("Name")
            if isinstance(layout_record, dict)
            else ""
        )
        or "Circuito RaceRoom"
    )
    layout = (
        payload.get("TrackLayout")
        or payload.get("TrackLayoutName")
        or (
            layout_record.get("Name")
            if isinstance(layout_record, dict)
            else ""
        )
        or ""
    )
    if isinstance(track, dict):
        track = track.get("Name") or track.get("name") or "Circuito RaceRoom"
    if isinstance(layout, dict):
        layout = layout.get("Name") or layout.get("name") or ""
    class_names = sorted(
        {
            str(
                (row.get("CarClass") or {}).get("Name")
                if isinstance(row.get("CarClass"), dict)
                else row.get("CarClassName") or ""
            ).strip()
            for row in starters
        }
        - {""}
    )
    series_name = (
        f"RaceRoom Ranked · {' / '.join(class_names[:2])}"
        if class_names
        else "RaceRoom Ranked"
    )
    results: list[dict[str, Any]] = []
    ordered = sorted(starters, key=lambda item: as_int(item.get("FinishPosition"), 9999))
    for index, row in enumerate(ordered):
        user_id = str(row.get("UserId") or row.get("Id") or row.get("Username") or index)
        name = str(
            row.get("FullName") or row.get("Username") or f"Piloto {index + 1}"
        ).strip()
        laps_complete = completed_laps(row)
        lap_rows = row.get("Laps") if isinstance(row.get("Laps"), list) else []
        valid_lap_times = [
            as_int(lap.get("Time"), 0)
            for lap in lap_rows
            if isinstance(lap, dict)
            and lap.get("Valid", True)
            and as_int(lap.get("Time"), 0) > 0
        ]
        distance_percent = (
            min(100.0, (laps_complete / leader_laps) * 100) if leader_laps else 100.0
        )
        class_info = row.get("CarClass") if isinstance(row.get("CarClass"), dict) else {}
        eligible = distance_percent + 0.0001 >= minimum_distance
        results.append(
            {
                "customerId": f"rr:{user_id}",
                "name": name,
                "finishPosition": max(1, as_int(row.get("FinishPosition"), index + 1)),
                "startPosition": as_int(row.get("StartPosition"), 0) or None,
                "incidents": max(0, as_int(row.get("Incidents"), 0)),
                "lapsComplete": laps_complete,
                "bestLapTime": (
                    min(valid_lap_times) / 1000 if valid_lap_times else None
                ),
                "iratingChange": as_float(row.get("RatingChange")) or 0,
                "safetyRatingChange": (
                    float(row.get("ReputationChange"))
                    if row.get("ReputationChange") is not None
                    else None
                ),
                "status": (
                    "Finalizada"
                    if eligible
                    else f"No puntuable (<{minimum_distance}% de distancia)"
                ),
                "classId": str(class_info.get("Id") or row.get("CarClassId") or ""),
                "className": str(class_info.get("Name") or row.get("CarClassName") or ""),
                "raceRoom": {
                    "ratingBefore": row.get("RatingBefore"),
                    "ratingAfter": row.get("RatingAfter"),
                    "reputationBefore": row.get("ReputationBefore"),
                    "reputationAfter": row.get("ReputationAfter"),
                    "distancePercent": round(distance_percent, 2),
                    "scoringEligible": eligible,
                    "isOwner": user_id == str(owner_user_id),
                },
            }
        )
    return {
        "platform": "raceroom",
        "source": "raceroom-web",
        "externalEventId": race_hash,
        "seriesId": f"rr:{normalized_person_key(series_name)}",
        "seasonId": f"rr:{normalized_person_key(series_name)}:{event_time.year}",
        "seriesName": series_name,
        "seasonName": str(event_time.year),
        "seasonYear": event_time.year,
        "seasonQuarter": 0,
        "carName": " / ".join(class_names) or "Multiclase",
        "setupType": "Ranked",
        "totalWeeks": 53,
        "raceWeek": event_time.isocalendar().week,
        "startTime": event_time.isoformat(timespec="seconds"),
        "track": str(track),
        "layout": str(layout),
        "splitNumber": None,
        "splitTotal": None,
        "strengthOfField": 0,
        "fieldSize": len(results),
        "official": True,
        "results": results,
        "raceRoom": {
            "minimumDistance": minimum_distance,
            "ownerUserId": owner_user_id,
        },
    }


def normalize_iracing_export(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list):
        entries: list[Any] = []
        for item in payload:
            if isinstance(item, list):
                entries.extend(item)
            else:
                entries.append(item)
        search_entries = [
            item
            for item in entries
            if isinstance(item, dict)
            and ("subsession_id" in item or "subsessionId" in item)
        ]
        if search_entries:
            race_count = sum(
                1
                for item in search_entries
                if str(
                    pick_value(
                        item,
                        "event_type_name",
                        "eventTypeName",
                        default="",
                    )
                ).lower()
                in {"race", "carrera"}
                or as_int(pick_value(item, "event_type", "eventType"), 0) == 5
            )
            raise ValueError(
                "Es un índice de búsqueda de iRacing "
                f"({len(search_entries)} sesiones, {race_count} carreras), "
                "no un resultado completo. Abre cada carrera y descarga su "
                "archivo eventresult para importar toda la parrilla"
            )
    if not isinstance(payload, dict):
        raise ValueError("El archivo JSON debe contener un objeto de resultados")
    root = payload
    for wrapper in ("data", "result", "event"):
        candidate = root.get(wrapper)
        if isinstance(candidate, dict) and any(
            key in candidate
            for key in ("subsession_id", "session_results", "results", "series_name")
        ):
            root = candidate
            break

    event_type_name = str(
        pick_value(root, "event_type_name", "eventTypeName", default="")
    ).strip()
    event_type = as_int(pick_value(root, "event_type", "eventType"), 0)
    if (
        event_type_name
        and event_type_name.lower() not in {"race", "carrera"}
    ) or (event_type and event_type != 5):
        raise ValueError(
            f"La sesiÃ³n es {event_type_name or event_type}, no una carrera"
        )

    sessions = pick_value(root, "session_results", "sessionResults", default=[])
    race_session: dict[str, Any] | None = None
    named_sessions: list[str] = []
    if isinstance(sessions, list):
        for session in sessions:
            if not isinstance(session, dict):
                continue
            name = str(
                pick_value(
                    session,
                    "simsession_name",
                    "session_name",
                    "simsessionName",
                    "name",
                    default="",
                )
            ).upper()
            if name:
                named_sessions.append(name)
            if "RACE" in name or "CARRERA" in name:
                race_session = session
        if race_session is None:
            if named_sessions:
                raise ValueError(
                    "El archivo contiene sesiones de "
                    f"{', '.join(named_sessions)}, pero ninguna carrera"
                )
            candidates = [
                session
                for session in sessions
                if isinstance(session, dict)
                and isinstance(pick_value(session, "results", "entries"), list)
            ]
            if candidates:
                race_session = candidates[-1]

    direct_results = pick_value(root, "results", "entries", "drivers")
    results_payload = (
        pick_value(race_session, "results", "entries", default=[])
        if race_session
        else direct_results
    )
    if not isinstance(results_payload, list) or not results_payload:
        raise ValueError("No se han encontrado resultados de carrera en el archivo")

    track_value = pick_value(root, "track", "track_info", "trackInfo", default={})
    if isinstance(track_value, dict):
        track_name = str(
            pick_value(
                track_value,
                "track_name",
                "trackName",
                "name",
                default="Circuito desconocido",
            )
        )
        layout = str(
            pick_value(
                track_value,
                "config_name",
                "configName",
                "layout",
                default="",
            )
        )
    else:
        track_name = str(track_value or "Circuito desconocido")
        layout = str(pick_value(root, "track_config_name", "trackConfigName", default=""))

    week_key = None
    for candidate in ("race_week_num", "raceWeekNum", "race_week", "week"):
        if candidate in root and root[candidate] is not None:
            week_key = candidate
            break
    raw_week = as_int(root.get(week_key), 0) if week_key else 0
    race_week = raw_week + 1 if week_key in {"race_week_num", "raceWeekNum"} else raw_week
    if race_week <= 0:
        raise ValueError("El archivo no indica una semana de temporada válida")

    car_classes = pick_value(root, "car_classes", "carClasses", default=[])
    class_lookup: dict[str, dict[str, Any]] = {}
    if isinstance(car_classes, list):
        for car_class in car_classes:
            if isinstance(car_class, dict):
                class_id = str(
                    pick_value(car_class, "car_class_id", "carClassId", "id", default="")
                )
                if class_id:
                    class_lookup[class_id] = car_class

    normalized_results = []
    for entry in results_payload:
        if not isinstance(entry, dict):
            continue
        customer_id = str(
            pick_value(
                entry,
                "cust_id",
                "customer_id",
                "iracing_cust_id",
                "custId",
                "customerId",
                default="",
            )
        ).strip()
        if not customer_id or not customer_id.isdigit():
            continue
        name = str(
            pick_value(
                entry,
                "display_name",
                "displayName",
                "driver_name",
                "driverName",
                "name",
                default=f"Piloto {customer_id}",
            )
        ).strip()
        finish_position = display_position(
            entry,
            "finish_position_in_class",
            "finishPositionInClass",
            "finish_position",
            "finishPosition",
            "position",
        )
        if finish_position <= 0:
            continue
        start_position = display_position(
            entry,
            "starting_position_in_class",
            "startingPositionInClass",
            "starting_position",
            "startingPosition",
            "start_position",
        )
        class_id = str(
            pick_value(entry, "car_class_id", "carClassId", "class_id", default="")
        )
        class_info = class_lookup.get(class_id, {})
        class_name = str(
            pick_value(
                entry,
                "car_class_name",
                "carClassName",
                "class_name",
                default=pick_value(class_info, "name", "short_name", default=""),
            )
        )
        old_irating = as_int(
            pick_value(entry, "oldi_rating", "old_irating", "oldIRating"), 0
        )
        new_irating = as_int(
            pick_value(entry, "newi_rating", "new_irating", "newIRating"), 0
        )
        irating_change = (
            new_irating - old_irating if old_irating and new_irating else None
        )
        old_safety = as_int(
            pick_value(entry, "old_sub_level", "oldSubLevel"), 0
        )
        new_safety = as_int(
            pick_value(entry, "new_sub_level", "newSubLevel"), 0
        )
        safety_change = (
            (new_safety - old_safety) / 100
            if old_safety and new_safety
            else None
        )
        best_lap = as_float(
            pick_value(entry, "best_lap_time", "bestLapTime")
        )
        if best_lap and best_lap > 1000:
            best_lap /= 10000
        normalized_results.append(
            {
                "customerId": customer_id,
                "name": name,
                "finishPosition": finish_position,
                "startPosition": start_position or None,
                "incidents": as_int(
                    pick_value(entry, "incidents", "incident_count", "incidentCount"),
                    0,
                ),
                "lapsComplete": as_int(
                    pick_value(entry, "laps_complete", "lapsComplete"), 0
                ),
                "bestLapTime": best_lap,
                "iratingChange": irating_change,
                "safetyRatingChange": safety_change,
                "status": str(
                    pick_value(entry, "reason_out", "reasonOut", "status", default="")
                ),
                "classId": class_id,
                "className": class_name,
            }
        )

    if not normalized_results:
        raise ValueError("No se han encontrado pilotos válidos en el resultado")

    first_class_id = normalized_results[0]["classId"]
    class_info = class_lookup.get(first_class_id, {})
    car_name = normalized_results[0]["className"] or str(
        pick_value(class_info, "name", "short_name", default="Coche iRacing")
    )
    series_name = str(
        pick_value(
            root,
            "series_name",
            "seriesName",
            "season_name",
            "seasonName",
            default="Serie iRacing",
        )
    )
    season_name = str(
        pick_value(root, "season_name", "seasonName", default="Temporada iRacing")
    )
    strength_of_field = as_int(
        pick_value(
            class_info,
            "strength_of_field",
            "strengthOfField",
            default=pick_value(
                root,
                "event_strength_of_field",
                "strength_of_field",
                "strengthOfField",
                default=0,
            ),
        ),
        0,
    )
    official_raw = pick_value(root, "official_session", "officialSession", "official", default=True)
    official = (
        official_raw
        if isinstance(official_raw, bool)
        else str(official_raw).lower() not in {"false", "0", "no"}
    )
    external_id = str(
        pick_value(
            root,
            "subsession_id",
            "subsessionId",
            "session_id",
            "sessionId",
            default="",
        )
    ).strip()
    if not external_id:
        digest_source = json.dumps(root, sort_keys=True, ensure_ascii=False).encode("utf-8")
        external_id = f"json-{hashlib.sha256(digest_source).hexdigest()[:20]}"

    session_splits = pick_value(root, "session_splits", "sessionSplits", default=[])
    detected_split_number = None
    detected_split_total = None
    if isinstance(session_splits, list) and session_splits:
        valid_splits = [item for item in session_splits if isinstance(item, dict)]
        detected_split_total = len(valid_splits) or None
        for index, split in enumerate(valid_splits, start=1):
            split_id = str(
                pick_value(split, "subsession_id", "subsessionId", default="")
            )
            if split_id == external_id:
                detected_split_number = index
                break

    return {
        "platform": "iracing",
        "source": "iracing-json",
        "externalEventId": external_id,
        "seriesId": str(pick_value(root, "series_id", "seriesId", default="")).strip(),
        "seasonId": str(pick_value(root, "season_id", "seasonId", default="")).strip(),
        "seriesName": series_name,
        "seasonName": season_name,
        "seasonYear": as_int(
            pick_value(root, "season_year", "seasonYear"), 0
        )
        or season_coordinates(season_name)[0],
        "seasonQuarter": as_int(
            pick_value(root, "season_quarter", "seasonQuarter"), 0
        )
        or season_coordinates(season_name)[1],
        "carName": car_name,
        "setupType": "Setup fijo" if "fixed" in series_name.lower() else "Setup abierto",
        "totalWeeks": max(
            as_int(pick_value(root, "max_weeks", "maxWeeks"), 12),
            race_week,
        ),
        "raceWeek": race_week,
        "startTime": str(
            pick_value(root, "start_time", "startTime", default="")
        ),
        "track": track_name,
        "layout": layout,
        "splitNumber": as_int(
            pick_value(root, "split", "split_number", "splitNumber"), 0
        )
        or detected_split_number,
        "splitTotal": as_int(
            pick_value(root, "num_splits", "split_total", "splitTotal"), 0
        )
        or detected_split_total,
        "strengthOfField": strength_of_field,
        "fieldSize": len(normalized_results),
        "official": official,
        "results": normalized_results,
    }


def iracing_lap_seconds(value: Any) -> float | None:
    raw = as_float(value)
    if raw is None or raw <= 0:
        return None
    return raw / 10000 if raw > 1000 else raw


def extract_iracing_rich_data(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"event": {}, "drivers": {}}
    root = payload
    for wrapper in ("data", "result", "event"):
        candidate = root.get(wrapper)
        if isinstance(candidate, dict):
            root = candidate
            break

    sessions = pick_value(root, "session_results", "sessionResults", default=[])
    race_session = None
    if isinstance(sessions, list):
        for session in sessions:
            if not isinstance(session, dict):
                continue
            session_name = str(
                pick_value(
                    session,
                    "simsession_name",
                    "session_name",
                    "simsessionName",
                    default="",
                )
            ).upper()
            if "RACE" in session_name or "CARRERA" in session_name:
                race_session = session
        if race_session is None:
            candidates = [
                session
                for session in sessions
                if isinstance(session, dict)
                and isinstance(pick_value(session, "results", "entries"), list)
            ]
            race_session = candidates[-1] if candidates else None

    results = (
        pick_value(race_session, "results", "entries", default=[])
        if race_session
        else pick_value(root, "results", "entries", default=[])
    )
    drivers: dict[str, dict[str, Any]] = {}
    if isinstance(results, list):
        for entry in results:
            if not isinstance(entry, dict):
                continue
            customer_id = str(
                pick_value(entry, "cust_id", "customer_id", "custId", default="")
            )
            if not customer_id:
                continue
            livery = pick_value(entry, "livery", default={})
            if not isinstance(livery, dict):
                livery = {}
            old_sub_level = as_int(
                pick_value(entry, "old_sub_level", "oldSubLevel"), 0
            )
            new_sub_level = as_int(
                pick_value(entry, "new_sub_level", "newSubLevel"), 0
            )
            interval_raw = as_int(
                pick_value(entry, "class_interval", "interval"), 0
            )
            drivers[customer_id] = {
                "carId": as_int(pick_value(entry, "car_id", "carId"), 0) or None,
                "carName": str(
                    pick_value(entry, "car_name", "carName", default="")
                ),
                "carNumber": str(
                    pick_value(livery, "car_number", "carNumber", default="")
                ),
                "countryCode": str(
                    pick_value(entry, "country_code", "countryCode", default="")
                ),
                "division": str(
                    pick_value(entry, "division_name", "divisionName", default="")
                ),
                "lapsLed": as_int(
                    pick_value(entry, "laps_lead", "laps_led", "lapsLed"), 0
                ),
                "averageLapTime": iracing_lap_seconds(
                    pick_value(entry, "average_lap", "averageLap")
                ),
                "bestLapNumber": as_int(
                    pick_value(entry, "best_lap_num", "bestLapNum"), 0
                )
                or None,
                "qualifyingLapTime": iracing_lap_seconds(
                    pick_value(entry, "qual_lap_time", "qualLapTime")
                ),
                "championshipPoints": as_int(
                    pick_value(entry, "champ_points", "champPoints"), 0
                ),
                "intervalSeconds": interval_raw / 10000
                if interval_raw > 0
                else (0 if interval_raw == 0 else None),
                "oldIRating": as_int(
                    pick_value(entry, "oldi_rating", "old_irating", "oldIRating"), 0
                )
                or None,
                "newIRating": as_int(
                    pick_value(entry, "newi_rating", "new_irating", "newIRating"), 0
                )
                or None,
                "oldSafetyRating": old_sub_level / 100 if old_sub_level else None,
                "newSafetyRating": new_sub_level / 100 if new_sub_level else None,
                "oldLicenseLevel": as_int(
                    pick_value(entry, "old_license_level", "oldLicenseLevel"), 0
                )
                or None,
                "newLicenseLevel": as_int(
                    pick_value(entry, "new_license_level", "newLicenseLevel"), 0
                )
                or None,
                "cpi": as_float(pick_value(entry, "new_cpi", "newCpi")),
                "weightPenaltyKg": as_float(
                    pick_value(entry, "weight_penalty_kg", "weightPenaltyKg")
                ),
                "dropRace": bool(pick_value(entry, "drop_race", "dropRace", default=False)),
            }

    weather = pick_value(root, "weather", default={})
    if not isinstance(weather, dict):
        weather = {}
    event = {
        "endTime": str(pick_value(root, "end_time", "endTime", default="")),
        "eventLapsComplete": as_int(
            pick_value(root, "event_laps_complete", "eventLapsComplete"), 0
        ),
        "eventAverageLapTime": iracing_lap_seconds(
            pick_value(root, "event_average_lap", "eventAverageLap")
        ),
        "eventBestLapTime": iracing_lap_seconds(
            pick_value(root, "event_best_lap_time", "eventBestLapTime")
        ),
        "cornersPerLap": as_int(
            pick_value(root, "corners_per_lap", "cornersPerLap"), 0
        ),
        "cautions": as_int(pick_value(root, "num_cautions", "numCautions"), 0),
        "cautionLaps": as_int(
            pick_value(root, "num_caution_laps", "numCautionLaps"), 0
        ),
        "leadChanges": as_int(
            pick_value(root, "num_lead_changes", "numLeadChanges"), 0
        ),
        "weather": {
            "temperature": as_float(
                pick_value(weather, "temp_value", "tempValue")
            ),
            "temperatureUnits": as_int(
                pick_value(weather, "temp_units", "tempUnits"), 0
            ),
            "humidity": as_float(
                pick_value(weather, "rel_humidity", "relHumidity")
            ),
            "wind": as_float(pick_value(weather, "wind_value", "windValue")),
            "windUnits": as_int(
                pick_value(weather, "wind_units", "windUnits"), 0
            ),
            "trackWater": as_float(
                pick_value(weather, "track_water", "trackWater")
            ),
            "simulatedStartTime": str(
                pick_value(
                    weather,
                    "simulated_start_time",
                    "simulatedStartTime",
                    default="",
                )
            ),
        },
    }
    return {"event": event, "drivers": drivers}


def extract_raceroom_rich_data(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"event": {}, "drivers": {}}
    drivers: dict[str, dict[str, Any]] = {}
    for row in payload.get("RaceResult") or []:
        if not isinstance(row, dict):
            continue
        user_id = str(row.get("UserId") or row.get("Id") or row.get("Username") or "")
        if not user_id:
            continue
        lap_rows = row.get("Laps") if isinstance(row.get("Laps"), list) else []
        valid_laps = [
            as_int(lap.get("Time"), 0)
            for lap in lap_rows
            if isinstance(lap, dict)
            and lap.get("Valid", True)
            and as_int(lap.get("Time"), 0) > 0
        ]
        best_lap = min(valid_laps) / 1000 if valid_laps else None
        drivers[f"rr:{user_id}"] = {
            "oldIRating": as_float(row.get("RatingBefore")),
            "newIRating": as_float(row.get("RatingAfter")),
            "oldSafetyRating": as_float(row.get("ReputationBefore")),
            "newSafetyRating": as_float(row.get("ReputationAfter")),
            "averageLapTime": None,
            "bestLapNumber": None,
            "qualifyingLapTime": None,
            "championshipPoints": None,
            "intervalSeconds": None,
            "lapsLed": 0,
            "bestLapTime": best_lap,
            "raceRoomDistancePercent": None,
        }
    return {
        "event": {
            "eventLapsComplete": max(
                (
                    len(row.get("Laps"))
                    if isinstance(row.get("Laps"), list)
                    else as_int(row.get("Laps"), 0)
                    for row in payload.get("RaceResult") or []
                    if isinstance(row, dict)
                ),
                default=0,
            ),
            "weather": {},
        },
        "drivers": drivers,
    }


def extract_assetto_corsa_rich_data(
    payload: Any, external_event_id: str
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"event": {}, "drivers": {}}
    players = payload.get("players")
    sessions = payload.get("sessions")
    if not isinstance(players, list) or not isinstance(sessions, list):
        return {"event": {}, "drivers": {}}
    match = re.search(r"-race-(\d+)$", str(external_event_id))
    session_index = as_int(match.group(1), 0) - 1 if match else -1
    session = (
        sessions[session_index]
        if 0 <= session_index < len(sessions)
        and isinstance(sessions[session_index], dict)
        else next(
            (
                item
                for item in sessions
                if isinstance(item, dict) and as_int(item.get("type"), 0) == 3
            ),
            {},
        )
    )
    laps = [lap for lap in session.get("laps", []) if isinstance(lap, dict)]
    drivers: dict[str, dict[str, Any]] = {}
    for player_index, player in enumerate(players):
        if not isinstance(player, dict):
            continue
        name = clean_assetto_driver_name(str(player.get("name") or "").strip())
        if not name:
            continue
        driver_id = assetto_driver_id(name)
        driver_laps = [
            lap for lap in laps if as_int(lap.get("car"), -1) == player_index
        ]
        valid_times = [
            as_int(lap.get("time"), 0) / 1000
            for lap in driver_laps
            if as_int(lap.get("time"), 0) > 0
        ]
        sector_count = max(
            [len(lap.get("sectors") or []) for lap in driver_laps] or [0]
        )
        best_sectors: list[float | None] = []
        for sector_index in range(sector_count):
            sector_values = [
                as_int(lap.get("sectors")[sector_index], 0) / 1000
                for lap in driver_laps
                if isinstance(lap.get("sectors"), list)
                and sector_index < len(lap["sectors"])
                and as_int(lap["sectors"][sector_index], 0) > 0
            ]
            best_sectors.append(min(sector_values) if sector_values else None)
        tyres = sorted(
            {
                str(lap.get("tyre")).strip()
                for lap in driver_laps
                if str(lap.get("tyre") or "").strip()
            }
        )
        average = sum(valid_times) / len(valid_times) if valid_times else None
        deviation = (
            (
                sum((lap_time - average) ** 2 for lap_time in valid_times)
                / len(valid_times)
            )
            ** 0.5
            if average is not None and len(valid_times) > 1
            else None
        )
        drivers[driver_id] = {
            "carName": humanize_assetto_identifier(
                str(player.get("car") or ""), "Coche de Assetto Corsa"
            ),
            "skin": str(player.get("skin") or ""),
            "bestLapTime": min(valid_times) if valid_times else None,
            "averageLapTime": average,
            "lapTimeDeviation": deviation,
            "validLapCount": len(valid_times),
            "drivingTimeMinutes": sum(valid_times) / 60 if valid_times else 0,
            "cuts": sum(max(0, as_int(lap.get("cuts"), 0)) for lap in driver_laps),
            "tyreCompounds": tyres,
            "bestSectorTimes": best_sectors,
            "theoreticalBestLapTime": (
                sum(value for value in best_sectors if value is not None)
                if best_sectors and all(value is not None for value in best_sectors)
                else None
            ),
        }
    raw_ini = payload.get("__raceIni", "")
    is_online_session = assetto_is_online_session(raw_ini)
    lap_totals = [
        max(0, as_int(value, 0)) for value in list(session.get("lapstotal") or [])
    ]
    return {
        "event": {
            "platform": "assetto-corsa",
            "serverName": assetto_ini_value(raw_ini, "SERVER_NAME"),
            "sessionDurationMinutes": as_int(session.get("duration"), 0),
            "sessionName": str(session.get("name") or "Race"),
            "rawTrackId": str(payload.get("track") or ""),
            "onlineSession": is_online_session,
            "aiDriversExcluded": 0 if is_online_session else max(len(players) - 1, 0),
            "eventLapsComplete": max(lap_totals or [0]),
        },
        "drivers": drivers,
    }


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def assetto_percentile_score(value: float | None, field_values: list[float]) -> float | None:
    if value is None or value <= 0:
        return None
    valid_values = [candidate for candidate in field_values if candidate > 0]
    if len(valid_values) < 2:
        return None
    slower = sum(1 for candidate in valid_values if candidate > value)
    equal = sum(1 for candidate in valid_values if candidate == value) - 1
    return clamp_score((slower + max(0, equal) * 0.5) / (len(valid_values) - 1) * 100)


def calculate_assetto_scores(
    result: dict[str, Any],
    event: dict[str, Any],
    field_best_laps: list[float],
    recurrent_score: float | None,
) -> dict[str, Any]:
    field_size = max(1, as_int(event.get("fieldSize"), 1))
    finish_position = max(1, as_int(result.get("finishPosition"), field_size))
    finish_score = (
        clamp_score((field_size - finish_position) / (field_size - 1) * 100)
        if field_size > 1
        else 100.0
    )

    start_position = result.get("startPosition")
    progress_score = None
    if start_position is not None and field_size > 1:
        start_position = max(1, as_int(start_position, finish_position))
        movement = start_position - finish_position
        movement_range = max(start_position - 1, field_size - start_position, 1)
        progress_score = clamp_score(50 + movement / movement_range * 50)

    pace_score = assetto_percentile_score(
        as_float(result.get("bestLapTime")), field_best_laps
    )
    average_lap = as_float(result.get("averageLapTime"))
    lap_deviation = as_float(result.get("lapTimeDeviation"))
    consistency_score = (
        clamp_score(100 - (lap_deviation / average_lap) * 1000)
        if average_lap is not None
        and average_lap > 0
        and lap_deviation is not None
        and as_int(result.get("validLapCount"), 0) >= 2
        else None
    )

    event_laps = max(0, as_int(event.get("eventLapsComplete"), 0))
    completed_laps = max(0, as_int(result.get("lapsComplete"), 0))
    completion_score = (
        clamp_score(completed_laps / event_laps * 100) if event_laps else None
    )
    performance_components = [
        ("finish", finish_score, 0.40),
        ("progress", progress_score, 0.15),
        ("pace", pace_score, 0.15),
        ("consistency", consistency_score, 0.10),
        ("completion", completion_score, 0.10),
        ("recurrent", recurrent_score, 0.10),
    ]
    available_weight = sum(
        weight for _, score, weight in performance_components if score is not None
    )
    performance_score = (
        sum(
            float(score) * weight
            for _, score, weight in performance_components
            if score is not None
        )
        / available_weight
        if available_weight
        else 50.0
    )

    completion_ratio = (
        min(1.0, completed_laps / event_laps) if event_laps else 1.0
    )
    recorded_minutes = max(0.0, as_float(result.get("drivingTimeMinutes")) or 0.0)
    scheduled_minutes = max(
        0.0, as_float(event.get("sessionDurationMinutes")) or 0.0
    )
    effective_minutes = max(
        recorded_minutes,
        scheduled_minutes * completion_ratio,
        min(5.0, scheduled_minutes) if scheduled_minutes else 0.0,
    )
    cuts = max(0, as_int(result.get("incidents"), 0))
    cuts_per_30 = cuts / (effective_minutes / 30) if effective_minutes > 0 else float(cuts)
    cleanliness_score = clamp_score(100 - cuts_per_30 * 12.5)
    grid_score = clamp_score(performance_score * 0.75 + cleanliness_score * 0.25)

    coverage = sum(
        weight for _, score, weight in performance_components if score is not None
    )
    race_confidence = clamp_score(
        coverage * 65
        + min(effective_minutes / 30, 1) * 25
        + min(field_size / 20, 1) * 10
    )
    return {
        "gridScore": round(grid_score, 2),
        "performanceScore": round(performance_score, 2),
        "cleanlinessScore": round(cleanliness_score, 2),
        "scoreConfidence": round(race_confidence, 2),
        "drivingTimeMinutes": round(effective_minutes, 2),
        "cutsPer30Minutes": round(cuts_per_30, 2),
        "scoreComponents": {
            "finish": round(finish_score, 2),
            "progress": round(progress_score, 2) if progress_score is not None else None,
            "pace": round(pace_score, 2) if pace_score is not None else None,
            "consistency": (
                round(consistency_score, 2)
                if consistency_score is not None
                else None
            ),
            "completion": (
                round(completion_score, 2)
                if completion_score is not None
                else None
            ),
            "recurrent": (
                round(recurrent_score, 2) if recurrent_score is not None else None
            ),
        },
    }


def calculate_iracing_scores(
    result: dict[str, Any],
    event: dict[str, Any],
    field_best_laps: list[float],
    recurrent_score: float | None,
) -> dict[str, Any]:
    field_size = max(1, as_int(event.get("fieldSize"), 1))
    finish_position = max(1, as_int(result.get("finishPosition"), field_size))
    finish_score = (
        clamp_score((field_size - finish_position) / (field_size - 1) * 100)
        if field_size > 1
        else 100.0
    )

    start_position = result.get("startPosition")
    progress_score = None
    if start_position is not None and field_size > 1:
        start_position = max(1, as_int(start_position, finish_position))
        movement = start_position - finish_position
        movement_range = max(start_position - 1, field_size - start_position, 1)
        progress_score = clamp_score(50 + movement / movement_range * 50)

    pace_score = assetto_percentile_score(
        as_float(result.get("bestLapTime")), field_best_laps
    )
    event_laps = max(0, as_int(event.get("eventLapsComplete"), 0))
    completed_laps = max(0, as_int(result.get("lapsComplete"), 0))
    completion_score = (
        clamp_score(completed_laps / event_laps * 100) if event_laps else None
    )
    strength_of_field = max(0, as_int(event.get("strengthOfField"), 0))
    sof_score = (
        clamp_score(math.log(max(strength_of_field, 500) / 500, 10) * 100)
        if strength_of_field
        else None
    )
    performance_components = [
        ("finish", finish_score, 0.35),
        ("progress", progress_score, 0.15),
        ("pace", pace_score, 0.15),
        ("completion", completion_score, 0.10),
        ("recurrent", recurrent_score, 0.10),
        ("sof", sof_score, 0.15),
    ]
    available_weight = sum(
        weight for _, score, weight in performance_components if score is not None
    )
    performance_score = (
        sum(
            float(score) * weight
            for _, score, weight in performance_components
            if score is not None
        )
        / available_weight
        if available_weight
        else 50.0
    )

    average_lap = as_float(result.get("averageLapTime"))
    best_lap = as_float(result.get("bestLapTime"))
    lap_seconds = average_lap if average_lap and average_lap > 0 else best_lap
    driving_minutes = (
        lap_seconds * completed_laps / 60
        if lap_seconds is not None and lap_seconds > 0
        else 0.0
    )
    corners_per_lap = max(0, as_int(event.get("cornersPerLap"), 0))
    completed_corners = completed_laps * corners_per_lap
    incidents = max(0, as_int(result.get("incidents"), 0))
    incidents_per_1000_corners = (
        incidents / completed_corners * 1000 if completed_corners else None
    )
    incidents_per_30 = (
        incidents / (driving_minutes / 30) if driving_minutes > 0 else None
    )
    cleanliness_score = (
        clamp_score(100 - incidents_per_1000_corners * 1.5)
        if incidents_per_1000_corners is not None
        else clamp_score(100 - incidents_per_30 * 8)
        if incidents_per_30 is not None
        else clamp_score(100 - incidents * 8)
    )
    grid_score = clamp_score(performance_score * 0.75 + cleanliness_score * 0.25)
    coverage = sum(
        weight for _, score, weight in performance_components if score is not None
    )
    race_confidence = clamp_score(
        coverage * 65
        + min(driving_minutes / 30, 1) * 25
        + min(field_size / 20, 1) * 10
    )
    return {
        "gridScore": round(grid_score, 2),
        "performanceScore": round(performance_score, 2),
        "cleanlinessScore": round(cleanliness_score, 2),
        "scoreConfidence": round(race_confidence, 2),
        "drivingTimeMinutes": round(driving_minutes, 2),
        "incidentsPer1000Corners": (
            round(incidents_per_1000_corners, 2)
            if incidents_per_1000_corners is not None
            else None
        ),
        "incidentsPer30Minutes": (
            round(incidents_per_30, 2) if incidents_per_30 is not None else None
        ),
        "scoreComponents": {
            "finish": round(finish_score, 2),
            "progress": round(progress_score, 2) if progress_score is not None else None,
            "pace": round(pace_score, 2) if pace_score is not None else None,
            "completion": (
                round(completion_score, 2)
                if completion_score is not None
                else None
            ),
            "recurrent": (
                round(recurrent_score, 2) if recurrent_score is not None else None
            ),
            "sof": round(sof_score, 2) if sof_score is not None else None,
        },
    }


def summarize_grid_scores(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    scored = [result for result in results if result.get("gridScore") is not None]
    if not scored:
        return None

    def weighted_average(items: list[dict[str, Any]], key: str) -> float:
        weighted = []
        for item in items:
            minutes = max(0.0, as_float(item.get("drivingTimeMinutes")) or 0.0)
            confidence = max(0.0, as_float(item.get("scoreConfidence")) or 0.0)
            weight = max(0.25, min(minutes / 30, 1.0)) * max(
                0.35, confidence / 100
            )
            weighted.append((float(item[key]), weight))
        total_weight = sum(weight for _, weight in weighted)
        return (
            sum(value * weight for value, weight in weighted) / total_weight
            if total_weight
            else sum(value for value, _ in weighted) / len(weighted)
        )

    opening = scored[: min(3, len(scored))]
    recent = scored[-min(10, len(scored)) :]
    grid_start = weighted_average(opening, "gridScore")
    grid_current = weighted_average(recent, "gridScore")
    clean_start = weighted_average(opening, "cleanlinessScore")
    clean_current = weighted_average(recent, "cleanlinessScore")
    total_minutes = sum(
        max(0.0, as_float(result.get("drivingTimeMinutes")) or 0.0)
        for result in scored
    )
    average_confidence = sum(
        max(0.0, as_float(result.get("scoreConfidence")) or 0.0)
        for result in scored
    ) / len(scored)
    if len(scored) >= 10 and total_minutes >= 180 and average_confidence >= 70:
        confidence = "Alta"
    elif len(scored) >= 4 and total_minutes >= 60 and average_confidence >= 50:
        confidence = "Media"
    else:
        confidence = "Baja"
    return {
        "gridScore": round(grid_current, 2),
        "gridScoreStart": round(grid_start, 2),
        "gridScoreChange": round(grid_current - grid_start, 2),
        "cleanlinessScore": round(clean_current, 2),
        "cleanlinessStart": round(clean_start, 2),
        "cleanlinessChange": round(clean_current - clean_start, 2),
        "confidence": confidence,
        "confidenceScore": round(average_confidence, 2),
        "ratedRaces": len(scored),
        "drivingMinutes": round(total_minutes, 2),
        "windowRaces": len(recent),
    }


def read_ibt_metadata(file_path: Path) -> dict[str, Any]:
    file_size = file_path.stat().st_size
    if file_size < 80:
        raise ValueError("El archivo IBT estÃ¡ vacÃ­o o incompleto")
    with file_path.open("rb") as handle:
        header_data = handle.read(104)
        if len(header_data) < 40:
            raise ValueError("La cabecera IBT no es vÃ¡lida")
        (
            version,
            _status,
            tick_rate,
            _session_update,
            session_info_len,
            session_info_offset,
            num_vars,
            var_header_offset,
            _num_buf,
            _buf_len,
        ) = struct.unpack_from("<10i", header_data)
        if version <= 0 or session_info_len <= 0 or session_info_offset <= 0:
            raise ValueError("La cabecera IBT no contiene informaciÃ³n de sesiÃ³n")
        if (
            session_info_len > 8_000_000
            or session_info_offset + session_info_len > file_size
        ):
            raise ValueError("La informaciÃ³n de sesiÃ³n del IBT estÃ¡ incompleta")
        handle.seek(session_info_offset)
        session_text = handle.read(session_info_len).decode(
            "utf-8", errors="replace"
        ).rstrip("\x00")

        channel_names: list[str] = []
        if 0 < num_vars <= 4096 and 0 < var_header_offset < file_size:
            handle.seek(var_header_offset)
            for _ in range(num_vars):
                var_header = handle.read(144)
                if len(var_header) < 144:
                    break
                name = var_header[16:48].split(b"\x00", 1)[0].decode(
                    "ascii", errors="ignore"
                )
                if name:
                    channel_names.append(name)

    def scalar(key: str) -> str:
        match = re.search(
            rf"(?mi)^[ \t]*(?:-[ \t]*)?{re.escape(key)}:[ \t]*(.+?)[ \t]*$",
            session_text,
        )
        return match.group(1).strip().strip('"') if match else ""

    session_types = [
        value.strip().strip('"')
        for value in re.findall(
            r"(?mi)^[ \t]*(?:-[ \t]*)?SessionType:[ \t]*(.+?)[ \t]*$",
            session_text,
        )
    ]
    normalized_types = {value.lower() for value in session_types}
    if any("race" in value or "carrera" in value for value in normalized_types):
        session_type = "Race"
    elif any("practice" in value for value in normalized_types):
        session_type = "Practice"
    elif any("qual" in value for value in normalized_types):
        session_type = "Qualifying"
    else:
        session_type = session_types[-1] if session_types else "Unknown"

    sample_count = 0
    if len(header_data) >= 104:
        try:
            sample_count = struct.unpack_from("<qddii", header_data, 72)[-1]
        except struct.error:
            sample_count = 0
    return {
        "version": version,
        "tickRate": tick_rate,
        "sampleCount": max(sample_count, 0),
        "channelCount": len(channel_names) or max(num_vars, 0),
        "channels": channel_names,
        "subsessionId": scalar("SubSessionID"),
        "sessionId": scalar("SessionID"),
        "sessionType": session_type,
        "trackName": scalar("TrackDisplayName")
        or scalar("TrackDisplayShortName")
        or scalar("TrackName"),
        "carName": scalar("CarScreenName") or scalar("CarPath"),
    }


class WindowsDataProtector:
    class DataBlob(ctypes.Structure):
        _fields_ = [
            ("size", ctypes.c_uint32),
            ("data", ctypes.POINTER(ctypes.c_ubyte)),
        ]

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("El cifrado de tokens requiere Windows")
        self.crypt32 = ctypes.windll.crypt32
        self.kernel32 = ctypes.windll.kernel32
        self.crypt32.CryptProtectData.restype = ctypes.c_bool
        self.crypt32.CryptUnprotectData.restype = ctypes.c_bool
        self.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        self.kernel32.LocalFree.restype = ctypes.c_void_p

    def protect(self, value: str) -> bytes:
        raw = value.encode("utf-8")
        buffer = ctypes.create_string_buffer(raw)
        input_blob = self.DataBlob(
            len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
        )
        output_blob = self.DataBlob()
        success = self.crypt32.CryptProtectData(
            ctypes.byref(input_blob),
            "GridScope",
            None,
            None,
            None,
            0x1,
            ctypes.byref(output_blob),
        )
        if not success:
            raise OSError("Windows no ha podido cifrar el token")
        try:
            return ctypes.string_at(output_blob.data, output_blob.size)
        finally:
            self.kernel32.LocalFree(output_blob.data)

    def unprotect(self, value: bytes) -> str:
        raw = bytes(value)
        buffer = ctypes.create_string_buffer(raw)
        input_blob = self.DataBlob(
            len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
        )
        output_blob = self.DataBlob()
        success = self.crypt32.CryptUnprotectData(
            ctypes.byref(input_blob),
            None,
            None,
            None,
            None,
            0x1,
            ctypes.byref(output_blob),
        )
        if not success:
            raise OSError("Windows no ha podido descifrar el token")
        try:
            return ctypes.string_at(output_blob.data, output_blob.size).decode("utf-8")
        finally:
            self.kernel32.LocalFree(output_blob.data)


class DataStore:
    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        protector: Any | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.protector = protector
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS leagues (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            series_name TEXT NOT NULL,
            season TEXT NOT NULL,
            car TEXT NOT NULL,
            setup_type TEXT NOT NULL,
            total_weeks INTEGER NOT NULL DEFAULT 12,
            weeks_completed INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS drivers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            iracing_id TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            initials TEXT NOT NULL,
            color TEXT NOT NULL,
            is_demo INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS league_drivers (
            league_id INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            driver_id INTEGER NOT NULL REFERENCES drivers(id) ON DELETE CASCADE,
            PRIMARY KEY (league_id, driver_id)
        );

        CREATE TABLE IF NOT EXISTS driver_stats (
            league_id INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            driver_id INTEGER NOT NULL REFERENCES drivers(id) ON DELETE CASCADE,
            weekly_average REAL NOT NULL DEFAULT 0,
            race_average REAL NOT NULL DEFAULT 0,
            incident_average REAL NOT NULL DEFAULT 0,
            weeks INTEGER NOT NULL DEFAULT 0,
            race_count INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            sof_average INTEGER NOT NULL DEFAULT 0,
            movement INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (league_id, driver_id)
        );

        CREATE TABLE IF NOT EXISTS rounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            week INTEGER NOT NULL,
            track TEXT NOT NULL,
            layout TEXT NOT NULL,
            race_count INTEGER NOT NULL DEFAULT 0,
            position_average REAL NOT NULL DEFAULT 0,
            incident_average REAL NOT NULL DEFAULT 0,
            top_sof INTEGER NOT NULL DEFAULT 0,
            UNIQUE (league_id, week)
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS custom_championships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            platform TEXT NOT NULL,
            series_names_json TEXT NOT NULL DEFAULT '[]',
            start_date TEXT,
            end_date TEXT,
            participant_mode TEXT NOT NULL DEFAULT 'recurrent',
            driver_ids_json TEXT NOT NULL DEFAULT '[]',
            include_owner INTEGER NOT NULL DEFAULT 1,
            minimum_races INTEGER NOT NULL DEFAULT 2,
            ranking_mode TEXT NOT NULL DEFAULT 'all-races',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS archives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            season TEXT NOT NULL,
            created_at TEXT NOT NULL,
            snapshot_json TEXT NOT NULL,
            UNIQUE (league_id, season)
        );

        CREATE TABLE IF NOT EXISTS backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS oauth_sessions (
            state TEXT PRIMARY KEY,
            code_verifier TEXT NOT NULL,
            redirect_uri TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS oauth_tokens (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            access_token BLOB NOT NULL,
            refresh_token BLOB,
            access_expires_at TEXT NOT NULL,
            refresh_expires_at TEXT,
            scope TEXT NOT NULL,
            profile_name TEXT,
            profile_cust_id INTEGER,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS imported_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            source TEXT NOT NULL,
            filename TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            external_event_id TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            UNIQUE (league_id, content_hash),
            UNIQUE (league_id, source, external_event_id)
        );

        CREATE TABLE IF NOT EXISTS race_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            source TEXT NOT NULL,
            external_event_id TEXT NOT NULL,
            series_name TEXT NOT NULL,
            season_name TEXT NOT NULL,
            race_week INTEGER NOT NULL,
            start_time TEXT,
            track TEXT NOT NULL,
            layout TEXT NOT NULL,
            split_number INTEGER,
            split_total INTEGER,
            strength_of_field INTEGER NOT NULL DEFAULT 0,
            field_size INTEGER NOT NULL DEFAULT 0,
            official INTEGER NOT NULL DEFAULT 1,
            imported_at TEXT NOT NULL,
            UNIQUE (league_id, source, external_event_id)
        );

        CREATE TABLE IF NOT EXISTS race_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL REFERENCES race_events(id) ON DELETE CASCADE,
            driver_id INTEGER NOT NULL REFERENCES drivers(id) ON DELETE CASCADE,
            finish_position INTEGER NOT NULL,
            start_position INTEGER,
            incidents INTEGER NOT NULL DEFAULT 0,
            laps_complete INTEGER NOT NULL DEFAULT 0,
            best_lap_time REAL,
            irating_change INTEGER,
            safety_rating_change REAL,
            status TEXT,
            class_id TEXT,
            class_name TEXT,
            scoring_eligible INTEGER NOT NULL DEFAULT 1,
            distance_percent REAL,
            UNIQUE (event_id, driver_id)
        );

        CREATE TABLE IF NOT EXISTS telemetry_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL UNIQUE,
            filename TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            modified_at TEXT NOT NULL,
            subsession_id TEXT,
            session_id TEXT,
            session_type TEXT NOT NULL,
            track_name TEXT,
            car_name TEXT,
            tick_rate INTEGER NOT NULL DEFAULT 0,
            sample_count INTEGER NOT NULL DEFAULT 0,
            channel_count INTEGER NOT NULL DEFAULT 0,
            channels_json TEXT NOT NULL DEFAULT '[]',
            linked_event_id INTEGER REFERENCES race_events(id) ON DELETE SET NULL,
            scanned_at TEXT NOT NULL
        );
        """
        with self.connect() as connection:
            connection.executescript(schema)
            self._migrate_schema(connection)
            self._seed_if_empty(connection)
            unnamed_cleanup = connection.execute(
                """
                SELECT 1 FROM settings
                WHERE key = 'assetto_unnamed_participants_cleanup_v1'
                """
            ).fetchone()
            if not unnamed_cleanup:
                self._remove_assetto_unnamed_results(connection)
                connection.execute(
                    """
                    INSERT INTO settings (key, value)
                    VALUES ('assetto_unnamed_participants_cleanup_v1', '1')
                    """
                )

    def _migrate_schema(self, connection: sqlite3.Connection) -> None:
        league_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(leagues)")
        }
        if "series_id" not in league_columns:
            connection.execute("ALTER TABLE leagues ADD COLUMN series_id TEXT")
        if "season_id" not in league_columns:
            connection.execute("ALTER TABLE leagues ADD COLUMN season_id TEXT")
        if "season_year" not in league_columns:
            connection.execute(
                "ALTER TABLE leagues ADD COLUMN season_year INTEGER NOT NULL DEFAULT 0"
            )
        if "season_quarter" not in league_columns:
            connection.execute(
                "ALTER TABLE leagues ADD COLUMN season_quarter INTEGER NOT NULL DEFAULT 0"
            )
        if "platform" not in league_columns:
            connection.execute(
                "ALTER TABLE leagues ADD COLUMN platform TEXT NOT NULL DEFAULT 'iracing'"
            )
        connection.execute(
            """
            UPDATE leagues
            SET platform = 'iracing'
            WHERE platform IS NULL OR platform = ''
            """
        )
        for league in connection.execute(
            "SELECT id, season, season_year, season_quarter FROM leagues"
        ).fetchall():
            year, quarter = season_coordinates(league["season"])
            if not league["season_year"] or not league["season_quarter"]:
                connection.execute(
                    """
                    UPDATE leagues
                    SET season_year = CASE WHEN season_year = 0 THEN ? ELSE season_year END,
                        season_quarter = CASE WHEN season_quarter = 0 THEN ? ELSE season_quarter END
                    WHERE id = ?
                    """,
                    (year, quarter, league["id"]),
                )
        connection.execute(
            """
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('owner_iracing_id', '')
            """
        )
        existing_iracing_results = connection.execute(
            """
            SELECT 1 FROM race_events event
            JOIN leagues league ON league.id = event.league_id
            WHERE league.platform = 'iracing'
            LIMIT 1
            """
        ).fetchone()
        for key, value in (
            ("selected_simulator", ""),
            ("setup_iracing_complete", "1" if existing_iracing_results else "0"),
            ("setup_assetto_corsa_complete", "0"),
            (
                "assetto_corsa_folder",
                str(
                    Path.home()
                    / "AppData"
                    / "Local"
                    / "AcTools Content Manager"
                    / "Progress"
                    / "Sessions"
                ),
            ),
            ("assetto_corsa_install_folder", ""),
            ("auto_scan_assetto_corsa", "0"),
            ("owner_assetto_corsa_id", ""),
            ("owner_assetto_corsa_name", ""),
            ("owner_assetto_corsa_aliases", "[]"),
            ("setup_raceroom_complete", "0"),
            ("raceroom_profile_slug", ""),
            ("raceroom_profile_url", ""),
            ("owner_raceroom_id", ""),
            ("owner_raceroom_name", ""),
            ("raceroom_results_folder", str(suggested_raceroom_results_folder())),
            ("auto_scan_raceroom", "0"),
            ("raceroom_minimum_distance", "50"),
            ("raceroom_last_sync", ""),
        ):
            connection.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_leagues_iracing_season
            ON leagues(series_id, season_id)
            WHERE series_id IS NOT NULL AND series_id != ''
              AND season_id IS NOT NULL AND season_id != ''
            """
        )
        active_fix = connection.execute(
            "SELECT 1 FROM settings WHERE key = 'active_season_model_v2'"
        ).fetchone()
        if not active_fix:
            current = connection.execute(
                """
                SELECT l.id
                FROM leagues l
                WHERE EXISTS (
                    SELECT 1 FROM race_events re WHERE re.league_id = l.id
                )
                ORDER BY l.season_year DESC, l.season_quarter DESC,
                         (SELECT MAX(re.start_time) FROM race_events re WHERE re.league_id = l.id) DESC,
                         l.id DESC
                LIMIT 1
                """
            ).fetchone()
            if current:
                connection.execute("UPDATE leagues SET active = 0")
                connection.execute(
                    "UPDATE leagues SET active = 1 WHERE id = ?", (current["id"],)
                )
            connection.execute(
                """
                INSERT INTO settings (key, value)
                VALUES ('active_season_model_v2', '1')
                """
            )
        driver_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(drivers)")
        }
        if "is_demo" not in driver_columns:
            connection.execute(
                "ALTER TABLE drivers ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0"
            )
        result_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(race_results)")
        }
        if "scoring_eligible" not in result_columns:
            connection.execute(
                "ALTER TABLE race_results ADD COLUMN scoring_eligible INTEGER NOT NULL DEFAULT 1"
            )
        if "distance_percent" not in result_columns:
            connection.execute(
                "ALTER TABLE race_results ADD COLUMN distance_percent REAL"
            )
        demo_ids = [str(driver[0]) for driver in DEMO_DRIVERS]
        placeholders = ",".join("?" for _ in demo_ids)
        has_imports = connection.execute(
            "SELECT 1 FROM race_events LIMIT 1"
        ).fetchone()
        if not has_imports:
            connection.execute(
                f"UPDATE drivers SET is_demo = 1 WHERE iracing_id IN ({placeholders})",
                demo_ids,
            )

    def _seed_if_empty(self, connection: sqlite3.Connection) -> None:
        exists = connection.execute("SELECT 1 FROM leagues LIMIT 1").fetchone()
        if exists:
            return

        now = utc_now()
        connection.execute(
            """
            INSERT INTO leagues
                (id, name, series_name, season, car, setup_type, total_weeks, weeks_completed, active, created_at)
            VALUES
                (1, ?, ?, ?, ?, ?, 12, 6, 1, ?)
            """,
            (
                "Porsche Cup",
                "iRacing Porsche Cup by CONSPIT",
                "2026 Season 3",
                "Porsche 911 Cup (992.2)",
                "Setup abierto",
                now,
            ),
        )

        for driver in DEMO_DRIVERS:
            (
                iracing_id,
                name,
                initials,
                color,
                weekly_average,
                race_average,
                incident_average,
                weeks,
                race_count,
                wins,
                sof_average,
                movement,
            ) = driver
            cursor = connection.execute(
                """
                INSERT INTO drivers (iracing_id, name, initials, color, is_demo, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (iracing_id, name, initials, color, now),
            )
            driver_id = cursor.lastrowid
            connection.execute(
                "INSERT INTO league_drivers (league_id, driver_id) VALUES (1, ?)",
                (driver_id,),
            )
            connection.execute(
                """
                INSERT INTO driver_stats
                    (league_id, driver_id, weekly_average, race_average, incident_average,
                     weeks, race_count, wins, sof_average, movement)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    driver_id,
                    weekly_average,
                    race_average,
                    incident_average,
                    weeks,
                    race_count,
                    wins,
                    sof_average,
                    movement,
                ),
            )

        connection.executemany(
            """
            INSERT INTO rounds
                (league_id, week, track, layout, race_count, position_average, incident_average, top_sof)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?)
            """,
            DEMO_ROUNDS,
        )

        connection.executemany(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            [
                ("ranking_mode", "weekly"),
                ("minimum_participation", "50"),
                ("tiebreaker", "incidents"),
                ("oauth_status", "disconnected"),
                ("oauth_client_id", ""),
                ("import_folder", str(Path.home() / "Downloads")),
                ("auto_scan_imports", "0"),
                ("telemetry_folder", ""),
                ("auto_scan_telemetry", "0"),
                ("owner_iracing_id", ""),
                ("selected_simulator", ""),
                ("setup_iracing_complete", "0"),
                ("setup_assetto_corsa_complete", "0"),
                (
                    "assetto_corsa_folder",
                    str(
                        Path.home()
                        / "AppData"
                        / "Local"
                        / "AcTools Content Manager"
                        / "Progress"
                        / "Sessions"
                    ),
                ),
                ("assetto_corsa_install_folder", ""),
                ("auto_scan_assetto_corsa", "0"),
                ("owner_assetto_corsa_id", ""),
                ("owner_assetto_corsa_name", ""),
                ("owner_assetto_corsa_aliases", "[]"),
                ("setup_raceroom_complete", "0"),
                ("raceroom_profile_slug", ""),
                ("raceroom_profile_url", ""),
                ("owner_raceroom_id", ""),
                ("owner_raceroom_name", ""),
                ("raceroom_results_folder", str(suggested_raceroom_results_folder())),
                ("auto_scan_raceroom", "0"),
                ("raceroom_minimum_distance", "50"),
                ("raceroom_last_sync", ""),
            ],
        )

    def _resolve_import_league(
        self, connection: sqlite3.Connection, normalized: dict[str, Any]
    ) -> tuple[int, bool]:
        platform = str(normalized.get("platform") or "iracing")
        series_id = normalized.get("seriesId") or None
        season_id = normalized.get("seasonId") or None
        league = None
        if series_id and season_id:
            league = connection.execute(
                """
                SELECT * FROM leagues
                WHERE platform = ? AND series_id = ? AND season_id = ?
                LIMIT 1
                """,
                (platform, series_id, season_id),
            ).fetchone()
        if not league:
            league = connection.execute(
                """
                SELECT * FROM leagues
                WHERE platform = ?
                  AND LOWER(series_name) = LOWER(?)
                  AND LOWER(season) = LOWER(?)
                ORDER BY id
                LIMIT 1
                """,
                (platform, normalized["seriesName"], normalized["seasonName"]),
            ).fetchone()

        created = False
        if not league:
            placeholder = connection.execute(
                """
                SELECT l.* FROM leagues l
                WHERE l.platform = ?
                  AND NOT EXISTS (
                    SELECT 1 FROM race_events re WHERE re.league_id = l.id
                  )
                  AND (
                    EXISTS (
                    SELECT 1 FROM league_drivers ld
                    JOIN drivers d ON d.id = ld.driver_id
                    WHERE ld.league_id = l.id AND d.is_demo = 1
                    )
                    OR l.platform IN ('assetto-corsa', 'raceroom')
                  )
                ORDER BY l.active DESC, l.id
                LIMIT 1
                """,
                (platform,),
            ).fetchone()
            if placeholder:
                league_id = placeholder["id"]
                connection.execute(
                    """
                    UPDATE leagues
                    SET name = ?, series_name = ?, season = ?, car = ?,
                        setup_type = ?, total_weeks = ?, series_id = ?, season_id = ?,
                        season_year = ?, season_quarter = ?, platform = ?
                    WHERE id = ?
                    """,
                    (
                        normalized["seriesName"],
                        normalized["seriesName"],
                        normalized["seasonName"],
                        normalized["carName"],
                        normalized["setupType"],
                        normalized["totalWeeks"],
                        series_id,
                        season_id,
                        normalized["seasonYear"],
                        normalized["seasonQuarter"],
                        platform,
                        league_id,
                    ),
                )
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO leagues
                        (name, series_name, season, car, setup_type, total_weeks,
                         weeks_completed, active, created_at, series_id, season_id,
                         season_year, season_quarter, platform)
                    VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized["seriesName"],
                        normalized["seriesName"],
                        normalized["seasonName"],
                        normalized["carName"],
                        normalized["setupType"],
                        normalized["totalWeeks"],
                        utc_now(),
                        series_id,
                        season_id,
                        normalized["seasonYear"],
                        normalized["seasonQuarter"],
                        platform,
                    ),
                )
                league_id = cursor.lastrowid
                created = True
        else:
            league_id = league["id"]
            connection.execute(
                """
                UPDATE leagues
                SET name = ?, series_name = ?, season = ?, car = ?,
                    setup_type = ?, total_weeks = MAX(total_weeks, ?),
                    series_id = COALESCE(NULLIF(series_id, ''), ?),
                    season_id = COALESCE(NULLIF(season_id, ''), ?),
                    season_year = CASE WHEN ? > 0 THEN ? ELSE season_year END,
                    season_quarter = CASE WHEN ? > 0 THEN ? ELSE season_quarter END
                WHERE id = ?
                """,
                (
                    normalized["seriesName"],
                    normalized["seriesName"],
                    normalized["seasonName"],
                    normalized["carName"],
                    normalized["setupType"],
                    normalized["totalWeeks"],
                    series_id,
                    season_id,
                    normalized["seasonYear"],
                    normalized["seasonYear"],
                    normalized["seasonQuarter"],
                    normalized["seasonQuarter"],
                    league_id,
                ),
            )
        return int(league_id), created

    def set_active_league(self, league_id: int) -> dict[str, Any]:
        with self.connect() as connection:
            league = connection.execute(
                "SELECT id, series_name, season, platform FROM leagues WHERE id = ?",
                (league_id,),
            ).fetchone()
            if not league:
                raise ValueError("La serie seleccionada no existe")
            connection.execute("UPDATE leagues SET active = 0")
            connection.execute(
                "UPDATE leagues SET active = 1 WHERE id = ?", (league_id,)
            )
            connection.execute(
                """
                INSERT INTO settings (key, value) VALUES ('selected_simulator', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (league["platform"],),
            )
        return {
            "id": league["id"],
            "seriesName": league["series_name"],
            "season": league["season"],
            "platform": league["platform"],
        }

    def get_state(self) -> dict[str, Any]:
        with self.connect() as connection:
            league_row = connection.execute(
                "SELECT * FROM leagues WHERE active = 1 ORDER BY id LIMIT 1"
            ).fetchone()
            if not league_row:
                raise RuntimeError("No hay una liga activa")

            league_id = league_row["id"]
            platform = str(league_row["platform"] or "iracing")
            league_rows = connection.execute(
                """
                SELECT l.*,
                       (SELECT COUNT(*) FROM race_events re WHERE re.league_id = l.id) AS race_count,
                       (SELECT COUNT(*) FROM league_drivers ld WHERE ld.league_id = l.id) AS driver_count,
                       (SELECT MAX(re.start_time) FROM race_events re WHERE re.league_id = l.id) AS last_race_time
                FROM leagues l
                WHERE l.platform = ?
                ORDER BY l.active DESC, l.created_at DESC, l.id DESC
                """,
                (platform,),
            ).fetchall()
            series_logos: dict[int, str] = {}
            latest_imports = connection.execute(
                """
                SELECT imported.league_id, imported.raw_json
                FROM imported_files imported
                JOIN (
                    SELECT league_id, MAX(id) AS latest_id
                    FROM imported_files
                    GROUP BY league_id
                ) latest ON latest.latest_id = imported.id
                """
            ).fetchall()
            for imported in latest_imports:
                series_logos[int(imported["league_id"])] = extract_series_logo(
                    imported["raw_json"]
                )
            track_ids_by_week: dict[int, int] = {}
            imported_tracks = connection.execute(
                """
                SELECT event.race_week, imported.raw_json
                FROM race_events event
                JOIN imported_files imported
                  ON imported.league_id = event.league_id
                 AND imported.source = event.source
                 AND imported.external_event_id = event.external_event_id
                WHERE event.league_id = ?
                ORDER BY event.start_time, event.id
                """,
                (league_id,),
            ).fetchall()
            for imported in imported_tracks:
                track_id = extract_track_id(imported["raw_json"])
                if track_id > 0:
                    track_ids_by_week[int(imported["race_week"])] = track_id
            current_league_id = max(
                league_rows,
                key=lambda row: (
                    row["season_year"] or 0,
                    row["season_quarter"] or 0,
                    row["last_race_time"] or "",
                    row["id"],
                ),
            )["id"]
            settings = {
                row["key"]: row["value"]
                for row in connection.execute("SELECT key, value FROM settings").fetchall()
            }
            owner_iracing_id = (
                settings.get("owner_assetto_corsa_id", "")
                if platform == "assetto-corsa"
                else settings.get("owner_raceroom_id", "")
                if platform == "raceroom"
                else settings.get("owner_iracing_id", "")
            )
            driver_rows = connection.execute(
                """
                SELECT d.iracing_id, d.name, d.initials, d.color,
                       s.weekly_average, s.race_average, s.incident_average,
                       s.weeks, s.race_count, s.wins, s.sof_average, s.movement,
                       (
                           SELECT COUNT(*)
                           FROM race_results rival_result
                           JOIN race_events shared_event
                             ON shared_event.id = rival_result.event_id
                           JOIN race_results owner_result
                             ON owner_result.event_id = shared_event.id
                           JOIN drivers owner
                             ON owner.id = owner_result.driver_id
                            AND owner.iracing_id = ?
                           WHERE rival_result.driver_id = d.id
                             AND shared_event.league_id = ld.league_id
                       ) AS meetings_with_owner
                FROM league_drivers ld
                JOIN drivers d ON d.id = ld.driver_id
                JOIN driver_stats s ON s.driver_id = d.id AND s.league_id = ld.league_id
                WHERE ld.league_id = ?
                """,
                (owner_iracing_id, league_id),
            ).fetchall()
            round_rows = connection.execute(
                "SELECT * FROM rounds WHERE league_id = ? ORDER BY week",
                (league_id,),
            ).fetchall()
            archive_count = connection.execute(
                "SELECT COUNT(*) FROM archives WHERE league_id = ?",
                (league_id,),
            ).fetchone()[0]
            import_count = connection.execute(
                "SELECT COUNT(*) FROM imported_files WHERE league_id = ?",
                (league_id,),
            ).fetchone()[0]
            event_count = connection.execute(
                "SELECT COUNT(*) FROM race_events WHERE league_id = ?",
                (league_id,),
            ).fetchone()[0]
            telemetry_counts = connection.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN linked_event_id IS NOT NULL THEN 1 ELSE 0 END) AS linked,
                       SUM(CASE WHEN LOWER(session_type) = 'practice' THEN 1 ELSE 0 END) AS practice
                FROM telemetry_files
                """
            ).fetchone()
            demo_count = connection.execute(
                """
                SELECT COUNT(*) FROM league_drivers ld
                JOIN drivers d ON d.id = ld.driver_id
                WHERE ld.league_id = ? AND d.is_demo = 1
                """,
                (league_id,),
            ).fetchone()[0]
            last_backup = connection.execute(
                "SELECT created_at FROM backups ORDER BY id DESC LIMIT 1"
            ).fetchone()

        oauth = self.get_oauth_status()
        league = {
            "id": league_row["id"],
            "name": league_row["name"],
            "seriesName": league_row["series_name"],
            "season": league_row["season"],
            "car": league_row["car"],
            "setupType": league_row["setup_type"],
            "totalWeeks": league_row["total_weeks"],
            "weeksCompleted": league_row["weeks_completed"],
            "isCurrent": league_row["id"] == current_league_id,
            "seriesLogo": series_logos.get(int(league_row["id"]), ""),
            "platform": platform,
        }
        drivers = [
            {
                "id": row["iracing_id"],
                "name": row["name"],
                "initials": row["initials"],
                "color": row["color"],
                "weekly": row["weekly_average"],
                "races": row["race_average"],
                "incidents": row["incident_average"],
                "weeks": row["weeks"],
                "racesCount": row["race_count"],
                "wins": row["wins"],
                "sof": row["sof_average"],
                "move": row["movement"],
                "meetingsWithOwner": row["meetings_with_owner"],
            }
            for row in driver_rows
        ]
        rounds = [
            {
                "week": row["week"],
                "track": row["track"],
                "layout": row["layout"],
                "races": row["race_count"],
                "average": row["position_average"],
                "incidents": row["incident_average"],
                "sof": row["top_sof"],
                "trackId": track_ids_by_week.get(int(row["week"]), 0),
            }
            for row in round_rows
        ]
        return {
            "league": league,
            "leagues": [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "seriesName": row["series_name"],
                    "season": row["season"],
                    "car": row["car"],
                    "setupType": row["setup_type"],
                    "weeksCompleted": row["weeks_completed"],
                    "totalWeeks": row["total_weeks"],
                    "raceCount": row["race_count"],
                    "driverCount": row["driver_count"],
                    "active": row["id"] == league_id,
                    "isCurrent": row["id"] == current_league_id,
                    "seriesLogo": series_logos.get(int(row["id"]), ""),
                    "platform": row["platform"],
                }
                for row in league_rows
            ],
            "drivers": drivers,
            "rounds": rounds,
            "settings": {
                "rankingMode": settings.get("ranking_mode", "weekly"),
                "minimumParticipation": int(settings.get("minimum_participation", "50")),
                "tiebreaker": settings.get("tiebreaker", "incidents"),
                "oauthStatus": "connected" if oauth["connected"] else "disconnected",
                "importFolder": settings.get(
                    "import_folder", str(Path.home() / "Downloads")
                ),
                "autoScanImports": settings.get("auto_scan_imports", "0") == "1",
                "telemetryFolder": settings.get("telemetry_folder", ""),
                "autoScanTelemetry": settings.get(
                    "auto_scan_telemetry", "0"
                )
                == "1",
                "ownerIracingId": owner_iracing_id,
                "ownerDriverId": owner_iracing_id,
                "ownerDisplayName": (
                    settings.get("owner_assetto_corsa_name", "")
                    if platform == "assetto-corsa"
                    else settings.get("owner_raceroom_name", "")
                    if platform == "raceroom"
                    else settings.get("owner_iracing_id", "")
                ),
                "ownerAliases": (
                    assetto_aliases_from_settings(settings)
                    if platform == "assetto-corsa"
                    else []
                ),
                "platform": platform,
                "assettoCorsaFolder": settings.get("assetto_corsa_folder", ""),
                "assettoCorsaInstallFolder": (
                    settings.get("assetto_corsa_install_folder", "")
                    or str(
                        detect_assetto_corsa_installation() or ""
                    )
                ),
                "autoScanAssettoCorsa": settings.get(
                    "auto_scan_assetto_corsa", "0"
                )
                == "1",
                "raceRoomProfileUrl": settings.get("raceroom_profile_url", ""),
                "raceRoomResultsFolder": settings.get(
                    "raceroom_results_folder", str(suggested_raceroom_results_folder())
                ),
                "autoScanRaceRoom": settings.get("auto_scan_raceroom", "0") == "1",
                "raceRoomMinimumDistance": int(
                    settings.get("raceroom_minimum_distance", "50")
                ),
                "raceRoomLastSync": settings.get("raceroom_last_sync", ""),
            },
            "oauth": oauth,
            "demoMode": bool(demo_count),
            "storage": {
                "archiveCount": archive_count,
                "raceCount": event_count
                if event_count
                else sum(round_item["races"] for round_item in rounds),
                "importCount": import_count,
                "telemetryCount": telemetry_counts["total"] or 0,
                "linkedTelemetryCount": telemetry_counts["linked"] or 0,
                "practiceTelemetryCount": telemetry_counts["practice"] or 0,
                "lastBackup": last_backup["created_at"] if last_backup else None,
            },
        }

    def add_driver(self, iracing_id: str) -> dict[str, Any]:
        normalized_id = iracing_id.strip()
        if not normalized_id.isdigit() or not 3 <= len(normalized_id) <= 12:
            raise ValueError("El ID de iRacing debe contener entre 3 y 12 números")

        palette = ["orange", "teal", "blue", "red", "violet", "gold", "slate", "green"]
        with self.connect() as connection:
            league = connection.execute(
                "SELECT id FROM leagues WHERE active = 1 ORDER BY id LIMIT 1"
            ).fetchone()
            if not league:
                raise RuntimeError("No hay una liga activa")
            existing = connection.execute(
                "SELECT id FROM drivers WHERE iracing_id = ?",
                (normalized_id,),
            ).fetchone()
            if existing:
                linked = connection.execute(
                    "SELECT 1 FROM league_drivers WHERE league_id = ? AND driver_id = ?",
                    (league["id"], existing["id"]),
                ).fetchone()
                if linked:
                    raise ValueError("Este piloto ya pertenece a la liga")
                driver_id = existing["id"]
            else:
                count = connection.execute("SELECT COUNT(*) FROM drivers").fetchone()[0]
                cursor = connection.execute(
                    """
                    INSERT INTO drivers (iracing_id, name, initials, color, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        normalized_id,
                        f"Piloto {normalized_id}",
                        "ID",
                        palette[count % len(palette)],
                        utc_now(),
                    ),
                )
                driver_id = cursor.lastrowid

            connection.execute(
                "INSERT INTO league_drivers (league_id, driver_id) VALUES (?, ?)",
                (league["id"], driver_id),
            )
            connection.execute(
                """
                INSERT INTO driver_stats
                    (league_id, driver_id, weekly_average, race_average, incident_average,
                     weeks, race_count, wins, sof_average, movement)
                VALUES (?, ?, 0, 0, 0, 0, 0, 0, 0, 0)
                """,
                (league["id"], driver_id),
            )

        return {"iracingId": normalized_id, "pendingValidation": True}

    def import_iracing_result(
        self,
        filename: str,
        payload: Any,
        include_all_drivers: bool = True,
        replace_demo: bool = True,
    ) -> dict[str, Any]:
        normalized = normalize_iracing_export(payload)
        return self._import_normalized_result(
            filename,
            payload,
            normalized,
            include_all_drivers=include_all_drivers,
            replace_demo=replace_demo,
        )

    def _import_normalized_result(
        self,
        filename: str,
        payload: Any,
        normalized: dict[str, Any],
        include_all_drivers: bool = True,
        replace_demo: bool = True,
    ) -> dict[str, Any]:
        if not normalized["official"]:
            raise ValueError("El archivo corresponde a una sesión no oficial")
        raw_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        content_hash = hashlib.sha256(
            f"{normalized['externalEventId']}\0{raw_json}".encode("utf-8")
        ).hexdigest()
        palette = ["orange", "teal", "blue", "red", "violet", "gold", "slate", "green"]

        with self.connect() as connection:
            league_id, league_created = self._resolve_import_league(
                connection, normalized
            )
            duplicate = connection.execute(
                """
                SELECT id FROM imported_files
                WHERE league_id = ?
                  AND (content_hash = ? OR (source = ? AND external_event_id = ?))
                """,
                (
                    league_id,
                    content_hash,
                    normalized["source"],
                    normalized["externalEventId"],
                ),
            ).fetchone()
            if duplicate:
                connection.execute(
                    """
                    UPDATE race_events
                    SET split_number = COALESCE(?, split_number),
                        split_total = COALESCE(?, split_total),
                        strength_of_field = CASE
                            WHEN ? > 0 THEN ? ELSE strength_of_field END,
                        field_size = CASE
                            WHEN ? > 0 THEN ? ELSE field_size END
                    WHERE league_id = ? AND source = ? AND external_event_id = ?
                    """,
                    (
                        normalized["splitNumber"],
                        normalized["splitTotal"],
                        normalized["strengthOfField"],
                        normalized["strengthOfField"],
                        normalized["fieldSize"],
                        normalized["fieldSize"],
                        league_id,
                        normalized["source"],
                        normalized["externalEventId"],
                    ),
                )
                return {
                    "duplicate": True,
                    "event": normalized,
                    "leagueId": league_id,
                    "leagueCreated": False,
                    "message": "Esta carrera ya estaba importada",
                }

            if replace_demo:
                demo_driver_ids = [
                    row["id"]
                    for row in connection.execute(
                        """
                        SELECT d.id FROM drivers d
                        JOIN league_drivers ld ON ld.driver_id = d.id
                        WHERE ld.league_id = ? AND d.is_demo = 1
                        """,
                        (league_id,),
                    ).fetchall()
                ]
                if demo_driver_ids:
                    placeholders = ",".join("?" for _ in demo_driver_ids)
                    connection.execute(
                        f"DELETE FROM league_drivers WHERE league_id = ? AND driver_id IN ({placeholders})",
                        (league_id, *demo_driver_ids),
                    )
                    connection.execute(
                        f"DELETE FROM drivers WHERE id IN ({placeholders})",
                        demo_driver_ids,
                    )
                    connection.execute(
                        "DELETE FROM rounds WHERE league_id = ?", (league_id,)
                    )

            event_cursor = connection.execute(
                """
                INSERT INTO race_events
                    (league_id, source, external_event_id, series_name, season_name,
                     race_week, start_time, track, layout, split_number, split_total,
                     strength_of_field, field_size, official, imported_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    league_id,
                    normalized["source"],
                    normalized["externalEventId"],
                    normalized["seriesName"],
                    normalized["seasonName"],
                    normalized["raceWeek"],
                    normalized["startTime"],
                    normalized["track"],
                    normalized["layout"],
                    normalized["splitNumber"],
                    normalized["splitTotal"],
                    normalized["strengthOfField"],
                    normalized["fieldSize"],
                    1,
                    utc_now(),
                ),
            )
            event_id = event_cursor.lastrowid
            driver_count = connection.execute("SELECT COUNT(*) FROM drivers").fetchone()[0]
            linked_count = 0
            results_to_import = [dict(result) for result in normalized["results"]]
            if normalized.get("platform") == "assetto-corsa":
                results_to_import = [
                    result for result in results_to_import if not result.get("isAi")
                ]
                assetto_settings = {
                    row["key"]: row["value"]
                    for row in connection.execute(
                        """
                        SELECT key, value FROM settings
                        WHERE key IN (
                            'owner_assetto_corsa_name',
                            'owner_assetto_corsa_aliases'
                        )
                        """
                    ).fetchall()
                }
                owner_aliases = assetto_aliases_from_settings(assetto_settings)
                if owner_aliases:
                    alias_keys = {
                        normalized_person_key(alias) for alias in owner_aliases
                    }
                    canonical_id = assetto_driver_id(owner_aliases[0])
                    for result in results_to_import:
                        if normalized_person_key(result["name"]) in alias_keys:
                            result["customerId"] = canonical_id
                            result["name"] = owner_aliases[0]
                    consolidated: dict[str, dict[str, Any]] = {}
                    for result in results_to_import:
                        current = consolidated.get(result["customerId"])
                        if (
                            current is None
                            or result["finishPosition"] < current["finishPosition"]
                        ):
                            consolidated[result["customerId"]] = result
                    results_to_import = list(consolidated.values())

            for result in results_to_import:
                driver = connection.execute(
                    "SELECT id FROM drivers WHERE iracing_id = ?",
                    (result["customerId"],),
                ).fetchone()
                if driver:
                    driver_id = driver["id"]
                    connection.execute(
                        """
                        UPDATE drivers
                        SET name = ?, initials = ?, is_demo = 0
                        WHERE id = ?
                        """,
                        (
                            result["name"],
                            driver_initials(result["name"]),
                            driver_id,
                        ),
                    )
                else:
                    cursor = connection.execute(
                        """
                        INSERT INTO drivers
                            (iracing_id, name, initials, color, is_demo, created_at)
                        VALUES (?, ?, ?, ?, 0, ?)
                        """,
                        (
                            result["customerId"],
                            result["name"],
                            driver_initials(result["name"]),
                            palette[driver_count % len(palette)],
                            utc_now(),
                        ),
                    )
                    driver_id = cursor.lastrowid
                    driver_count += 1

                already_linked = connection.execute(
                    """
                    SELECT 1 FROM league_drivers
                    WHERE league_id = ? AND driver_id = ?
                    """,
                    (league_id, driver_id),
                ).fetchone()
                if include_all_drivers and not already_linked:
                    connection.execute(
                        "INSERT INTO league_drivers (league_id, driver_id) VALUES (?, ?)",
                        (league_id, driver_id),
                    )
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO driver_stats
                            (league_id, driver_id, weekly_average, race_average,
                             incident_average, weeks, race_count, wins, sof_average, movement)
                        VALUES (?, ?, 0, 0, 0, 0, 0, 0, 0, 0)
                        """,
                        (league_id, driver_id),
                    )
                    already_linked = True
                if already_linked:
                    linked_count += 1

                connection.execute(
                    """
                    INSERT INTO race_results
                        (event_id, driver_id, finish_position, start_position, incidents,
                         laps_complete, best_lap_time, irating_change, safety_rating_change,
                         status, class_id, class_name, scoring_eligible, distance_percent)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        driver_id,
                        result["finishPosition"],
                        result["startPosition"],
                        result["incidents"],
                        result["lapsComplete"],
                        result["bestLapTime"],
                        result["iratingChange"],
                        result["safetyRatingChange"],
                        result["status"],
                        result["classId"],
                        result["className"],
                        1
                        if result.get("raceRoom", {}).get("scoringEligible", True)
                        else 0,
                        result.get("raceRoom", {}).get("distancePercent"),
                    ),
                )

            connection.execute(
                """
                INSERT INTO imported_files
                    (league_id, source, filename, content_hash, external_event_id,
                     raw_json, imported_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    league_id,
                    normalized["source"],
                    Path(filename).name or "resultado.json",
                    content_hash,
                    normalized["externalEventId"],
                    raw_json,
                    utc_now(),
                ),
            )
            self._recalculate_league(connection, league_id)
            connection.execute(
                """
                UPDATE leagues
                SET series_name = ?, season = ?, car = ?, setup_type = ?,
                    total_weeks = MAX(total_weeks, ?),
                    weeks_completed = MAX(weeks_completed, ?),
                    season_year = CASE WHEN ? > 0 THEN ? ELSE season_year END,
                    season_quarter = CASE WHEN ? > 0 THEN ? ELSE season_quarter END
                WHERE id = ?
                """,
                (
                    normalized["seriesName"],
                    normalized["seasonName"],
                    normalized["carName"],
                    normalized["setupType"],
                    normalized["totalWeeks"],
                    normalized["raceWeek"],
                    normalized["seasonYear"],
                    normalized["seasonYear"],
                    normalized["seasonQuarter"],
                    normalized["seasonQuarter"],
                    league_id,
                ),
            )
            active_league = connection.execute(
                "SELECT id FROM leagues WHERE active = 1 ORDER BY id LIMIT 1"
            ).fetchone()
            if not active_league:
                connection.execute(
                    "UPDATE leagues SET active = 1 WHERE id = ?", (league_id,)
                )

        return {
            "duplicate": False,
            "event": normalized,
            "leagueId": league_id,
            "leagueCreated": league_created,
            "linkedDrivers": linked_count,
            "message": f"Carrera importada con {len(normalized['results'])} pilotos",
        }

    def save_import_folder(
        self, folder_value: str, auto_scan: bool
    ) -> dict[str, Any]:
        candidate = Path(folder_value.strip()).expanduser()
        if not candidate.is_absolute():
            raise ValueError("La carpeta debe indicarse con una ruta completa")
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as error:
            raise ValueError("La carpeta indicada no existe") from error
        if not resolved.is_dir():
            raise ValueError("La ruta indicada no es una carpeta")
        with self.connect() as connection:
            for key, value in (
                ("import_folder", str(resolved)),
                ("auto_scan_imports", "1" if auto_scan else "0"),
            ):
                connection.execute(
                    """
                    INSERT INTO settings (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (key, value),
                )
        return {"folder": str(resolved), "autoScan": auto_scan}

    def scan_import_folder(self) -> dict[str, Any]:
        with self.connect() as connection:
            settings = {
                row["key"]: row["value"]
                for row in connection.execute(
                    """
                    SELECT key, value FROM settings
                    WHERE key IN ('import_folder', 'auto_scan_imports')
                    """
                ).fetchall()
            }
        folder = Path(
            settings.get("import_folder", str(Path.home() / "Downloads"))
        )
        if not folder.exists() or not folder.is_dir():
            raise ValueError("La carpeta de importación no existe")

        imported = 0
        duplicates = 0
        ignored = 0
        errors: list[dict[str, str]] = []
        files = sorted(
            folder.glob("*.json"),
            key=lambda item: item.stat().st_mtime,
        )
        for file_path in files[:500]:
            try:
                if file_path.stat().st_size > 12_000_000:
                    ignored += 1
                    continue
                payload = json.loads(file_path.read_text(encoding="utf-8-sig"))
                result = self.import_iracing_result(
                    file_path.name,
                    payload,
                    include_all_drivers=True,
                    replace_demo=True,
                )
                if result["duplicate"]:
                    duplicates += 1
                else:
                    imported += 1
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                ignored += 1
                if len(errors) < 10:
                    errors.append({"filename": file_path.name, "error": str(error)})
        return {
            "folder": str(folder),
            "scanned": min(len(files), 500),
            "imported": imported,
            "duplicates": duplicates,
            "ignored": ignored,
            "errors": errors,
        }

    def get_bootstrap(self) -> dict[str, Any]:
        suggested_assetto_folder = (
            Path.home()
            / "AppData"
            / "Local"
            / "AcTools Content Manager"
            / "Progress"
            / "Sessions"
        )
        with self.connect() as connection:
            settings = {
                row["key"]: row["value"]
                for row in connection.execute("SELECT key, value FROM settings")
            }
            counts = {
                row["platform"]: row["race_count"]
                for row in connection.execute(
                    """
                    SELECT league.platform, COUNT(event.id) AS race_count
                    FROM leagues league
                    LEFT JOIN race_events event ON event.league_id = league.id
                    GROUP BY league.platform
                    """
                ).fetchall()
            }
        configured_assetto_folder = Path(
            settings.get("assetto_corsa_folder", str(suggested_assetto_folder))
        )
        assetto_installation = detect_assetto_corsa_installation(
            settings.get("assetto_corsa_install_folder", "")
        )
        detection_folder = (
            configured_assetto_folder
            if configured_assetto_folder.is_dir()
            else suggested_assetto_folder
        )
        suggested_assetto_aliases = detect_assetto_owner_aliases(detection_folder)
        suggested_assetto_owner = (
            suggested_assetto_aliases[0] if suggested_assetto_aliases else ""
        )
        saved_assetto_aliases = assetto_aliases_from_settings(settings)
        effective_assetto_aliases = normalize_assetto_owner_aliases(
            (
                settings.get("owner_assetto_corsa_name", "")
                or suggested_assetto_owner
            ),
            [*saved_assetto_aliases, *suggested_assetto_aliases],
        )
        return {
            "selectedSimulator": settings.get("selected_simulator", ""),
            "simulators": {
                "iracing": {
                    "configured": settings.get("setup_iracing_complete", "0") == "1",
                    "raceCount": counts.get("iracing", 0),
                    "folder": settings.get(
                        "import_folder", str(Path.home() / "Downloads")
                    ),
                    "autoScan": settings.get("auto_scan_imports", "0") == "1",
                    "ownerIdentity": settings.get("owner_iracing_id", ""),
                },
                "assetto-corsa": {
                    "configured": settings.get(
                        "setup_assetto_corsa_complete", "0"
                    )
                    == "1",
                    "raceCount": counts.get("assetto-corsa", 0),
                    "folder": settings.get(
                        "assetto_corsa_folder", str(suggested_assetto_folder)
                    ),
                    "suggestedFolder": str(suggested_assetto_folder),
                    "suggestedFolderExists": suggested_assetto_folder.is_dir(),
                    "installFolder": (
                        settings.get("assetto_corsa_install_folder", "")
                        or (str(assetto_installation) if assetto_installation else "")
                    ),
                    "suggestedInstallFolder": (
                        str(assetto_installation) if assetto_installation else ""
                    ),
                    "suggestedOwnerIdentity": suggested_assetto_owner,
                    "suggestedOwnerAliases": suggested_assetto_aliases,
                    "autoScan": settings.get("auto_scan_assetto_corsa", "0") == "1",
                    "ownerIdentity": settings.get("owner_assetto_corsa_name", "")
                    or suggested_assetto_owner,
                    "ownerAliases": effective_assetto_aliases,
                },
                "raceroom": {
                    "configured": settings.get("setup_raceroom_complete", "0") == "1",
                    "raceCount": counts.get("raceroom", 0),
                    "folder": settings.get(
                        "raceroom_results_folder",
                        str(suggested_raceroom_results_folder()),
                    ),
                    "suggestedFolder": str(suggested_raceroom_results_folder()),
                    "suggestedFolderExists": suggested_raceroom_results_folder().is_dir(),
                    "autoScan": settings.get("auto_scan_raceroom", "0") == "1",
                    "ownerIdentity": settings.get("raceroom_profile_url", "")
                    or settings.get("raceroom_profile_slug", ""),
                    "minimumDistance": int(
                        settings.get("raceroom_minimum_distance", "50")
                    ),
                },
            },
        }

    def get_assetto_corsa_installation(self) -> Path | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT value FROM settings
                WHERE key = 'assetto_corsa_install_folder'
                """
            ).fetchone()
        return detect_assetto_corsa_installation(
            str(row["value"] if row else "")
        )

    def select_simulator(self, simulator: str) -> dict[str, Any]:
        platform = str(simulator or "").strip().lower()
        if platform not in {"iracing", "assetto-corsa", "raceroom"}:
            raise ValueError("El simulador seleccionado no es válido")
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO settings (key, value) VALUES ('selected_simulator', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (platform,),
            )
            setup_key = {
                "assetto-corsa": "setup_assetto_corsa_complete",
                "raceroom": "setup_raceroom_complete",
            }.get(platform, "setup_iracing_complete")
            configured_row = connection.execute(
                "SELECT value FROM settings WHERE key = ?", (setup_key,)
            ).fetchone()
            configured = bool(configured_row and configured_row["value"] == "1")
            if configured:
                owner_key = {
                    "assetto-corsa": "owner_assetto_corsa_id",
                    "raceroom": "owner_raceroom_id",
                }.get(platform, "owner_iracing_id")
                owner_row = connection.execute(
                    "SELECT value FROM settings WHERE key = ?", (owner_key,)
                ).fetchone()
                owner_driver_id = str(owner_row["value"] if owner_row else "")
                latest = connection.execute(
                    """
                    SELECT league.id
                    FROM leagues league
                    LEFT JOIN race_events event ON event.league_id = league.id
                    WHERE league.platform = ?
                    GROUP BY league.id
                    ORDER BY CASE WHEN EXISTS (
                               SELECT 1
                               FROM race_results result
                               JOIN race_events owner_event ON owner_event.id = result.event_id
                               JOIN drivers driver ON driver.id = result.driver_id
                               WHERE owner_event.league_id = league.id
                                 AND driver.iracing_id = ?
                             ) THEN 1 ELSE 0 END DESC,
                             MAX(COALESCE(event.start_time, league.created_at)) DESC,
                             league.id DESC
                    LIMIT 1
                    """,
                    (platform, owner_driver_id),
                ).fetchone()
                if latest:
                    connection.execute("UPDATE leagues SET active = 0")
                    connection.execute(
                        "UPDATE leagues SET active = 1 WHERE id = ?",
                        (latest["id"],),
                    )
        return {"simulator": platform, "configured": configured}

    def _merge_assetto_owner_aliases(
        self, connection: sqlite3.Connection, aliases: list[str]
    ) -> str:
        if not aliases:
            raise ValueError("Indica al menos un nombre de Assetto Corsa")
        primary_name = aliases[0]
        canonical_external_id = assetto_driver_id(primary_name)
        alias_external_ids = [assetto_driver_id(name) for name in aliases]
        placeholders = ",".join("?" for _ in alias_external_ids)
        existing = connection.execute(
            f"""
            SELECT id, iracing_id, color
            FROM drivers
            WHERE iracing_id IN ({placeholders})
            ORDER BY CASE WHEN iracing_id = ? THEN 0 ELSE 1 END, id
            """,
            (*alias_external_ids, canonical_external_id),
        ).fetchall()
        if not existing:
            return canonical_external_id

        canonical = next(
            (
                row
                for row in existing
                if row["iracing_id"] == canonical_external_id
            ),
            None,
        )
        if canonical is None:
            canonical = existing[0]
            connection.execute(
                """
                UPDATE drivers
                SET iracing_id = ?, name = ?, initials = ?, is_demo = 0
                WHERE id = ?
                """,
                (
                    canonical_external_id,
                    primary_name,
                    driver_initials(primary_name),
                    canonical["id"],
                ),
            )
        else:
            connection.execute(
                """
                UPDATE drivers
                SET name = ?, initials = ?, is_demo = 0
                WHERE id = ?
                """,
                (primary_name, driver_initials(primary_name), canonical["id"]),
            )

        canonical_id = int(canonical["id"])
        affected_leagues: set[int] = set()
        for alias in existing:
            alias_id = int(alias["id"])
            if alias_id == canonical_id:
                continue
            league_rows = connection.execute(
                "SELECT league_id FROM league_drivers WHERE driver_id = ?",
                (alias_id,),
            ).fetchall()
            for league in league_rows:
                league_id = int(league["league_id"])
                affected_leagues.add(league_id)
                connection.execute(
                    """
                    INSERT OR IGNORE INTO league_drivers (league_id, driver_id)
                    VALUES (?, ?)
                    """,
                    (league_id, canonical_id),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO driver_stats
                        (league_id, driver_id, weekly_average, race_average,
                         incident_average, weeks, race_count, wins, sof_average, movement)
                    VALUES (?, ?, 0, 0, 0, 0, 0, 0, 0, 0)
                    """,
                    (league_id, canonical_id),
                )
            connection.execute(
                """
                DELETE FROM race_results
                WHERE driver_id = ?
                  AND EXISTS (
                      SELECT 1 FROM race_results canonical_result
                      WHERE canonical_result.event_id = race_results.event_id
                        AND canonical_result.driver_id = ?
                  )
                """,
                (alias_id, canonical_id),
            )
            connection.execute(
                "UPDATE race_results SET driver_id = ? WHERE driver_id = ?",
                (canonical_id, alias_id),
            )
            connection.execute(
                "DELETE FROM driver_stats WHERE driver_id = ?", (alias_id,)
            )
            connection.execute(
                "DELETE FROM league_drivers WHERE driver_id = ?", (alias_id,)
            )
            connection.execute("DELETE FROM drivers WHERE id = ?", (alias_id,))

        for league_id in affected_leagues:
            self._recalculate_league(connection, league_id)
        return canonical_external_id

    def _remove_assetto_ai_results(
        self, connection: sqlite3.Connection
    ) -> int:
        imported_rows = connection.execute(
            """
            SELECT league_id, external_event_id, filename, raw_json
            FROM imported_files
            WHERE source = 'assetto-corsa-cm'
            """
        ).fetchall()
        removed = 0
        affected_leagues: set[int] = set()
        for imported in imported_rows:
            try:
                payload = json.loads(imported["raw_json"])
                normalized_events = normalize_assetto_corsa_export(
                    payload, imported["filename"]
                )
            except (TypeError, json.JSONDecodeError, ValueError):
                continue
            normalized = next(
                (
                    event
                    for event in normalized_events
                    if event["externalEventId"] == imported["external_event_id"]
                ),
                None,
            )
            if normalized is None:
                continue
            ai_driver_ids = [
                result["customerId"]
                for result in normalized["results"]
                if result.get("isAi")
            ]
            if not ai_driver_ids:
                continue
            event = connection.execute(
                """
                SELECT id FROM race_events
                WHERE league_id = ? AND source = 'assetto-corsa-cm'
                  AND external_event_id = ?
                """,
                (imported["league_id"], imported["external_event_id"]),
            ).fetchone()
            if event is None:
                continue
            placeholders = ",".join("?" for _ in ai_driver_ids)
            cursor = connection.execute(
                f"""
                DELETE FROM race_results
                WHERE event_id = ?
                  AND driver_id IN (
                      SELECT id FROM drivers
                      WHERE iracing_id IN ({placeholders})
                  )
                """,
                (event["id"], *ai_driver_ids),
            )
            if cursor.rowcount:
                removed += cursor.rowcount
                affected_leagues.add(int(imported["league_id"]))

        for league_id in affected_leagues:
            connection.execute(
                """
                DELETE FROM driver_stats
                WHERE league_id = ?
                  AND NOT EXISTS (
                      SELECT 1
                      FROM race_results result
                      JOIN race_events event ON event.id = result.event_id
                      WHERE event.league_id = driver_stats.league_id
                        AND result.driver_id = driver_stats.driver_id
                  )
                """,
                (league_id,),
            )
            connection.execute(
                """
                DELETE FROM league_drivers
                WHERE league_id = ?
                  AND NOT EXISTS (
                      SELECT 1
                      FROM race_results result
                      JOIN race_events event ON event.id = result.event_id
                      WHERE event.league_id = league_drivers.league_id
                        AND result.driver_id = league_drivers.driver_id
                  )
                """,
                (league_id,),
            )
            self._recalculate_league(connection, league_id)
        connection.execute(
            """
            DELETE FROM drivers
            WHERE iracing_id LIKE 'ac:%'
              AND NOT EXISTS (
                  SELECT 1 FROM race_results
                  WHERE race_results.driver_id = drivers.id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM league_drivers
                  WHERE league_drivers.driver_id = drivers.id
              )
            """
        )
        return removed

    def _remove_assetto_unnamed_results(
        self, connection: sqlite3.Connection
    ) -> int:
        imported_rows = connection.execute(
            """
            SELECT league_id, external_event_id, raw_json
            FROM imported_files
            WHERE source = 'assetto-corsa-cm'
            """
        ).fetchall()
        removed = 0
        affected_leagues: set[int] = set()
        affected_events: set[int] = set()
        for imported in imported_rows:
            try:
                payload = json.loads(imported["raw_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            players = payload.get("players") if isinstance(payload, dict) else None
            if not isinstance(players, list):
                continue
            unnamed_driver_ids = [
                assetto_driver_id(f"Piloto {player_index + 1}")
                for player_index, player in enumerate(players)
                if isinstance(player, dict)
                and not str(player.get("name") or "").strip()
            ]
            if not unnamed_driver_ids:
                continue
            event = connection.execute(
                """
                SELECT id FROM race_events
                WHERE league_id = ? AND source = 'assetto-corsa-cm'
                  AND external_event_id = ?
                """,
                (imported["league_id"], imported["external_event_id"]),
            ).fetchone()
            if event is None:
                continue
            placeholders = ",".join("?" for _ in unnamed_driver_ids)
            cursor = connection.execute(
                f"""
                DELETE FROM race_results
                WHERE event_id = ?
                  AND driver_id IN (
                      SELECT id FROM drivers
                      WHERE iracing_id IN ({placeholders})
                  )
                """,
                (event["id"], *unnamed_driver_ids),
            )
            if cursor.rowcount:
                removed += cursor.rowcount
                affected_leagues.add(int(imported["league_id"]))
                affected_events.add(int(event["id"]))

        for event_id in affected_events:
            remaining = connection.execute(
                """
                SELECT id, start_position
                FROM race_results
                WHERE event_id = ?
                ORDER BY finish_position, id
                """,
                (event_id,),
            ).fetchall()
            for finish_position, result in enumerate(remaining, start=1):
                connection.execute(
                    "UPDATE race_results SET finish_position = ? WHERE id = ?",
                    (finish_position, result["id"]),
                )
            starters = sorted(
                (result for result in remaining if result["start_position"] is not None),
                key=lambda result: (result["start_position"], result["id"]),
            )
            for start_position, result in enumerate(starters, start=1):
                connection.execute(
                    "UPDATE race_results SET start_position = ? WHERE id = ?",
                    (start_position, result["id"]),
                )
            connection.execute(
                "UPDATE race_events SET field_size = ? WHERE id = ?",
                (len(remaining), event_id),
            )

        for league_id in affected_leagues:
            connection.execute(
                """
                DELETE FROM driver_stats
                WHERE league_id = ?
                  AND NOT EXISTS (
                      SELECT 1
                      FROM race_results result
                      JOIN race_events event ON event.id = result.event_id
                      WHERE event.league_id = driver_stats.league_id
                        AND result.driver_id = driver_stats.driver_id
                  )
                """,
                (league_id,),
            )
            connection.execute(
                """
                DELETE FROM league_drivers
                WHERE league_id = ?
                  AND NOT EXISTS (
                      SELECT 1
                      FROM race_results result
                      JOIN race_events event ON event.id = result.event_id
                      WHERE event.league_id = league_drivers.league_id
                        AND result.driver_id = league_drivers.driver_id
                  )
                """,
                (league_id,),
            )
            self._recalculate_league(connection, league_id)
        connection.execute(
            """
            DELETE FROM drivers
            WHERE iracing_id LIKE 'ac:%'
              AND NOT EXISTS (
                  SELECT 1 FROM race_results
                  WHERE race_results.driver_id = drivers.id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM league_drivers
                  WHERE league_drivers.driver_id = drivers.id
              )
            """
        )
        return removed

    def save_simulator_config(self, values: dict[str, Any]) -> dict[str, Any]:
        platform = str(values.get("simulator", "")).strip().lower()
        folder_value = str(values.get("folder", "")).strip()
        install_folder_value = str(values.get("installFolder", "")).strip()
        owner_identity = str(values.get("ownerIdentity", "")).strip()
        owner_aliases = normalize_assetto_owner_aliases(
            owner_identity, values.get("ownerAliases")
        )
        auto_scan = bool(values.get("autoScan", True))
        if platform not in {"iracing", "assetto-corsa", "raceroom"}:
            raise ValueError("El simulador seleccionado no es válido")
        candidate = Path(folder_value).expanduser()
        if not candidate.is_absolute():
            raise ValueError("La carpeta debe indicarse con una ruta completa")
        try:
            resolved = candidate.resolve(strict=platform != "raceroom")
        except OSError as error:
            raise ValueError("La carpeta indicada no existe") from error
        if platform != "raceroom" and not resolved.is_dir():
            raise ValueError("La ruta indicada no es una carpeta")

        if platform == "iracing":
            if not owner_identity.isdigit() or not 3 <= len(owner_identity) <= 12:
                raise ValueError("El ID del piloto de iRacing no es válido")
            setting_values = (
                ("import_folder", str(resolved)),
                ("auto_scan_imports", "1" if auto_scan else "0"),
                ("owner_iracing_id", owner_identity),
                ("setup_iracing_complete", "1"),
                ("selected_simulator", platform),
            )
        elif platform == "assetto-corsa":
            if not owner_aliases:
                raise ValueError("Indica el nombre con el que apareces en Assetto Corsa")
            owner_identity = owner_aliases[0]
            detected_installation = detect_assetto_corsa_installation(
                install_folder_value
            )
            if install_folder_value and detected_installation is None:
                raise ValueError(
                    "La carpeta de instalación no contiene Assetto Corsa"
                )
            install_folder = (
                str(detected_installation) if detected_installation else ""
            )
            setting_values = (
                ("assetto_corsa_folder", str(resolved)),
                ("assetto_corsa_install_folder", install_folder),
                ("auto_scan_assetto_corsa", "1" if auto_scan else "0"),
                ("owner_assetto_corsa_name", owner_identity),
                ("owner_assetto_corsa_id", assetto_driver_id(owner_identity)),
                (
                    "owner_assetto_corsa_aliases",
                    json.dumps(owner_aliases, ensure_ascii=False),
                ),
                ("setup_assetto_corsa_complete", "1"),
                ("selected_simulator", platform),
            )
        else:
            profile = fetch_raceroom_profile(owner_identity)
            owner_identity = profile["profileUrl"]
            try:
                minimum_distance = int(values.get("minimumDistance", 50))
            except (TypeError, ValueError) as error:
                raise ValueError("La distancia mínima no es válida") from error
            if not 10 <= minimum_distance <= 100:
                raise ValueError("La distancia mínima debe estar entre el 10% y el 100%")
            setting_values = (
                ("raceroom_profile_slug", profile["slug"]),
                ("raceroom_profile_url", profile["profileUrl"]),
                ("owner_raceroom_id", f"rr:{profile['userId']}"),
                ("owner_raceroom_name", profile["displayName"]),
                ("raceroom_results_folder", str(resolved)),
                ("auto_scan_raceroom", "1" if auto_scan else "0"),
                ("raceroom_minimum_distance", str(minimum_distance)),
                ("setup_raceroom_complete", "1"),
                ("selected_simulator", platform),
            )

        with self.connect() as connection:
            for key, value in setting_values:
                connection.execute(
                    """
                    INSERT INTO settings (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (key, value),
                )
            if platform == "assetto-corsa":
                canonical_id = self._merge_assetto_owner_aliases(
                    connection, owner_aliases
                )
                connection.execute(
                    """
                    INSERT INTO settings (key, value)
                    VALUES ('owner_assetto_corsa_id', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (canonical_id,),
                )
            league = connection.execute(
                "SELECT id FROM leagues WHERE platform = ? ORDER BY id DESC LIMIT 1",
                (platform,),
            ).fetchone()
            if not league:
                year = datetime.now().year
                cursor = connection.execute(
                    """
                    INSERT INTO leagues
                        (name, series_name, season, car, setup_type, total_weeks,
                         weeks_completed, active, created_at, series_id, season_id,
                         season_year, season_quarter, platform)
                    VALUES (?, ?, ?, ?, ?, 53, 0, 0, ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        "Assetto Corsa"
                        if platform == "assetto-corsa"
                        else "RaceRoom"
                        if platform == "raceroom"
                        else "iRacing",
                        "Historial de Assetto Corsa"
                        if platform == "assetto-corsa"
                        else "RaceRoom Ranked"
                        if platform == "raceroom"
                        else "Serie iRacing",
                        str(year)
                        if platform == "assetto-corsa"
                        else f"{year} Season 1",
                        "Sin carreras importadas",
                        "Ranked" if platform == "raceroom" else "Local",
                        utc_now(),
                        f"{platform}:pending",
                        f"{platform}:pending:{year}",
                        year,
                        platform,
                    ),
                )
                league_id = int(cursor.lastrowid)
            else:
                league_id = int(league["id"])
            connection.execute("UPDATE leagues SET active = 0")
            connection.execute(
                "UPDATE leagues SET active = 1 WHERE id = ?", (league_id,)
            )
        return {
            "simulator": platform,
            "folder": str(resolved),
            "installFolder": (
                install_folder if platform == "assetto-corsa" else ""
            ),
            "ownerIdentity": owner_identity,
            "ownerAliases": owner_aliases if platform == "assetto-corsa" else [],
            "autoScan": auto_scan,
            "minimumDistance": (
                minimum_distance if platform == "raceroom" else None
            ),
            "configured": True,
        }

    def sync_raceroom_history(self, maximum_new: int = 25) -> dict[str, Any]:
        maximum_new = max(1, min(100, as_int(maximum_new, 25)))
        with self.connect() as connection:
            settings = {
                row["key"]: row["value"]
                for row in connection.execute(
                    """
                    SELECT key, value FROM settings
                    WHERE key IN (
                        'raceroom_profile_slug', 'owner_raceroom_id',
                        'raceroom_minimum_distance'
                    )
                    """
                ).fetchall()
            }
            known_hashes = {
                str(row["external_event_id"])
                for row in connection.execute(
                    "SELECT external_event_id FROM imported_files WHERE source = 'raceroom-web'"
                ).fetchall()
            }
        slug = settings.get("raceroom_profile_slug", "").strip()
        owner_id = settings.get("owner_raceroom_id", "").removeprefix("rr:")
        if not slug or not owner_id:
            raise ValueError("Configura primero tu perfil público de RaceRoom")
        minimum_distance = max(
            10, min(100, as_int(settings.get("raceroom_minimum_distance"), 50))
        )

        summaries: list[dict[str, Any]] = []
        page = -1
        total_entries = 0
        while len(summaries) < 5000:
            payload = fetch_json_url(
                f"{RACEROOM_BASE_URL}/r3e/users/{quote(slug)}/career"
                f"?CurrentPage={page}&PageSize=100&json"
            )
            try:
                payload = payload["context"]["c"]["raceList"][
                    "GetUserMpRatingProgressResult"
                ]
            except (KeyError, TypeError):
                pass
            entries = payload.get("Entries") or payload.get("entries") or []
            total_entries = as_int(
                payload.get("TotalEntries", payload.get("totalEntries")), len(entries)
            )
            if not isinstance(entries, list) or not entries:
                break
            summaries.extend(entry for entry in entries if isinstance(entry, dict))
            if len(summaries) >= total_entries or len(entries) < 100:
                break
            page -= 1

        summaries = list(
            {
                str(summary.get("RaceHash") or ""): summary
                for summary in summaries
                if str(summary.get("RaceHash") or "").strip()
            }.values()
        )
        pending = [
            summary
            for summary in summaries
            if str(summary.get("RaceHash") or "").strip() not in known_hashes
        ]
        pending.sort(
            key=lambda item: as_int(item.get("RaceFinishTime"), 0), reverse=True
        )
        imported = 0
        duplicates = 0
        errors: list[str] = []
        for summary in pending[:maximum_new]:
            race_hash = str(summary.get("RaceHash") or "").strip()
            if not race_hash:
                continue
            try:
                detail_response = fetch_json_url(
                    f"{RACEROOM_BASE_URL}/multiplayer/results/{quote(race_hash)}"
                )
                detail = (
                    detail_response.get("GetMpRaceResultResult")
                    if isinstance(detail_response, dict)
                    else None
                )
                if not isinstance(detail, dict):
                    detail = detail_response
                if not isinstance(detail, dict):
                    raise ValueError("RaceRoom no ha devuelto el detalle esperado")
                detail = {**summary, **detail, "RaceHash": race_hash}
                normalized = normalize_raceroom_result(
                    detail, owner_id, minimum_distance
                )
                result = self._import_normalized_result(
                    f"raceroom-{race_hash}.json",
                    detail,
                    normalized,
                    include_all_drivers=True,
                    replace_demo=True,
                )
                if result.get("duplicate"):
                    duplicates += 1
                else:
                    imported += 1
            except (ValueError, TypeError, KeyError) as error:
                errors.append(f"{race_hash}: {error}")

        remaining = max(0, len(pending) - min(len(pending), maximum_new))
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO settings (key, value) VALUES ('raceroom_last_sync', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (now,),
            )
            latest = connection.execute(
                """
                SELECT league.id
                FROM leagues league
                JOIN race_events event ON event.league_id = league.id
                WHERE league.platform = 'raceroom'
                ORDER BY event.start_time DESC, event.id DESC
                LIMIT 1
                """
            ).fetchone()
            if latest:
                connection.execute("UPDATE leagues SET active = 0")
                connection.execute(
                    "UPDATE leagues SET active = 1 WHERE id = ?", (latest["id"],)
                )
        return {
            "profile": slug,
            "available": total_entries,
            "reviewed": len(summaries),
            "imported": imported,
            "duplicates": duplicates,
            "remaining": remaining,
            "minimumDistance": minimum_distance,
            "lastSync": now,
            "errors": errors[:10],
            "complete": remaining == 0,
        }

    def scan_assetto_corsa_folder(self) -> dict[str, Any]:
        with self.connect() as connection:
            settings = {
                row["key"]: row["value"]
                for row in connection.execute(
                    """
                    SELECT key, value FROM settings
                    WHERE key IN (
                        'assetto_corsa_folder',
                        'auto_scan_assetto_corsa',
                        'owner_assetto_corsa_name',
                        'owner_assetto_corsa_aliases'
                    )
                    """
                ).fetchall()
            }
        folder_value = settings.get("assetto_corsa_folder", "").strip()
        if not folder_value:
            raise ValueError("Configura primero la carpeta de Content Manager")
        folder = Path(folder_value)
        if not folder.is_dir():
            raise ValueError("La carpeta de sesiones de Assetto Corsa no existe")

        detected_aliases = detect_assetto_owner_aliases(folder)
        saved_aliases = assetto_aliases_from_settings(settings)
        owner_aliases = normalize_assetto_owner_aliases(
            settings.get("owner_assetto_corsa_name", "")
            or (detected_aliases[0] if detected_aliases else ""),
            [*saved_aliases, *detected_aliases],
        )
        if owner_aliases:
            with self.connect() as connection:
                canonical_id = self._merge_assetto_owner_aliases(
                    connection, owner_aliases
                )
                for key, value in (
                    ("owner_assetto_corsa_name", owner_aliases[0]),
                    ("owner_assetto_corsa_id", canonical_id),
                    (
                        "owner_assetto_corsa_aliases",
                        json.dumps(owner_aliases, ensure_ascii=False),
                    ),
                ):
                    connection.execute(
                        """
                        INSERT INTO settings (key, value) VALUES (?, ?)
                        ON CONFLICT(key) DO UPDATE SET value = excluded.value
                        """,
                        (key, value),
                    )

        imported = 0
        duplicates = 0
        ignored = 0
        race_sessions = 0
        errors: list[dict[str, str]] = []
        files = sorted(folder.glob("*.json"), key=lambda item: item.stat().st_mtime)
        for file_path in files[:2500]:
            try:
                if file_path.stat().st_size > 25_000_000:
                    ignored += 1
                    continue
                payload = json.loads(file_path.read_text(encoding="utf-8-sig"))
                events = normalize_assetto_corsa_export(payload, file_path.name)
                race_sessions += len(events)
                for event in events:
                    result = self._import_normalized_result(
                        file_path.name,
                        payload,
                        event,
                        include_all_drivers=True,
                        replace_demo=False,
                    )
                    if result["duplicate"]:
                        duplicates += 1
                    else:
                        imported += 1
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                ignored += 1
                if len(errors) < 10 and "ninguna sesión de carrera" not in str(error):
                    errors.append({"filename": file_path.name, "error": str(error)})

        with self.connect() as connection:
            ai_removed = self._remove_assetto_ai_results(connection)
            unnamed_removed = self._remove_assetto_unnamed_results(connection)
            owner_row = connection.execute(
                "SELECT value FROM settings WHERE key = 'owner_assetto_corsa_id'"
            ).fetchone()
            owner_driver_id = str(owner_row["value"] if owner_row else "")
            latest = connection.execute(
                """
                SELECT league.id
                FROM leagues league
                JOIN race_events event ON event.league_id = league.id
                WHERE league.platform = 'assetto-corsa'
                GROUP BY league.id
                ORDER BY CASE WHEN EXISTS (
                           SELECT 1
                           FROM race_results result
                           JOIN race_events owner_event ON owner_event.id = result.event_id
                           JOIN drivers driver ON driver.id = result.driver_id
                           WHERE owner_event.league_id = league.id
                             AND driver.iracing_id = ?
                         ) THEN 1 ELSE 0 END DESC,
                         MAX(event.start_time) DESC, league.id DESC
                LIMIT 1
                """,
                (owner_driver_id,),
            ).fetchone()
            if latest:
                connection.execute("UPDATE leagues SET active = 0")
                connection.execute(
                    "UPDATE leagues SET active = 1 WHERE id = ?", (latest["id"],)
                )
            connection.execute(
                """
                INSERT INTO settings (key, value)
                VALUES ('selected_simulator', 'assetto-corsa')
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """
            )
        return {
            "folder": str(folder),
            "scanned": min(len(files), 2500),
            "raceSessions": race_sessions,
            "imported": imported,
            "duplicates": duplicates,
            "ignored": ignored,
            "aiDriversRemoved": ai_removed,
            "unnamedParticipantsRemoved": unnamed_removed,
            "ownerAliases": owner_aliases,
            "errors": errors,
        }

    def save_telemetry_folder(
        self, folder_value: str, auto_scan: bool
    ) -> dict[str, Any]:
        candidate = Path(folder_value.strip()).expanduser()
        if not candidate.is_absolute():
            raise ValueError("La carpeta debe indicarse con una ruta completa")
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as error:
            raise ValueError("La carpeta indicada no existe") from error
        if not resolved.is_dir():
            raise ValueError("La ruta indicada no es una carpeta")
        with self.connect() as connection:
            for key, value in (
                ("telemetry_folder", str(resolved)),
                ("auto_scan_telemetry", "1" if auto_scan else "0"),
            ):
                connection.execute(
                    """
                    INSERT INTO settings (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (key, value),
                )
        return {"folder": str(resolved), "autoScan": auto_scan}

    def scan_telemetry_folder(self) -> dict[str, Any]:
        with self.connect() as connection:
            settings = {
                row["key"]: row["value"]
                for row in connection.execute(
                    """
                    SELECT key, value FROM settings
                    WHERE key IN ('telemetry_folder', 'auto_scan_telemetry')
                    """
                ).fetchall()
            }
        folder_value = settings.get("telemetry_folder", "").strip()
        if not folder_value:
            raise ValueError("Configura primero la carpeta de telemetrÃ­as")
        folder = Path(folder_value)
        if not folder.exists() or not folder.is_dir():
            raise ValueError("La carpeta de telemetrÃ­as no existe")

        added = 0
        updated = 0
        unchanged = 0
        linked = 0
        practice = 0
        errors: list[dict[str, str]] = []
        files = sorted(folder.glob("*.ibt"), key=lambda item: item.stat().st_mtime)
        for file_path in files[:500]:
            try:
                stat = file_path.stat()
                if stat.st_size > 2_500_000_000:
                    raise ValueError("El archivo supera el lÃ­mite de 2,5 GB")
                resolved_path = str(file_path.resolve())
                modified_at = datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat()
                with self.connect() as connection:
                    existing = connection.execute(
                        """
                        SELECT file_size, modified_at, linked_event_id, session_type,
                               subsession_id
                        FROM telemetry_files
                        WHERE file_path = ?
                        """,
                        (resolved_path,),
                    ).fetchone()
                    if (
                        existing
                        and existing["file_size"] == stat.st_size
                        and existing["modified_at"] == modified_at
                    ):
                        newly_linked_event = None
                        if (
                            existing["linked_event_id"] is None
                            and str(existing["session_type"]).lower() == "race"
                            and existing["subsession_id"]
                        ):
                            newly_linked_event = connection.execute(
                                """
                                SELECT id FROM race_events
                                WHERE external_event_id = ?
                                ORDER BY id LIMIT 1
                                """,
                                (existing["subsession_id"],),
                            ).fetchone()
                        if newly_linked_event:
                            connection.execute(
                                """
                                UPDATE telemetry_files
                                SET linked_event_id = ?, scanned_at = ?
                                WHERE file_path = ?
                                """,
                                (
                                    int(newly_linked_event["id"]),
                                    utc_now(),
                                    resolved_path,
                                ),
                            )
                            updated += 1
                            linked += 1
                        else:
                            unchanged += 1
                        continue
                metadata = read_ibt_metadata(file_path)
                with self.connect() as connection:
                    linked_event = None
                    if metadata["subsessionId"]:
                        linked_event = connection.execute(
                            """
                            SELECT id FROM race_events
                            WHERE external_event_id = ?
                            ORDER BY id LIMIT 1
                            """,
                            (metadata["subsessionId"],),
                        ).fetchone()
                    linked_event_id = (
                        int(linked_event["id"]) if linked_event else None
                    )
                    connection.execute(
                        """
                        INSERT INTO telemetry_files
                            (file_path, filename, file_size, modified_at,
                             subsession_id, session_id, session_type,
                             track_name, car_name, tick_rate, sample_count,
                             channel_count, channels_json, linked_event_id,
                             scanned_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(file_path) DO UPDATE SET
                            filename = excluded.filename,
                            file_size = excluded.file_size,
                            modified_at = excluded.modified_at,
                            subsession_id = excluded.subsession_id,
                            session_id = excluded.session_id,
                            session_type = excluded.session_type,
                            track_name = excluded.track_name,
                            car_name = excluded.car_name,
                            tick_rate = excluded.tick_rate,
                            sample_count = excluded.sample_count,
                            channel_count = excluded.channel_count,
                            channels_json = excluded.channels_json,
                            linked_event_id = excluded.linked_event_id,
                            scanned_at = excluded.scanned_at
                        """,
                        (
                            resolved_path,
                            file_path.name,
                            stat.st_size,
                            modified_at,
                            metadata["subsessionId"],
                            metadata["sessionId"],
                            metadata["sessionType"],
                            metadata["trackName"],
                            metadata["carName"],
                            metadata["tickRate"],
                            metadata["sampleCount"],
                            metadata["channelCount"],
                            json.dumps(metadata["channels"]),
                            linked_event_id,
                            utc_now(),
                        ),
                    )
                if existing:
                    updated += 1
                else:
                    added += 1
                linked += int(linked_event_id is not None)
                practice += int(metadata["sessionType"].lower() == "practice")
            except (OSError, ValueError, struct.error) as error:
                if len(errors) < 10:
                    errors.append({"filename": file_path.name, "error": str(error)})
        return {
            "folder": str(folder),
            "scanned": min(len(files), 500),
            "added": added,
            "updated": updated,
            "unchanged": unchanged,
            "linked": linked,
            "practice": practice,
            "errors": errors,
        }

    def get_telemetry_overview(self) -> dict[str, Any]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT telemetry.*, event.track AS linked_track,
                       event.start_time AS linked_start_time,
                       league.series_name AS linked_series
                FROM telemetry_files AS telemetry
                LEFT JOIN race_events AS event
                  ON event.id = telemetry.linked_event_id
                LEFT JOIN leagues AS league ON league.id = event.league_id
                ORDER BY telemetry.modified_at DESC, telemetry.id DESC
                LIMIT 100
                """
            ).fetchall()
        return {
            "files": [
                {
                    "id": row["id"],
                    "filename": row["filename"],
                    "filePath": row["file_path"],
                    "fileSize": row["file_size"],
                    "modifiedAt": row["modified_at"],
                    "subsessionId": row["subsession_id"],
                    "sessionType": row["session_type"],
                    "trackName": row["track_name"],
                    "carName": row["car_name"],
                    "tickRate": row["tick_rate"],
                    "sampleCount": row["sample_count"],
                    "channelCount": row["channel_count"],
                    "linkedEventId": row["linked_event_id"],
                    "linkedTrack": row["linked_track"],
                    "linkedStartTime": row["linked_start_time"],
                    "linkedSeries": row["linked_series"],
                }
                for row in rows
            ]
        }

    def _recalculate_league(
        self, connection: sqlite3.Connection, league_id: int
    ) -> None:
        linked_drivers = connection.execute(
            "SELECT driver_id FROM league_drivers WHERE league_id = ?",
            (league_id,),
        ).fetchall()
        for driver in linked_drivers:
            rows = connection.execute(
                """
                SELECT rr.finish_position, rr.incidents, re.race_week,
                       re.strength_of_field
                FROM race_results rr
                JOIN race_events re ON re.id = rr.event_id
                WHERE re.league_id = ? AND rr.driver_id = ?
                  AND rr.scoring_eligible = 1
                ORDER BY re.race_week, re.start_time
                """,
                (league_id, driver["driver_id"]),
            ).fetchall()
            if not rows:
                connection.execute(
                    """
                    UPDATE driver_stats
                    SET weekly_average = 0, race_average = 0, incident_average = 0,
                        weeks = 0, race_count = 0, wins = 0, sof_average = 0, movement = 0
                    WHERE league_id = ? AND driver_id = ?
                    """,
                    (league_id, driver["driver_id"]),
                )
                continue

            weekly: dict[int, list[sqlite3.Row]] = {}
            for row in rows:
                weekly.setdefault(row["race_week"], []).append(row)
            weekly_positions = [
                sum(item["finish_position"] for item in week_rows) / len(week_rows)
                for week_rows in weekly.values()
            ]
            weekly_incidents = [
                sum(item["incidents"] for item in week_rows) / len(week_rows)
                for week_rows in weekly.values()
            ]
            race_average = sum(row["finish_position"] for row in rows) / len(rows)
            weekly_average = sum(weekly_positions) / len(weekly_positions)
            incident_average = sum(weekly_incidents) / len(weekly_incidents)
            sof_values = [
                row["strength_of_field"] for row in rows if row["strength_of_field"]
            ]
            sof_average = round(sum(sof_values) / len(sof_values)) if sof_values else 0
            wins = sum(1 for row in rows if row["finish_position"] == 1)
            connection.execute(
                """
                INSERT INTO driver_stats
                    (league_id, driver_id, weekly_average, race_average,
                     incident_average, weeks, race_count, wins, sof_average, movement)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(league_id, driver_id) DO UPDATE SET
                    weekly_average = excluded.weekly_average,
                    race_average = excluded.race_average,
                    incident_average = excluded.incident_average,
                    weeks = excluded.weeks,
                    race_count = excluded.race_count,
                    wins = excluded.wins,
                    sof_average = excluded.sof_average,
                    movement = 0
                """,
                (
                    league_id,
                    driver["driver_id"],
                    weekly_average,
                    race_average,
                    incident_average,
                    len(weekly),
                    len(rows),
                    wins,
                    sof_average,
                ),
            )

        events = connection.execute(
            """
            SELECT race_week, track, layout, COUNT(*) AS race_count,
                   MAX(strength_of_field) AS top_sof
            FROM race_events
            WHERE league_id = ?
            GROUP BY race_week
            ORDER BY race_week
            """,
            (league_id,),
        ).fetchall()
        if events:
            connection.execute("DELETE FROM rounds WHERE league_id = ?", (league_id,))
        for event in events:
            averages = connection.execute(
                """
                SELECT AVG(rr.finish_position) AS position_average,
                       AVG(rr.incidents) AS incident_average
                FROM race_results rr
                JOIN race_events re ON re.id = rr.event_id
                JOIN league_drivers ld
                  ON ld.driver_id = rr.driver_id AND ld.league_id = re.league_id
                WHERE re.league_id = ? AND re.race_week = ?
                  AND rr.scoring_eligible = 1
                """,
                (league_id, event["race_week"]),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO rounds
                    (league_id, week, track, layout, race_count, position_average,
                     incident_average, top_sof)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    league_id,
                    event["race_week"],
                    event["track"],
                    event["layout"],
                    event["race_count"],
                    averages["position_average"] or 0,
                    averages["incident_average"] or 0,
                    event["top_sof"] or 0,
                ),
            )

    def _active_league_and_owner(
        self, connection: sqlite3.Connection
    ) -> tuple[int, str]:
        league = connection.execute(
            "SELECT id, platform FROM leagues WHERE active = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        if not league:
            raise RuntimeError("No hay una liga activa")
        owner_key = {
            "assetto-corsa": "owner_assetto_corsa_id",
            "raceroom": "owner_raceroom_id",
        }.get(str(league["platform"]), "owner_iracing_id")
        owner = connection.execute(
            "SELECT value FROM settings WHERE key = ?",
            (owner_key,),
        ).fetchone()
        fallback = ""
        return int(league["id"]), str(owner["value"] if owner else fallback)

    def get_races(self) -> dict[str, Any]:
        with self.connect() as connection:
            league_id, owner_iracing_id = self._active_league_and_owner(connection)
            rows = connection.execute(
                """
                SELECT re.*,
                       winner.name AS winner_name,
                       owner_result.finish_position AS owner_finish_position,
                       owner_result.start_position AS owner_start_position,
                       owner_result.incidents AS owner_incidents,
                       owner_result.irating_change AS owner_irating_change,
                       owner_result.safety_rating_change AS owner_safety_rating_change
                FROM race_events re
                LEFT JOIN race_results winner_result
                  ON winner_result.event_id = re.id
                 AND winner_result.finish_position = 1
                LEFT JOIN drivers winner ON winner.id = winner_result.driver_id
                LEFT JOIN drivers owner ON owner.iracing_id = ?
                LEFT JOIN race_results owner_result
                  ON owner_result.event_id = re.id
                 AND owner_result.driver_id = owner.id
                WHERE re.league_id = ?
                ORDER BY COALESCE(re.start_time, '') DESC, re.id DESC
                """,
                (owner_iracing_id, league_id),
            ).fetchall()
        return {
            "ownerIracingId": owner_iracing_id,
            "races": [
                {
                    "id": row["id"],
                    "externalEventId": row["external_event_id"],
                    "week": row["race_week"],
                    "startTime": row["start_time"],
                    "track": row["track"],
                    "layout": row["layout"],
                    "splitNumber": row["split_number"],
                    "splitTotal": row["split_total"],
                    "strengthOfField": row["strength_of_field"],
                    "fieldSize": row["field_size"],
                    "winnerName": row["winner_name"],
                    "ownerResult": {
                        "finishPosition": row["owner_finish_position"],
                        "startPosition": row["owner_start_position"],
                        "positionChange": (
                            row["owner_start_position"] - row["owner_finish_position"]
                            if row["owner_start_position"] is not None
                            and row["owner_finish_position"] is not None
                            else None
                        ),
                        "incidents": row["owner_incidents"],
                        "iratingChange": row["owner_irating_change"],
                        "safetyRatingChange": row["owner_safety_rating_change"],
                    }
                    if row["owner_finish_position"] is not None
                    else None,
                }
                for row in rows
            ],
        }

    def get_race_detail(self, event_id: int) -> dict[str, Any]:
        with self.connect() as connection:
            _, owner_iracing_id = self._active_league_and_owner(connection)
            event = connection.execute(
                """
                SELECT event.*, league.platform
                FROM race_events event
                JOIN leagues league ON league.id = event.league_id
                WHERE event.id = ?
                """,
                (event_id,),
            ).fetchone()
            if not event:
                raise ValueError("La carrera seleccionada no existe")
            rows = connection.execute(
                """
                SELECT d.id AS driver_db_id, d.iracing_id, d.name, d.initials, d.color,
                       rr.finish_position, rr.start_position, rr.incidents,
                       rr.laps_complete, rr.best_lap_time, rr.irating_change,
                       rr.safety_rating_change, rr.status, rr.class_id, rr.class_name,
                       rr.scoring_eligible, rr.distance_percent
                FROM race_results rr
                JOIN drivers d ON d.id = rr.driver_id
                WHERE rr.event_id = ?
                ORDER BY rr.finish_position, d.name
                """,
                (event_id,),
            ).fetchall()
            recurrent_rows = []
            if event["platform"] in {"assetto-corsa", "iracing", "raceroom"}:
                recurrent_rows = connection.execute(
                    """
                    WITH current_drivers AS (
                        SELECT driver_id
                        FROM race_results
                        WHERE event_id = ?
                    )
                    SELECT first.driver_id,
                           second.driver_id AS opponent_id,
                           COUNT(*) AS meetings
                    FROM race_results AS first
                    JOIN race_results AS second
                      ON second.event_id = first.event_id
                     AND second.driver_id != first.driver_id
                    JOIN race_events AS shared_event
                      ON shared_event.id = first.event_id
                    JOIN leagues AS shared_league
                      ON shared_league.id = shared_event.league_id
                    WHERE shared_league.platform = ?
                      AND first.driver_id IN (
                          SELECT driver_id FROM current_drivers
                      )
                      AND second.driver_id IN (
                          SELECT driver_id FROM current_drivers
                      )
                    GROUP BY first.driver_id, second.driver_id
                    HAVING COUNT(*) >= 2
                    """,
                    (event_id, event["platform"]),
                ).fetchall()
            imported = connection.execute(
                """
                SELECT raw_json FROM imported_files
                WHERE league_id = ? AND source = ? AND external_event_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (event["league_id"], event["source"], event["external_event_id"]),
            ).fetchone()
            telemetry_rows = connection.execute(
                """
                SELECT id, filename, file_size, session_type, track_name,
                       car_name, tick_rate, sample_count, channel_count
                FROM telemetry_files
                WHERE linked_event_id = ?
                ORDER BY modified_at DESC
                """,
                (event_id,),
            ).fetchall()
            assetto_settings = {
                row["key"]: row["value"]
                for row in connection.execute(
                    """
                    SELECT key, value FROM settings
                    WHERE key IN (
                        'owner_assetto_corsa_name',
                        'owner_assetto_corsa_aliases'
                    )
                    """
                ).fetchall()
            }

        rich = {"event": {}, "drivers": {}}
        if imported:
            try:
                raw_payload = json.loads(imported["raw_json"])
                if event["platform"] == "assetto-corsa":
                    rich = extract_assetto_corsa_rich_data(
                        raw_payload, event["external_event_id"]
                    )
                elif event["platform"] == "raceroom":
                    rich = extract_raceroom_rich_data(raw_payload)
                else:
                    rich = extract_iracing_rich_data(raw_payload)
            except (TypeError, json.JSONDecodeError):
                rich = {"event": {}, "drivers": {}}

        results = []
        assetto_owner_alias_ids = [
            assetto_driver_id(alias)
            for alias in assetto_aliases_from_settings(assetto_settings)
        ]
        for row in rows:
            extra = rich["drivers"].get(row["iracing_id"], {})
            if (
                event["platform"] == "assetto-corsa"
                and row["iracing_id"] == owner_iracing_id
                and not extra
            ):
                extra = next(
                    (
                        rich["drivers"][alias_id]
                        for alias_id in assetto_owner_alias_ids
                        if alias_id in rich["drivers"]
                    ),
                    {},
                )
            result = {
                "_driverDbId": row["driver_db_id"],
                "iracingId": row["iracing_id"],
                "name": row["name"],
                "initials": row["initials"],
                "color": row["color"],
                "isOwner": row["iracing_id"] == owner_iracing_id,
                "finishPosition": row["finish_position"],
                "startPosition": row["start_position"],
                "positionChange": (
                    row["start_position"] - row["finish_position"]
                    if row["start_position"] is not None
                    else None
                ),
                "incidents": row["incidents"],
                "lapsComplete": row["laps_complete"],
                "bestLapTime": row["best_lap_time"],
                "iratingChange": row["irating_change"],
                "safetyRatingChange": row["safety_rating_change"],
                "status": row["status"],
                "classId": row["class_id"],
                "className": row["class_name"],
                "scoringEligible": bool(row["scoring_eligible"]),
                "distancePercent": row["distance_percent"],
                "countryCode": "",
                "division": "",
                "lapsLed": 0,
                "averageLapTime": None,
                "intervalSeconds": None,
                "championshipPoints": None,
                "oldIRating": None,
                "newIRating": None,
                "oldSafetyRating": None,
                "newSafetyRating": None,
            }
            result.update(extra)
            results.append(result)

        current_finishes = {
            result["_driverDbId"]: result["finishPosition"] for result in results
        }
        recurrent_opponents: dict[int, list[int]] = {}
        for recurrent in recurrent_rows:
            driver_db_id = int(recurrent["driver_id"])
            opponent_id = int(recurrent["opponent_id"])
            if opponent_id in current_finishes:
                recurrent_opponents.setdefault(driver_db_id, []).append(opponent_id)
        recurrent_scores: dict[int, float] = {}
        for driver_db_id, opponent_ids in recurrent_opponents.items():
            driver_finish = current_finishes.get(driver_db_id)
            if driver_finish is None or not opponent_ids:
                continue
            wins = sum(
                1
                for opponent_id in opponent_ids
                if driver_finish < current_finishes[opponent_id]
            )
            ties = sum(
                1
                for opponent_id in opponent_ids
                if driver_finish == current_finishes[opponent_id]
            )
            recurrent_scores[driver_db_id] = (
                (wins + ties * 0.5) / len(opponent_ids) * 100
            )
        if event["platform"] == "assetto-corsa":
            field_best_laps = [
                float(driver["bestLapTime"])
                for driver in rich["drivers"].values()
                if as_float(driver.get("bestLapTime")) is not None
                and float(driver["bestLapTime"]) > 0
            ]
            score_event = {
                "fieldSize": event["field_size"],
                **rich["event"],
            }
            for result in results:
                result.update(
                    calculate_assetto_scores(
                        result,
                        score_event,
                        field_best_laps,
                        recurrent_scores.get(result["_driverDbId"]),
                    )
                )
        elif event["platform"] == "iracing":
            field_best_laps = [
                float(result["bestLapTime"])
                for result in results
                if as_float(result.get("bestLapTime")) is not None
                and float(result["bestLapTime"]) > 0
            ]
            score_event = {
                "fieldSize": event["field_size"],
                "strengthOfField": event["strength_of_field"],
                **rich["event"],
            }
            for result in results:
                result.update(
                    calculate_iracing_scores(
                        result,
                        score_event,
                        field_best_laps,
                        recurrent_scores.get(result["_driverDbId"]),
                    )
                )
        for result in results:
            result.pop("_driverDbId", None)

        best_laps = [
            result["bestLapTime"]
            for result in results
            if result["bestLapTime"] and result["bestLapTime"] > 0
        ]
        owner_result = next(
            (result for result in results if result["isOwner"]), None
        )
        return {
            "ownerIracingId": owner_iracing_id,
            "event": {
                "id": event["id"],
                "externalEventId": event["external_event_id"],
                "seriesName": event["series_name"],
                "seasonName": event["season_name"],
                "week": event["race_week"],
                "startTime": event["start_time"],
                "track": event["track"],
                "layout": event["layout"],
                "splitNumber": event["split_number"],
                "splitTotal": event["split_total"],
                "strengthOfField": event["strength_of_field"],
                "fieldSize": event["field_size"],
                "official": bool(event["official"]),
                "platform": event["platform"],
                "telemetryFiles": [
                    {
                        "id": telemetry["id"],
                        "filename": telemetry["filename"],
                        "fileSize": telemetry["file_size"],
                        "sessionType": telemetry["session_type"],
                        "trackName": telemetry["track_name"],
                        "carName": telemetry["car_name"],
                        "tickRate": telemetry["tick_rate"],
                        "sampleCount": telemetry["sample_count"],
                        "channelCount": telemetry["channel_count"],
                    }
                    for telemetry in telemetry_rows
                ],
                **rich["event"],
            },
            "summary": {
                "totalIncidents": sum(result["incidents"] for result in results),
                "averageIncidents": (
                    sum(result["incidents"] for result in results) / len(results)
                    if results
                    else 0
                ),
                "fastestLapTime": min(best_laps) if best_laps else None,
                "finishers": sum(
                    1
                    for result in results
                    if str(result["status"]).lower()
                    in {"running", "finished", "finalizada", "finalizado"}
                ),
                "ownerResult": owner_result,
            },
            "results": results,
        }

    def get_session_detail(self, week: int) -> dict[str, Any]:
        with self.connect() as connection:
            league_id, owner_iracing_id = self._active_league_and_owner(connection)
            league = connection.execute(
                "SELECT series_name, season, platform FROM leagues WHERE id = ?",
                (league_id,),
            ).fetchone()
            events = connection.execute(
                """
                SELECT id FROM race_events
                WHERE league_id = ? AND race_week = ?
                ORDER BY COALESCE(start_time, ''), id
                """,
                (league_id, week),
            ).fetchall()
        if not events:
            raise ValueError("La sesión seleccionada no contiene carreras importadas")

        race_details = [self.get_race_detail(int(event["id"])) for event in events]
        grouped: dict[str, dict[str, Any]] = {}
        race_summaries = []
        total_incidents = 0
        sof_values = []
        owner_races = 0

        for detail in race_details:
            event = detail["event"]
            results = detail["results"]
            owner_result = next(
                (result for result in results if result["isOwner"]), None
            )
            if owner_result:
                owner_races += 1
            total_incidents += detail["summary"]["totalIncidents"]
            if event["strengthOfField"]:
                sof_values.append(event["strengthOfField"])
            race_summaries.append(
                {
                    "id": event["id"],
                    "startTime": event["startTime"],
                    "track": event["track"],
                    "layout": event["layout"],
                    "splitNumber": event["splitNumber"],
                    "splitTotal": event["splitTotal"],
                    "strengthOfField": event["strengthOfField"],
                    "fieldSize": event["fieldSize"],
                    "ownerResult": {
                        "finishPosition": owner_result["finishPosition"],
                        "startPosition": owner_result["startPosition"],
                        "incidents": owner_result["incidents"],
                        "iratingChange": owner_result["iratingChange"],
                        "safetyRatingChange": owner_result["safetyRatingChange"],
                        "gridScore": owner_result.get("gridScore"),
                        "cleanlinessScore": owner_result.get(
                            "cleanlinessScore"
                        ),
                    }
                    if owner_result
                    else None,
                }
            )
            for result in results:
                driver = grouped.setdefault(
                    result["iracingId"],
                    {
                        "iracingId": result["iracingId"],
                        "name": result["name"],
                        "initials": result["initials"],
                        "color": result["color"],
                        "isOwner": result["isOwner"],
                        "entries": [],
                    },
                )
                driver["entries"].append(
                    {
                        "eventId": event["id"],
                        "startTime": event["startTime"],
                        "track": event["track"],
                        "layout": event["layout"],
                        "splitNumber": event["splitNumber"],
                        "splitTotal": event["splitTotal"],
                        "strengthOfField": event["strengthOfField"],
                        "result": result,
                        "ownerResult": owner_result,
                    }
                )

        drivers = []
        for driver in grouped.values():
            entries = driver.pop("entries")
            results = [entry["result"] for entry in entries]
            starts = [
                result["startPosition"]
                for result in results
                if result["startPosition"] is not None
            ]
            best_laps = [
                result["bestLapTime"]
                for result in results
                if result["bestLapTime"] and result["bestLapTime"] > 0
            ]
            irating_start = next(
                (
                    result["oldIRating"]
                    for result in results
                    if result.get("oldIRating") is not None
                ),
                None,
            )
            irating_end = next(
                (
                    result["newIRating"]
                    for result in reversed(results)
                    if result.get("newIRating") is not None
                ),
                None,
            )
            safety_start = next(
                (
                    result["oldSafetyRating"]
                    for result in results
                    if result.get("oldSafetyRating") is not None
                ),
                None,
            )
            safety_end = next(
                (
                    result["newSafetyRating"]
                    for result in reversed(results)
                    if result.get("newSafetyRating") is not None
                ),
                None,
            )
            meetings = [
                entry
                for entry in entries
                if not driver["isOwner"] and entry["ownerResult"] is not None
            ]
            owner_ahead = sum(
                1
                for entry in meetings
                if entry["ownerResult"]["finishPosition"]
                < entry["result"]["finishPosition"]
            )
            rival_ahead = sum(
                1
                for entry in meetings
                if entry["ownerResult"]["finishPosition"]
                > entry["result"]["finishPosition"]
            )
            drivers.append(
                {
                    **driver,
                    "appearances": len(results),
                    "repeated": len(results) > 1,
                    "averageFinish": sum(
                        result["finishPosition"] for result in results
                    )
                    / len(results),
                    "bestFinish": min(result["finishPosition"] for result in results),
                    "wins": sum(
                        1 for result in results if result["finishPosition"] == 1
                    ),
                    "averageStart": sum(starts) / len(starts) if starts else None,
                    "positionsGained": sum(
                        result["positionChange"] or 0 for result in results
                    ),
                    "totalIncidents": sum(
                        result["incidents"] for result in results
                    ),
                    "averageIncidents": sum(
                        result["incidents"] for result in results
                    )
                    / len(results),
                    "lapsComplete": sum(
                        result["lapsComplete"] for result in results
                    ),
                    "bestLapTime": min(best_laps) if best_laps else None,
                    "iratingStart": irating_start,
                    "iratingEnd": irating_end,
                    "iratingChange": (
                        irating_end - irating_start
                        if irating_start is not None and irating_end is not None
                        else sum(
                            result["iratingChange"] or 0 for result in results
                        )
                    ),
                    "safetyRatingStart": safety_start,
                    "safetyRatingEnd": safety_end,
                    "safetyRatingChange": (
                        safety_end - safety_start
                        if safety_start is not None and safety_end is not None
                        else sum(
                            result["safetyRatingChange"] or 0
                            for result in results
                        )
                    ),
                    "gridRating": (
                        summarize_grid_scores(results)
                    ),
                    "meetingsWithOwner": len(meetings),
                    "ownerAhead": owner_ahead,
                    "rivalAhead": rival_ahead,
                    "sharedRaces": [
                        {
                            "eventId": entry["eventId"],
                            "track": entry["track"],
                            "ownerPosition": entry["ownerResult"]["finishPosition"],
                            "rivalPosition": entry["result"]["finishPosition"],
                        }
                        for entry in meetings
                    ],
                    "raceDetails": [
                        {
                            "eventId": entry["eventId"],
                            "startTime": entry["startTime"],
                            "track": entry["track"],
                            "layout": entry["layout"],
                            "splitNumber": entry["splitNumber"],
                            "splitTotal": entry["splitTotal"],
                            "strengthOfField": entry["strengthOfField"],
                            "startPosition": entry["result"]["startPosition"],
                            "finishPosition": entry["result"]["finishPosition"],
                            "positionChange": entry["result"]["positionChange"],
                            "incidents": entry["result"]["incidents"],
                            "lapsComplete": entry["result"]["lapsComplete"],
                            "bestLapTime": entry["result"]["bestLapTime"],
                            "gridScore": entry["result"].get("gridScore"),
                            "performanceScore": entry["result"].get(
                                "performanceScore"
                            ),
                            "cleanlinessScore": entry["result"].get(
                                "cleanlinessScore"
                            ),
                            "scoreConfidence": entry["result"].get(
                                "scoreConfidence"
                            ),
                            "cutsPer30Minutes": entry["result"].get(
                                "cutsPer30Minutes"
                            ),
                            "incidentsPer1000Corners": entry["result"].get(
                                "incidentsPer1000Corners"
                            ),
                            "incidentsPer30Minutes": entry["result"].get(
                                "incidentsPer30Minutes"
                            ),
                            "scoreComponents": entry["result"].get(
                                "scoreComponents"
                            ),
                            "oldIRating": entry["result"]["oldIRating"],
                            "newIRating": entry["result"]["newIRating"],
                            "iratingChange": entry["result"]["iratingChange"],
                            "oldSafetyRating": entry["result"]["oldSafetyRating"],
                            "newSafetyRating": entry["result"]["newSafetyRating"],
                            "safetyRatingChange": entry["result"][
                                "safetyRatingChange"
                            ],
                            "ownerPosition": (
                                entry["ownerResult"]["finishPosition"]
                                if entry["ownerResult"] is not None
                                else None
                            ),
                            "ownerIncidents": (
                                entry["ownerResult"]["incidents"]
                                if entry["ownerResult"] is not None
                                else None
                            ),
                        }
                        for entry in entries
                    ],
                }
            )
        drivers.sort(
            key=lambda driver: (
                not driver["repeated"],
                -driver["appearances"],
                driver["averageFinish"],
                driver["name"].lower(),
            )
        )
        return {
            "ownerIracingId": owner_iracing_id,
            "session": {
                "week": week,
                "seriesName": league["series_name"],
                "season": league["season"],
                "track": race_details[-1]["event"]["track"],
                "layout": race_details[-1]["event"]["layout"],
                "raceCount": len(race_details),
                "uniqueDrivers": len(drivers),
                "repeatedDrivers": sum(
                    1 for driver in drivers if driver["repeated"]
                ),
                "ownerRaces": owner_races,
                "averageSof": round(sum(sof_values) / len(sof_values))
                if sof_values
                else 0,
                "totalIncidents": total_incidents,
            },
            "races": list(reversed(race_summaries)),
            "drivers": drivers,
        }

    def get_driver_detail(
        self, iracing_id: str, scope: str = "active"
    ) -> dict[str, Any]:
        if scope not in {"active", "global"}:
            raise ValueError("El ámbito del perfil no es válido")
        with self.connect() as connection:
            league_id, owner_iracing_id = self._active_league_and_owner(connection)
            league = connection.execute(
                "SELECT series_name, season, platform FROM leagues WHERE id = ?",
                (league_id,),
            ).fetchone()
            if scope == "global":
                events = connection.execute(
                    """
                    SELECT DISTINCT event.id, source_league.series_name,
                           source_league.season
                    FROM race_events AS event
                    JOIN leagues AS source_league
                      ON source_league.id = event.league_id
                    JOIN race_results AS result ON result.event_id = event.id
                    JOIN drivers AS driver ON driver.id = result.driver_id
                    WHERE source_league.platform = ?
                      AND driver.iracing_id = ?
                    ORDER BY COALESCE(event.start_time, ''), event.id
                    """,
                    (league["platform"], str(iracing_id)),
                ).fetchall()
            else:
                events = connection.execute(
                    """
                    SELECT DISTINCT event.id, source_league.series_name,
                           source_league.season
                    FROM race_events AS event
                    JOIN leagues AS source_league
                      ON source_league.id = event.league_id
                    JOIN race_results AS result ON result.event_id = event.id
                    JOIN drivers AS driver ON driver.id = result.driver_id
                    WHERE event.league_id = ? AND driver.iracing_id = ?
                    ORDER BY COALESCE(event.start_time, ''), event.id
                    """,
                    (league_id, str(iracing_id)),
                ).fetchall()
        if not events:
            raise ValueError(
                "El piloto seleccionado no tiene carreras en este ámbito"
            )

        event_context = {
            int(event["id"]): {
                "seriesName": event["series_name"],
                "season": event["season"],
            }
            for event in events
        }
        details = [self.get_race_detail(int(event["id"])) for event in events]
        entries = []
        for detail in details:
            result = next(
                (
                    item
                    for item in detail["results"]
                    if item["iracingId"] == str(iracing_id)
                ),
                None,
            )
            if result is None:
                continue
            owner_result = next(
                (item for item in detail["results"] if item["isOwner"]), None
            )
            entries.append(
                {
                    "event": detail["event"],
                    "result": result,
                    "ownerResult": owner_result,
                    "allResults": detail["results"],
                    **event_context[int(detail["event"]["id"])],
                }
            )
        if not entries:
            raise ValueError(
                "No se ha podido reconstruir el historial de este piloto"
            )

        results = [entry["result"] for entry in entries]
        finishes = [result["finishPosition"] for result in results]
        starts = [
            result["startPosition"]
            for result in results
            if result["startPosition"] is not None
        ]
        best_laps = [
            result["bestLapTime"]
            for result in results
            if result["bestLapTime"] and result["bestLapTime"] > 0
        ]
        sof_values = [
            entry["event"]["strengthOfField"]
            for entry in entries
            if entry["event"]["strengthOfField"]
        ]
        irating_start = next(
            (
                result["oldIRating"]
                for result in results
                if result.get("oldIRating") is not None
            ),
            None,
        )
        irating_end = next(
            (
                result["newIRating"]
                for result in reversed(results)
                if result.get("newIRating") is not None
            ),
            None,
        )
        safety_start = next(
            (
                result["oldSafetyRating"]
                for result in results
                if result.get("oldSafetyRating") is not None
            ),
            None,
        )
        safety_end = next(
            (
                result["newSafetyRating"]
                for result in reversed(results)
                if result.get("newSafetyRating") is not None
            ),
            None,
        )
        is_owner = results[-1]["isOwner"]
        meetings = [
            entry
            for entry in entries
            if not is_owner and entry["ownerResult"] is not None
        ]
        owner_ahead = sum(
            1
            for entry in meetings
            if entry["ownerResult"]["finishPosition"]
            < entry["result"]["finishPosition"]
        )
        rival_ahead = sum(
            1
            for entry in meetings
            if entry["ownerResult"]["finishPosition"]
            > entry["result"]["finishPosition"]
        )

        periods: dict[str, dict[str, Any]] = {}
        for entry in entries:
            event = entry["event"]
            period_key = f"{entry['seriesName']}|{entry['season']}"
            period = periods.setdefault(
                period_key,
                {
                    "seriesName": entry["seriesName"],
                    "season": entry["season"],
                    "races": 0,
                    "sessions": set(),
                    "tracks": set(),
                    "ownerAhead": 0,
                    "rivalAhead": 0,
                    "latestStart": "",
                },
            )
            period["races"] += 1
            period["sessions"].add(
                (
                    event["week"],
                    event["track"],
                    event["layout"] or "",
                )
            )
            period["tracks"].add((event["track"], event["layout"] or ""))
            period["latestStart"] = max(
                period["latestStart"], event["startTime"] or ""
            )
            if not is_owner and entry["ownerResult"] is not None:
                if (
                    entry["ownerResult"]["finishPosition"]
                    < entry["result"]["finishPosition"]
                ):
                    period["ownerAhead"] += 1
                elif (
                    entry["ownerResult"]["finishPosition"]
                    > entry["result"]["finishPosition"]
                ):
                    period["rivalAhead"] += 1
        period_breakdown = [
            {
                "seriesName": period["seriesName"],
                "season": period["season"],
                "races": period["races"],
                "sessions": len(period["sessions"]),
                "tracks": len(period["tracks"]),
                "ownerAhead": period["ownerAhead"],
                "rivalAhead": period["rivalAhead"],
                "latestStart": period["latestStart"],
            }
            for period in periods.values()
        ]
        period_breakdown.sort(
            key=lambda period: (
                period["latestStart"],
                period["seriesName"].lower(),
            ),
            reverse=True,
        )

        tracks: dict[str, dict[str, Any]] = {}
        for entry in entries:
            event = entry["event"]
            result = entry["result"]
            key = f"{event['track']}|{event['layout'] or ''}"
            track = tracks.setdefault(
                key,
                {
                    "track": event["track"],
                    "layout": event["layout"],
                    "races": 0,
                    "finishes": [],
                    "starts": [],
                    "positionChanges": [],
                    "incidents": 0,
                    "wins": 0,
                    "topFive": 0,
                    "topTen": 0,
                    "lapsComplete": 0,
                    "lapsLed": 0,
                    "validLaps": 0,
                    "bestLaps": [],
                    "averageLaps": [],
                    "theoreticalBestLaps": [],
                    "fieldSizes": [],
                    "sofValues": [],
                    "gridScores": [],
                    "performanceScores": [],
                    "cleanlinessScores": [],
                    "consistencyScores": [],
                    "confidenceScores": [],
                    "drivingMinutes": 0.0,
                    "cars": set(),
                    "tyres": set(),
                    "rivals": set(),
                    "duelWins": 0,
                    "duelLosses": 0,
                    "duelTies": 0,
                    "firstStart": "",
                    "lastStart": "",
                },
            )
            track["races"] += 1
            track["finishes"].append(result["finishPosition"])
            if result["startPosition"] is not None:
                track["starts"].append(result["startPosition"])
            if result["positionChange"] is not None:
                track["positionChanges"].append(result["positionChange"])
            track["incidents"] += result["incidents"]
            track["wins"] += int(result["finishPosition"] == 1)
            track["topFive"] += int(result["finishPosition"] <= 5)
            track["topTen"] += int(result["finishPosition"] <= 10)
            track["lapsComplete"] += result["lapsComplete"] or 0
            track["lapsLed"] += result["lapsLed"] or 0
            track["validLaps"] += result.get("validLapCount") or 0
            if result.get("bestLapTime"):
                track["bestLaps"].append(result["bestLapTime"])
            if result.get("averageLapTime"):
                track["averageLaps"].append(result["averageLapTime"])
            if result.get("theoreticalBestLapTime"):
                track["theoreticalBestLaps"].append(
                    result["theoreticalBestLapTime"]
                )
            if event["fieldSize"]:
                track["fieldSizes"].append(event["fieldSize"])
            if event["strengthOfField"]:
                track["sofValues"].append(event["strengthOfField"])
            if result.get("gridScore") is not None:
                track["gridScores"].append(result["gridScore"])
            if result.get("performanceScore") is not None:
                track["performanceScores"].append(result["performanceScore"])
            if result.get("cleanlinessScore") is not None:
                track["cleanlinessScores"].append(result["cleanlinessScore"])
            consistency_score = (result.get("scoreComponents") or {}).get(
                "consistency"
            )
            if consistency_score is not None:
                track["consistencyScores"].append(consistency_score)
            if result.get("scoreConfidence") is not None:
                track["confidenceScores"].append(result["scoreConfidence"])
            track["drivingMinutes"] += result.get("drivingTimeMinutes") or 0
            if result.get("carName"):
                track["cars"].add(result["carName"])
            track["tyres"].update(result.get("tyreCompounds") or [])
            start_time = event["startTime"] or ""
            if start_time:
                track["firstStart"] = min(
                    track["firstStart"] or start_time, start_time
                )
                track["lastStart"] = max(track["lastStart"], start_time)
            for opponent in entry["allResults"]:
                if opponent["iracingId"] == result["iracingId"]:
                    continue
                track["rivals"].add(opponent["iracingId"])
                if result["finishPosition"] < opponent["finishPosition"]:
                    track["duelWins"] += 1
                elif result["finishPosition"] > opponent["finishPosition"]:
                    track["duelLosses"] += 1
                else:
                    track["duelTies"] += 1
        track_breakdown = [
            {
                "track": track["track"],
                "layout": track["layout"],
                "races": track["races"],
                "averageFinish": sum(track["finishes"]) / len(track["finishes"]),
                "bestFinish": min(track["finishes"]),
                "worstFinish": max(track["finishes"]),
                "averageStart": (
                    sum(track["starts"]) / len(track["starts"])
                    if track["starts"]
                    else None
                ),
                "positionsGained": sum(track["positionChanges"]),
                "totalIncidents": track["incidents"],
                "averageIncidents": track["incidents"] / track["races"],
                "wins": track["wins"],
                "topFive": track["topFive"],
                "topTen": track["topTen"],
                "lapsComplete": track["lapsComplete"],
                "lapsLed": track["lapsLed"],
                "validLaps": track["validLaps"],
                "bestLapTime": (
                    min(track["bestLaps"]) if track["bestLaps"] else None
                ),
                "averageLapTime": (
                    sum(track["averageLaps"]) / len(track["averageLaps"])
                    if track["averageLaps"]
                    else None
                ),
                "theoreticalBestLapTime": (
                    min(track["theoreticalBestLaps"])
                    if track["theoreticalBestLaps"]
                    else None
                ),
                "averageFieldSize": (
                    sum(track["fieldSizes"]) / len(track["fieldSizes"])
                    if track["fieldSizes"]
                    else None
                ),
                "averageSof": round(
                    sum(track["sofValues"]) / len(track["sofValues"])
                )
                if track["sofValues"]
                else 0,
                "averageGridScore": (
                    sum(track["gridScores"]) / len(track["gridScores"])
                    if track["gridScores"]
                    else None
                ),
                "bestGridScore": (
                    max(track["gridScores"]) if track["gridScores"] else None
                ),
                "averagePerformance": (
                    sum(track["performanceScores"])
                    / len(track["performanceScores"])
                    if track["performanceScores"]
                    else None
                ),
                "averageCleanliness": (
                    sum(track["cleanlinessScores"])
                    / len(track["cleanlinessScores"])
                    if track["cleanlinessScores"]
                    else None
                ),
                "averageConsistency": (
                    sum(track["consistencyScores"])
                    / len(track["consistencyScores"])
                    if track["consistencyScores"]
                    else None
                ),
                "averageConfidence": (
                    sum(track["confidenceScores"])
                    / len(track["confidenceScores"])
                    if track["confidenceScores"]
                    else None
                ),
                "drivingMinutes": track["drivingMinutes"],
                "cars": sorted(track["cars"]),
                "tyreCompounds": sorted(track["tyres"]),
                "uniqueRivals": len(track["rivals"]),
                "duelWins": track["duelWins"],
                "duelLosses": track["duelLosses"],
                "duelTies": track["duelTies"],
                "firstStart": track["firstStart"] or None,
                "lastStart": track["lastStart"] or None,
            }
            for track in tracks.values()
        ]
        track_breakdown.sort(
            key=lambda track: (-track["races"], track["averageFinish"], track["track"])
        )

        latest = results[-1]
        grid_rating = summarize_grid_scores(results)
        unique_sessions = {
            (
                entry["seriesName"],
                entry["season"],
                entry["event"]["week"],
                entry["event"]["track"],
                entry["event"]["layout"] or "",
            )
            for entry in entries
        }
        return {
            "scope": scope,
            "ownerIracingId": owner_iracing_id,
            "seriesName": (
                league["series_name"]
                if scope == "active"
                else "Todas las series"
            ),
            "season": (
                league["season"]
                if scope == "active"
                else "Todo el historial"
            ),
            "driver": {
                "iracingId": latest["iracingId"],
                "name": latest["name"],
                "initials": latest["initials"],
                "color": latest["color"],
                "countryCode": latest["countryCode"],
                "division": latest["division"],
                "isOwner": is_owner,
            },
            "summary": {
                "races": len(results),
                "weeks": len(
                    {
                        (
                            entry["seriesName"],
                            entry["season"],
                            entry["event"]["week"],
                        )
                        for entry in entries
                    }
                ),
                "sessions": len(unique_sessions),
                "series": len({entry["seriesName"] for entry in entries}),
                "seasons": len(
                    {
                        (entry["seriesName"], entry["season"])
                        for entry in entries
                    }
                ),
                "wins": sum(1 for finish in finishes if finish == 1),
                "topFive": sum(1 for finish in finishes if finish <= 5),
                "topTen": sum(1 for finish in finishes if finish <= 10),
                "averageFinish": sum(finishes) / len(finishes),
                "bestFinish": min(finishes),
                "worstFinish": max(finishes),
                "averageStart": sum(starts) / len(starts) if starts else None,
                "positionsGained": sum(
                    result["positionChange"] or 0 for result in results
                ),
                "totalIncidents": sum(result["incidents"] for result in results),
                "averageIncidents": sum(
                    result["incidents"] for result in results
                )
                / len(results),
                "lapsComplete": sum(result["lapsComplete"] for result in results),
                "lapsLed": sum(result["lapsLed"] or 0 for result in results),
                "bestLapTime": min(best_laps) if best_laps else None,
                "averageSof": round(sum(sof_values) / len(sof_values))
                if sof_values
                else 0,
                "iratingStart": irating_start,
                "iratingEnd": irating_end,
                "iratingChange": (
                    irating_end - irating_start
                    if irating_start is not None and irating_end is not None
                    else sum(result["iratingChange"] or 0 for result in results)
                ),
                "safetyRatingStart": safety_start,
                "safetyRatingEnd": safety_end,
                "safetyRatingChange": (
                    safety_end - safety_start
                    if safety_start is not None and safety_end is not None
                    else sum(
                        result["safetyRatingChange"] or 0 for result in results
                    )
                ),
                "meetingsWithOwner": len(meetings),
                "ownerAhead": owner_ahead,
                "rivalAhead": rival_ahead,
                "gridRating": grid_rating,
            },
            "periods": period_breakdown,
            "tracks": track_breakdown,
            "races": [
                {
                    "eventId": entry["event"]["id"],
                    "seriesName": entry["seriesName"],
                    "season": entry["season"],
                    "week": entry["event"]["week"],
                    "startTime": entry["event"]["startTime"],
                    "track": entry["event"]["track"],
                    "layout": entry["event"]["layout"],
                    "splitNumber": entry["event"]["splitNumber"],
                    "splitTotal": entry["event"]["splitTotal"],
                    "strengthOfField": entry["event"]["strengthOfField"],
                    "fieldSize": entry["event"]["fieldSize"],
                    "startPosition": entry["result"]["startPosition"],
                    "finishPosition": entry["result"]["finishPosition"],
                    "positionChange": entry["result"]["positionChange"],
                    "incidents": entry["result"]["incidents"],
                    "lapsComplete": entry["result"]["lapsComplete"],
                    "lapsLed": entry["result"]["lapsLed"],
                    "bestLapTime": entry["result"]["bestLapTime"],
                    "averageLapTime": entry["result"]["averageLapTime"],
                    "validLapCount": entry["result"].get("validLapCount"),
                    "lapTimeDeviation": entry["result"].get(
                        "lapTimeDeviation"
                    ),
                    "theoreticalBestLapTime": entry["result"].get(
                        "theoreticalBestLapTime"
                    ),
                    "bestSectorTimes": entry["result"].get(
                        "bestSectorTimes"
                    ),
                    "carName": entry["result"].get("carName"),
                    "tyreCompounds": entry["result"].get("tyreCompounds", []),
                    "status": entry["result"]["status"],
                    "championshipPoints": entry["result"]["championshipPoints"],
                    "oldIRating": entry["result"]["oldIRating"],
                    "newIRating": entry["result"]["newIRating"],
                    "iratingChange": entry["result"]["iratingChange"],
                    "oldSafetyRating": entry["result"]["oldSafetyRating"],
                    "newSafetyRating": entry["result"]["newSafetyRating"],
                    "safetyRatingChange": entry["result"]["safetyRatingChange"],
                    "gridScore": entry["result"].get("gridScore"),
                    "performanceScore": entry["result"].get("performanceScore"),
                    "cleanlinessScore": entry["result"].get("cleanlinessScore"),
                    "scoreConfidence": entry["result"].get("scoreConfidence"),
                    "drivingTimeMinutes": entry["result"].get(
                        "drivingTimeMinutes"
                    ),
                    "cutsPer30Minutes": entry["result"].get(
                        "cutsPer30Minutes"
                    ),
                    "incidentsPer1000Corners": entry["result"].get(
                        "incidentsPer1000Corners"
                    ),
                    "incidentsPer30Minutes": entry["result"].get(
                        "incidentsPer30Minutes"
                    ),
                    "scoreComponents": entry["result"].get("scoreComponents"),
                    "ownerPosition": (
                        entry["ownerResult"]["finishPosition"]
                        if entry["ownerResult"] is not None
                        else None
                    ),
                    "ownerIncidents": (
                        entry["ownerResult"]["incidents"]
                        if entry["ownerResult"] is not None
                        else None
                    ),
                }
                for entry in reversed(entries)
            ],
        }

    def get_rival_comparisons(self) -> dict[str, Any]:
        with self.connect() as connection:
            league_id, owner_iracing_id = self._active_league_and_owner(connection)
            owner = connection.execute(
                "SELECT id, name FROM drivers WHERE iracing_id = ?",
                (owner_iracing_id,),
            ).fetchone()
            if not owner:
                return {
                    "owner": {
                        "iracingId": owner_iracing_id,
                        "name": f"Piloto {owner_iracing_id}",
                    },
                    "summary": {
                        "races": 0,
                        "uniqueRivals": 0,
                        "recurrentRivals": 0,
                        "totalEncounters": 0,
                    },
                    "rivals": [],
                }
            rows = connection.execute(
                """
                SELECT rival.iracing_id, rival.name, rival.initials, rival.color,
                       re.id AS event_id, re.start_time, re.track, re.layout,
                       re.race_week, re.strength_of_field, re.field_size,
                       re.split_number, re.split_total,
                       owner_result.finish_position AS owner_position,
                       owner_result.start_position AS owner_start_position,
                       owner_result.incidents AS owner_incidents,
                       rival_result.finish_position AS rival_position,
                       rival_result.start_position AS rival_start_position,
                       rival_result.incidents AS rival_incidents
                FROM race_results owner_result
                JOIN race_events re ON re.id = owner_result.event_id
                JOIN race_results rival_result
                  ON rival_result.event_id = owner_result.event_id
                 AND rival_result.driver_id != owner_result.driver_id
                JOIN drivers rival ON rival.id = rival_result.driver_id
                WHERE re.league_id = ? AND owner_result.driver_id = ?
                ORDER BY COALESCE(re.start_time, ''), re.id
                """,
                (league_id, owner["id"]),
            ).fetchall()

        grouped: dict[str, dict[str, Any]] = {}
        race_ids: set[int] = set()
        for row in rows:
            race_ids.add(row["event_id"])
            rival = grouped.setdefault(
                row["iracing_id"],
                {
                    "iracingId": row["iracing_id"],
                    "name": row["name"],
                    "initials": row["initials"],
                    "color": row["color"],
                    "meetings": [],
                },
            )
            rival["meetings"].append(
                {
                    "eventId": row["event_id"],
                    "startTime": row["start_time"],
                    "track": row["track"],
                    "layout": row["layout"],
                    "week": row["race_week"],
                    "strengthOfField": row["strength_of_field"],
                    "fieldSize": row["field_size"],
                    "splitNumber": row["split_number"],
                    "splitTotal": row["split_total"],
                    "ownerPosition": row["owner_position"],
                    "ownerStartPosition": row["owner_start_position"],
                    "rivalPosition": row["rival_position"],
                    "rivalStartPosition": row["rival_start_position"],
                    "ownerIncidents": row["owner_incidents"],
                    "rivalIncidents": row["rival_incidents"],
                }
            )

        rivals = []
        for rival in grouped.values():
            meetings = rival.pop("meetings")
            total = len(meetings)
            wins = sum(
                1
                for meeting in meetings
                if meeting["ownerPosition"] < meeting["rivalPosition"]
            )
            losses = sum(
                1
                for meeting in meetings
                if meeting["ownerPosition"] > meeting["rivalPosition"]
            )
            ties = total - wins - losses
            recent = meetings[-5:]
            recent_wins = sum(
                1
                for meeting in recent
                if meeting["ownerPosition"] < meeting["rivalPosition"]
            )
            win_rate = (wins / total * 100) if total else 0
            recent_rate = (recent_wins / len(recent) * 100) if recent else 0
            rivals.append(
                {
                    **rival,
                    "meetings": total,
                    "ownerAhead": wins,
                    "rivalAhead": losses,
                    "ties": ties,
                    "winRate": win_rate,
                    "recentWinRate": recent_rate,
                    "trend": recent_rate - win_rate,
                    "averageOwnerPosition": sum(
                        meeting["ownerPosition"] for meeting in meetings
                    )
                    / total,
                    "averageRivalPosition": sum(
                        meeting["rivalPosition"] for meeting in meetings
                    )
                    / total,
                    "averagePositionAdvantage": sum(
                        meeting["rivalPosition"] - meeting["ownerPosition"]
                        for meeting in meetings
                    )
                    / total,
                    "averageOwnerIncidents": sum(
                        meeting["ownerIncidents"] for meeting in meetings
                    )
                    / total,
                    "averageRivalIncidents": sum(
                        meeting["rivalIncidents"] for meeting in meetings
                    )
                    / total,
                    "meetingDetails": list(reversed(meetings)),
                    "recentMeetings": list(reversed(meetings[-5:])),
                }
            )
        rivals.sort(
            key=lambda rival: (
                -rival["meetings"],
                -rival["winRate"],
                rival["name"].lower(),
            )
        )
        return {
            "owner": {"iracingId": owner_iracing_id, "name": owner["name"]},
            "summary": {
                "races": len(race_ids),
                "uniqueRivals": len(rivals),
                "recurrentRivals": sum(
                    1 for rival in rivals if rival["meetings"] > 1
                ),
                "totalEncounters": len(rows),
            },
            "rivals": rivals,
        }

    def save_custom_championship(
        self, values: dict[str, Any], championship_id: int | None = None
    ) -> dict[str, Any]:
        name = str(values.get("name") or "").strip()
        if not name or len(name) > 80:
            raise ValueError("Indica un nombre de campeonato de hasta 80 caracteres")
        participant_mode = str(
            values.get("participantMode") or "recurrent"
        ).strip()
        if participant_mode not in {"recurrent", "all", "selected"}:
            raise ValueError("La selección de pilotos no es válida")
        ranking_mode = str(values.get("rankingMode") or "all-races").strip()
        if ranking_mode not in {"all-races", "weekly"}:
            raise ValueError("El sistema de clasificación no es válido")
        series_names = sorted(
            {
                str(value).strip()
                for value in values.get("seriesNames", [])
                if str(value).strip()
            }
        )
        driver_ids = sorted(
            {
                str(value).strip()
                for value in values.get("driverIds", [])
                if str(value).strip()
            }
        )
        if participant_mode == "selected" and not driver_ids:
            raise ValueError("Selecciona al menos un piloto")
        start_date = str(values.get("startDate") or "").strip() or None
        end_date = str(values.get("endDate") or "").strip() or None
        try:
            parsed_start = (
                datetime.fromisoformat(start_date).date() if start_date else None
            )
            parsed_end = datetime.fromisoformat(end_date).date() if end_date else None
        except ValueError as error:
            raise ValueError("Las fechas del campeonato no son válidas") from error
        if parsed_start and parsed_end and parsed_start > parsed_end:
            raise ValueError("La fecha inicial no puede ser posterior a la final")
        minimum_races = max(1, min(999, as_int(values.get("minimumRaces"), 2)))
        include_owner = bool(values.get("includeOwner", True))
        with self.connect() as connection:
            active = connection.execute(
                "SELECT platform FROM leagues WHERE active = 1 ORDER BY id LIMIT 1"
            ).fetchone()
            platform = str(active["platform"] if active else "iracing")
            now = utc_now()
            payload = (
                name,
                platform,
                json.dumps(series_names, ensure_ascii=False),
                start_date,
                end_date,
                participant_mode,
                json.dumps(driver_ids, ensure_ascii=False),
                int(include_owner),
                minimum_races,
                ranking_mode,
                now,
            )
            if championship_id is None:
                cursor = connection.execute(
                    """
                    INSERT INTO custom_championships
                        (name, platform, series_names_json, start_date, end_date,
                         participant_mode, driver_ids_json, include_owner,
                         minimum_races, ranking_mode, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (*payload[:-1], now, now),
                )
                saved_id = int(cursor.lastrowid)
            else:
                existing = connection.execute(
                    """
                    SELECT id FROM custom_championships
                    WHERE id = ? AND platform = ?
                    """,
                    (championship_id, platform),
                ).fetchone()
                if not existing:
                    raise ValueError("El campeonato seleccionado no existe")
                connection.execute(
                    """
                    UPDATE custom_championships
                    SET name = ?, platform = ?, series_names_json = ?,
                        start_date = ?, end_date = ?, participant_mode = ?,
                        driver_ids_json = ?, include_owner = ?,
                        minimum_races = ?, ranking_mode = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (*payload, championship_id),
                )
                saved_id = championship_id
        return {"id": saved_id, "name": name}

    def delete_custom_championship(self, championship_id: int) -> dict[str, Any]:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM custom_championships WHERE id = ?",
                (championship_id,),
            )
            if not cursor.rowcount:
                raise ValueError("El campeonato seleccionado no existe")
        return {"deleted": True, "id": championship_id}

    def get_coincidence_leagues(self) -> dict[str, Any]:
        with self.connect() as connection:
            active_league_id, owner_iracing_id = self._active_league_and_owner(connection)
            active_platform = connection.execute(
                "SELECT platform FROM leagues WHERE id = ?", (active_league_id,)
            ).fetchone()["platform"]
            owner = connection.execute(
                "SELECT id, name FROM drivers WHERE iracing_id = ?",
                (owner_iracing_id,),
            ).fetchone()
            if not owner:
                return {"ownerIracingId": owner_iracing_id, "leagues": {}}
            event_rows = connection.execute(
                """
                SELECT DISTINCT event.id, league.series_name, league.season,
                                league.season_year, league.season_quarter
                FROM race_events AS event
                JOIN leagues AS league ON league.id = event.league_id
                JOIN race_results AS result ON result.event_id = event.id
                WHERE result.driver_id = ? AND league.platform = ?
                ORDER BY COALESCE(event.start_time, ''), event.id
                """,
                (owner["id"], active_platform),
            ).fetchall()
            custom_rows = connection.execute(
                """
                SELECT * FROM custom_championships
                WHERE platform = ?
                ORDER BY updated_at DESC, id DESC
                """,
                (active_platform,),
            ).fetchall()

        events = []
        for row in event_rows:
            detail = self.get_race_detail(int(row["id"]))
            start_value = detail["event"]["startTime"]
            parsed_date = None
            if start_value:
                try:
                    parsed_date = datetime.fromisoformat(
                        str(start_value).replace("Z", "+00:00")
                    )
                    if parsed_date.tzinfo is None:
                        parsed_date = parsed_date.replace(tzinfo=timezone.utc)
                except ValueError:
                    parsed_date = None
            events.append(
                {
                    "id": int(row["id"]),
                    "seriesName": row["series_name"],
                    "season": row["season"],
                    "seasonYear": row["season_year"],
                    "seasonQuarter": row["season_quarter"],
                    "date": parsed_date,
                    "detail": detail,
                }
            )
        dated_events = [event for event in events if event["date"] is not None]
        reference_date = (
            max(event["date"] for event in dated_events)
            if dated_events
            else datetime.now(timezone.utc)
        )
        month_names = (
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "septiembre",
            "octubre",
            "noviembre",
            "diciembre",
        )

        def build_league(
            scope: str,
            label: str,
            scoped_events: list[dict[str, Any]],
            period_key: str,
            participant_mode: str = "recurrent",
            selected_driver_ids: set[str] | None = None,
            include_owner: bool = True,
            ranking_mode: str = "all-races",
            minimum_races: int = 2,
        ) -> dict[str, Any]:
            appearances: dict[str, int] = {}
            identities: dict[str, dict[str, Any]] = {}
            for event in scoped_events:
                for result in event["detail"]["results"]:
                    identities[result["iracingId"]] = {
                        "iracingId": result["iracingId"],
                        "name": result["name"],
                        "initials": result["initials"],
                        "color": result["color"],
                        "isOwner": result["isOwner"],
                    }
                    if not result["isOwner"]:
                        appearances[result["iracingId"]] = (
                            appearances.get(result["iracingId"], 0) + 1
                        )
            recurrent_ids = {
                iracing_id
                for iracing_id, count in appearances.items()
                if count >= 2
            }
            if participant_mode == "selected":
                participant_ids = set(selected_driver_ids or set())
            elif participant_mode == "all":
                participant_ids = set(identities)
            else:
                participant_ids = set(recurrent_ids)
            if include_owner:
                participant_ids.add(owner_iracing_id)
            participant_ids &= set(identities)
            aggregates: dict[str, dict[str, Any]] = {}
            league_events = []
            for event in scoped_events:
                present = [
                    result
                    for result in event["detail"]["results"]
                    if result["iracingId"] in participant_ids
                    and result.get("scoringEligible", True)
                ]
                if len(present) < 2:
                    continue
                present.sort(key=lambda result: result["finishPosition"])
                owner_result = next(
                    (result for result in present if result["isOwner"]), None
                )
                league_events.append(
                    {
                        "eventId": event["id"],
                        "startTime": event["detail"]["event"]["startTime"],
                        "seriesName": event["seriesName"],
                        "season": event["season"],
                        "track": event["detail"]["event"]["track"],
                        "layout": event["detail"]["event"]["layout"],
                        "strengthOfField": event["detail"]["event"][
                            "strengthOfField"
                        ],
                        "splitNumber": event["detail"]["event"]["splitNumber"],
                        "splitTotal": event["detail"]["event"]["splitTotal"],
                        "participants": len(present),
                    }
                )
                for result in present:
                    aggregate = aggregates.setdefault(
                        result["iracingId"],
                        {
                            **identities[result["iracingId"]],
                            "races": 0,
                            "wins": 0,
                            "losses": 0,
                            "ties": 0,
                            "incidents": 0,
                            "positionsGained": 0,
                            "series": set(),
                            "raceScores": [],
                            "weeklyScores": {},
                            "ratingResults": [],
                            "raceDetails": [],
                            "ownerAhead": 0,
                            "rivalAhead": 0,
                        },
                    )
                    opponents = [
                        opponent
                        for opponent in present
                        if opponent["iracingId"] != result["iracingId"]
                    ]
                    wins = sum(
                        1
                        for opponent in opponents
                        if result["finishPosition"] < opponent["finishPosition"]
                    )
                    losses = sum(
                        1
                        for opponent in opponents
                        if result["finishPosition"] > opponent["finishPosition"]
                    )
                    ties = len(opponents) - wins - losses
                    aggregate["races"] += 1
                    aggregate["wins"] += wins
                    aggregate["losses"] += losses
                    aggregate["ties"] += ties
                    aggregate["incidents"] += result["incidents"]
                    aggregate["positionsGained"] += result["positionChange"] or 0
                    aggregate["series"].add(event["seriesName"])
                    race_score = (
                        ((wins + ties * 0.5) / len(opponents) * 100)
                        if opponents
                        else 0
                    )
                    aggregate["raceScores"].append(race_score)
                    week_key = (
                        f"{event['date'].isocalendar().year}-"
                        f"{event['date'].isocalendar().week:02d}"
                        if event["date"] is not None
                        else f"{event['season']}:{event['detail']['event']['raceWeek']}"
                    )
                    aggregate["weeklyScores"].setdefault(week_key, []).append(
                        race_score
                    )
                    aggregate["ratingResults"].append(result)
                    if not result["isOwner"] and owner_result is not None:
                        aggregate["ownerAhead"] += int(
                            owner_result["finishPosition"]
                            < result["finishPosition"]
                        )
                        aggregate["rivalAhead"] += int(
                            owner_result["finishPosition"]
                            > result["finishPosition"]
                        )
                    aggregate["raceDetails"].append(
                        {
                            "eventId": event["id"],
                            "startTime": event["detail"]["event"]["startTime"],
                            "seriesName": event["seriesName"],
                            "track": event["detail"]["event"]["track"],
                            "layout": event["detail"]["event"]["layout"],
                            "strengthOfField": event["detail"]["event"][
                                "strengthOfField"
                            ],
                            "finishPosition": result["finishPosition"],
                            "leaguePosition": present.index(result) + 1,
                            "leagueParticipants": len(present),
                            "incidents": result["incidents"],
                            "score": aggregate["raceScores"][-1],
                            "gridScore": result.get("gridScore"),
                            "performanceScore": result.get("performanceScore"),
                            "cleanlinessScore": result.get(
                                "cleanlinessScore"
                            ),
                            "scoreConfidence": result.get("scoreConfidence"),
                            "cutsPer30Minutes": result.get(
                                "cutsPer30Minutes"
                            ),
                            "incidentsPer1000Corners": result.get(
                                "incidentsPer1000Corners"
                            ),
                            "incidentsPer30Minutes": result.get(
                                "incidentsPer30Minutes"
                            ),
                            "scoreComponents": result.get("scoreComponents"),
                            "ownerPosition": (
                                owner_result["finishPosition"]
                                if owner_result is not None
                                else None
                            ),
                        }
                    )

            participants = []
            for aggregate in aggregates.values():
                rating_results = aggregate.pop("ratingResults")
                race_scores = aggregate.pop("raceScores")
                weekly_scores = aggregate.pop("weeklyScores")
                series_names = sorted(aggregate.pop("series"))
                irating_start = next(
                    (
                        result["oldIRating"]
                        for result in rating_results
                        if result.get("oldIRating") is not None
                    ),
                    None,
                )
                irating_end = next(
                    (
                        result["newIRating"]
                        for result in reversed(rating_results)
                        if result.get("newIRating") is not None
                    ),
                    None,
                )
                safety_start = next(
                    (
                        result["oldSafetyRating"]
                        for result in rating_results
                        if result.get("oldSafetyRating") is not None
                    ),
                    None,
                )
                safety_end = next(
                    (
                        result["newSafetyRating"]
                        for result in reversed(rating_results)
                        if result.get("newSafetyRating") is not None
                    ),
                    None,
                )
                duels = (
                    aggregate["wins"]
                    + aggregate["losses"]
                    + aggregate["ties"]
                )
                participants.append(
                    {
                        **aggregate,
                        "score": (
                            sum(
                                sum(scores) / len(scores)
                                for scores in weekly_scores.values()
                            )
                            / len(weekly_scores)
                            if ranking_mode == "weekly" and weekly_scores
                            else (
                                sum(race_scores) / len(race_scores)
                                if race_scores
                                else 0
                            )
                        ),
                        "duels": duels,
                        "duelWinRate": (
                            (aggregate["wins"] + aggregate["ties"] * 0.5)
                            / duels
                            * 100
                        )
                        if duels
                        else 0,
                        "averageIncidents": aggregate["incidents"]
                        / aggregate["races"],
                        "seriesCount": len(series_names),
                        "seriesNames": series_names,
                        "iratingStart": irating_start,
                        "iratingEnd": irating_end,
                        "iratingChange": (
                            irating_end - irating_start
                            if irating_start is not None
                            and irating_end is not None
                            else None
                        ),
                        "safetyRatingStart": safety_start,
                        "safetyRatingEnd": safety_end,
                        "safetyRatingChange": (
                            safety_end - safety_start
                            if safety_start is not None
                            and safety_end is not None
                            else None
                        ),
                        "gridRating": (
                            summarize_grid_scores(rating_results)
                        ),
                        "raceDetails": list(reversed(aggregate["raceDetails"])),
                    }
                )
            participants.sort(
                key=lambda participant: (
                    -participant["score"],
                    -participant["races"],
                    participant["averageIncidents"],
                    participant["name"].lower(),
                )
            )
            for position, participant in enumerate(participants, 1):
                participant["position"] = position
            sof_values = [
                event["strengthOfField"]
                for event in league_events
                if event["strengthOfField"]
            ]
            classified_results = sum(
                participant["races"] for participant in participants
            )
            total_incidents = sum(
                participant["incidents"] for participant in participants
            )
            owner_participant = next(
                (
                    participant
                    for participant in participants
                    if participant["isOwner"]
                ),
                None,
            )
            return {
                "scope": scope,
                "periodKey": period_key,
                "label": label,
                "minimumMeetings": 2,
                "minimumRaces": minimum_races,
                "rankingMode": ranking_mode,
                "summary": {
                    "races": len(league_events),
                    "participants": len(participants),
                    "recurrentRivals": len(
                        {
                            driver_id
                            for driver_id in participant_ids
                            if driver_id != owner_iracing_id
                        }
                    ),
                    "series": len(
                        {
                            event["seriesName"]
                            for event in league_events
                        }
                    ),
                    "tracks": len(
                        {
                            (event["track"], event["layout"])
                            for event in league_events
                        }
                    ),
                    "duels": sum(
                        participant["duels"] for participant in participants
                    )
                    // 2,
                    "averageSof": (
                        round(sum(sof_values) / len(sof_values))
                        if sof_values
                        else 0
                    ),
                    "averageMembers": (
                        sum(event["participants"] for event in league_events)
                        / len(league_events)
                        if league_events
                        else 0
                    ),
                    "classifiedResults": classified_results,
                    "averageIncidents": (
                        total_incidents / classified_results
                        if classified_results
                        else 0
                    ),
                    "leaderName": (
                        participants[0]["name"] if participants else None
                    ),
                    "ownerPosition": (
                        owner_participant["position"]
                        if owner_participant
                        else None
                    ),
                },
                "participants": participants,
                "events": list(reversed(league_events)),
            }

        yearly_groups: dict[int, list[dict[str, Any]]] = {}
        monthly_groups: dict[tuple[int, int], list[dict[str, Any]]] = {}
        season_groups: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for event in events:
            if event["date"] is not None:
                yearly_groups.setdefault(event["date"].year, []).append(event)
                monthly_groups.setdefault(
                    (event["date"].year, event["date"].month), []
                ).append(event)
            season_year = as_int(event.get("seasonYear"), 0)
            season_quarter = as_int(event.get("seasonQuarter"), 0)
            if not season_year or not season_quarter:
                season_match = re.search(
                    r"(\d{4}).*?Season\s+(\d+)",
                    str(event.get("season") or ""),
                    re.IGNORECASE,
                )
                if season_match:
                    season_year = int(season_match.group(1))
                    season_quarter = int(season_match.group(2))
            if season_year and season_quarter:
                season_groups.setdefault(
                    (season_year, season_quarter), []
                ).append(event)

        yearly_periods = [
            build_league("yearly", str(year), grouped, f"year:{year}")
            for year, grouped in sorted(
                yearly_groups.items(), key=lambda item: item[0], reverse=True
            )
        ]
        season_periods = [
            build_league(
                "season",
                f"{year} · Temporada {quarter}",
                grouped,
                f"season:{year}:{quarter}",
            )
            for (year, quarter), grouped in sorted(
                season_groups.items(), key=lambda item: item[0], reverse=True
            )
        ]
        monthly_periods = [
            build_league(
                "monthly",
                f"{month_names[month - 1].capitalize()} {year}",
                grouped,
                f"month:{year}:{month:02d}",
            )
            for (year, month), grouped in sorted(
                monthly_groups.items(), key=lambda item: item[0], reverse=True
            )
        ]
        monthly_periods = [
            period
            for period in monthly_periods
            if period["summary"]["races"] > 0
        ]
        eternal_period = build_league(
            "eternal", "Todo el historial", events, "eternal"
        )
        custom_championships = []
        for custom in custom_rows:
            try:
                series_names = {
                    str(value)
                    for value in json.loads(custom["series_names_json"] or "[]")
                }
                driver_ids = {
                    str(value)
                    for value in json.loads(custom["driver_ids_json"] or "[]")
                }
            except (TypeError, json.JSONDecodeError):
                series_names, driver_ids = set(), set()
            start_date = str(custom["start_date"] or "")
            end_date = str(custom["end_date"] or "")
            scoped_events = [
                event
                for event in events
                if (not series_names or event["seriesName"] in series_names)
                and (
                    not start_date
                    or (
                        event["date"] is not None
                        and event["date"].date().isoformat() >= start_date
                    )
                )
                and (
                    not end_date
                    or (
                        event["date"] is not None
                        and event["date"].date().isoformat() <= end_date
                    )
                )
            ]
            championship_id = int(custom["id"])
            config = {
                "id": championship_id,
                "name": custom["name"],
                "seriesNames": sorted(series_names),
                "startDate": start_date,
                "endDate": end_date,
                "participantMode": custom["participant_mode"],
                "driverIds": sorted(driver_ids),
                "includeOwner": bool(custom["include_owner"]),
                "minimumRaces": int(custom["minimum_races"]),
                "rankingMode": custom["ranking_mode"],
            }
            custom_championships.append(
                {
                    **config,
                    "league": build_league(
                        "custom",
                        custom["name"],
                        scoped_events,
                        f"custom:{championship_id}",
                        participant_mode=custom["participant_mode"],
                        selected_driver_ids=driver_ids,
                        include_owner=bool(custom["include_owner"]),
                        ranking_mode=custom["ranking_mode"],
                        minimum_races=int(custom["minimum_races"]),
                    ),
                }
            )
        option_drivers: dict[str, dict[str, Any]] = {}
        for event in events:
            for result in event["detail"]["results"]:
                option_drivers[str(result["iracingId"])] = {
                    "iracingId": str(result["iracingId"]),
                    "name": result["name"],
                    "initials": result["initials"],
                    "color": result["color"],
                    "isOwner": result["isOwner"],
                }
        return {
            "ownerIracingId": owner_iracing_id,
            "referenceDate": reference_date.isoformat(),
            "leagues": {
                "monthly": monthly_periods[0] if monthly_periods else None,
                "season": season_periods[0] if season_periods else None,
                "yearly": yearly_periods[0] if yearly_periods else None,
                "eternal": eternal_period,
            },
            "periods": {
                "monthly": monthly_periods,
                "season": season_periods,
                "yearly": yearly_periods,
                "eternal": [eternal_period],
            },
            "customChampionships": custom_championships,
            "options": {
                "series": sorted(
                    {event["seriesName"] for event in events},
                    key=str.casefold,
                ),
                "drivers": sorted(
                    option_drivers.values(),
                    key=lambda driver: (
                        not driver["isOwner"],
                        str(driver["name"]).casefold(),
                    ),
                ),
            },
        }

    def get_global_overview(self) -> dict[str, Any]:
        with self.connect() as connection:
            active = connection.execute(
                "SELECT platform FROM leagues WHERE active = 1 ORDER BY id LIMIT 1"
            ).fetchone()
            platform = str(active["platform"] if active else "iracing")
            owner_key = {
                "assetto-corsa": "owner_assetto_corsa_id",
                "raceroom": "owner_raceroom_id",
            }.get(platform, "owner_iracing_id")
            owner_row = connection.execute(
                "SELECT value FROM settings WHERE key = ?", (owner_key,)
            ).fetchone()
            owner_iracing_id = str(
                owner_row["value"]
                if owner_row
                else ""
            )
            rows = connection.execute(
                """
                SELECT l.*,
                       (SELECT COUNT(*) FROM race_events re WHERE re.league_id = l.id) AS race_count,
                       (SELECT COUNT(DISTINCT re.track) FROM race_events re WHERE re.league_id = l.id) AS track_count,
                       (SELECT COUNT(DISTINCT rr.driver_id)
                          FROM race_results rr JOIN race_events re ON re.id = rr.event_id
                         WHERE re.league_id = l.id) AS driver_count,
                       (SELECT AVG(re.strength_of_field) FROM race_events re WHERE re.league_id = l.id) AS average_sof,
                       (SELECT SUM(rr.incidents)
                          FROM race_results rr JOIN race_events re ON re.id = rr.event_id
                         WHERE re.league_id = l.id) AS total_incidents,
                       (SELECT AVG(rr.incidents)
                          FROM race_results rr JOIN race_events re ON re.id = rr.event_id
                         WHERE re.league_id = l.id) AS average_incidents,
                       (SELECT MAX(re.start_time) FROM race_events re WHERE re.league_id = l.id) AS last_race_time,
                       (SELECT COUNT(*)
                          FROM race_results rr
                          JOIN race_events re ON re.id = rr.event_id
                          JOIN drivers d ON d.id = rr.driver_id
                         WHERE re.league_id = l.id AND d.iracing_id = ?) AS owner_races,
                       (SELECT AVG(rr.finish_position)
                          FROM race_results rr
                          JOIN race_events re ON re.id = rr.event_id
                          JOIN drivers d ON d.id = rr.driver_id
                         WHERE re.league_id = l.id AND d.iracing_id = ?) AS owner_average_finish,
                       (SELECT MIN(rr.finish_position)
                          FROM race_results rr
                          JOIN race_events re ON re.id = rr.event_id
                          JOIN drivers d ON d.id = rr.driver_id
                         WHERE re.league_id = l.id AND d.iracing_id = ?) AS owner_best_finish,
                       (SELECT SUM(CASE WHEN rr.finish_position = 1 THEN 1 ELSE 0 END)
                          FROM race_results rr
                          JOIN race_events re ON re.id = rr.event_id
                          JOIN drivers d ON d.id = rr.driver_id
                         WHERE re.league_id = l.id AND d.iracing_id = ?) AS owner_wins,
                       (SELECT SUM(COALESCE(rr.irating_change, 0))
                          FROM race_results rr
                          JOIN race_events re ON re.id = rr.event_id
                          JOIN drivers d ON d.id = rr.driver_id
                         WHERE re.league_id = l.id AND d.iracing_id = ?) AS owner_irating_change
                FROM leagues l
                WHERE l.platform = ?
                ORDER BY l.season_year DESC, l.season_quarter DESC, last_race_time DESC, l.id DESC
                """,
                (owner_iracing_id,) * 5 + (platform,),
            ).fetchall()
            totals = connection.execute(
                """
                WITH platform_events AS (
                    SELECT event.*
                    FROM race_events event
                    JOIN leagues league ON league.id = event.league_id
                    WHERE league.platform = ?
                )
                SELECT (SELECT COUNT(DISTINCT league_id) FROM platform_events) AS seasons,
                       (SELECT COUNT(*) FROM platform_events) AS races,
                       (SELECT COUNT(DISTINCT result.driver_id)
                          FROM race_results result
                          JOIN platform_events event ON event.id = result.event_id) AS drivers,
                       (SELECT COUNT(DISTINCT track) FROM platform_events) AS tracks,
                       (SELECT AVG(NULLIF(strength_of_field, 0)) FROM platform_events) AS average_sof,
                       (SELECT SUM(result.incidents)
                          FROM race_results result
                          JOIN platform_events event ON event.id = result.event_id) AS total_incidents,
                       (SELECT AVG(result.incidents)
                          FROM race_results result
                          JOIN platform_events event ON event.id = result.event_id) AS average_incidents
                """,
                (platform,),
            ).fetchone()
            recent_rows = connection.execute(
                """
                SELECT re.id, re.league_id, re.start_time, re.track, re.layout,
                       re.race_week, re.strength_of_field, re.split_number,
                       re.split_total, l.series_name, l.season,
                       owner_result.finish_position, owner_result.incidents
                FROM race_events re
                JOIN leagues l ON l.id = re.league_id
                LEFT JOIN drivers owner ON owner.iracing_id = ?
                LEFT JOIN race_results owner_result
                  ON owner_result.event_id = re.id AND owner_result.driver_id = owner.id
                WHERE l.platform = ?
                ORDER BY COALESCE(re.start_time, '') DESC, re.id DESC
                LIMIT 10
                """,
                (owner_iracing_id, platform),
            ).fetchall()

        seasons = [row for row in rows if row["race_count"]]
        current_id = (
            max(
                seasons,
                key=lambda row: (
                    row["season_year"] or 0,
                    row["season_quarter"] or 0,
                    row["last_race_time"] or "",
                    row["id"],
                ),
            )["id"]
            if seasons
            else None
        )
        return {
            "ownerIracingId": owner_iracing_id,
            "totals": {
                "seasons": totals["seasons"] or 0,
                "races": totals["races"] or 0,
                "drivers": totals["drivers"] or 0,
                "tracks": totals["tracks"] or 0,
                "averageSof": round(totals["average_sof"] or 0),
                "totalIncidents": totals["total_incidents"] or 0,
                "averageIncidents": totals["average_incidents"] or 0,
            },
            "seasons": [
                {
                    "id": row["id"],
                    "seriesName": row["series_name"],
                    "season": row["season"],
                    "car": row["car"],
                    "setupType": row["setup_type"],
                    "seasonYear": row["season_year"],
                    "seasonQuarter": row["season_quarter"],
                    "weeksCompleted": row["weeks_completed"],
                    "totalWeeks": row["total_weeks"],
                    "raceCount": row["race_count"],
                    "driverCount": row["driver_count"],
                    "trackCount": row["track_count"],
                    "averageSof": round(row["average_sof"] or 0),
                    "totalIncidents": row["total_incidents"] or 0,
                    "averageIncidents": row["average_incidents"] or 0,
                    "lastRaceTime": row["last_race_time"],
                    "ownerRaces": row["owner_races"] or 0,
                    "ownerAverageFinish": row["owner_average_finish"],
                    "ownerBestFinish": row["owner_best_finish"],
                    "ownerWins": row["owner_wins"] or 0,
                    "ownerIRatingChange": row["owner_irating_change"] or 0,
                    "selected": bool(row["active"]),
                    "isCurrent": row["id"] == current_id,
                }
                for row in seasons
            ],
            "recentRaces": [
                {
                    "id": row["id"],
                    "leagueId": row["league_id"],
                    "seriesName": row["series_name"],
                    "season": row["season"],
                    "startTime": row["start_time"],
                    "track": row["track"],
                    "layout": row["layout"],
                    "week": row["race_week"],
                    "strengthOfField": row["strength_of_field"],
                    "splitNumber": row["split_number"],
                    "splitTotal": row["split_total"],
                    "ownerFinishPosition": row["finish_position"],
                    "ownerIncidents": row["incidents"],
                }
                for row in recent_rows
            ],
        }

    def update_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        ranking_mode = str(values.get("rankingMode", "weekly"))
        tiebreaker = str(values.get("tiebreaker", "incidents"))
        owner_identity = str(
            values.get("ownerIdentity", values.get("ownerIracingId", ""))
        ).strip()
        owner_aliases = normalize_assetto_owner_aliases(
            owner_identity, values.get("ownerAliases")
        )
        try:
            minimum = int(values.get("minimumParticipation", 50))
        except (TypeError, ValueError) as error:
            raise ValueError("La participación mínima no es válida") from error

        if ranking_mode not in {"weekly", "races"}:
            raise ValueError("El modo de clasificación no es válido")
        if tiebreaker not in {"incidents", "participation", "wins"}:
            raise ValueError("El desempate no es válido")
        if not 1 <= minimum <= 100:
            raise ValueError("La participación mínima debe estar entre 1 y 100")
        with self.connect() as connection:
            active = connection.execute(
                "SELECT platform FROM leagues WHERE active = 1 ORDER BY id LIMIT 1"
            ).fetchone()
            platform = str(active["platform"] if active else "iracing")
            if not owner_identity:
                owner_key = {
                    "assetto-corsa": "owner_assetto_corsa_name",
                    "raceroom": "owner_raceroom_name",
                }.get(platform, "owner_iracing_id")
                current_owner = connection.execute(
                    "SELECT value FROM settings WHERE key = ?",
                    (owner_key,),
                ).fetchone()
                owner_identity = str(
                    current_owner["value"] if current_owner else ""
                ).strip()
                if platform == "assetto-corsa":
                    aliases_row = connection.execute(
                        """
                        SELECT value FROM settings
                        WHERE key = 'owner_assetto_corsa_aliases'
                        """
                    ).fetchone()
                    try:
                        saved_aliases = json.loads(
                            aliases_row["value"] if aliases_row else "[]"
                        )
                    except (TypeError, json.JSONDecodeError):
                        saved_aliases = []
                    owner_aliases = normalize_assetto_owner_aliases(
                        owner_identity, saved_aliases
                    )
            if platform == "assetto-corsa":
                if not owner_aliases:
                    raise ValueError(
                        "Indica el nombre con el que apareces en Assetto Corsa"
                    )
                owner_identity = owner_aliases[0]
                owner_values = (
                    ("owner_assetto_corsa_name", owner_identity),
                    ("owner_assetto_corsa_id", assetto_driver_id(owner_identity)),
                    (
                        "owner_assetto_corsa_aliases",
                        json.dumps(owner_aliases, ensure_ascii=False),
                    ),
                )
                owner_driver_id = assetto_driver_id(owner_identity)
            elif platform == "raceroom":
                owner_id_row = connection.execute(
                    "SELECT value FROM settings WHERE key = 'owner_raceroom_id'"
                ).fetchone()
                owner_driver_id = str(owner_id_row["value"] if owner_id_row else "")
                if not owner_driver_id:
                    raise ValueError("Configura primero tu perfil de RaceRoom")
                owner_values = (("owner_raceroom_name", owner_identity),)
            else:
                if not owner_identity.isdigit() or not 3 <= len(owner_identity) <= 12:
                    raise ValueError("El ID del piloto de referencia no es válido")
                owner_values = (("owner_iracing_id", owner_identity),)
                owner_driver_id = owner_identity
            for key, value in (
                ("ranking_mode", ranking_mode),
                ("minimum_participation", str(minimum)),
                ("tiebreaker", tiebreaker),
                *owner_values,
            ):
                connection.execute(
                    """
                    INSERT INTO settings (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (key, value),
                )
            if platform == "assetto-corsa":
                owner_driver_id = self._merge_assetto_owner_aliases(
                    connection, owner_aliases
                )
                connection.execute(
                    """
                    UPDATE settings SET value = ?
                    WHERE key = 'owner_assetto_corsa_id'
                    """,
                    (owner_driver_id,),
                )
        return {
            "rankingMode": ranking_mode,
            "minimumParticipation": minimum,
            "tiebreaker": tiebreaker,
            "ownerIracingId": owner_driver_id,
            "ownerDriverId": owner_driver_id,
            "ownerDisplayName": owner_identity,
            "ownerAliases": owner_aliases if platform == "assetto-corsa" else [],
            "platform": platform,
        }

    def save_oauth_client_id(self, client_id: str) -> dict[str, Any]:
        normalized = client_id.strip()
        if not 3 <= len(normalized) <= 200 or any(character.isspace() for character in normalized):
            raise ValueError("El client ID de iRacing no es válido")
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO settings (key, value) VALUES ('oauth_client_id', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (normalized,),
            )
        return self.get_oauth_status()

    def get_oauth_client_id(self) -> str:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = 'oauth_client_id'"
            ).fetchone()
        return row["value"] if row else ""

    def get_oauth_status(self) -> dict[str, Any]:
        client_id = self.get_oauth_client_id()
        with self.connect() as connection:
            token = connection.execute(
                """
                SELECT access_expires_at, refresh_expires_at, scope,
                       profile_name, profile_cust_id, updated_at
                FROM oauth_tokens WHERE id = 1
                """
            ).fetchone()
        if not token:
            return {
                "configured": bool(client_id),
                "clientId": client_id,
                "connected": False,
                "profileName": None,
                "profileCustId": None,
                "scope": "",
                "accessExpiresAt": None,
                "refreshExpiresAt": None,
            }
        return {
            "configured": bool(client_id),
            "clientId": client_id,
            "connected": True,
            "profileName": token["profile_name"],
            "profileCustId": token["profile_cust_id"],
            "scope": token["scope"],
            "accessExpiresAt": token["access_expires_at"],
            "refreshExpiresAt": token["refresh_expires_at"],
        }

    def create_oauth_session(
        self, state: str, code_verifier: str, redirect_uri: str
    ) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(
            timespec="seconds"
        )
        with self.connect() as connection:
            connection.execute("DELETE FROM oauth_sessions WHERE created_at < ?", (cutoff,))
            connection.execute(
                """
                INSERT INTO oauth_sessions (state, code_verifier, redirect_uri, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (state, code_verifier, redirect_uri, utc_now()),
            )

    def consume_oauth_session(self, state: str) -> dict[str, str]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM oauth_sessions WHERE state = ?", (state,)
            ).fetchone()
            connection.execute("DELETE FROM oauth_sessions WHERE state = ?", (state,))
        if not row:
            raise ValueError("La sesión OAuth no existe o ya fue utilizada")
        created_at = datetime.fromisoformat(row["created_at"])
        if datetime.now(timezone.utc) - created_at > timedelta(minutes=10):
            raise ValueError("La sesión OAuth ha caducado")
        return {
            "codeVerifier": row["code_verifier"],
            "redirectUri": row["redirect_uri"],
        }

    def _token_protector(self) -> Any:
        if self.protector is None:
            self.protector = WindowsDataProtector()
        return self.protector

    def save_oauth_tokens(
        self,
        token_payload: dict[str, Any],
        profile: dict[str, Any] | None = None,
    ) -> None:
        access_token = str(token_payload.get("access_token", ""))
        if not access_token:
            raise ValueError("iRacing no ha devuelto un access token")
        refresh_token = str(token_payload.get("refresh_token", ""))
        now = datetime.now(timezone.utc)
        access_expires = now + timedelta(seconds=int(token_payload.get("expires_in", 0)))
        refresh_expires = (
            now + timedelta(seconds=int(token_payload["refresh_token_expires_in"]))
            if token_payload.get("refresh_token_expires_in")
            else None
        )
        protector = self._token_protector()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO oauth_tokens
                    (id, access_token, refresh_token, access_expires_at,
                     refresh_expires_at, scope, profile_name, profile_cust_id, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    access_token = excluded.access_token,
                    refresh_token = COALESCE(excluded.refresh_token, oauth_tokens.refresh_token),
                    access_expires_at = excluded.access_expires_at,
                    refresh_expires_at = COALESCE(excluded.refresh_expires_at, oauth_tokens.refresh_expires_at),
                    scope = excluded.scope,
                    profile_name = COALESCE(excluded.profile_name, oauth_tokens.profile_name),
                    profile_cust_id = COALESCE(excluded.profile_cust_id, oauth_tokens.profile_cust_id),
                    updated_at = excluded.updated_at
                """,
                (
                    protector.protect(access_token),
                    protector.protect(refresh_token) if refresh_token else None,
                    access_expires.isoformat(timespec="seconds"),
                    refresh_expires.isoformat(timespec="seconds")
                    if refresh_expires
                    else None,
                    str(token_payload.get("scope", "")),
                    profile.get("iracing_name") if profile else None,
                    profile.get("iracing_cust_id") if profile else None,
                    utc_now(),
                ),
            )

    def get_oauth_tokens(self) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM oauth_tokens WHERE id = 1"
            ).fetchone()
        if not row:
            return None
        protector = self._token_protector()
        return {
            "accessToken": protector.unprotect(row["access_token"]),
            "refreshToken": protector.unprotect(row["refresh_token"])
            if row["refresh_token"]
            else None,
            "accessExpiresAt": row["access_expires_at"],
            "refreshExpiresAt": row["refresh_expires_at"],
            "scope": row["scope"],
            "profileName": row["profile_name"],
            "profileCustId": row["profile_cust_id"],
        }

    def disconnect_oauth(self) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM oauth_tokens")
            connection.execute("DELETE FROM oauth_sessions")

    def archive_current_season(self) -> dict[str, Any]:
        state = self.get_state()
        league = state["league"]
        created_at = utc_now()
        snapshot = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO archives (league_id, season, created_at, snapshot_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(league_id, season)
                DO UPDATE SET created_at = excluded.created_at, snapshot_json = excluded.snapshot_json
                """,
                (league["id"], league["season"], created_at, snapshot),
            )
        return {"season": league["season"], "createdAt": created_at}

    def create_backup(self, backup_directory: Path = BACKUP_DIR) -> dict[str, Any]:
        backup_directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = backup_directory / f"gridscope-{timestamp}.db"
        counter = 2
        while backup_path.exists():
            backup_path = backup_directory / f"gridscope-{timestamp}-{counter}.db"
            counter += 1

        with self.connect() as source:
            destination = sqlite3.connect(backup_path)
            try:
                source.backup(destination)
            finally:
                destination.close()

        created_at = utc_now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO backups (filename, created_at) VALUES (?, ?)",
                (backup_path.name, created_at),
            )
        return {"filename": backup_path.name, "createdAt": created_at}

    def standings_csv(self) -> bytes:
        state = self.get_state()
        weeks_completed = state["league"]["weeksCompleted"]
        minimum = state["settings"]["minimumParticipation"]
        required_weeks = max(1, -(-weeks_completed * minimum // 100))
        drivers = sorted(
            state["drivers"],
            key=lambda driver: (
                driver["weeks"] < required_weeks,
                driver["weekly"] if driver["weeks"] else float("inf"),
                driver["incidents"],
            ),
        )

        stream = io.StringIO(newline="")
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(
            [
                "Posición",
                "Piloto",
                "iRacing ID",
                "Media semanal",
                "Media carrera",
                "Incidentes",
                "Semanas",
                "Carreras",
                "Victorias",
                "SoF medio",
                "Estado",
            ]
        )
        official_position = 0
        for driver in drivers:
            eligible = driver["weeks"] >= required_weeks
            if eligible:
                official_position += 1
            writer.writerow(
                [
                    official_position if eligible else "",
                    driver["name"],
                    driver["id"],
                    f'{driver["weekly"]:.2f}'.replace(".", ","),
                    f'{driver["races"]:.2f}'.replace(".", ","),
                    f'{driver["incidents"]:.2f}'.replace(".", ","),
                    driver["weeks"],
                    driver["racesCount"],
                    driver["wins"],
                    driver["sof"],
                    "Oficial" if eligible else "Provisional",
                ]
            )
        return ("\ufeff" + stream.getvalue()).encode("utf-8")


def create_oauth_authorization(
    store: DataStore, redirect_uri: str
) -> dict[str, str]:
    client_id = store.get_oauth_client_id()
    if not client_id:
        raise ValueError("Primero debes guardar un client ID de iRacing")
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode("ascii")).digest()
        )
        .rstrip(b"=")
        .decode("ascii")
    )
    store.create_oauth_session(state, code_verifier, redirect_uri)
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
            "scope": "iracing.auth iracing.profile",
        }
    )
    return {
        "authorizationUrl": f"{OAUTH_AUTHORIZE_URL}?{query}",
        "redirectUri": redirect_uri,
    }


def request_json(request: Request) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        try:
            details = json.loads(error.read().decode("utf-8"))
            message = (
                details.get("error_description")
                or details.get("error")
                or f"iRacing ha respondido con el error {error.code}"
            )
        except (UnicodeDecodeError, json.JSONDecodeError):
            message = f"iRacing ha respondido con el error {error.code}"
        raise ValueError(message) from error
    except URLError as error:
        raise ValueError("No se ha podido contactar con iRacing") from error
    except json.JSONDecodeError as error:
        raise ValueError("iRacing ha devuelto una respuesta no válida") from error
    if not isinstance(payload, dict):
        raise ValueError("iRacing ha devuelto una respuesta inesperada")
    return payload


def exchange_oauth_code(
    client_id: str,
    code: str,
    code_verifier: str,
    redirect_uri: str,
) -> dict[str, Any]:
    content = urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        }
    ).encode("utf-8")
    request = Request(
        OAUTH_TOKEN_URL,
        data=content,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": f"GridScope/{APP_VERSION}",
        },
    )
    return request_json(request)


def fetch_iracing_profile(access_token: str) -> dict[str, Any]:
    request = Request(
        OAUTH_PROFILE_URL,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "User-Agent": f"GridScope/{APP_VERSION}",
        },
    )
    return request_json(request)


def get_valid_access_token(store: DataStore) -> str:
    tokens = store.get_oauth_tokens()
    if not tokens:
        raise ValueError("La cuenta de iRacing no está conectada")
    access_expires = datetime.fromisoformat(tokens["accessExpiresAt"])
    if access_expires > datetime.now(timezone.utc) + timedelta(seconds=30):
        return str(tokens["accessToken"])
    refresh_token = tokens.get("refreshToken")
    if not refresh_token:
        raise ValueError("La autorización ha caducado; vuelve a conectar iRacing")
    refresh_expires_at = tokens.get("refreshExpiresAt")
    if refresh_expires_at and datetime.fromisoformat(refresh_expires_at) <= datetime.now(
        timezone.utc
    ):
        raise ValueError("La autorización ha caducado; vuelve a conectar iRacing")

    content = urlencode(
        {
            "grant_type": "refresh_token",
            "client_id": store.get_oauth_client_id(),
            "refresh_token": refresh_token,
        }
    ).encode("utf-8")
    request = Request(
        OAUTH_TOKEN_URL,
        data=content,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": f"GridScope/{APP_VERSION}",
        },
    )
    refreshed = request_json(request)
    store.save_oauth_tokens(refreshed)
    return str(refreshed["access_token"])


@dataclass
class ApiError(Exception):
    status: int
    message: str


class ApexRequestHandler(SimpleHTTPRequestHandler):
    server_version = f"GridScope/{APP_VERSION}"

    def __init__(self, *args: Any, store: DataStore, **kwargs: Any) -> None:
        self.store = store
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        try:
            if path == "/api/health":
                self.send_json(
                    {
                        "status": "ok",
                        "database": self.store.db_path.name,
                        "version": APP_VERSION,
                    }
                )
                return
            if path == "/api/state":
                self.send_json(self.store.get_state())
                return
            if path == "/api/bootstrap":
                self.send_json(self.store.get_bootstrap())
                return
            if path == "/api/assets/track":
                query = parse_qs(parsed_url.query)
                track_name = query.get("name", [""])[0].strip()
                layout = query.get("layout", [""])[0].strip()
                platform = query.get("platform", ["iracing"])[0].strip().lower()
                if (
                    not track_name
                    or len(track_name) > 180
                    or len(layout) > 180
                    or platform not in {"iracing", "assetto-corsa", "raceroom"}
                ):
                    raise ValueError("El circuito indicado no es válido")
                content, content_type, image_source = resolve_track_image(
                    track_name,
                    platform,
                    layout,
                    self.store.get_assetto_corsa_installation()
                    if platform == "assetto-corsa"
                    else None,
                )
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("X-Apex-Image-Source", image_source)
                self.end_headers()
                self.wfile.write(content)
                return
            if path == "/api/assets/series":
                query = parse_qs(parsed_url.query)
                logo = query.get("logo", [""])[0].strip()
                platform = query.get("platform", ["iracing"])[0].strip().lower()
                if platform not in {"iracing", "assetto-corsa", "raceroom"}:
                    platform = "iracing"
                fallback_name = (
                    "Serie de Assetto Corsa"
                    if platform == "assetto-corsa"
                    else "Serie de RaceRoom"
                    if platform == "raceroom"
                    else "Serie iRacing"
                )
                series_name = query.get("name", [fallback_name])[0].strip()
                if len(logo) > 180 or len(series_name) > 180:
                    raise ValueError("La serie indicada no es válida")
                content, content_type, image_source = resolve_series_logo(
                    logo, series_name or fallback_name, platform
                )
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("X-Apex-Image-Source", image_source)
                self.end_headers()
                self.wfile.write(content)
                return
            if path == "/api/assets/track-map":
                query = parse_qs(parsed_url.query)
                track_id = as_int(query.get("id", ["0"])[0], 0)
                track_name = query.get("name", ["Circuito iRacing"])[0].strip()
                layout = query.get("layout", [""])[0].strip()
                platform = query.get("platform", ["iracing"])[0].strip().lower()
                if (
                    track_id < 0
                    or len(track_name) > 180
                    or len(layout) > 180
                    or platform not in {"iracing", "assetto-corsa", "raceroom"}
                ):
                    raise ValueError("El trazado indicado no es válido")
                content, content_type, image_source = resolve_track_map(
                    track_id,
                    track_name or "Circuito iRacing",
                    platform,
                    layout,
                    self.store.get_assetto_corsa_installation()
                    if platform == "assetto-corsa"
                    else None,
                )
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("X-Apex-Image-Source", image_source)
                self.end_headers()
                self.wfile.write(content)
                return
            if path.startswith("/api/drivers/"):
                iracing_id = unquote(path.rsplit("/", 1)[-1]).strip()
                if not iracing_id or len(iracing_id) > 100:
                    raise ValueError("El piloto seleccionado no es válido")
                scope = parse_qs(parsed_url.query).get("scope", ["active"])[0]
                self.send_json(self.store.get_driver_detail(iracing_id, scope))
                return
            if path == "/api/races":
                self.send_json(self.store.get_races())
                return
            if path.startswith("/api/sessions/"):
                try:
                    week = int(path.rsplit("/", 1)[-1])
                except ValueError as error:
                    raise ValueError("La sesión seleccionada no es válida") from error
                self.send_json(self.store.get_session_detail(week))
                return
            if path.startswith("/api/races/"):
                try:
                    event_id = int(path.rsplit("/", 1)[-1])
                except ValueError as error:
                    raise ValueError("La carrera seleccionada no es válida") from error
                self.send_json(self.store.get_race_detail(event_id))
                return
            if path == "/api/rivals":
                self.send_json(self.store.get_rival_comparisons())
                return
            if path == "/api/mini-leagues":
                self.send_json(self.store.get_coincidence_leagues())
                return
            if path == "/api/telemetry":
                self.send_json(self.store.get_telemetry_overview())
                return
            if path == "/api/overview/global":
                self.send_json(self.store.get_global_overview())
                return
            if path == "/api/oauth/start":
                port = self.server.server_address[1]
                redirect_uri = f"http://127.0.0.1:{port}/oauth/callback"
                self.send_json(create_oauth_authorization(self.store, redirect_uri))
                return
            if path == "/oauth/callback":
                try:
                    self.handle_oauth_callback(parse_qs(parsed_url.query))
                except Exception as error:
                    self.send_redirect(
                        f"/?{urlencode({'oauth': 'error', 'message': str(error)})}"
                    )
                return
            if path == "/api/export/standings.csv":
                content = self.store.standings_csv()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header(
                    "Content-Disposition",
                    'attachment; filename="clasificacion-porsche-cup-2026-s3.csv"',
                )
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            super().do_GET()
        except Exception as error:
            self.handle_error(error)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/drivers":
                payload = self.read_json()
                result = self.store.add_driver(str(payload.get("iracingId", "")))
                self.send_json(result, HTTPStatus.CREATED)
                return
            if path == "/api/archive":
                self.send_json(self.store.archive_current_season(), HTTPStatus.CREATED)
                return
            if path == "/api/backup":
                self.send_json(self.store.create_backup(), HTTPStatus.CREATED)
                return
            if path == "/api/championships":
                self.send_json(
                    self.store.save_custom_championship(self.read_json()),
                    HTTPStatus.CREATED,
                )
                return
            if path == "/api/oauth/disconnect":
                self.store.disconnect_oauth()
                self.send_json({"connected": False})
                return
            if path == "/api/import/iracing/preview":
                payload = self.read_json(max_length=15_000_000)
                normalized = normalize_iracing_export(payload.get("content"))
                self.send_json(
                    {
                        "event": {
                            key: value
                            for key, value in normalized.items()
                            if key != "results"
                        },
                        "drivers": [
                            {
                                "customerId": result["customerId"],
                                "name": result["name"],
                                "finishPosition": result["finishPosition"],
                                "incidents": result["incidents"],
                            }
                            for result in normalized["results"]
                        ],
                    }
                )
                return
            if path == "/api/import/iracing":
                payload = self.read_json(max_length=15_000_000)
                result = self.store.import_iracing_result(
                    str(payload.get("filename", "resultado.json")),
                    payload.get("content"),
                    bool(payload.get("includeAllDrivers", True)),
                    bool(payload.get("replaceDemo", True)),
                )
                self.send_json(result, HTTPStatus.CREATED)
                return
            if path == "/api/import/folder/scan":
                self.send_json(self.store.scan_import_folder())
                return
            if path == "/api/assetto-corsa/folder/scan":
                self.send_json(self.store.scan_assetto_corsa_folder())
                return
            if path == "/api/raceroom/sync":
                payload = self.read_json()
                self.send_json(
                    self.store.sync_raceroom_history(
                        as_int(payload.get("maximumNew"), 25)
                    )
                )
                return
            if path == "/api/telemetry/folder/scan":
                self.send_json(self.store.scan_telemetry_folder())
                return
            raise ApiError(HTTPStatus.NOT_FOUND, "Ruta no encontrada")
        except Exception as error:
            self.handle_error(error)

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/settings":
                self.send_json(self.store.update_settings(self.read_json()))
                return
            if path == "/api/simulators/active":
                payload = self.read_json()
                self.send_json(
                    self.store.select_simulator(str(payload.get("simulator", "")))
                )
                return
            if path == "/api/simulators/config":
                self.send_json(self.store.save_simulator_config(self.read_json()))
                return
            if path == "/api/oauth/config":
                payload = self.read_json()
                self.send_json(
                    self.store.save_oauth_client_id(str(payload.get("clientId", "")))
                )
                return
            if path == "/api/import/folder":
                payload = self.read_json()
                self.send_json(
                    self.store.save_import_folder(
                        str(payload.get("folder", "")),
                        bool(payload.get("autoScan", False)),
                    )
                )
                return
            if path == "/api/telemetry/folder":
                payload = self.read_json()
                self.send_json(
                    self.store.save_telemetry_folder(
                        str(payload.get("folder", "")),
                        bool(payload.get("autoScan", False)),
                    )
                )
                return
            if path == "/api/leagues/active":
                payload = self.read_json()
                try:
                    league_id = int(payload.get("leagueId", 0))
                except (TypeError, ValueError) as error:
                    raise ValueError("La serie seleccionada no es válida") from error
                self.send_json(self.store.set_active_league(league_id))
                return
            if path.startswith("/api/championships/"):
                try:
                    championship_id = int(path.rsplit("/", 1)[-1])
                except ValueError as error:
                    raise ValueError("El campeonato seleccionado no es válido") from error
                self.send_json(
                    self.store.save_custom_championship(
                        self.read_json(), championship_id
                    )
                )
                return
            raise ApiError(HTTPStatus.NOT_FOUND, "Ruta no encontrada")
        except Exception as error:
            self.handle_error(error)

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        try:
            if path.startswith("/api/championships/"):
                try:
                    championship_id = int(path.rsplit("/", 1)[-1])
                except ValueError as error:
                    raise ValueError("El campeonato seleccionado no es válido") from error
                self.send_json(
                    self.store.delete_custom_championship(championship_id)
                )
                return
            raise ApiError(HTTPStatus.NOT_FOUND, "Ruta no encontrada")
        except Exception as error:
            self.handle_error(error)

    def read_json(self, max_length: int = 1_000_000) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Longitud de petición no válida") from error
        if length <= 0 or length > max_length:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Petición vacía o demasiado grande")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ApiError(HTTPStatus.BAD_REQUEST, "JSON no válido") from error
        if not isinstance(payload, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "El contenido debe ser un objeto JSON")
        return payload

    def send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def handle_oauth_callback(self, query: dict[str, list[str]]) -> None:
        provider_error = query.get("error", [None])[0]
        if provider_error:
            message = query.get("error_description", [provider_error])[0]
            self.send_redirect(f"/?{urlencode({'oauth': 'error', 'message': message})}")
            return
        code = query.get("code", [""])[0]
        state = query.get("state", [""])[0]
        if not code or not state:
            raise ValueError("La respuesta OAuth no contiene el código y estado requeridos")

        session = self.store.consume_oauth_session(state)
        token_payload = exchange_oauth_code(
            self.store.get_oauth_client_id(),
            code,
            session["codeVerifier"],
            session["redirectUri"],
        )
        profile = None
        try:
            profile = fetch_iracing_profile(str(token_payload["access_token"]))
        except ValueError:
            profile = None
        self.store.save_oauth_tokens(token_payload, profile)
        self.send_redirect("/?oauth=success")

    def handle_error(self, error: Exception) -> None:
        if isinstance(error, ApiError):
            status, message = error.status, error.message
        elif isinstance(error, ValueError):
            status, message = HTTPStatus.BAD_REQUEST, str(error)
        else:
            status, message = HTTPStatus.INTERNAL_SERVER_ERROR, "Error interno de la aplicación"
            self.log_error("%s", error)
        self.send_json({"error": message}, status)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[GridScope] {self.address_string()} - {format % args}")


def build_server(host: str, port: int, store: DataStore) -> ThreadingHTTPServer:
    handler = partial(ApexRequestHandler, store=store)
    return ThreadingHTTPServer((host, port), handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor local de GridScope")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument(
        "--no-open-browser",
        action="store_true",
        help="No abre el navegador automaticamente, incluso desde el ejecutable.",
    )
    arguments = parser.parse_args()

    store = DataStore(arguments.db)
    server = build_server(arguments.host, arguments.port, store)
    application_url = f"http://{arguments.host}:{arguments.port}"
    print(f"GridScope disponible en {application_url}")
    print("Manten esta ventana abierta. Pulsa Ctrl+C para detener la aplicacion.")
    if not arguments.no_open_browser and (arguments.open_browser or getattr(sys, "frozen", False)):
        webbrowser.open(application_url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
