import os
import json
import requests
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
        model = "gemini-2.0-flash-thinking-exp-01-21"

        # Ottieni i messaggi più recenti
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

        # Ottieni ID della pagina per evitare risposte a se stessa
        page_info_url = "https://graph.instagram.com/me"
        page_info_params = {"fields": "id", "access_token": instagram_token}
        page_info_res = requests.get(page_info_url, params=page_info_params)
        page_info = page_info_res.json()
        page_id = page_info.get("id")

        if not page_id:
            return context.res.send("Errore nel recupero dell'ID pagina.")

        # Ordina i messaggi e prendi l'ultimo dell'utente
        sorted_messages = sorted(messages, key=lambda m: m["created_time"])
        last_msg = sorted_messages[-1]
        user_id = last_msg["from"]["id"]
        user_text = last_msg["message"]

        # Ignora i messaggi della pagina stessa
        if user_id == page_id:
            return context.res.send("Messaggio interno ignorato.")

        # Prepara il contenuto per Gemini (ora inviamo il testo direttamente)
        user_message = user_text.strip()

        # Genera risposta con Gemini
        try:
            # Chiamata all'API di Gemini per generare la risposta
            response = genai.chat(
                model=model,
                messages=[{
                    "role": "user",
                    "content": user_message
                }],
                system_instruction=prompt_data["system_instruction"],
                temperature=0.7,
                max_output_tokens=100,
                top_k=1
            )

            full_text = response.get("text", "")

            # Funzione per deduplicare frasi troppo simili
            def dedup_responses(text):
                parts = [p.strip() for p in text.split("\n") if p.strip()]
                seen = set()
                filtered = []
                for p in parts:
                    low = p.lower().strip("!?.")
                    if low not in seen:
                        seen.add(low)
                        filtered.append(p)
                return " ".join(filtered)

            # Funzione per tagliare a max 30 parole
            def cut_sentence(text, max_words=30):
                words = text.split()
                if len(words) <= max_words:
                    return text
                short = " ".join(words[:max_words])
                for stop in [".", "!", "?"]:
                    if stop in short:
                        return short[:short.rfind(stop) + 1]
                return short + "..."

            # Applica combinazione intelligente
            clean_text = dedup_responses(full_text.strip())
            reply_text = cut_sentence(clean_text)

        except Exception as e:
            context.error(f"Errore nella generazione della risposta: {str(e)}")
            reply_text = "😘!"

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

