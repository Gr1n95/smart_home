#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TTS-сервис Astra для Pi4: слушает MQTT astra/tts/say и озвучивает текст
через Piper (офлайн). Очередь — фразы не перебивают друг друга.

Зависимости (на Pi4):
  pip install paho-mqtt==1.6.1
  pip install piper-tts          # возьмёт onnxruntime, ставится на aarch64
  # голос: models/piper/ru_RU-irina-medium.onnx + .onnx.json

Запуск (см. systemd unit в docs/13_PI4_INSTALL.md):
  python3 tts_service.py
Env:
  MQTT_HOST (по умолч. localhost), PIPER_MODEL_DIR, PIPER_VOICE
"""

import os
import queue
import subprocess
import sys
import tempfile
import threading

try:
    import paho.mqtt.client as mqtt
except ImportError:
    sys.exit("Нужен paho-mqtt: pip install paho-mqtt==1.6.1")

BROKER = os.environ.get("MQTT_HOST", "localhost")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
USER = os.environ.get("MQTT_USER", "garage")
PASS = os.environ.get("MQTT_PASS", "garage2026")
MODEL_DIR = os.environ.get("PIPER_MODEL_DIR", "models/piper")
VOICE = os.environ.get("PIPER_VOICE", "ru_RU-irina-medium.onnx")

q: "queue.Queue[str]" = queue.Queue(maxsize=10)


def on_connect(client, userdata, flags, rc):
    print(f"[TTS] connected rc={rc}, подписка astra/tts/say", flush=True)
    client.subscribe("astra/tts/say")


def on_message(client, userdata, msg):
    text = msg.payload.decode("utf-8", "ignore").strip()
    if text:
        try:
            q.put_nowait(text)
        except queue.Full:
            # переполнили очередь — старые фразы теряем, свежая важнее
            try:
                q.get_nowait()
                q.put_nowait(text)
            except queue.Empty:
                pass


def speak(text):
    voice_path = os.path.join(MODEL_DIR, VOICE)
    if not os.path.exists(voice_path):
        print(f"[TTS] нет модели {voice_path}, пропускаю", flush=True)
        return
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav = f.name
    try:
        subprocess.run(
            ["piper", "--model", voice_path, "--output_file", wav],
            input=text.encode(), check=True, timeout=30,
        )
        subprocess.run(["aplay", wav], check=True, timeout=60)
        print(f"[TTS] озвучено: {text[:60]}", flush=True)
    finally:
        try:
            os.unlink(wav)
        except OSError:
            pass


def worker():
    while True:
        text = q.get()
        try:
            speak(text)
        except Exception as e:
            print(f"[TTS] ошибка: {e}", flush=True)


def main():
    threading.Thread(target=worker, daemon=True).start()
    client = mqtt.Client(
        client_id="pi4-tts", callback_api_version=mqtt.CallbackAPIVersion.VERSION1
    )
    client.username_pw_set(USER, PASS)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, keepalive=30)
    client.loop_forever()


if __name__ == "__main__":
    main()
