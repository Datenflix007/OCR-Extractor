# OCR-Extractor

## Über den OCR-Extractor
- soll etwa Annalen, oder alte Schriften extahieren
- pro Werk soll ein ordner in ``output/[Ordername]`` angelegt werden
    - bei Annalen soll pro Jahreseintrag ein Unterordner für das Jahr erstellt werden und in die README.md geschrieben werden




## Ideensammlung:
- Bilder oder PDFs hochlädt
- OCR in deutscher Antiqua oder Fraktur ausführt
- Dokumenttyp „Annalen“ oder „Andere Schrift“ unterscheidet
- Einen Ausgabeordner anlegt
- Bei Annalen die Einträge jahrweise in Unterordnern mit README.md ablegt
- Bei „Andere Schrift“ den gesamten Text in README.md schreibt
- Eine Auto-Verlinkung erzeugt: Personen-, Orts- und Wortregister (Markdown) samt Links zurück zu den Fundstellen und Jahresangaben

Abhängigkeiten (Python ≥3.9): flask, pytesseract, Pillow, pdf2image (oder alternativ PyMuPDF), optional spacy + de_core_news_sm
System: Tesseract muss installiert sein inkl. Sprachpakete deu und Fraktur (oft deu_frak oder Fraktur).
(Linux: sudo apt install tesseract-ocr tesseract-ocr-deu tesseract-ocr-frk poppler-utils)

## Wie es arbeitet (kurz)
- OCR: mit pytesseract (Sprachen: deu bzw. deu_frak/Fraktur).
- PDFs werden zu Bildern gerendert (via pdf2image oder ersatzweise PyMuPDF).
- Annalen-Parser: Erkannt werden Jahreszahlen (^\d{3,4}[.:]?$) als Überschriften; alles dazwischen wird in jahre/<Jahr>/README.md geschrieben.
- Register:
- Ordner register/personen, register/orte, register/worte
- Zu jedem Eintrag entsteht eine Datei <slug>.md mit Fundstellen (Jahr/Link + Snippet)
- Der Text in den Jahres-README.md wird automatisch verlinkt: [Naumburg](../../register/orte/naumburg.md) usw.
- Index-Dateien README.md in jedem Register verlinken alle Einträge.
- Ohne spaCy arbeitet eine solide Heuristik (Titelwörter, Präpositionen, Hinweiswörter). Wenn du bessere Erkennung willst: pip install spacy && python -m spacy download de_core_news_sm. 


## Dependencies:
- Python must be installed on your device
- [Tesseract must be installed on the devide](https://github.com/UB-Mannheim/tesseract/wiki?utm_source=chatgpt.com)
## Weiterführende Ideen:
- Aus dem Ortsregister eine OSM Kartenanwendung schaffen


1. Poppler herunterladen

Gehe auf die Seite mit den Windows-Builds, z. B.:
👉 https://github.com/oschwartz10612/poppler-windows/releases/

Lade das neueste poppler-xx.x.0-x64.zip (oder -x86.zip falls du nur 32-bit hast) herunter.

2. Entpacken

Entpacke das ZIP nach einem festen Ort, z. B.:

C:\Tools\poppler


Dort liegt dann u. a.:

C:\Tools\poppler\Library\bin\pdfinfo.exe
C:\Tools\poppler\Library\bin\pdftoppm.exe


Öffne PowerShell (als Benutzer, reicht):

setx POPPLER_PATH "C:\Tools\poppler\Library\bin"





````
 $env:POPPLER_PATH = "C:\Tools\poppler\Library\bin"
 $env:Path += ";C:\Tools\poppler\Library\bin"
 where pdfinfo
 pdfinfo -v
````