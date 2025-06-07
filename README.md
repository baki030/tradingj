# 📊 Trading Journal

Ein professionelles Trading Journal mit Flask, entwickelt für die Analyse und Verfolgung von Trading-Aktivitäten.

## ✨ Features

- 📊 **Dashboard** mit umfassenden Statistiken und Charts
- 📈 **Trade-Tracking** mit detaillierter Analyse
- 📝 **Tägliches Journal** für Trading-Notizen
- 🔍 **Erweiterte Filteroptionen** für Trade-Suche
- 📱 **Responsive Design** für alle Geräte
- 🔐 **Sichere Benutzer-Authentifizierung**
- 📁 **HTML-Import** für Trading-Historie
- 📸 **Bild-Upload** für Trade-Screenshots

## 🚀 Installation

### 1. Repository klonen
```bash
git clone https://github.com/yourusername/trading-journal.git
cd trading-journal
```

### 2. Virtual Environment erstellen
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 3. Dependencies installieren
```bash
pip install -r requirements.txt
```

### 4. Umgebungsvariablen konfigurieren
```bash
# Kopiere die Beispiel-Datei
cp env_example.txt .env

# Bearbeite .env und fülle die Werte aus:
# - Generiere einen sicheren SECRET_KEY
# - Konfiguriere deine Datenbank-URL
```

**⚠️ WICHTIG:** Die `.env`-Datei enthält sensible Daten und darf NIEMALS committed werden!

### 5. Datenbank initialisieren
```bash
python -c "from app import app, db; app.app_context().push(); db.create_all()"
```

### 6. Anwendung starten
```bash
# Development
python app.py

# Production (mit Gunicorn)
gunicorn app:app
```

## 🔧 Konfiguration

### Umgebungsvariablen (.env)
```env
SECRET_KEY=your-super-secret-key-here
DATABASE_URL=sqlite:///trading_journal.db
FLASK_ENV=development
```

### Production Deployment
Die Anwendung ist für Cloud-Deployment optimiert:
- **Railway**: Nutze `Procfile` und `runtime.txt`
- **Render**: Automatische Python-Erkennung
- **Heroku**: Kompatibel mit Buildpacks

## 📁 Projektstruktur
```
trading-journal/
├── app.py                 # Haupt-Anwendung
├── config.py             # Konfiguration
├── requirements.txt      # Python Dependencies
├── Procfile             # Production Server
├── templates/           # HTML Templates
├── static/             # CSS, JS, Bilder
└── uploads/            # Upload-Verzeichnis (nicht in Git)
```

## 🔒 Sicherheit

- ✅ Umgebungsvariablen für sensible Daten
- ✅ Sichere Passwort-Hashing
- ✅ CSRF-Schutz
- ✅ Session-Management
- ✅ File-Upload Validation
- ✅ SQL-Injection Schutz durch SQLAlchemy

## 📈 Verwendung

1. **Registrierung**: Erstelle einen Account
2. **Trade-Import**: Lade HTML-Dateien von deinem Broker hoch
3. **Manueller Trade**: Füge Trades manuell hinzu
4. **Analyse**: Nutze Dashboard und Filter für Insights
5. **Journal**: Dokumentiere deine Trading-Gedanken

## 🤝 Beitragen

1. Fork das Repository
2. Erstelle einen Feature-Branch
3. Committe deine Änderungen
4. Push zum Branch
5. Erstelle einen Pull Request

## 📄 Lizenz

Dieses Projekt ist privat. Alle Rechte vorbehalten.

## ⚠️ Haftungsausschluss

Diese Software dient nur zu Bildungszwecken. Trading birgt Risiken und alle Entscheidungen liegen beim Nutzer. 