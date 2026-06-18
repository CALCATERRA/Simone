import os
import json
import requests
import time
from datetime import datetime, timezone
import google.generativeai as genai


# =========================================================
# 🌤️ CONTEXT ENGINE: METEO (INVARIATO)
# =========================================================
def get_weather(city):
    try:
        api_key = os.environ.get("OPENWEATHER_API_KEY")
        if not api_key:
            return None

        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": city,
            "appid": api_key,
            "units": "metric",
            "lang": "it"
        }

        res = requests.get(url, params=params)
        data = res.json()

        if res.status_code != 200:
            return None

        temp = data["main"]["temp"]
        desc = data["weather"][0]["description"]

        return f"{temp}°C, {desc}"

    except Exception:
        return None


# =========================================================
# 🔁 ROTAZIONE GEMINI KEYS (INVARIATO)
# =========================================================
def get_rotated_gemini_key():
    now = datetime.now()
    hour = now.hour

    if 6 <= hour < 10:
        index = 1
    elif 10 <= hour < 15:
        index = 2
    elif 15 <= hour < 18:
        index = 3
    elif 18 <= hour < 22:
        index = 5
    elif 22 <= hour or hour < 2:
        index = 5
    else:
        return None

    return os.environ.get(f"GEMINI_API_KEY_{index}")


def main(context):
    try:
        context.log("Funzione avviata")

        with open(os.path.join(os.path.dirname(__file__), "prompt.json"), "r") as f:
            prompt_data = json.load(f)

        instagram_token = os.environ["INSTAGRAM_TOKEN"]

        gemini_api_key = get_rotated_gemini_key()
        if not gemini_api_key:
            return context.res.send("Orario inattivo.")

        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")

        # =========================================================
        # 📩 RECUPERO CONVERSAZIONI
        # =========================================================
        convo_url = "https://graph.instagram.com/v18.0/me/conversations"
        convo_params = {
            "fields": "messages{message,from,id,created_time}",
            "access_token": instagram_token
        }

        convo_res = requests.get(convo_url, params=convo_params)
        convo_data = convo_res.json()

        if "data" not in convo_data or not convo_data["data"]:
            return context.res.send("Nessun messaggio.")

        last_convo = convo_data["data"][0]
        messages = last_convo.get("messages", {}).get("data", [])

        if not messages:
            return context.res.send("Nessun messaggio utile.")

        # =========================================================
        # 🧠 ORDINE SICURO MESSAGGI
        # =========================================================
        sorted_messages = sorted(messages, key=lambda m: m["created_time"])

        page_info_url = "https://graph.instagram.com/me"
        page_info_params = {"fields": "id", "access_token": instagram_token}
        page_id = requests.get(page_info_url, params=page_info_params).json().get("id")

        if not page_id:
            return context.res.send("Errore ID pagina.")

        last_msg = sorted_messages[-1]

        user_id = last_msg["from"]["id"]
        user_text = last_msg["message"]

        msg_time = datetime.fromisoformat(
            last_msg["created_time"].replace("Z", "+00:00")
        )

        # =========================================================
        # 🚫 SELF MESSAGE CHECK
        # =========================================================
        if user_id == page_id:
            return context.res.send("Ignorato self message.")

        # =========================================================
        # 🚫 DEDUPLICAZIONE ROBUSTA
        # =========================================================
        processed_ids = getattr(context, "processed_ids", set())

        message_id = last_msg["id"]

        if message_id in processed_ids:
            return context.res.send("Duplicato ignorato.")

        processed_ids.add(message_id)
        context.processed_ids = processed_ids

        # =========================================================
        # ⏱️ TIMING
        # =========================================================
        now = datetime.now(timezone.utc)
        diff_sec = (now - msg_time).total_seconds()

        if diff_sec < 5:
            context.log("Messaggio troppo recente.")

        # =========================================================
        # 🧠 CONTEXT ENGINE
        # =========================================================
        context_block = f"""
📅 Data: {now.strftime('%d/%m/%Y')}
🕒 Ora: {now.strftime('%H:%M')}
"""

        # =========================================================
        # 🌤️ METEO INTELLIGENTE (solo se serve)
        # =========================================================
        trigger_words = [
            "meteo", "pioggia", "sole", "tempo",
            "domani", "oggi", "uscire", "evento", "viaggio"
        ]

        include_weather = any(w in user_text.lower() for w in trigger_words)

        if include_weather:
            cities = ["Verona", "Padova", "Milano"]
            weather_lines = []

            for city in cities:
                w = get_weather(city)
                if w:
                    weather_lines.append(f"{city}: {w}")

            if weather_lines:
                context_block += "\n🌤️ Meteo:\n" + "\n".join(weather_lines)

        # =========================================================
        # 🧠 PROMPT BUILDING
        # =========================================================
        prompt_parts.append({
            "text": f"""
        🎯 MISSIONE:
        Rispondi ESCLUSIVAMENTE all’ultimo messaggio dell’utente.

        MESSAGGIO ATTUALE:
        USER: {user_text}

        REGOLE:
        - Non ignorare il messaggio sopra
        - Non continuare conversazioni precedenti se non richiesto
        - Usa la chat solo come contesto, non come compito principale
        """
        })

        # =========================================================
        # 💬 CHAT STRUCTURE MIGLIORATA (FIX IMPORTANTE)
        # =========================================================
        last_10 = sorted_messages[-10:]

        chat_block = "\nCONVERSAZIONE RECENTE:\n"

        for m in last_10:
            role = "ASSISTANT" if m["from"]["id"] == page_id else "USER"
            chat_block += f"{role}: {m['message']}\n"

        chat_block += "\nRispondi in modo coerente all'ultimo messaggio dell'utente mantenendo il contesto della conversazione.\n"

        prompt_parts.append({"text": chat_block})

        prompt_parts.append({"text": "ASSISTANT:"})

        # =========================================================
        # 🤖 GENERAZIONE RISPOSTA
        # =========================================================
        try:
            response = model.generate_content(
                prompt_parts,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 65536,
                    "top_k": 64,
                    "top_p": 0.95
                }
            )

            if not response.candidates or not response.text:
                raise ValueError("No response")

            reply_text = response.text.strip()

        except Exception as e:
            context.error(str(e))
            reply_text = "😘"

        # =========================================================
        # ✂️ LIMITAZIONE RISPOSTA
        # =========================================================
        if len(reply_text.split()) > 60:
            reply_text = " ".join(reply_text.split()[:60]) + "..."

        # =========================================================
        # 📤 INVIO INSTAGRAM
        # =========================================================
        send_url = "https://graph.instagram.com/v18.0/me/messages"
        send_payload = {
            "recipient": {"id": user_id},
            "message": {"text": reply_text}
        }

        requests.post(
            send_url,
            headers={"Content-Type": "application/json"},
            json=send_payload,
            params={"access_token": instagram_token}
        )

        context.last_response_time = time.time()
        return context.res.send("OK")

    except Exception as e:
        context.error(str(e))
        return context.res.json({"error": str(e)}, 500)
