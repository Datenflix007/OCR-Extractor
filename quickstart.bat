# run.ps1
# Batch-Skript zum Starten des OCR-Extractors

# Prüfen, ob venv-Ordner existiert
if (!(Test-Path -Path ".\venv")) {
    Write-Host "⚙️  Erstelle neues virtuelles Environment..."
    python -m venv venv
}

# Aktivieren des venv
Write-Host "✅ Aktiviere venv..."
. .\venv\Scripts\Activate.ps1

# Pakete installieren (nur wenn requirements.txt existiert)
if (Test-Path -Path ".\requirements.txt") {
    Write-Host "📦 Installiere Dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt
} else {
    Write-Host "⚠️  Keine requirements.txt gefunden, überspringe Installation."
}

# Server starten
Write-Host "🚀 Starte OCR-Extractor..."
python app.py
