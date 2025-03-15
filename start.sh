#!/bin/bash

# Start Tor service
service tor start

# Wait for Tor to start
sleep 5

# Start the application
python -m app.main 