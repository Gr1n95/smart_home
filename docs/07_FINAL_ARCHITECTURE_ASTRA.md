# Финальная архитектура дипломного проекта: Smart Garage + Astra

> **Astra** — локальный голосовой ассистент гаража. Полностью офлайн. Название для диплома.
> **Структура для диплома: Pi4 = Сервер + Astra + ESP, Pi5 = Распознавание (Face + Voice) + Coral**

Ты правильно решил: **весь сервер на Pi4**. Это логично для диплома — один главный узел, второй — сопроцессор восприятия. Так проще защищать.

## Итоговая схема v3 (дипломная)

```
                    ГАРАЖНАЯ СЕТЬ OFFLINE
                    GarageNet WiFi AP на Pi4 (192.168.4.1)
                    Прямой Ethernet Pi4 <-> Pi5 (10.0.0.0/24)

┌─────────────────────────────────────────────────────────────────────────┐
│ Pi4 — SERVER + ASTRA BRAIN (192.168.4.1 / 10.0.0.1) — ГЛАВНЫЙ ДЛЯ ДИПЛОМА│
│ Роль: Мозг, сервер, голос Astra                                         │
│ Железо: DS3231 RTC, UPS HAT, SSD 256GB, ReSpeaker? Нет, mic на Pi5      │
│         Реле 4ch, сирена, Ethernet, WiFi AP                             │
│ Софт (критичный, дипломный):                                            │
│  - Mosquitto MQTT (главный брокер)                                      │
│  - Home Assistant + InfluxDB + Grafana                                  │
│  - FastAPI Backend (регулятор климата/газа/света)                       │
│  - Astra Core:                                                          │
│     * Dialogue Manager (python)                                         │
│     * Intent Router (HA intents)                                        │
│     * Piper TTS ru_RU-irina (говорит Astra)                             │
│     * Ollama phi3:mini 3.8B Q4 (болталка, Q&A)                          │
│     * Speaker (3W колонка)                                              │
│  - ESP Controller (ESPHome API)                                         │
│  - hostapd + dnsmasq (GarageNet)                                        │
│  - База данных: SQLite (лица, доступы), Influx (телеметрия)             │
│                                                                         │
│  MQTT топики публикует/слушает:                                         │
│   garage/climate/#, garage/actuator/#, astra/#, garage/access/#         │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ MQTT + HTTP API
                               │ 10.0.0.2 -> 10.0.0.1
┌──────────────────────────────▼──────────────────────────────────────────┐
│ Pi5 — PERCEPTION NODE + CORAL (10.0.0.2 / 192.168.4.2) — СОПРОЦЕССОР     │
│ Роль: Глаза и уши, тяжелое распознавание                                │
│ Железо: Coral M.2 TPU (/dev/apex_0) — твой гайд, PiCam3 NoIR + ИК,      │
│         R503 fingerprint, LD2450 radar, ReSpeaker 2-Mics (микрофоны)     │
│ Софт (тяжелый):                                                         │
│  - face_service:                                                        │
│     BlazeFace Coral (pci:0) 25ms -> crop -> InsightFace buffalo_s CPU   │
│     150ms -> garage/access/face/result {name, score} -> MQTT к Pi4      │
│  - fingerprint_service: R503 -> garage/access/finger/result             │
│  - radar_service: LD2450 -> garage/security/radar {count, x,y}          │
│  - voice_recognition:                                                   │
│     openWakeWord ("Астра") -> faster-whisper small ru -> текст          │
│     -> MQTT astra/stt/text {text: "включи свет"} -> Pi4 Astra           │
│  - Frigate (опционально): person/car detect на Coral 12ms               │
│                                                                         │
│  Ничего не решает сам, только распознает и шлет на Pi4.                 │
│  Если Pi5 упал — Pi4 продолжает работать (газ, свет, отпечаток на Pi4). │
└─────────────────────────────────────────────────────────────────────────┘
         │              │
      [ESP32-1]      [ESP32-2]   [Телефон -> GarageNet -> HA 192.168.4.1:8123]
      BME280+MQ      BH1750+геркон+реле
      Климат+Газ     Свет+ворота
```

## Поток данных Astra (пример)

1.  Человек в гараже говорит: **"Астра, включи свет"**
2.  Pi5: ReSpeaker -> VAD -> openWakeWord детектит "Астра" (модель hey_jarvis переобучена на Astra)
3.  Pi5: запись 4 сек -> faster-whisper small ru (1.2 сек на Pi5 CPU) -> текст "включи свет"
4.  Pi5: MQTT `astra/stt/text` -> `{"text":"включи свет","ts":...}` -> Pi4
5.  Pi4: Astra Core получает текст
    - HA Intent: `HassTurnOn` -> `light.garage`
    - MQTT `garage/actuator/light` -> `ON` -> ESP32 включает реле
6.  Pi4: Piper TTS: "Включаю свет в гараже" -> `aplay` на колонку, подключенную к Pi4
7.  Pi4: логирует в Influx, отвечает в HA UI

**Задержка офлайн: ~2 сек от фразы до света. Приемлемо для диплома.**

Второй пример — доступ:
1.  Радар LD2450 на Pi5 видит человека -> включает ИК подсветку
2.  Pi5: Coral BlazeFace -> лицо -> InsightFace embedding -> сравнение -> `garage/access/face/result {"name":"Ivan","score":0.78}`
3.  Pi5: R503 палец -> `garage/access/finger/result {"id":1}`
4.  Pi4: получает оба, проверяет (лицо AND палец) -> `garage/actuator/lock OPEN` -> реле замка
5.  Pi4: Astra говорит: "Добро пожаловать, Иван"

## Почему так лучше для диплома

1.  **Четкое разделение по главам:**
    - Глава 2: Аппаратная часть — Pi4 сервер, Pi5 сопроцессор, Coral, датчики
    - Глава 3: Софт Pi4 — сервер, MQTT, HA, Astra Core (TTS, LLM)
    - Глава 4: Софт Pi5 — распознавание (Face, Voice STT) с Coral
    - Глава 5: Интеграция и тестирование

2.  **Весь сервер на Pi4 — проще защищать:** один IP, один дашборд, один AP. Комиссия подключается к GarageNet и видит все.

3.  **Pi5 как Edge AI ускоритель:** ты можешь сослаться на свой репозиторий Coral — это отдельный раздел диплома про ускорение нейросетей на Edge TPU.

4.  **Надежность:** даже если Pi5 сдох во время защиты, Pi4 покажет графики и включит свет. Демо не упадет.

## Что такое Astra технически

Astra — не просто Piper. Это 3 уровня:

**Уровень 1: Команды (HA Intents)**
- "Астра, включи свет/вытяжку/обогрев"
- "Астра, какая температура/влажность/газ"
- "Астра, кто был в гараже"
- Реализуется через Home Assistant intents YAML

**Уровень 2: Болталка (LLM)**
- "Астра, что такое угарный газ?"
- "Астра, почему в гараже влажно?"
- Ollama phi3:mini 3.8B Q4, промпт: "Ты Astra, ассистент умного гаража, отвечай кратко, по-русски, про гараж"

**Уровень 3: Проактивность**
- Astra сама говорит: "Внимание, CO 65 ppm, включаю вытяжку" (триггер от Pi4 regulator)
- "Иван, ворота открыты уже 10 минут"

Голос: Piper `ru_RU-irina-medium` — женский, приятный, офлайн. Можно переименовать в Astra.

Wake word: обучить модель "Астра" для openWakeWord. Есть гайд: записать 20 раз "Астра" и натренировать.

## Дипломная структура (рекомендую)

```
Введение — зачем умный гараж, проблема CO, безопасность
Глава 1 — Обзор аналогов (Aqara, Xiaomi, Home Assistant, Яндекс)
Глава 2 — Аппаратная часть
  2.1 Требования (офлайн, -15..+40, пыль, газ)
  2.2 Выбор Pi4/Pi5, ESP32, датчиков (BME280 vs DHT22)
  2.3 Coral M.2 TPU — твой гайд, почему M.2 а не USB
  2.4 Радар LD2450 vs PIR
  2.5 СКУД: PiCam NoIR + R503 + замок
  2.6 Схема подключения, питание 12В, UPS, RTC
Глава 3 — Программная часть Pi4 (Сервер + Astra)
  3.1 Архитектура MQTT, HA, Influx, Grafana
  3.2 Регулятор климата/газа (алгоритм, PID, гистерезис)
  3.3 Astra Core: STT->Intent->TTS, Piper, Ollama, Wake Word
  3.4 WiFi AP GarageNet, офлайн работа
Глава 4 — Программная часть Pi5 (Perception + Coral)
  4.1 FaceID: BlazeFace Coral + InsightFace
  4.2 Voice STT: Whisper small, openWakeWord
  4.3 Frigate + Coral person detection
  4.4 Radar трекинг
Глава 5 — Интеграция, тестирование, безопасность
  5.1 Тест газа, FaceID (20 человек, очки/шапка), радар
  5.2 Нагрузочное тестирование Pi4/Pi5 + Coral (таблица 29x speedup)
  5.3 Безопасность: LUKS, биометрия только эмбеддинги
Заключение
Приложения: BOM, схемы, код, ссылка на репозитории
```

## Конфиги под новую структуру

### docker-compose.pi4.yml (Сервер + Astra)

```yaml
services:
  mosquitto: ...
  homeassistant: ...
  influxdb: ...
  grafana: ...
  regulator: # газ/климат
  astra_core:
    build: ./services/astra
    ports: ["8001:8001"]
    devices: ["/dev/snd"]
    volumes: ["./models/piper:/data", "./models/ollama:/root/.ollama"]
    environment:
      - MQTT_BROKER=localhost
    # Piper + Ollama + Dialogue Manager
```

### docker-compose.pi5.yml (Perception)

```yaml
services:
  face_service:
    devices: ["/dev/apex_0", "/dev/video0"]
  whisper:
    image: rhasspy/wyoming-whisper
    command: --model small --language ru
  openwakeword:
    command: --preload-model 'astra' # кастом
  radar_service: ...
  fingerprint_service: ...
```

## Что делать дальше для диплома

1.  Переименовать Whisper wake word в "Астра" — записать датасет
2.  Написать `services/astra/dialogue_manager.py` — ядро Astra
3.  Сделать красивый дашборд HA с логотипом Astra
4.  Подготовить демо-сценарий для защиты (5 минут)

Хочешь, я сейчас сгенерирую код Astra Core и диалог-менеджер?
