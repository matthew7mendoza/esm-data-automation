#!/bin/bash

trap "kill 0" EXIT

if lsof -t -i:8000 >/dev/null 2>&1; then
    echo "Clearing port 8000..."
    kill -9 $(lsof -t -i:8000) >/dev/null 2>&1
    sleep 1
fi

echo "Starting backend..."
uvicorn backend.api:app --reload --port 8000 &

sleep 3

echo "Starting frontend..."
streamlit run frontend/app.py

wait