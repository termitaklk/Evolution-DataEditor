"""
card_info_parser.py
===================
Fiel a DataManager.cs de DataEditorX.
Parsea el formato `cardinfo_english.txt` con secciones ##tag separadas
por tabulador, devolviendo diccionarios {int → str} por sección.

Reglas de parseo (espejadas desde DataManager.cs):
- Líneas con ## inician una nueva sección (tag).
- Líneas con # (solo #) o que empiezan con # pero no ## son ignoradas.
- Separador de columna es tabulador.
- Claves en formato hex (0x...) o decimal.
- Clave -1 es válida (Custom).
- Valores "N/A" son ignorados (no se incluyen en el resultado).
- Si una clave ya existe, no se sobreescribe (primera ocurrencia gana).
- Soporte especial para líneas "!setname KEY VALUE" (EdoPro strings.conf).
"""

from __future__ import annotations
import re
from typing import Dict


# Tipo principal: sección → {clave_entera → nombre}
CardInfoData = Dict[str, Dict[int, str]]


def parse_cardinfo_file(path: str, encoding: str = "utf-8") -> CardInfoData:
    """
    Lee un archivo con formato cardinfo_english.txt y lo parsea.
    Devuelve un dict cuyas claves son los nombres de sección (sin los ##)
    y cuyos valores son dicts {int: str}.

    Args:
        path: Ruta absoluta al archivo cardinfo_*.txt
        encoding: Codificación del archivo (por defecto utf-8)

    Returns:
        CardInfoData
    """
    try:
        with open(path, "r", encoding=encoding, errors="ignore") as f:
            content = f.read()
    except OSError as e:
        raise FileNotFoundError(f"No se pudo abrir {path}: {e}") from e

    return parse_cardinfo_string(content)


def parse_cardinfo_string(content: str) -> CardInfoData:
    """
    Parsea el contenido de un cardinfo_*.txt ya leído en memoria.
    Idéntico al comportamiento de DataManager.Read(content, tag) en C#.
    """
    # Normalizar saltos de línea (Windows/Unix/Mac)
    text = content.replace("\r\n", "\n").replace("\r", "\n")

    data: CardInfoData = {}
    current_section: str | None = None

    for raw_line in text.split("\n"):
        line = raw_line.strip()

        # Línea vacía → saltar
        if not line:
            continue

        # --- Inicio de sección: ##tag ---
        # Solo tratar como sección si después de '##' hay un nombre legible
        m = re.match(r'^##\s*([A-Za-z0-9].*)', line)
        if m:
            current_section = m.group(1).strip()
            if current_section not in data:
                data[current_section] = {}
            continue
        # Si empieza con ## pero no tiene nombre legible, ignorar como comentario
        if line.startswith("##"):
            continue

        # --- Fin de archivo o comentario simple: #end, # ... ---
        if line.startswith("#"):
            continue

        # --- Soporte para "!setname KEY VALUE" (EdoPro strings.conf) ---
        if line.startswith("!setname "):
            if current_section is None:
                # Crear sección virtual si no hay una activa
                current_section = "setname"
                data.setdefault(current_section, {})
            parts = line.split(" ", 2)
            if len(parts) >= 3:
                key = _parse_key(parts[1])
                if key is not None:
                    value = parts[2].strip()
                    # Excluir únicamente valores marcados como N/A
                    if value == "N/A":
                        continue
                    section_dict = data.setdefault(current_section, {})
                    if key not in section_dict:
                        section_dict[key] = value
            continue

        # --- Línea normal: key\tvalue (puede haber más columnas) ---
        # Algunos archivos (o ediciones manuales) usan espacios en vez de tabulador.
        # DataEditorX usa tabulador, pero aceptar ambos mejora la robustez sin romper el formato oficial.
        if current_section is None:
            continue

        if "\t" in line:
            parts = line.split("\t")
        else:
            # Fallback: split por espacios (solo 2 columnas: key + resto)
            parts = re.split(r"\s+", line, maxsplit=1)

        if len(parts) < 2:
            continue

        key = _parse_key(parts[0].strip())
        if key is None:
            continue

        # Unir columnas adicionales (permitir valores vacíos)
        value = " ".join(p.strip() for p in parts[1:])
        # Excluir únicamente valores marcados como N/A; aceptar cadena vacía
        if value == "N/A":
            continue

        section_dict = data[current_section]
        # Primera ocurrencia gana (mismo comportamiento que C#)
        if key not in section_dict:
            section_dict[key] = value

    return data


def _parse_key(raw: str) -> int | None:
    """
    Convierte una cadena de clave en entero.
    Soporta: '0x1A' (hex), '-1' (negativo), '42' (decimal).
    Devuelve None si no se puede parsear.
    """
    raw = raw.strip()
    try:
        if raw.lower().startswith("0x"):
            return int(raw, 16)
        return int(raw)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Helpers para resolver valores desde los diccionarios parseados
# ---------------------------------------------------------------------------

def get_value(section_dict: Dict[int, str], key: int, default: str = "") -> str:
    """
    Espejo de DataManager.GetValue en C#.
    Devuelve el valor si existe, o el key en hex como fallback.
    """
    if key in section_dict:
        return section_dict[key].strip()
    if default:
        return default
    return f"{key:x}"


def get_flags(section_dict: Dict[int, str], bitmask: int) -> list[str]:
    """
    Extrae todos los flags activos de un bitmask dado un diccionario de bits → nombre.
    Ignora las claves 0 y -1 (placeholders de sección).
    """
    flags: list[str] = []
    for bit_val, name in section_dict.items():
        if bit_val <= 0:
            continue
        if (bitmask & bit_val) == bit_val:
            flags.append(name.strip())
    return flags
