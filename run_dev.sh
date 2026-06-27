#!/bin/bash

trap "kill 0" EXIT

echo "Activating environment, starting uvicorn backend"

uvicorn api:app --reload --port 8000 &

sleep 4

echo "starting streamlit frontend"

streamlit run app.py

wait