# Quickstart — запуск за вечер (Фаза 0-1)

## Что нужно на столе

- Pi4 (любой RAM) + SD 32GB
- Pi5 8GB + SD + Coral M.2 (уже установлен по твоему гайду)
- ESP32 DevKit + BME280 + провода
- Ethernet патч-корд 1м
- Ноут

## Шаг 1: Pi4 — сервер (30 мин)

```bash
# На Pi4
sudo apt update && sudo apt install -y git
git clone https://github.com/Gr1n95/smart_home.git
cd smart_home
bash scripts/pi4/01-install-docker-mosquitto.sh
# Перелогиниться, чтобы docker без sudo
# Проверить:
bash scripts/pi4/test-mqtt.sh
```

Должен увидеть `garage/test Pi4 online`.

## Шаг 2: Pi5 — проверка Coral + связь (15 мин)

```bash
# На Pi5
cd ~/smart_home
bash scripts/pi5/01-check-coral.sh
# Ожидаем /dev/apex_0 и [{'type': 'pci', 'path': '/dev/apex_0'}]

# Подключить Ethernet кабель Pi4<->Pi5
# На Pi4 eth0 10.0.0.1 уже настроен в dhcpcd.conf? Если нет — вручную:
# sudo ip addr add 10.0.0.1/24 dev eth0

# На Pi5:
sudo ip addr add 10.0.0.2/24 dev eth0
ping 10.0.0.1

bash scripts/pi5/02-test-mqtt.sh
```

На Pi4 в `test-mqtt.sh` должен прийти `Pi5 online`.

## Шаг 3: ESP32 + BME280 (30 мин)

1.  Установить ESPHome на ноут: `pip install esphome`
2.  Скопировать `esphome/secrets.yaml.example` -> `secrets.yaml`, вписать WiFi
3.  Подключить BME280: VCC 3.3V, GND, SDA GPIO21, SCL GPIO22
4.  Прошить:
    ```bash
    esphome run esphome/garage-climate.yaml --device /dev/ttyUSB0
    ```
5.  В логах ESPHome увидишь температуру, и в MQTT на Pi4:
    ```bash
    mosquitto_sub -h localhost -u garage -P garage2026 -t "garage/#" -v
    # garage/climate/temp 22.5
    ```

## Шаг 4: Grafana (10 мин)

```bash
# На Pi4
docker compose -f docker-compose.pi4.yml up -d influxdb grafana
# Открыть http://10.0.0.1:3000 (или http://192.168.4.1:3000 если AP поднят)
# admin/admin
# Add datasource InfluxDB, bucket garage
```

## Итого за вечер

- Pi4 Mosquitto работает
- Pi5 видит Pi4 по Ethernet и Coral работает
- ESP32 шлет температуру в Grafana
- Скелет готов — Фаза 1 done

## Дальше — Фаза 2: газ и отпечаток

- MQ-7 подключить к GPIO34, оставить на 48ч прогрев
- R503 к Pi5 /dev/ttyUSB0, запустить fingerprint_service

Смотри `docs/09_WORK_PLAN_PRACTICAL.md` для следующих фаз.
