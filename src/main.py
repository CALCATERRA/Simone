import os
import json
import requests
import google.generativeai as genai
from datetime import datetime, timezone

def main(context):
    try:
        context.log("Funzione avviata")

        # Legge il prompt dal file JSON
        with open(os.path.join(os.path.dirname(__file__), "prompt.json"), "r") as f:
            prompt_data = json.load(f)
        system_instruction = prompt_data.get("system_instruction", "")

        instagram_token = os.environ["INSTAGRAM_TOKEN"]
        gemini_api_key = os.environ["GEMINI_API_KEY"]

        # Configura Gemini
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel("gemini-2.0-flash-thinking-exp-01-21")

        # Ottieni i messaggi da Instagram
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

        # Prendi ID della pagina per evitare risposte a se stessa
        page_info = requests.get(
            "https://graph.instagram.com/me",
            params={"fields": "id", "access_token": instagram_token}
        ).json()
        page_id = page_info.get("id")

        if not page_id:
            return context.res.send("Errore nel recupero dell'ID pagina.")

        # Ordina messaggi per data
        sorted_messages = sorted(messages, key=lambda m: m["created_time"])
        last_msg = sorted_messages[-1]
        user_id = last_msg["from"]["id"]
        user_text = last_msg["message"]

        if user_id == page_id:
            return context.res.send("Messaggio interno ignorato.")

        msg_time = datetime.fromisoformat(last_msg["created_time"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if (now - msg_time).total_seconds() < 5:
            return context.res.send("Messaggio ignorato per evitare duplicati.")

        # Prepara la conversazione per Gemini
        chat_history = [{"text": system_instruction}] + [{"text": msg["message"]} for msg in sorted_messages[-15:]]

        # Genera la risposta
        try:
            response = model.generate_content(
                chat_history,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 100,
                    "top_k": 1
                }
            )
            raw_reply = response.text.strip() if response and hasattr(response, 'text') else ""
        except Exception as e:
            context.error(f"Errore nella generazione della risposta: {str(e)}")
            raw_reply = "😘!"

        # Pulisce la risposta
        reply_text = " ".join(raw_reply.splitlines()).strip()
        words = reply_text.split()
        if len(words) > 30:
            reply_text = " ".join(words[:30]) + "..."

        # Invia la risposta a Instagram
        send_url = "https://graph.instagram.com/v18.0/me/messages"
        send_payload = {
            "recipient": {"id": user_id},
            "message": {"text": reply_text}
        }
        send_headers = {"Content-Type": "application/json"}
        send_params = {"access_token": instagram_token}

        send_res = requests.post(send_url, headers=send_headers, json=send_payload, params=send_params)
        context.log(f"Risposta inviata: {send_res.status_code} - {send_res.text}")

        return context.res.send("OK")

    except Exception as e:
        context.error(f"Errore: {str(e)}")
        return context.res.json({"error": str(e)}, 500)
