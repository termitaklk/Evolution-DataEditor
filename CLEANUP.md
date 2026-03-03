# Limpieza del proyecto (qué se usa y qué no)

Este repo tiene 2 modos típicos de uso:

1) **Ejecutar desde código fuente (Python)**: `python srt_advanced.py`
2) **Ejecutar el binario ya compilado**: `dist/AnalizadorScriptsYuGiOh.exe`

---

## Archivos/carpetas necesarios (modo código fuente)

- `srt_advanced.py` (servidor + lógica principal)
- `index.html` (UI del editor/analyzer)
- `card_decoder.py` (decodificación de Type/Setname/Rule/etc)
- `editor_constants.py` (carga/caché de constantes de `cardinfo_english.txt`)
- `card_info_parser.py` (parser de `cardinfo_english.txt`)
- `config_app.json` (config local: rutas de CDB/scripts/strings/pics)
- `config/cardinfo_english.txt` (tablas: rule/attribute/level/type/category/flags/setname)
- `script/` **solo si** tu `config_app.json` apunta ahí para leer `constant.lua / procedure.lua / utility.lua` (análisis)

Notas:
- `resultados.json` se genera cuando corres el análisis; la UI lo intenta leer en algunas pantallas. Si no existe, se regenerará cuando vuelvas a ejecutar análisis.

---

## Archivos necesarios (modo EXE)

- `dist/AnalizadorScriptsYuGiOh.exe`

`build/` y el `.spec` solo sirven para volver a compilar.

---

## Utilidades (opcionales)

Estos scripts NO son necesarios para que la app corra, pero son útiles para tareas puntuales:

- `export_editor_cards.py` (genera `editor_cards.json`)
- `inspect_editor_cards.py`
- `inspect_cardinfo.py`
- `resolve_unknown_sets.py` (usa `editor_cards.json`, genera `unknown_set_candidates.json`)
- `stats_editor_cards.py`
- `tests/` (solo para tests)
- `run_tests.ps1`, `run_tests.sh`

---

## Basura / generados (candidatos a borrar)

Generalmente se pueden borrar sin romper nada (se regeneran):

- `__pycache__/`
- `.pytest_cache/`
- `build/` (PyInstaller build)
- `resultados.json` (se regenera al correr análisis)
- `editor_cards.json` (solo si NO usas `export_editor_cards.py` / `resolve_unknown_sets.py` / `stats_editor_cards.py`)
- `unknown_set_candidates.json` (solo si NO lo estás usando)

“No usados por la app” pero pueden servirte como referencia/histórico:

- `Backup/`, `backup2/`
- `temp_dataeditorx/` (proyecto original DataEditorX de referencia)

---

## Cómo limpiar

Ejecuta el script:

- `powershell -ExecutionPolicy Bypass -File cleanup_unused.ps1`

Por defecto **solo** borra cachés y outputs regenerables. Si quieres borrar también utilidades y referencias, edita el script o ejecútalo con `-Aggressive`.

Ejemplos:

- Mantener el EXE pero limpiar cachés/build: `powershell -ExecutionPolicy Bypass -File cleanup_unused.ps1 -KeepExe`
- Limpieza fuerte (borra utilidades, referencias y JSON grandes): `powershell -ExecutionPolicy Bypass -File cleanup_unused.ps1 -Aggressive`
