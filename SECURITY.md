# 🔒 Sicherheitsrichtlinien

## Wichtige Sicherheitshinweise

### ⚠️ NIEMALS committen:
- `.env` Dateien mit echten Werten
- Datenbank-Dateien (`*.db`, `*.sqlite`)
- Upload-Ordner mit Benutzerdaten
- Log-Dateien mit sensiblen Informationen
- Backup-Dateien

### 🔐 Sichere Konfiguration

1. **SECRET_KEY**: Generiere einen sicheren 32-stelligen Key
   ```python
   import secrets
   secrets.token_hex(32)
   ```

2. **Datenbank**: Nutze PostgreSQL für Production
3. **HTTPS**: Aktiviere SSL in Production
4. **Session**: Sichere Cookie-Einstellungen

### 🛡️ Implementierte Schutzmaßnahmen

- ✅ Passwort-Hashing mit Werkzeug
- ✅ SQL-Injection Schutz durch SQLAlchemy ORM
- ✅ File-Upload Validation
- ✅ Session-Management
- ✅ CSRF-Schutz (optional aktivierbar)
- ✅ Input-Sanitization

### 📋 Sicherheits-Checkliste für Deployment

- [ ] `.env` Datei nur lokal, nicht im Repository
- [ ] PostgreSQL statt SQLite für Production
- [ ] HTTPS aktiviert
- [ ] Sichere Session-Cookies
- [ ] Regelmäßige Backups
- [ ] Log-Monitoring
- [ ] File-Upload Limits
- [ ] Rate-Limiting (empfohlen)

### 🚨 Sicherheitsprobleme melden

Falls du ein Sicherheitsproblem findest, melde es bitte privat an:
- E-Mail: [deine-email@domain.com]
- Beschreibe das Problem detailliert
- Erwarte eine Antwort innerhalb von 48 Stunden

Bitte melde Sicherheitsprobleme NICHT über öffentliche Issues! 