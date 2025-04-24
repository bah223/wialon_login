#!/bin/bash

# Start Tor service
service tor start

# Wait for Tor to start
sleep 5

# Run database migrations before starting the app
alembic upgrade head

# Start the application
python -m app.main 