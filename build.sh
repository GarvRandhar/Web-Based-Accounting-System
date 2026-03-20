#!/usr/bin/env bash
# exit on error
set -o errexit

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Installing Node dependencies and building React frontend..."
cd frontend
npm install
npm run build
cd ..

echo "Initializing database..."
python init_db.py

echo "Seeding data..."
python seed_data.py

echo "Build complete."
