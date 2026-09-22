"""
MVP backend для умного гаража
FastAPI + MQTT + Face + Fingerprint + Radar
"""
from fastapi import FastAPI
import paho.mqtt.client as mqtt
import json
import time

app = FastAPI(title="Smart Garage API")

# MQTT setup
MQTT_BROKER = "localhost"
MQTT_PORT = 1883

client = mqtt.Client()

telemetry = {
    "temp": 0,
    "humidity": 0,
    "co_ppm": 0,
    "lux": 0,
    "radar_count": 0,
}

def on_connect(c, userdata, flags, rc):
    print(f"MQTT connected {rc}")
    c.subscribe("garage/#")

def on_message(c, userdata, msg):
    try:
        payload = msg.payload.decode()
        # print(f"{msg.topic}: {payload}")
        if "climate/temp" in msg.topic:
            telemetry["temp"] = float(payload)
        elif "climate/humidity" in msg.topic:
            telemetry["humidity"] = float(payload)
        elif "gas/co" in msg.topic:
            telemetry["co_ppm"] = float(payload)
        elif "light/lux" in msg.topic:
            telemetry["lux"] = float(payload)
        elif "radar/count" in msg.topic:
            telemetry["radar_count"] = int(float(payload))
        
        # Логика тревоги по газу
        if telemetry["co_ppm"] > 50:
            print(f"!!! ALARM CO {telemetry['co_ppm']} ppm !!!")
            c.publish("garage/actuator/fan", "ON")
            c.publish("garage/alarm", json.dumps({"type":"CO","value":telemetry["co_ppm"]}))
    except Exception as e:
        print(f"MQTT error {e}")

client.on_connect = on_connect
client.on_message = on_message

@app.on_event("startup")
def startup():
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
    except Exception as e:
        print(f"MQTT not available yet: {e}")

@app.get("/")
def root():
    return {"status":"garage brain online", "telemetry": telemetry}

@app.get("/telemetry")
def get_telemetry():
    return telemetry

@app.post("/access/grant")
def grant_access(method: str, user: str):
    """Выдать доступ, открыть замок"""
    client.publish("garage/actuator/lock", "OPEN")
    client.publish("garage/access/log", json.dumps({"user":user,"method":method,"ts":time.time()}))
    return {"result":"open","user":user}

@app.post("/actuator/{device}/{action}")
def actuator(device: str, action: str):
    client.publish(f"garage/actuator/{device}", action.upper())
    return {"device":device,"action":action}

# Для FaceID будет отдельный сервис
# from .access.face_recognizer import FaceService
# face_service = FaceService()
# @app.post("/access/face/check")
# def face_check():
#     ...
