# Astra — голосовой ассистент умного гаража (офлайн)

Локальный ассистент, работает без интернета на Pi4.

## Архитектура Astra

```
[Pi5] ReSpeaker -> openWakeWord ("Астра") -> Whisper small ru -> MQTT astra/stt/text
                                                                            |
[Pi4] Astra Core -----------------------------------------------------------+
  |-> Intent Parser (HA intents)
  |   - "включи свет" -> garage/actuator/light ON
  |   - "какая температура" -> garage/climate/temp?
  |   - "открой ворота" -> garage/actuator/gate OPEN
  |
  |-> LLM Fallback (Ollama phi3:mini)
  |   - "что такое угарный газ" -> ответ
  |
  |-> Proactive Alerts
  |   - CO > 50ppm -> "Внимание, загазованность!"
  |
  |-> TTS Piper ru_RU-irina-medium -> speaker
```

## Установка на Pi4

Модели скачать заранее (офлайн):

```bash
mkdir -p models/piper models/ollama
# Piper
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx
# Ollama phi3:mini
docker exec ollama ollama pull phi3:mini
```

## Топики MQTT

- `astra/stt/text` — Pi5 -> Pi4, распознанный текст
- `astra/tts/say` — Pi4 -> Pi4, текст для озвучки
- `astra/intent/result` — результат интента
- `garage/actuator/#` — команды

## Команды для диплома

- "Астра, включи свет"
- "Астра, какая температура в гараже"
- "Астра, что с газом"
- "Астра, кто был в гараже"
- "Астра, открой ворота"
- "Астра, что такое CO"

## Wake Word "Астра"

Обучить кастомный wake word:

1. Записать 20 сэмплов "Астра" в тишине
2. Использовать openwakeword training: https://github.com/fwartner/openwakeword
3. Получить модель `astra.tflite`
4. Положить в `models/wakeword/`

Или использовать `hey_jarvis` для прототипа и переименовать в дипломе.
