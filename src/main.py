import os
import requests
import openai
import time

# ID dell'account Instagram da escludere (il tuo)
MY_INSTAGRAM_ID = "17841464183957073"

# Cache dei messaggi già trattati (volatilmente in RAM)
handled_message_ids = set()

# Funzione per leggere il prompt da un file
def get_prompt():
    try:
        with open("prompt.txt", "r", encoding="utf-8") as file:
            return file.read().strip()
    except Exception as e:
        print(f"Errore nella lettura di prompt.txt: {e}")
        return "Sei Simone, una ragazza ironica e spontanea. Non chiedere mai come puoi aiutare."

# Funzione per ottenere i messaggi da Instagram
def get_instagram_messages():
    print("[INFO] Chiamata a get_instagram_messages()")
    token = os.getenv("INSTAGRAM_TOKEN")
    url = "https://graph.instagram.com/v18.0/me/conversations?fields=messages{message,from,id,created_time}&access_token=" + token

    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        print("[ERROR] Errore nel recupero messaggi:", response.text)
        return None

# Funzione per inviare messaggio a OpenAI
def send_message_to_openai(user_message):
    openai.api_key = os.getenv("OPENAI_API_KEY")
    prompt = get_prompt()

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message}
            ]
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[ERROR] Errore nella chiamata a OpenAI: {e}")
        return "Ops! Qualcosa è andato storto."

# Funzione per rispondere su Instagram
def send_instagram_reply(user_id, text):
    token = os.getenv("INSTAGRAM_TOKEN")
    url = f"https://graph.instagram.com/v18.0/me/messages?access_token={token}"

    data = {
        "recipient": {"id": user_id},
        "message": {"text": text}
    }

    response = requests.post(url, json=data)
    if response.status_code != 200:
        print("[ERROR] Invio risposta Instagram:", response.text)

# Funzione principale per Appwrite
def main(context):
    context.log("[INFO] Funzione avviata.")
    
    # Log della richiesta (utile per debug da Appwrite)
    try:
        context.log("[DEBUG] Corpo richiesta:")
        context.log(context.req.body)
    except:
        pass

    # Verifica webhook di Meta
    mode = context.req.query.get("hub.mode")
    challenge = context.req.query.get("hub.challenge")
    verify_token = context.req.query.get("hub.verify_token")

    if mode == "subscribe" and verify_token == os.getenv("VERIFY_TOKEN"):
        return context.res.text(challenge)

    # Recupera i messaggi da Instagram
    data = get_instagram_messages()

    if data and "data" in data:
        for convo in data["data"]:
            if "messages" in convo:
                for msg in convo["messages"]["data"]:
                    msg_id = msg.get("id")
                    sender_id = msg.get("from", {}).get("id")
                    text = msg.get("message", "").strip()

                    context.log(f"[DEBUG] ID messaggio: {msg_id}")
                    context.log(f"[DEBUG] Mittente ID: {sender_id}")
                    context.log(f"[DEBUG] Contenuto: {text}")

                    # Ignora se:
                    # - messaggio già gestito
                    # - arriva da te stesso
                    if msg_id in handled_message_ids:
                        context.log("[DEBUG] Già gestito. Skip.")
                        continue

                    if sender_id == MY_INSTAGRAM_ID:
                        context.log("[DEBUG] Mittente è l'account personale. Skip.")
                        continue

                    handled_message_ids.add(msg_id)

                    # Elabora e rispondi
                    risposta = send_message_to_openai(text)
                    send_instagram_reply(sender_id, risposta)

    return context.res.text("OK")
