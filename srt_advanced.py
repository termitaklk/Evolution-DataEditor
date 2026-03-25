import tkinter as tk
from tkinter import filedialog
import sqlite3
import os
import re
import http.server
import socketserver
import threading
import webbrowser
import time
import json
import uuid
import urllib.parse
import requests
import random
import shutil
import sys
import queue
import zipfile
import html
import io
import difflib
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from deep_translator import GoogleTranslator
from editor_constants import load_editor_constants, DEFAULT_CONSTANTS_PATH
from openpyxl import Workbook
try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

# Cola para comunicación entre hilos (HTTP -> Principal)
DIALOG_QUEUE = queue.Queue()

GLOBAL_PROGRESS = {'total': 0, 'current': 0, 'last_file': ''}
CURRENT_LANG = 'es'
CURRENT_PICS_DIR = None
CONFIG_FILE = 'config_app.json'
TEMP_YPK_ROOT = 'temp_ypk'
TEMP_YPK_SOURCE_BY_PROFILE = {}
YUGIOH_DB_COMPARE_CACHE = {}
YUGIOH_DB_COMPARE_CACHE_FILE = 'ygo_compare_cache.json'
YUGIOH_DB_COMPARE_CACHE_VERSION = 2
YGO_COMPARE_DIFFS_FILE = 'ygo_compare_differences.json'
YGO_COMPARE_CARD_LIMIT = 50
YGO_CACHE_LOADED = False
YGO_CACHE_DIRTY_COUNT = 0
YGO_COMPARE_BATCH_SIZE = 20
YGO_COMPARE_BATCH_WAIT_SECONDS = 3.0
YGO_REQUEST_LOCK = threading.Lock()
YGO_LAST_REQUEST_TS = 0.0
YGO_COMPARE_JOBS = {}
YGO_COMPARE_JOBS_LOCK = threading.Lock()
LUA_FUNCTION_DOCS_FILES = [
    os.path.join('config', '_function_english.txt'),
    os.path.join('config', '_functions.txt'),
]
LUA_FUNCTION_DOCS_CACHE = {}
LUA_FUNCTION_DOCS_LOCK = threading.Lock()
DEBUG_LOG_FILE = 'logs.txt'

# Regex precompilados para acelerar análisis masivo de scripts.
RE_STRINGID_FULL = re.compile(r'aux\.Stringid\s*\(([^)]+)\)', re.DOTALL)
RE_ANY_NUMBER = re.compile(r'\b(\d+)\b')
RE_SETDESC_NUM = re.compile(r'SetDescription\s*\(\s*(\d{1,8})\s*\)', re.DOTALL)
RE_SETDESC_CONST = re.compile(r'SetDescription\s*\(\s*([A-Z0-9_]+)\s*\)', re.DOTALL)
RE_HINT = re.compile(r'Duel\.Hint\s*\(\s*([^,]+)\s*,\s*[^,]+\s*,\s*(\d+|[A-Z0-9_]+)\s*\)', re.DOTALL)
RE_SELECT_EFFECT_YESNO = re.compile(r'Duel\.SelectEffectYesNo\s*\(\s*[^,]+\s*,\s*[^,]+\s*,\s*(\d+|[A-Z0-9_]+)\s*\)', re.DOTALL)
RE_SELECT_YESNO = re.compile(r'Duel\.SelectYesNo\s*\(\s*[^,]+\s*,\s*(\d+|[A-Z0-9_]+)\s*\)', re.DOTALL)
RE_SELECT_OPTION = re.compile(r'Duel\.SelectOption\s*\(\s*[^,]+\s*,\s*((?:[^()]|\([^()]*\))*)\s*\)', re.DOTALL)
RE_NESTED_STRINGID = re.compile(r'aux\.Stringid\s*\(\s*(\d+|id|s|[A-Z0-9_]+)\s*,\s*(\d+)\s*\)', re.DOTALL)
RE_ITEM = re.compile(r'\b(\d+|[A-Z0-9_]+)\b')
RE_LUA_DOC_SIGNATURE = re.compile(r'^[^\w]*([A-Za-z0-9_\[\], ]+)\s+([A-Za-z_][A-Za-z0-9_:.]*)\s*\((.*)\)\s*$')

def translate_text(text, target_lang='es'):
    """
    e texto usando Google Translate (gratuito).
    Específico para Yu-Gi-Oh: mantiene nombres de cartas y términos técnicos en inglés cuando no hay traducción oficial.
    """
    if not text or not text.strip():
        return text
    
    try:
        # Usar deep-translator para compatibilidad
        translator = GoogleTranslator(source='auto', target=target_lang)
        translated_text = translator.translate(text)
        
        # Post-procesamiento para Yu-Gi-Oh: mantener términos técnicos en inglés
        # Esto es básico; se puede mejorar con una lista de términos conocidos
        ygo_terms = [
            'Monster', 'Spell', 'Trap', 'Effect', 'Fusion', 'Synchro', 'Xyz', 'Pendulum',
            'ATK', 'DEF', 'Level', 'Rank', 'Scale', 'Link', 'Attribute', 'Type',
            'Normal', 'Quick-Play', 'Continuous', 'Equip', 'Field', 'Ritual',
            'Flip', 'Spirit', 'Union', 'Gemini', 'Tuner', 'Toon', 'Token'
        ]
        
        for term in ygo_terms:
            # Reemplazar traducciones comunes de vuelta al inglés
            if term.lower() in translated_text.lower():
                # Buscar variaciones en español y reemplazar
                spanish_variations = {
                    'monstruo': 'Monster',
                    'hechizo': 'Spell', 
                    'trampa': 'Trap',
                    'efecto': 'Effect',
                    'fusión': 'Fusion',
                    'sincro': 'Synchro',
                    'xyz': 'Xyz',
                    'péndulo': 'Pendulum',
                    'ataque': 'ATK',
                    'defensa': 'DEF',
                    'nivel': 'Level',
                    'rango': 'Rank',
                    'escala': 'Scale',
                    'enlace': 'Link',
                    'atributo': 'Attribute',
                    'tipo': 'Type',
                    'normal': 'Normal',
                    'juego-rápido': 'Quick-Play',
                    'continuo': 'Continuous',
                    'equipo': 'Equip',
                    'campo': 'Field',
                    'ritual': 'Ritual',
                    'volteo': 'Flip',
                    'espíritu': 'Spirit',
                    'unión': 'Union',
                    'gemelo': 'Gemini',
                    'afinador': 'Tuner',
                    'dibujo': 'Toon',
                    'ficha': 'Token'
                }
                for sp, en in spanish_variations.items():
                    translated_text = re.sub(r'\b' + re.escape(sp) + r'\b', en, translated_text, flags=re.IGNORECASE)
        
        return translated_text
        
    except Exception as e:
        print(f"Error en traducción: {e}")
        return text  # Devolver original si falla

def build_filetypes_from_extensions(raw_exts: str):
    txt = str(raw_exts or '').strip()
    if not txt:
        return []
    exts = []
    for part in txt.split(','):
        ext = part.strip().lower()
        if not ext:
            continue
        if not ext.startswith('.'):
            ext = '.' + ext
        if not re.match(r'^\.[a-z0-9]+$', ext):
            continue
        if ext not in exts:
            exts.append(ext)
    if not exts:
        return []
    patterns = ' '.join(f'*{ext}' for ext in exts)
    label = ' / '.join(ext.upper() for ext in exts)
    return [(label, patterns)]

def normalize_ui_lang_code(code: str, profile_key: str = '') -> str:
    raw = str(code or '').strip().lower().replace('_', '-')
    if raw:
        if raw == 'cn':
            return 'zh-cn'
        if raw == 'kr':
            return 'ko-kr'
        return raw

    pk = str(profile_key or '').strip().lower()
    if pk == 'cn' or pk.startswith('zh'):
        return 'zh-cn'
    if pk == 'kr' or pk.startswith('ko'):
        return 'ko-kr'
    if pk.startswith('es'):
        return 'es'
    if pk.startswith('en'):
        return 'en'
    if pk.startswith('ja'):
        return 'ja'
    if pk.startswith('pt'):
        return 'pt'
    if pk.startswith('fr'):
        return 'fr'
    if pk.startswith('de') or pk == 'ge':
        return 'de'
    if pk.startswith('it'):
        return 'it'
    return 'en'

def normalize_config(config: dict) -> dict:
    """
    Backward-compatible normalization:
    - Old format: {cdb_dir, script_dir, strings_conf, pics_dir}
    - New format: {profiles: {lang: {...}}, active_profile: lang}
    """
    if not isinstance(config, dict):
        return {'profiles': {}, 'active_profile': 'es'}

    if isinstance(config.get('profiles'), dict):
        config.setdefault('active_profile', 'es')
        return config

    profiles = {}
    if any(k in config for k in ('cdb_dir', 'script_dir', 'strings_conf', 'pics_dir')):
        profiles['es'] = {
            'cdb_dir': config.get('cdb_dir', ''),
            'script_dir': config.get('script_dir', ''),
            'strings_conf': config.get('strings_conf', ''),
            'pics_dir': config.get('pics_dir', ''),
        }

    out = dict(config)
    out['profiles'] = profiles
    out.setdefault('active_profile', 'es')
    return out

def get_active_profile_paths(config: dict) -> dict:
    cfg = normalize_config(config)
    profiles = cfg.get('profiles') or {}
    active = cfg.get('active_profile') or 'es'
    has_active_profile = active in profiles
    if has_active_profile:
        # Si el perfil activo existe, respetarlo tal cual (aunque tenga rutas vacías).
        p = profiles.get(active) or {}
        return {
            'cdb_dir': p.get('cdb_dir', ''),
            'script_dir': p.get('script_dir', ''),
            'strings_conf': p.get('strings_conf', ''),
            'pics_dir': p.get('pics_dir', ''),
            'active_profile': active,
            'profiles': profiles,
        }

    # Fallbacks para compatibilidad: perfil ES o claves top-level (formato legado).
    p = profiles.get('es') or {}
    return {
        'cdb_dir': p.get('cdb_dir') or cfg.get('cdb_dir') or '',
        'script_dir': p.get('script_dir') or cfg.get('script_dir') or '',
        'strings_conf': p.get('strings_conf') or cfg.get('strings_conf') or '',
        'pics_dir': p.get('pics_dir') or cfg.get('pics_dir') or '',
        'active_profile': active,
        'profiles': profiles,
    }

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return normalize_config(json.load(f))
        except: pass
    return normalize_config({})

def detect_text_file_encoding(path: str) -> str:
    try:
        with open(path, 'rb') as f:
            raw = f.read(4)
        if raw.startswith(b'\xef\xbb\xbf'):
            return 'utf-8-sig'
        if raw.startswith(b'\xff\xfe'):
            return 'utf-16'
        if raw.startswith(b'\xfe\xff'):
            return 'utf-16'
    except Exception:
        pass

    for enc in ('utf-8', 'cp1252', 'latin-1'):
        try:
            with open(path, 'r', encoding=enc) as f:
                f.read()
            return enc
        except Exception:
            continue
    return 'utf-8'

def read_text_file(path: str) -> tuple[str, str]:
    encoding = detect_text_file_encoding(path)
    with open(path, 'r', encoding=encoding, errors='replace') as f:
        return f.read(), encoding

def write_text_file(path: str, content: str, encoding: str = 'utf-8'):
    with open(path, 'w', encoding=encoding, newline='') as f:
        f.write(str(content or ''))

def normalize_strings_conf_content(content: str) -> str:
    """
    En strings.conf, los nombres compuestos después del código deben usar NBSP
    en lugar de espacios normales para compatibilidad con algunos clientes.
    Ejemplo:
      !setname 0x2de Cantante Oscuro
    pasa a:
      !setname 0x2de Cantante\u00A0Oscuro
    """
    out_lines = []
    pattern = re.compile(r'^(\s*![^\s]+)(\s+)(\S+)(\s+)(.+)$')

    for line in str(content or '').splitlines(keepends=True):
        line_ending = ''
        body = line
        if body.endswith('\r\n'):
            body = body[:-2]
            line_ending = '\r\n'
        elif body.endswith('\n'):
            body = body[:-1]
            line_ending = '\n'

        m = pattern.match(body)
        if not m:
            out_lines.append(body + line_ending)
            continue

        head_1, sep_1, code_token, sep_2, label = m.groups()
        normalized_label = label.replace(' ', '\u00A0')
        out_lines.append(f'{head_1}{sep_1}{code_token}{sep_2}{normalized_label}{line_ending}')

    return ''.join(out_lines)

RE_SETNAME_LINE = re.compile(r'^\s*!setname\s+(\S+)\s+(.+?)\s*$')

def _format_setname_code(code: int) -> str:
    try:
        num = int(code)
    except Exception:
        return str(code)
    return str(num) if num < 0 else f'0x{num:x}'

def _resolve_editor_constants_path() -> str:
    candidate = str(DEFAULT_CONSTANTS_PATH or '').strip() or os.path.join('config', 'cardinfo_english.txt')
    if os.path.exists(candidate):
        return os.path.abspath(candidate)
    base_file = os.path.dirname(os.path.abspath(__file__))
    alt = os.path.join(base_file, candidate)
    if os.path.exists(alt):
        return os.path.abspath(alt)
    return os.path.abspath(candidate)

def _parse_setname_entries_from_text(content: str, source_kind: str = 'strings_conf') -> dict[int, str]:
    entries: dict[int, str] = {}
    lines = str(content or '').replace('\r\n', '\n').replace('\r', '\n').split('\n')
    if source_kind == 'constants_txt':
        in_setname = False
        for raw_line in lines:
            line = str(raw_line or '').strip()
            if not line:
                continue
            if line.lower().startswith('##'):
                in_setname = (line.lower() == '##setname')
                continue
            if not in_setname or line.startswith('#'):
                continue
            if '\t' in line:
                parts = line.split('\t')
            else:
                parts = re.split(r'\s+', line, maxsplit=1)
            if len(parts) < 2:
                continue
            try:
                code = int(parts[0], 16) if str(parts[0]).lower().startswith('0x') else int(parts[0])
            except Exception:
                continue
            name = ' '.join(str(p or '').strip() for p in parts[1:]).replace('\xa0', ' ').strip()
            if not name or code in entries:
                continue
            entries[code] = name
        return entries

    for raw_line in lines:
        match = RE_SETNAME_LINE.match(raw_line)
        if not match:
            continue
        try:
            code = int(match.group(1), 16) if match.group(1).lower().startswith('0x') else int(match.group(1))
        except Exception:
            continue
        name = str(match.group(2) or '').replace('\xa0', ' ').strip()
        if not name or code in entries:
            continue
        entries[code] = name
    return entries

def _format_setname_entries(entries: list[dict], target_kind: str = 'strings_conf', use_nbsp: bool = False) -> list[str]:
    lines: list[str] = []
    for entry in entries or []:
        try:
            code = int(entry.get('code'))
        except Exception:
            continue
        name = str(entry.get('name') or '').replace('\xa0', ' ').strip()
        if not name:
            continue
        label = name.replace(' ', '\xa0') if use_nbsp else name
        code_token = _format_setname_code(code)
        if target_kind == 'constants_txt':
            lines.append(f'{code_token}\t{label}')
        else:
            lines.append(f'!setname {code_token} {label}')
    return lines

def _append_setname_entries_to_content(content: str, entries: list[dict], target_kind: str) -> str:
    base_text = str(content or '')
    existing = _parse_setname_entries_from_text(base_text, target_kind)
    pending = []
    for entry in entries or []:
        try:
            code = int(entry.get('code'))
        except Exception:
            continue
        name = str(entry.get('name') or '').replace('\xa0', ' ').strip()
        if not name or code in existing:
            continue
        existing[code] = name
        pending.append({'code': code, 'name': name})
    if not pending:
        return base_text

    line_break = '\r\n' if '\r\n' in base_text else '\n'
    block_lines = _format_setname_entries(pending, target_kind=target_kind, use_nbsp=(target_kind == 'strings_conf'))
    if not block_lines:
        return base_text

    trimmed = base_text.rstrip('\r\n')
    if target_kind == 'constants_txt':
        lines = trimmed.splitlines() if trimmed else []
        insert_at = len(lines)
        found_section = False
        for idx, line in enumerate(lines):
            stripped = str(line or '').strip().lower()
            if stripped.startswith('##'):
                if stripped == '##setname':
                    found_section = True
                    insert_at = idx + 1
                    continue
                if found_section:
                    insert_at = idx
                    break
            if found_section and stripped == '#end':
                insert_at = idx
                break
            elif found_section:
                insert_at = idx + 1
        if not found_section:
            if lines and str(lines[-1]).strip():
                lines.append('')
            lines.append('##setname')
            insert_at = len(lines)
        lines[insert_at:insert_at] = block_lines
        merged = line_break.join(lines)
    else:
        parts = [trimmed] if trimmed else []
        parts.extend(block_lines)
        merged = line_break.join(parts)
    if base_text.endswith('\n') or not base_text:
        merged += line_break
    if target_kind == 'strings_conf':
        merged = normalize_strings_conf_content(merged)
    return merged

def _build_setname_sync_snapshot(strings_content: str, constants_content: str) -> dict:
    strings_entries = _parse_setname_entries_from_text(strings_content, 'strings_conf')
    constants_entries = _parse_setname_entries_from_text(constants_content, 'constants_txt')

    def to_list(source: dict[int, str]) -> list[dict]:
        return [
            {'code': code, 'code_hex': _format_setname_code(code), 'name': name}
            for code, name in sorted(source.items(), key=lambda item: (item[0], item[1].lower()))
        ]

    only_in_strings = [
        {'code': code, 'code_hex': _format_setname_code(code), 'name': name}
        for code, name in sorted(strings_entries.items(), key=lambda item: (item[0], item[1].lower()))
        if code not in constants_entries
    ]
    only_in_constants = [
        {'code': code, 'code_hex': _format_setname_code(code), 'name': name}
        for code, name in sorted(constants_entries.items(), key=lambda item: (item[0], item[1].lower()))
        if code not in strings_entries
    ]

    mismatches = []
    for code, strings_name in strings_entries.items():
        constants_name = constants_entries.get(code)
        if constants_name is not None and constants_name != strings_name:
            mismatches.append({
                'code': code,
                'code_hex': _format_setname_code(code),
                'strings_name': strings_name,
                'constants_name': constants_name,
            })

    return {
        'strings_entries': to_list(strings_entries),
        'constants_entries': to_list(constants_entries),
        'only_in_strings': only_in_strings,
        'only_in_constants': only_in_constants,
        'mismatches': sorted(mismatches, key=lambda item: (item['code'], item['strings_name'].lower())),
    }

def _build_setname_sync_snapshot_for_targets(strings_targets: list[dict], constants_content: str, scope: str = 'current') -> dict:
    constants_entries = _parse_setname_entries_from_text(constants_content, 'constants_txt')
    target_maps: list[tuple[str, str, dict[int, str]]] = []
    union_strings_entries: dict[int, str] = {}
    profile_order: list[str] = []

    for target in strings_targets or []:
        profile = str((target or {}).get('profile') or '').strip().lower()
        path = str((target or {}).get('path') or '').strip()
        content, _enc = read_text_file(path)
        parsed = _parse_setname_entries_from_text(content, 'strings_conf')
        target_maps.append((profile, path, parsed))
        if profile and profile not in profile_order:
            profile_order.append(profile)
        for code, name in parsed.items():
            if code not in union_strings_entries:
                union_strings_entries[code] = name

    if scope != 'all':
        strings_content = '\n'.join(_format_setname_entries(
            [{'code': code, 'name': name} for code, name in union_strings_entries.items()],
            target_kind='strings_conf',
            use_nbsp=False
        ))
        return _build_setname_sync_snapshot(strings_content, constants_content)

    def to_union_list(source: dict[int, str]) -> list[dict]:
        return [
            {'code': code, 'code_hex': _format_setname_code(code), 'name': name}
            for code, name in sorted(source.items(), key=lambda item: (item[0], item[1].lower()))
        ]

    only_in_strings = []
    for code, name in sorted(union_strings_entries.items(), key=lambda item: (item[0], item[1].lower())):
        if code not in constants_entries:
            present_in = [
                {'profile': profile, 'path': path}
                for profile, path, parsed in target_maps
                if code in parsed
            ]
            only_in_strings.append({
                'code': code,
                'code_hex': _format_setname_code(code),
                'name': name,
                'present_in_count': len(present_in),
                'present_in': present_in,
            })

    only_in_constants = []
    for code, name in sorted(constants_entries.items(), key=lambda item: (item[0], item[1].lower())):
        missing_in = [
            {'profile': profile, 'path': path}
            for profile, path, parsed in target_maps
            if code not in parsed
        ]
        if missing_in:
            only_in_constants.append({
                'code': code,
                'code_hex': _format_setname_code(code),
                'name': name,
                'missing_in_count': len(missing_in),
                'missing_in': missing_in,
            })

    mismatches = []
    for code, constants_name in constants_entries.items():
        differing = []
        for profile, path, parsed in target_maps:
            strings_name = parsed.get(code)
            if strings_name is not None and strings_name != constants_name:
                differing.append({
                    'profile': profile,
                    'path': path,
                    'strings_name': strings_name,
                })
        if differing:
            per_profile_names = {}
            for profile, _path, parsed in target_maps:
                per_profile_names[profile] = str(parsed.get(code) or '')
            mismatches.append({
                'code': code,
                'code_hex': _format_setname_code(code),
                'constants_name': constants_name,
                'strings_name': differing[0]['strings_name'],
                'different_in_count': len(differing),
                'different_in': differing,
                'per_profile_names': per_profile_names,
            })

    return {
        'profiles': profile_order,
        'strings_entries': to_union_list(union_strings_entries),
        'constants_entries': to_union_list(constants_entries),
        'only_in_strings': only_in_strings,
        'only_in_constants': only_in_constants,
        'mismatches': sorted(mismatches, key=lambda item: (item['code'], item['constants_name'].lower())),
    }

def _build_archetype_mismatch_workbook(mismatches: list[dict], profiles: list[str] | None = None, scope: str = 'current', active_profile: str = '') -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = 'Diferencias'
    profile_cols = [str(p or '').upper() for p in (profiles or []) if str(p or '').strip()]
    if not profile_cols and active_profile:
        profile_cols = [str(active_profile).upper()]
    ws.append(['Code', 'Config Name', *profile_cols, 'Tabs/Profiles', 'Count', 'Scope'])

    for item in mismatches or []:
        profiles = []
        if isinstance(item.get('different_in'), list) and item.get('different_in'):
            profiles = [str((entry or {}).get('profile') or '').upper() for entry in (item.get('different_in') or []) if str((entry or {}).get('profile') or '').strip()]
        elif active_profile:
            profiles = [str(active_profile).upper()]

        per_profile_names = item.get('per_profile_names') or {}
        profile_values = []
        for profile in profile_cols:
            raw_value = per_profile_names.get(str(profile).lower(), '')
            profile_values.append(str(raw_value or ''))

        ws.append([
            str(item.get('code_hex') or ''),
            str(item.get('constants_name') or ''),
            *profile_values,
            ', '.join(profiles),
            int(item.get('different_in_count') or (1 if profiles else 0)),
            str(scope or 'current'),
        ])

    for col_cells in ws.columns:
        max_len = 0
        col_letter = col_cells[0].column_letter
        for cell in col_cells:
            try:
                max_len = max(max_len, len(str(cell.value or '')))
            except Exception:
                continue
        ws.column_dimensions[col_letter].width = min(max(12, max_len + 2), 48)

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()

def _iter_cdb_files(cdb_root: str) -> list[str]:
    base = os.path.abspath(str(cdb_root or '').strip())
    if not base or not os.path.exists(base):
        return []
    if os.path.isfile(base):
        return [base] if base.lower().endswith('.cdb') else []
    cdb_files = []
    for dirpath, _, filenames in os.walk(base):
        for fn in filenames:
            if fn.lower().endswith('.cdb'):
                cdb_files.append(os.path.join(dirpath, fn))
    return sorted(set(cdb_files), key=lambda p: (0 if os.path.basename(p).lower() == 'cards.cdb' else 1, p.lower()))

def _extract_setcodes16(value) -> list[int]:
    try:
        tmp = int(value or 0)
    except Exception:
        return []
    found = []
    while tmp:
        part = int(tmp & 0xffff)
        if part and part not in found:
            found.append(part)
        tmp >>= 16
    return found

def _collect_language_cdb_targets(config: dict) -> list[dict]:
    cfg = normalize_config(config or {})
    profiles = cfg.get('profiles') or {}
    targets = []
    seen_profiles = set()

    def add_target(profile_key: str, cdb_dir: str):
        key = str(profile_key or '').strip().lower()
        path = os.path.abspath(str(cdb_dir or '').strip()) if str(cdb_dir or '').strip() else ''
        if not key or not path or not os.path.exists(path) or key in seen_profiles:
            return
        cdb_files = _iter_cdb_files(path)
        if not cdb_files:
            return
        seen_profiles.add(key)
        targets.append({
            'profile': key,
            'path': path,
            'cdb_files': cdb_files,
        })

    if profiles:
        for key in sorted(profiles.keys()):
            profile = profiles.get(key) or {}
            if profile.get('is_temp_ypk'):
                continue
            add_target(key, profile.get('cdb_dir'))
    else:
        active = get_active_profile_paths(cfg)
        add_target(active.get('active_profile') or 'es', active.get('cdb_dir') or '')

    return targets

def _scan_unknown_archetypes_from_cdb_targets(cdb_targets: list[dict], constants_content: str) -> dict:
    constants_entries = _parse_setname_entries_from_text(constants_content, 'constants_txt')
    known_codes = set(constants_entries.keys())
    unknown = {}
    scanned_profiles = set()
    failed_profiles = {}

    for target in cdb_targets:
        profile_key = str(target.get('profile') or '').strip().lower()
        for cdb_file in target.get('cdb_files') or []:
            conn = None
            try:
                conn = sqlite3.connect(cdb_file)
                cursor = conn.cursor()
                cursor.execute('SELECT setcode FROM datas WHERE setcode IS NOT NULL AND setcode != 0')
                scanned_profiles.add(profile_key)
                for (raw_setcode,) in cursor.fetchall():
                    for code in _extract_setcodes16(raw_setcode):
                        if code <= 0 or code in known_codes:
                            continue
                        item = unknown.setdefault(code, {
                            'code': code,
                            'code_hex': _format_setname_code(code),
                            'profiles': set(),
                            'profile_counts': {},
                            'occurrences': 0,
                        })
                        item['profiles'].add(profile_key)
                        item['profile_counts'][profile_key] = int(item['profile_counts'].get(profile_key, 0) or 0) + 1
                        item['occurrences'] = int(item.get('occurrences', 0) or 0) + 1
            except Exception as ex:
                print(f'Error scanning archetypes in {cdb_file}: {ex}')
                failed_profiles.setdefault(profile_key, []).append({
                    'path': str(cdb_file or ''),
                    'error': str(ex or ''),
                })
            finally:
                try:
                    if conn:
                        conn.close()
                except Exception:
                    pass

    candidates = []
    for code in sorted(unknown.keys()):
        item = unknown[code]
        profiles = sorted([str(p or '').upper() for p in item.get('profiles') or [] if str(p or '').strip()])
        profile_counts = {
            str(profile or '').lower(): int(count or 0)
            for profile, count in (item.get('profile_counts') or {}).items()
            if str(profile or '').strip()
        }
        candidates.append({
            'code': code,
            'code_hex': _format_setname_code(code),
            'profiles': profiles,
            'profile_counts': profile_counts,
            'occurrences': int(item.get('occurrences', 0) or 0),
        })

    return {
        'candidates': candidates,
        'profiles': [str(target.get('profile') or '').upper() for target in cdb_targets if str(target.get('profile') or '').strip()],
        'cdb_paths': [str(target.get('path') or '') for target in cdb_targets if str(target.get('path') or '').strip()],
        'scanned_profiles': sorted([str(profile or '').upper() for profile in scanned_profiles if str(profile or '').strip()]),
        'failed_profiles': {
            str(profile or '').upper(): errors
            for profile, errors in failed_profiles.items()
            if str(profile or '').strip()
        },
    }

def _sanitize_ypk_filename(name: str) -> str:
    base = os.path.basename(str(name or '').strip())
    base = re.sub(r'[<>:"/\\|?*]+', '_', base)
    if not base:
        base = 'custom.ypk'
    if not base.lower().endswith('.ypk'):
        base += '.ypk'
    return base

def _sanitize_cdb_filename(name: str, index: int) -> str:
    base = os.path.basename(str(name or '').strip())
    base = re.sub(r'[<>:"/\\|?*]+', '_', base)
    if not base:
        base = f'cards_{index}.cdb'
    if not base.lower().endswith('.cdb'):
        base += '.cdb'
    return base

def _find_named_resource_near_paths(start_paths: list[str], resource_name: str, is_dir: bool = False, max_levels: int = 6) -> str:
    checked = set()
    for raw_path in start_paths or []:
        src = str(raw_path or '').strip()
        if not src:
            continue
        current = os.path.abspath(src)
        if os.path.isfile(current):
            current = os.path.dirname(current)
        for _ in range(max_levels + 1):
            candidate = os.path.join(current, resource_name)
            if candidate not in checked:
                checked.add(candidate)
                if is_dir and os.path.isdir(candidate):
                    return candidate
                if not is_dir and os.path.isfile(candidate):
                    return candidate
            parent = os.path.dirname(current)
            if not parent or parent == current:
                break
            current = parent
    return ''

def _get_table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    cur = conn.cursor()
    cur.execute(f'PRAGMA table_info({table_name})')
    return [str(row[1]) for row in cur.fetchall() if len(row) > 1]

def _load_card_rows_from_source_cdbs(card_ids: list[int], cdb_files: list[str]) -> dict:
    wanted = [int(x) for x in card_ids if int(x) > 0]
    if not wanted:
        return {'template_cdb': '', 'datas_columns': [], 'texts_columns': [], 'datas_rows': {}, 'texts_rows': {}, 'missing_ids': []}

    template_cdb = str((cdb_files or [''])[0] or '')
    datas_rows = {}
    texts_rows = {}
    datas_columns = []
    texts_columns = []
    chunk_size = 400

    for cdb_file in cdb_files or []:
        conn = None
        try:
            conn = sqlite3.connect(cdb_file)
            if not datas_columns:
                datas_columns = _get_table_columns(conn, 'datas')
            if not texts_columns:
                texts_columns = _get_table_columns(conn, 'texts')
            remaining = [card_id for card_id in wanted if card_id not in datas_rows or card_id not in texts_rows]
            if not remaining:
                break
            for start in range(0, len(remaining), chunk_size):
                batch = remaining[start:start + chunk_size]
                placeholders = ','.join('?' for _ in batch)
                cur = conn.cursor()
                cur.execute(f'SELECT * FROM datas WHERE id IN ({placeholders})', batch)
                for row in cur.fetchall():
                    datas_rows[int(row[0])] = tuple(row)
                cur.execute(f'SELECT * FROM texts WHERE id IN ({placeholders})', batch)
                for row in cur.fetchall():
                    texts_rows[int(row[0])] = tuple(row)
        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

    missing_ids = [card_id for card_id in wanted if card_id not in datas_rows or card_id not in texts_rows]
    return {
        'template_cdb': template_cdb,
        'datas_columns': datas_columns,
        'texts_columns': texts_columns,
        'datas_rows': datas_rows,
        'texts_rows': texts_rows,
        'missing_ids': missing_ids,
    }

def _build_subset_cdb(template_cdb: str, output_cdb: str, card_ids: list[int], source_rows: dict) -> list[int]:
    shutil.copy2(template_cdb, output_cdb)
    conn = sqlite3.connect(output_cdb)
    try:
        cur = conn.cursor()
        cur.execute('DELETE FROM datas')
        cur.execute('DELETE FROM texts')
        datas_columns = source_rows.get('datas_columns') or []
        texts_columns = source_rows.get('texts_columns') or []
        datas_rows = source_rows.get('datas_rows') or {}
        texts_rows = source_rows.get('texts_rows') or {}
        datas_insert = f"INSERT OR REPLACE INTO datas ({', '.join(datas_columns)}) VALUES ({', '.join('?' for _ in datas_columns)})"
        texts_insert = f"INSERT OR REPLACE INTO texts ({', '.join(texts_columns)}) VALUES ({', '.join('?' for _ in texts_columns)})"
        inserted = []
        for card_id in card_ids:
            data_row = datas_rows.get(int(card_id))
            text_row = texts_rows.get(int(card_id))
            if not data_row or not text_row:
                continue
            cur.execute(datas_insert, data_row)
            cur.execute(texts_insert, text_row)
            inserted.append(int(card_id))
        conn.commit()
        return inserted
    finally:
        conn.close()

def _create_ypk_package(params: dict) -> dict:
    config = load_config()
    config = normalize_config(config)
    requested_profile = str(params.get('active_profile') or config.get('active_profile') or 'es').strip().lower()
    if requested_profile:
        config['active_profile'] = requested_profile
    active_paths = get_active_profile_paths(config)
    cdb_root = str(active_paths.get('cdb_dir') or '').strip()
    script_dir = str(active_paths.get('script_dir') or '').strip()
    pics_dir = str(active_paths.get('pics_dir') or '').strip()
    if not cdb_root or not os.path.exists(cdb_root):
        raise Exception('CDB path not configured')

    output_dir = os.path.abspath(str(params.get('output_dir') or '').strip())
    if not output_dir:
        raise Exception('Output folder is required')
    os.makedirs(output_dir, exist_ok=True)
    output_name = _sanitize_ypk_filename(params.get('output_name') or 'custom.ypk')
    output_path = os.path.join(output_dir, output_name)

    include_script = bool(params.get('include_script'))
    include_pics = bool(params.get('include_pics'))
    include_pack = bool(params.get('include_pack'))
    include_lflist = bool(params.get('include_lflist'))
    dry_run = bool(params.get('dry_run'))
    custom_lflist = os.path.abspath(str(params.get('lflist_path') or '').strip()) if str(params.get('lflist_path') or '').strip() else ''
    cdb_defs = params.get('cdb_files') or []
    if not isinstance(cdb_defs, list) or not cdb_defs:
        raise Exception('At least one CDB definition is required')

    normalized_cdb_defs = []
    all_ids = set()
    for idx, item in enumerate(cdb_defs, start=1):
        ids = []
        for raw in (item.get('ids') or []):
            try:
                num = int(str(raw or '').strip())
            except Exception:
                continue
            if num > 0:
                ids.append(num)
        ids = list(dict.fromkeys(ids))
        if not ids:
            raise Exception(f'CDB #{idx} has no valid card IDs')
        filename = _sanitize_cdb_filename(item.get('name') or '', idx)
        normalized_cdb_defs.append({'name': filename, 'ids': ids})
        all_ids.update(ids)

    source_cdb_files = _iter_cdb_files(cdb_root)
    if not source_cdb_files:
        raise Exception('No source CDB files found')
    source_rows = _load_card_rows_from_source_cdbs(sorted(all_ids), source_cdb_files)
    if not source_rows.get('template_cdb'):
        raise Exception('No source CDB template available')

    start_paths = [cdb_root, script_dir, pics_dir]
    pack_dir = _find_named_resource_near_paths(start_paths, 'pack', is_dir=True) if include_pack else ''
    if include_lflist and custom_lflist and os.path.isfile(custom_lflist):
        lflist_path = custom_lflist
    else:
        lflist_path = _find_named_resource_near_paths(start_paths, 'lflist.conf', is_dir=False) if include_lflist else ''

    missing_scripts = []
    missing_pics = []
    created_cdbs = []

    for cdb_def in normalized_cdb_defs:
        available = [int(card_id) for card_id in cdb_def['ids'] if int(card_id) in (source_rows.get('datas_rows') or {}) and int(card_id) in (source_rows.get('texts_rows') or {})]
        created_cdbs.append({
            'name': cdb_def['name'],
            'requested': len(cdb_def['ids']),
            'inserted': len(available),
        })

    if include_script:
        for card_id in sorted(all_ids):
            src = find_script_file(script_dir, int(card_id)) if script_dir and os.path.exists(script_dir) else ''
            if not (src and os.path.exists(src)):
                missing_scripts.append(int(card_id))

    if include_pics:
        for card_id in sorted(all_ids):
            src = find_picture_file(pics_dir, f'{int(card_id)}.jpg') if pics_dir and os.path.exists(pics_dir) else ''
            if not (src and os.path.exists(src)):
                missing_pics.append(int(card_id))

    if not dry_run:
        with tempfile.TemporaryDirectory(prefix='ypk_build_') as temp_root:
            for cdb_def in normalized_cdb_defs:
                output_cdb = os.path.join(temp_root, cdb_def['name'])
                _build_subset_cdb(source_rows['template_cdb'], output_cdb, cdb_def['ids'], source_rows)

            if include_script and script_dir and os.path.exists(script_dir):
                script_out = os.path.join(temp_root, 'script')
                os.makedirs(script_out, exist_ok=True)
                for card_id in sorted(all_ids):
                    src = find_script_file(script_dir, int(card_id))
                    if src and os.path.exists(src):
                        shutil.copy2(src, os.path.join(script_out, os.path.basename(src)))

            if include_pics and pics_dir and os.path.exists(pics_dir):
                pics_out = os.path.join(temp_root, 'pics')
                os.makedirs(pics_out, exist_ok=True)
                for card_id in sorted(all_ids):
                    src = find_picture_file(pics_dir, f'{int(card_id)}.jpg')
                    if src and os.path.exists(src):
                        shutil.copy2(src, os.path.join(pics_out, os.path.basename(src)))

            if include_pack and pack_dir and os.path.isdir(pack_dir):
                shutil.copytree(pack_dir, os.path.join(temp_root, 'pack'), dirs_exist_ok=True)

            if include_lflist and lflist_path and os.path.isfile(lflist_path):
                shutil.copy2(lflist_path, os.path.join(temp_root, 'lflist.conf'))

            tmp_out = output_path + '.tmp'
            with zipfile.ZipFile(tmp_out, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                for dirpath, _, filenames in os.walk(temp_root):
                    for fn in filenames:
                        full = os.path.join(dirpath, fn)
                        rel = os.path.relpath(full, temp_root).replace('\\', '/')
                        zf.write(full, rel)
            os.replace(tmp_out, output_path)

    return {
        'output_path': output_path,
        'active_profile': requested_profile,
        'dry_run': dry_run,
        'created_cdbs': created_cdbs,
        'missing_card_ids': source_rows.get('missing_ids') or [],
        'missing_scripts': missing_scripts,
        'missing_pics': missing_pics,
        'included_pack': bool(include_pack and pack_dir and os.path.isdir(pack_dir)),
        'included_lflist': bool(include_lflist and lflist_path and os.path.isfile(lflist_path)),
        'pack_path': pack_dir,
        'lflist_path': lflist_path,
    }

def _collect_strings_conf_targets(config: dict, requested_profile: str = '', scope: str = 'current', allowed_profiles: list[str] | None = None) -> tuple[list[dict], str]:
    cfg = normalize_config(config)
    profiles = cfg.get('profiles') or {}
    active_profile = str(requested_profile or cfg.get('active_profile') or 'es').strip().lower() or 'es'
    out: list[dict] = []
    seen_paths: set[str] = set()
    allowed = {str(x or '').strip().lower() for x in (allowed_profiles or []) if str(x or '').strip()}

    def add_target(profile_key: str, path_value: str):
        if allowed and profile_key not in allowed:
            return
        path = str(path_value or '').strip()
        if not path or not os.path.exists(path):
            return
        norm = os.path.abspath(path)
        if norm in seen_paths:
            return
        seen_paths.add(norm)
        out.append({'profile': profile_key, 'path': norm})

    if scope == 'all':
        for key, profile in profiles.items():
            add_target(str(key or '').strip().lower(), (profile or {}).get('strings_conf'))
        if not out:
            active_paths = get_active_profile_paths(cfg)
            add_target(active_profile, active_paths.get('strings_conf'))
    else:
        active_paths = get_active_profile_paths({**cfg, 'active_profile': active_profile})
        add_target(active_profile, active_paths.get('strings_conf'))

    return out, active_profile

def read_text_preview(path: str, max_bytes: int = 262144) -> str:
    try:
        with open(path, 'rb') as f:
            raw = f.read(max_bytes)
    except Exception:
        return ''

    for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1', 'utf-16'):
        try:
            return raw.decode(enc, errors='ignore')
        except Exception:
            continue
    return ''

def score_system_strings_candidate(path: str) -> tuple | None:
    try:
        if not path or not os.path.isfile(path):
            return None
        if os.path.getsize(path) > 5 * 1024 * 1024:
            return None
    except Exception:
        return None

    filename = os.path.basename(path).lower()
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ('.conf', '.cfg', '.ini', '.txt', '.strings', '.lst', ''):
        return None

    preview = read_text_preview(path)
    if not preview:
        return None

    lowered = preview.lower()
    has_system = '!system' in lowered
    has_setname = '!setname' in lowered
    has_counter = '!counter' in lowered
    if not (has_system or has_setname or has_counter):
        return None

    # Priorizar contenido válido antes que el nombre, porque en YPK el archivo
    # puede no llamarse exactamente "strings.conf".
    name_rank = 3
    if filename == 'strings.conf':
        name_rank = 0
    elif 'strings' in filename:
        name_rank = 1
    elif 'string' in filename:
        name_rank = 2

    content_rank = 0 if has_system else (1 if has_setname else 2)
    return (content_rank, name_rank, len(filename), path.count(os.sep), path.lower())

def resolve_system_strings_path(path: str, *search_roots: str) -> str:
    preferred = str(path or '').strip()
    candidate_roots = []

    if preferred:
        if os.path.isfile(preferred):
            return preferred
        parent = os.path.dirname(preferred)
        if parent:
            candidate_roots.append(parent)

    for root in search_roots:
        root = str(root or '').strip()
        if not root:
            continue
        if os.path.isfile(root):
            scored = score_system_strings_candidate(root)
            if scored is not None:
                return root
            root = os.path.dirname(root)
        if root:
            candidate_roots.append(root)

    seen = set()
    scored_candidates = []
    for root in candidate_roots:
        try:
            abs_root = os.path.abspath(root)
        except Exception:
            abs_root = root
        if not abs_root or abs_root in seen or not os.path.exists(abs_root):
            continue
        seen.add(abs_root)
        for dirpath, _, filenames in os.walk(abs_root):
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                scored = score_system_strings_candidate(full)
                if scored is not None:
                    scored_candidates.append((scored, full))

    if not scored_candidates:
        return preferred

    scored_candidates.sort(key=lambda item: item[0])
    return scored_candidates[0][1]

def load_lua_function_docs(path: str):
    with LUA_FUNCTION_DOCS_LOCK:
        key = str(path or '').strip()
        if key in LUA_FUNCTION_DOCS_CACHE:
            return LUA_FUNCTION_DOCS_CACHE[key]

        docs = []
        if not key or not os.path.exists(key):
            LUA_FUNCTION_DOCS_CACHE[key] = docs
            return docs

        try:
            content, _encoding = read_text_file(key)
        except Exception:
            LUA_FUNCTION_DOCS_CACHE[key] = docs
            return docs

        current = None
        for raw_line in str(content or '').splitlines():
            line = str(raw_line or '').replace('\ufeff', '').strip()
            if not line:
                continue
            if line.startswith('#') or line.startswith('=========='):
                continue

            m = RE_LUA_DOC_SIGNATURE.match(line.lstrip('●').strip())
            if m:
                if current:
                    current['description'] = '\n'.join(current['description_lines']).strip()
                    current.pop('description_lines', None)
                    docs.append(current)
                return_type = str(m.group(1) or '').strip()
                name = str(m.group(2) or '').strip()
                args = str(m.group(3) or '').strip()
                current = {
                    'name': name,
                    'signature': f'{return_type} {name}({args})'.strip(),
                    'description_lines': [],
                    'source_path': key,
                }
                continue

            if current:
                current['description_lines'].append(line)

        if current:
            current['description'] = '\n'.join(current['description_lines']).strip()
            current.pop('description_lines', None)
            docs.append(current)

        LUA_FUNCTION_DOCS_CACHE[key] = docs
        return docs

def find_lua_function_doc_matches(query: str, limit: int = 8):
    token = str(query or '').strip()
    if not token:
        return []

    token_lower = token.lower()
    token_bare = token_lower.split(':')[-1].split('.')[-1]
    candidates = [str(p or '').strip() for p in LUA_FUNCTION_DOCS_FILES if str(p or '').strip()]

    for path in candidates:
        docs = load_lua_function_docs(path)
        if not docs:
            continue

        exact_full = [
            d for d in docs
            if str(d.get('name') or '').strip().lower() == token_lower
        ]
        if exact_full:
            return exact_full[:limit]

        exact_bare = []
        for doc in docs:
            name_lower = str(doc.get('name') or '').strip().lower()
            if not name_lower:
                continue
            name_bare = name_lower.split(':')[-1].split('.')[-1]
            if name_bare == token_bare:
                exact_bare.append(doc)

        if exact_bare:
            return exact_bare[:limit]

    return []

def append_debug_log(payload):
    try:
        entry = {
            'ts': int(time.time()),
            'payload': payload if isinstance(payload, dict) else {'value': payload}
        }
        with open(DEBUG_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass

def normalize_compare_text(value: str) -> str:
    txt = html.unescape(str(value or ''))
    txt = txt.replace('\xa0', ' ')
    txt = txt.replace('\u3000', ' ')
    txt = txt.replace('／', '/')
    txt = txt.replace('“', '"').replace('”', '"').replace('’', "'").replace('‘', "'")
    txt = txt.replace('\r\n', '\n').replace('\r', '\n')
    txt = re.sub(r'[ \t]+', ' ', txt)
    txt = re.sub(r' *\n *', '\n', txt)
    txt = re.sub(r'\n{3,}', '\n\n', txt)
    return txt.strip()

def normalize_compare_name(value: str) -> str:
    txt = normalize_compare_text(value).lower()
    txt = re.sub(r'[^a-z0-9áéíóúüñçàèìòùäëïöüß/\-+&\'" ]+', ' ', txt, flags=re.IGNORECASE)
    txt = re.sub(r'\s+', ' ', txt)
    return txt.strip()

def normalize_compare_rule_name(value: str) -> str:
    txt = normalize_compare_text(value).upper().replace('FORMAT', '').strip()
    txt = re.sub(r'\s+', ' ', txt)
    return txt

def normalize_compare_desc_text(value: str) -> str:
    txt = normalize_compare_text(value)
    txt = re.sub(r'\s*\n\s*', ' ', txt)
    txt = re.sub(r'\s+', ' ', txt)
    return txt.strip()

def build_compare_field_diff(local_value: str, official_value: str) -> dict:
    local_text = str(local_value or '')
    official_text = str(official_value or '')
    diff_lines = list(difflib.unified_diff(
        local_text.splitlines(),
        official_text.splitlines(),
        fromfile='cdb',
        tofile='yugioh_db',
        lineterm=''
    ))
    return {
        'local': local_text,
        'official': official_text,
        'diff': diff_lines,
    }

def save_ygo_compare_differences(results: list[dict], request_locale: str, active_profile: str, processed: int, total: int):
    output_path = os.path.join(os.getcwd(), YGO_COMPARE_DIFFS_FILE)
    payload = {
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'active_profile': str(active_profile or '').lower(),
        'request_locale': str(request_locale or '').lower(),
        'processed': int(processed or 0),
        'total': int(total or 0),
        'items': results,
    }
    with open(output_path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return output_path

def strip_yugioh_db_text_label(value: str) -> str:
    txt = normalize_compare_text(value)
    prefixes = [
        'Card Text',
        'Pendulum Effect',
        'Texto de la Carta',
        'Texto de Carta',
        'Efecto de Péndulo',
        'Efecto Péndulo',
        'Texte de Carte',
        'Effet Pendule',
        'Kartentext',
        'Pendeleffekt',
        'Testo Carta',
        'Effetto Pendulum',
        'Texto do Card',
        'Efeito de Pêndulo',
    ]
    for prefix in prefixes:
        if txt.lower().startswith(prefix.lower()):
            return txt[len(prefix):].strip()
    return txt

def map_profile_to_yugioh_request_locale(profile_key: str, ui_lang: str = '') -> str:
    code = normalize_ui_lang_code(ui_lang, profile_key)
    code = str(code or '').lower()
    mapping = {
        'es': 'es',
        'en': 'en',
        'fr': 'fr',
        'de': 'de',
        'it': 'it',
        'pt': 'pt',
        'ja': 'ja',
        'ja-jp': 'ja',
        'ko': 'ko',
        'ko-kr': 'ko',
        'kr': 'ko',
        'cn': 'cn',
        'zh-cn': 'cn',
        'zh-tw': 'cn',
        'ae': 'ae',
    }
    return mapping.get(code, 'en')

def parse_yugioh_db_detail(detail_html: str) -> dict:
    raw = str(detail_html or '')
    official_name = ''
    if BeautifulSoup is not None:
        soup = BeautifulSoup(raw, 'html.parser')
        title_node = soup.find('meta', attrs={'name': 'title'}) or soup.find('meta', attrs={'property': 'og:title'})
        title_text = ''
        if title_node and title_node.get('content'):
            title_text = str(title_node.get('content') or '')
        elif soup.title:
            title_text = soup.title.get_text(' ', strip=True)
        if title_text:
            official_name = normalize_compare_text(title_text.split('|', 1)[0])
    if not official_name:
        title_match = re.search(r'<title>\s*(.*?)\s*\|', raw, re.IGNORECASE | re.DOTALL)
        if not title_match:
            title_match = re.search(r'<meta\s+name="title"\s+content="(.*?)\s*\|', raw, re.IGNORECASE | re.DOTALL)
        official_name = normalize_compare_text(title_match.group(1) if title_match else '')

    official_texts = []
    has_ocg = False
    has_tcg = False
    if BeautifulSoup is not None:
        soup = BeautifulSoup(raw, 'html.parser')
        for node in soup.select('.item_box_text'):
            plain = strip_yugioh_db_text_label(node.get_text(' ', strip=True))
            if plain:
                official_texts.append(plain)
        for box in soup.select('.item_box'):
            title_node = box.select_one('.item_box_title')
            value_node = box.select_one('.item_box_value')
            title = normalize_compare_text(title_node.get_text(' ', strip=True) if title_node else '').upper()
            value = normalize_compare_text(value_node.get_text(' ', strip=True) if value_node else '')
            if title == 'OCG' and value:
                has_ocg = True
            elif title == 'TCG' and value:
                has_tcg = True
    else:
        text_blocks = re.findall(r'<div class="item_box_text"[^>]*>(.*?)</div>', raw, re.IGNORECASE | re.DOTALL)
        for block in text_blocks:
            plain = strip_yugioh_db_text_label(re.sub(r'<[^>]+>', ' ', block))
            if plain:
                official_texts.append(plain)
        item_boxes = re.findall(
            r'<div class="item_box(?:\s+ocg)?">\s*<div class="item_box_title(?:\s+ocg)?">(.*?)</div>\s*<div class="item_box_value">(.*?)</div>\s*</div>',
            raw,
            re.IGNORECASE | re.DOTALL
        )
        for title_html, value_html in item_boxes:
            title = normalize_compare_text(re.sub(r'<[^>]+>', ' ', title_html)).upper()
            value = normalize_compare_text(re.sub(r'<[^>]+>', ' ', value_html))
            if title == 'OCG' and value:
                has_ocg = True
            elif title == 'TCG' and value:
                has_tcg = True

    official_desc = '\n\n'.join(official_texts).strip()

    if has_ocg and has_tcg:
        official_rule = 'OCG & TCG'
    elif has_ocg:
        official_rule = 'OCG'
    elif has_tcg:
        official_rule = 'TCG'
    else:
        official_rule = ''

    return {
        'name': official_name,
        'desc': official_desc,
        'rule': official_rule,
    }

def make_ygo_compare_cache_key(card_id: int | str, request_locale: str, local_name: str = '') -> str:
    cid = str(card_id or '').strip()
    locale = str(request_locale or 'en').strip().lower()
    name_key = normalize_compare_name(local_name)
    return f"{cid}|{locale}|{name_key}"

def ensure_ygo_compare_cache_loaded():
    global YGO_CACHE_LOADED
    if YGO_CACHE_LOADED:
        return
    cache_path = os.path.join(os.getcwd(), YUGIOH_DB_COMPARE_CACHE_FILE)
    loaded = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as fh:
                raw = json.load(fh)
            if isinstance(raw, dict):
                meta = raw.get('__meta__') if isinstance(raw.get('__meta__'), dict) else {}
                version = int(meta.get('version') or 0)
                if version == YUGIOH_DB_COMPARE_CACHE_VERSION:
                    loaded = {k: v for k, v in raw.items() if k != '__meta__'}
                else:
                    loaded = {}
        except Exception as exc:
            print(f"Could not load Yugioh DB cache: {exc}")
    YUGIOH_DB_COMPARE_CACHE.clear()
    YUGIOH_DB_COMPARE_CACHE.update(loaded)
    YGO_CACHE_LOADED = True

def flush_ygo_compare_cache(force: bool = False):
    global YGO_CACHE_DIRTY_COUNT
    if not YGO_CACHE_LOADED:
        return
    if not force and YGO_CACHE_DIRTY_COUNT < 10:
        return
    cache_path = os.path.join(os.getcwd(), YUGIOH_DB_COMPARE_CACHE_FILE)
    try:
        with open(cache_path, 'w', encoding='utf-8') as fh:
            json.dump({
                '__meta__': {
                    'version': YUGIOH_DB_COMPARE_CACHE_VERSION,
                },
                **YUGIOH_DB_COMPARE_CACHE,
            }, fh, ensure_ascii=False, indent=2)
        YGO_CACHE_DIRTY_COUNT = 0
    except Exception as exc:
        print(f"Could not save Yugioh DB cache: {exc}")

def set_ygo_compare_cache(cache_key: str, value):
    global YGO_CACHE_DIRTY_COUNT
    YUGIOH_DB_COMPARE_CACHE[cache_key] = value
    YGO_CACHE_DIRTY_COUNT += 1
    flush_ygo_compare_cache()

def ygo_db_get(session: requests.Session, url: str, timeout: int = 20):
    global YGO_LAST_REQUEST_TS
    sess = session or requests.Session()
    with YGO_REQUEST_LOCK:
        resp = sess.get(
            url,
            timeout=timeout,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9,es;q=0.8',
            }
        )
        YGO_LAST_REQUEST_TS = time.time()
        return resp

def resolve_yugioh_db_card_link_by_name(name: str, request_locale: str, session: requests.Session | None = None) -> str:
    wanted_name = normalize_compare_name(name)
    if not wanted_name:
        return ''
    sess = session or requests.Session()
    search_url = (
        "https://www.db.yugioh-card.com/yugiohdb/card_search.action?"
        + urllib.parse.urlencode({
            'ope': 1,
            'sess': 1,
            'rp': 10,
            'sort': 1,
            'keyword': str(name or ''),
            'stype': 1,
            'ctype': '',
            'othercon': 2,
            'request_locale': request_locale,
        })
    )
    resp = ygo_db_get(sess, search_url, timeout=20)
    if resp.status_code == 403:
        return '__blocked__'
    search_html = resp.text
    for block in re.findall(r'<div class="t_row c_normal open">(.*?)</div><!-- \.t_row c_normal -->', search_html, re.IGNORECASE | re.DOTALL):
        name_match = re.search(r'class="cnm"\s+value=[\'"]([^\'"]+)[\'"]', block, re.IGNORECASE)
        link_match = re.search(r'class="link_value"\s+value=[\'"]([^\'"]+)[\'"]', block, re.IGNORECASE)
        if not name_match or not link_match:
            continue
        result_name = normalize_compare_name(name_match.group(1))
        if result_name != wanted_name:
            continue
        result_link = html.unescape(link_match.group(1)).strip()
        if not result_link:
            continue
        full_link = urllib.parse.urljoin('https://www.db.yugioh-card.com', result_link)
        if 'request_locale=' not in full_link:
            full_link += ('&' if '?' in full_link else '?') + f"request_locale={urllib.parse.quote(request_locale)}"
        return full_link
    return ''

def search_yugioh_db_card(card_id: int | str, request_locale: str, local_name: str = '', session: requests.Session | None = None, allow_name_fallback: bool = False) -> dict | None:
    ensure_ygo_compare_cache_loaded()
    cid = str(card_id or '').strip()
    cache_key = make_ygo_compare_cache_key(cid, request_locale, local_name)
    if cache_key in YUGIOH_DB_COMPARE_CACHE:
        return YUGIOH_DB_COMPARE_CACHE.get(cache_key)

    sess = session or requests.Session()
    parsed = None
    detail_url = ''

    if cid and re.fullmatch(r'\d+', cid):
        detail_url = (
            "https://www.db.yugioh-card.com/yugiohdb/card_search.action?"
            + urllib.parse.urlencode({
                'ope': 2,
                'cid': cid,
                'request_locale': request_locale,
            })
        )
    if not detail_url:
        if not allow_name_fallback:
            set_ygo_compare_cache(cache_key, None)
            return None
    else:
        detail_resp = ygo_db_get(sess, detail_url, timeout=20)
        if detail_resp.status_code == 403:
            blocked = {'blocked': True, 'link': detail_url, 'cid': cid, 'resolved_by': 'cid'}
            set_ygo_compare_cache(cache_key, blocked)
            return blocked
        detail_html = detail_resp.text
        parsed = parse_yugioh_db_detail(detail_html)
        if parsed and (parsed.get('name') or parsed.get('desc') or parsed.get('rule')):
            parsed['link'] = detail_url
            parsed['cid'] = cid
            parsed['resolved_by'] = 'cid'
            set_ygo_compare_cache(cache_key, parsed)
            return parsed

    if not allow_name_fallback:
        set_ygo_compare_cache(cache_key, None)
        return None

    fallback_link = resolve_yugioh_db_card_link_by_name(local_name, request_locale, session=sess)
    if fallback_link == '__blocked__':
        blocked = {'blocked': True, 'link': '', 'cid': '', 'resolved_by': 'name'}
        set_ygo_compare_cache(cache_key, blocked)
        return blocked
    if not fallback_link:
        set_ygo_compare_cache(cache_key, None)
        return None

    fallback_resp = ygo_db_get(sess, fallback_link, timeout=20)
    if fallback_resp.status_code == 403:
        blocked = {'blocked': True, 'link': fallback_link, 'cid': '', 'resolved_by': 'name'}
        set_ygo_compare_cache(cache_key, blocked)
        return blocked
    detail_html = fallback_resp.text
    parsed = parse_yugioh_db_detail(detail_html)
    if not parsed.get('name') and not parsed.get('desc') and not parsed.get('rule'):
        set_ygo_compare_cache(cache_key, None)
        return None
    cid_match = re.search(r'[?&]cid=(\d+)', fallback_link, re.IGNORECASE)
    parsed['cid'] = cid_match.group(1) if cid_match else ''
    parsed['resolved_by'] = 'name'
    detail_url = fallback_link
    parsed['link'] = detail_url
    set_ygo_compare_cache(cache_key, parsed)
    return parsed

def compare_cards_with_yugioh_db(cards: list[dict], request_locale: str, progress_callback=None) -> dict:
    results = []
    if not cards:
        return {'results': results, 'aborted': False, 'processed': 0, 'reason': ''}

    def compare_one(card: dict) -> dict | None:
        local_name = normalize_compare_text(card.get('name') or '')
        local_rule_raw = card.get('ot_name') or card.get('rule_name') or ''
        result = {
            'id': card.get('id'),
            'name': card.get('name') or '',
            'has_changes': False,
            'changed_fields': [],
            'status': 'pending',
            'local': {
                'name': card.get('name') or '',
                'desc': card.get('desc') or '',
                'rule': local_rule_raw,
            },
            'official': {
                'name': '',
                'desc': '',
                'rule': '',
                'link': '',
                'cid': '',
                'resolved_by': '',
            }
        }
        if not local_name:
            result['status'] = 'local_name_empty'
            return result
        session = requests.Session()
        try:
            official = search_yugioh_db_card(
                '',
                request_locale,
                local_name=local_name,
                session=session,
                allow_name_fallback=True
            )
        finally:
            session.close()
        if not official:
            result['status'] = 'not_found'
            return result
        if official.get('blocked'):
            result['status'] = 'search_blocked'
            result['official'] = {
                'name': '',
                'desc': '',
                'rule': '',
                'link': official.get('link') or '',
                'cid': official.get('cid') or '',
                'resolved_by': official.get('resolved_by') or '',
            }
            return result

        local_desc = normalize_compare_desc_text(card.get('desc') or '')
        official_desc = normalize_compare_desc_text(official.get('desc') or '')
        local_rule = normalize_compare_rule_name(local_rule_raw)
        official_rule = normalize_compare_rule_name(official.get('rule') or '')
        result['official'] = {
            'name': official.get('name') or '',
            'desc': official.get('desc') or '',
            'rule': official.get('rule') or '',
            'link': official.get('link') or '',
            'cid': official.get('cid') or '',
            'resolved_by': official.get('resolved_by') or '',
        }

        changed_fields = []
        if normalize_compare_name(local_name) != normalize_compare_name(official.get('name') or ''):
            changed_fields.append('name')
        if local_desc != official_desc and official_desc:
            changed_fields.append('desc')
        if local_rule and official_rule and local_rule != official_rule:
            changed_fields.append('rule')

        result['has_changes'] = bool(changed_fields)
        result['changed_fields'] = changed_fields
        result['status'] = 'changed' if changed_fields else 'matched'
        if changed_fields:
            result['field_diffs'] = {}
            if 'name' in changed_fields:
                result['field_diffs']['name'] = build_compare_field_diff(card.get('name') or '', official.get('name') or '')
            if 'desc' in changed_fields:
                result['field_diffs']['desc'] = build_compare_field_diff(card.get('desc') or '', official.get('desc') or '')
            if 'rule' in changed_fields:
                result['field_diffs']['rule'] = build_compare_field_diff(local_rule_raw, official.get('rule') or '')
        return result

    total_cards = len(cards)
    processed = 0
    aborted = False
    abort_reason = ''
    batch_size = max(1, int(YGO_COMPARE_BATCH_SIZE or 10))
    batch_wait = max(0.0, float(YGO_COMPARE_BATCH_WAIT_SECONDS or 0.0))

    for batch_start in range(0, total_cards, batch_size):
        batch_cards = cards[batch_start:batch_start + batch_size]
        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            future_map = {executor.submit(compare_one, card): card for card in batch_cards}
            for fut in as_completed(future_map):
                try:
                    item = fut.result()
                except Exception as exc:
                    print(f"Yugioh DB compare error: {exc}")
                    item = None
                processed += 1
                if item and item.get('has_changes'):
                    results.append(item)
                if callable(progress_callback):
                    try:
                        progress_callback({
                            'processed': processed,
                            'total': total_cards,
                            'remaining': max(total_cards - processed, 0),
                            'found': len(results),
                            'last_item': item,
                        })
                    except Exception:
                        pass
                if item and str(item.get('status') or '') == 'search_blocked':
                    aborted = True
                    abort_reason = 'Yugioh DB bloqueo las consultas; el proceso se detuvo para evitar mas intentos.'
                    for future in future_map:
                        future.cancel()
                    break
        if aborted:
            break
        if batch_wait > 0 and processed < total_cards:
            time.sleep(batch_wait)

    results.sort(key=lambda x: int(x.get('id') or 0))
    flush_ygo_compare_cache(force=True)
    return {'results': results, 'aborted': aborted, 'processed': processed, 'reason': abort_reason}

def _set_ygo_compare_job_state(job_id: str, **updates):
    with YGO_COMPARE_JOBS_LOCK:
        job = YGO_COMPARE_JOBS.get(job_id) or {}
        job.update(updates)
        YGO_COMPARE_JOBS[job_id] = job
        return dict(job)

def start_ygo_compare_job(cards: list[dict], request_locale: str, active_profile: str) -> str:
    job_id = str(uuid.uuid4())
    card_names = [f"{int(card.get('id') or 0)} - {str(card.get('name') or '').strip()}" for card in cards]
    _set_ygo_compare_job_state(
        job_id,
        status='running',
        active_profile=str(active_profile or '').lower(),
        request_locale=str(request_locale or 'en').lower(),
        total=len(cards),
        processed=0,
        remaining=len(cards),
        found=0,
        results=[],
        logs=[f"Iniciando comparación Yugioh DB para {len(cards)} cartas..."],
        pending=card_names[:200],
        current='',
        last_compare={},
        error='',
        diffs_file='',
    )

    def worker():
        try:
            def on_progress(info: dict):
                processed = int(info.get('processed') or 0)
                total = int(info.get('total') or 0)
                remaining = int(info.get('remaining') or 0)
                found = int(info.get('found') or 0)
                last_item = info.get('last_item') or None
                current_text = ''
                logs = []
                if last_item:
                    current_text = f"{int(last_item.get('id') or 0)} - {str(last_item.get('name') or '').strip()}"
                    changed = ', '.join(last_item.get('changed_fields') or [])
                    status = str(last_item.get('status') or '')
                    if last_item.get('has_changes'):
                        logs.append(f"[{processed}/{total}] Cambio detectado en {current_text} ({changed})")
                    elif status == 'search_blocked':
                        logs.append(f"[{processed}/{total}] Yugioh DB bloqueó la verificación de {current_text}")
                    elif status == 'not_found':
                        logs.append(f"[{processed}/{total}] No encontrada en Yugioh DB: {current_text}")
                    elif status == 'local_name_empty':
                        logs.append(f"[{processed}/{total}] Sin nombre local para comparar: {current_text}")
                    else:
                        logs.append(f"[{processed}/{total}] Sin cambios en {current_text}")
                else:
                    current_text = f"Procesadas {processed} de {total}"
                    logs.append(f"[{processed}/{total}] Sin cambios en la última carta procesada")
                with YGO_COMPARE_JOBS_LOCK:
                    job = YGO_COMPARE_JOBS.get(job_id) or {}
                    existing_logs = list(job.get('logs') or [])
                    existing_logs.extend(logs)
                    existing_results = list(job.get('results') or [])
                    if last_item and last_item.get('has_changes'):
                        last_id = str(last_item.get('id') or '')
                        existing_results = [item for item in existing_results if str(item.get('id') or '') != last_id]
                        existing_results.append(last_item)
                    job['processed'] = processed
                    job['total'] = total
                    job['remaining'] = remaining
                    job['found'] = found
                    job['current'] = current_text
                    job['last_compare'] = last_item or {}
                    job['results'] = existing_results
                    job['logs'] = existing_logs[-200:]
                    pending_names = card_names[processed:processed + 200]
                    job['pending'] = pending_names
                    YGO_COMPARE_JOBS[job_id] = job

            compare_result = compare_cards_with_yugioh_db(cards, request_locale, progress_callback=on_progress)
            results = list(compare_result.get('results') or [])
            processed_count = int(compare_result.get('processed') or 0)
            aborted = bool(compare_result.get('aborted'))
            abort_reason = str(compare_result.get('reason') or '').strip()
            final_logs = list((YGO_COMPARE_JOBS.get(job_id) or {}).get('logs') or [])
            if aborted and abort_reason:
                final_logs.append(abort_reason)
            final_logs.append(f"Comparaci?n completada. {len(results)} cartas con cambios.")
            diffs_file = save_ygo_compare_differences(
                results,
                request_locale=request_locale,
                active_profile=active_profile,
                processed=processed_count if aborted else len(cards),
                total=len(cards),
            )
            _set_ygo_compare_job_state(
                job_id,
                status='done',
                processed=processed_count if aborted else len(cards),
                remaining=max(len(cards) - processed_count, 0) if aborted else 0,
                found=len(results),
                current='Detenido para evitar bloqueo adicional.' if aborted else '',
                results=results,
                diffs_file=diffs_file,
                logs=final_logs[-200:],
                pending=card_names[processed_count:processed_count + 200] if aborted else [],
            )
        except Exception as exc:
            _set_ygo_compare_job_state(
                job_id,
                status='error',
                error=str(exc),
                current='',
                logs=(list((YGO_COMPARE_JOBS.get(job_id) or {}).get('logs') or []) + [f"Error: {exc}"])[-200:],
            )

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return job_id

def _find_best_dir_by_predicate(root_dir: str, predicate):
    best_dir = ''
    best_count = 0
    for dirpath, _, filenames in os.walk(root_dir):
        try:
            count = sum(1 for fn in filenames if predicate(dirpath, fn))
        except Exception:
            count = 0
        if count > best_count:
            best_count = count
            best_dir = dirpath
    return best_dir, best_count

def extract_ypk_to_profile(ypk_path: str, profile_key: str):
    if not ypk_path or not os.path.exists(ypk_path):
        raise FileNotFoundError('YPK file does not exist')

    profile = str(profile_key or 'es').strip().lower()
    target_dir = os.path.join(os.getcwd(), TEMP_YPK_ROOT, profile)
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir, ignore_errors=True)
    os.makedirs(target_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(ypk_path, 'r') as zf:
            zf.extractall(target_dir)
    except zipfile.BadZipFile:
        raise ValueError('Invalid YPK format (not a ZIP-compatible archive)')

    cdb_dir, cdb_count = _find_best_dir_by_predicate(
        target_dir,
        lambda _dp, fn: fn.lower().endswith('.cdb')
    )
    script_dir, script_count = _find_best_dir_by_predicate(
        target_dir,
        lambda _dp, fn: re.match(r'^c\d+\.lua$', fn.lower()) is not None
    )
    pics_dir, pics_count = _find_best_dir_by_predicate(
        target_dir,
        lambda _dp, fn: fn.lower().endswith(('.jpg', '.jpeg', '.png'))
    )

    strings_conf = resolve_system_strings_path('', target_dir)

    return {
        'profile': profile,
        'root_dir': target_dir,
        'cdb_dir': cdb_dir if cdb_count > 0 else '',
        'script_dir': script_dir if script_count > 0 else '',
        'pics_dir': pics_dir if pics_count > 0 else '',
        'strings_conf': strings_conf,
        'cdb_count': int(cdb_count or 0),
        'script_count': int(script_count or 0),
        'pics_count': int(pics_count or 0),
    }

def find_picture_file(pics_dir: str, filename: str) -> str:
    if not pics_dir:
        return ''
    direct = os.path.join(pics_dir, filename)
    if os.path.exists(direct):
        return direct

    base = os.path.splitext(filename)[0]
    exts = ('.jpg', '.png', '.jpeg', '.JPG', '.PNG', '.JPEG')
    for ext in exts:
        candidate = os.path.join(pics_dir, base + ext)
        if os.path.exists(candidate):
            return candidate

    # Fallback recursivo: algunos paquetes guardan imágenes en subcarpetas.
    targets = {f"{base}.jpg", f"{base}.png", f"{base}.jpeg"}
    targets_upper = {t.upper() for t in targets}
    for dirpath, _, filenames in os.walk(pics_dir):
        for fn in filenames:
            low = fn.lower()
            if low in targets or fn.upper() in targets_upper:
                return os.path.join(dirpath, fn)
    return ''

def find_script_file(script_dir: str, card_id: int) -> str:
    if not script_dir:
        return ''
    target = f'c{int(card_id)}.lua'
    direct = os.path.join(script_dir, target)
    if os.path.exists(direct):
        return direct
    for dirpath, _, filenames in os.walk(script_dir):
        for fn in filenames:
            if fn.lower() == target.lower():
                return os.path.join(dirpath, fn)
    return direct

def next_temp_ypk_profile_key(config: dict) -> str:
    cfg = normalize_config(config or {})
    profiles = cfg.get('profiles') or {}
    idx = 1
    while True:
        key = f'ypk-{idx}'
        if key not in profiles:
            return key
        idx += 1

def apply_ypk_load_to_config(params: dict):
    ypk_path = (params.get('ypk_path') or '').strip()
    if not ypk_path:
        raise ValueError('Missing ypk_path')

    cfg = load_config()
    cfg = normalize_config(cfg)

    requested_profile = str(params.get('profile_key') or '').strip().lower()
    if requested_profile and requested_profile not in (cfg.get('profiles') or {}):
        requested_profile = ''
    target_profile = requested_profile or next_temp_ypk_profile_key(cfg)

    extracted = extract_ypk_to_profile(ypk_path, target_profile)

    cfg.setdefault('profiles', {})
    cfg['profiles'].setdefault(target_profile, {})
    source_profile = str(params.get('active_profile') or '').strip().lower()
    if source_profile == target_profile:
        source_profile = ''
    cfg['profiles'][target_profile].update({
        'cdb_dir': extracted.get('cdb_dir') or '',
        'script_dir': extracted.get('script_dir') or '',
        'strings_conf': extracted.get('strings_conf') or '',
        'pics_dir': extracted.get('pics_dir') or '',
        'ui_lang': str(params.get('ui_lang') or '').strip().lower() or str(cfg['profiles'][target_profile].get('ui_lang') or ''),
        'is_temp_ypk': True,
        'ypk_file': os.path.basename(ypk_path),
        'ypk_source_path': os.path.abspath(ypk_path),
        'base_profile': source_profile,
    })
    TEMP_YPK_SOURCE_BY_PROFILE[target_profile] = os.path.abspath(ypk_path)
    cfg['active_profile'] = target_profile
    save_config(cfg)
    return extracted, cfg

def sync_temp_profile_to_ypk(cfg: dict, profile_key: str) -> bool:
    config = normalize_config(cfg or {})
    pk = str(profile_key or '').strip().lower()
    prof = (config.get('profiles') or {}).get(pk) or {}
    if not prof or not bool(prof.get('is_temp_ypk')):
        return False

    ypk_path = str(prof.get('ypk_source_path') or '').strip()
    if not ypk_path:
        ypk_path = str(TEMP_YPK_SOURCE_BY_PROFILE.get(pk) or '').strip()
    if not ypk_path:
        fallback_top = str(config.get('ypk_path') or '').strip()
        if fallback_top and os.path.exists(fallback_top):
            ypk_path = os.path.abspath(fallback_top)
    if not ypk_path:
        ypk_file = str(prof.get('ypk_file') or '').strip()
        downloads_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
        candidate = os.path.join(downloads_dir, ypk_file) if ypk_file else ''
        if candidate and os.path.exists(candidate):
            ypk_path = os.path.abspath(candidate)
    if not ypk_path:
        return False

    try:
        config.setdefault('profiles', {})
        config['profiles'].setdefault(pk, {})
        config['profiles'][pk]['ypk_source_path'] = ypk_path
        TEMP_YPK_SOURCE_BY_PROFILE[pk] = ypk_path
        save_config(config)
    except Exception:
        pass

    root_dir = os.path.join(os.getcwd(), TEMP_YPK_ROOT, pk)
    if not os.path.exists(root_dir):
        raise FileNotFoundError('Temporary YPK profile folder not found')

    tmp_out = ypk_path + '.tmp'
    with zipfile.ZipFile(tmp_out, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _, filenames in os.walk(root_dir):
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root_dir).replace('\\', '/')
                zf.write(full, rel)
    os.replace(tmp_out, ypk_path)
    return True

def save_config(config):
    try:
        current = load_config()
        # If we receive profiles, persist them as-is and also keep top-level keys in sync
        if isinstance(config, dict) and isinstance(config.get('profiles'), dict):
            normalized_profiles = {}
            for key, incoming_profile in (config.get('profiles') or {}).items():
                profile_key = str(key or '').strip().lower()
                if not profile_key:
                    continue
                existing_profile = dict(((current.get('profiles') or {}).get(profile_key) or {}))
                existing_profile.update(incoming_profile or {})
                normalized_profiles[profile_key] = existing_profile
            current['profiles'] = normalized_profiles
            current['active_profile'] = config.get('active_profile') or current.get('active_profile') or 'es'
            active_paths = get_active_profile_paths(current)
            current['cdb_dir'] = active_paths.get('cdb_dir', '')
            current['script_dir'] = active_paths.get('script_dir', '')
            current['strings_conf'] = active_paths.get('strings_conf', '')
            current['pics_dir'] = active_paths.get('pics_dir', '')
        else:
            current.update(config)
            # Keep normalized wrapper
            current = normalize_config(current)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(current, f, indent=4)
        return True
    except: return False

# Cargar configuración inicial
INITIAL_CONFIG = load_config()
try:
    for _k, _p in (INITIAL_CONFIG.get('profiles') or {}).items():
        if bool((_p or {}).get('is_temp_ypk')) and (_p or {}).get('ypk_source_path'):
            TEMP_YPK_SOURCE_BY_PROFILE[str(_k).lower()] = os.path.abspath(str((_p or {}).get('ypk_source_path')))
except Exception:
    pass
CURRENT_PICS_DIR = get_active_profile_paths(INITIAL_CONFIG).get('pics_dir')

def resource_path(relative_path):
    """ Obtiene la ruta absoluta para recursos, compatible con PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- CONFIGURACIÓN I18N ---
I18N = {
    'es': {
        'placeholder_empty': '[VACÍO]',
        'placeholder_no_sys': '[No encontrado en strings.conf]',
        'placeholder_range': '[Índice fuera de rango]',
        'anomaly_type_invalid': 'ID Inválido',
        'anomaly_type_orphan': 'CDB Huérfano',
        'anomaly_desc_invalid': "El script usa {ref} pero no tiene texto asociado.",
        'script_no_effects': 'No se detectaron referencias de texto en el script.',
        'title_select_folder': 'Seleccionar Carpeta',
        'title_select_file': 'Seleccionar Archivo',
        'title_cdb': 'Seleccionar Carpeta de los archivos .CDB',
        'title_scripts': 'Seleccionar Carpeta de los Scripts (c*.lua)',
        'title_strings': 'Seleccionar Archivo de Sistema (strings.conf)',
        'title_vars': 'Seleccionar Carpeta de Variables (all .lua)',
        'stat_no_script': 'Scripts Faltantes',
        'tab_no_script': 'Scripts Faltantes',
        'stat_excluded': 'Cartas Excluidas',
        'tab_excluded': 'Cartas Excluidas',
        'col_reason': 'Motivo Exclusión',
    },
    'en': {
        'placeholder_empty': '[EMPTY]',
        'placeholder_no_sys': '[Not found in strings.conf]',
        'placeholder_range': '[Index out of range]',
        'anomaly_type_invalid': 'Invalid ID',
        'anomaly_type_orphan': 'Orphan CDB',
        'anomaly_desc_invalid': "The script uses {ref} but has no associated text.",
        'anomaly_desc_orphan': "The card has text in str{idx} but the script does not use it.",
        'pred_no_effects': 'No effects detected in description.',
        'script_no_effects': 'No text references detected in script.',
        'title_select_folder': 'Select Folder',
        'title_select_file': 'Select File',
        'title_cdb': 'Select .CDB Database Folder',
        'title_scripts': 'Select Scripts Folder (c*.lua)',
        'title_strings': 'Select System File (strings.conf)',
        'title_vars': 'Select Variables Folder (all .lua)',
        'stat_no_script': 'Missing Scripts',
        'tab_no_script': 'Missing Scripts',
        'stat_excluded': 'Excluded Cards',
        'tab_excluded': 'Excluded Cards',
        'col_reason': 'Exclusion Reason',
    }
}
CURRENT_LANG = 'es' # Por defecto

def t(key, **kwargs):
    text = I18N[CURRENT_LANG].get(key, key)
    return text.format(**kwargs)

# --- PRE-CARGA DE LUA ---
def load_lua_constants(script_dir):
    constants = {}
    if not os.path.exists(script_dir): return constants
    
    # Archivos específicos donde se definen constantes globales
    target_files = ['constant.lua', 'procedure.lua', 'utility.lua']
    pattern = re.compile(r'^([A-Z0-9_]+)\s*=\s*(0x[0-9a-fA-F]+|[0-9\-]+)')
    
    for lua_file in target_files:
        path = os.path.join(script_dir, lua_file)
        if not os.path.exists(path): continue
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('--'): continue
                    match = pattern.match(line)
                    if match:
                        name, val_str = match.groups()
                        try:
                            val = int(val_str, 16) if val_str.startswith('0x') else int(val_str)
                            constants[name] = val
                        except: pass
        except Exception as e:
            print(f"Error cargando constantes de {lua_file}: {e}")
            
    return constants

def load_lua_procedures(script_dir, constants=None):
    procedures = {}
    if not os.path.exists(script_dir): return procedures
    
    target_files = ['procedure.lua', 'utility.lua', 'constant.lua']
    
    # Patrón para encontrar funciones de procedimiento y su SetDescription interno
    func_pattern = re.compile(r'function\s+(?:aux\.)?([A-Za-z0-9_]+)\s*\(.*?\)(.*?)end', re.DOTALL)
    desc_pattern = re.compile(r'SetDescription\s*\(\s*(\d+|[A-Z0-9_]+)\s*\)')
    
    # Pre-cargamos constantes para resolver nombres dentro de SetDescription
    constants = constants if isinstance(constants, dict) else load_lua_constants(script_dir)
    
    for lua_file in target_files:
        path = os.path.join(script_dir, lua_file)
        if not os.path.exists(path): continue
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                for func_match in func_pattern.finditer(content):
                    func_name, func_body = func_match.groups()
                    if "Procedure" in func_name or "DualAttribute" in func_name:
                        desc_match = desc_pattern.search(func_body)
                        if desc_match:
                            m = desc_match.group(1)
                            val = None
                            if m.isdigit(): val = int(m)
                            elif m in constants: val = constants[m]
                            
                            if val is not None:
                                procedures[func_name] = val
        except: pass
    
    # Si no se encontró nada (por seguridad), mantenemos el fallback mínimo
    if not procedures:
        procedures = {
            'AddSynchroProcedure': 1164, 'AddXyzProcedure': 1165, 'AddLinkProcedure': 1166,
            'AddFusionProcedure': 1169, 'AddRitualProcedure': 1168, 'EnableDualAttribute': 1150
        }
    return procedures

# --- LÓGICA DE PREVISIÓN DETALLADA ---
def predict_effects_detailed(description):
    if not description: return []
    text = description.replace('\r\n', ' ').replace('\n', ' ')
    if '●' in text:
        bullets = [b.strip() for b in text.split('●') if b.strip()]
        return [f"● {b}" for b in bullets]
    sentences = text.split('.')
    found_fragments = []
    for s in sentences:
        s = s.strip()
        if not s: continue
        if ':' in s or ';' in s or "Puedes Invocar de Modo Especial" in s or "Puedes Special Summon" in s:
            found_fragments.append(s)
    return found_fragments

# --- ANÁLISIS DE SCRIPT LUA ---
def analyze_script(script_path, card_id, lua_constants, lua_procedures):
    if not os.path.exists(script_path): return None
    with open(script_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    found_details = []
    # Capturar aux.Stringid con lógica profunda: busca todos los índices (0-15) dentro de los paréntesis.
    # Esto soporta expresiones como aux.Stringid(id, (p==tp and 2 or 3)) capturando el 2 y el 3.
    for match in RE_STRINGID_FULL.finditer(content):
        args_text = match.group(1)
        # Buscar todos los números independientes que parezcan índices (0-15)
        potential_indices = RE_ANY_NUMBER.findall(args_text)
        for num_str in potential_indices:
            num_val = int(num_str)
            # Un índice de string siempre es 0-15. Si es mayor, probablemente es un ID de carta.
            if 0 <= num_val <= 15:
                found_details.append({'type': 'CDB', 'id': num_val, 'code': match.group(0).strip()})

    for match in RE_SETDESC_NUM.finditer(content):
        m = match.group(1)
        if m.isdigit():
            found_details.append({'type': 'SYS', 'id': int(m), 'code': match.group(0).strip()})
    for match in RE_SETDESC_CONST.finditer(content):
        m = match.group(1)
        # Ignorar CARD_QUESTION (caso especial del cliente)
        if m == "CARD_QUESTION": continue
        val = lua_constants.get(m)
        if val is not None:
            found_details.append({'type': 'SYS', 'id': val, 'code': match.group(0).strip()})
    
    for match in RE_HINT.finditer(content):
        hint_type = match.group(1).strip()
        m = match.group(2).strip()
        
        # Ignorar HINT_CARD (7)
        if hint_type == "HINT_CARD" or hint_type == "7" or (hint_type in lua_constants and lua_constants[hint_type] == 7):
            continue
            
        # Ignorar HINT_SELECTMSG solo si el valor es 0 (Duel.Hint(HINT_SELECTMSG, tp, 0))
        # Si el valor es un ID (m != "0"), debe procesarse normalmente
        is_select_msg = hint_type == "HINT_SELECTMSG" or (hint_type in lua_constants and lua_constants[hint_type] == 17)
        if is_select_msg and m == "0":
            continue
            
        val = None
        if m.isdigit(): val = int(m)
        elif m in lua_constants: val = lua_constants[m]
        if val is not None:
            found_details.append({'type': 'SYS', 'id': val, 'code': match.group(0).strip()})
    
    # Duel.SelectYesNo(tp, desc) y Duel.SelectEffectYesNo(tp, handler, desc)
    # Buscamos el último argumento si es un número o constante
    for p_regex in (RE_SELECT_EFFECT_YESNO, RE_SELECT_YESNO):
        for match in p_regex.finditer(content):
            m = match.group(1)
            # Si m es parte de un aux.Stringid, ya se capturó arriba
            val = int(m) if m.isdigit() else lua_constants.get(m)
            if val is not None:
                found_details.append({'type': 'SYS', 'id': val, 'code': match.group(0).strip()})

    for match in RE_SELECT_OPTION.finditer(content):
        full_call = match.group(0).strip()
        arg_text = match.group(1)
        for ns_match in RE_NESTED_STRINGID.finditer(arg_text):
            found_details.append({'type': 'CDB', 'id': int(ns_match.group(2)), 'code': full_call})
        clean_args = RE_NESTED_STRINGID.sub(" ", arg_text)
        for item_match in RE_ITEM.finditer(clean_args):
            p = item_match.group(1)
            if p.lower() in ["id", "s", "tp", "p", "c", "e", "g", "h"]: continue 
            val = None
            if p.isdigit(): 
                num_val = int(p)
                if num_val < 100000: val = num_val
            elif p in lua_constants: val = lua_constants[p]
            if val is not None:
                found_details.append({'type': 'SYS', 'id': val, 'code': full_call})
    for proc, sys_id in lua_procedures.items():
        if proc in content:
            found_details.append({'type': 'SYS', 'id': sys_id, 'code': proc})
    return found_details

# --- CARGA DE STRINGS.CONF ---
def load_system_strings(path):
    sys_strings = {}
    resolved_path = resolve_system_strings_path(path, os.path.dirname(path) if path else '')
    if not resolved_path or not os.path.exists(resolved_path): return sys_strings
    content, _encoding = read_text_file(resolved_path)
    for raw_line in str(content or '').splitlines():
        line = str(raw_line or '').lstrip('\ufeff').strip()
        if line.startswith('!system'):
            parts = line.split(' ', 2)
            if len(parts) >= 3:
                try: sys_strings[int(parts[1])] = parts[2].strip()
                except: pass
    return sys_strings

def get_temp_profile_base_strings_conf(active_profile: str) -> str:
    profile_key = str(active_profile or '').strip().lower()
    if not profile_key:
        return ''

    config = load_config()
    profiles = config.get('profiles') or {}
    profile = profiles.get(profile_key) or {}
    if not bool(profile.get('is_temp_ypk')):
        return ''

    base_profile = str(profile.get('base_profile') or '').strip().lower()
    if base_profile and base_profile in profiles:
        base_prof = profiles.get(base_profile) or {}
        if not bool(base_prof.get('is_temp_ypk')):
            return str(base_prof.get('strings_conf') or '').strip()

    desired_ui_lang = normalize_ui_lang_code(str(profile.get('ui_lang') or '').strip().lower(), profile_key)
    for key, candidate in profiles.items():
        candidate_key = str(key or '').strip().lower()
        if candidate_key == profile_key or bool((candidate or {}).get('is_temp_ypk')):
            continue
        candidate_ui_lang = normalize_ui_lang_code(str((candidate or {}).get('ui_lang') or '').strip().lower(), candidate_key)
        if desired_ui_lang and candidate_ui_lang == desired_ui_lang:
            return str((candidate or {}).get('strings_conf') or '').strip()

    for fallback_key in ('en', 'es'):
        candidate = profiles.get(fallback_key) or {}
        if candidate and not bool(candidate.get('is_temp_ypk')):
            return str(candidate.get('strings_conf') or '').strip()
    return ''

# --- MOTOR DE ANÁLISIS ---
def run_analysis(cdb_dir, strings_conf, script_dir, active_profile=''):
    lua_constants = load_lua_constants(script_dir)
    lua_procedures = load_lua_procedures(script_dir, lua_constants)
    common_root = ''
    try:
        common_root = os.path.commonpath([p for p in [cdb_dir, script_dir, os.path.dirname(strings_conf or '')] if p])
    except Exception:
        common_root = ''
    resolved_strings_conf = resolve_system_strings_path(strings_conf, common_root, cdb_dir, script_dir)
    sys_strings = {}
    fallback_strings_conf = get_temp_profile_base_strings_conf(active_profile)
    resolved_fallback = resolve_system_strings_path(fallback_strings_conf, common_root, cdb_dir, script_dir)
    if resolved_fallback and resolved_fallback != resolved_strings_conf:
        sys_strings.update(load_system_strings(resolved_fallback))
    sys_strings.update(load_system_strings(resolved_strings_conf))
    
    results = {'coincidencias': [], 'anomalias': [], 'faltantes': [], 'scripts_faltantes': [], 'excluidas': []}
    
    if not os.path.exists(cdb_dir): return results
    cdb_files = [f for f in os.listdir(cdb_dir) if f.endswith('.cdb')]
    available_scripts = set()
    analyzed_script_cache = {}
    if os.path.exists(script_dir):
        try:
            for filename in os.listdir(script_dir):
                if not (filename.startswith('c') and filename.endswith('.lua')):
                    continue
                raw_id = filename[1:-4]
                if raw_id.isdigit():
                    available_scripts.add(int(raw_id))
        except Exception:
            available_scripts = set()
    
    for cdb_file in cdb_files:
        cdb_path = os.path.join(cdb_dir, cdb_file)
        conn = sqlite3.connect(cdb_path)
        cursor = conn.cursor()
        try:
            # JOIN con datas para excluir:
            # - Monstruos normales (cualquier variante con bit TYPE_NORMAL)
            # - Tokens (bit TYPE_TOKEN)
            # - Alias
            cursor.execute("""
                SELECT t.id, t.name, t.desc, 
                       t.str1, t.str2, t.str3, t.str4, t.str5, t.str6, t.str7, t.str8, 
                       t.str9, t.str10, t.str11, t.str12, t.str13, t.str14, t.str15, t.str16 
                FROM texts t
                JOIN datas d ON t.id = d.id
                WHERE d.alias = 0
                  AND (d.type & 0x4000) = 0
                  AND NOT ((d.type & 0x1) != 0 AND (d.type & 0x10) != 0)
            """)
            rows = cursor.fetchall()
            
            # Capturar las cartas excluidas para el reporte
            cursor.execute("""
                SELECT t.id, t.name, d.type, d.alias
                FROM texts t
                JOIN datas d ON t.id = d.id
                WHERE d.alias != 0
                   OR (d.type & 0x4000) != 0
                   OR ((d.type & 0x1) != 0 AND (d.type & 0x10) != 0)
            """)
            excl_rows = cursor.fetchall()
            for r in excl_rows:
                card_type = int(r[2] or 0)
                if (card_type & 0x4000) != 0:
                    reason = "Ficha/Token"
                elif (card_type & 0x1) != 0 and (card_type & 0x10) != 0:
                    reason = "Monstruo Normal"
                else:
                    reason = f"Alias de {r[3]}"
                results['excluidas'].append({
                    'id': r[0],
                    'name': r[1],
                    'reason': reason
                })
        except: continue

        for row in rows:
            card_id, name, desc, *cdb_strs = row
            pred_fragments = predict_effects_detailed(desc)
            script_full_path = os.path.join(script_dir, f"c{card_id}.lua")
            has_script = (card_id in available_scripts) if available_scripts else os.path.exists(script_full_path)

            # Verificar si el script existe antes de analizar
            if not has_script:
                info = {
                    'id': card_id, 'name': name, 'desc': desc,
                    'pred_count': len(pred_fragments),
                    'pred_texts': pred_fragments, 'script_count': 0,
                    'script_details': [], 'anomalies': []
                }
                for i, s in enumerate(cdb_strs):
                    info[f'str{i+1}'] = str(s) if s else ""
                results['scripts_faltantes'].append(info)
                continue

            if card_id in analyzed_script_cache:
                script_details = analyzed_script_cache[card_id]
            else:
                script_details = analyze_script(script_full_path, card_id, lua_constants, lua_procedures)
                if script_details is None: script_details = []
                analyzed_script_cache[card_id] = script_details
            
            final_details = []
            anomalies_found = []
            used_cdb_indices = set()
            
            for det in script_details:
                if det['type'] == 'CDB':
                    idx = det['id']
                    used_cdb_indices.add(idx)
                    txt = cdb_strs[idx] if idx < 16 else t('placeholder_range')
                else:
                    txt = sys_strings.get(det['id'], t('placeholder_no_sys'))
                
                det['text'] = txt or t('placeholder_empty')
                if det['text'] in [t('placeholder_empty'), t('placeholder_no_sys'), t('placeholder_range')]:
                    anomalies_found.append({
                        'tipo': 'anomaly_type_invalid',
                        'ref': f"{det['type']} {det['id']}",
                        'code': det['code'],
                        'desc': 'anomaly_desc_invalid'
                    })
                final_details.append(det)

            for i, txt in enumerate(cdb_strs):
                if txt and txt.strip() and i not in used_cdb_indices:
                    anomalies_found.append({
                        'tipo': 'anomaly_type_orphan',
                        'ref': f"CDB str{i+1}",
                        'desc': 'anomaly_desc_orphan',
                        'idx_num': i+1
                    })

            info = {
                'id': card_id, 'name': name, 'desc': desc,
                'pred_count': len(pred_fragments),
                'pred_texts': pred_fragments, 'script_count': len(final_details),
                'script_details': final_details, 'anomalies': anomalies_found
            }
            # Añadir str1-16 (como cadenas limpias)
            for i, s in enumerate(cdb_strs):
                info[f'str{i+1}'] = str(s) if s else ""
            
            if not anomalies_found: results['coincidencias'].append(info)
            else: results['anomalias'].append(info)
                
            has_missing = any(det['text'] in [t('placeholder_empty'), t('placeholder_no_sys'), t('placeholder_range')] for det in final_details)
            if has_missing: results['faltantes'].append(info)

        conn.close()
    
    results['i18n'] = I18N
    return results

# --- SERVIDOR API ---
class APIHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        global CURRENT_LANG, CURRENT_PICS_DIR
        parsed_path = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed_path.query)
        lang = query.get('lang', ['es'])[0]
        title_key = query.get('title_key', [None])[0]
        extensions = query.get('extensions', [''])[0]
        
        # Sincronizar idioma del backend con el del frontend para las utilidades t()
        if lang in I18N:
            CURRENT_LANG = lang

        if parsed_path.path == '/api/browse_folder' or parsed_path.path == '/api/browse_file':
            is_folder = parsed_path.path == '/api/browse_folder'
            
            # Enviar solicitud a la cola del hilo principal
            response_q = queue.Queue()
            DIALOG_QUEUE.put({
                'is_folder': is_folder,
                'lang': lang,
                'title_key': title_key,
                'filetypes': [] if is_folder else build_filetypes_from_extensions(extensions),
                'response_q': response_q
            })
            
            # Esperar el resultado del hilo principal
            path = response_q.get()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'path': path}).encode())
        elif parsed_path.path == '/api/progress':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(GLOBAL_PROGRESS).encode())
        elif parsed_path.path == '/index.html' or parsed_path.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            with open(resource_path('index.html'), 'rb') as f:
                self.wfile.write(f.read())
        elif parsed_path.path.startswith('/pics/'):
            # Servir imágenes de la carpeta PICs seleccionada (por perfil activo)
            requested_profile = (query.get('active_profile', [''])[0] or '').strip().lower()
            pics_dir = CURRENT_PICS_DIR
            if requested_profile:
                try:
                    cfg = load_config()
                    cfg = normalize_config(cfg)
                    cfg['active_profile'] = requested_profile
                    pics_dir = get_active_profile_paths(cfg).get('pics_dir') or pics_dir
                except Exception:
                    pass

            if pics_dir and os.path.exists(pics_dir):
                filename = parsed_path.path[6:] # Eliminar '/pics/'
                img_path = find_picture_file(pics_dir, filename)
                if img_path:
                    filename = os.path.basename(img_path)

                if os.path.exists(img_path):
                    self.send_response(200)
                    mime = 'image/png' if filename.lower().endswith('.png') else 'image/jpeg'
                    self.send_header('Content-type', mime)
                    self.end_headers()
                    with open(img_path, 'rb') as f:
                        self.wfile.write(f.read())
                else:
                    self.send_error(404)
        elif parsed_path.path == '/api/editor/load':
            config = load_config()
            requested_profile = (query.get('active_profile', [''])[0] or '').strip().lower()
            requested_target_cdb = (query.get('target_cdb_path', [''])[0] or '').strip()
            if requested_profile:
                config = normalize_config(config)
                config['active_profile'] = requested_profile
            active_paths = get_active_profile_paths(config)
            cdb_dir = active_paths.get('cdb_dir')
            CURRENT_PICS_DIR = active_paths.get('pics_dir') or CURRENT_PICS_DIR
            all_cards = []
            seen_ids = set()
            if cdb_dir and os.path.exists(cdb_dir):
                # Pre-cargar constantes para decodificar tipos y setcodes
                from card_decoder import CardDecoder
                editor_constants = load_editor_constants()
                decoder = CardDecoder(editor_constants)

                cdb_files = []
                for dirpath, _, filenames in os.walk(cdb_dir):
                    for f in filenames:
                        if f.lower().endswith('.cdb'):
                            cdb_files.append(os.path.join(dirpath, f))
                if requested_target_cdb:
                    requested_target_cdb_abs = os.path.abspath(requested_target_cdb)
                    matched_cdbs = [p for p in cdb_files if os.path.abspath(p) == requested_target_cdb_abs]
                    if not matched_cdbs:
                        self.send_response(400)
                        self.send_header('Content-type', 'application/json')
                        self.send_header('Cache-Control', 'no-store')
                        self.end_headers()
                        self.wfile.write(json.dumps({
                            'status': 'error',
                            'error': 'Requested target CDB was not found in the active profile'
                        }).encode())
                        return
                    cdb_files = matched_cdbs
                for cdb_file in cdb_files:
                    cdb_path = cdb_file
                    try:
                        conn = sqlite3.connect(cdb_path)
                        cursor = conn.cursor()
                        cursor.execute("""
                            SELECT t.id, t.name, t.desc,
                                   d.atk, d.def, d.level, d.race, d.attribute, d.type, d.alias, d.setcode, d.ot, d.category,
                                   t.str1, t.str2, t.str3, t.str4, t.str5, t.str6, t.str7, t.str8,
                                   t.str9, t.str10, t.str11, t.str12, t.str13, t.str14, t.str15, t.str16
                            FROM texts t
                            JOIN datas d ON t.id = d.id
                        """)
                        rows = cursor.fetchall()
                        for row in rows:
                            type_val   = row[8]
                            setcode_val = row[10]
                            ot_val     = row[11]
                            category_val = row[12]
                            level_val  = row[5] or 0

                            # El editor UI usa un <select> de arquetipo con valores de 16 bits (setname keys).
                            # `setcode` en .cdb viene empaquetado (hasta 4 bloques de 16 bits), así que para
                            # preseleccionar el arquetipo debemos exponer el primer bloque no-cero.
                            setcode_primary = 0
                            setcodes16 = []
                            tmp = int(setcode_val or 0)
                            for _ in range(4):
                                part = tmp & 0xFFFF
                                if part:
                                    setcodes16.append(part)
                                    if not setcode_primary:
                                        setcode_primary = part
                                tmp >>= 16

                            # El <select> Level/Rank/Link usa valores simples (1..12, etc.).
                            # En .cdb `level` puede venir empaquetado (Péndulo/Link), así que exponemos el
                            # byte bajo para preselección.
                            level_primary = int(level_val) & 0xFF
                            lscale = (int(level_val) >> 24) & 0xFF
                            rscale = (int(level_val) >> 16) & 0xFF
                            card = {
                                'id': row[0], 'name': row[1], 'desc': row[2],
                                'atk': int(row[3] or 0), 'def': int(row[4] or 0), 'level': row[5],
                                'race': row[6], 'attribute': row[7], 'type': type_val,
                                'alias': row[9], 'setcode': setcode_val, 'ot': ot_val, 'rule': ot_val,
                                'category': int(category_val or 0),
                                'setcode_primary': setcode_primary,
                                'setcodes16': setcodes16,
                                'level_primary': level_primary,
                                'lscale': lscale,
                                'rscale': rscale,
                                # Campos decodificados
                                'type_display':   decoder.get_card_type_display(type_val),
                                'type_string':    decoder.get_type_string(type_val),
                                'ot_name':        decoder.decode_ot(ot_val)['ot_name'],
                                'setname_display': decoder.get_setname_string(setcode_val),
                                'attribute_name': decoder.decode_attribute(row[7])['attribute_name'] if type_val & 0x1 else '',
                                'race_name':      decoder.decode_race(row[6])['race_name'] if type_val & 0x1 else '',
                            }
                            for i in range(1, 17):
                                card[f'str{i}'] = str(row[12+i]) if row[12+i] else ''
                            if card['id'] in seen_ids:
                                continue
                            seen_ids.add(card['id'])
                            all_cards.append(card)
                        conn.close()
                    except Exception as ex:
                        print(f'Error loading {cdb_file}: {ex}')
                        continue

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(json.dumps(all_cards).encode())
        elif parsed_path.path == '/api/editor/compare_yugioh_db':
            try:
                config = load_config()
                requested_profile = (query.get('active_profile', [''])[0] or '').strip().lower()
                if requested_profile:
                    config = normalize_config(config)
                    config['active_profile'] = requested_profile
                active_paths = get_active_profile_paths(config)
                active_profile = str(active_paths.get('active_profile') or requested_profile or 'es').strip().lower()
                profiles = active_paths.get('profiles') or {}
                profile_data = profiles.get(active_profile) or {}
                cdb_dir = active_paths.get('cdb_dir')
                if not cdb_dir or not os.path.exists(cdb_dir):
                    raise FileNotFoundError('CDB path not configured')

                request_locale = map_profile_to_yugioh_request_locale(active_profile, profile_data.get('ui_lang') or '')
                all_cards = []
                seen_ids = set()
                from card_decoder import CardDecoder
                editor_constants = load_editor_constants()
                decoder = CardDecoder(editor_constants)

                cdb_files = []
                for dirpath, _, filenames in os.walk(cdb_dir):
                    for f in filenames:
                        if f.lower().endswith('.cdb'):
                            cdb_files.append(os.path.join(dirpath, f))

                for cdb_file in cdb_files:
                    try:
                        conn = sqlite3.connect(cdb_file)
                        cursor = conn.cursor()
                        cursor.execute("""
                            SELECT t.id, t.name, t.desc, d.ot, d.type
                            FROM texts t
                            JOIN datas d ON t.id = d.id
                            ORDER BY t.id ASC
                        """)
                        rows = cursor.fetchall()
                        conn.close()
                        for row in rows:
                            card_id = row[0]
                            if card_id in seen_ids:
                                continue
                            seen_ids.add(card_id)
                            ot_val = int(row[3] or 0)
                            type_val = int(row[4] or 0)
                            is_normal_monster = bool((type_val & 0x1) != 0 and (type_val & 0x10) != 0)
                            if is_normal_monster:
                                continue
                            all_cards.append({
                                'id': card_id,
                                'name': row[1] or '',
                                'desc': row[2] or '',
                                'rule_name': decoder.decode_ot(ot_val)['ot_name'],
                            })
                            if len(all_cards) >= YGO_COMPARE_CARD_LIMIT:
                                break
                        if len(all_cards) >= YGO_COMPARE_CARD_LIMIT:
                            break
                    except Exception as ex:
                        print(f'Error loading {cdb_file} for Yugioh DB compare: {ex}')
                        try:
                            conn.close()
                        except Exception:
                            pass
                        continue
                all_cards = all_cards[:YGO_COMPARE_CARD_LIMIT]

                job_id = start_ygo_compare_job(all_cards, request_locale, active_profile)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'status': 'ok',
                    'job_id': job_id,
                    'request_locale': request_locale,
                }, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))
        elif parsed_path.path == '/api/editor/compare_yugioh_db_status':
            job_id = str(query.get('job_id', [''])[0] or '').strip()
            with YGO_COMPARE_JOBS_LOCK:
                job = dict(YGO_COMPARE_JOBS.get(job_id) or {})
            if not job:
                self.send_response(404)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Job not found'}, ensure_ascii=False).encode('utf-8'))
            else:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(json.dumps(job, ensure_ascii=False).encode('utf-8'))
        elif parsed_path.path == '/api/get_config':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(load_config(), ensure_ascii=False).encode('utf-8'))
        elif parsed_path.path == '/api/editor/constants':
            constants = load_editor_constants()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(json.dumps(constants).encode())
        elif parsed_path.path == '/api/editor/target_cdb':
            config = load_config()
            requested_profile = (query.get('active_profile', [''])[0] or '').strip().lower()
            if requested_profile:
                config = normalize_config(config)
                config['active_profile'] = requested_profile
            active_paths = get_active_profile_paths(config)
            cdb_dir = active_paths.get('cdb_dir')
            target_cdb = ''
            cdb_files = []
            if cdb_dir and os.path.exists(cdb_dir):
                for dirpath, _, filenames in os.walk(cdb_dir):
                    for f in filenames:
                        if f.lower().endswith('.cdb'):
                            cdb_files.append(os.path.join(dirpath, f))
                if cdb_files:
                    preferred = sorted(cdb_files, key=lambda p: (0 if os.path.basename(p).lower() == 'cards.cdb' else 1, p.lower()))
                    target_cdb = preferred[0]

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(json.dumps({
                'status': 'ok',
                'target_cdb': target_cdb,
                'target_cdb_name': os.path.basename(target_cdb) if target_cdb else '',
                'cdb_files': cdb_files
            }, ensure_ascii=False).encode('utf-8'))
        elif parsed_path.path == '/api/editor/strings_conf':
            try:
                config = load_config()
                requested_profile = (query.get('active_profile', [''])[0] or '').strip().lower()
                if requested_profile:
                    config = normalize_config(config)
                    config['active_profile'] = requested_profile
                active_paths = get_active_profile_paths(config)
                strings_conf = str(active_paths.get('strings_conf') or '').strip()
                if not strings_conf or not os.path.exists(strings_conf):
                    raise FileNotFoundError('strings.conf path not configured')

                content, encoding = read_text_file(strings_conf)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'status': 'ok',
                    'path': strings_conf,
                    'encoding': encoding,
                    'content': content,
                }, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))
        elif parsed_path.path == '/api/editor/archetype_sync':
            try:
                config = load_config()
                requested_profile = (query.get('active_profile', [''])[0] or '').strip().lower()
                requested_scope = (query.get('scope', ['current'])[0] or 'current').strip().lower()
                if requested_profile:
                    config = normalize_config(config)
                    config['active_profile'] = requested_profile
                strings_targets, resolved_profile = _collect_strings_conf_targets(config, requested_profile, requested_scope)
                if not strings_targets:
                    raise FileNotFoundError('strings.conf path not configured')

                constants_path = _resolve_editor_constants_path()
                if not constants_path or not os.path.exists(constants_path):
                    raise FileNotFoundError('cardinfo_english.txt path not configured')

                strings_paths = []
                strings_encoding = ''
                for target in strings_targets:
                    _content, enc = read_text_file(str(target.get('path') or ''))
                    strings_encoding = strings_encoding or enc
                    strings_paths.append(str(target.get('path') or ''))
                constants_content, constants_encoding = read_text_file(constants_path)
                snapshot = _build_setname_sync_snapshot_for_targets(strings_targets, constants_content, requested_scope)

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'status': 'ok',
                    'scope': requested_scope,
                    'active_profile': resolved_profile,
                    'strings_path': strings_paths[0] if len(strings_paths) == 1 else '',
                    'strings_paths': strings_paths,
                    'strings_encoding': strings_encoding,
                    'constants_path': constants_path,
                    'constants_encoding': constants_encoding,
                    **snapshot,
                }, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))
        elif parsed_path.path == '/api/editor/archetype_sync_export':
            try:
                config = load_config()
                requested_profile = (query.get('active_profile', [''])[0] or '').strip().lower()
                requested_scope = (query.get('scope', ['current'])[0] or 'current').strip().lower()
                if requested_profile:
                    config = normalize_config(config)
                    config['active_profile'] = requested_profile
                strings_targets, resolved_profile = _collect_strings_conf_targets(config, requested_profile, requested_scope)
                if not strings_targets:
                    raise FileNotFoundError('strings.conf path not configured')
                constants_path = _resolve_editor_constants_path()
                if not constants_path or not os.path.exists(constants_path):
                    raise FileNotFoundError('cardinfo_english.txt path not configured')

                constants_content, _constants_encoding = read_text_file(constants_path)
                snapshot = _build_setname_sync_snapshot_for_targets(strings_targets, constants_content, requested_scope)
                payload = _build_archetype_mismatch_workbook(
                    snapshot.get('mismatches') or [],
                    snapshot.get('profiles') or [],
                    requested_scope,
                    resolved_profile,
                )
                filename = f"archetype_differences_{requested_scope}.xlsx"

                self.send_response(200)
                self.send_header('Content-type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(payload)
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))
        elif parsed_path.path == '/api/editor/archetype_candidates':
            try:
                config = load_config()
                constants_path = _resolve_editor_constants_path()
                if not constants_path or not os.path.exists(constants_path):
                    raise FileNotFoundError('cardinfo_english.txt path not configured')
                cdb_targets = _collect_language_cdb_targets(config)
                if not cdb_targets:
                    raise FileNotFoundError('No language CDB paths configured')
                constants_content, constants_encoding = read_text_file(constants_path)
                result = _scan_unknown_archetypes_from_cdb_targets(cdb_targets, constants_content)

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'status': 'ok',
                    'constants_path': constants_path,
                    'constants_encoding': constants_encoding,
                    **result,
                }, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))
        elif parsed_path.path == '/api/editor/lua_script':
            try:
                config = load_config()
                requested_profile = (query.get('active_profile', [''])[0] or '').strip().lower()
                if requested_profile:
                    config = normalize_config(config)
                    config['active_profile'] = requested_profile
                active_paths = get_active_profile_paths(config)
                script_dir = str(active_paths.get('script_dir') or '').strip()
                if not script_dir or not os.path.exists(script_dir):
                    raise FileNotFoundError('script path not configured')

                card_id = int((query.get('card_id', ['0'])[0] or '0').strip() or 0)
                if not card_id:
                    raise ValueError('invalid card id')

                script_path = find_script_file(script_dir, card_id)
                exists = os.path.exists(script_path)
                content = ''
                encoding = 'utf-8'
                if exists:
                    content, encoding = read_text_file(script_path)

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'status': 'ok',
                    'path': script_path,
                    'exists': exists,
                    'encoding': encoding,
                    'content': content,
                }, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))
        elif parsed_path.path == '/api/editor/lua_function_doc':
            try:
                query_name = str(query.get('name', [''])[0] or '').strip()
                matches = find_lua_function_doc_matches(query_name)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'status': 'ok',
                    'query': query_name,
                    'matches': matches,
                    'source_paths': LUA_FUNCTION_DOCS_FILES,
                }, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))
        elif parsed_path.path == '/api/translate':
            text = query.get('text', [''])[0]
            target_lang = query.get('target_lang', ['es'])[0]
            translated = translate_text(text, target_lang)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(json.dumps({'translated': translated}, ensure_ascii=False).encode('utf-8'))
        else:
            super().do_GET()

    def do_POST(self):
        global CURRENT_PICS_DIR
        parsed_path = urllib.parse.urlparse(self.path)
        post_path = parsed_path.path
        if post_path == '/api/run':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            params = json.loads(post_data)
            
            mode = params.get('mode', 'local')
            temp_dir = os.path.join(os.getcwd(), 'temp_analysis')

            try:
                if mode == 'github':
                    # Limpiar y preparar carpeta temporal
                    if os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir)
                    os.makedirs(temp_dir)
                    
                    # Descargar CDBs
                    cdb_local = os.path.join(temp_dir, 'cdb')
                    os.makedirs(cdb_local)
                    GitHubDownloader.download_folder(params['github_cdb'], cdb_local)
                    
                    # Descargar Scripts
                    scripts_local = os.path.join(temp_dir, 'script')
                    os.makedirs(scripts_local)
                    GitHubDownloader.download_folder(params['github_scripts'], scripts_local)
                    
                    # Descargar Strings
                    strings_local = os.path.join(temp_dir, 'strings.conf')
                    GitHubDownloader.download_file(params['github_strings'], strings_local)
                    
                    cdb_dir, script_dir, strings_conf = cdb_local, scripts_local, strings_local
                else:
                    cdb_dir = params.get('cdb_dir')
                    script_dir = params.get('script_dir')
                    strings_conf = params.get('strings_conf')
                    
                # Guardar configuración para persistencia (por perfiles de idioma)
                pics_dir = params.get('pics_dir')
                try:
                    cfg = load_config()
                    cfg = normalize_config(cfg)
                    active_profile = (params.get('active_profile') or params.get('db_profile') or cfg.get('active_profile') or 'es')
                    active_profile = str(active_profile).lower()
                    cfg['active_profile'] = active_profile
                    cfg.setdefault('profiles', {})
                    cfg['profiles'].setdefault(active_profile, {})
                    cfg['profiles'][active_profile].update({
                        'cdb_dir': cdb_dir,
                        'script_dir': script_dir,
                        'strings_conf': strings_conf,
                        'pics_dir': pics_dir,
                    })
                    save_config(cfg)
                    CURRENT_PICS_DIR = get_active_profile_paths(cfg).get('pics_dir') or pics_dir or CURRENT_PICS_DIR
                except Exception:
                    # Fallback: mantener comportamiento anterior si algo falla
                    save_config({
                        'cdb_dir': cdb_dir,
                        'script_dir': script_dir,
                        'strings_conf': strings_conf,
                        'pics_dir': pics_dir
                    })
                    CURRENT_PICS_DIR = pics_dir

                results = run_analysis(cdb_dir, strings_conf, script_dir, active_profile)
                profile_key = (params.get('active_profile') or params.get('db_profile') or '').strip().lower()
                profile_ui_lang = ''
                try:
                    if 'cfg' in locals():
                        profile_ui_lang = str((cfg.get('profiles', {}).get(profile_key, {}) or {}).get('ui_lang') or '').strip().lower()
                except Exception:
                    profile_ui_lang = ''
                profile_ui_lang = normalize_ui_lang_code(profile_ui_lang, profile_key)
                results['_meta'] = {
                    'active_profile': profile_key,
                    'ui_lang': profile_ui_lang,
                    'cdb_dir': cdb_dir,
                    'script_dir': script_dir,
                    'strings_conf': strings_conf,
                    'generated_at': int(time.time())
                }
                
                with open('resultados.json', 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=4, ensure_ascii=False)
                if profile_ui_lang:
                    safe_lang = re.sub(r'[^a-z0-9_-]', '', profile_ui_lang)
                    if safe_lang:
                        with open(f'resultados_{safe_lang}.json', 'w', encoding='utf-8') as f:
                            json.dump(results, f, indent=4, ensure_ascii=False)
                        base_lang = safe_lang.split('-')[0]
                        if base_lang and base_lang != safe_lang:
                            with open(f'resultados_{base_lang}.json', 'w', encoding='utf-8') as f:
                                json.dump(results, f, indent=4, ensure_ascii=False)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'ok'}).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
                
        elif post_path == '/api/editor/analyze_card':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            card_data = json.loads(post_data)

            try:
                from card_decoder import CardDecoder
                constants = load_editor_constants()
                decoder = CardDecoder(constants)
                analysis = decoder.analyzeCardRow(card_data)

                # Eliminar lambdas no serializables
                analysis.pop('helpers', None)

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(analysis, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        elif post_path == '/api/debug/log':
            content_length = int(self.headers.get('Content-Length', '0') or '0')
            post_data = self.rfile.read(content_length) if content_length > 0 else b'{}'
            try:
                payload = json.loads(post_data.decode('utf-8') or '{}')
            except Exception:
                payload = {'raw': post_data.decode('utf-8', errors='replace')}
            append_debug_log(payload)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok'}).encode())
        elif post_path == '/api/editor/save_card' or post_path == '/api/editor/insert_card':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            params = json.loads(post_data or b'{}')

            try:
                config = load_config()
                config = normalize_config(config)
                requested_profile = str(params.get('active_profile') or '').strip().lower()
                if requested_profile:
                    config['active_profile'] = requested_profile

                active_paths = get_active_profile_paths(config)
                cdb_dir = active_paths.get('cdb_dir')
                if not cdb_dir or not os.path.exists(cdb_dir):
                    raise Exception('CDB path not configured')

                card = params.get('card') or {}
                card_id = int(card.get('id') or 0)
                if not card_id:
                    raise Exception('Invalid card id')

                cdb_files = []
                for dirpath, _, filenames in os.walk(cdb_dir):
                    for f in filenames:
                        if f.lower().endswith('.cdb'):
                            cdb_files.append(os.path.join(dirpath, f))

                force_insert = (post_path == '/api/editor/insert_card')
                target_cdb = None
                card_exists = False
                existing_cdb = None
                for cdb_path in cdb_files:
                    try:
                        conn = sqlite3.connect(cdb_path)
                        cur = conn.cursor()
                        cur.execute('SELECT 1 FROM datas WHERE id=? LIMIT 1', (card_id,))
                        ok = cur.fetchone() is not None
                        conn.close()
                        if ok:
                            card_exists = True
                            existing_cdb = cdb_path
                            if not force_insert:
                                target_cdb = cdb_path
                                break
                    except Exception:
                        try:
                            conn.close()
                        except Exception:
                            pass
                        continue

                if force_insert and card_exists:
                    raise Exception(f'Card ID {card_id} already exists')

                if not force_insert and not card_exists:
                    raise Exception(f'Card ID {card_id} not found for update')

                if not target_cdb:
                    if not cdb_files:
                        raise Exception('No CDB files found in active profile')
                    if force_insert:
                        requested_target = os.path.abspath(str(params.get('target_cdb_path') or '').strip())
                        if requested_target and any(os.path.abspath(p) == requested_target for p in cdb_files):
                            target_cdb = requested_target
                        else:
                            preferred = sorted(cdb_files, key=lambda p: (0 if os.path.basename(p).lower() == 'cards.cdb' else 1, p.lower()))
                            target_cdb = preferred[0]
                    else:
                        preferred = sorted(cdb_files, key=lambda p: (0 if os.path.basename(p).lower() == 'cards.cdb' else 1, p.lower()))
                        target_cdb = preferred[0]

                name = str(card.get('name') or '')
                desc = str(card.get('desc') or '')
                strs = [str(card.get(f'str{i}') or '') for i in range(1, 17)]
                atk = int(card.get('atk') or 0)
                defe = int(card.get('def') or 0)
                level = int(card.get('level') or 0)
                race = int(card.get('race') or 0)
                attribute = int(card.get('attribute') or 0)
                type_val = int(card.get('type') or 0)
                alias = int(card.get('alias') or 0)
                setcode = int(card.get('setcode') or 0)
                ot = int(card.get('ot') or 0)
                category = int(card.get('category') or 0)

                conn = sqlite3.connect(target_cdb)
                cur = conn.cursor()
                try:
                    if card_exists and not force_insert:
                        cur.execute("""
                            UPDATE texts
                            SET name=?, desc=?, str1=?, str2=?, str3=?, str4=?, str5=?, str6=?, str7=?, str8=?,
                                str9=?, str10=?, str11=?, str12=?, str13=?, str14=?, str15=?, str16=?
                            WHERE id=?
                        """, (name, desc, *strs, card_id))

                        cur.execute("""
                            UPDATE datas
                            SET ot=?, alias=?, setcode=?, type=?, atk=?, def=?, level=?, race=?, attribute=?, category=?
                            WHERE id=?
                        """, (ot, alias, setcode, type_val, atk, defe, level, race, attribute, category, card_id))
                    else:
                        cur.execute("""
                            INSERT INTO texts (
                                id, name, desc, str1, str2, str3, str4, str5, str6, str7, str8,
                                str9, str10, str11, str12, str13, str14, str15, str16
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (card_id, name, desc, *strs))
                        cur.execute("""
                            INSERT INTO datas (
                                id, ot, alias, setcode, type, atk, def, level, race, attribute, category
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (card_id, ot, alias, setcode, type_val, atk, defe, level, race, attribute, category))
                    conn.commit()
                finally:
                    conn.close()

                active_profile_for_sync = str(requested_profile or config.get('active_profile') or '').strip().lower()
                ypk_synced = False
                try:
                    ypk_synced = sync_temp_profile_to_ypk(config, active_profile_for_sync)
                except Exception as sync_err:
                    raise Exception(f'Card saved, but YPK sync failed: {sync_err}')
                prof_sync = (config.get('profiles') or {}).get(active_profile_for_sync) or {}
                if bool(prof_sync.get('is_temp_ypk')) and not ypk_synced:
                    raise Exception('Card saved, but YPK source path is missing for sync')

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'status': 'ok',
                    'mode': ('update' if card_exists else 'insert'),
                    'cdb': target_cdb,
                    'id': card_id,
                    'ypk_synced': ypk_synced
                }, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))
        elif post_path == '/api/editor/delete_card':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            params = json.loads(post_data or b'{}')

            try:
                config = load_config()
                config = normalize_config(config)
                requested_profile = str(params.get('active_profile') or '').strip().lower()
                if requested_profile:
                    config['active_profile'] = requested_profile
                cdb_dir = str(params.get('cdb_dir') or '').strip()
                if not cdb_dir:
                    active_paths = get_active_profile_paths(config)
                    cdb_dir = active_paths.get('cdb_dir')
                if not cdb_dir or not os.path.exists(cdb_dir):
                    raise Exception('CDB path not configured')

                card_id = int(params.get('card_id') or 0)
                if not card_id:
                    raise Exception('Invalid card id')

                cdb_files = []
                for dirpath, _, filenames in os.walk(cdb_dir):
                    for f in filenames:
                        if f.lower().endswith('.cdb'):
                            cdb_files.append(os.path.join(dirpath, f))
                if not cdb_files:
                    raise Exception('No CDB files found in active profile')

                deleted = False
                for cdb_path in cdb_files:
                    conn = None
                    try:
                        conn = sqlite3.connect(cdb_path)
                        cur = conn.cursor()
                        cur.execute('SELECT 1 FROM datas WHERE id=? LIMIT 1', (card_id,))
                        if cur.fetchone() is None:
                            conn.close()
                            continue
                        cur.execute('DELETE FROM texts WHERE id=?', (card_id,))
                        cur.execute('DELETE FROM datas WHERE id=?', (card_id,))
                        conn.commit()
                        conn.close()
                        deleted = True
                        break
                    except Exception:
                        if conn is not None:
                            try:
                                conn.close()
                            except Exception:
                                pass
                        continue

                if not deleted:
                    raise Exception(f'Card ID {card_id} not found')

                active_profile_for_sync = str(requested_profile or config.get('active_profile') or '').strip().lower()
                ypk_synced = False
                try:
                    ypk_synced = sync_temp_profile_to_ypk(config, active_profile_for_sync)
                except Exception as sync_err:
                    raise Exception(f'Card deleted, but YPK sync failed: {sync_err}')
                prof_sync = (config.get('profiles') or {}).get(active_profile_for_sync) or {}
                if bool(prof_sync.get('is_temp_ypk')) and not ypk_synced:
                    raise Exception('Card deleted, but YPK source path is missing for sync')

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'ok', 'id': card_id, 'ypk_synced': ypk_synced}, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))
        elif post_path == '/api/editor/save_strings_conf':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            params = json.loads(post_data or b'{}')

            try:
                config = load_config()
                config = normalize_config(config)
                requested_profile = str(params.get('active_profile') or '').strip().lower()
                if requested_profile:
                    config['active_profile'] = requested_profile

                active_paths = get_active_profile_paths(config)
                strings_conf = str(active_paths.get('strings_conf') or '').strip()
                if not strings_conf or not os.path.exists(strings_conf):
                    raise Exception('strings.conf path not configured')

                content = normalize_strings_conf_content(str(params.get('content') or ''))
                encoding = str(params.get('encoding') or '').strip() or detect_text_file_encoding(strings_conf)
                write_text_file(strings_conf, content, encoding)

                active_profile_for_sync = str(requested_profile or config.get('active_profile') or '').strip().lower()
                ypk_synced = False
                try:
                    ypk_synced = sync_temp_profile_to_ypk(config, active_profile_for_sync)
                except Exception as sync_err:
                    raise Exception(f'strings.conf saved, but YPK sync failed: {sync_err}')
                prof_sync = (config.get('profiles') or {}).get(active_profile_for_sync) or {}
                if bool(prof_sync.get('is_temp_ypk')) and not ypk_synced:
                    raise Exception('strings.conf saved, but YPK source path is missing for sync')

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'status': 'ok',
                    'path': strings_conf,
                    'encoding': encoding,
                    'ypk_synced': ypk_synced,
                }, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))
        elif post_path == '/api/editor/archetype_sync_apply':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            params = json.loads(post_data or b'{}')

            try:
                config = load_config()
                config = normalize_config(config)
                requested_profile = str(params.get('active_profile') or '').strip().lower()
                requested_scope = str(params.get('scope') or 'current').strip().lower()
                requested_target_profiles = params.get('target_profiles') or []
                if requested_profile:
                    config['active_profile'] = requested_profile

                direction = str(params.get('direction') or '').strip().lower()
                entries = params.get('entries') or []
                if direction not in ('to_constants', 'to_strings'):
                    raise Exception('Invalid sync direction')
                if not isinstance(entries, list) or not entries:
                    raise Exception('No archetypes selected')

                target_profiles = [str(x or '').strip().lower() for x in requested_target_profiles if str(x or '').strip()]
                strings_targets, resolved_profile = _collect_strings_conf_targets(
                    config,
                    requested_profile,
                    requested_scope,
                    target_profiles if (direction == 'to_strings' and target_profiles) else None
                )
                constants_path = _resolve_editor_constants_path()
                if not strings_targets:
                    raise Exception('strings.conf path not configured')
                if not constants_path or not os.path.exists(constants_path):
                    raise Exception('cardinfo_english.txt path not configured')

                ypk_synced = False
                updated_path = ''
                updated_encoding = ''
                if direction == 'to_strings':
                    written_paths = []
                    wrote_any_temp = False
                    any_temp_synced = False
                    for target in strings_targets:
                        target_path = str(target.get('path') or '').strip()
                        original_content, encoding = read_text_file(target_path)
                        updated_content = _append_setname_entries_to_content(original_content, entries, 'strings_conf')
                        write_text_file(target_path, updated_content, encoding)
                        written_paths.append(target_path)
                        updated_encoding = updated_encoding or encoding
                    profiles_map = config.get('profiles') or {}
                    for profile_key, profile_data in profiles_map.items():
                        prof_path = os.path.abspath(str((profile_data or {}).get('strings_conf') or '').strip()) if (profile_data or {}).get('strings_conf') else ''
                        if prof_path and any(os.path.abspath(str(t.get('path') or '')) == prof_path for t in strings_targets):
                            if bool((profile_data or {}).get('is_temp_ypk')):
                                wrote_any_temp = True
                                try:
                                    synced = sync_temp_profile_to_ypk(config, str(profile_key or '').strip().lower())
                                    any_temp_synced = any_temp_synced or synced
                                except Exception as sync_err:
                                    raise Exception(f'strings.conf saved, but YPK sync failed: {sync_err}')
                    if wrote_any_temp and not any_temp_synced:
                        raise Exception('strings.conf saved, but YPK source path is missing for sync')
                    ypk_synced = any_temp_synced
                    updated_path = written_paths[0] if len(written_paths) == 1 else '; '.join(written_paths)
                else:
                    original_content, encoding = read_text_file(constants_path)
                    updated_content = _append_setname_entries_to_content(original_content, entries, 'constants_txt')
                    write_text_file(constants_path, updated_content, encoding)
                    load_editor_constants(force=True)
                    updated_path = constants_path
                    updated_encoding = encoding

                strings_paths = []
                strings_encoding = ''
                for target in strings_targets:
                    target_path = str(target.get('path') or '').strip()
                    _content, enc = read_text_file(target_path)
                    strings_encoding = strings_encoding or enc
                    strings_paths.append(target_path)
                constants_content, constants_encoding = read_text_file(constants_path)
                snapshot = _build_setname_sync_snapshot_for_targets(strings_targets, constants_content, requested_scope)

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'status': 'ok',
                    'scope': requested_scope,
                    'active_profile': resolved_profile,
                    'direction': direction,
                    'path': updated_path,
                    'encoding': updated_encoding,
                    'ypk_synced': ypk_synced,
                    'strings_path': strings_paths[0] if len(strings_paths) == 1 else '',
                    'strings_paths': strings_paths,
                    'strings_encoding': strings_encoding,
                    'constants_path': constants_path,
                    'constants_encoding': constants_encoding,
                    **snapshot,
                }, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))
        elif post_path == '/api/editor/archetype_create':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            params = json.loads(post_data or b'{}')

            try:
                name = str(params.get('name') or '').strip()
                code_raw = str(params.get('code') or '').strip()
                if not code_raw:
                    raise Exception('Missing archetype code')
                if not name:
                    raise Exception('Missing archetype name')
                try:
                    code = int(code_raw, 0)
                except Exception:
                    raise Exception('Invalid archetype code')

                constants_path = _resolve_editor_constants_path()
                if not constants_path or not os.path.exists(constants_path):
                    raise Exception('cardinfo_english.txt path not configured')

                original_content, constants_encoding = read_text_file(constants_path)
                existing = _parse_setname_entries_from_text(original_content, 'constants_txt')
                if code in existing:
                    raise Exception('Archetype code already exists in config')

                updated_content = _append_setname_entries_to_content(
                    original_content,
                    [{'code': code, 'name': name}],
                    'constants_txt'
                )
                write_text_file(constants_path, updated_content, constants_encoding or 'utf-8')
                load_editor_constants(force=True)

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'status': 'ok',
                    'code': code,
                    'code_hex': _format_setname_code(code),
                    'name': name,
                    'constants_path': constants_path,
                }, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))
        elif post_path == '/api/editor/create_ypk':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            params = json.loads(post_data or b'{}')

            try:
                result = _create_ypk_package(params)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'status': 'ok',
                    **result,
                }, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))
        elif post_path == '/api/editor/save_lua_script':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            params = json.loads(post_data or b'{}')

            try:
                config = load_config()
                config = normalize_config(config)
                requested_profile = str(params.get('active_profile') or '').strip().lower()
                if requested_profile:
                    config['active_profile'] = requested_profile

                active_paths = get_active_profile_paths(config)
                script_dir = str(active_paths.get('script_dir') or '').strip()
                if not script_dir or not os.path.exists(script_dir):
                    raise Exception('script path not configured')

                card_id = int(params.get('card_id') or 0)
                if not card_id:
                    raise Exception('invalid card id')

                script_path = find_script_file(script_dir, card_id)
                target_dir = os.path.dirname(script_path)
                if target_dir and not os.path.exists(target_dir):
                    os.makedirs(target_dir, exist_ok=True)

                content = str(params.get('content') or '')
                encoding = str(params.get('encoding') or '').strip() or (
                    detect_text_file_encoding(script_path) if os.path.exists(script_path) else 'utf-8'
                )
                write_text_file(script_path, content, encoding)

                active_profile_for_sync = str(requested_profile or config.get('active_profile') or '').strip().lower()
                ypk_synced = False
                try:
                    ypk_synced = sync_temp_profile_to_ypk(config, active_profile_for_sync)
                except Exception as sync_err:
                    raise Exception(f'LUA script saved, but YPK sync failed: {sync_err}')
                prof_sync = (config.get('profiles') or {}).get(active_profile_for_sync) or {}
                if bool(prof_sync.get('is_temp_ypk')) and not ypk_synced:
                    raise Exception('LUA script saved, but YPK source path is missing for sync')

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'status': 'ok',
                    'path': script_path,
                    'encoding': encoding,
                    'ypk_synced': ypk_synced,
                }, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))
        elif post_path == '/api/config':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            params = json.loads(post_data)

            # Fallback compatible: permitir carga de YPK por /api/config
            # para clientes/instancias donde /api/load_ypk no esté enrutando.
            if params.get('action') == 'load_ypk' or params.get('ypk_path'):
                try:
                    extracted, _cfg = apply_ypk_load_to_config(params)
                    CURRENT_PICS_DIR = extracted.get('pics_dir') or CURRENT_PICS_DIR

                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'status': 'ok',
                        'active_profile': extracted['profile'],
                        'paths': {
                            'cdb_dir': extracted.get('cdb_dir') or '',
                            'script_dir': extracted.get('script_dir') or '',
                            'strings_conf': extracted.get('strings_conf') or '',
                            'pics_dir': extracted.get('pics_dir') or '',
                        },
                        'counts': {
                            'cdb': extracted.get('cdb_count') or 0,
                            'scripts': extracted.get('script_count') or 0,
                            'pics': extracted.get('pics_count') or 0,
                        }
                    }, ensure_ascii=False).encode('utf-8'))
                except Exception as e:
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))
                return

            save_config(params)
            # Actualizar pics_dir activo (si aplica)
            try:
                cfg = load_config()
                CURRENT_PICS_DIR = get_active_profile_paths(cfg).get('pics_dir') or CURRENT_PICS_DIR
            except:
                pass
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok'}).encode())
        elif post_path.startswith('/api/load_ypk') or post_path.startswith('/api/editor/load_ypk'):
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            params = json.loads(post_data)

            try:
                extracted, _cfg = apply_ypk_load_to_config(params)
                CURRENT_PICS_DIR = extracted.get('pics_dir') or CURRENT_PICS_DIR

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'status': 'ok',
                    'active_profile': extracted['profile'],
                    'paths': {
                        'cdb_dir': extracted.get('cdb_dir') or '',
                        'script_dir': extracted.get('script_dir') or '',
                        'strings_conf': extracted.get('strings_conf') or '',
                        'pics_dir': extracted.get('pics_dir') or '',
                    },
                    'counts': {
                        'cdb': extracted.get('cdb_count') or 0,
                        'scripts': extracted.get('script_count') or 0,
                        'pics': extracted.get('pics_count') or 0,
                    }
                }, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))
        else:
            self.send_error(404)


class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    pass

def start_server():
    PORT = 58927
    socketserver.TCPServer.allow_reuse_address = True
    with ThreadingTCPServer(("", PORT), APIHandler) as httpd:
        httpd.serve_forever()

def process_dialogs(root):
    """ Función que corre en el hilo principal para manejar los diálogos """
    try:
        while True:
            try:
                task = DIALOG_QUEUE.get_nowait()
                # Configurar título basado en i18n
                lang, title_key = task['lang'], task['title_key']
                if not title_key:
                    title_key = 'title_select_folder' if task['is_folder'] else 'title_select_file'
                title = I18N.get(lang, I18N['es']).get(title_key, title_key)
                
                # Mostrar diálogo
                if task['is_folder']:
                    path = filedialog.askdirectory(title=title)
                else:
                    filetypes = task.get('filetypes') or None
                    path = filedialog.askopenfilename(title=title, filetypes=filetypes) if filetypes else filedialog.askopenfilename(title=title)
                
                task['response_q'].put(path)
            except queue.Empty:
                pass
            root.update()
            time.sleep(0.05)
    except tk.TclError:
        pass

def main():
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    
    # Iniciar servidor en hilo secundario
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    
    # Abrir navegador
    time.sleep(1)
    webbrowser.open("http://localhost:58927/index.html")
    
    # Procesar diálogos en el hilo principal
    process_dialogs(root)

class GitHubDownloader:
    @staticmethod
    def _parse_url(url):
        # Convierte URL de navegador a URL de API
        # Ejemplo: https://github.com/owner/repo/tree/branch/path
        url = url.strip().rstrip('/')
        if 'github.com' not in url: return None
        
        parts = url.split('/')
        if len(parts) < 5: return None
        
        owner = parts[3]
        repo = parts[4]
        path = ""
        branch = "master" # Default
        
        if len(parts) > 6 and parts[5] == "tree":
            branch = parts[6]
            path = "/".join(parts[7:]) if len(parts) > 7 else ""
        elif len(parts) > 6 and parts[5] == "blob":
            branch = parts[6]
            path = "/".join(parts[7:]) if len(parts) > 7 else ""
            
        return {'owner': owner, 'repo': repo, 'path': path, 'branch': branch}

    @staticmethod
    def download_file(url, dest_path):
        raw_url = url
        if 'github.com' in url and '/blob/' in url:
            raw_url = url.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')
        
        resp = requests.get(raw_url)
        resp.raise_for_status()
        with open(dest_path, 'wb') as f:
            f.write(resp.content)

    @staticmethod
    def download_folder(url, dest_dir):
        info = GitHubDownloader._parse_url(url)
        if not info:
            raise ValueError(f"URL de GitHub inválida: {url}")
            
        # Paso 1: Obtener el SHA de la rama para poder usar la API de Trees
        # (Si no tenemos el SHA del subdirectorio, la API de Trees recursiva es más difícil,
        # así que usaremos un truco: listar la rama principal recursivamente y filtrar)
        
        api_base = f"https://api.github.com/repos/{info['owner']}/{info['repo']}"
        
        # Obtener el SHA de la rama (branch)
        branch_resp = requests.get(f"{api_base}/branches/{info['branch']}")
        branch_resp.raise_for_status()
        tree_sha = branch_resp.json()['commit']['commit']['tree']['sha']
        
        # Obtener el árbol completo (recursivo) - Soporta hasta 100,000 archivos
        tree_url = f"{api_base}/git/trees/{tree_sha}?recursive=1"
        tree_resp = requests.get(tree_url)
        tree_resp.raise_for_status()
        tree_data = tree_resp.json()
        
        # El path en la URL puede estar vacío o ser algo como "script"
        target_path = info['path'].strip('/')
        
        files_to_download = []
        for item in tree_data.get('tree', []):
            if item['type'] == 'blob':
                item_path = item['path']
                if target_path == "" or item_path.startswith(target_path + "/"):
                    if item_path.endswith('.lua') or item_path.endswith('.cdb'):
                        download_url = f"https://raw.githubusercontent.com/{info['owner']}/{info['repo']}/{info['branch']}/{item_path}"
                        files_to_download.append((item['path'], download_url))
        
        # Actualizar progreso inicial
        global GLOBAL_PROGRESS
        GLOBAL_PROGRESS['total'] = len(files_to_download)
        GLOBAL_PROGRESS['current'] = 0
        GLOBAL_PROGRESS['last_file'] = 'Preparando...'

        if not files_to_download:
            # Fallback
            api_url = f"{api_base}/contents/{info['path']}?ref={info['branch']}"
            resp = requests.get(api_url)
            resp.raise_for_status()
            items = resp.json()
            if isinstance(items, list):
                for item in items:
                    if item['type'] == 'file':
                        files_to_download.append((item['name'], item['download_url']))
            GLOBAL_PROGRESS['total'] = len(files_to_download)

        # Descargar los archivos encontrados
        for path_in_repo, d_url in files_to_download:
            filename = os.path.basename(path_in_repo)
            file_dest = os.path.join(dest_dir, filename)
            
            GLOBAL_PROGRESS['last_file'] = filename
            
            try:
                f_resp = requests.get(d_url)
                f_resp.raise_for_status()
                with open(file_dest, 'wb') as f:
                    f.write(f_resp.content)
                GLOBAL_PROGRESS['current'] += 1
            except Exception as e:
                print(f"Error descargando {path_in_repo}: {e}")

if __name__ == "__main__":
    main()
