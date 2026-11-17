#!/usr/bin/env python3
"""Modern living-room smart-home dashboard for USB serial sensor frames."""

from __future__ import annotations

import argparse
import calendar
import io
import json
import math
import re
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pygame
import serial
from PIL import Image, ImageFilter
from serial.tools import list_ports

ISRAEL_TZ: ZoneInfo = ZoneInfo("Asia/Jerusalem")

# Soft charcoal living-room palette
BG: tuple[int, int, int] = (28, 31, 36)
CARD: tuple[int, int, int] = (38, 42, 49)
CARD_ALT: tuple[int, int, int] = (44, 48, 56)
BORDER: tuple[int, int, int] = (58, 64, 74)
TEXT: tuple[int, int, int] = (10, 10, 12)
MUTED: tuple[int, int, int] = (40, 40, 44)
ACCENT: tuple[int, int, int] = (10, 10, 12)
SAND: tuple[int, int, int] = (10, 10, 12)
SOFT_BLUE: tuple[int, int, int] = (20, 70, 140)
SOFT_GREEN: tuple[int, int, int] = (20, 110, 55)
SOFT_ORANGE: tuple[int, int, int] = (150, 80, 15)
SOFT_ROSE: tuple[int, int, int] = (150, 35, 40)
RING_TRACK: tuple[int, int, int] = (180, 180, 185)

SECTION_RE: re.Pattern[str] = re.compile(r"^---\s*(.+?)\s*---\s*$")
KV_RE: re.Pattern[str] = re.compile(r"^([^:]+):\s*(.+)$")
NUM_RE: re.Pattern[str] = re.compile(r"(-?\d+(?:\.\d+)?)")
FRAME_EDGE: str = "=================================================="
TILE_CACHE: Path = Path.home() / ".cache" / "super_station" / "tiles"
STATIC_BG_PATH: Path = Path(__file__).resolve().parent / "super_station_bg.png"
HOLIDAY_CACHE: Path = Path.home() / ".cache" / "super_station" / "holidays"
MAP_ZOOM: int = 15
USER_AGENT: str = "SuperStation/2.0 (Raspberry Pi home dashboard)"
CARD_RADIUS: int = 22
CARD_FROST: tuple[int, int, int, int] = (32, 36, 42, 18)
PILL_FROST: tuple[int, int, int, int] = (32, 36, 42, 24)
CARD_BLUR_RADIUS: int = 8
TEXT_OUTLINE: tuple[int, int, int] = (255, 255, 255)
TEXT_OUTLINE_WIDTH: int = 2
FONT_CANDIDATES: tuple[str, ...] = (
    "Liberation Sans",
    "FreeSans",
    "DejaVu Sans",
    "Noto Sans",
    "Sans",
)


@dataclass
class SensorState:
    """Parsed sensor frame plus connection metadata."""

    title: str = "CENTRAL SENSOR DATA"
    sections: dict[str, dict[str, str]] = field(default_factory=dict)
    last_update: float = 0.0
    frames: int = 0
    connected: bool = False
    port: str = ""
    raw_tail: list[str] = field(default_factory=list)
    error: str = ""


def parse_frame(text: str) -> tuple[str, dict[str, dict[str, str]]]:
    """Parse one CENTRAL SENSOR DATA frame into title + sections."""
    lines: list[str] = [line.strip("\r") for line in text.splitlines()]
    title: str = "CENTRAL SENSOR DATA"
    sections: dict[str, dict[str, str]] = {}
    current: str | None = None

    for line in lines:
        stripped: str = line.strip()
        if not stripped or stripped.startswith("="):
            continue
        if "CENTRAL SENSOR DATA" in stripped:
            title = stripped
            continue
        section_match: re.Match[str] | None = SECTION_RE.match(stripped)
        if section_match is not None:
            current = section_match.group(1).strip()
            sections.setdefault(current, {})
            continue
        if current is None:
            continue
        kv_match: re.Match[str] | None = KV_RE.match(stripped)
        if kv_match is not None:
            key: str = kv_match.group(1).strip()
            value: str = kv_match.group(2).strip()
            sections[current][key] = value
    return title, sections


def auto_detect_port() -> str | None:
    """Pick the first USB serial device, preferring ttyUSB/ttyACM."""
    preferred: list[str] = []
    others: list[str] = []
    for port in list_ports.comports():
        device: str = port.device
        if "ttyUSB" in device or "ttyACM" in device:
            preferred.append(device)
        else:
            others.append(device)
    if preferred:
        return preferred[0]
    if others:
        return others[0]
    return None


def parse_float(value: str | None) -> float | None:
    """Extract the first float from a sensor value string."""
    if value is None:
        return None
    match: re.Match[str] | None = NUM_RE.search(value)
    if match is None:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def clamp(value: float, low: float, high: float) -> float:
    """Clamp value into [low, high]."""
    return max(low, min(high, value))


def pick_font(size: int, bold: bool = False) -> pygame.font.Font:
    """Load the best available modern sans-serif font."""
    for name in FONT_CANDIDATES:
        path: str | None = pygame.font.match_font(name, bold=bold)
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.SysFont("sans-serif", size, bold=bold)


def render_text(
    font: pygame.font.Font,
    text: str,
    color: tuple[int, int, int],
    outline: tuple[int, int, int] = TEXT_OUTLINE,
    outline_width: int = TEXT_OUTLINE_WIDTH,
) -> pygame.Surface:
    """Render text with a visible border/outline around the glyphs."""
    fill: pygame.Surface = font.render(text, True, color)
    if outline_width <= 0:
        return fill
    edge: pygame.Surface = font.render(text, True, outline)
    pad: int = outline_width
    canvas: pygame.Surface = pygame.Surface(
        (fill.get_width() + pad * 2, fill.get_height() + pad * 2),
        pygame.SRCALPHA,
    )
    for dx in range(-pad, pad + 1):
        for dy in range(-pad, pad + 1):
            if dx == 0 and dy == 0:
                continue
            if dx * dx + dy * dy > pad * pad + pad:
                continue
            canvas.blit(edge, (pad + dx, pad + dy))
    canvas.blit(fill, (pad, pad))
    return canvas


def parse_gps_utc(
    sections: dict[str, dict[str, str]],
    last_update: float = 0.0,
) -> datetime | None:
    """Parse GPS UTC Date/Time into an aware UTC datetime."""
    gps: dict[str, str] = sections.get("GPS NEO-8M", {})
    utc_date: str = gps.get("UTC Date", "").strip()
    utc_time: str = gps.get("UTC Time", "").strip()
    if not utc_date or not utc_time:
        return None

    date_formats: tuple[str, ...] = ("%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d")
    time_formats: tuple[str, ...] = ("%H:%M:%S", "%H:%M")
    parsed: datetime | None = None
    for d_fmt in date_formats:
        for t_fmt in time_formats:
            try:
                parsed = datetime.strptime(f"{utc_date} {utc_time}", f"{d_fmt} {t_fmt}")
                break
            except ValueError:
                continue
        if parsed is not None:
            break
    if parsed is None:
        return None

    utc_dt: datetime = parsed.replace(tzinfo=timezone.utc)
    if last_update > 0:
        utc_dt = utc_dt + timedelta(seconds=max(0.0, time.time() - last_update))
    return utc_dt


def israel_time_from_gps(
    sections: dict[str, dict[str, str]],
    last_update: float,
) -> tuple[datetime | None, str]:
    """Build Israel local time from GPS UTC Date/Time fields."""
    utc_dt: datetime | None = parse_gps_utc(sections, last_update)
    if utc_dt is None:
        return None, "local"
    return utc_dt.astimezone(ISRAEL_TZ), "gps"


@dataclass
class SolarInfo:
    """Sunrise/sunset and sun bearing for the current GPS fix."""

    sunrise_local: datetime | None
    sunset_local: datetime | None
    day_length: timedelta | None
    sun_azimuth: float | None
    sun_altitude: float | None
    heading: float | None
    relative_sun: float | None


def _solar_utc_hours(
    lat: float,
    lon: float,
    day: date,
    rising: bool,
) -> float | None:
    """Return UTC decimal hours for sunrise/sunset (zenith 90.833 deg)."""
    n: int = day.timetuple().tm_yday
    lng_hour: float = lon / 15.0
    t: float = n + ((6.0 - lng_hour) / 24.0 if rising else (18.0 - lng_hour) / 24.0)

    m: float = (0.9856 * t) - 3.289
    l_sun: float = (
        m
        + (1.916 * math.sin(math.radians(m)))
        + (0.020 * math.sin(math.radians(2.0 * m)))
        + 282.634
    ) % 360.0

    ra: float = math.degrees(math.atan(0.91764 * math.tan(math.radians(l_sun)))) % 360.0
    l_quad: float = math.floor(l_sun / 90.0) * 90.0
    ra_quad: float = math.floor(ra / 90.0) * 90.0
    ra = (ra + (l_quad - ra_quad)) / 15.0

    sin_dec: float = 0.39782 * math.sin(math.radians(l_sun))
    cos_dec: float = math.cos(math.asin(sin_dec))
    cos_h: float = (
        math.cos(math.radians(90.833)) - (sin_dec * math.sin(math.radians(lat)))
    ) / (cos_dec * math.cos(math.radians(lat)))
    if cos_h > 1.0 or cos_h < -1.0:
        return None

    h: float
    if rising:
        h = 360.0 - math.degrees(math.acos(cos_h))
    else:
        h = math.degrees(math.acos(cos_h))
    h /= 15.0

    t_local: float = h + ra - (0.06571 * t) - 6.622
    ut: float = (t_local - lng_hour) % 24.0
    return ut


def _hours_to_utc_datetime(day: date, hours: float) -> datetime:
    """Convert UTC decimal hours on a calendar day to an aware datetime."""
    base: datetime = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return base + timedelta(hours=hours)


def sun_position(
    lat: float,
    lon: float,
    when_utc: datetime,
) -> tuple[float, float]:
    """Return (azimuth degrees from N, altitude degrees) for the sun."""
    if when_utc.tzinfo is None:
        when_utc = when_utc.replace(tzinfo=timezone.utc)
    else:
        when_utc = when_utc.astimezone(timezone.utc)

    day: date = when_utc.date()
    n: int = day.timetuple().tm_yday
    hour: float = (
        when_utc.hour
        + when_utc.minute / 60.0
        + when_utc.second / 3600.0
        + when_utc.microsecond / 3_600_000_000.0
    )

    gamma: float = 2.0 * math.pi / 365.0 * (n - 1 + (hour - 12.0) / 24.0)
    eqtime: float = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2.0 * gamma)
        - 0.040849 * math.sin(2.0 * gamma)
    )
    decl: float = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2.0 * gamma)
        + 0.000907 * math.sin(2.0 * gamma)
        - 0.002697 * math.cos(3.0 * gamma)
        + 0.00148 * math.sin(3.0 * gamma)
    )

    time_offset: float = eqtime + 4.0 * lon
    tst: float = hour * 60.0 + time_offset
    ha: float = math.radians(tst / 4.0 - 180.0)
    lat_r: float = math.radians(lat)

    cos_zenith: float = math.sin(lat_r) * math.sin(decl) + math.cos(lat_r) * math.cos(
        decl
    ) * math.cos(ha)
    cos_zenith = clamp(cos_zenith, -1.0, 1.0)
    zenith: float = math.acos(cos_zenith)
    altitude: float = 90.0 - math.degrees(zenith)

    az_y: float = -math.sin(ha)
    az_x: float = math.tan(decl) * math.cos(lat_r) - math.sin(lat_r) * math.cos(ha)
    azimuth: float = (math.degrees(math.atan2(az_y, az_x)) + 360.0) % 360.0
    return azimuth, altitude


def compute_solar_info(sections: dict[str, dict[str, str]], last_update: float) -> SolarInfo:
    """Compute sunrise/sunset/day length from GPS; relative sun from compass."""
    gps: dict[str, str] = sections.get("GPS NEO-8M", {})
    mag: dict[str, str] = sections.get("HP5883 / QMC5883P", {})
    lat: float | None = parse_float(gps.get("Latitude"))
    lon: float | None = parse_float(gps.get("Longitude"))
    heading: float | None = parse_float(mag.get("Heading"))

    empty: SolarInfo = SolarInfo(None, None, None, None, None, heading, None)
    if lat is None or lon is None:
        return empty

    when_utc: datetime | None = parse_gps_utc(sections, last_update)
    if when_utc is None:
        when_utc = datetime.now(timezone.utc)
    day: date = when_utc.astimezone(ISRAEL_TZ).date()

    rise_h: float | None = _solar_utc_hours(lat, lon, day, rising=True)
    set_h: float | None = _solar_utc_hours(lat, lon, day, rising=False)
    sunrise_local: datetime | None = None
    sunset_local: datetime | None = None
    day_length: timedelta | None = None
    if rise_h is not None:
        sunrise_local = _hours_to_utc_datetime(day, rise_h).astimezone(ISRAEL_TZ)
    if set_h is not None:
        sunset_local = _hours_to_utc_datetime(day, set_h).astimezone(ISRAEL_TZ)
    if sunrise_local is not None and sunset_local is not None:
        if sunset_local <= sunrise_local:
            sunset_local = sunset_local + timedelta(days=1)
        day_length = sunset_local - sunrise_local

    azimuth: float
    altitude: float
    azimuth, altitude = sun_position(lat, lon, when_utc)
    relative: float | None = None
    if heading is not None:
        relative = (azimuth - heading + 540.0) % 360.0 - 180.0

    return SolarInfo(
        sunrise_local=sunrise_local,
        sunset_local=sunset_local,
        day_length=day_length,
        sun_azimuth=azimuth,
        sun_altitude=altitude,
        heading=heading,
        relative_sun=relative,
    )


def format_day_length(delta: timedelta | None) -> str:
    """Format a day-length timedelta as Hh Mm."""
    if delta is None:
        return "—"
    total_sec: int = int(delta.total_seconds())
    hours: int = total_sec // 3600
    minutes: int = (total_sec % 3600) // 60
    return f"{hours}h {minutes:02d}m"


def relative_sun_text(relative: float | None) -> str:
    """Describe sun direction relative to compass heading."""
    if relative is None:
        return "—"
    if abs(relative) < 15:
        return "Ahead"
    if abs(relative) > 165:
        return "Behind"
    if relative > 0:
        return f"Right {relative:.0f}°"
    return f"Left {abs(relative):.0f}°"


class SerialReader(threading.Thread):
    """Background thread that reassembles frames from a serial port or file."""

    def __init__(
        self,
        state: SensorState,
        port: str,
        baud: int,
        demo_path: Path | None = None,
        lock: threading.Lock | None = None,
    ) -> None:
        super().__init__(daemon=True)
        self.state: SensorState = state
        self.port: str = port
        self.baud: int = baud
        self.demo_path: Path | None = demo_path
        self.lock: threading.Lock = lock if lock is not None else threading.Lock()
        self._stop: threading.Event = threading.Event()
        self._buffer: str = ""

    def stop(self) -> None:
        """Request the reader thread to exit."""
        self._stop.set()

    def _apply_frame(self, frame_text: str) -> None:
        title: str
        sections: dict[str, dict[str, str]]
        title, sections = parse_frame(frame_text)
        if not sections:
            return
        with self.lock:
            self.state.title = title
            self.state.sections = sections
            self.state.last_update = time.time()
            self.state.frames += 1
            self.state.error = ""
            self.state.raw_tail = [
                line for line in frame_text.splitlines() if line.strip()
            ][-8:]

    def _feed(self, chunk: str) -> None:
        """Reassemble frames. Header uses the same ==== bars as the footer."""
        self._buffer += chunk
        while True:
            marker_at: int = self._buffer.find("CENTRAL SENSOR DATA")
            if marker_at < 0:
                if len(self._buffer) > 20000:
                    self._buffer = self._buffer[-4000:]
                return
            after_marker: str = self._buffer[marker_at:]
            first_section: int = after_marker.find("---")
            if first_section < 0:
                return
            end_at: int = after_marker.find(FRAME_EDGE, first_section)
            if end_at < 0:
                return
            frame_body: str = after_marker[:end_at]
            self._buffer = after_marker[end_at + len(FRAME_EDGE) :]
            self._apply_frame(frame_body)

    def _run_demo(self) -> None:
        assert self.demo_path is not None
        with self.lock:
            self.state.connected = True
            self.state.port = f"DEMO:{self.demo_path.name}"
        while not self._stop.is_set():
            try:
                text: str = self.demo_path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                with self.lock:
                    self.state.error = str(exc)
                    self.state.connected = False
                time.sleep(1.0)
                continue
            self._apply_frame(text)
            time.sleep(1.0)

    def _run_serial(self) -> None:
        while not self._stop.is_set():
            try:
                with serial.Serial(self.port, self.baud, timeout=0.2) as ser:
                    with self.lock:
                        self.state.connected = True
                        self.state.port = self.port
                        self.state.error = ""
                    while not self._stop.is_set():
                        data: bytes = ser.read(4096)
                        if data:
                            self._feed(data.decode("utf-8", errors="replace"))
            except serial.SerialException as exc:
                with self.lock:
                    self.state.connected = False
                    self.state.error = str(exc)
                time.sleep(1.5)

    def run(self) -> None:
        if self.demo_path is not None:
            self._run_demo()
        else:
            self._run_serial()


def status_label(value: str | None) -> tuple[str, tuple[int, int, int]]:
    """Map ONLINE/OFFLINE to calm living-room labels."""
    if value is None:
        return "—", MUTED
    upper: str = value.upper()
    if "ONLINE" in upper:
        return "Online", SOFT_GREEN
    if "OFFLINE" in upper:
        return "Offline", SOFT_ROSE
    return value.title(), MUTED


def temp_to_color(temp_c: float | None) -> tuple[int, int, int]:
    """Pick soft accent color from temperature bands."""
    if temp_c is None:
        return MUTED
    if temp_c < 20:
        return SOFT_BLUE
    if temp_c <= 25:
        return SOFT_GREEN
    if temp_c <= 30:
        return SOFT_ORANGE
    return SOFT_ROSE


def pressure_to_color(hpa: float | None) -> tuple[int, int, int]:
    """Pick soft accent color from barometric pressure."""
    if hpa is None:
        return MUTED
    if hpa < 1000:
        return SOFT_BLUE
    if hpa <= 1015:
        return SOFT_GREEN
    if hpa <= 1025:
        return SOFT_ORANGE
    return SOFT_ROSE


SUN_FILL: tuple[int, int, int] = (232, 196, 120)
CLOUD_FILL: tuple[int, int, int] = (176, 174, 170)
CLOUD_DARK: tuple[int, int, int] = (120, 124, 132)
RAIN_DROP: tuple[int, int, int] = (120, 168, 210)
MOON_FILL: tuple[int, int, int] = (214, 210, 200)


def _avg_humidity(sections: dict[str, dict[str, str]]) -> float | None:
    """Average humidity from online DHT sensors."""
    values: list[float] = []
    for name, fields in sections.items():
        if "DHT" not in name.upper() and "LOCAL" not in name.upper():
            continue
        status: str = fields.get("Status", "ONLINE").upper()
        if "OFFLINE" in status:
            continue
        hum: float | None = parse_float(fields.get("Humidity"))
        if hum is not None:
            values.append(hum)
    if not values:
        return None
    return sum(values) / len(values)


def infer_weather(
    sections: dict[str, dict[str, str]],
    last_update: float,
) -> tuple[str, str]:
    """Infer a simple weather state from sensors + sun altitude.

    Returns (kind, label) where kind is one of:
    clear, partly_cloudy, cloudy, rain, night_clear, night_cloudy.
    """
    solar: SolarInfo = compute_solar_info(sections, last_update)
    humidity: float | None = _avg_humidity(sections)
    pressure: float | None = parse_float(
        sections.get("BMP180", {}).get("Pressure")
    )
    sun_alt: float = solar.sun_altitude if solar.sun_altitude is not None else 20.0
    is_day: bool = sun_alt > 0.5

    rainy: bool = False
    if humidity is not None and pressure is not None:
        rainy = humidity >= 78 and pressure <= 1005
    elif humidity is not None:
        rainy = humidity >= 85
    elif pressure is not None:
        rainy = pressure <= 998

    cloudy: bool = False
    if humidity is not None:
        cloudy = humidity >= 62
    if pressure is not None and pressure <= 1010:
        cloudy = True

    partly: bool = False
    if humidity is not None:
        partly = 45 <= humidity < 62
    elif pressure is not None:
        partly = 1010 < pressure <= 1018

    if rainy:
        return "rain", "Rain likely"
    if not is_day:
        if cloudy:
            return "night_cloudy", "Cloudy night"
        return "night_clear", "Clear night"
    if cloudy:
        return "cloudy", "Cloudy"
    if partly:
        return "partly_cloudy", "Partly cloudy"
    return "clear", "Sunny"


def _draw_sun(surface: pygame.Surface, cx: int, cy: int, radius: int) -> None:
    """Draw a soft sun disc with short rays."""
    pygame.draw.circle(surface, SUN_FILL, (cx, cy), radius)
    pygame.draw.circle(surface, (245, 220, 160), (cx, cy), max(2, radius // 2))
    ray_inner: int = radius + 4
    ray_outer: int = radius + 14
    for i in range(8):
        ang: float = math.radians(i * 45)
        x0: int = int(cx + math.cos(ang) * ray_inner)
        y0: int = int(cy + math.sin(ang) * ray_inner)
        x1: int = int(cx + math.cos(ang) * ray_outer)
        y1: int = int(cy + math.sin(ang) * ray_outer)
        pygame.draw.line(surface, SUN_FILL, (x0, y0), (x1, y1), 3)


def _draw_moon(surface: pygame.Surface, cx: int, cy: int, radius: int) -> None:
    """Draw a crescent moon."""
    pygame.draw.circle(surface, MOON_FILL, (cx, cy), radius)
    pygame.draw.circle(surface, BG, (cx + radius // 3, cy - radius // 8), radius - 2)


def _draw_cloud(
    surface: pygame.Surface,
    cx: int,
    cy: int,
    scale: float = 1.0,
    color: tuple[int, int, int] = CLOUD_FILL,
) -> None:
    """Draw a soft cloud from overlapping circles."""
    r1: int = int(16 * scale)
    r2: int = int(20 * scale)
    r3: int = int(14 * scale)
    pygame.draw.circle(surface, color, (cx - int(18 * scale), cy), r1)
    pygame.draw.circle(surface, color, (cx + int(2 * scale), cy - int(6 * scale)), r2)
    pygame.draw.circle(surface, color, (cx + int(22 * scale), cy), r3)
    pygame.draw.ellipse(
        surface,
        color,
        pygame.Rect(
            cx - int(34 * scale),
            cy - int(4 * scale),
            int(68 * scale),
            int(28 * scale),
        ),
    )


def _draw_rain(surface: pygame.Surface, cx: int, cy: int, scale: float = 1.0) -> None:
    """Draw a few rain drops under a cloud."""
    for dx, dy in ((-14, 18), (-2, 24), (12, 20)):
        x0: int = cx + int(dx * scale)
        y0: int = cy + int(dy * scale)
        pygame.draw.line(
            surface,
            RAIN_DROP,
            (x0, y0),
            (x0 - int(3 * scale), y0 + int(10 * scale)),
            3,
        )


def draw_weather_icon(
    surface: pygame.Surface,
    kind: str,
    rect: pygame.Rect,
) -> None:
    """Draw a weather glyph inside rect."""
    cx: int = rect.centerx
    cy: int = rect.centery
    if kind == "clear":
        _draw_sun(surface, cx, cy, 28)
    elif kind == "partly_cloudy":
        _draw_sun(surface, cx - 16, cy - 10, 18)
        _draw_cloud(surface, cx + 8, cy + 8, 1.05)
    elif kind == "cloudy":
        _draw_cloud(surface, cx - 6, cy - 2, 1.15, CLOUD_FILL)
        _draw_cloud(surface, cx + 14, cy + 8, 0.9, CLOUD_DARK)
    elif kind == "rain":
        _draw_cloud(surface, cx, cy - 8, 1.15, CLOUD_DARK)
        _draw_rain(surface, cx, cy - 2, 1.1)
    elif kind == "night_clear":
        _draw_moon(surface, cx, cy, 26)
    elif kind == "night_cloudy":
        _draw_moon(surface, cx - 18, cy - 10, 16)
        _draw_cloud(surface, cx + 10, cy + 6, 1.05, CLOUD_DARK)
    else:
        _draw_cloud(surface, cx, cy, 1.0)


# Sharp daily photo used for card blur sampling
_CURRENT_SHARP_BG: pygame.Surface | None = None
_CARD_BLUR_CACHE: dict[tuple[int, int, int, int, int, int], pygame.Surface] = {}
_CARD_BLUR_BG_ID: int = 0


def set_sharp_background(backdrop: pygame.Surface) -> None:
    """Set the sharp photo used under frosted cards; clears blur cache on change."""
    global _CURRENT_SHARP_BG, _CARD_BLUR_CACHE, _CARD_BLUR_BG_ID
    if backdrop is _CURRENT_SHARP_BG:
        return
    _CURRENT_SHARP_BG = backdrop
    _CARD_BLUR_CACHE.clear()
    _CARD_BLUR_BG_ID += 1


def _blurred_card_backdrop(rect: pygame.Rect, radius: int) -> pygame.Surface | None:
    """Return a cached rounded blur of the sharp photo under rect."""
    if _CURRENT_SHARP_BG is None:
        return None
    key: tuple[int, int, int, int, int, int] = (
        rect.x,
        rect.y,
        rect.width,
        rect.height,
        radius,
        CARD_BLUR_RADIUS,
    )
    cached: pygame.Surface | None = _CARD_BLUR_CACHE.get(key)
    if cached is not None:
        return cached

    bg: pygame.Surface = _CURRENT_SHARP_BG
    clip: pygame.Rect = rect.clip(bg.get_rect())
    if clip.width <= 2 or clip.height <= 2:
        return None

    region: pygame.Surface = bg.subsurface(clip).copy()
    if region.get_size() != (rect.width, rect.height):
        region = pygame.transform.smoothscale(region, (rect.width, rect.height))

    to_bytes = getattr(pygame.image, "tobytes", None) or pygame.image.tostring
    from_bytes = getattr(pygame.image, "frombytes", None) or pygame.image.fromstring
    raw: bytes = to_bytes(region, "RGB")
    image: Image.Image = Image.frombytes("RGB", (rect.width, rect.height), raw)
    image = image.filter(ImageFilter.GaussianBlur(radius=CARD_BLUR_RADIUS))
    blurred: pygame.Surface = from_bytes(
        image.tobytes(),
        (rect.width, rect.height),
        "RGB",
    ).convert_alpha()

    mask: pygame.Surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
    blurred.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

    _CARD_BLUR_CACHE[key] = blurred
    return blurred


def draw_frosted_rect(
    surface: pygame.Surface,
    rect: pygame.Rect,
    radius: int,
    frost: tuple[int, int, int, int] = CARD_FROST,
) -> None:
    """Draw a frosted glass card: blur only the box, keep the photo sharp around it."""
    blurred: pygame.Surface | None = _blurred_card_backdrop(rect, radius)
    if blurred is not None:
        surface.blit(blurred, rect.topleft)

    panel: pygame.Surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    pygame.draw.rect(panel, frost, panel.get_rect(), border_radius=radius)
    pygame.draw.rect(
        panel,
        (255, 255, 255, 36),
        panel.get_rect(),
        width=1,
        border_radius=radius,
    )
    surface.blit(panel, rect.topleft)


def draw_card(surface: pygame.Surface, rect: pygame.Rect) -> None:
    """Draw a soft frosted living-room card."""
    draw_frosted_rect(surface, rect, CARD_RADIUS, CARD_FROST)


@dataclass
class HolidayDay:
    """One calendar day with optional Israeli holiday label."""

    day: date
    day_num: str
    holiday: str


class IsraelHolidayGuide:
    """Load Israeli holidays from Hebcal for today and the next 3 days."""

    def __init__(self) -> None:
        HOLIDAY_CACHE.mkdir(parents=True, exist_ok=True)
        self._lock: threading.Lock = threading.Lock()
        self._by_date: dict[str, list[str]] = {}
        self._loaded_for: str = ""
        self._loading: bool = False
        self._pending: dict[str, list[str]] | None = None
        self._pending_key: str = ""

    def _range_key(self, start: date) -> str:
        return start.isoformat()

    def _cache_path(self, start: date) -> Path:
        end: date = start + timedelta(days=3)
        return HOLIDAY_CACHE / f"{start.isoformat()}_{end.isoformat()}.json"

    def _fetch_async(self, start: date) -> None:
        end: date = start + timedelta(days=3)
        path: Path = self._cache_path(start)
        key: str = self._range_key(start)

        def worker() -> None:
            try:
                if path.exists() and path.stat().st_size > 20:
                    payload: dict[str, object] = json.loads(
                        path.read_text(encoding="utf-8")
                    )
                else:
                    # Hebcal Israel + major Jewish holidays
                    url: str = (
                        "https://www.hebcal.com/hebcal?v=1&cfg=json"
                        "&maj=1&min=1&mod=1&i=on&c=off&geo=none"
                        f"&start={start.isoformat()}&end={end.isoformat()}"
                    )
                    req: urllib.request.Request = urllib.request.Request(
                        url,
                        headers={"User-Agent": USER_AGENT},
                    )
                    with urllib.request.urlopen(req, timeout=12) as resp:
                        payload = json.loads(resp.read().decode("utf-8"))
                    path.write_text(json.dumps(payload), encoding="utf-8")

                mapped: dict[str, list[str]] = {}
                items = payload.get("items", [])
                if isinstance(items, list):
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        category: str = str(item.get("category", ""))
                        if category not in {"holiday", "modern"}:
                            continue
                        raw_date: str = str(item.get("date", ""))[:10]
                        title: str = str(item.get("title", "")).strip()
                        if not raw_date or not title:
                            continue
                        mapped.setdefault(raw_date, []).append(title)
                with self._lock:
                    self._pending = mapped
                    self._pending_key = key
            except Exception:
                with self._lock:
                    self._loading = False

        threading.Thread(target=worker, daemon=True).start()

    def days(self) -> list[HolidayDay]:
        """Return 4 days: today (Israel) through +3, with holiday names."""
        start: date = datetime.now(ISRAEL_TZ).date()
        key: str = self._range_key(start)

        with self._lock:
            pending = self._pending
            pending_key = self._pending_key
            if pending is not None and pending_key == key:
                self._by_date = pending
                self._loaded_for = key
                self._pending = None
                self._loading = False
            loading: bool = self._loading

        if self._loaded_for != key and not loading:
            cache: Path = self._cache_path(start)
            if cache.exists():
                try:
                    payload = json.loads(cache.read_text(encoding="utf-8"))
                    mapped: dict[str, list[str]] = {}
                    for item in payload.get("items", []):
                        if not isinstance(item, dict):
                            continue
                        category = str(item.get("category", ""))
                        if category not in {"holiday", "modern"}:
                            continue
                        raw_date = str(item.get("date", ""))[:10]
                        title = str(item.get("title", "")).strip()
                        if raw_date and title:
                            mapped.setdefault(raw_date, []).append(title)
                    self._by_date = mapped
                    self._loaded_for = key
                except Exception:
                    pass
            with self._lock:
                if not self._loading:
                    self._loading = True
                    self._fetch_async(start)

        result: list[HolidayDay] = []
        for offset in range(4):
            day: date = start + timedelta(days=offset)
            names: list[str] = self._by_date.get(day.isoformat(), [])
            # Prefer the first major-looking title; skip very long candle notes
            holiday: str = names[0] if names else "—"
            if len(holiday) > 22:
                holiday = holiday[:21] + "…"
            result.append(
                HolidayDay(
                    day=day,
                    day_num=day.strftime("%d"),
                    holiday=holiday,
                )
            )
        return result


class DailyBackground:
    """Load a fixed local photo as the dashboard background."""

    def __init__(self, path: Path = STATIC_BG_PATH) -> None:
        self._path: Path = path
        self._screen_size: tuple[int, int] = (0, 0)
        self._photo: pygame.Surface | None = None
        self._source_bytes: bytes | None = self._load_bytes(path)

    def _load_bytes(self, path: Path) -> bytes | None:
        """Read image bytes; ignore missing or empty files."""
        try:
            if not path.is_file() or path.stat().st_size < 32:
                return None
            data: bytes = path.read_bytes()
            if len(data) < 32:
                return None
            return data
        except OSError:
            return None

    def _build_surface(self, data: bytes, width: int, height: int) -> pygame.Surface:
        """Build a sharp full-screen photo (no blur)."""
        image: Image.Image = Image.open(io.BytesIO(data)).convert("RGB")
        src_w, src_h = image.size
        scale: float = max(width / src_w, height / src_h)
        new_w: int = max(1, int(src_w * scale))
        new_h: int = max(1, int(src_h * scale))
        image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        left: int = max(0, (new_w - width) // 2)
        top: int = max(0, (new_h - height) // 2)
        image = image.crop((left, top, left + width, top + height))
        mode: str = image.mode
        raw: bytes = image.tobytes()
        return pygame.image.fromstring(raw, (width, height), mode).convert()

    def get(self, width: int, height: int) -> pygame.Surface:
        """Return the static background scaled to the screen."""
        if self._source_bytes is None:
            # Retry in case the file was written after startup
            self._source_bytes = self._load_bytes(self._path)
        if self._source_bytes is None:
            fallback: pygame.Surface = pygame.Surface((width, height))
            fallback.fill(BG)
            return fallback

        if self._photo is None or self._screen_size != (width, height):
            try:
                self._photo = self._build_surface(self._source_bytes, width, height)
                self._screen_size = (width, height)
            except Exception:
                fallback = pygame.Surface((width, height))
                fallback.fill(BG)
                return fallback

        assert self._photo is not None
        return self._photo


def draw_arc(
    surface: pygame.Surface,
    center: tuple[int, int],
    radius: int,
    width: int,
    start_angle: float,
    end_angle: float,
    color: tuple[int, int, int],
) -> None:
    """Draw a thick circular arc using short line segments."""
    if end_angle <= start_angle:
        return
    steps: int = max(8, int((end_angle - start_angle) * radius / 4))
    points: list[tuple[float, float]] = []
    for i in range(steps + 1):
        t: float = i / steps
        ang: float = start_angle + (end_angle - start_angle) * t
        points.append(
            (
                center[0] + math.cos(ang) * radius,
                center[1] + math.sin(ang) * radius,
            )
        )
    if len(points) >= 2:
        pygame.draw.lines(surface, color, False, points, width)


def draw_progress_ring(
    surface: pygame.Surface,
    rect: pygame.Rect,
    title: str,
    value: float | None,
    unit: str,
    vmin: float,
    vmax: float,
    font_title: pygame.font.Font,
    font_value: pygame.font.Font,
    font_meta: pygame.font.Font,
    accent: tuple[int, int, int],
    status: str | None = None,
    secondary: float | None = None,
    secondary_unit: str = "%",
    value_decimals: int = 1,
) -> None:
    """Modern circular progress ring with large readable typography."""
    draw_card(surface, rect)

    title_surf: pygame.Surface = render_text(font_title, title, MUTED)
    surface.blit(title_surf, (rect.x + 20, rect.y + 16))

    if status is not None:
        label: str
        color: tuple[int, int, int]
        label, color = status_label(status)
        st_surf: pygame.Surface = render_text(font_meta, label, color)
        surface.blit(st_surf, (rect.right - st_surf.get_width() - 20, rect.y + 18))

    cx: int = rect.centerx
    cy: int = rect.centery + 10
    radius: int = min(rect.width, rect.height) // 2 - 36
    ring_w: int = max(10, radius // 7)

    # Full track
    draw_arc(surface, (cx, cy), radius, ring_w, -math.pi * 0.75, math.pi * 0.75, RING_TRACK)

    ratio: float = 0.0
    if value is not None and vmax > vmin:
        ratio = clamp((value - vmin) / (vmax - vmin), 0.0, 1.0)
        end: float = -math.pi * 0.75 + (math.pi * 1.5) * ratio
        draw_arc(surface, (cx, cy), radius, ring_w, -math.pi * 0.75, end, accent)

    if value is not None:
        value_text: str = f"{value:.{value_decimals}f}"
    else:
        value_text = "—"
    value_surf: pygame.Surface = render_text(font_value, value_text, TEXT)
    unit_surf: pygame.Surface = render_text(font_meta, unit, MUTED)
    surface.blit(value_surf, (cx - value_surf.get_width() // 2, cy - value_surf.get_height() // 2 - 4))
    surface.blit(unit_surf, (cx - unit_surf.get_width() // 2, cy + value_surf.get_height() // 2 - 2))

    if secondary is not None:
        hum_surf: pygame.Surface = render_text(
            font_meta,
            f"Humidity {secondary:.0f}{secondary_unit}",
            MUTED,
        )
        surface.blit(
            hum_surf,
            (cx - hum_surf.get_width() // 2, rect.bottom - 28),
        )


def latlon_to_world(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Convert WGS84 to OSM world pixel coords at zoom."""
    n: float = 2.0 ** zoom
    x: float = (lon + 180.0) / 360.0 * n * 256.0
    lat_rad: float = math.radians(lat)
    y: float = (
        (1.0 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi)
        / 2.0
        * n
        * 256.0
    )
    return x, y


class MapTileCache:
    """Download and cache OpenStreetMap tiles for the location card."""

    def __init__(self) -> None:
        TILE_CACHE.mkdir(parents=True, exist_ok=True)
        self._memory: dict[tuple[int, int, int], pygame.Surface | None] = {}
        self._bytes: dict[tuple[int, int, int], bytes] = {}
        self._lock: threading.Lock = threading.Lock()
        self._inflight: set[tuple[int, int, int]] = set()
        self._last_center: tuple[float, float, int] | None = None
        self._mosaic: pygame.Surface | None = None
        self._mosaic_origin: tuple[float, float] = (0.0, 0.0)
        self._dirty: bool = True

    def _fetch_tile_async(self, zoom: int, x: int, y: int) -> None:
        key: tuple[int, int, int] = (zoom, x, y)
        path: Path = TILE_CACHE / f"{zoom}_{x}_{y}.png"

        def worker() -> None:
            try:
                if path.exists():
                    data: bytes = path.read_bytes()
                else:
                    url: str = f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"
                    req: urllib.request.Request = urllib.request.Request(
                        url,
                        headers={"User-Agent": USER_AGENT},
                    )
                    with urllib.request.urlopen(req, timeout=4) as resp:
                        data = resp.read()
                    path.write_bytes(data)
                with self._lock:
                    self._bytes[key] = data
                    self._dirty = True
            except Exception:
                with self._lock:
                    self._memory[key] = None
            finally:
                with self._lock:
                    self._inflight.discard(key)

        threading.Thread(target=worker, daemon=True).start()

    def _load_tile(self, zoom: int, x: int, y: int) -> pygame.Surface | None:
        key: tuple[int, int, int] = (zoom, x, y)
        with self._lock:
            if key in self._memory:
                return self._memory[key]
            raw: bytes | None = self._bytes.pop(key, None)

        if raw is not None:
            try:
                surf: pygame.Surface = pygame.image.load(io.BytesIO(raw)).convert()
            except pygame.error:
                surf = pygame.image.load(io.BytesIO(raw))
            with self._lock:
                self._memory[key] = surf
            return surf

        path: Path = TILE_CACHE / f"{zoom}_{x}_{y}.png"
        if path.exists():
            try:
                surf = pygame.image.load(str(path)).convert()
            except pygame.error:
                surf = pygame.image.load(str(path))
            with self._lock:
                self._memory[key] = surf
            return surf

        with self._lock:
            if key in self._inflight:
                return None
            self._inflight.add(key)
        self._fetch_tile_async(zoom, x, y)
        return None

    def build_mosaic(
        self,
        lat: float,
        lon: float,
        zoom: int,
        width: int,
        height: int,
    ) -> tuple[pygame.Surface, tuple[float, float]]:
        """Return a map mosaic and its top-left world-pixel origin."""
        center: tuple[float, float, int] = (round(lat, 5), round(lon, 5), zoom)
        with self._lock:
            dirty: bool = self._dirty
            self._dirty = False
        if (
            self._mosaic is not None
            and self._last_center == center
            and self._mosaic.get_width() == width
            and self._mosaic.get_height() == height
            and not dirty
        ):
            return self._mosaic, self._mosaic_origin

        wx: float
        wy: float
        wx, wy = latlon_to_world(lat, lon, zoom)
        left: float = wx - width / 2
        top: float = wy - height / 2
        mosaic: pygame.Surface = pygame.Surface((width, height))
        mosaic.fill(CARD_ALT)

        tile_x0: int = int(math.floor(left / 256.0))
        tile_y0: int = int(math.floor(top / 256.0))
        tile_x1: int = int(math.floor((left + width) / 256.0))
        tile_y1: int = int(math.floor((top + height) / 256.0))
        n_tiles: int = 2**zoom

        for ty in range(tile_y0, tile_y1 + 1):
            for tx in range(tile_x0, tile_x1 + 1):
                if tx < 0 or ty < 0 or tx >= n_tiles or ty >= n_tiles:
                    continue
                tile: pygame.Surface | None = self._load_tile(zoom, tx, ty)
                dest_x: int = int(tx * 256 - left)
                dest_y: int = int(ty * 256 - top)
                if tile is None:
                    pygame.draw.rect(
                        mosaic,
                        RING_TRACK,
                        pygame.Rect(dest_x, dest_y, 256, 256),
                    )
                else:
                    mosaic.blit(tile, (dest_x, dest_y))

        # Soft warm wash so the map matches the dashboard
        tint: pygame.Surface = pygame.Surface((width, height), pygame.SRCALPHA)
        tint.fill((28, 31, 36, 70))
        mosaic.blit(tint, (0, 0))

        self._mosaic = mosaic
        self._mosaic_origin = (left, top)
        self._last_center = center
        return mosaic, (left, top)


def draw_location_card(
    surface: pygame.Surface,
    rect: pygame.Rect,
    fields: dict[str, str],
    tile_cache: MapTileCache,
    font_title: pygame.font.Font,
    font_body: pygame.font.Font,
) -> None:
    """Draw a calm location card with a small map."""
    draw_card(surface, rect)
    title: pygame.Surface = render_text(font_title, "Location", MUTED)
    surface.blit(title, (rect.x + 22, rect.y + 18))

    map_rect: pygame.Rect = pygame.Rect(
        rect.x + 18,
        rect.y + 52,
        rect.width - 36,
        rect.height - 120,
    )
    clip: pygame.Rect = map_rect.inflate(0, 0)
    # Rounded map well
    pygame.draw.rect(surface, CARD_ALT, map_rect, border_radius=16)

    lat: float | None = parse_float(fields.get("Latitude"))
    lon: float | None = parse_float(fields.get("Longitude"))

    if lat is not None and lon is not None:
        mosaic: pygame.Surface
        origin: tuple[float, float]
        mosaic, origin = tile_cache.build_mosaic(
            lat,
            lon,
            MAP_ZOOM,
            map_rect.width,
            map_rect.height,
        )
        surface.set_clip(map_rect)
        surface.blit(mosaic, map_rect.topleft)
        surface.set_clip(None)

        wx: float
        wy: float
        wx, wy = latlon_to_world(lat, lon, MAP_ZOOM)
        px: int = map_rect.x + int(wx - origin[0])
        py: int = map_rect.y + int(wy - origin[1])
        pygame.draw.circle(surface, ACCENT, (px, py), 8)
        pygame.draw.circle(surface, TEXT, (px, py), 3)
    else:
        wait: pygame.Surface = render_text(font_body, "Waiting for GPS…", MUTED)
        surface.blit(
            wait,
            (
                map_rect.centerx - wait.get_width() // 2,
                map_rect.centery - wait.get_height() // 2,
            ),
        )

    pygame.draw.rect(surface, BORDER, map_rect, width=1, border_radius=16)

    info_y: int = map_rect.bottom + 14
    if lat is not None and lon is not None:
        coords: str = f"{lat:.4f}, {lon:.4f}"
    else:
        coords = "No fix yet"
    sats: str = fields.get("Satellites", "—")
    line1: pygame.Surface = render_text(font_body, coords, TEXT)
    line2: pygame.Surface = render_text(font_body, f"{sats} satellites", MUTED)
    surface.blit(line1, (rect.x + 22, info_y))
    surface.blit(line2, (rect.x + 22, info_y + 24))
    _ = clip


def draw_solar_card(
    surface: pygame.Surface,
    rect: pygame.Rect,
    solar: SolarInfo,
    font_title: pygame.font.Font,
    font_body: pygame.font.Font,
    font_value: pygame.font.Font,
) -> None:
    """Draw sunrise, sunset, and day length for the living room."""
    draw_card(surface, rect)
    title: pygame.Surface = render_text(font_title, "Daylight", MUTED)
    surface.blit(title, (rect.x + 22, rect.y + 18))

    rise_txt: str = (
        solar.sunrise_local.strftime("%H:%M") if solar.sunrise_local is not None else "—"
    )
    set_txt: str = (
        solar.sunset_local.strftime("%H:%M") if solar.sunset_local is not None else "—"
    )
    len_txt: str = format_day_length(solar.day_length)

    items: list[tuple[str, str, tuple[int, int, int]]] = [
        ("Sunrise", rise_txt, SAND),
        ("Sunset", set_txt, SOFT_ORANGE),
        ("Day length", len_txt, ACCENT),
    ]
    # Compact horizontal row so the card fits under the map
    col_w: int = (rect.width - 44) // 3
    y: int = rect.y + 54
    for idx, (label, value, color) in enumerate(items):
        x: int = rect.x + 22 + idx * col_w
        lab: pygame.Surface = render_text(font_body, label, MUTED)
        val: pygame.Surface = render_text(font_value, value, color)
        surface.blit(lab, (x, y))
        surface.blit(val, (x, y + 28))

    rel: pygame.Surface = render_text(
        font_body,
        f"Sun is {relative_sun_text(solar.relative_sun).lower()}",
        MUTED,
    )
    surface.blit(rel, (rect.x + 22, rect.bottom - 36))


@dataclass
class GaugeSpec:
    """One dial gauge definition (temperature or pressure)."""

    section: str
    title: str
    value_key: str = "Temperature"
    unit: str = "°C"
    vmin: float = -5.0
    vmax: float = 50.0
    humid_key: str | None = "Humidity"
    status_key: str | None = "Status"
    color_mode: str = "temp"
    value_decimals: int = 1


def gauge_has_data(spec: GaugeSpec, sections: dict[str, dict[str, str]]) -> bool:
    """Return True only when this sensor has a real value to display."""
    fields: dict[str, str] | None = sections.get(spec.section)
    if not fields:
        return False
    if spec.status_key is not None:
        status: str = fields.get(spec.status_key, "").upper()
        if "OFFLINE" in status:
            return False
    value: float | None = parse_float(fields.get(spec.value_key))
    return value is not None


class HomeDashboard:
    """Fullscreen modern smart-home dashboard."""

    def __init__(self, state: SensorState, lock: threading.Lock, fullscreen: bool) -> None:
        pygame.init()
        pygame.display.set_caption("Home")
        flags: int = pygame.FULLSCREEN if fullscreen else 0
        size: tuple[int, int] = (1280, 800) if not fullscreen else (0, 0)
        self.screen: pygame.Surface = pygame.display.set_mode(size, flags)
        self.clock: pygame.time.Clock = pygame.time.Clock()
        self.state: SensorState = state
        self.lock: threading.Lock = lock
        self.running: bool = True
        self.map_cache: MapTileCache = MapTileCache()
        self.daily_bg: DailyBackground = DailyBackground()
        self.holiday_guide: IsraelHolidayGuide = IsraelHolidayGuide()
        self.font_clock: pygame.font.Font = pick_font(172, bold=True)
        self.font_date: pygame.font.Font = pick_font(28)
        self.font_brand: pygame.font.Font = pick_font(28, bold=True)
        self.font_title: pygame.font.Font = pick_font(20)
        self.font_body: pygame.font.Font = pick_font(18)
        self.font_value: pygame.font.Font = pick_font(36, bold=True)
        self.font_ring: pygame.font.Font = pick_font(42, bold=True)
        self.font_meta: pygame.font.Font = pick_font(16)
        self.gauges: list[GaugeSpec] = [
            GaugeSpec("LOCAL DHT11", "Living room", status_key=None),
            GaugeSpec("ESP-NOW DHT11 #1", "Sensor 1"),
            GaugeSpec("ESP-NOW DHT11 #2", "Bedroom"),
            GaugeSpec("ESP-NOW DHT11 #3", "Balcony"),
            GaugeSpec("ESP-NOW DHT11 #4", "Sensor 4"),
            GaugeSpec("BMP180", "Air temp", humid_key=None, status_key=None),
            GaugeSpec(
                "BMP180",
                "Pressure",
                value_key="Pressure",
                unit="hPa",
                vmin=960.0,
                vmax=1060.0,
                humid_key=None,
                status_key=None,
                color_mode="pressure",
                value_decimals=0,
            ),
        ]

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    self.running = False
                elif event.key == pygame.K_f:
                    pygame.display.toggle_fullscreen()

    def draw_header(self, snapshot: SensorState) -> int:
        """Draw calm header with brand, weather, stacked date, and clock."""
        width: int = self.screen.get_width()
        header_h: int = 250

        brand: pygame.Surface = render_text(self.font_brand, "Home", TEXT)
        self.screen.blit(brand, (36, 18))

        weather_kind: str
        weather_label: str
        weather_kind, weather_label = infer_weather(
            snapshot.sections,
            snapshot.last_update,
        )
        weather_card: pygame.Rect = pygame.Rect(28, 56, 150, 128)
        draw_frosted_rect(self.screen, weather_card, 20, CARD_FROST)
        icon_rect: pygame.Rect = pygame.Rect(
            weather_card.x + 10,
            weather_card.y + 10,
            weather_card.width - 20,
            78,
        )
        draw_weather_icon(self.screen, weather_kind, icon_rect)
        weather_txt: pygame.Surface = render_text(self.font_meta, weather_label, MUTED)
        self.screen.blit(
            weather_txt,
            (
                weather_card.centerx - weather_txt.get_width() // 2,
                weather_card.bottom - 30,
            ),
        )

        gps_now: datetime | None
        time_source: str
        gps_now, time_source = israel_time_from_gps(
            snapshot.sections,
            snapshot.last_update,
        )
        now: datetime = gps_now if gps_now is not None else datetime.now(ISRAEL_TZ)
        clock_text: str = now.strftime("%H:%M")
        seconds: str = now.strftime("%S")
        days_in_month: int = calendar.monthrange(now.year, now.month)[1]
        day_text: str = f"{now.strftime('%d')} | {days_in_month}"
        month_text: str = now.strftime("%B").lower()

        clock_surf: pygame.Surface = render_text(self.font_clock, clock_text, TEXT)
        # Stretch digits horizontally so the time reads a bit wider
        clock_surf = pygame.transform.smoothscale(
            clock_surf,
            (int(clock_surf.get_width() * 1.30), clock_surf.get_height()),
        )
        sec_surf: pygame.Surface = render_text(self.font_date, seconds, MUTED)
        day_surf: pygame.Surface = render_text(self.font_value, day_text, TEXT)
        month_surf: pygame.Surface = render_text(self.font_body, month_text, MUTED)

        # Date box between weather and clock — same size as weather card
        date_box: pygame.Rect = pygame.Rect(
            weather_card.right + 16,
            weather_card.y,
            weather_card.width,
            weather_card.height,
        )
        draw_frosted_rect(self.screen, date_box, 20, CARD_FROST)
        day_y: int = date_box.y + (
            date_box.height - (day_surf.get_height() + 8 + month_surf.get_height())
        ) // 2
        self.screen.blit(
            day_surf,
            (date_box.centerx - day_surf.get_width() // 2, day_y),
        )
        self.screen.blit(
            month_surf,
            (
                date_box.centerx - month_surf.get_width() // 2,
                day_y + day_surf.get_height() + 8,
            ),
        )

        # Clock box — to the right of the date card
        clock_pad_x: int = 28
        clock_pad_y: int = 10
        clock_gap: int = 12
        clock_inner_w: int = clock_surf.get_width() + clock_gap + sec_surf.get_width()
        clock_inner_h: int = max(clock_surf.get_height(), sec_surf.get_height() + 24)
        clock_box: pygame.Rect = pygame.Rect(
            date_box.right + 90,
            0,
            clock_inner_w + clock_pad_x * 2,
            clock_inner_h + clock_pad_y * 2,
        )
        clock_box.centery = weather_card.centery
        draw_frosted_rect(self.screen, clock_box, 22, CARD_FROST)
        clock_x: int = clock_box.x + clock_pad_x
        clock_y: int = clock_box.y + clock_pad_y - 4
        self.screen.blit(clock_surf, (clock_x, clock_y))
        self.screen.blit(
            sec_surf,
            (clock_x + clock_surf.get_width() + clock_gap, clock_y + 28),
        )

        # Israeli holidays: today + next 3 days (top-right, top to bottom)
        holiday_days: list[HolidayDay] = self.holiday_guide.days()
        box_w: int = 200
        box_h: int = 40
        box_gap: int = 6
        box_x: int = width - box_w - 24
        box_y: int = 12
        for item in holiday_days:
            box: pygame.Rect = pygame.Rect(box_x, box_y, box_w, box_h)
            draw_frosted_rect(self.screen, box, 12, CARD_FROST)
            num_surf: pygame.Surface = render_text(self.font_body, item.day_num, TEXT)
            hol_surf: pygame.Surface = render_text(self.font_meta, item.holiday, MUTED)
            self.screen.blit(
                num_surf,
                (box.x + 12, box.centery - num_surf.get_height() // 2),
            )
            self.screen.blit(
                hol_surf,
                (box.x + 52, box.centery - hol_surf.get_height() // 2),
            )
            box_y += box_h + box_gap
        return header_h

    def draw_gauges(self, sections: dict[str, dict[str, str]], area: pygame.Rect) -> None:
        """Draw live sensors packed in order, with constant card size."""
        total_slots: int = max(1, len(self.gauges))
        # Card size is based on the full sensor list so it never resizes
        cols: int = 4
        rows: int = max(1, math.ceil(total_slots / cols))
        gap: int = 18
        cell_w: int = (area.width - gap * (cols - 1)) // cols
        cell_h: int = (area.height - gap * (rows - 1)) // rows

        active: list[GaugeSpec] = [
            spec for spec in self.gauges if gauge_has_data(spec, sections)
        ]
        if not active:
            empty: pygame.Surface = render_text(
                self.font_body,
                "No sensor readings yet",
                MUTED,
            )
            self.screen.blit(
                empty,
                (
                    area.centerx - empty.get_width() // 2,
                    area.centery - empty.get_height() // 2,
                ),
            )
            return

        for pack_idx, spec in enumerate(active):
            r: int = pack_idx // cols
            c: int = pack_idx % cols
            cell: pygame.Rect = pygame.Rect(
                area.x + c * (cell_w + gap),
                area.y + r * (cell_h + gap),
                cell_w,
                cell_h,
            )
            fields: dict[str, str] = sections.get(spec.section, {})
            value: float | None = parse_float(fields.get(spec.value_key))
            humid: float | None = (
                parse_float(fields.get(spec.humid_key)) if spec.humid_key else None
            )
            status: str | None = fields.get(spec.status_key) if spec.status_key else None
            if spec.color_mode == "pressure":
                accent: tuple[int, int, int] = pressure_to_color(value)
            else:
                accent = temp_to_color(value)
            draw_progress_ring(
                self.screen,
                cell,
                spec.title,
                value,
                spec.unit,
                spec.vmin,
                spec.vmax,
                self.font_title,
                self.font_ring,
                self.font_meta,
                accent,
                status=status,
                secondary=humid,
                value_decimals=spec.value_decimals,
            )

    def draw(self) -> None:
        with self.lock:
            snapshot: SensorState = SensorState(
                title=self.state.title,
                sections={k: dict(v) for k, v in self.state.sections.items()},
                last_update=self.state.last_update,
                frames=self.state.frames,
                connected=self.state.connected,
                port=self.state.port,
                raw_tail=list(self.state.raw_tail),
                error=self.state.error,
            )

        width: int = self.screen.get_width()
        height: int = self.screen.get_height()
        backdrop: pygame.Surface = self.daily_bg.get(width, height)
        set_sharp_background(backdrop)
        self.screen.blit(backdrop, (0, 0))

        top: int = self.draw_header(snapshot)
        margin: int = 28
        gap: int = 22

        content_top: int = top + 36
        left_w: int = int(width * 0.62) - margin - gap // 2
        right_w: int = width - left_w - margin * 2 - gap
        main_h: int = height - content_top - margin

        gauge_rect: pygame.Rect = pygame.Rect(margin, content_top, left_w, main_h)
        self.draw_gauges(snapshot.sections, gauge_rect)

        right_x: int = margin + left_w + gap
        map_h: int = int(main_h * 0.58)
        solar_h: int = main_h - map_h - gap
        map_rect: pygame.Rect = pygame.Rect(right_x, content_top, right_w, map_h)
        solar_rect: pygame.Rect = pygame.Rect(
            right_x,
            content_top + map_h + gap,
            right_w,
            solar_h,
        )

        solar: SolarInfo = compute_solar_info(snapshot.sections, snapshot.last_update)
        draw_location_card(
            self.screen,
            map_rect,
            snapshot.sections.get("GPS NEO-8M", {}),
            self.map_cache,
            self.font_title,
            self.font_body,
        )
        draw_solar_card(
            self.screen,
            solar_rect,
            solar,
            self.font_title,
            self.font_body,
            self.font_value,
        )

        if not snapshot.sections:
            msg: pygame.Surface = render_text(
                self.font_body,
                "Waiting for sensor data…",
                MUTED,
            )
            self.screen.blit(
                msg,
                (width // 2 - msg.get_width() // 2, height // 2),
            )

        pygame.display.flip()

    def run(self) -> None:
        while self.running:
            self.handle_events()
            self.draw()
            self.clock.tick(30)
        pygame.quit()


def build_arg_parser() -> argparse.ArgumentParser:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Modern smart-home dashboard for Raspberry Pi USB serial sensors",
    )
    parser.add_argument(
        "--port",
        default="",
        help="Serial device path (default: auto-detect)",
    )
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    parser.add_argument(
        "--demo",
        nargs="?",
        const=str(Path.home() / "serial_output.txt"),
        default=None,
        help="Replay a captured frame file instead of serial",
    )
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="Run in a window instead of fullscreen",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args: argparse.Namespace = build_arg_parser().parse_args(argv)
    demo_path: Path | None = Path(args.demo) if args.demo else None
    port: str = args.port
    if demo_path is None and not port:
        detected: str | None = auto_detect_port()
        if detected is None:
            print("No serial port found. Pass --port or use --demo.", file=sys.stderr)
            return 1
        port = detected

    state: SensorState = SensorState(port=port if demo_path is None else "DEMO")
    lock: threading.Lock = threading.Lock()
    reader: SerialReader = SerialReader(
        state=state,
        port=port,
        baud=args.baud,
        demo_path=demo_path,
        lock=lock,
    )
    reader.start()

    dash: HomeDashboard = HomeDashboard(
        state=state,
        lock=lock,
        fullscreen=not args.windowed,
    )
    try:
        dash.run()
    finally:
        reader.stop()
        reader.join(timeout=2.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
