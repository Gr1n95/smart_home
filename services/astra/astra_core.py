"""
Astra Core — главный мозг голосового ассистента на Pi4
Офлайн, без интернета. Получает текст с Pi5 (Whisper) и выполняет действия.
"""
import json
import time
import re
import paho.mqtt.client as mqtt
from pathlib import Path

# Конфиг
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
ASTRA_NAME = "Астра"

# Интенты для диплома — простые, но покрывают 90% кейсов гаража
INTENTS = {
    "light_on": [r"включи свет", r"свет включи", r"да будет свет"],
    "light_off": [r"выключи свет", r"свет выключи"],
    "fan_on": [r"включи вытяжку", r"включи вентилятор", r"включи вентиляцию"],
    "fan_off": [r"выключи вытяжку"],
    "heater_on": [r"включи обогрев", r"включи отопление"],
    "heater_off": [r"выключи обогрев"],
    "gate_open": [r"открой ворота", r"открыть ворота"],
    "gate_close": [r"закрой ворота"],
    "status_climate": [r"какая температура", r"температура в гараже", r"влажность", r"что с климатом"],
    "status_gas": [r"что с газом", r"какой газ", r"загазованность", r"co"],
    "status_security": [r"кто был в гараже", r"кто в гараже", r"есть кто в гараже"],
    "status_all": [r"что в гараже", r"как дела в гараже", r"статус гаража"],
}

class AstraCore:
    def __init__(self):
        self.client = mqtt.Client(client_id="astra_core")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.telemetry = {"temp": 22.5, "humidity": 60, "co": 5, "lux": 100, "radar_count": 0}
        self.last_access = {"name": "никого", "time": 0}
        
        # Для TTS — Piper
        self.tts_enabled = True
        
    def on_connect(self, client, userdata, flags, rc):
        print(f"[Astra] Connected to MQTT {rc}, listening...")
        client.subscribe("astra/stt/text")
        client.subscribe("garage/climate/#")
        client.subscribe("garage/gas/#")
        client.subscribe("garage/security/radar/#")
        client.subscribe("garage/access/log")
        client.subscribe("garage/alarm")

    def on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode()
        
        # Обновляем телеметрию
        if "climate/temp" in topic:
            try: self.telemetry["temp"] = float(payload)
            except: pass
        elif "climate/humidity" in topic:
            try: self.telemetry["humidity"] = float(payload)
            except: pass
        elif "gas/co" in topic:
            try: self.telemetry["co"] = float(payload)
            except: pass
        elif "radar/count" in topic:
            try: self.telemetry["radar_count"] = int(float(payload))
            except: pass
        elif "access/log" in topic:
            try:
                data = json.loads(payload)
                self.last_access = data
            except: pass
        
        # Тревога по газу — проактивно говорит Astra
        if topic == "garage/alarm":
            self.handle_alarm(payload)
        
        # Главная логика — пришел текст от Pi5 Whisper
        if topic == "astra/stt/text":
            self.handle_voice(payload)

    def handle_voice(self, payload):
        try:
            data = json.loads(payload) if payload.startswith("{") else {"text": payload}
            text = data.get("text", payload).lower()
            print(f"[Astra] Heard: {text}")
            
            # Ищем интент
            intent = self.parse_intent(text)
            if intent:
                self.execute_intent(intent, text)
            else:
                # Fallback в LLM
                self.handle_llm(text)
        except Exception as e:
            print(f"[Astra] Error handle_voice {e}")

    def parse_intent(self, text):
        for intent, patterns in INTENTS.items():
            for pat in patterns:
                if re.search(pat, text):
                    return intent
        return None

    def execute_intent(self, intent, original_text):
        print(f"[Astra] Intent: {intent}")
        response = ""
        
        if intent == "light_on":
            self.client.publish("garage/actuator/light", "ON")
            response = "Включаю свет в гараже"
        elif intent == "light_off":
            self.client.publish("garage/actuator/light", "OFF")
            response = "Выключаю свет"
        elif intent == "fan_on":
            self.client.publish("garage/actuator/fan", "ON")
            response = "Включаю вытяжку"
        elif intent == "fan_off":
            self.client.publish("garage/actuator/fan", "OFF")
            response = "Выключаю вытяжку"
        elif intent == "gate_open":
            self.client.publish("garage/actuator/gate", "OPEN")
            response = "Открываю ворота"
        elif intent == "gate_close":
            self.client.publish("garage/actuator/gate", "CLOSE")
            response = "Закрываю ворота"
        elif intent == "status_climate":
            response = f"В гараже {self.telemetry['temp']} градусов, влажность {self.telemetry['humidity']} процентов"
        elif intent == "status_gas":
            co = self.telemetry['co']
            if co < 10:
                response = f"С газом все в порядке, CO {co} ppm"
            elif co < 50:
                response = f"Повышенный CO, {co} ppm, рекомендую включить вытяжку"
            else:
                response = f"Внимание! Загазованность {co} ppm, включаю вытяжку!"
                self.client.publish("garage/actuator/fan", "ON")
        elif intent == "status_security":
            count = self.telemetry['radar_count']
            if count == 0:
                response = "В гараже сейчас никого нет"
            else:
                response = f"В гараже {count} человек"
        elif intent == "status_all":
            response = f"Температура {self.telemetry['temp']} градусов, влажность {self.telemetry['humidity']}, CO {self.telemetry['co']} ppm, в гараже {self.telemetry['radar_count']} человек"
        
        if response:
            self.say(response)
            self.client.publish("astra/intent/result", json.dumps({"intent": intent, "response": response}))

    def handle_llm(self, text):
        """Fallback в Ollama phi3:mini — для вопросов типа 'что такое угарный газ'"""
        print(f"[Astra] LLM fallback for: {text}")
        # Заглушка — в реале запрос к Ollama
        # import requests
        # r = requests.post("http://localhost:11434/api/generate", json={
        #   "model": "phi3:mini",
        #   "prompt": f"Ты Astra, ассистент умного гаража, отвечай кратко по-русски. Вопрос: {text}",
        #   "stream": False
        # })
        # response = r.json()["response"]
        
        # Для диплома — простые ответы без LLM
        if "угарный газ" in text or "co" in text:
            response = "Угарный газ CO — опасен, без запаха. При 50 ppm включаю вытяжку и сирену"
        elif "влажность" in text:
            response = "Высокая влажность вызывает коррозию. При 75 процентах включаю вентиляцию"
        else:
            response = "Не поняла команду, скажи например включи свет или какая температура"
        
        self.say(response)

    def handle_alarm(self, payload):
        try:
            data = json.loads(payload)
            if data.get("type") == "CO":
                self.say(f"Внимание! Загазованность {data.get('value')} ppm! Включаю вытяжку и сирену!")
        except:
            pass

    def say(self, text):
        """Отправить в TTS Piper на Pi4"""
        print(f"[Astra says] {text}")
        self.client.publish("astra/tts/say", json.dumps({"text": text}))
        # Локально вызвать Piper:
        # echo "text" | piper --model ru_RU-irina-medium.onnx --output_file /tmp/astra.wav && aplay /tmp/astra.wav

    def run(self):
        self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
        self.client.loop_forever()

if __name__ == "__main__":
    astra = AstraCore()
    print(f"Starting {ASTRA_NAME} Core on Pi4...")
    astra.run()
