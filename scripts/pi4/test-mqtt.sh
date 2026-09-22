#!/bin/bash
# Pi4 - Тест MQTT

BROKER="localhost"
USER="garage"
PASS="garage2026"

echo "=== Pi4 MQTT Test ==="
sudo apt install -y mosquitto-clients || true

echo "Publish..."
mosquitto_pub -h $BROKER -u $USER -P $PASS -t garage/test -m "Pi4 online $(date)"

echo "Subscribe garage/# (Ctrl+C)..."
mosquitto_sub -h $BROKER -u $USER -P $PASS -t "garage/#" -v
