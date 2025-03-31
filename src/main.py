import os
import json
import requests
import google.generativeai as genai
from datetime import datetime
from google.generativeai.types import Content, Part, GenerateContentConfig

def main(context):
    try:
        context.log("Funzione avviata")
        
        # Carica il prompt base
        with open(os.path.join(os.path.dirname(__file__), "prompt.txt"), "r") as f:
            prompt_text = f.read()
        
        instagram_token = os.getenv("INSTAGRAM_TOKEN")
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        
        # Configura Gemini
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

        # Ignora i messaggi inviati dalla stessa pagina
        if user_id == page_id:
            context.log("Messaggio proveniente dalla pagina stessa. Nessuna risposta.")
            return context.res.send("Messaggio interno ignorato.")

        # Costruzione del contesto conversazionale basato sulla struttura di Gemini
        chat_history = [
            Content(role="user", parts=[Part.from_text(msg["message"])] ) for msg in sorted_messages[-10:]
        ]
        
        gemini_contents = [
            Content(role="system", parts=[Part.from_text(prompt_text)]),
            *chat_history,
            Content(role="user", parts=[Part.from_text(user_text)])
        ]

        # Configurazione della generazione di contenuti
        gen_config = GenerateContentConfig(
            response_mime_type="text/plain",
            system_instruction=[Part.from_text(prompt_text)]
        )

        # Generazione della risposta
        try:
            response = model.generate_content(
                contents=gemini_contents, 
                config=gen_config
            )
            
            context.log(f"Risposta grezza di Gemini: {response}")
            
            if response and hasattr(response, 'candidates') and response.candidates:
                raw_reply = response.candidates[0].content.parts[0].text.strip()
            else:
                context.error(f"Nessun testo generato. Risultato: {response}")
                raw_reply = "😘!"

        except Exception as e:
            context.error(f"Errore nella generazione della risposta: {str(e)}")
            raw_reply = "😘!"

        # Funzione per troncare la risposta con logica pulita
        def cut_sentence(text, max_words=30):
            words = text.split()
            if len(words) <= max_words:
                return text
            short_text = " ".join(words[:max_words])
            for stop_char in [".", "!", "?"]:
                if stop_char in short_text:
                    return short_text[:short_text.rfind(stop_char) + 1]
            return short_text + "..."

        reply_text = cut_sentence(raw_reply)
        context.log(f"Risposta generata (corta): {reply_text}")

        # Invio della risposta all'utente
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
