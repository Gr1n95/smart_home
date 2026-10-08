#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Watcher — подсистема обнаружения резких изменений параметров
и проактивного речевого информирования через Astra.

Роль в системе (разделение ответственности):
  Регулятор  — РЕАГИРУЕТ: датчик -> правило -> реле (рефлекс)
  Watcher    — ИНФОРМИРУЕТ: скорость изменения -> голосовое предупреждение
  Astra TTS  — ОЗВУЧИВАЕТ: astra/tts/say -> Piper -> колонка

Идея: следим не только за значением, но и за ПЕРВОЙ ПРОИЗВОДНОЙ
(скоростью изменения). Резкий рост CO — предупредить ещё ДО порога 50 ppm,
когда регулятор молчит. Резкое падение температуры — предупредить до
заморозка. Резкое падение давления в помещении — верный признак открывшихся
ворот (атмосфера так быстро не меняется).

Правила (пороги изменения за окно 5 мин, настраиваются ниже):
  CO        +10 ppm/мин (скорость) -> "Угарный газ быстро растёт" (раннее предупреждение)
  Температура >2.0 C за окно -> "Температура резко падает/растёт"
  Влажность  +10 % за окно -> "Резко растёт влажность, возможен конденсат"
  Давление   -2 гПа за окно -> "Давление резко упало — возможно открыли ворота"
  Давление   +2 гПа за окно -> "Давление резко выросло — ворота закрыли"

Антиспам: cooldown 300 сек на тип события + минимум 60 сек между озвучками.

Публикует:
  astra/tts/say   текст для озвучки (Piper)
  garage/alert    JSON-событие {type, value, rate, message} — для лога/Influx

Запуск: systemd юнит astra-watcher (см. docs/13_PI4_INSTALL.md).
"""

import json
import os
import sys
import time
from collections import deque

try:
    import paho.mqtt.client as mqtt
except ImportError:
    sys.exit("Нужен paho-mqtt: pip install paho-mqtt==1.6.1")

BROKER = os.environ.get("MQTT_HOST", "localhost")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
USER = os.environ.get("MQTT_USER", "garage")
PASS = os.environ.get("MQTT_PASS", "garage2026")

WINDOW_S = 300          # окно анализа скорости: 5 минут
COOLDOWN_S = 300        # не повторять один тип события чаще 5 мин
GLOBAL_GAP_S = 60       # минимум между любыми озвучками

CO_RATE = 10.0          # ppm/мин
TEMP_RATE = 2.0         # °C за окно 5 мин
HUM_RATE = 10.0         # % за окно
PRESS_RATE = 2.0        # гПа за окно


def window_delta(dq):
    """Изменение за окно: v_посл - v_перв. None если мало данных."""
    if len(dq) < 2:
        return None
    (t0, v0), (t1, v1) = dq[0], dq[-1]
    if t1 - t0 < 60:        # меньше минуты данных — не судим
        return None
    return v1 - v0


class Watcher:
    def __init__(self):
        self.series = {
            "temp": deque(maxlen=400),      # ~13 мин при тике 2с
            "humidity": deque(maxlen=400),
            "pressure": deque(maxlen=400),
            "co": deque(maxlen=400),
        }
        self.last_alert = {}                # type -> ts
        self.last_speak = 0.0
        self.client = mqtt.Client(
            client_id="astra-watcher", callback_api_version=mqtt.CallbackAPIVersion.VERSION1
        )
        if USER:
            self.client.username_pw_set(USER, PASS)

    def start(self):
        c = self.client
        c.on_connect = self.on_connect
        c.on_message = self.on_message
        c.connect(BROKER, PORT, keepalive=30)
        print(f"[WATCH] старт, брокер {BROKER}:{PORT}, окно {WINDOW_S}s", flush=True)
        c.loop_forever()

    def on_connect(self, c, *_):
        c.subscribe([
            ("garage/climate/#", 0),
            ("garage/gas/co", 0),
        ])
        print("[WATCH] подписан на климат и газ", flush=True)

    def on_message(self, _c, _u, msg):
        t, p = msg.topic, msg.payload.decode("utf-8", "ignore").strip()
        key = {"garage/climate/temp": "temp",
               "garage/climate/humidity": "humidity",
               "garage/climate/pressure": "pressure",
               "garage/gas/co": "co"}.get(t)
        if not key:
            return
        try:
            value = float(p)
        except ValueError:
            return
        self.series[key].append((time.time(), value))
        self.check(key)

    def check(self, key):
        dq = self.series[key]
        delta = window_delta(dq)
        if delta is None:
            return
        now = time.time()
        v_now = dq[-1][1]
        rate = delta / (WINDOW_S / 60.0)   # для сообщений: в минуту

        alerts = []
        if key == "co" and rate >= CO_RATE:
            alerts.append(("co_rise",
                f"Внимание. Угарный газ быстро растёт: {v_now:.0f} частей на миллион, "
                f"плюс {rate:.0f} в минуту. Рекомендуется проветрить помещение."))
        elif key == "temp" and delta <= -TEMP_RATE:
            alerts.append(("temp_drop",
                f"Температура резко падает: {v_now:.1f} градусов, "
                f"изменение {delta:.1f} за пять минут. Проверьте обогрев."))
        elif key == "temp" and delta >= TEMP_RATE:
            alerts.append(("temp_rise",
                f"Температура резко растёт: {v_now:.1f} градусов, "
                f"плюс {delta:.1f} за пять минут."))
        elif key == "humidity" and delta >= HUM_RATE:
            alerts.append(("hum_rise",
                f"Резко растёт влажность: {v_now:.0f} процентов. "
                f"Возможен конденсат, рекомендуется вентиляция."))
        elif key == "pressure" and delta <= -PRESS_RATE:
            alerts.append(("press_drop",
                "Давление в помещении резко упало. Возможно, открылись ворота или дверь."))
        elif key == "pressure" and delta >= PRESS_RATE:
            alerts.append(("press_rise",
                "Давление резко выросло. Ворота, вероятно, закрыли."))

        for a_type, message in alerts:
            if now - self.last_alert.get(a_type, 0) < COOLDOWN_S:
                continue
            if now - self.last_speak < GLOBAL_GAP_S:
                continue  # не перебиваем предыдущую озвучку
            self.last_alert[a_type] = now
            self.last_speak = now
            print(f"[WATCH] {a_type}: delta={delta:.2f} за {WINDOW_S}s -> {message[:70]}", flush=True)
            self.client.publish("astra/tts/say", message)
            self.client.publish("garage/alert", json.dumps({
                "type": a_type, "value": v_now, "delta": round(delta, 2),
                "rate_per_min": round(rate, 2),
                "message": message, "ts": now}, ensure_ascii=False))


if __name__ == "__main__":
    Watcher().start()
