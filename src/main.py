import os
import json
import requests
from datetime import datetime, timezone
import google.generativeai as genai

def main(context):
    try:
        context.log("Funzione avviata")

        # Legge il prompt dal file
        with open(os.path.join(os.path.dirname(__file__), "prompt.txt"), "r") as f:
            prompt_prefix = f.read()

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

        # Costruisce il contesto conversazionale (ultimi 10 messaggi per ridurre i token)
        chat_history = [{"text": msg["message"]} for msg in sorted_messages[-10:]]

        # Chiamata a Gemini per generare la risposta
        try:
            prompt_input = [{"text": prompt_prefix}] + chat_history
            context.log(f"Prompt inviato a Gemini: {prompt_input}")
            
            response = model.generate_content(
                prompt_input, 
                generation_config={
                    "temperature": 0.7, 
                    "max_output_tokens": 2500,  # Ridotto per evitare risposte troppo lunghe
                    "top_k": 1
                }
            )
            context.log(f"Risposta grezza di Gemini: {response}")

            # Estrai il testo dalla risposta
            if response and hasattr(response, 'candidates') and response.candidates:
                raw_reply = response.candidates[0].content.parts[0].text.strip()
            else:
                context.error(f"Nessun testo generato. Risultato: {response}")
                raw_reply = "😘!"

        except Exception as e:
            context.error(f"Errore nella generazione della risposta: {str(e)}")
            raw_reply = "😘!"

        # **Taglia la risposta in modo più pulito (fermandosi al primo punto o punto esclamativo)**
        def cut_sentence(text, max_words=30):
            words = text.split()
            if len(words) <= max_words:
                return text
            short_text = " ".join(words[:max_words])
            for stop_char in [".", "!", "?"]:
                if stop_char in short_text:
                    return short_text[:short_text.rfind(stop_char) + 1]  # Tronca alla frase più vicina
            return short_text + "..."  # Se non trova un punto, tronca a 30 parole

        reply_text = cut_sentence(raw_reply)
        context.log(f"Risposta generata (corta): {reply_text}")

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
