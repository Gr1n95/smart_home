#!/bin/bash
# Pi5 - Тест связи с Pi4 MQTT брокером (10.0.0.1)

BROKER="10.0.0.1"
USER="garage"
PASS="garage2026"

echo "=== Pi5 -> Pi4 MQTT Test ==="
echo "Broker: $BROKER:1883"

echo "[1] Install mosquitto-clients..."
sudo apt install -y mosquitto-clients || true

echo "[2] Publish test..."
mosquitto_pub -h $BROKER -u $USER -P $PASS -t garage/test -m "Pi5 online $(date)" -d

echo "[3] Subscribe to all garage topics (Ctrl+C to exit)..."
mosquitto_sub -h $BROKER -u $USER -P $PASS -t "garage/#" -v

# В другом терминале на Pi4:
# mosquitto_sub -h localhost -u garage -P garage2026 -t "garage/#" -v
