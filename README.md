# Smart Garage — программно-аппаратный комплекс для гаража

> Контроль климата, газа, света, трекинг людей радаром, СКУД по лицу и отпечатку, голосовой помощник. **Полностью офлайн, 2x Pi.**

Этот репозиторий — план, документация и MVP код.

## 📚 Документация

1.  [**00_ANALYSIS.md**](./docs/00_ANALYSIS.md) — мое мнение о задаче, риски, оценка
2.  [**01_ARCHITECTURE.md**](./docs/01_ARCHITECTURE.md) — базовая архитектура (1 Pi)
3.  [**01b_ARCHITECTURE_OFFLINE_DUAL_PI.md**](./docs/01b_ARCHITECTURE_OFFLINE_DUAL_PI.md) — **v2: Офлайн на 2x Pi (Pi4 Home Brain + Pi5 AI Brain) — актуальная**
4.  [**02_HARDWARE_BOM.md**](./docs/02_HARDWARE_BOM.md) — что покупать в DE, с ценами
5.  [**03_SOFTWARE_PLAN.md**](./docs/03_SOFTWARE_PLAN.md) — как писать софт, примеры кода ESPHome / Python
6.  [**04_IMPLEMENTATION_ROADMAP.md**](./docs/04_IMPLEMENTATION_ROADMAP.md) — пошаговый план на 8 недель
7.  [**05_OFFLINE_SETUP.md**](./docs/05_OFFLINE_SETUP.md) — чеклист настройки без интернета, WiFi AP, RTC, модели
8.  [**01c_CORAL_INTEGRATION.md**](./docs/01c_CORAL_INTEGRATION.md) — **интеграция твоего Coral M.2 TPU, бенчмарки, Frigate + BlazeFace**
9.  [`frigate/config.yml`](./frigate/config.yml) — конфиг Frigate для Pi5 + Coral pci:0
10. [`services/face/coral_face_detector.py`](./services/face/coral_face_detector.py) — сервис FaceID на Coral + InsightFace

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
