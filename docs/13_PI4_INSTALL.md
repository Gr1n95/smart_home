# Установка Pi4 (сервер + Astra) — по полочкам

> Pi4 = **весь сервер и мозг**: MQTT, БД истории, HA, регулятор (автоматика), Astra
> (интенты + LLM + TTS), GPIO реле/сирены, точка доступа GarageNet.
> Устанавливаем послойно, каждый слой проверяем — не идём дальше, пока слой не зелёный.

---

## Полка 0 — ОС (основа)

| Что | Версия/вариант | Почему |
|---|---|---|
| Raspberry Pi OS **Lite 64-bit** | Bookworm | Без десктопа: экономия ~700MB RAM для Ollama. 64-bit обязателен (модели/пакеты) |
| Инструмент прошивки | Raspberry Pi Imager | В настройках сразу задать: hostname `pi4-server`, SSH = on, user `pi`, WiFi для первого запуска, timezone Europe/Berlin |

После первого входа по SSH:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git curl htop i2c-tools mosquitto-clients python3-venv
```

RTC (если стоит DS3231): `bash scripts/pi4/03-setup-rtc.sh` → reboot.

---

## Полка 1 — Сеть (адреса до всего остального)

```bash
# eth0 к Pi5 — статика 10.0.0.1
sudo tee -a /etc/dhcpcd.conf <<'EOF'
interface eth0
static ip_address=10.0.0.1/24
EOF
sudo reboot
```

Проверка: `ip a` → eth0 = 10.0.0.1. Позже (Фаза 5) wlan0 станет AP 192.168.4.1 — скрипт `scripts/pi4/02-setup-garagenet-ap.sh`. **Не запускать пока**, дома удобнее через роутер с интернетом.

---

## Полка 2 — Docker

```bash
bash scripts/pi4/01-install-docker-mosquitto.sh
# скрипт: docker + compose plugin + пароль mosquitto + запуск брокера
# после: перелогин (docker без sudo)
```

Проверка: `docker ps` → контейнер mosquitto Up; `bash scripts/pi4/test-mqtt.sh`.

---

## Полка 3 — Docker-стек (docker-compose.pi4.yml)

| Контейнер | Порт | RAM | Что даёт |
|---|---|---|---|
| mosquitto | 1883, 9001 | ~30MB | Шина всего проекта |
| influxdb:2.7 | 8086 | ~200MB | БД истории телеметрии, bucket `garage` |
| homeassistant | 8123 | ~500-700MB | Панель управления (опционален) |
| ollama | 11434 | ~2.3GB с phi3:mini | LLM fallback Astra — **только если RAM >= 4GB** |

**Grafana убран** (решение: без визуализации, вся история в InfluxDB — блок закомментирован в compose). Регулятор и логгер — systemd-сервисы на хосте (Полка 4б), не контейнеры: регулятору нужен GPIO.

```bash
docker compose -f docker-compose.pi4.yml up -d mosquitto influxdb homeassistant ollama
```

Первичная настройка (по одному разу):
- **InfluxDB**: http://pi4:8086 → Get Started → user/org → bucket `garage` → **сохранить token** (нужен логгеру)
- **Ollama** (если запущен): `docker exec -it smart_home-ollama-1 ollama pull phi3:mini`
- **HA**: http://pi4:8123 → интеграция MQTT → broker `10.0.0.1`, user `garage`

### Сколько RAM у Pi4 — что включать

| RAM | Стек | Astra |
|---|---|---|
| 2GB | mosquitto + influx + регулятор + логгер (~450MB) | интенты + TTS, **без** LLM |
| 4GB | всё выше + HA + Ollama (~3.3GB, добавить swap 1GB) | полный, LLM впритык |
| 8GB | всё без ограничений | полный |

### Полка 4б — Регулятор + логгер (systemd)

```bash
cd ~/smart_home && source venv/bin/activate
pip install influxdb-client   # для логгера
```

Юнит `/etc/systemd/system/garage-regulator.service` (шаблон как у astra-core):
`ExecStart=/home/pi/smart_home/venv/bin/python services/regulator/regulator.py`

Юнит `/etc/systemd/system/influx-logger.service` (то же + Environment с INFLUX_TOKEN из Полки 3):
`ExecStart=... python services/influx_logger/influx_logger.py`

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now garage-regulator influx-logger
```

Проверка автоматики без железа: запусти симулятор `scenario cold` с ноутбука —
в логе MQTT регулятор сам опубликует `garage/actuator/heater ON`.

---

## Полка 4 — Astra (на хосте, не в Docker — ей нужен звук)

```bash
cd ~/smart_home
python3 -m venv venv
source venv/bin/activate
pip install paho-mqtt==1.6.1 piper-tts

# Голос Piper (пока есть интернет, ~60MB)
mkdir -p models/piper
wget -P models/piper https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx
wget -P models/piper https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx.json

# Звук: колонка в 3.5мм или USB
aplay -l                # список устройств
speaker-test -twav -c2  # должен шуметь
```

Два сервиса (юниты ниже):

```ini
# /etc/systemd/system/astra-core.service  — мозг (интенты, MQTT)
[Unit]
Description=Astra Core
After=network-online.target docker.service

[Service]
User=pi
WorkingDirectory=/home/pi/smart_home
ExecStart=/home/pi/smart_home/venv/bin/python services/astra/astra_core.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/astra-tts.service  — голос (Piper)
[Unit]
Description=Astra TTS (Piper)
After=astra-core.service

[Service]
User=pi
WorkingDirectory=/home/pi/smart_home
Environment=PIPER_MODEL_DIR=/home/pi/smart_home/models/piper
ExecStart=/home/pi/smart_home/venv/bin/python services/astra/tts_service.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now astra-core astra-tts
```

Проверка голоса, не дожидаясь Pi5:
```bash
mosquitto_pub -h localhost -u garage -P garage2026 -t astra/tts/say -m "Проверка связи"
```

---

## Полка 5 — Офлайн-подготовка (ОБЯЗАТЕЛЬНО пока есть интернет)

Полностью офлайн-система = все образы и модели уже на месте:

```bash
# 1. Docker-образы в архив (на случай переезда/наката)
docker save $(docker images --format '{{.Repository}}:{{.Tag}}' | grep -v '<none>') \
  | gzip > offline-images.tar.gz   # ~2-3GB, на ноут/флешку

# 2. Модель Ollama уже в ./ollama/ (volume) — попадает в бэкап репо/диска
# 3. Голос Piper уже в models/piper/
# 4. Pi5 отдельно: Whisper + FaceID модели — см. docs/07, полка Pi5
```

---

## Полка 6 — Контрольная проверка (всё зелёное = Pi4 готов)

- [ ] `docker ps` — 5-6 контейнеров Up
- [ ] `mosquitto_sub -t 'garage/#' -v` — видит сообщения симулятора с Pi5
- [ ] Сценарий `cold` симулятора → регулятор сам публикует `garage/actuator/heater ON`
- [ ] InfluxDB: запись истории идёт (логгер active, запрос bucket в UI :8086 возвращает точки)
- [ ] http://pi4:8123 — HA видит MQTT
- [ ] `systemctl status astra-core astra-tts` — active (running)
- [ ] `mosquitto_pub -t astra/tts/say -m "Тест"` — говорит голосом
- [ ] `ping 10.0.0.2` — Pi5 на месте
- [ ] `curl http://localhost:11434/api/tags` — phi3:mini в списке (если Ollama включена)

После этого Pi4 ждёт только данных: симулятор/ESP32 с Pi5 — и всё оживает.

---

## Порядок установки одной строкой

**Полка 0** ОС → **1** сеть → **2** Docker → **3** стек → **4** Astra+голос → **5** офлайн-бэкап → **6** проверка. Никогда не прыгай через слой.
