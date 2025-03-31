import os
import json
import requests
import time
from datetime import datetime, timezone
import google.generativeai as genai

def main(context):
    try:
        context.log("Funzione avviata")

        # Carica il prompt da prompt.json
        with open(os.path.join(os.path.dirname(__file__), "prompt.json"), "r") as f:
            prompt_data = json.load(f)

        instagram_token = os.environ["INSTAGRAM_TOKEN"]
        gemini_api_key = os.environ["GEMINI_API_KEY"]

        # Configura Gemini
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel("gemini-2.0-flash-thinking-exp-01-21")

        # Recupera i messaggi recenti
        convo_url = "https://graph.instagram.com/v18.0/me/conversations"
        convo_params = {"fields": "messages{message,from,id,created_time}", "access_token": instagram_token}
        convo_res = requests.get(convo_url, params=convo_params)
        convo_data = convo_res.json()

        if "data" not in convo_data or not convo_data["data"]:
            return context.res.send("Nessun messaggio.")

        last_convo = convo_data["data"][0]
        messages = last_convo.get("messages", {}).get("data", [])
        if not messages:
            return context.res.send("Nessun messaggio utile.")

        # Evita loop rispondendo a sé stesso
        page_info_url = "https://graph.instagram.com/me"
        page_info_params = {"fields": "id", "access_token": instagram_token}
        page_id = requests.get(page_info_url, params=page_info_params).json().get("id")
        if not page_id:
            return context.res.send("Errore nel recupero ID pagina.")

        sorted_messages = sorted(messages, key=lambda m: m["created_time"])
        last_msg = sorted_messages[-1]
        user_id = last_msg["from"]["id"]
        user_text = last_msg["message"]

        if user_id == page_id:
            return context.res.send("Messaggio interno ignorato.")

        # Ignora messaggi troppo recenti
        msg_time = datetime.fromisoformat(last_msg["created_time"].replace("Z", "+00:00"))
        if (datetime.now(timezone.utc) - msg_time).total_seconds() < 5:
            return context.res.send("Messaggio troppo recente, ignorato.")

        # Costruisce il prompt da system_instruction + ultimi messaggi
        prompt_parts = [{"text": prompt_data["system_instruction"]}]
        prompt_parts += [{"text": m["message"]} for m in sorted_messages[-10:]]

        # Chiamata a Gemini
        try:
            response = model.generate_content(
                prompt_parts,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 5024,
                    "top_k": 1
                }
            )

            if not response.candidates or not response.text:
                raise ValueError("Gemini non ha generato risposte.")

            reply_text = response.text.strip()

        except Exception as e:
            context.error(f"Errore nella generazione della risposta: {str(e)}")
            reply_text = "😘!"

        # Limita a 30 parole
        words = reply_text.split()
        if len(words) > 15:
            reply_text = " ".join(words[:30]) + "..."

        # Invia la risposta
        send_url = "https://graph.instagram.com/v18.0/me/messages"
        send_payload = {"recipient": {"id": user_id}, "message": {"text": reply_text}}
        send_headers = {"Content-Type": "application/json"}
        send_params = {"access_token": instagram_token}
        send_res = requests.post(send_url, headers=send_headers, json=send_payload, params=send_params)

        context.log(f"Risposta inviata: {send_res.status_code} - {send_res.text}")
        return context.res.send("OK")

    except Exception as e:
        context.error(f"Errore: {str(e)}")
        return context.res.json({"error": str(e)}, 500)
