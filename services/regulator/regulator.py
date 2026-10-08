#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Регулятор гаража — подсистема автоматического управления (агент-рефлекс).

Философия: это НЕ LLM и не Astra. Это простой, всегда живой рефлекс:
событие датчика -> правило с гистерезисом -> команда актуатору.
Работает без интернета, без Astra, без Pi5. Ничего умного — поэтому надёжно.

Приоритеты:
  1. Газ (CO) — принудительная вентиляция + сирена, перекрывает всё
  2. Ручной режим (команды Astra/человека) — 15 мин не трогаем автоматикой
  3. Климат — обогрев/вентиляция по гистерезису
  4. Свет — темно + человек -> ON, человека нет 5 мин -> OFF

Правила (все с гистерезисом, чтобы не щёлкать реле):
  Обогреватель: T <= 3.0C -> ON,  T >= 8.0C -> OFF
  Вентиляция:   T >= 28C  -> ON,  T <= 24C  -> OFF (перегрев/двигатель)
                RH >= 75% -> ON,  RH <= 65% -> OFF (конденсат)
  Газ:          CO >= 50ppm -> вентиляция ON + сирена ON + alarm
                CO <= 30ppm -> сирена OFF (вентиляция может держаться
                              из-за климата)

Топики управления (Astra/человек могут командовать вручную):
  garage/actuator/heater ON|OFF
  garage/actuator/fan    ON|OFF
  garage/actuator/light  ON|OFF

Публикует:
  garage/actuator/*        команды (только при ИЗМЕНЕНИИ состояния)
  garage/alarm             тревога CO
  garage/regulator/state   heartbeat раз в 60с — полный статус (отладка без Grafana)

Запуск (systemd unit в docs/13_PI4_INSTALL.md):
  MQTT_HOST=localhost python3 regulator.py
"""

import json
import os
import sys
import threading
import time

try:
    import paho.mqtt.client as mqtt
except ImportError:
    sys.exit("Нужен paho-mqtt: pip install paho-mqtt==1.6.1")

# --- пороги (настройка одним местом) ---
HEAT_ON, HEAT_OFF = 3.0, 8.0        # антифриз: ниже 3 включаем, выше 8 выключаем
VENT_HOT_ON, VENT_HOT_OFF = 28.0, 24.0
VENT_HUM_ON, VENT_HUM_OFF = 75.0, 65.0
CO_ALARM, CO_CLEAR = 50.0, 30.0
LIGHT_ON_LUX = 50.0
PERSON_TIMEOUT = 300                 # нет человека 5 мин -> свет гасим
MANUAL_TIMEOUT = 900                 # ручная команда держится 15 мин
HEARTBEAT = 60

BROKER = os.environ.get("MQTT_HOST", "localhost")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
USER = os.environ.get("MQTT_USER", "garage")
PASS = os.environ.get("MQTT_PASS", "garage2026")


class Regulator:
    def __init__(self):
        self.lock = threading.Lock()
        self.s = {  # sensors
            "temp": None, "humidity": None, "co": None, "lux": None,
            "person": False, "person_ts": 0.0, "gate": None,
        }
        self.state = {"heater": False, "fan": False, "light": False, "siren": False}
        self.fan_reasons = set()     # {"gas"|"hot"|"humidity"}
        self.manual_until = {}       # device -> timestamp
        self.co_alarm_active = False
        self.client = mqtt.Client(
            client_id="pi4-regulator", callback_api_version=mqtt.CallbackAPIVersion.VERSION1
        )
        if USER:
            self.client.username_pw_set(USER, PASS)

    # ---------- MQTT ----------
    def start(self):
        c = self.client
        c.on_connect = self.on_connect
        c.on_message = self.on_message
        c.connect(BROKER, PORT, keepalive=30)
        c.loop_start()
        threading.Thread(target=self.heartbeat_loop, daemon=True).start()

    def on_connect(self, c, *_):
        print("[REG] connected, подписки...", flush=True)
        c.subscribe([
            ("garage/climate/#", 0),
            ("garage/gas/co", 0),
            ("garage/light/lux", 0),
            ("garage/security/radar", 0),
            ("garage/security/motion", 0),
            ("garage/gate/state", 0),
            ("garage/actuator/heater", 0),
            ("garage/actuator/fan", 0),
            ("garage/actuator/light", 0),
        ])

    def on_message(self, c, _u, msg):
        try:
            t, p = msg.topic, msg.payload.decode("utf-8", "ignore").strip()
            with self.lock:
                if t == "garage/climate/temp":
                    self.s["temp"] = float(p)
                elif t == "garage/climate/humidity":
                    self.s["humidity"] = float(p)
                elif t == "garage/gas/co":
                    self.s["co"] = float(p)
                elif t == "garage/light/lux":
                    self.s["lux"] = float(p)
                elif t == "garage/security/radar":
                    targets = json.loads(p).get("targets", [])
                    if targets:
                        self.s["person"] = True
                        self.s["person_ts"] = time.time()
                elif t == "garage/security/motion":
                    if p == "ON":
                        self.s["person"] = True
                        self.s["person_ts"] = time.time()
                elif t == "garage/gate/state":
                    self.s["gate"] = p
                elif t.startswith("garage/actuator/"):
                    dev = t.split("/")[-1]
                    if dev in ("heater", "fan", "light"):
                        # человек/Astra скомандовал вручную -> приоритет на 15 мин
                        self.manual_until[dev] = time.time() + MANUAL_TIMEOUT
                        print(f"[REG] ручное управление {dev}={p} (авто подождёт)", flush=True)
                        self.set(c, dev, p == "ON", force=True)
                        return
            self.decide(c)
        except (ValueError, json.JSONDecodeError) as e:
            print(f"[REG] bad payload {msg.topic}: {e}", flush=True)

    # ---------- логика ----------
    def decide(self, c):
        with self.lock:
            s, now = self.s, time.time()

            # --- 1. ГАЗ: приоритет, независим от всего ---
            co = s["co"]
            gas = co is not None
            if gas and co >= CO_ALARM:
                self.fan_reasons.add("gas")
                if not self.co_alarm_active:
                    self.co_alarm_active = True
                    c.publish("garage/alarm", json.dumps(
                        {"type": "CO", "value": co, "action": "fan+siren"}))
                    print(f"[REG] !!! ТРЕВОГА CO {co} ppm -> вентиляция + сирена", flush=True)
            elif gas and co <= CO_CLEAR and self.co_alarm_active:
                self.co_alarm_active = False
                self.fan_reasons.discard("gas")
                c.publish("garage/alarm", json.dumps(
                    {"type": "CO", "value": co, "action": "clear"}))
                print(f"[REG] CO в норме ({co} ppm), сирена выкл", flush=True)
            self.set(c, "siren", self.co_alarm_active)

            # --- 2. КЛИМАТ: обогрев ---
            if s["temp"] is not None and "heater" not in self._manual(now):
                if s["temp"] <= HEAT_ON:
                    self.set(c, "heater", True)
                elif s["temp"] >= HEAT_OFF:
                    self.set(c, "heater", False)

            # --- 3. КЛИМАТ: вентиляция по перегреву/влажности ---
            if s["temp"] is not None:
                if s["temp"] >= VENT_HOT_ON:
                    self.fan_reasons.add("hot")
                elif s["temp"] <= VENT_HOT_OFF:
                    self.fan_reasons.discard("hot")
            if s["humidity"] is not None:
                if s["humidity"] >= VENT_HUM_ON:
                    self.fan_reasons.add("humidity")
                elif s["humidity"] <= VENT_HUM_OFF:
                    self.fan_reasons.discard("humidity")
            if "fan" not in self._manual(now):
                self.set(c, "fan", bool(self.fan_reasons))

            # --- 4. СВЕТ: темно + человек ---
            if "light" not in self._manual(now):
                person_now = s["person"] and (now - s["person_ts"] < PERSON_TIMEOUT)
                if s["lux"] is not None and s["lux"] < LIGHT_ON_LUX and person_now:
                    self.set(c, "light", True)
                elif not person_now:
                    self.set(c, "light", False)

    def _manual(self, now):
        return {d for d, ts in self.manual_until.items() if ts > now}

    def set(self, c, dev, on: bool, force=False):
        """Публикует команду только при изменении состояния (или force)."""
        if force or self.state.get(dev) != on:
            self.state[dev] = on
            c.publish(f"garage/actuator/{dev}", "ON" if on else "OFF", retain=True)
            print(f"[REG] {dev} -> {'ON' if on else 'OFF'}", flush=True)

    def heartbeat_loop(self):
        while True:
            with self.lock:
                status = {
                    "sensors": self.s,
                    "actuators": self.state,
                    "fan_reasons": sorted(self.fan_reasons),
                    "manual": sorted(self._manual(time.time())),
                }
            self.client.publish("garage/regulator/state",
                                json.dumps(status, ensure_ascii=False), retain=True)
            time.sleep(HEARTBEAT)


if __name__ == "__main__":
    print(f"[REG] регулятор стартует, брокер {BROKER}:{PORT}", flush=True)
    Regulator().start()
    while True:
        time.sleep(3600)
