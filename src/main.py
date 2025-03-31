import os
import json
import requests
import time
from datetime import datetime, timezone
import google.generativeai as genai
from prompt import generate  # Usa la funzione generate dal tuo prompt.py

def main(context):
    try:
        context.log("Funzione avviata")

        instagram_token = os.environ["INSTAGRAM_TOKEN"]
        gemini_api_key = os.environ["GEMINI_API_KEY"]

        # Configura l'API Gemini
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel("gemini-2.0-flash-thinking-exp-01-21")

        # Recupera le conversazioni recenti da Instagram
        convo_url = "https://graph.instagram.com/v18.0/me/conversations"
        convo_params = {"fields": "messages{message,from,id,created_time}", "access_token": instagram_token}
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
        page_info_params = {"fields": "id", "access_token": instagram_token}
        page_info_res = requests.get(page_info_url, params=page_info_params)
        page_info = page_info_res.json()
        page_id = page_info.get("id")

        if not page_id:
            context.error("Impossibile ottenere l'ID della pagina.")
            return context.res.send("Errore nel recupero dell'ID pagina.")

        # Ordina i messaggi per data
        sorted_messages = sorted(messages, key=lambda m: m["created_time"])
        last_msg = sorted_messages[-1]
        user_id = last_msg["from"]["id"]
        user_text = last_msg["message"]

        # Ignora i messaggi della pagina stessa
        if user_id == page_id:
            context.log("Messaggio proveniente dalla pagina stessa. Nessuna risposta.")
            return context.res.send("Messaggio interno ignorato.")

        # Controllo temporale: ignora messaggi troppo recenti
        msg_time = datetime.fromisoformat(last_msg["created_time"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if (now - msg_time).total_seconds() < 5:
            context.log("Messaggio troppo recente, potenziale duplicato. Ignorato.")
            return context.res.send("Messaggio ignorato per evitare duplicati.")

        # Costruisce il contesto conversazionale (ultimi 15 messaggi)
        chat_history = [{"text": msg["message"]} for msg in sorted_messages[-15:]]

        # Usa la funzione 'generate' di prompt.py per generare il contenuto personalizzato
        try:
            # Chiamata al modello Gemini con il contesto e il comportamento di Simone
            response = generate()  # Qui usiamo la funzione definita in prompt.py
            raw_reply = response.text.strip() if response and hasattr(response, 'text') else ""
        except Exception as e:
            context.error(f"Errore nella generazione della risposta: {str(e)}")
            raw_reply = "😘!"

        reply_text = " ".join(raw_reply.splitlines()).strip()
        words = reply_text.split()
        if len(words) > 30:
            reply_text = " ".join(words[:30]) + "..."

        context.log(f"Risposta generata: {reply_text}")

        # Invia la risposta all'utente su Instagram
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
