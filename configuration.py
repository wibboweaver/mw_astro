"""Validated application settings with atomic, comment-preserving persistence."""
from dataclasses import dataclass, fields, replace
from datetime import date
from pathlib import Path
import fcntl
import json
import math
import os
import re
import tempfile
from zoneinfo import ZoneInfo

CONFIG_PATH = Path(__file__).with_name('config.toml')
VISIBILITY_MODES = ('During window', 'At start', 'Throughout window')
TARGET_SOURCES = ('Automatic catalogue', 'Custom CSV')
CATALOGUE_SCOPES = ('Named and Messier objects', 'All deep-sky objects')
IMAGE_FIELDS = ('Fit target', '0.5°', '1°', '2°', '5°')
SECTIONS = {
    'observatory': ('latitude_deg', 'longitude_deg', 'height_m', 'timezone', 'horizon_file'),
    'chart': ('evening_date', 'start_hour', 'start_minute', 'exposure_seconds', 'minimum_altitude_deg', 'duration_hours', 'step_minutes', 'visibility_mode'),
    'targets': ('target_source', 'catalogue_scope', 'catalogue_file'),
    'preview': ('show_preview', 'image_field'),
    'equipment': ('focal_length_mm', 'sensor_width_mm', 'sensor_height_mm', 'frame_rotation_deg', 'camera_width_px', 'camera_height_px'),
}


@dataclass(frozen=True)
class Settings:
    latitude_deg: float | None = None
    longitude_deg: float | None = None
    height_m: float = 0.0
    timezone: str = 'Europe/London'
    horizon_file: str = ''
    evening_date: str = ''
    start_hour: int = 18
    start_minute: int = 0
    exposure_seconds: float = 180.0
    minimum_altitude_deg: float = 40
    duration_hours: float = 12
    step_minutes: float = 10
    visibility_mode: str = 'During window'
    target_source: str = 'Automatic catalogue'
    catalogue_scope: str = 'Named and Messier objects'
    catalogue_file: str = 'targets.csv'
    show_preview: bool = True
    image_field: str = 'Fit target'
    focal_length_mm: float = 550.0
    sensor_width_mm: float = 23.5
    sensor_height_mm: float = 15.7
    frame_rotation_deg: float = 0.0
    camera_width_px: int = 6248
    camera_height_px: int = 4176

    def __post_init__(self):
        for name, lower, upper in (
            ('focal_length_mm', 20, 20000), ('sensor_width_mm', 0.1, 100),
            ('sensor_height_mm', 0.1, 100), ('frame_rotation_deg', 0, 360),
            ('latitude_deg', -90, 90), ('longitude_deg', -180, 180),
            ('height_m', -500, 10000), ('duration_hours', 0.1, 48),
            ('step_minutes', 1, 60), ('exposure_seconds', 0.1, 86400), ('minimum_altitude_deg', 0, 90),
        ):
            value = getattr(self, name)
            if value is None and name in ('latitude_deg', 'longitude_deg'):
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lower <= value <= upper:
                raise ValueError(f'Invalid {name}: expected {lower} to {upper}.')
        for name in ('camera_width_px', 'camera_height_px'):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 100000:
                raise ValueError(f'{name} must be an integer from 1 to 100000.')
        for name, maximum in (('start_hour', 23), ('start_minute', 59)):
            if type(getattr(self, name)) is not int or not 0 <= getattr(self, name) <= maximum:
                raise ValueError(f'{name} must be an integer from 0 to {maximum}.')
        for name, options in (('visibility_mode', VISIBILITY_MODES), ('target_source', TARGET_SOURCES),
                              ('catalogue_scope', CATALOGUE_SCOPES), ('image_field', IMAGE_FIELDS)):
            if getattr(self, name) not in options:
                raise ValueError(f'Invalid {name}.')
        if type(self.show_preview) is not bool:
            raise ValueError('show_preview must be true or false.')
        if not isinstance(self.evening_date, str):
            raise ValueError('evening_date must be an ISO date string.')
        if self.evening_date:
            date.fromisoformat(self.evening_date)
        for name in ('horizon_file', 'catalogue_file'):
            if not isinstance(getattr(self, name), str):
                raise ValueError(f'{name} must be a filename.')
        if self.horizon_file and (Path(self.horizon_file).name != self.horizon_file or Path(self.horizon_file).suffix != '.txt'):
            raise ValueError('horizon_file must be a .txt filename in locations/.')
        if not self.catalogue_file or Path(self.catalogue_file).is_absolute() or '..' in Path(self.catalogue_file).parts:
            raise ValueError('catalogue_file must be a project-relative path.')
        ZoneInfo(self.timezone)


def load_settings(path=None):
    import tomllib
    path = Path(path) if path is not None else CONFIG_PATH
    with path.open('rb') as handle:
        data = tomllib.load(handle)
    values = {}
    for section, names in SECTIONS.items():
        values.update({name: data.get(section, {})[name] for name in names if name in data.get(section, {})})
    return Settings(**values)


def _updated_text(text, settings, changed):
    """Update our scalar keys only; retain other sections, keys and comments."""
    lines = text.splitlines()
    for section, names in SECTIONS.items():
        for name in names:
            if name not in changed:
                continue
            value = getattr(settings, name)
            headers = [(i, re.fullmatch(r'\s*\[([^\[\]]+)\]\s*(?:#.*)?', line)) for i, line in enumerate(lines)]
            begin = next((i for i, m in headers if m and m[1] == section), None)
            if begin is None:
                if value is None:
                    continue
                lines.extend(['', f'[{section}]'])
                begin = len(lines)-1
            end = next((i for i in range(begin+1, len(lines)) if lines[i].lstrip().startswith('[')), len(lines))
            existing = next((i for i in range(begin+1,end) if re.match(r'^\s*'+re.escape(name)+r'\s*=', lines[i])), None)
            if value is None:
                if existing is not None:
                    lines.pop(existing)
                continue
            encoded = str(value).lower() if isinstance(value, bool) else json.dumps(value, ensure_ascii=False, allow_nan=False)
            assignment = f'{name} = {encoded}'
            if existing is not None:
                lines[existing] = assignment
            else:
                lines.insert(end, assignment)
    return '\n'.join(lines).rstrip()+'\n'


def _atomic_write(path, content):
    """Replace only after the complete file has been flushed successfully."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=f'.{path.name}.', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_settings_changes(path=None, **changes):
    """Merge changed fields with the latest file, leaving other sessions' edits intact."""
    path = Path(path) if path is not None else CONFIG_PATH
    unknown = set(changes) - {field.name for field in fields(Settings)}
    if unknown:
        raise ValueError(f'Unknown settings: {unknown}')
    with path.with_name(path.name+'.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = load_settings(path)
        updated = replace(current, **changes)
        text = _updated_text(path.read_text(encoding='utf-8'), updated, changes)
        if text != path.read_text(encoding='utf-8'):
            _atomic_write(path, text)
    return updated


def save_uploaded_catalogue(content, config_path=None):
    """Retain a validated upload so Custom CSV works after reopening the app."""
    from targets import parse_targets
    text = content.decode('utf-8-sig')
    parse_targets(text)
    path = Path(config_path) if config_path is not None else CONFIG_PATH
    destination = path.parent/'catalogues'/'last_upload.csv'
    destination.parent.mkdir(exist_ok=True)
    _atomic_write(destination, text)
    return save_settings_changes(path, catalogue_file='catalogues/last_upload.csv')

# Used by the app to refresh this module when Python sources change during a session.
_loaded_source_stamp = Path(__file__).stat().st_mtime_ns
