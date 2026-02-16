"""
Impulse Language Translator - Web Version
Created by: Stefc3
GitHub: github.com/Stefcee/-Cherax---Impulse-Lua-Translator-
Discord: dc.gg/chatify
"""

import os
import json
import io
import time
import uuid
import threading
from datetime import datetime, timedelta
from flask import Flask, render_template, request, send_file, jsonify, Response
from deep_translator import GoogleTranslator

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "impulse_web_key_2026")

# Vollständige 56-Sprachen-Liste
LANGUAGES = {
    "Afrikaans": "af", "Albanian": "sq", "Arabic": "ar", "Armenian": "hy", "Azerbaijani": "az",
    "Basque": "eu", "Belarusian": "be", "Bengali": "bn", "Bulgarian": "bg", "Catalan": "ca",
    "Chinese (Simp)": "zh-CN", "Chinese (Trad)": "zh-TW", "Croatian": "hr", "Czech": "cs",
    "Danish": "da", "Dutch": "nl", "English": "en", "Estonian": "et", "Filipino": "tl",
    "Finnish": "fi", "French": "fr", "Galician": "gl", "Georgian": "ka", "German": "de",
    "Greek": "el", "Gujarati": "gu", "Haitian Creole": "ht", "Hebrew": "iw", "Hindi": "hi",
    "Hungarian": "hu", "Icelandic": "is", "Indonesian": "id", "Irish": "ga", "Italian": "it",
    "Japanese": "ja", "Kannada": "kn", "Korean": "ko", "Latvian": "lv", "Lithuanian": "lt",
    "Macedonian": "mk", "Malay": "ms", "Maltese": "mt", "Norwegian": "no", "Persian": "fa",
    "Polish": "pl", "Portuguese": "pt", "Romanian": "ro", "Russian": "ru", "Serbian": "sr",
    "Slovak": "sk", "Slovenian": "sl", "Spanish": "es", "Swahili": "sw", "Swedish": "sv",
    "Tamil": "ta", "Telugu": "te", "Thai": "th", "Turkish": "tr", "Ukrainian": "uk",
    "Urdu": "ur", "Vietnamese": "vi", "Welsh": "cy", "Yiddish": "yi"
}

# Temporärer Speicher für übersetzte Dateien mit Timestamp
translated_files = {}

def cleanup_old_files():
    """Background-Task: Löscht Dateien älter als 1 Stunde"""
    while True:
        try:
            now = datetime.now()
            to_delete = []
            
            for file_id, file_data in translated_files.items():
                if 'timestamp' in file_data:
                    age = now - file_data['timestamp']
                    if age > timedelta(hours=1):
                        to_delete.append(file_id)
            
            for file_id in to_delete:
                del translated_files[file_id]
                print(f"🗑 Gelöscht: {file_id} (älter als 1 Stunde)")
            
            if to_delete:
                print(f"✅ Cleanup: {len(to_delete)} Dateien gelöscht")
        
        except Exception as e:
            print(f"⚠ Cleanup-Fehler: {e}")
        
        time.sleep(600)  # Alle 10 Minuten

# Cleanup-Task im Hintergrund starten
cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()

def flatten_dict(d, parent_key='', sep='|||'):
    """Flatten nested dictionary into flat structure for translation"""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

def unflatten_dict(d, sep='|||'):
    """Reconstruct nested dictionary from flat structure"""
    result = {}
    for key, value in d.items():
        parts = key.split(sep)
        current = result
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value
    return result

def log_message(msg_type, text):
    """Erstellt formatierte Log-Nachricht mit Timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    return f"data: {json.dumps({'type': msg_type, 'message': f'[{timestamp}] {text}'})}\n\n"

def translate_with_sse(data, target_lang, target_lang_name):
    """
    Generator-Funktion für Server-Sent Events mit nested JSON support
    """
    try:
        # Validate structure
        if "strings" not in data:
            yield log_message('error', '❌ Invalid JSON structure! Missing "strings" key.')
            yield f"data: {json.dumps({'type': 'error', 'message': 'Invalid structure'})}\n\n"
            return
        
        font_value = data.get("font", 0)
        
        yield log_message('info', '=' * 60)
        yield log_message('info', '🚀 Übersetzung gestartet...')
        yield log_message('info', '🔄 Flattening nested structure...')
        
        # Flatten nested structure
        flat_source = flatten_dict(data["strings"])
        
        translator = GoogleTranslator(source='auto', target=target_lang)
        flat_translated = {}
        keys = list(flat_source.keys())
        total_items = len(keys)
        separator = " ||| "
        batch_size = 50
        
        yield log_message('info', f'📊 Gesamt: {total_items} Einträge')
        yield log_message('info', f'🌍 Zielsprache: {target_lang_name} ({target_lang})')
        yield log_message('info', '-' * 60)
        
        batch_count = 0
        i = 0
        
        while i < len(keys):
            batch_keys = keys[i:i + batch_size]
            
            try:
                if len(batch_keys) == 1:
                    key = batch_keys[0]
                    value = flat_source[key]
                    if value is None or str(value).strip() == "":
                        flat_translated[key] = value
                    else:
                        flat_translated[key] = translator.translate(str(value))
                else:
                    # Batch-Übersetzung
                    batch_texts = [str(flat_source[k]) if flat_source[k] is not None else "" 
                                  for k in batch_keys]
                    combined = separator.join(batch_texts)
                    
                    translated_result = translator.translate(combined)
                    parts = translated_result.split(separator.strip())
                    
                    if len(parts) == len(batch_keys):
                        for idx, key in enumerate(batch_keys):
                            flat_translated[key] = parts[idx].strip() if parts[idx].strip() else flat_source[key]
                    else:
                        # Fallback: Einzelübersetzung
                        yield log_message('warning', '⚠ Batch mismatch, einzelne Übersetzung...')
                        for key in batch_keys:
                            value = flat_source[key]
                            if value is None or str(value).strip() == "":
                                flat_translated[key] = value
                            else:
                                try:
                                    flat_translated[key] = translator.translate(str(value))
                                    time.sleep(0.3)
                                except Exception as e:
                                    yield log_message('error', f'❌ Fehler bei "{key}": {str(e)}')
                                    flat_translated[key] = value
                
                i += len(batch_keys)
                batch_count += 1
                progress = len(flat_translated)
                percentage = int((progress / total_items) * 100)
                
                if batch_count % 10 == 0 or progress == total_items:
                    yield log_message('progress', f'⏳ Fortschritt: {progress}/{total_items} ({percentage}%)')
                    yield f"data: {json.dumps({'type': 'percentage', 'value': percentage})}\n\n"
                
                time.sleep(0.2)
                
            except Exception as e:
                yield log_message('error', f'❌ Fehler: {str(e)}')
                yield log_message('warning', f'⏸ Pausiert bei {len(flat_translated)}/{total_items}')
                break
        
        # Erfolgsmeldung
        if len(flat_translated) >= total_items:
            yield log_message('info', '🔄 Reconstructing nested structure...')
            
            # Reconstruct nested structure
            final_strings = unflatten_dict(flat_translated)
            
            final_output = {
                "font": font_value,
                "strings": final_strings
            }
            
            # Eindeutige ID für Download
            file_id = str(uuid.uuid4())
            lang_code_upper = target_lang.upper().replace('-', '_')
            translated_files[file_id] = {
                'data': final_output,
                'lang_code': lang_code_upper,
                'timestamp': datetime.now()
            }
            
            yield log_message('info', '=' * 60)
            yield log_message('success', '✅ ÜBERSETZUNG ABGESCHLOSSEN!')
            yield log_message('info', f'📊 {total_items}/{total_items} Einträge übersetzt')
            yield log_message('info', f'🌍 Sprache: {target_lang_name}')
            yield f"data: {json.dumps({'type': 'complete', 'file_id': file_id, 'lang_code': lang_code_upper})}\n\n"
        else:
            yield log_message('error', '❌ Übersetzung unvollständig')
            yield f"data: {json.dumps({'type': 'error', 'message': 'Übersetzung fehlgeschlagen'})}\n\n"
    
    except Exception as e:
        yield log_message('error', f'❌ Critical Error: {str(e)}')
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

@app.route('/', methods=['GET'])
def index():
    """Hauptseite mit Upload-Formular"""
    return render_template('index.html', languages=sorted(LANGUAGES.keys()))

@app.route('/translate', methods=['POST'])
def translate():
    """SSE-Endpoint für Echtzeit-Übersetzung"""
    try:
        file = request.files.get('file')
        target_lang_name = request.form.get('language')
        
        if not file or file.filename == '':
            return jsonify({'error': 'Keine Datei ausgewählt'}), 400
        
        if not target_lang_name or target_lang_name not in LANGUAGES:
            return jsonify({'error': 'Ungültige Sprache'}), 400
        
        # Dateigrößen-Check (Max 5MB)
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > 5 * 1024 * 1024:
            return jsonify({'error': 'Datei zu groß (max. 5MB)'}), 400
        
        # JSON laden
        try:
            content = json.load(file)
        except json.JSONDecodeError:
            return jsonify({'error': 'Ungültige JSON-Datei'}), 400
        
        target_code = LANGUAGES[target_lang_name]
        
        # SSE-Stream starten
        return Response(
            translate_with_sse(content, target_code, target_lang_name),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no'
            }
        )
        
    except Exception as e:
        print(f"Server error: {e}")
        return jsonify({'error': f'Serverfehler: {str(e)}'}), 500

@app.route('/download/<file_id>')
def download(file_id):
    """Download der übersetzten Datei"""
    if file_id not in translated_files:
        return jsonify({'error': 'Datei nicht gefunden oder abgelaufen'}), 404
    
    try:
        file_info = translated_files[file_id]
        data = file_info['data']
        lang_code = file_info['lang_code']
        
        # JSON erstellen
        output = io.BytesIO()
        output.write(json.dumps(data, indent=4, ensure_ascii=False).encode('utf-8'))
        output.seek(0)
        
        # Nach Download aus Speicher löschen
        del translated_files[file_id]
        
        return send_file(
            output,
            as_attachment=True,
            download_name=f'language_{lang_code}.json',
            mimetype='application/json'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health-Check für Render.com"""
    return jsonify({
        'status': 'ok', 
        'languages': len(LANGUAGES),
        'cached_files': len(translated_files)
    }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
