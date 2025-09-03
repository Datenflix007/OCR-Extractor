# OCR‑Extractor


## 1. Über den OCR‑Extractor
Ziel: Historische Dokumente (z. B. Chroniken, Briefe, Archive) in durchsuchbare, verlinkte Markdown‑Sammlungen umwandeln.
Core‑Features:
PDF → Bilder (Poppler / PyMuPDF)
Tesseract OCR (Deutsch + Fraktur)
Optional spaCy‑NER für Personen/Orte
Automatischer Aufbau von Register‑Ordnern (personen, orte, worte, schlagworte)
Fortschritts‑Monitoring über REST‑/SSE
Ergebnis‑ZIP mit allen Text‑ und Register‑Dateien
Warum?
Historiker:innen und Bibliothekswissenschaftler:innen haben oft tausende PDF‑Bände, deren Inhalte offline nicht durchsuchbar sind. Dieser Service liefert eine sofort nutzbare, Markdown‑basierte Struktur, die in Git, MkDocs, Jekyll usw. integriert werden kann.

## 2. Voraussetzungen
Komponente	Version	Hinweis
Python	3.10 +	pip install -r requirements.txt
Tesseract OCR	≥ 4.1	apt install tesseract-ocr (Linux) / brew install tesseract (macOS) / Windows‑Installer
Poppler (nur wenn pdf2image verwendet)	≥ 22	apt install poppler-utils / brew install poppler / Windows‑Binary
spaCy (optional)	de_core_news_sm	pip install -U spacy && python -m spacy download de_core_news_sm
pdf2image / PyMuPDF	–	Automatisch installiert via requirements.txt
Docker (optional)	–	Für die Docker‑Version (siehe 3.3)
Tipp: Um die Laufzeit zu verkürzen, können Sie Tesseract mit GPU‑Support (z. B. tesserocr oder pytesseract‑CUDA‑Wrapper) nutzen – allerdings nicht im Scope dieser README.

## 3. Installation
### 3.1 Klonen & virtuelle Umgebung
git clone https://github.com/your-org/ocr-extractor.git
cd ocr-extractor
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -U pip
3.2 Abhängigkeiten installieren
pip install -r requirements.txt
requirements.txt (Beispiel):

Flask>=2.3
pytesseract>=0.3
Pillow>=10
pdf2image>=1.16   # optional
PyMuPDF>=1.23      # optional
spacy>=3.5         # optional
3.3 Tesseract & Poppler
Linux (Debian/Ubuntu):

sudo apt-get update
sudo apt-get install tesseract-ocr tesseract-ocr-deu tesseract-ocr-frk poppler-utils
macOS (Homebrew):

brew install tesseract
brew install poppler
Windows:

Tesseract: https://github.com/UB-Mannheim/tesseract/wiki (bitte “Add to system PATH” auswählen).
Poppler: https://github.com/oschwartz10612/poppler-windows (Binärordner zum PATH hinzufügen).
Optional: Setzen Sie die Umgebungsvariable POPPLER_PATH, falls Tesseract nicht automatisch Poppler finden kann.

### 3.4 spaCy‑Modell (optional)
python -m spacy download de_core_news_sm
Ohne spaCy wird die regex‑basierte Entitätenerkennung verwendet, was weniger präzise ist, aber immer noch brauchbare Register liefert.

### 3.5 Docker‑Installation (optional)
Ein Dockerfile befindet sich im Repository.

docker build -t ocr-extractor .
docker run -p 8000:8000 ocr-extractor
## 4. Benutzung
### 4.1 Flask‑Server starten
export TESSERACT_CMD=/usr/bin/tesseract   # optional, wenn Tesseract nicht im PATH
export POPPLER_PATH=/usr/bin              # optional
python app.py
Der Service ist unter http://localhost:8000 erreichbar.
Im Browser erscheint eine einfache Upload‑Seite (templates/index.html).

Hinweis: Für Produktionsumgebungen empfehlen wir einen Reverse‑Proxy (NGINX/Traefik) und HTTPS.

### 4.2 API‑Endpoints
Endpoint	Methode	Zweck	Beispiel
/api/ocr	POST	OCR‑Pipeline starten	curl -F "file=@/path/chronik.pdf" -F "script=frak" -F "doc_type=annals" -F "work_name=Chronik_1453" http://localhost:8000/api/ocr
/api/progress	GET	Fortschritt abfragen	curl http://localhost:8000/api/progress?job=<JOB_ID>
/download/<zipname>	GET	ZIP‑Archiv herunterladen	curl -O http://localhost:8000/download/Chronik_1453.zip
#### 4.2.1 /api/ocr – Details
Parameter	Typ	Pflicht	Beschreibung
file	Datei	Ja	PDF oder Bild (JPG/PNG)
script	deu / frak	Nein	Welche Schriftart OCR‑Tesseract benutzen soll
doc_type	annals / other	Nein	Gibt an, ob Jahreszahlen erwartet werden
work_name	string	Nein	Ordner‑Name im output/ (automatisches „sanitizing“)
job	string	Nein	Optional, um Progress‑Monitoring zu starten (wenn nicht gesetzt, wird UUID generiert)
SSE‑Streaming (optional):
?stream=1 aktiviert Server‑Sent Events, sodass der Client live‑Aktualisierungen erhält:

curl -N http://localhost:8000/api/ocr?stream=1 \
     -F "file=@chronik.pdf" \
     -F "script=deu" \
     -F "doc_type=annals" \
     -F "work_name=Chronik_1453"
Ausgabe:

event: start
data: 3f7b6c4a-...

event: done
data: /download/Chronik_1453.zip
### 4.3 Ergebnis‑ZIP‑Inhalt
Chronik_1453/
├── README.md                # Überblick + gesamter Text (bei "other") oder Jahres‑Index (bei "annals")
├── jahre/
│   ├── 1453/
│   │   └── README.md       # Text von 1453
│   └── 1454/
│       └── README.md       # Text von 1454
└── register/
    ├── personen/
    │   ├── README.md
    │   ├── kaiser-otto.md
    │   └── ...
    ├── orte/
    │   └── ...
    ├── worte/
    │   └── ...
    └── schlagworte/
        └── ...
Alle Register‑Dateien enthalten Markdown‑Links zu den jeweiligen Textstellen. Das ZIP ist sofort als Git‑Repository, Jekyll‑Site oder MkDocs‑Projekt nutzbar.

## 5. Über den Workflow
Datei‑Upload
Der Client sendet eine Datei an /api/ocr.
Optional wird ein job‑ID angegeben, um den Fortschritt zu verfolgen.

Initialisierung

PROGRESS[job_id] wird erstellt (total = Anzahl Seiten, done = 0).
PDF → Bilder

pdf_to_images konvertiert jede Seite in ein 300 dpi‑PNG.
Bei Bild‑Upload wird die Datei direkt als Image geöffnet.
OCR

Jede Seite wird mittels pytesseract.image_to_string ausgelesen.
Text wird zusammengeführt (full_text).
Fortschritt wird pro Seite aktualisiert.
Text‑Verarbeitung

Bei doc_type=annals wird split_annals_by_year verwendet.
Sonst wird der gesamte Text verarbeitet.
Entitätenerkennung

Mit spaCy: PER, LOC, GPE.
Ohne spaCy: regex‑Basierte Erkennung (Titel‑Phrasen, Präpositionen, SPECIAL_KEYWORDS).
Für jedes Fundstück wird ein kurzer Sätze‑Snippet erzeugt.
Annotieren & Register‑Erstellung

Der Text wird mit Markdown‑Links zu Register‑Einträgen verknüpft.
Für jede verwendete Entität werden:
Eintrag‑Datei (<kind>/<slug>.md) erstellt bzw. ergänzt.
Index‑Datei (<kind>/README.md) aktualisiert.
Der Link‑Kontext (mention_info) gibt an, wo der Fund stattgefunden hat.
Erzeugung der README

Für other: kompletter Text in README.md.
Für annals: jahre/<Jahr>/README.md + Jahres‑Index.
ZIP‑Packaging

make_zip_of_folder erstellt ein ZIP im Speicher, wird dann im System‑Temp‑Verzeichnis abgelegt.
Rückgabe: /download/<name> URL.
Fortschritt‑Abschluss

PROGRESS[job_id] wird auf „fertig“ gesetzt.
Bei SSE‑Stream: event: done gesendet.
## 6. Troubleshooting
Symptom	Ursache	Lösung
RuntimeError: Kein funktionierender PDF-Reader gefunden	Poppler/Pymupdf nicht installiert	Installieren (apt install poppler-utils oder pip install pymupdf)
OCR liefert leeren Text	Bildqualität schlecht (grau, niedrig DPI)	Bild auf höherer Auflösung speichern (≥ 300 dpi) oder vorher Bild‑Enhancement durchführen
Fehlende deu Sprache in Tesseract	Tesseract‑Sprachpaket fehlt	sudo apt install tesseract-ocr-deu (Linux)
Zu lange Laufzeit	Große PDF (hundert Seiten)	Nutzen Sie den SSE‑Stream und zeigen Sie Fortschritt im UI; alternativ ein Batch‑Job mit mehr Ressourcen
Register‑Dateien doppelt vorhanden	Mehrere Vorkommen derselben Entität	Der Code verhindert Duplikate, aber bei vielen Snippets kann die Datei sehr groß werden – prüfen Sie max_snippets (keine aktuelle Option)
Fehler: UnicodeDecodeError	PDF enthält nicht‑UTF‑8 Text	pdf_to_images konvertiert immer zu PNG, OCR liefert UTF‑8, daher sollte es kein Problem geben
## 7. Weiterentwicklung
Mehrsprachigkeit: pytesseract unterstützt viele Sprachen.
Spacy‑NER‑Modelle: de_core_news_lg oder de_dep_news_trf für bessere Ergebnisse.
Persistente Datenbank: Statt globalem PROGRESS ein Redis‑Store für Skalierbarkeit.
Docker Compose: Kombinieren mit Tesseract‑Server oder Celery‑Worker.
UI: Integrieren Sie die Upload‑Seite in MkDocs oder Vue‑App.
## 8. Lizenz
MIT © 2025 Your Name

## 9. Kontakt & Support
Issue‑Tracker: https://github.com/your-org/ocr-extractor/issues
Mail: yourname@example.com
Discord: #ocr-extractor (falls vorhanden)