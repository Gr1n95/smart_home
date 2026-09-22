#!/bin/bash
# Pi4 + Pi5 - Установка RTC DS3231 (время без интернета)
# Подключение: VCC 3.3V, GND GND, SDA GPIO2, SCL GPIO3

set -e

echo "=== RTC DS3231 Setup ==="

if [ "$EUID" -ne 0 ]; then
  echo "Run with sudo"
  exit 1
fi

echo "[1/4] Enable I2C..."
raspi-config nonint do_i2c 0 || echo "dtparam=i2c_arm=on" >> /boot/firmware/config.txt

echo "[2/4] Add overlay..."
if ! grep -q "i2c-rtc,ds3231" /boot/firmware/config.txt; then
  echo "dtoverlay=i2c-rtc,ds3231" >> /boot/firmware/config.txt
  echo "Added dtoverlay=i2c-rtc,ds3231"
else
  echo "Already in config.txt"
fi

echo "[3/4] Install i2c-tools..."
apt update
apt install -y i2c-tools

echo "[4/4] Check I2C..."
echo "Reboot required, then run:"
echo "  sudo i2cdetect -y 1  # should show 68"
echo "  sudo hwclock -r"
echo "  sudo hwclock -w  # write system time to RTC"
echo "  sudo hwclock -s  # read RTC to system"

echo ""
echo "After reboot, disable fake-hwclock:"
echo "  sudo apt remove -y fake-hwclock"
echo "  sudo systemctl disable fake-hwclock"
