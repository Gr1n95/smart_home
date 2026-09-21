# Софт — как писать

## Стек, который я рекомендую

Не изобретай велосипед. 90% умного дома уже решено.

### Вариант A: Быстрый (рекомендую для старта)
**Home Assistant OS + ESPHome + Node-RED**

1.  На Pi ставишь HA OS.
2.  ESP32 прошиваешь через ESPHome (YAML, без кода): BME280, BH1750, MQ — сразу в HA.
3.  Радар LD2450 — в ESPHome уже есть компонент.
4.  Автоматизации — в HA UI.
5.  FaceID и отпечаток — пишешь аддон на Python (Docker) который дергает HA API.

Плюс: за неделю уже все работает и есть приложение на телефоне.

### Вариант B: Свой (для диплома / если хочешь контроль)
**Custom Python Stack**

```
/backend
  /app
    main.py (FastAPI)
    mqtt_client.py
    sensors/
      bme280.py
      gas.py
      light.py
      radar_ld2450.py
    access/
      face_recognizer.py
      fingerprint_r503.py
      lock_controller.py
    climate/
      regulator.py (PID)
    voice/
      stt.py (whisper)
      tts.py (piper)
      assistant.py
    db/
      models.py
  docker-compose.yml
/frontend
  React + Vite + Recharts (графики)
```

## Ключевые модули — детали реализации

### 1. Датчики (ESP32 код)
Используй ESPHome YAML пример:

```yaml
sensor:
  - platform: bme280
    temperature:
      name: "Garage Temp"
    humidity:
      name: "Garage Humidity"
    address: 0x76
    update_interval: 10s

  - platform: bh1750
    name: "Garage Lux"
    address: 0x23

  - platform: adc
    pin: 34
    name: "MQ-7 CO"
    filters:
      - calibrate_linear:
          - 0.0 -> 0.0
          - 1.0 -> 100.0
```

Калибровка MQ: прогрев 48ч, потом на чистом воздухе замерить Ro, потом по даташиту формула Rs/Ro.

### 2. Радар LD2450
Подключение: 5V, GND, TX->RX ESP32, RX->TX ESP32, 115200 baud.

Протокол: парсишь кадры по даташиту. Есть готовые библиотеки: `ld2450` для ESPHome / Python.

Выход: JSON:
```json
{"targets": [{"x": -1200, "y": 2500, "speed": 50, "distance": 2780}, ...], "count": 1}
```

Трекинг: фильтр Калмана, чтобы не дребезжал.

### 3. FaceID
Стек:
- `picamera2` для захвата
- `insightface` (buffalo_l) — самая точная, работает на Pi 5 ~0.8с на лицо
- База: `faces.db` — id, name, embedding (pickle), photo_path

Процесс регистрации:
```python
import insightface
model = insightface.app.FaceAnalysis()
model.prepare(ctx_id=0, det_size=(640,640))
faces = model.get(frame)
embedding = faces[0].normed_embedding
# сохранить
```

Распознавание: косинусная близость >0.5 = match.

Liveness: простой вариант — просить моргнуть (eye aspect ratio) или использовать ИК: у фото нет ИК блика в глазах.

### 4. Отпечаток R503
Библиотека: `pyfingerprint` или `adafruit_fingerprint`.

Подключение UART 57600.

Логика: на R503 можно хранить до 200 отпечатков прямо в модуле. Pi только спрашивает ID.

### 5. Регулировка климата
Не просто if, а PID + гистерезис.

```python
# Пример
if gas_co > 70:
    emergency_mode()
elif humidity > 75:
    fan.on(speed=100)
    if temp < 3: heater.on()
elif temp < 5:
    heater.on()
    fan.on(speed=30) # циркуляция
```

Обязательно: дедлайн таймер для обогревателя (не более 2ч подряд), защита от перегрева.

### 6. Голосовой ассистент
Архитектура офлайн:

```
[ReSpeaker] -> VAD (silero) -> Whisper small ru -> Text
Text -> Intent (HA Assist) -> Action -> TTS Piper -> Speaker
        |
        -> LLM (Ollama) для болталки: "а что такое CO?"
```

Whisper на Pi 5: ~1.5с на фразу 3с.

Piper TTS: почти реалтайм.

Wake word: `openwakeword` с моделью "hey_jarvis" или обучить "привет гараж".

### 7. Уведомления и UI
- Telegram бот: `python-telegram-bot` — фото с камеры + графики при тревоге
- Frontend: Home Assistant Lovelace уже дает дашборд. Если свой — Grafana для графиков + React для управления.

## Безопасность данных
- Фото лиц — шифровать на диске (LUKS)
- Эмбеддинги — не обратимы, но все равно не светить
- Логи доступа — хранить год

## Тестирование
1.  Юнит-тесты для регулятора
2.  Тест газа: баллончик CO2 / дым
3.  Тест FaceID: 20 людей, разное освещение, очки, шапка
4.  Тест радара: пройтись по гаражу, проверить зоны
5.  Стресс-тест: вырубить интернет, вырубить свет
