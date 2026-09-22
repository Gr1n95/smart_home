# Диплом: Smart Garage + Astra — что осталось сделать

## Текущий статус (что уже в репе)

- [x] Анализ, архитектура базовая и офлайн dual Pi
- [x] BOM, дорожная карта 8 недель
- [x] Интеграция Coral M.2 TPU (твой репозиторий) — бенчмарки, Frigate, BlazeFace
- [x] Финальная архитектура v3: Pi4 Server + Astra, Pi5 Perception + Coral
- [x] Код Astra Core (dialogue manager, intents, MQTT)
- [x] Код Coral Face Detector (BlazeFace EdgeTPU + InsightFace)
- [x] docker-compose.pi4.yml и pi5.yml
- [x] Frigate config для Coral pci:0
- [x] Офлайн чеклист (hostapd, RTC, модели)

## Что нужно для диплома (TODO)

### 1. Код Astra — доделать
- [ ] Обучить wake word "Астра" для openWakeWord (20 записей)
- [ ] Подключить Piper TTS на Pi4 (ru_RU-irina-medium)
- [ ] Подключить Ollama phi3:mini Q4 (2.2GB) для болталки
- [ ] Сделать `astra_api.py` — REST для HA: /astra/say, /astra/listen
- [ ] Логотип Astra (сгенерировать)

### 2. Pi5 Perception Node
- [ ] Собрать Docker образ face_service с pycoral + insightface
- [ ] Тест Coral: `python -c "from pycoral.utils import edgetpu; print(edgetpu.list_edge_tpus())"`
- [ ] Тест Whisper small ru на Pi5: время инференса 3 сек аудио
- [ ] Интеграция R503 fingerprint -> MQTT

### 3. Pi4 Server
- [ ] hostapd GarageNet + dnsmasq
- [ ] DS3231 RTC на оба Pi
- [ ] Mosquitto + HA + Influx + Grafana
- [ ] Регулятор: газ >50ppm -> вытяжка + сирена (код в backend/app/main.py уже есть)

### 4. Дипломный текст
- [ ] Глава 1: Обзор (используй 00_ANALYSIS)
- [ ] Глава 2: Железо (используй 02_HARDWARE_BOM + твой Coral репо)
- [ ] Глава 3: Софт Pi4 + Astra (используй 07_FINAL_ARCHITECTURE_ASTRA + astra_core.py)
- [ ] Глава 4: Софт Pi5 + Coral (используй 01c_CORAL_INTEGRATION + coral_face_detector.py)
- [ ] Глава 5: Тесты — таблица speedup Coral 29x, тест газа, тест FaceID
- [ ] Приложение: схемы, BOM, ссылка на GitHub

### 5. Демо для защиты (5 минут)
Сценарий:
1. Показать GarageNet WiFi, подключение телефона, дашборд HA (Pi4)
2. Поднести палец R503 -> Pi5 -> MQTT -> Pi4 -> замок открывается, Astra говорит "Добро пожаловать"
3. Сказать "Астра, включи свет" -> Pi5 Whisper -> Pi4 Astra -> реле -> свет
4. "Астра, что с газом" -> Astra отвечает телеметрию
5. Показать Frigate с Coral: детекция человека 12ms, график Grafana CO
6. Выдернуть Ethernet Pi5 — показать что Pi4 продолжает работать (газ, свет)

### 6. Презентация
- Слайд 1: Проблема — CO в гараже, кражи, нет офлайн решений
- Слайд 2: Архитектура v3 — Pi4 Server + Pi5 Perception + Coral
- Слайд 3: Coral M.2 — твой гайд, 29x speedup
- Слайд 4: Astra — офлайн ассистент, Piper + Whisper + phi3
- Слайд 5: Тесты, графики
- Слайд 6: Итог, BOM 500€, полностью автономно

## Вопросы к научруку

- Сколько страниц? 60-80?
- Нужен ли патент/новизна? (Coral + офлайн + Astra — уже новизна)
- Можно ли использовать твой репозиторий Coral как часть диплома? (Да, ссылка)
- Нужна ли печатная плата или можно на макетке?
