import os
import json
import requests
from openai import OpenAI

def main(context):
    try:
        context.log("Funzione avviata")

        # Legge il prompt dal file
        with open(os.path.join(os.path.dirname(__file__), "prompt.txt"), "r") as f:
            prompt_prefix = f.read()

        instagram_token = os.environ["INSTAGRAM_TOKEN"]
        openai_api_key = os.environ["OPENAI_API_KEY"]

        # Recupera le conversazioni recenti da Instagram
        convo_url = f"https://graph.instagram.com/v18.0/me/conversations"
        convo_params = {
            "fields": "messages{message,from,id,created_time}",
            "access_token": instagram_token
        }
        convo_res = requests.get(convo_url, params=convo_params)
        convo_data = convo_res.json()

        if "data" not in convo_data or not convo_data["data"]:
            context.log("Nessuna conversazione trovata.")
            return context.res.send("Nessun messaggio.")

        last_convo = convo_data["data"][0]
        messages = last_convo.get("messages", {}).get("data", [])

        if not messages:
            context.log("Nessun messaggio nella conversazione.")
            return context.res.send("Nessun messaggio utile.")

        # Trova l'ultimo messaggio dell'utente
        last_msg = messages[0]
        user_id = last_msg["from"]["id"]
        user_text = last_msg["message"]

        context.log(f"Messaggio ricevuto da {user_id}: {user_text}")

        # Costruisce il prompt completo
        prompt = f"{prompt_prefix}\n\nUtente: {user_text}\nAssistente:"

        # Chiamata a OpenAI con nuova sintassi
        client = OpenAI(api_key=openai_api_key)
        ai_response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": prompt_prefix},
                {"role": "user", "content": user_text}
            ]
        )

        reply_text = ai_response.choices[0].message.content.strip()
        context.log(f"Risposta generata: {reply_text}")

        # Invia la risposta all'utente su Instagram
        send_url = f"https://graph.instagram.com/v18.0/me/messages"
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
