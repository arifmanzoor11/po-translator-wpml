from flask import Flask, request, render_template, jsonify, send_file, Response
from werkzeug.utils import secure_filename
from deep_translator import GoogleTranslator
import polib
import os
import json
import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
TRANSLATED_FOLDER = os.path.join(BASE_DIR, "translated")

ALLOWED_EXTENSIONS = {"po", "pot"}

# Maximum upload size: 10 MB
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["TRANSLATED_FOLDER"] = TRANSLATED_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TRANSLATED_FOLDER, exist_ok=True)


# ---------------------------------------------------------
# Translation jobs
# ---------------------------------------------------------

jobs = {}

jobs_lock = threading.Lock()


def create_job():
    job_id = str(uuid.uuid4())

    with jobs_lock:
        jobs[job_id] = {
            "status": "starting",
            "current_string": "",
            "translated_text": "",
            "progress": 0,
            "error": None,
            "download_url": None,
        }

    return job_id


def update_job(job_id, **kwargs):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(kwargs)


def get_job(job_id):
    with jobs_lock:
        return jobs.get(job_id, {}).copy()


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def allowed_file(filename):
    if not filename or "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1].lower()

    return extension in ALLOWED_EXTENSIONS


def safe_language_code(language):
    """
    Keep language codes simple and prevent unexpected values.
    """
    if not language:
        return "en"

    return language.strip().lower()


def get_translatable_entries(po):
    """
    Return entries that actually need translation.

    We skip:
    - Header entry
    - Empty msgid
    - Already translated msgstr
    """

    entries = []

    for entry in po:
        # Header
        if not entry.msgid:
            continue

        # Contextual strings are still translatable
        if entry.msgid_plural:
            # Plural entries are handled separately.
            entries.append(entry)
            continue

        if not entry.msgstr.strip():
            entries.append(entry)

    return entries


def translate_text(translator, text, retries=3):
    """
    Translate one string with retry support.
    """

    if not text or not text.strip():
        return ""

    last_error = None

    for attempt in range(retries):
        try:
            result = translator.translate(text)

            if result:
                return result

        except Exception as exc:
            last_error = exc

            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))

    raise last_error or Exception("Translation failed")


# ---------------------------------------------------------
# PO/POT Translation
# ---------------------------------------------------------

def translate_po_file(filepath, source_lang, target_lang, job_id):

    source_lang = safe_language_code(source_lang)
    target_lang = safe_language_code(target_lang)

    if source_lang == target_lang:
        raise ValueError("Source and target languages cannot be the same.")

    update_job(
        job_id,
        status="loading",
        current_string="Reading PO/POT file...",
        progress=0
    )

    # Load PO or POT
    po = polib.pofile(filepath)

    entries = get_translatable_entries(po)

    total_entries = len(entries)

    if total_entries == 0:
        update_job(
            job_id,
            status="completed",
            current_string="No untranslated strings found.",
            translated_text="",
            progress=100
        )

        translated_filename = (
            f"translated_{source_lang}_to_{target_lang}_"
            f"{os.path.basename(filepath)}"
        )

        translated_filepath = os.path.join(
            app.config["TRANSLATED_FOLDER"],
            translated_filename
        )

        po.save(translated_filepath)

        update_job(
            job_id,
            download_url=f"/download/{translated_filename}"
        )

        return translated_filepath

    translator = GoogleTranslator(
        source=source_lang,
        target=target_lang
    )

    translated_count = 0
    failed_count = 0

    for index, entry in enumerate(entries, start=1):

        text_to_translate = entry.msgid

        # Context is preserved automatically by polib.
        # We only translate msgid -> msgstr.

        preview = text_to_translate.replace("\n", " ")

        if len(preview) > 80:
            preview = preview[:80] + "..."

        progress = int(((index - 1) / total_entries) * 100)

        update_job(
            job_id,
            status="translating",
            current_string=preview,
            translated_text="",
            progress=progress
        )

        try:

            # -------------------------------------------------
            # Singular
            # -------------------------------------------------

            if not entry.msgid_plural:

                translated = translate_text(
                    translator,
                    entry.msgid
                )

                entry.msgstr = translated

                translated_preview = translated.replace("\n", " ")

                if len(translated_preview) > 80:
                    translated_preview = translated_preview[:80] + "..."

                translated_count += 1

                update_job(
                    job_id,
                    translated_text=translated_preview
                )

            # -------------------------------------------------
            # Plural
            # -------------------------------------------------

            else:

                # Translate singular form
                singular_translation = translate_text(
                    translator,
                    entry.msgid
                )

                # Translate plural form
                plural_translation = translate_text(
                    translator,
                    entry.msgid_plural
                )

                entry.msgstr_plural[0] = singular_translation
                entry.msgstr_plural[1] = plural_translation

                translated_count += 1

                update_job(
                    job_id,
                    translated_text=(
                        f"{singular_translation} / "
                        f"{plural_translation}"
                    )[:160]
                )

        except Exception as exc:

            failed_count += 1

            print(
                f"Translation error for "
                f"'{text_to_translate[:100]}': {exc}"
            )

            # Keep the string untranslated instead of breaking
            # the entire file.

        progress = int((index / total_entries) * 100)

        update_job(
            job_id,
            progress=progress
        )

        # Small delay to reduce the chance of rate limiting.
        time.sleep(0.15)

    # ---------------------------------------------------------
    # Save translated file
    # ---------------------------------------------------------

    original_filename = os.path.basename(filepath)

    translated_filename = (
        f"translated_{source_lang}_to_{target_lang}_"
        f"{original_filename}"
    )

    translated_filepath = os.path.join(
        app.config["TRANSLATED_FOLDER"],
        translated_filename
    )

    po.save(translated_filepath)

    # ---------------------------------------------------------
    # Completed
    # ---------------------------------------------------------

    update_job(
        job_id,
        status="completed",
        current_string="Translation complete!",
        translated_text=(
            f"{translated_count} translated, "
            f"{failed_count} failed"
        ),
        progress=100,
        download_url=f"/download/{translated_filename}"
    )

    return translated_filepath


# ---------------------------------------------------------
# Background worker
# ---------------------------------------------------------

def translation_worker(
    filepath,
    source_lang,
    target_lang,
    job_id
):

    try:

        translate_po_file(
            filepath,
            source_lang,
            target_lang,
            job_id
        )

    except Exception as exc:

        print(f"Translation job failed: {exc}")

        update_job(
            job_id,
            status="error",
            error=str(exc),
            current_string="Translation failed.",
            progress=0
        )


# ---------------------------------------------------------
# Routes
# ---------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/documentation")
def documentation():
    return render_template("documentation.html")


# ---------------------------------------------------------
# Translation progress SSE
# ---------------------------------------------------------

@app.route("/translation-progress/<job_id>")
def translation_progress(job_id):

    def generate():

        last_data = None

        while True:

            job = get_job(job_id)

            if not job:
                yield (
                    "data: "
                    + json.dumps({
                        "status": "error",
                        "error": "Translation job not found."
                    })
                    + "\n\n"
                )
                break

            data = {
                "status": job.get("status"),
                "current_string": job.get(
                    "current_string",
                    ""
                ),
                "translated_text": job.get(
                    "translated_text",
                    ""
                ),
                "progress": job.get(
                    "progress",
                    0
                ),
                "error": job.get(
                    "error"
                ),
                "download_url": job.get(
                    "download_url"
                ),
            }

            # Only send changes
            if data != last_data:

                yield (
                    "data: "
                    + json.dumps(data)
                    + "\n\n"
                )

                last_data = data

            if data["status"] in (
                "completed",
                "error"
            ):
                break

            time.sleep(0.5)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


# ---------------------------------------------------------
# Upload
# ---------------------------------------------------------

@app.route("/upload", methods=["POST"])
def upload_file():

    if "file" not in request.files:
        return jsonify({
            "error": "No file uploaded."
        }), 400

    file = request.files["file"]

    if not file.filename:
        return jsonify({
            "error": "No file selected."
        }), 400

    if not allowed_file(file.filename):
        return jsonify({
            "error": "Only .po and .pot files are supported."
        }), 400

    source_lang = safe_language_code(
        request.form.get(
            "source_lang",
            "en"
        )
    )

    target_lang = safe_language_code(
        request.form.get(
            "target_lang",
            "fr"
        )
    )

    if source_lang == target_lang:
        return jsonify({
            "error": (
                "Source and target languages "
                "must be different."
            )
        }), 400

    # Secure filename
    original_filename = secure_filename(
        file.filename
    )

    # Add unique ID to avoid collisions when multiple
    # users upload files with the same filename.
    unique_filename = (
        f"{uuid.uuid4().hex[:12]}_"
        f"{original_filename}"
    )

    filepath = os.path.join(
        app.config["UPLOAD_FOLDER"],
        unique_filename
    )

    try:

        file.save(filepath)

    except Exception as exc:

        return jsonify({
            "error": f"Could not save file: {exc}"
        }), 500

    # Create translation job
    job_id = create_job()

    # Start background translation
    thread = threading.Thread(
        target=translation_worker,
        args=(
            filepath,
            source_lang,
            target_lang,
            job_id
        ),
        daemon=True
    )

    thread.start()

    return jsonify({
        "message": "Translation started.",
        "job_id": job_id,
        "progress_url": (
            f"/translation-progress/{job_id}"
        )
    })


# ---------------------------------------------------------
# Download
# ---------------------------------------------------------

@app.route("/download/<filename>")
def download_file(filename):

    safe_filename = secure_filename(filename)

    filepath = os.path.join(
        app.config["TRANSLATED_FOLDER"],
        safe_filename
    )

    if not os.path.isfile(filepath):
        return jsonify({
            "error": "Translated file not found."
        }), 404

    return send_file(
        filepath,
        as_attachment=True,
        download_name=safe_filename
    )


# ---------------------------------------------------------
# Error handlers
# ---------------------------------------------------------

@app.errorhandler(413)
def file_too_large(error):

    return jsonify({
        "error": "File is too large. Maximum size is 10MB."
    }), 413


@app.errorhandler(500)
def internal_error(error):

    return jsonify({
        "error": "An internal server error occurred."
    }), 500


# ---------------------------------------------------------
# Development server
# ---------------------------------------------------------

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=3003,
        debug=True,
        threaded=True
    )