#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Симулятор узлов гаража для демонстрационного стенда (диплом).
Имитирует ESP32-узлы и радар, публикуя телеметрию в те же MQTT-топики,
что и реальные датчики. Grafana/Astra/HA не знают разницы.

Топики (совпадают с реальной архитектурой):
  garage/climate/temp, garage/climate/humidity, garage/climate/pressure
  garage/gas/co                - ppm CO
  garage/light/lux             - освещённость
  garage/security/radar        - JSON целей LD2450
  garage/gate/state            - OPEN/CLOSED

Запуск на Pi4 или Pi5 (нужен интернет-пакет paho-mqtt, см. requirements.txt):
  pip install paho-mqtt
  python3 garage_simulator.py --broker 10.0.0.1 scenario normal
  python3 garage_simulator.py --broker 10.0.0.1 interactive

Сценарии:
  normal    - ровный фон: -2°C, влажность 60%, CO 5ppm, темно
  gas_leak  - утечка CO: рост 5 -> 120 ppm за 60 сек (тревога на Pi4)
  person    - приход владельца: радар видит цель, движение к воротам
  night     - ночь: -8°C, темно, тишина
  cold      - похолодание: температура падает ниже 3°C (антифриз-алерт)
"""

import argparse
import json
import math
import random
import sys
import time
import threading

try:
    import paho.mqtt.client as mqtt
except ImportError:
    sys.exit("Нужен paho-mqtt: pip install paho-mqtt")


class GarageSim:
    def __init__(self, host, port, user, password):
        self.host, self.port = host, port
        # Состояние "виртуального гаража" - его меняют сценарии
        self.state = {
            "temp": -2.0, "humidity": 58.0, "pressure": 1013.0,
            "co_ppm": 5.0, "lux": 15.0,
            "person_present": False, "gate": "CLOSED",
            "co_trend": 0.0,   # скорость роста CO, ppm/тик
            "temp_trend": 0.0, # скорость изменения T, °C/мин
        }
        self.tick = 0
        self.lock = threading.Lock()
        self.client = mqtt.Client(
            client_id=f"sim-garage-{int(time.time())}",
            callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
        )
        if user:
            self.client.username_pw_set(user, password)
        # LWT: если симулятор умер, Pi4 узнает
        self.client.will_set("garage/sim/status", "offline", retain=True)

    def start(self):
        self.client.connect(self.host, self.port, keepalive=30)
        self.client.loop_start()
        self.client.publish("garage/sim/status", "online", retain=True)
        t = threading.Thread(target=self.loop, daemon=True)
        t.start()
        print(f"[SIM] подключен к {self.host}:{self.port}, публикую топики garage/#")

    # ---------------- физическая модель ----------------

    def step(self):
        """Один шаг времени (2 сек). Простая, но правдоподобная физика."""
        with self.lock:
            s = self.state
            self.tick += 1

            # CO: тренд + шум + дрейф к фону при утечке без "горения"
            s["co_ppm"] += s["co_trend"] + random.uniform(-0.3, 0.3)
            if s["co_trend"] == 0:
                s["co_ppm"] = max(4.0, s["co_ppm"] - 0.5)  # проветривание
            s["co_ppm"] = max(0.0, min(500.0, s["co_ppm"]))

            # Температура
            s["temp"] += s["temp_trend"] / 30.0 + random.uniform(-0.05, 0.05)

            # Влажность связана с температурой (грубая модель конденсата)
            s["humidity"] += (8.0 - s["temp"]) * 0.002 + random.uniform(-0.2, 0.2)
            s["humidity"] = max(30.0, min(95.0, s["humidity"]))

            # Давление - медленная синусоида
            s["pressure"] = 1013.0 + 6.0 * math.sin(self.tick / 900.0)

    def publish(self):
        with self.lock:
            s = dict(self.state)
        c = self.client
        c.publish("garage/climate/temp", f"{s['temp']:.1f}")
        c.publish("garage/climate/humidity", f"{s['humidity']:.1f}")
        c.publish("garage/climate/pressure", f"{s['pressure']:.1f}")
        c.publish("garage/gas/co", f"{s['co_ppm']:.1f}")
        c.publish("garage/light/lux", f"{s['lux']:.0f}")
        c.publish("garage/gate/state", s["gate"])
        # Радар: до 3 целей как LD2450 (X,Y мм, скорость см/с)
        if s["person_present"]:
            targets = [{
                "id": 1,
                "x": random.randint(800, 2200),
                "y": random.randint(1500, 3500),
                "speed": random.randint(5, 40),
            }]
        else:
            targets = []
        c.publish("garage/security/radar", json.dumps({"targets": targets, "ts": time.time()}))
        if self.tick % 15 == 0:  # раз в 30 сек
            print(f"[SIM] T={s['temp']:.1f}C  RH={s['humidity']:.0f}%  CO={s['co_ppm']:.0f}ppm  "
                  f"lux={s['lux']:.0f}  чел={'да' if s['person_present'] else 'нет'}  ворота={s['gate']}")

    def loop(self):
        while True:
            self.step()
            self.publish()
            time.sleep(2)

    # ---------------- управление сценариями ----------------

    def set(self, key, value):
        with self.lock:
            self.state[key] = value

    def run_scenario(self, name):
        with self.lock:
            s = self.state
        if name == "normal":
            self.set("co_trend", 0.0); self.set("temp_trend", 0.0)
            self.set("temp", -2.0); self.set("lux", 15.0); self.set("person_present", False)
            print("[SIM] сценарий: норма")
        elif name == "gas_leak":
            self.set("co_trend", 2.0)  # ~+2ppm/2сек => 50ppm через ~45 сек
            print("[SIM] сценарий: УТЕЧКА ГАЗА (CO ползёт, тревога через ~45 сек)")
        elif name == "person":
            self.set("person_present", True)
            self.set("gate", "OPEN"); self.set("lux", 300.0)
            print("[SIM] сценарий: пришёл человек (радар + открытые ворота + свет)")
        elif name == "night":
            self.set("temp_trend", -1.5); self.set("lux", 0.0); self.set("person_present", False)
            print("[SIM] сценарий: ночь, похолодание (антифриз-алерт скоро)")
        elif name == "cold":
            self.set("temp", 5.0); self.set("temp_trend", -3.0)
            print("[SIM] сценарий: холодный фронт (T падает ниже 3°C)")
        else:
            print(f"[SIM] неизвестный сценарий: {name}")


INTERACTIVE_HELP = """
Команды (interactive-режим):
  gas up|down|stop     - рост/спад/стоп утечки CO
  temp <+/-град>       - изменение целевой температуры, напр. temp -5
  lux <число>          - установить освещённость
  person in|out        - человек пришёл/ушёл (радар)
  gate open|close      - ворота
  scenario <имя>       - normal|gas_leak|person|night|cold
  status               - показать состояние
  quit                 - выход
"""


def interactive(sim):
    print(INTERACTIVE_HELP)
    while True:
        try:
            parts = input("sim> ").strip().split()
        except (EOFError, KeyboardInterrupt):
            break
        if not parts:
            continue
        cmd = parts[0].lower()
        if cmd == "quit":
            break
        elif cmd == "scenario" and len(parts) > 1:
            sim.run_scenario(parts[1])
        elif cmd == "gas" and len(parts) > 1:
            sim.set("co_trend", {"up": 2.0, "down": -2.0, "stop": 0.0}.get(parts[1], 0.0))
        elif cmd == "temp" and len(parts) > 1:
            try:
                with sim.lock:
                    sim.state["temp"] += float(parts[1])
            except ValueError:
                print("пример: temp -5")
        elif cmd == "lux" and len(parts) > 1:
            try:
                sim.set("lux", float(parts[1]))
            except ValueError:
                print("пример: lux 250")
        elif cmd == "person" and len(parts) > 1:
            sim.set("person_present", parts[1] == "in")
        elif cmd == "gate" and len(parts) > 1:
            sim.set("gate", parts[1].upper())
        elif cmd == "status":
            with sim.lock:
                print("  " + json.dumps(sim.state, ensure_ascii=False))
        else:
            print(INTERACTIVE_HELP)


def main():
    ap = argparse.ArgumentParser(description="Симулятор узлов гаража для стенда")
    ap.add_argument("--broker", default="10.0.0.1", help="IP Pi4 (MQTT), по умолч. 10.0.0.1")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--user", default="garage")
    ap.add_argument("--password", default="garage2026")
    ap.add_argument("mode", nargs="?", default="interactive",
                    help="scenario | interactive")
    ap.add_argument("scenario", nargs="?", default="normal",
                    help="имя сценария для mode=scenario: normal|gas_leak|person|night|cold")
    args = ap.parse_args()

    sim = GarageSim(args.broker, args.port, args.user, args.password)
    sim.start()
    time.sleep(1)

    if args.mode == "scenario":
        sim.run_scenario(args.scenario)
        print("[SIM] работает бесконечно, Ctrl+C для выхода")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    else:
        interactive(sim)

    sim.client.publish("garage/sim/status", "offline", retain=True)
    print("[SIM] остановлен")


if __name__ == "__main__":
    main()
