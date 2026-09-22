# Офлайн настройка без интернета — чеклист

## 1. Подготовка на ноуте с интернетом (до поездки в гараж)

Скачать все образы и модели:

```bash
# Docker образы
docker pull eclipse-mosquitto:2
docker pull ghcr.io/home-assistant/home-assistant:stable
docker pull influxdb:2.7
docker pull grafana/grafana
docker pull rhasspy/wyoming-whisper
docker pull rhasspy/wyoming-piper
docker pull rhasspy/wyoming-openwakeword
docker pull ollama/ollama
docker save -o offline-images.tar eclipse-mosquitto:2 ghcr.io/home-assistant/home-assistant:stable influxdb:2.7 grafana/grafana rhasspy/wyoming-whisper rhasspy/wyoming-piper rhasspy/wyoming-openwakeword ollama/ollama

# Модели Whisper
mkdir -p models/whisper
# скачать вручную с huggingface: https://huggingface.co/ggerganov/whisper.cpp
# small.bin ~ 150MB

# Piper
mkdir -p models/piper
# скачать ru_RU-irina-medium: https://huggingface.co/rhasspy/piper-voices/tree/main/ru/ru_RU/irina/medium

# Ollama модель phi3:mini
# на ноуте: ollama pull phi3:mini
# скопировать ~/.ollama/models в models/ollama

# InsightFace buffalo_s
mkdir -p models/insightface
# https://github.com/deepinsight/insightface - buffalo_s.zip
```

Скопировать на SSD/флешку 64GB.

## 2. Настройка Pi4 как WiFi точки (GarageNet)

На Pi4 (Raspberry Pi OS Lite):

```bash
sudo apt install hostapd dnsmasq -y
sudo systemctl stop hostapd dnsmasq

# /etc/dhcpcd.conf
interface wlan0
static ip_address=192.168.4.1/24
nohook wpa_supplicant

interface eth0
static ip_address=10.0.0.1/24

# /etc/dnsmasq.conf
interface=wlan0
dhcp-range=192.168.4.10,192.168.4.100,255.255.255.0,24h
domain=garage.local

# /etc/hostapd/hostapd.conf
interface=wlan0
ssid=GarageNet
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=Garage2026Secure!
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP

sudo systemctl unmask hostapd
sudo systemctl enable hostapd dnsmasq
sudo reboot
```

Теперь телефон видит GarageNet.

## 3. RTC DS3231

Подключить: VCC->3.3V, GND->GND, SDA->GPIO2, SCL->GPIO3

```bash
# /boot/firmware/config.txt добавить:
dtoverlay=i2c-rtc,ds3231

sudo apt install i2c-tools -y
sudo i2cdetect -y 1 # должен увидеть 68
sudo hwclock -r
sudo hwclock -w # записать время
```

## 4. Связь Pi4 <-> Pi5 по Ethernet

Прямой кабель между Pi. На Pi5:

```bash
# /etc/dhcpcd.conf на Pi5
interface eth0
static ip_address=10.0.0.2/24
static routers=10.0.0.1

# MQTT брокер на 10.0.0.1:1883
ping 10.0.0.1 # должен пинговаться
```

## 5. Проверка офлайна

- Отключить интернет на обоих
- Перезагрузить
- Подключиться телефоном к GarageNet
- Открыть http://192.168.4.1:8123 (HA на Pi4)
- Сказать "привет гараж" — должен ответить
- Поднести палец — открыть
- Зажать MQ-7 над зажигалкой (без огня, только газ) — сирена

## 6. Резервирование

Если Pi5 упал:
- Pi4 по MQTT LWT детектит `garage/ai/status offline`
- Включает сирену коротко 2 сек + пишет в лог
- Доступ по отпечатку продолжает работать через Pi4 (R503 можно переключить на Pi4 по USB)

Сделать watchdog на Pi5:
```bash
# /etc/systemd/system/ai-watchdog.service
# рестарт сервисов если MQTT не отвечает 30 сек
```
