from flask import Flask, request, render_template, jsonify, send_file, Response
from werkzeug.utils import secure_filename
import os
import polib
from deep_translator import GoogleTranslator
import time
import json

app = Flask(__name__)

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
TRANSLATED_FOLDER = 'translated'
ALLOWED_EXTENSIONS = {'po'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['TRANSLATED_FOLDER'] = TRANSLATED_FOLDER

# Ensure upload directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TRANSLATED_FOLDER, exist_ok=True)

# Global variable for translation progress
current_translation = {"text": "", "progress": 0}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/translation-progress')

@app.route("/documentation")
def documentation():
    return render_template("documentation.html")

def translation_progress():
    def generate():
        while True:
            data = {
                'current_string': current_translation['text'],
                'translated_text': current_translation.get('translated_text', ''),
                'progress': current_translation['progress']
            }
            yield f"data: {json.dumps(data)}\n\n"
            time.sleep(0.5)
            if current_translation['progress'] >= 100:
                break
    return Response(generate(), mimetype='text/event-stream')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    source_lang = request.form.get('source_lang', 'auto')
    target_lang = request.form.get('target_lang', 'en')
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            translated_filepath = translate_po_file(filepath, source_lang, target_lang)
            return jsonify({
                'message': 'File translated successfully',
                'download_url': f'/download/{os.path.basename(translated_filepath)}'
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/download/<filename>')
def download_file(filename):
    return send_file(
        os.path.join(app.config['TRANSLATED_FOLDER'], filename),
        as_attachment=True,
        download_name=filename
    )

def translate_po_file(filepath, source_lang, target_lang):
    global current_translation
    translator = GoogleTranslator(source=source_lang, target=target_lang)
    po = polib.pofile(filepath)
    total_entries = len(po)
    
    translated_filename = f'translated_{source_lang}_to_{target_lang}_{os.path.basename(filepath)}'
    translated_filepath = os.path.join(app.config['TRANSLATED_FOLDER'], translated_filename)
    
    for idx, entry in enumerate(po):
        if entry.msgstr == "" and entry.msgid != "":
            try:
                current_translation['text'] = entry.msgid[:50] + "..." if len(entry.msgid) > 50 else entry.msgid
                current_translation['progress'] = int((idx / total_entries) * 100)
                
                time.sleep(0.5)  # Rate limiting
                translated = translator.translate(entry.msgid)
                entry.msgstr = translated
                
                # Update the current_translation to include the translated text
                current_translation['translated_text'] = translated[:50] + "..." if len(translated) > 50 else translated
                
            except Exception as e:
                print(f"Error translating '{entry.msgid}': {str(e)}")
                continue
    
    current_translation['progress'] = 100
    current_translation['text'] = "Complete!"
    current_translation['translated_text'] = "Complete!"
    
    po.save(translated_filepath)
    return translated_filepath

if __name__ == '__main__':
    app.run(debug=True, port=3003)
