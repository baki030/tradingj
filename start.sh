#!/bin/bash

echo "=== Railway Deployment Start ==="
echo "PORT: $PORT"
echo "DATABASE_URL: ${DATABASE_URL:0:20}..." # Nur ersten 20 Zeichen zeigen
echo "FLASK_ENV: $FLASK_ENV"
echo "SECRET_KEY: ${SECRET_KEY:0:10}..." # Nur ersten 10 Zeichen zeigen

# Initialize database
echo "Initializing database..."
python -c "
from app import app, db
with app.app_context():
    try:
        db.create_all()
        print('Database initialized successfully')
    except Exception as e:
        print(f'Database initialization error: {e}')
"

echo "Starting Gunicorn..."
exec gunicorn app:app \
    --bind 0.0.0.0:$PORT \
    --workers 1 \
    --timeout 120 \
    --keep-alive 2 \
    --log-level info \
    --access-logfile - \
    --error-logfile - 