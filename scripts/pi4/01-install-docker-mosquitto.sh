#!/bin/bash
# Pi4 Server - Установка Docker + Mosquitto + Influx + Grafana
# Запускать на Pi4 (10.0.0.1) под пользователем pi
# Офлайн: образы должны быть заранее скачаны на флешку offline-images.tar

set -e

echo "=== Pi4 Server Setup: Docker + Mosquitto + HA Stack ==="

# 1. Обновление (если есть интернет, если нет — пропустить)
if ping -c 1 8.8.8.8 &> /dev/null; then
  echo "[1/6] Updating system..."
  sudo apt update && sudo apt upgrade -y
  sudo apt install -y git curl wget
else
  echo "[1/6] Offline mode - skip apt update"
fi

# 2. Docker
if ! command -v docker &> /dev/null; then
  echo "[2/6] Installing Docker..."
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker $USER
  echo "Docker installed, you may need to relogin"
else
  echo "[2/6] Docker already installed: $(docker --version)"
fi

# 3. Docker Compose
if ! docker compose version &> /dev/null; then
  echo "Installing docker-compose plugin..."
  sudo apt install -y docker-compose-plugin
fi

# 4. Подготовка папок
echo "[3/6] Preparing folders..."
cd ~/smart_home || cd /home/pi/smart_home || { echo "Clone repo first!"; exit 1; }
mkdir -p mosquitto/config mosquitto/data mosquitto/log
mkdir -p influxdb grafana ha_config

# 5. Mosquitto password
echo "[4/6] Setup Mosquitto auth..."
if [ ! -f mosquitto/config/passwd ]; then
  echo "Creating garage user..."
  # Ставим mosquitto-clients для mosquitto_passwd
  sudo apt install -y mosquitto-clients || true
  touch mosquitto/config/passwd
  chmod 0700 mosquitto/config/passwd
  # Создаст файл с пользователем garage / пароль garage2026
  # Вручную: mosquitto_passwd -c mosquitto/config/passwd garage
  # Для автоматики:
  docker run --rm -v $(pwd)/mosquitto/config:/config eclipse-mosquitto:2 mosquitto_passwd -c -b /config/passwd garage garage2026
  echo "User garage:garage2026 created"
  # Второй пользователь для HA
  docker run --rm -v $(pwd)/mosquitto/config:/config eclipse-mosquitto:2 mosquitto_passwd -b /config/passwd homeassistant ha_garage_2026
else
  echo "Passwd already exists"
fi

# 6. Загрузка офлайн образов если есть
if [ -f offline-images.tar ]; then
  echo "[5/6] Loading offline Docker images..."
  docker load -i offline-images.tar
fi

# 7. Запуск Mosquitto
echo "[6/6] Starting Mosquitto..."
docker compose -f docker-compose.pi4.yml up -d mosquitto

sleep 3
docker logs smart_home-mosquitto-1 || docker logs mosquitto || true

echo ""
echo "=== Pi4 Mosquitto Ready ==="
echo "Broker: 10.0.0.1:1883 and 192.168.4.1:1883"
echo "User: garage / garage2026"
echo "Test:"
echo "  mosquitto_pub -h localhost -u garage -P garage2026 -t garage/test -m hello"
echo "  mosquitto_sub -h localhost -u garage -P garage2026 -t garage/# -v"
echo ""
echo "Next: docker compose -f docker-compose.pi4.yml up -d influxdb grafana homeassistant"
