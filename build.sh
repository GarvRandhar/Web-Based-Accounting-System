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



echo "Build complete."
