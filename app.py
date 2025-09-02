# app.py
import os
import io
import re
import time
import uuid
import zipfile
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from flask import Flask, request, send_file, jsonify, render_template, Response, stream_with_context

from PIL import Image
import pytesseract

# Optional: PDF -> Images
_IMAGES_FROM_PDF_BACKEND = None
try:
    from pdf2image import convert_from_bytes  # requires poppler
    _IMAGES_FROM_PDF_BACKEND = "pdf2image"
except Exception:
    try:
        import fitz  # PyMuPDF
        _IMAGES_FROM_PDF_BACKEND = "pymupdf"
    except Exception:
        _IMAGES_FROM_PDF_BACKEND = None

# Optional: spaCy NER (für bessere Personen/Orts-Erkennung)
_SPACY_NLP = None
try:
    import spacy
    _SPACY_NLP = spacy.load("de_core_news_sm")
except Exception:
    _SPACY_NLP = None

app = Flask(__name__, template_folder="templates", static_folder="static")

# --- Fortschritt / ETA --------------------------------------------------------

# Sehr einfache globale Fortschrittsverfolgung pro Job
PROGRESS: Dict[str, Dict[str, float]] = {}
# Struktur:
# PROGRESS[job_id] = {
#   "total": int, "done": int, "start": epoch_seconds, "eta": float, "message": str
# }

def _progress_init(job_id: str, total: int, message: str = "Starte…"):
    PROGRESS[job_id] = {"total": total, "done": 0, "start": time.time(), "eta": 0.0, "message": message}

def _progress_step(job_id: str, inc: int = 1, message: Optional[str] = None):
    p = PROGRESS.get(job_id)
    if not p:
        return
    p["done"] = min(p["total"], p.get("done", 0) + inc)
    # ETA aus gleitendem Durchschnitt
    elapsed = max(0.001, time.time() - p["start"])
    avg_per = elapsed / max(1, p["done"])
    remaining = max(0, p["total"] - p["done"])
    p["eta"] = remaining * avg_per
    if message is not None:
        p["message"] = message

def _progress_finish(job_id: str, message: str = "Fertig."):
    p = PROGRESS.get(job_id)
    if not p:
        return
    p["done"] = p["total"]
    p["eta"] = 0.0
    p["message"] = message

# --- Utility -----------------------------------------------------------------

GERMAN_STOPWORDS = {
    # sehr kleine Stopliste, damit das Wortregister nicht "zumüllt"
    "und","oder","der","die","das","des","den","dem","ein","eine","eines","einem","einen",
    "zu","in","im","am","an","auf","aus","bei","nach","von","vor","über","unter","mit",
    "ohne","für","als","ist","war","sind","waren","wird","werden","hat","haben","auch",
    "nicht","so","dass","daß","wie","wenn","dann","weil","doch","nur","schon","noch",
    "beim","zum","zur","vom","ins","am","um","etc"
}

TITLES = {"Kaiser","König","Herzog","Markgraf","Graf","Bischof","Abt","Papst","Landgraf","Prinz","Fürst"}
PLACE_HINTS = {"Stadt","Dorf","Kloster","Bistum","Burg","Mark","Gau","Grafschaft"}

# ► Erweiterbare Liste spezieller Schlagwörter (regex, case-insensitive, Wortgrenzen)
SPECIAL_KEYWORDS = [
    r"Bier", r"Brauerei(?:en)?", r"Stadtrat", r"Domkapitel", r"Pfarrer", r"Gericht(?:e|s)?",
    # Ergänzbar, z.B.:
    r"Schöffen(?:stuhl)?", r"Zoll", r"Markt", r"Wein", r"Mühle", r"Hospital", r"Abgabe(?:n)?"
]

def secure_folder_name(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_\- ]+", "", name).strip().replace(" ", "_")
    return s or f"werk_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

def tesseract_lang(choice: str) -> str:
    """
    choice: 'deu' (Antiqua) oder 'frak' (Fraktur)
    Wählt einen tatsächlich verfügbaren Sprachcode.
    """
    try:
        available = set(pytesseract.get_languages(config=""))
    except Exception:
        available = {"deu"}

    if choice == "frak":
        for cand in ("deu_frak", "Fraktur", "frk", "deu"):
            if cand in available:
                return cand
        return "deu"
    return "deu" if "deu" in available else (sorted(available)[0])

def pdf_to_images(pdf_bytes: bytes) -> List[Image.Image]:
    """
    Versucht zuerst pdf2image (+ Poppler). Wenn Poppler fehlt oder scheitert,
    fällt auf PyMuPDF zurück – falls installiert.
    Optional: POPPLER_PATH Umgebungsvariable verwenden.
    """
    # 1) pdf2image versuchen
    if _IMAGES_FROM_PDF_BACKEND == "pdf2image":
        try:
            from pdf2image import convert_from_bytes
            import os as _os
            poppler_path = _os.environ.get("POPPLER_PATH")  # z. B. C:\Tools\poppler\Library\bin
            kwargs = {"dpi": 300}
            if poppler_path:
                kwargs["poppler_path"] = poppler_path
            return convert_from_bytes(pdf_bytes, **kwargs)
        except Exception as e:
            print("pdf2image fehlgeschlagen:", e)

    # 2) PyMuPDF als Fallback
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = []
        for page in doc:
            pix = page.get_pixmap(dpi=300)
            import io as _io
            img = Image.open(_io.BytesIO(pix.tobytes("png")))
            pages.append(img)
        return pages
    except Exception as e:
        raise RuntimeError(
            "Kein funktionierender PDF-Reader gefunden. "
            "Installiere Poppler (und setze PATH oder POPPLER_PATH) oder 'pip install pymupdf'."
        ) from e

def ocr_image(img: Image.Image, lang: str) -> str:
    # leichte Vorverarbeitung + stabile Tesseract-Config für Fließtext
    gray = img.convert("L")
    config = "--oem 1 --psm 6"
    text = pytesseract.image_to_string(gray, lang=lang, config=config)
    return text

def split_annals_by_year(full_text: str) -> Dict[str, str]:
    """
    Erwartet z. B.:
      '1151.\nIn diesem Jahre ...\n\n1212.\nKaiser Otto ...'
    Liefert { '1151': 'In diesem Jahre ...', '1212': 'Kaiser Otto ...' }
    """
    # Jahreszahlen (3- oder 4-stellig) am Zeilenanfang, optional mit Punkt
    pattern = re.compile(r"(?m)^\s*(\d{3,4})\s*[.:]?\s*$")
    parts = []
    last_pos = 0
    last_year = None
    for m in pattern.finditer(full_text):
        year = m.group(1)
        if last_year is not None:
            parts.append((last_year, full_text[last_pos:m.start()].strip()))
        last_year = year
        last_pos = m.end()
    if last_year is not None:
        parts.append((last_year, full_text[last_pos:].strip()))
    # Filter: leere Einträge raus
    result = {y: t for y, t in parts if t}
    return result

def slugify(text: str) -> str:
    text = re.sub(r"[^\w\- ]+", "", text, flags=re.UNICODE).strip().lower()
    text = text.replace(" ", "-")
    return text or "eintrag"

def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

def write_file(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")

def make_zip_of_folder(folder: Path) -> bytes:
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(folder):
            for f in files:
                full = Path(root) / f
                zf.write(full, arcname=str(full.relative_to(folder)))
    memory_file.seek(0)
    return memory_file.read()

# --- Auto-Indexer / Linker ---------------------------------------------------

def detect_entities(text: str) -> Dict[str, Dict[str, List[str]]]:
    """
    Liefert ein Dict mit Schlüsseln 'personen', 'orte', 'worte', 'schlagworte'
    jeweils -> {ent: [fundstellen...]} (Fundstellen = kurze Snippets).
    """
    persons: Dict[str, List[str]] = {}
    places: Dict[str, List[str]] = {}
    words: Dict[str, List[str]] = {}
    specials: Dict[str, List[str]] = {}

    if _SPACY_NLP:
        doc = _SPACY_NLP(text)
        for ent in doc.ents:
            if ent.label_ in ("PER",):
                persons.setdefault(ent.text, []).append(ent.sent.text.strip())
            elif ent.label_ in ("LOC","GPE"):
                places.setdefault(ent.text, []).append(ent.sent.text.strip())
        for token in doc:
            if token.pos_ in ("NOUN", "PROPN"):
                t = token.text.strip()
                if t and t.lower() not in GERMAN_STOPWORDS and not t[0].isdigit():
                    words.setdefault(t, []).append(token.sent.text.strip())
    else:
        for m in re.finditer(r"\b(" + "|".join(TITLES) + r")\s+[A-ZÄÖÜ][a-zäöüß]+(?:\s+von\s+[A-ZÄÖÜ][a-zäöüß]+)?", text):
            persons.setdefault(m.group(0), []).append(get_sentence(text, m.start()))
        for m in re.finditer(r"\b(?:zu|in|bei|nach|aus|von)\s+([A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+)", text):
            places.setdefault(m.group(1), []).append(get_sentence(text, m.start()))
        for hint in PLACE_HINTS:
            for m in re.finditer(rf"\b{hint}\s+([A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+)", text):
                places.setdefault(m.group(1), []).append(get_sentence(text, m.start()))
        for m in re.finditer(r"\b([A-ZÄÖÜ][a-zäöüß]{3,})\b", text):
            token = m.group(1)
            if token.lower() not in GERMAN_STOPWORDS and token not in persons and token not in places:
                words.setdefault(token, []).append(get_sentence(text, m.start()))

    # Spezielle Schlagworte (case-insensitive, Wortgrenzen)
    for pattern in SPECIAL_KEYWORDS:
        rx = re.compile(rf"\b{pattern}\b", flags=re.IGNORECASE)
        for m in rx.finditer(text):
            kw = m.group(0)  # wie im Text gefunden
            specials.setdefault(kw, []).append(get_sentence(text, m.start()))

    return {"personen": persons, "orte": places, "worte": words, "schlagworte": specials}

def get_sentence(text: str, idx: int, window: int=180) -> str:
    start = max(0, text.rfind('.', 0, idx) + 1)
    end = text.find('.', idx)
    if end == -1:
        end = min(len(text), idx + window)
    return text[start:end].strip()

def annotate_text_with_links(
    text: str,
    base_rel_to_register: str,
    entities: Dict[str, Dict[str, List[str]]]
) -> Tuple[str, Dict[str, Dict[str, List[str]]]]:
    """
    Ersetzt Vorkommen im Text durch Markdown-Links zu Registerdateien.
    Gibt (annotierter_text, verwendete_entities) zurück.
    """
    used = {"personen": {}, "orte": {}, "worte": {}, "schlagworte": {}}

    def sorted_keys(d):
        return sorted(d.keys(), key=lambda s: (-len(s), s.lower()))

    # Reihenfolge: erst Spezial-Schlagwörter (case-insensitive),
    # dann Personen/Orte/Worte (case-sensitive, um Eigennamen zu schonen)
    for ent in sorted_keys(entities.get("schlagworte", {})):
        slug = slugify(ent)
        link = f"[{ent}]({base_rel_to_register}/schlagworte/{slug}.md)"
        pattern = re.compile(rf"\b{re.escape(ent)}\b", flags=re.IGNORECASE)
        if pattern.search(text):
            text = pattern.sub(link, text)
            used["schlagworte"].setdefault(ent, entities["schlagworte"][ent])

    for kind in ("personen","orte","worte"):
        for ent in sorted_keys(entities.get(kind, {})):
            slug = slugify(ent)
            link = f"[{ent}]({base_rel_to_register}/{kind}/{slug}.md)"
            pattern = re.compile(rf"\b{re.escape(ent)}\b")
            if pattern.search(text):
                text = pattern.sub(link, text)
                used[kind].setdefault(ent, entities[kind][ent])

    return text, used

def update_register_files(
    work_dir: Path,
    used_entities: Dict[str, Dict[str, List[str]]],
    mention_info: Tuple[str, str, str]
) -> None:
    """
    Legt/aktualisiert die Registerdateien.
    mention_info = (kind_context, relative_link_from_register, year_or_label)
    """
    register_root = work_dir / "register"
    index_files = {
        "personen":   register_root / "personen" / "README.md",
        "orte":       register_root / "orte" / "README.md",
        "worte":      register_root / "worte" / "README.md",
        "schlagworte":register_root / "schlagworte" / "README.md",
    }
    for kind, idx_path in index_files.items():
        ensure_dir(idx_path.parent)
        if not idx_path.exists():
            write_file(idx_path, f"# {kind.capitalize()}-Register\n\n")

    kind_context, rel_link, label = mention_info

    for kind in ("personen","orte","worte","schlagworte"):
        for ent, snippets in used_entities.get(kind, {}).items():
            slug = slugify(ent)
            entry_file = register_root / kind / f"{slug}.md"
            if not entry_file.exists():
                write_file(entry_file, f"# {ent}\n\n**Ersterwähnung:** {label}\n\n## Vorkommen\n")
            existing = entry_file.read_text(encoding="utf-8")
            bullet = f"- {label}: [{kind_context}]({rel_link})"
            if snippets:
                bullet += f" – {snippets[0][:140].strip()}..."
            if bullet not in existing:
                write_file(entry_file, existing.rstrip() + "\n" + bullet + "\n")

            idx_p = index_files[kind]
            idx = idx_p.read_text(encoding="utf-8")
            rel = f"./{slug}.md"
            line = f"- [{ent}]({rel})"
            if line not in idx:
                write_file(idx_p, idx.rstrip() + "\n" + line + "\n")

# --- Flask Routes -------------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/api/progress", methods=["GET"])
def api_progress():
    job_id = request.args.get("job") or "default"
    p = PROGRESS.get(job_id)
    if not p:
        return jsonify({"ok": True, "percent": 0, "done": 0, "total": 0, "eta_seconds": 0, "message": "Warte auf Start…"})
    percent = 0 if p["total"] == 0 else int(100 * p["done"] / max(1, p["total"]))
    return jsonify({
        "ok": True,
        "percent": percent,
        "done": int(p["done"]),
        "total": int(p["total"]),
        "eta_seconds": round(p["eta"], 1),
        "message": p.get("message", "")
    })

def _run_ocr_pipeline(raw_bytes: bytes, filename: str, script: str, doc_type: str, work_name: str, job_id: str):
    # Basis-Ausgabeordner
    out_root = Path("output")
    work_dir = out_root / work_name
    if work_dir.exists():
        shutil.rmtree(work_dir)
    ensure_dir(work_dir)

    # PDF / Bild lesen
    pages: List[Image.Image] = []
    try:
        if filename.lower().endswith(".pdf"):
            pages = pdf_to_images(raw_bytes)
        else:
            pages = [Image.open(io.BytesIO(raw_bytes))]
    except Exception as e:
        raise RuntimeError(f"Lesefehler: {e}")

    _progress_init(job_id, total=len(pages), message="Seiten vorbereiten…")

    lang = tesseract_lang("frak" if script == "frak" else "deu")
    full_text_list = []
    for i, img in enumerate(pages, 1):
        t0 = time.time()
        txt = ocr_image(img, lang=lang)
        full_text_list.append(txt)
        _progress_step(job_id, 1, message=f"OCR {i}/{len(pages)} (⌀/ETA wird berechnet)…")
        # (kleiner Sleep 0,0x verhindert, dass Browser-Polling zu dicht ist)
        time.sleep(0.01)

    full_text = "\n\n".join(full_text_list).strip()
    if not full_text:
        raise RuntimeError("OCR ergab keinen Text.")

    # Oberes README mit kurzer Info
    write_file(work_dir / "README.md",
               f"# {work_name}\n\nErstellt am {datetime.now().strftime('%Y-%m-%d %H:%M')} mit OCR-Extractor.\n\n")

    summary = {"created": [], "register": []}

    if doc_type == "other":
        entities = detect_entities(full_text)
        annotated, used = annotate_text_with_links(
            full_text,
            base_rel_to_register="register",
            entities=entities
        )
        write_file(work_dir / "README.md",
                   (work_dir / "README.md").read_text(encoding="utf-8") + "\n\n" + annotated + "\n")
        update_register_files(
            work_dir,
            used,
            mention_info=("README.md", "./README.md", "Haupttext")
        )
        summary["created"].append("README.md (voller Text)")
    else:
        year_map = split_annals_by_year(full_text)
        if not year_map:
            entities = detect_entities(full_text)
            annotated, used = annotate_text_with_links(
                full_text,
                base_rel_to_register="register",
                entities=entities
            )
            write_file(work_dir / "README.md",
                       (work_dir / "README.md").read_text(encoding="utf-8") + "\n\n" + annotated + "\n")
            update_register_files(
                work_dir,
                used,
                mention_info=("README.md", "./README.md", "Haupttext")
            )
            summary["created"].append("README.md (Fallback, keine Jahreszahlen erkannt)")
        else:
            years_root = work_dir / "jahre"
            ensure_dir(years_root)

            items = list(year_map.items())
            # Fortschritt neu kalibrieren: OCR war 100%, jetzt wir zählen weiter für Jahresverarbeitung
            PROGRESS[job_id]["total"] = PROGRESS[job_id]["done"] + len(items)
            for idx, (y, text) in enumerate(items, 1):
                entities = detect_entities(text)
                annotated, used = annotate_text_with_links(
                    text,
                    base_rel_to_register="../../register",
                    entities=entities
                )
                year_dir = years_root / y
                ensure_dir(year_dir)
                write_file(year_dir / "README.md", f"# {y}\n\n{annotated}\n")
                update_register_files(
                    work_dir,
                    used,
                    mention_info=(f"jahre/{y}/README.md", f"../jahre/{y}/README.md", y)
                )
                summary["created"].append(f"jahre/{y}/README.md")
                _progress_step(job_id, 1, message=f"Schreibe Jahresordner {idx}/{len(items)}…")

    # Ergebnis bündeln als ZIP zum Download
    zip_bytes = make_zip_of_folder(work_dir)
    zip_name = f"{work_name}.zip"
    zip_path = Path(tempfile.gettempdir()) / zip_name
    zip_path.write_bytes(zip_bytes)

    _progress_finish(job_id, message="Fertig.")
    return {"zip": f"/download/{zip_name}", "created": summary["created"]}

@app.route("/api/ocr", methods=["POST"])
def api_ocr():
    """
    Erwartet Multipart:
      - file: Bild oder PDF
      - script: 'deu' | 'frak'
      - doc_type: 'annals' | 'other'
      - work_name: Ordnername
    Optional: ?stream=1 für SSE-Progress.
    """
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Bitte eine Datei hochladen."}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"ok": False, "error": "Leere Datei."}), 400

    script = request.form.get("script", "deu")
    doc_type = request.form.get("doc_type", "other")
    work_name = secure_folder_name(request.form.get("work_name", ""))

    job_id = request.form.get("job") or str(uuid.uuid4())

    raw_bytes = f.read()
    filename = f.filename

    # Streaming (SSE): verarbeitet synchron, sendet aber Fortschritt live
    if request.args.get("stream") == "1":
        @stream_with_context
        def generate():
            yield f"event: start\ndata: {job_id}\n\n"
            try:
                result = _run_ocr_pipeline(raw_bytes, filename, script, doc_type, work_name, job_id)
                yield f"event: done\ndata: {result['zip']}\n\n"
            except Exception as e:
                err = str(e).replace("\n", " ")
                yield f"event: error\ndata: {err}\n\n"
        return Response(generate(), mimetype="text/event-stream")

    # Normale (nicht-streamende) Antwort – Fortschritt kann parallel via /api/progress polled werden
    try:
        _progress_init(job_id, total=1, message="Initialisiere…")
        result = _run_ocr_pipeline(raw_bytes, filename, script, doc_type, work_name, job_id)
        return jsonify({"ok": True, "job": job_id, "summary": {"created": result["created"], "zip": result["zip"]}})
    except Exception as e:
        _progress_finish(job_id, message="Fehler.")
        return jsonify({"ok": False, "error": str(e)}), 400

@app.route("/download/<zipname>", methods=["GET"])
def download(zipname):
    zip_path = Path(tempfile.gettempdir()) / zipname
    if not zip_path.exists():
        return jsonify({"ok": False, "error": "Datei nicht gefunden."}), 404
    return send_file(str(zip_path), as_attachment=True, download_name=zipname, mimetype="application/zip")

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Optional: expliziten Tesseract-Pfad aus Umgebungsvariable verwenden
    if os.environ.get("TESSERACT_CMD"):
        pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]

    os.makedirs("output", exist_ok=True)
    app.run(host="0.0.0.0", port=8000, debug=True)
