"""
editor_constants.py

Carga y cachea las constantes del editor desde `config/cardinfo_english.txt`.

Se separa de `srt_advanced.py` para que los scripts CLI (export/inspect/resolve)
no tengan que importar Tkinter/requests/servidor HTTP cuando solo necesitan
las constantes.
"""

from __future__ import annotations

import os
import sys

from card_info_parser import parse_cardinfo_file


DEFAULT_CONSTANTS_PATH = os.path.join("config", "cardinfo_english.txt")

_CACHE: dict[tuple[str, str], tuple[float, dict[str, dict[int, str]]]] = {}


def _resolve_constants_path(path: str) -> str:
    candidate = str(path or "").strip()
    if not candidate:
        candidate = DEFAULT_CONSTANTS_PATH

    if os.path.exists(candidate):
        return candidate

    base_meipass = getattr(sys, "_MEIPASS", "")
    if base_meipass:
        p = os.path.join(base_meipass, candidate)
        if os.path.exists(p):
            return p

    base_file = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(base_file, candidate)
    if os.path.exists(p):
        return p

    return candidate


def load_editor_constants(
    path: str = DEFAULT_CONSTANTS_PATH,
    encoding: str = "utf-8",
    force: bool = False,
) -> dict[str, dict[int, str]]:
    """
    Parsea `cardinfo_english.txt` usando `card_info_parser` (fiel a DataManager.cs).
    Devuelve dict[str, dict[int, str]] con todas las secciones del archivo.
    """
    resolved_path = _resolve_constants_path(path)
    if not resolved_path or not os.path.exists(resolved_path):
        return {}
    try:
        mtime = os.path.getmtime(resolved_path)
    except OSError:
        mtime = -1.0

    cache_key = (resolved_path, encoding)
    if not force:
        cached = _CACHE.get(cache_key)
        if cached and cached[0] == mtime:
            return cached[1]
    try:
        data = parse_cardinfo_file(resolved_path, encoding=encoding)
        _CACHE[cache_key] = (mtime, data)
        return data
    except Exception as e:
        print(f"Error loading constants from {path}: {e}")
        return {}
