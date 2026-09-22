# Smart Garage + Astra — дипломный проект

> Контроль климата, газа, света, трекинг радаром, СКУД по лицу и отпечатку, голосовой ассистент **Astra**. Полностью офлайн, 2x Pi, Coral M.2 TPU.

**Финальная структура для диплома:**
- **Pi4 — SERVER + ASTRA BRAIN** (192.168.4.1): Mosquitto, HA, Influx, Grafana, Astra Core (Piper TTS + Ollama), ESP control, GarageNet AP
- **Pi5 — PERCEPTION NODE + CORAL** (10.0.0.2): FaceID (BlazeFace Coral + InsightFace), Voice STT (Whisper), Radar LD2450, R503, PiCam NoIR, Frigate

## 📚 Документация

1.  [**00_ANALYSIS.md**](./docs/00_ANALYSIS.md) — анализ задачи, риски, оценка
2.  [**01_ARCHITECTURE.md**](./docs/01_ARCHITECTURE.md) — базовая архитектура (1 Pi)
3.  [**01b_ARCHITECTURE_OFFLINE_DUAL_PI.md**](./docs/01b_ARCHITECTURE_OFFLINE_DUAL_PI.md) — v2: Офлайн на 2x Pi
4.  [**01c_CORAL_INTEGRATION.md**](./docs/01c_CORAL_INTEGRATION.md) — интеграция Coral M.2 TPU (pci:0), бенчмарки 29x speedup, Frigate + BlazeFace
5.  [**07_FINAL_ARCHITECTURE_ASTRA.md**](./docs/07_FINAL_ARCHITECTURE_ASTRA.md) — **v3 ФИНАЛЬНАЯ для диплома: Pi4 Server+Astra, Pi5 Perception+Coral**
6.  [**02_HARDWARE_BOM.md**](./docs/02_HARDWARE_BOM.md) — BOM с ценами DE
7.  [**03_SOFTWARE_PLAN.md**](./docs/03_SOFTWARE_PLAN.md) — софт план, ESPHome, Python
8.  [**04_IMPLEMENTATION_ROADMAP.md**](./docs/04_IMPLEMENTATION_ROADMAP.md) — план на 8 недель
9.  [**05_OFFLINE_SETUP.md**](./docs/05_OFFLINE_SETUP.md) — офлайн настройка, hostapd, RTC, модели
10. [**08_DIPLOMA_TODO.md**](./docs/08_DIPLOMA_TODO.md) — что осталось для диплома, сценарий защиты
11. [`services/astra/astra_core.py`](./services/astra/astra_core.py) — ядро Astra, интент-парсер, MQTT, TTS
12. [`services/face/coral_face_detector.py`](./services/face/coral_face_detector.py) — FaceID на Coral + InsightFace
13. [`frigate/config.yml`](./frigate/config.yml) — Frigate для Pi5 + Coral pci:0

## 🚀 Быстрый старт

```bash
# Pi4 Server + Astra
docker compose -f docker-compose.pi4.yml up -d

# Pi5 Perception + Coral
# Предварительно: установка драйвера Coral по https://github.com/Gr1n95/Raspberry-Pi5-Edge-M.2-Coral_TPU
docker compose -f docker-compose.pi5.yml up -d
```

## 🧠 Astra — голосовой ассистент

- Wake word: "Астра" (openWakeWord)
- STT: faster-whisper small ru на Pi5 -> MQTT astra/stt/text -> Pi4
- Brain: Astra Core на Pi4 — intents + Ollama phi3:mini
- TTS: Piper ru_RU-irina-medium на Pi4

Команды: "Астра, включи свет", "Астра, что с газом", "Астра, кто был в гараже"

## 🔗 Связанные репозитории

- Coral M.2 TPU setup: https://github.com/Gr1n95/Raspberry-Pi5-Edge-M.2-Coral_TPU — используется в этом проекте как ускоритель

## 🚀 Быстрый старт MVP

```bash
# На Raspberry Pi 5
git clone <repo>
cd smart_home
docker-compose up -d mosquitto influxdb grafana
# Прошить ESP32 через ESPHome, подключить BME280
# Открыть http://pi-ip:3000 — графики
# Открыть http://pi-ip:8000/docs — API
```

## 🧠 Идея

```
Датчики (ESP32) --MQTT--> Raspberry Pi 5 --реле--> Обогреватель/Вентилятор/Свет
Радар LD2450 --> трекинг людей
PiCam NoIR + R503 --> FaceID + Fingerprint --> Замок
ReSpeaker --> Whisper + Piper --> Локальная Алиса
```

## 🔒 Безопасность

- VPN WireGuard, без проброса портов
- Liveness detection для лица
- Механический ключ всегда!
- CO тревога: вытяжка + ворота + Telegram

## Следующие шаги

Смотри ROADMAP. Начни с недели 1 — ядро.

---
Автор: план сгенерирован для проекта умного гаража, Nuremberg 2026
