import os
import json
import requests
from openai import OpenAI
from datetime import datetime, timedelta

def main(context):
    try:
        context.log("Funzione avviata")

        # Legge il prompt dal file
        with open(os.path.join(os.path.dirname(__file__), "prompt.txt"), "r") as f:
            prompt_prefix = f.read()

        instagram_token = os.environ["INSTAGRAM_TOKEN"]
        openai_api_key = os.environ["OPENAI_API_KEY"]

        # Recupera le conversazioni recenti da Instagram
        convo_url = "https://graph.instagram.com/v18.0/me/conversations"
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

        # Recupera l'ID della pagina per evitare loop
        page_info_url = "https://graph.instagram.com/me"
        page_info_params = {
            "fields": "id",
            "access_token": instagram_token
        }
        page_info_res = requests.get(page_info_url, params=page_info_params)
        page_info = page_info_res.json()
        page_id = page_info.get("id")

        if not page_id:
            context.error("Impossibile ottenere l'ID della pagina.")
            return context.res.send("Errore nel recupero dell'ID pagina.")

        # Ordina i messaggi per data (dal più vecchio al più recente)
        sorted_messages = sorted(messages, key=lambda m: m["created_time"])
        last_msg = sorted_messages[-1]

        # Se l'ultimo messaggio è del bot, ignoriamo
        if last_msg["from"]["id"] == page_id:
            context.log("Ultimo messaggio è stato inviato dal bot. Ignoro per evitare loop.")
            return context.res.send("Ultimo messaggio è del bot, non rispondo.")

        # Controlla se il bot ha risposto recentemente (entro 60 secondi)
        last_bot_msg = next((m for m in reversed(sorted_messages) if m["from"]["id"] == page_id), None)
        if last_bot_msg:
            bot_time = datetime.strptime(last_bot_msg["created_time"], "%Y-%m-%dT%H:%M:%S%z")
            now = datetime.now(bot_time.tzinfo)
            if now - bot_time < timedelta(seconds=60):
                context.log("Il bot ha già risposto di recente. Ignoro per evitare spam.")
                return context.res.send("Risposta recente già inviata.")

        message_id = last_msg["id"]
        user_id = last_msg["from"]["id"]
        user_text = last_msg["message"]

        # Costruisce il contesto conversazionale
        chat_history = []
        for msg in sorted_messages:
            role = "user" if msg["from"]["id"] != page_id else "assistant"
            chat_history.append({
                "role": role,
                "content": msg["message"]
            })

        # Mantiene solo gli ultimi 15 messaggi
        chat_history = chat_history[-15:]

        # Chiamata a OpenAI
        client = OpenAI(api_key=openai_api_key)
        ai_response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": prompt_prefix}] + chat_history,
            max_tokens=300
        )

        reply_text = ai_response.choices[0].message.content.strip()
        context.log(f"Risposta generata: {reply_text}")

        # Invia la risposta all'utente su Instagram
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


