import os
import json
import requests
import time
from datetime import datetime, timezone
import google.generativeai as genai

def get_rotated_gemini_key():
    now = datetime.now()
    hour = now.hour

    if 6 <= hour < 10:
        index = 1
    elif 10 <= hour < 14:
        index = 2
    elif 14 <= hour < 18:
        index = 3
    elif 18 <= hour < 22:
        index = 4
    elif 22 <= hour or hour < 2:
        index = 5
    else:
        # Tra le 2:00 e le 6:00 non usare nessuna chiave
        return None

    return os.environ.get(f"GEMINI_API_KEY_{index}")

def main(context):
    try:
        context.log("Funzione avviata")

        # Carica il prompt da prompt.json
        with open(os.path.join(os.path.dirname(__file__), "prompt.json"), "r") as f:
            prompt_data = json.load(f)

        instagram_token = os.environ["INSTAGRAM_TOKEN"]
        context.log(f"TOKEN caricato: {instagram_token[:10]}...")

        gemini_api_key = get_rotated_gemini_key()
        if not gemini_api_key:
            context.log("Fascia oraria non coperta da API key. Nessuna azione eseguita.")
            return context.res.send("Orario inattivo.")
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel("gemini-2.5-flash-lite")

        # Recupera i messaggi recenti
        convo_url = "https://graph.instagram.com/v18.0/me/conversations"
        convo_params = {"fields": "messages{message,from,id,created_time}", "access_token": instagram_token}
        convo_res = requests.get(convo_url, params=convo_params)
        context.log(f"Richiesta conversazioni: {convo_res.status_code}")
        convo_data = convo_res.json()
        context.log(f"Risposta conversazioni: {json.dumps(convo_data)[:300]}...")

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
        context.log(f"ID pagina: {page_id}")
        if not page_id:
            return context.res.send("Errore nel recupero ID pagina.")

        # Ordina i messaggi per timestamp crescente (dal più vecchio al più nuovo)
        sorted_messages = sorted(messages, key=lambda m: m["created_time"])
        last_msg = sorted_messages[-1]
        user_id = last_msg["from"]["id"]
        user_text = last_msg["message"]
        msg_time = datetime.fromisoformat(last_msg["created_time"].replace("Z", "+00:00"))

        # ✅ Blocca messaggi generati da sé stesso
        if user_id == page_id:
            context.log("Messaggio inviato da me stesso, ignorato.")
            return context.res.send("Messaggio interno ignorato.")

        # 🚫 Blocca messaggi già visti
        processed_ids = getattr(context, "processed_ids", set())
        if last_msg["id"] in processed_ids:
            context.log("Messaggio già gestito, ignorato.")
            return context.res.send("Duplicato ignorato.")
        else:
            processed_ids.add(last_msg["id"])
            context.processed_ids = processed_ids

        context.log(f"Ultimo messaggio da {user_id}: {user_text}")
        context.log(f"Timestamp messaggio: {msg_time}")
        now = datetime.now(timezone.utc)
        diff_sec = (now - msg_time).total_seconds()
        context.log(f"Adesso è: {now}")
        context.log(f"Differenza in secondi: {diff_sec}")

        # 🔧 Disattiva temporaneamente il filtro tempo per debugging
        if diff_sec < 5:
            context.log("Messaggio troppo recente, ignorato.")
            # return context.res.send("Messaggio troppo recente, ignorato.")

        last_response_time = getattr(context, "last_response_time", None)
        current_time = time.time()
        if last_response_time and (current_time - last_response_time < 10):
            context.log("Messaggio ignorato per evitare risposte duplicate.")
            return context.res.send("Ignorato: risposta già inviata di recente.")

        # Costruzione prompt per Gemini: includi sia messaggi utente che risposte Simone
        prompt_parts = [{"text": prompt_data["system_instruction"] + "\n"}]

        # Prendi gli ultimi 10 messaggi (se ce ne sono meno, prende quelli disponibili)
        last_10 = sorted_messages[-10:]

        for m in last_10:
            role = "Simone" if m["from"]["id"] == page_id else "Utente"
            prompt_parts.append({"text": f"{role}: {m['message']}\n"})

        # Aggiungi "Simone:" per far generare la risposta dal modello
        prompt_parts.append({"text": "Simone:"})

        context.log("Prompt per Gemini costruito.")

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

            context.log(f"Gemini ha risposto: {response.text[:200]}...")

            if not response.candidates or not response.text:
                raise ValueError("Gemini non ha generato risposte.")

            reply_text = response.text.strip()
            for prefix in ["User:", "Utente:", "Response:", "Simone:"]:
                if reply_text.startswith(prefix):
                    reply_text = reply_text[len(prefix):].strip()

        except Exception as e:
            context.error(f"Errore nella generazione della risposta: {str(e)}")
            reply_text = "😘"

        # Limita la lunghezza della risposta
        words = reply_text.split()
        if len(words) > 20:
            reply_text = " ".join(words[:20]) + "..."

        context.log(f"Risposta finale: {reply_text}")

        # Invio risposta a Instagram
        send_url = "https://graph.instagram.com/v18.0/me/messages"
        send_payload = {"recipient": {"id": user_id}, "message": {"text": reply_text}}
        send_headers = {"Content-Type": "application/json"}
        send_params = {"access_token": instagram_token}

        context.log(f"Payload inviato a Instagram: {json.dumps(send_payload)}")
        send_res = requests.post(send_url, headers=send_headers, json=send_payload, params=send_params)
        context.log(f"Risposta Instagram: {send_res.status_code} - {send_res.text}")

        context.last_response_time = current_time
        return context.res.send("OK")

    except Exception as e:
        context.error(f"Errore: {str(e)}")
        return context.res.json({"error": str(e)}, 500)
