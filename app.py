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
import requests
import psycopg
from psycopg.rows import dict_row
from datetime import datetime, timedelta
from flask import Flask, render_template, request, send_file, jsonify, Response
from deep_translator import GoogleTranslator

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "impulse_web_key_2026")

# ==================== DISCORD WEBHOOK ====================
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK", "")

def send_milestone_webhook(count):
    """Sendet Discord Notification bei Milestones"""
    milestones = [10, 25, 50, 100, 250, 500, 750, 1000, 2500, 5000]
    
    if count not in milestones or not DISCORD_WEBHOOK_URL:
        return
    
    embed = {
        "embeds": [{
            "title": "🚀 Impulse Translator - Milestone Reached!",
            "description": f"**{count} translations completed!** 🎉",
            "color": 15844367,  # Gold color
            "fields": [
                {
                    "name": "📊 Total Translations",
                    "value": f"**{count}**",
                    "inline": True
                },
                {
                    "name": "⏰ Time",
                    "value": datetime.now().strftime("%d.%m.%Y %H:%M CET"),
                    "inline": True
                }
            ],
            "footer": {
                "text": "Impulse Translator • Created by Stefc3"
            },
            "timestamp": datetime.utcnow().isoformat()
        }]
    }
    
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=embed, timeout=5)
        if response.status_code == 204:
            print(f"✅ Milestone webhook sent: {count}")
        else:
            print(f"⚠ Webhook response: {response.status_code}")
    except Exception as e:
        print(f"⚠ Webhook failed: {e}")
# ==================== END WEBHOOK ====================

# ==================== DATABASE ====================
DATABASE_URL = os.environ.get("DATABASE_URL", "")

def get_db_connection():
    """Verbindung zur PostgreSQL DB"""
    try:
        conn = psycopg.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"❌ DB Connection Error: {e}")
        return None

def init_db():
    """Erstellt Tabellen wenn nicht vorhanden"""
    conn = get_db_connection()
    if not conn:
        print("⚠ No database connection - skipping init")
        return
    
    try:
        with conn.cursor() as cur:
            # Counter Tabelle
            cur.execute("""
                CREATE TABLE IF NOT EXISTS impulse_translation_count (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    count INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT NOW()
                )
            """)
            
            cur.execute("""
                INSERT INTO impulse_translation_count (id, count) 
                VALUES (1, 0) 
                ON CONFLICT (id) DO NOTHING
            """)
            
            # Translated Files Tabelle
            cur.execute("""
                CREATE TABLE IF NOT EXISTS impulse_translated_files (
                    file_id VARCHAR(255) PRIMARY KEY,
                    data JSONB NOT NULL,
                    lang_code VARCHAR(50) NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    downloaded BOOLEAN DEFAULT FALSE,
                    downloaded_at TIMESTAMP
                )
            """)
            
            conn.commit()
            print("✅ Database initialized successfully")
    except Exception as e:
        print(f"❌ DB Init Error: {e}")
    finally:
        conn.close()

def load_counter():
    """Lädt Counter aus DB"""
    conn = get_db_connection()
    if not conn:
        print("⚠ No DB connection - using RAM counter (0)")
        return 0
    
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT count FROM impulse_translation_count WHERE id = 1")
            result = cur.fetchone()
            count = result['count'] if result else 0
            print(f"✅ Counter loaded from DB: {count}")
            return count
    except Exception as e:
        print(f"❌ Counter Load Error: {e}")
        return 0
    finally:
        conn.close()

def save_counter(count):
    """Speichert Counter in DB"""
    conn = get_db_connection()
    if not conn:
        print("⚠ No DB connection - counter not saved")
        return
    
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE impulse_translation_count 
                SET count = %s, last_updated = NOW() 
                WHERE id = 1
            """, (count,))
            conn.commit()
            print(f"✅ Counter saved to DB: {count}")
    except Exception as e:
        print(f"❌ Counter Save Error: {e}")
    finally:
        conn.close()

def save_translated_file(file_id, data, lang_code):
    """Speichert übersetzte Datei in DB"""
    conn = get_db_connection()
    if not conn:
        print("⚠ No DB connection - file not saved")
        return
    
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO impulse_translated_files (file_id, data, lang_code)
                VALUES (%s, %s, %s)
            """, (file_id, json.dumps(data), lang_code))
            conn.commit()
            print(f"💾 File saved to DB: {file_id}")
    except Exception as e:
        print(f"❌ File Save Error: {e}")
    finally:
        conn.close()

def get_translated_file(file_id):
    """Lädt übersetzte Datei aus DB"""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT data, lang_code, downloaded 
                FROM impulse_translated_files 
                WHERE file_id = %s
            """, (file_id,))
            result = cur.fetchone()
            
            if result:
                print(f"✅ File loaded from DB: {file_id}")
                return {
                    'data': result['data'],
                    'lang_code': result['lang_code'],
                    'downloaded': result['downloaded']
                }
            return None
    except Exception as e:
        print(f"❌ File Load Error: {e}")
        return None
    finally:
        conn.close()

def mark_file_downloaded(file_id):
    """Markiert Datei als downloaded"""
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE impulse_translated_files 
                SET downloaded = TRUE, downloaded_at = NOW()
                WHERE file_id = %s
            """, (file_id,))
            conn.commit()
            print(f"✅ File marked as downloaded: {file_id}")
    except Exception as e:
        print(f"❌ Mark Downloaded Error: {e}")
    finally:
        conn.close()

def cleanup_old_files():
    """
    Background-Task: Löscht Dateien die:
    1. Downloaded wurden
    2. Älter als 1 Stunde sind
    """
    while True:
        try:
            conn = get_db_connection()
            if not conn:
                print("⚠ No DB connection for cleanup")
                time.sleep(600)
                continue
            
            with conn.cursor() as cur:
                # Lösche downloaded Files
                cur.execute("""
                    DELETE FROM impulse_translated_files 
                    WHERE downloaded = TRUE
                """)
                deleted_downloaded = cur.rowcount
                
                # Lösche alte Files (älter als 1 Stunde)
                cur.execute("""
                    DELETE FROM impulse_translated_files 
                    WHERE created_at < NOW() - INTERVAL '1 hour'
                """)
                deleted_old = cur.rowcount
                
                conn.commit()
                
                if deleted_downloaded > 0 or deleted_old > 0:
                    print(f"🗑 Cleanup: {deleted_downloaded} downloaded, {deleted_old} old files deleted")
            
            conn.close()
        
        except Exception as e:
            print(f"⚠ Cleanup-Fehler: {e}")
        
        time.sleep(600)  # Alle 10 Minuten

# Database initialisieren beim Start
init_db()
translation_count = load_counter()

# Cleanup-Task starten
cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()
# ==================== END DATABASE ====================

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
            
            # Speichere in PostgreSQL statt RAM!
            save_translated_file(file_id, final_output, lang_code_upper)
            
            print(f"✅ Translation complete - file_id: {file_id}")
            
            # ==================== COUNTER & WEBHOOK ====================
            global translation_count
            translation_count += 1
            save_counter(translation_count)
            
            threading.Thread(
                target=send_milestone_webhook, 
                args=(translation_count,), 
                daemon=True
            ).start()
            # ==================== END ====================
            
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
    """Download der übersetzten Datei aus PostgreSQL"""
    print(f"📥 Download request for file_id: {file_id}")
    
    # Lade aus PostgreSQL
    file_info = get_translated_file(file_id)
    
    if not file_info:
        print(f"❌ Download failed - file_id not found: {file_id}")
        return jsonify({'error': 'Datei nicht gefunden oder abgelaufen'}), 404
    
    try:
        data = file_info['data']
        lang_code = file_info['lang_code']
        
        print(f"✅ Download started - file_id: {file_id}, lang: {lang_code}")
        
        # JSON erstellen
        output = io.BytesIO()
        output.write(json.dumps(data, indent=4, ensure_ascii=False).encode('utf-8'))
        output.seek(0)
        
        # Markiere als downloaded (wird beim nächsten Cleanup gelöscht)
        mark_file_downloaded(file_id)
        
        return send_file(
            output,
            as_attachment=True,
            download_name=f'language_{lang_code}.json',
            mimetype='application/json'
        )
    except Exception as e:
        print(f"❌ Download error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health-Check für Render.com"""
    conn = get_db_connection()
    cached_files = 0
    
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM impulse_translated_files")
                cached_files = cur.fetchone()[0]
            conn.close()
        except:
            pass
    
    return jsonify({
        'status': 'ok', 
        'languages': len(LANGUAGES),
        'cached_files': cached_files,
        'total_translations': translation_count
    }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Impulse Translator starting... (Total translations: {translation_count})")
    app.run(host='0.0.0.0', port=port, debug=False)
