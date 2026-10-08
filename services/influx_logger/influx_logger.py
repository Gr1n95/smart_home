#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Логгер истории: MQTT garage/# -> InfluxDB.
Регулятор решает по событиям в реальном времени и БД в контуре управления
не участвует — база нужна для истории: анализ за период, результаты
испытаний для диплома, вопросы Astra вида "какая была температура ночью".

Измерения (bucket: garage):
  climate  fields: temp, humidity, pressure
  gas      fields: co
  light    fields: lux
  presence fields: targets (int)
  gate     fields: closed (bool)
  alarm    fields: value, tag: type
  actuator fields: state(bool=1/0), tag: device (события реле)

Запуск (systemd unit в docs/13_PI4_INSTALL.md):
  INFLUX_URL=http://localhost:8086 INFLUX_TOKEN=... INFLUX_ORG=garage \
    INFLUX_BUCKET=garage python3 influx_logger.py
"""

import json
import os
import sys

try:
    import paho.mqtt.client as mqtt
except ImportError:
    sys.exit("Нужен paho-mqtt: pip install paho-mqtt==1.6.1")
try:
    from influxdb_client import InfluxDBClient, Point, WritePrecision
    from influxdb_client.client.write_api import SYNCHRONOUS
except ImportError:
    sys.exit("Нужен influxdb-client: pip install influxdb-client")

URL = os.environ.get("INFLUX_URL", "http://localhost:8086")
TOKEN = os.environ.get("INFLUX_TOKEN", "")
ORG = os.environ.get("INFLUX_ORG", "garage")
BUCKET = os.environ.get("INFLUX_BUCKET", "garage")

# garage/climate/temp -> ("climate", "temp")
TOPIC_MAP = {
    "garage/climate/temp": ("climate", "temp", float),
    "garage/climate/humidity": ("climate", "humidity", float),
    "garage/climate/pressure": ("climate", "pressure", float),
    "garage/gas/co": ("gas", "co", float),
    "garage/light/lux": ("light", "lux", float),
    "garage/gate/state": ("gate", "closed", lambda p: p.strip().upper() == "CLOSED"),
}


class Logger:
    def __init__(self):
        self.influx = InfluxDBClient(url=URL, token=TOKEN, org=ORG)
        self.write = self.influx.write_api(write_options=SYNCHRONOUS)
        self.mqtt = mqtt.Client(
            client_id="influx-logger", callback_api_version=mqtt.CallbackAPIVersion.VERSION1
        )
        self.mqtt.username_pw_set(
            os.environ.get("MQTT_USER", "garage"), os.environ.get("MQTT_PASS", "garage2026")
        )

    def on_connect(self, c, *_):
        print("[LOG] MQTT connected, подписка garage/#", flush=True)
        c.subscribe("garage/#")

    def on_message(self, _c, _u, msg):
        topic, payload = msg.topic, msg.payload.decode("utf-8", "ignore").strip()
        try:
            if topic in TOPIC_MAP:
                meas, field, cast = TOPIC_MAP[topic]
                p = Point(meas).field(field, cast(payload)).time(int(time.time_ns()), WritePrecision.NS)
                self.write.write(bucket=BUCKET, org=ORG, record=p)
            elif topic == "garage/security/radar":
                n = len(json.loads(payload).get("targets", []))
                p = Point("presence").field("targets", n).time(int(time.time_ns()), WritePrecision.NS)
                self.write.write(bucket=BUCKET, org=ORG, record=p)
            elif topic == "garage/alarm":
                d = json.loads(payload)
                p = (Point("alarm").tag("type", str(d.get("type", "?")))
                     .field("value", float(d.get("value", 0) or 0))
                     .time(int(time.time_ns()), WritePrecision.NS))
                self.write.write(bucket=BUCKET, org=ORG, record=p)
            elif topic.startswith("garage/actuator/"):
                dev = topic.split("/")[-1]
                p = (Point("actuator").tag("device", dev)
                     .field("state", 1 if payload.upper() == "ON" else 0)
                     .time(int(time.time_ns()), WritePrecision.NS))
                self.write.write(bucket=BUCKET, org=ORG, record=p)
        except (ValueError, json.JSONDecodeError) as e:
            print(f"[LOG] skip {topic}: {e}", flush=True)

    def run(self):
        self.mqtt.on_connect = self.on_connect
        self.mqtt.on_message = self.on_message
        self.mqtt.connect(os.environ.get("MQTT_HOST", "localhost"), 1883, 30)
        self.mqtt.loop_forever()


if __name__ == "__main__":
    if not TOKEN:
        print("[LOG] ВНИМАНИЕ: INFLUX_TOKEN не задан — запись будет падать", flush=True)
    print(f"[LOG] MQTT garage/# -> InfluxDB {URL} bucket={BUCKET}", flush=True)
    Logger().run()
