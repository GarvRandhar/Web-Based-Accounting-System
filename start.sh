#!/usr/bin/env bash
# exit on error
set -o errexit

echo "Ensuring instance directory exists..."
mkdir -p instance

echo "Initializing database..."
python3 init_db.py

echo "Seeding data..."
python3 seed_data.py

echo "Starting web server..."
gunicorn run:app
