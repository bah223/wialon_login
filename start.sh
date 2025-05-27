#!/bin/bash

# Start Tor service
service tor start

# Wait for Tor SOCKS port to become available
echo "Waiting for Tor SOCKS port..."
while ! nc -z localhost 9050; do
    sleep 1
done

# Start the application
python -m app.main 