@echo off
setlocal

REM Prüfen, ob venv-Ordner existiert
if not exist "venv\" (
    echo ⚙️  Erstelle neues virtuelles Environment...
    python -m venv venv

    REM venv aktivieren
    call venv\Scripts\activate.bat

    REM Dependencies installieren, falls requirements.txt vorhanden
    if exist requirements.txt (
        echo 📦 Installiere Dependencies...
        pip install --upgrade pip
        pip install -r requirements.txt
    ) else (
        echo ⚠️  Keine requirements.txt gefunden, ueberspringe Installation.
    )
) else (
    REM venv aktivieren
    call venv\Scripts\activate.bat
)

REM Server starten
echo 🚀 Starte OCR-Extractor...
python app.py

endlocal
pause
