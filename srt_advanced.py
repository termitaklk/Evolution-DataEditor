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
import urllib.parse
import requests
import shutil
import sys
import queue
from editor_constants import load_editor_constants

# Cola para comunicación entre hilos (HTTP -> Principal)
DIALOG_QUEUE = queue.Queue()

GLOBAL_PROGRESS = {'total': 0, 'current': 0, 'last_file': ''}
CURRENT_LANG = 'es'
CURRENT_PICS_DIR = None
CONFIG_FILE = 'config_app.json'

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return {}

def save_config(config):
    try:
        current = load_config()
        current.update(config)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(current, f, indent=4)
        return True
    except: return False

# Cargar configuración inicial
INITIAL_CONFIG = load_config()
CURRENT_PICS_DIR = INITIAL_CONFIG.get('pics_dir')

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

def load_lua_procedures(script_dir):
    procedures = {}
    if not os.path.exists(script_dir): return procedures
    
    target_files = ['procedure.lua', 'utility.lua', 'constant.lua']
    
    # Patrón para encontrar funciones de procedimiento y su SetDescription interno
    func_pattern = re.compile(r'function\s+(?:aux\.)?([A-Za-z0-9_]+)\s*\(.*?\)(.*?)end', re.DOTALL)
    desc_pattern = re.compile(r'SetDescription\s*\(\s*(\d+|[A-Z0-9_]+)\s*\)')
    
    # Pre-cargamos constantes para resolver nombres dentro de SetDescription
    constants = load_lua_constants(script_dir)
    
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
    stringid_full_pattern = r'aux\.Stringid\s*\(([^)]+)\)'
    for match in re.finditer(stringid_full_pattern, content, re.DOTALL):
        args_text = match.group(1)
        # Buscar todos los números independientes que parezcan índices (0-15)
        potential_indices = re.findall(r'\b(\d+)\b', args_text)
        for num_str in potential_indices:
            num_val = int(num_str)
            # Un índice de string siempre es 0-15. Si es mayor, probablemente es un ID de carta.
            if 0 <= num_val <= 15:
                found_details.append({'type': 'CDB', 'id': num_val, 'code': match.group(0).strip()})

    set_desc_patterns = [r'SetDescription\s*\(\s*(\d{1,8})\s*\)', r'SetDescription\s*\(\s*([A-Z0-9_]+)\s*\)']
    for p_regex in set_desc_patterns:
        for match in re.finditer(p_regex, content, re.DOTALL):
            m = match.group(1)
            # Ignorar CARD_QUESTION (caso especial del cliente)
            if m == "CARD_QUESTION": continue
            
            val = None
            if m.isdigit(): val = int(m)
            elif m in lua_constants: val = lua_constants[m]
            if val is not None:
                found_details.append({'type': 'SYS', 'id': val, 'code': match.group(0).strip()})
    
    hint_pattern = r'Duel\.Hint\s*\(\s*([^,]+)\s*,\s*[^,]+\s*,\s*(\d+|[A-Z0-9_]+)\s*\)'
    for match in re.finditer(hint_pattern, content, re.DOTALL):
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
    select_yn_patterns = [
        r'Duel\.SelectEffectYesNo\s*\(\s*[^,]+\s*,\s*[^,]+\s*,\s*(\d+|[A-Z0-9_]+)\s*\)',
        r'Duel\.SelectYesNo\s*\(\s*[^,]+\s*,\s*(\d+|[A-Z0-9_]+)\s*\)'
    ]
    for p_regex in select_yn_patterns:
        for match in re.finditer(p_regex, content, re.DOTALL):
            m = match.group(1)
            # Si m es parte de un aux.Stringid, ya se capturó arriba
            val = None
            if m.isdigit(): val = int(m)
            elif m in lua_constants: val = lua_constants[m]
            if val is not None:
                found_details.append({'type': 'SYS', 'id': val, 'code': match.group(0).strip()})

    option_pattern = r'Duel\.SelectOption\s*\(\s*[^,]+\s*,\s*((?:[^()]|\([^()]*\))*)\s*\)'
    for match in re.finditer(option_pattern, content, re.DOTALL):
        full_call = match.group(0).strip()
        arg_text = match.group(1)
        nested_stringid = r'aux\.Stringid\s*\(\s*(\d+|id|s|[A-Z0-9_]+)\s*,\s*(\d+)\s*\)'
        for ns_match in re.finditer(nested_stringid, arg_text, re.DOTALL):
            found_details.append({'type': 'CDB', 'id': int(ns_match.group(2)), 'code': full_call})
        clean_args = re.sub(nested_stringid, " ", arg_text, flags=re.DOTALL)
        item_pattern = r'\b(\d+|[A-Z0-9_]+)\b'
        for item_match in re.finditer(item_pattern, clean_args):
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
    if not os.path.exists(path): return sys_strings
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if line.startswith('!system'):
                parts = line.split(' ', 2)
                if len(parts) >= 3:
                    try: sys_strings[int(parts[1])] = parts[2].strip()
                    except: pass
    return sys_strings

# --- MOTOR DE ANÁLISIS ---
def run_analysis(cdb_dir, strings_conf, script_dir):
    lua_constants = load_lua_constants(script_dir)
    lua_procedures = load_lua_procedures(script_dir)
    sys_strings = load_system_strings(strings_conf)
    
    results = {'coincidencias': [], 'anomalias': [], 'faltantes': [], 'scripts_faltantes': [], 'excluidas': []}
    
    if not os.path.exists(cdb_dir): return results
    cdb_files = [f for f in os.listdir(cdb_dir) if f.endswith('.cdb')]
    
    for cdb_file in cdb_files:
        cdb_path = os.path.join(cdb_dir, cdb_file)
        conn = sqlite3.connect(cdb_path)
        cursor = conn.cursor()
        try:
            # JOIN con datas para filtrar monstruos normales (vanilla) con type 17
            cursor.execute("""
                SELECT t.id, t.name, t.desc, 
                       t.str1, t.str2, t.str3, t.str4, t.str5, t.str6, t.str7, t.str8, 
                       t.str9, t.str10, t.str11, t.str12, t.str13, t.str14, t.str15, t.str16 
                FROM texts t
                JOIN datas d ON t.id = d.id
                WHERE d.type != 17 AND d.type != 16401 AND d.alias = 0
            """)
            rows = cursor.fetchall()
            
            # Capturar las cartas excluidas para el reporte
            cursor.execute("""
                SELECT t.id, t.name, d.type, d.alias
                FROM texts t
                JOIN datas d ON t.id = d.id
                WHERE d.type = 17 OR d.type = 16401 OR d.alias != 0
            """)
            excl_rows = cursor.fetchall()
            for r in excl_rows:
                reason = "Ficha/Token" if r[2] == 16401 else ("Monstruo Normal" if r[2] == 17 else f"Alias de {r[3]}")
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
            
            # Verificar si el script existe antes de analizar
            if not os.path.exists(script_full_path):
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

            script_details = analyze_script(script_full_path, card_id, lua_constants, lua_procedures)
            if script_details is None: script_details = []
            
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
        parsed_path = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed_path.query)
        lang = query.get('lang', ['es'])[0]
        title_key = query.get('title_key', [None])[0]
        
        # Sincronizar idioma del backend con el del frontend para las utilidades t()
        global CURRENT_LANG
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
            # Servir imágenes de la carpeta PICs seleccionada
            if CURRENT_PICS_DIR and os.path.exists(CURRENT_PICS_DIR):
                filename = parsed_path.path[6:] # Eliminar '/pics/'
                img_path = os.path.join(CURRENT_PICS_DIR, filename)
                if os.path.exists(img_path):
                    self.send_response(200)
                    mime = 'image/jpeg' if filename.lower().endswith('.jpg') else 'image/png'
                    self.send_header('Content-type', mime)
                    self.end_headers()
                    with open(img_path, 'rb') as f:
                        self.wfile.write(f.read())
                else:
                    self.send_error(404)
        elif parsed_path.path == '/api/editor/load':
            config = load_config()
            cdb_dir = config.get('cdb_dir')
            all_cards = []
            if cdb_dir and os.path.exists(cdb_dir):
                # Pre-cargar constantes para decodificar tipos y setcodes
                from card_decoder import CardDecoder
                editor_constants = load_editor_constants()
                decoder = CardDecoder(editor_constants)

                cdb_files = [f for f in os.listdir(cdb_dir) if f.endswith('.cdb')]
                for cdb_file in cdb_files:
                    cdb_path = os.path.join(cdb_dir, cdb_file)
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
        elif parsed_path.path == '/api/get_config':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(load_config()).encode())
        elif parsed_path.path == '/api/editor/constants':
            constants = load_editor_constants()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(json.dumps(constants).encode())
        else:
            super().do_GET()

    def do_POST(self):
        global CURRENT_PICS_DIR
        if self.path == '/api/run':
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
                    
                # Guardar configuración local para persistencia
                save_config({
                    'cdb_dir': cdb_dir,
                    'script_dir': script_dir,
                    'strings_conf': strings_conf,
                    'pics_dir': params.get('pics_dir')
                })
                
                CURRENT_PICS_DIR = params.get('pics_dir')

                results = run_analysis(cdb_dir, strings_conf, script_dir)
                
                with open('resultados.json', 'w', encoding='utf-8') as f:
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
                
        elif self.path == '/api/editor/analyze_card':
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
        elif self.path == '/api/config':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            params = json.loads(post_data)
            
            save_config(params)
            
            if params.get('pics_dir'):
                CURRENT_PICS_DIR = params.get('pics_dir')
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok'}).encode())
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
                    path = filedialog.askopenfilename(title=title)
                
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
