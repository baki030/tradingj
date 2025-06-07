# Production Deployment Checklist

## 🔒 Sicherheit (KRITISCH)
- [ ] Debug-Modus deaktivieren (`debug=False`)
- [ ] Sichere SECRET_KEY generieren und in Umgebungsvariablen
- [ ] HTTPS konfigurieren
- [ ] File-Upload Validierung verstärken
- [ ] Input-Sanitization für alle Formulare
- [ ] Rate Limiting für Login/Registration

## 🗄️ Datenbank
- [ ] PostgreSQL für Production verwenden
- [ ] Database Migrations testen
- [ ] Backup-Strategie implementieren
- [ ] Connection Pooling aktivieren

## 🚀 Server-Konfiguration
- [ ] WSGI-Server (Gunicorn) konfigurieren
- [ ] Reverse Proxy (Nginx) einrichten
- [ ] Static Files korrekt ausliefern
- [ ] Error Logging konfigurieren

## 🧹 Code-Cleanup
- [ ] Debug-Prints entfernen
- [ ] Error-Handling verbessern
- [ ] Input-Validierung hinzufügen
- [ ] Große Funktionen aufteilen

## 📝 Dokumentation
- [ ] README mit Installation/Setup
- [ ] User-Manual erstellen
- [ ] API-Dokumentation (falls nötig)

## 🧪 Testing
- [ ] Unit Tests schreiben
- [ ] Integration Tests
- [ ] Load Testing
- [ ] User Acceptance Testing

## 🔧 Production Files
```python
# requirements.txt
Flask==2.3.3
Flask-SQLAlchemy==3.0.5
Flask-Login==0.6.3
Flask-Migrate==4.0.5
gunicorn==21.2.0
psycopg2-binary==2.9.7
python-dotenv==1.0.0
# ... andere dependencies
```

```python
# config.py
import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False

class DevelopmentConfig(Config):
    DEBUG = True
```

```bash
# .env (NICHT in Git!)
SECRET_KEY=your-super-secret-key-here
DATABASE_URL=postgresql://user:password@localhost/tradingjournal
```

## 🌐 Deployment
- [ ] Domain und Hosting wählen
- [ ] SSL-Zertifikat einrichten
- [ ] Monitoring einrichten
- [ ] Backup-System testen 