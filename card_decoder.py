"""
card_decoder.py
===============
Decodificador de datos de cartas Yu-Gi-Oh! leídas desde bases de datos .cdb.
Replica la lógica de YGOUtil.cs de DataEditorX (C#).

Campos de la tabla `datas`:
    id, ot, alias, setcode, type, atk, def, level, race, attribute, category

Campos de la tabla `texts`:
    id, name, desc, str1..str16
"""

from __future__ import annotations
from typing import Any

# Máscaras de tipo de carta (espejo de CardType enum en DataEditorX)
TYPE_MONSTER   = 0x1
TYPE_SPELL     = 0x2
TYPE_TRAP      = 0x4
TYPE_NORMAL    = 0x10
TYPE_EFFECT    = 0x20
TYPE_FUSION    = 0x40
TYPE_RITUAL    = 0x80
TYPE_SPIRIT    = 0x200
TYPE_UNION     = 0x400
TYPE_GEMINI    = 0x800
TYPE_TUNER     = 0x1000
TYPE_SYNCHRO   = 0x2000
TYPE_TOKEN     = 0x4000
TYPE_QUICKPLAY = 0x10000
TYPE_CONTINUOUS= 0x20000
TYPE_EQUIP     = 0x40000
TYPE_FIELD     = 0x80000
TYPE_COUNTER   = 0x100000
TYPE_FLIP      = 0x200000
TYPE_TOON      = 0x400000
TYPE_XYZ       = 0x800000
TYPE_PENDULUM  = 0x1000000
TYPE_SPSUMMON  = 0x2000000
TYPE_LINK      = 0x4000000

# Bits de link markers en el campo `level` de las cartas Link
LINK_MARKER_BITS = {
    0x1:   "↙",
    0x2:   "↓",
    0x4:   "↘",
    0x8:   "←",
    # 0x10 reservado
    0x20:  "→",
    0x40:  "↖",
    0x80:  "↑",
    0x100: "↗",
}

SETCODE_MAX = 4  # Máximo de setcodes empaquetados en el campo `setcode`


class CardDecoder:
    """
    Decodificador de datos de cartas Yu-Gi-Oh!

    Se inicializa con un diccionario de constantes del editor (cardinfo_english.txt),
    separado por sección: {'type': {int: str}, 'race': {int: str}, ...}.
    """

    def __init__(self, constants: dict[str, dict[int, str]] | None = None):
        self.constants = constants or {}
        # Secciones del cardinfo
        self.types      = self.constants.get("type", {})
        self.attributes = self.constants.get("attribute", {})
        self.races      = self.constants.get("race", {})
        self.categories = self.constants.get("category (genre)", {})
        self.setnames   = self.constants.get("setname", {})
        self.rules      = self.constants.get("rule", {})
        self.flags_cat  = self.constants.get("flags (category)", {})

    # ------------------------------------------------------------------
    # Métodos de bajo nivel
    # ------------------------------------------------------------------

    def _get_value(self, section_dict: dict[int, str], key: int, default: str = "") -> str:
        """Espejo de DataManager.GetValue en C#."""
        if key in section_dict:
            return section_dict[key].strip()
        return default if default else f"{key:x}"

    def decode_flags(self, value: int, constant_dict: dict[int, str]) -> list[str]:
        """Extrae flags activos desde un bitmask."""
        flags: list[str] = []
        for bit_val, name in constant_dict.items():
            if bit_val <= 0:
                continue
            if (value & bit_val) == bit_val:
                flags.append(name.strip())
        return flags

    # ------------------------------------------------------------------
    # Decodificadores de campo
    # ------------------------------------------------------------------

    def decode_ot(self, ot_val: int) -> dict[str, Any]:
        """Decodifica la regla (ot): OCG, TCG, Custom, etc."""
        name = self._get_value(self.rules, ot_val, f"Unknown Rule ({ot_val})")
        return {
            "ot_decimal": ot_val,
            "ot_hex": hex(ot_val),
            "ot_name": name
        }

    def decode_type(self, type_val: int) -> dict[str, Any]:
        """Decodifica el bitmask de tipo de carta."""
        flags = self.decode_flags(type_val, self.types)
        return {
            "type_decimal": type_val,
            "type_hex": hex(type_val),
            "isMonster":  bool(type_val & TYPE_MONSTER),
            "isSpell":    bool(type_val & TYPE_SPELL),
            "isTrap":     bool(type_val & TYPE_TRAP),
            "isPendulum": bool(type_val & TYPE_PENDULUM),
            "isLink":     bool(type_val & TYPE_LINK),
            "isXyz":      bool(type_val & TYPE_XYZ),
            "isSynchro":  bool(type_val & TYPE_SYNCHRO),
            "isFusion":   bool(type_val & TYPE_FUSION),
            "isRitual":   bool(type_val & TYPE_RITUAL),
            "isToken":    bool(type_val & TYPE_TOKEN),
            "typeFlags":  flags,
        }

    def get_type_string(self, type_val: int) -> str:
        """
        Réplica de YGOUtil.GetTypeString(long type) en C#.
        Devuelve todos los flags activos unidos con '|'.
        Ejemplo: "Monster|Effect|Pendulum"
        """
        parts = []
        for bit_val, name in sorted(self.types.items()):
            if bit_val <= 0:
                continue
            if (type_val & bit_val) == bit_val:
                parts.append(name.strip())
        return "|".join(parts) if parts else "???"

    def get_card_type_display(self, type_val: int) -> str:
        """
        Réplica de YGOUtil.GetCardType(Card c) en C#.
        Devuelve un string legible como "Effect Monster", "Quick-Play Spell", etc.
        """
        def gtype(mask: int) -> str:
            return self._get_value(self.types, mask, "")

        if type_val & TYPE_MONSTER:
            # Tipo principal del monstruo
            if type_val & TYPE_TOKEN:
                prefix = gtype(TYPE_TOKEN)
            elif type_val & TYPE_XYZ:
                prefix = gtype(TYPE_XYZ)
            elif type_val & TYPE_LINK:
                prefix = gtype(TYPE_LINK)
            elif type_val & TYPE_SYNCHRO:
                prefix = gtype(TYPE_SYNCHRO)
            elif type_val & TYPE_FUSION:
                prefix = gtype(TYPE_FUSION)
            elif type_val & TYPE_RITUAL:
                prefix = gtype(TYPE_RITUAL)
            elif type_val & TYPE_EFFECT:
                prefix = gtype(TYPE_EFFECT)
            else:
                prefix = gtype(TYPE_NORMAL)
            # Subtipos adicionales notables
            extras = []
            if type_val & TYPE_PENDULUM:
                extras.append(gtype(TYPE_PENDULUM))
            if type_val & TYPE_TUNER and not (type_val & TYPE_SYNCHRO):
                extras.append(gtype(TYPE_TUNER))
            if type_val & TYPE_FLIP:
                extras.append(gtype(TYPE_FLIP))
            if type_val & TYPE_TOON:
                extras.append(gtype(TYPE_TOON))
            if type_val & TYPE_SPIRIT:
                extras.append(gtype(TYPE_SPIRIT))
            if type_val & TYPE_GEMINI:
                extras.append(gtype(TYPE_GEMINI))
            if type_val & TYPE_UNION:
                extras.append(gtype(TYPE_UNION))
            suffix = gtype(TYPE_MONSTER)
            parts = [p for p in [prefix] + extras + [suffix] if p]
            return " ".join(parts)

        elif type_val & TYPE_SPELL:
            if type_val & TYPE_EQUIP:
                prefix = gtype(TYPE_EQUIP)
            elif type_val & TYPE_QUICKPLAY:
                prefix = gtype(TYPE_QUICKPLAY)
            elif type_val & TYPE_FIELD:
                prefix = gtype(TYPE_FIELD)
            elif type_val & TYPE_CONTINUOUS:
                prefix = gtype(TYPE_CONTINUOUS)
            elif type_val & TYPE_RITUAL:
                prefix = gtype(TYPE_RITUAL)
            else:
                prefix = gtype(TYPE_NORMAL)
            suffix = gtype(TYPE_SPELL)
            parts = [p for p in [prefix, suffix] if p]
            return " ".join(parts)

        elif type_val & TYPE_TRAP:
            if type_val & TYPE_CONTINUOUS:
                prefix = gtype(TYPE_CONTINUOUS)
            elif type_val & TYPE_COUNTER:
                prefix = gtype(TYPE_COUNTER)
            else:
                prefix = gtype(TYPE_NORMAL)
            suffix = gtype(TYPE_TRAP)
            parts = [p for p in [prefix, suffix] if p]
            return " ".join(parts)

        return "???"

    def decode_attribute(self, attr_val: int) -> dict[str, Any]:
        """Decodifica el atributo del monstruo."""
        flags = self.decode_flags(attr_val, self.attributes)
        name = flags[0] if flags else self._get_value(self.attributes, attr_val, "???")
        return {
            "attribute_decimal": attr_val,
            "attribute_hex": hex(attr_val),
            "attribute_name": name,
            "attributeFlags": flags,
        }

    def decode_race(self, race_val: int) -> dict[str, Any]:
        """Decodifica la raza del monstruo."""
        flags = self.decode_flags(race_val, self.races)
        name = flags[0] if flags else self._get_value(self.races, race_val, "???")
        return {
            "race_decimal": race_val,
            "race_hex": hex(race_val),
            "race_name": name,
            "raceFlags": flags,
        }

    def decode_category(self, cat_val: int) -> dict[str, Any]:
        """Decodifica las categorías de efecto."""
        flags = self.decode_flags(cat_val, self.categories)
        return {
            "category_decimal": cat_val,
            "category_hex": hex(cat_val),
            "categoryFlags": flags,
        }

    def decode_setcode(self, setcode_val: int) -> dict[str, Any]:
        """
        Decodifica el setcode empaquetado (hasta 4 bloques de 16 bits).
        Réplica de Card.GetSetCode() y YGOUtil.GetSetNameString() de DataEditorX.

        Cada bloque de 16 bits es un setcode completo (incluyendo subtipo en bits 12-15).
        Se busca la clave exacta de 16 bits en el diccionario de setnames.
        """
        setcodes: list[int] = []
        setnames: list[str] = []

        val = setcode_val
        for _ in range(SETCODE_MAX):
            part = val & 0xFFFF
            setcodes.append(part)
            if part != 0:
                name = self._resolve_setname(part)
                setnames.append(name)
            val >>= 16

        # Eliminar los ceros de la lista interna pero conservar los índices
        active_setcodes     = [c for c in setcodes if c != 0]
        active_setnames     = setnames  # Ya excluidos los cero
        active_setcodes_hex = [hex(c) for c in active_setcodes]

        return {
            "setcode_decimal": setcode_val,
            "setcode_hex": hex(setcode_val),
            "setcodes": active_setcodes,
            "setcodes_hex": active_setcodes_hex,
            "setnames": active_setnames,
            "setnames_display": ", ".join(active_setnames) if active_setnames else "",
        }

    def _resolve_setname(self, code16: int) -> str:
        """
        Resuelve el nombre de un setcode de 16 bits.
        Un code16 puede ser:
          - Solo base (e.g. 0x0008 = HERO)
          - Base + subtipo (e.g. 0x3008 = Elemental HERO)
        Se busca primero la clave exacta de 16 bits, luego el base de 12 bits.
        """
        # 1. Búsqueda exacta (incluye subtipo)
        if code16 in self.setnames:
            return self.setnames[code16].strip()
        # 2. Búsqueda por base (12 bits bajos) si el subtipo no tiene nombre propio
        base = code16 & 0x0FFF
        if base != code16 and base in self.setnames:
            return self.setnames[base].strip()
        return f"Unknown Set (0x{code16:X})"

    def get_setname_string(self, setcode_val: int) -> str:
        """
        Réplica de YGOUtil.GetSetNameString(long setcode).
        Devuelve los nombres de los 4 bloques separados por espacio.
        """
        parts: list[str] = []
        for i in range(SETCODE_MAX):
            sc = (setcode_val >> (i * 16)) & 0xFFFF
            if sc != 0:
                parts.append(self._resolve_setname(sc))
        return " ".join(parts)

    def decode_level(self, level_val: int, type_val: int, def_val: int = 0) -> dict[str, Any]:
        """
        Decodifica el campo `level`.
        - Monstruos normales: level = level_val & 0xFF
        - Péndulo: escala izquierda = bits 24-31, derecha = bits 16-23
        - Link: rating = level_val & 0xFF, markers en bits 8+ (algunas DB los guardan en `def`)
        """
        level = level_val & 0xFF
        result: dict[str, Any] = {
            "level_decimal": level_val,
            "level_hex": hex(level_val),
            "level": level,
        }

        if type_val & TYPE_PENDULUM:
            result["lscale"] = (level_val >> 24) & 0xFF
            result["rscale"] = (level_val >> 16) & 0xFF

        if type_val & TYPE_LINK:
            # Rating = nivel del link
            result["link_rating"] = level
            # Link markers: normalmente en los bits del nivel por encima de 0xFF.
            # Nota: algunas bases de datos guardan los marcadores en `def` (porque los Link no tienen DEF).
            marker_mask_from_level = (int(level_val) >> 8) & 0x1FF
            marker_mask = marker_mask_from_level
            if marker_mask == 0:
                try:
                    marker_mask = int(def_val or 0) & 0x1FF
                except Exception:
                    marker_mask = 0

            markers: list[str] = []
            for bit, arrow in LINK_MARKER_BITS.items():
                if (marker_mask & bit) == bit:
                    markers.append(arrow)
            result["link_markers"] = markers

        return result

    # ------------------------------------------------------------------
    # Método principal de análisis de una fila de carta
    # ------------------------------------------------------------------

    def analyzeCardRow(self, row_dict: dict[str, Any]) -> dict[str, Any]:
        """
        Análisis completo de una fila de carta.
        Espera un dict con: id, type, attribute, race, level, setcode, category,
        y opcionalmente: ot, alias, atk, def.

        Devuelve un dict enriquecido listo para serializar a JSON.
        """
        t_val   = row_dict.get("type", 0)
        lvl_val = row_dict.get("level", 0)

        analysis: dict[str, Any] = {}
        analysis["id"]   = row_dict.get("id", 0)
        analysis["type"] = self.decode_type(t_val)

        # Tipo legible (para mostrar en UI)
        analysis["type_display"]    = self.get_card_type_display(t_val)
        analysis["type_string"]     = self.get_type_string(t_val)

        # OT / Regla
        ot_val = row_dict.get("ot", 0)
        analysis["ot"] = self.decode_ot(ot_val)

        # Datos exclusivos de monstruos
        if analysis["type"]["isMonster"]:
            analysis["attribute"] = self.decode_attribute(row_dict.get("attribute", 0))
            analysis["race"]      = self.decode_race(row_dict.get("race", 0))
            analysis["level"]     = self.decode_level(lvl_val, t_val, def_val=row_dict.get("def", 0))
            analysis["atk"]       = row_dict.get("atk", 0)
            analysis["def"]       = row_dict.get("def", 0)

        # Setcodes (arquetipos)
        setcode_val = row_dict.get("setcode", 0)
        analysis["setcode"] = self.decode_setcode(setcode_val)

        # Categorías de efecto
        analysis["category"] = self.decode_category(row_dict.get("category", 0))

        # Alias
        analysis["alias"] = row_dict.get("alias", 0)

        # --- human_explanation: resumen legible para el usuario ---
        explanation_parts: list[str] = []

        explanation_parts.append(analysis["type_display"])

        if analysis["type"]["isMonster"]:
            attr = analysis.get("attribute", {})
            race = analysis.get("race", {})
            if attr.get("attribute_name"):
                explanation_parts.append(f"Attribute: {attr['attribute_name']}")
            if race.get("race_name"):
                explanation_parts.append(f"Race: {race['race_name']}")

        setnames = analysis["setcode"].get("setnames", [])
        if setnames:
            explanation_parts.append(f"Sets: {', '.join(setnames)}")

        analysis["human_explanation"] = ", ".join(explanation_parts)

        return analysis
