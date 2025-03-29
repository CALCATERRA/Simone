import os
import json
import openai
import requests

def main(req, res):
    try:
        body = json.loads(req.body.decode("utf-8") or "{}")
        print("Request body:", body)

        # Verifica del webhook (Messenger)
        if req.method == "GET":
            mode = req.query.get("hub.mode")
            token = req.query.get("hub.verify_token")
            challenge = req.query.get("hub.challenge")

            if mode == "subscribe" and token == os.environ["VERIFY_TOKEN"]:
                return res.json({"challenge": challenge})
            else:
                return res.json({"error": "Verification failed"}, 403)

        # POST - Messaggio in arrivo
        if req.method == "POST":
            entry = body.get("entry", [])[0]
            changes = entry.get("changes", [])[0]
            value = changes.get("value", {})
            messages = value.get("messages", [])
            
            if not messages:
                return res.send("No message to process.")

            message = messages[0]
            sender_id = message["from"]
            user_text = message["text"]["body"]
            print(f"Ricevuto da Instagram: {user_text}")

            # Carica il prompt da file
            with open("prompt.txt", "r") as f:
                prompt_prefix = f.read()

            prompt = f"{prompt_prefix}\n\nUtente: {user_text}\nAssistente:"

            # Chiamata a OpenAI
            openai.api_key = os.environ["OPENAI_API_KEY"]
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": prompt_prefix}, {"role": "user", "content": user_text}]
            )
            reply = response.choices[0].message["content"].strip()
            print(f"Risposta generata: {reply}")

            # Invia la risposta su Instagram
            instagram_token = os.environ["INSTAGRAM_TOKEN"]
            username = "simonefoulesol"

            # Ottieni l'ID della pagina Instagram dal nome utente
            user_url = f"https://graph.instagram.com/v18.0/{username}?fields=id&access_token={instagram_token}"
            user_res = requests.get(user_url)
            user_id = user_res.json().get("id")

            if not user_id:
                print("Errore: impossibile ottenere l'ID dell'utente Instagram.")
                return res.json({"error": "Instagram ID not found"}, 500)

            message_url = f"https://graph.instagram.com/v18.0/{user_id}/messages"
            payload = {
                "messaging_product": "instagram",
                "recipient": {"id": sender_id},
                "message": {"text": reply}
            }
            headers = {"Content-Type": "application/json"}
            r = requests.post(message_url, headers=headers, json=payload, params={"access_token": instagram_token})

            print(f"Risposta inviata: {r.status_code} - {r.text}")
            return res.send("OK")

        return res.send("Unsupported method", 405)

    except Exception as e:
        print("Errore:", str(e))
        return res.json({"error": str(e)}, 500)
