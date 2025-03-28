import os
import json
import requests
import openai

STATE_FILE = "last_message_ids.json"

# === Lettura prompt ===
def get_prompt():
    try:
        with open("prompt.txt", "r", encoding="utf-8") as file:
            return file.read().strip()
    except Exception as e:
        print(f"[ERRORE] prompt.txt: {e}")
        return "Sei Simone, una ragazza ironica e spontanea. Non chiedere mai come puoi aiutare."

# === Carica messaggi già risposti ===
def load_processed_ids():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"messenger": [], "instagram": []}

# === Salva nuovi ID messaggi ===
def save_processed_ids(data):
    with open(STATE_FILE, "w") as f:
        json.dump(data, f)

# === API: Messenger ===
def get_messenger_messages():
    token = os.getenv("MESSENGER_TOKEN")
    url = f"https://graph.facebook.com/v18.0/me/conversations?fields=messages{{message,from,id,created_time}}&access_token={token}"
    response = requests.get(url)
    return response.json() if response.status_code == 200 else None

# === API: Instagram ===
def get_instagram_messages():
    token = os.getenv("INSTAGRAM_TOKEN")
    url = f"https://graph.instagram.com/v18.0/me/conversations?fields=messages{{message,from,id,created_time}}&access_token={token}"
    response = requests.get(url)
    return response.json() if response.status_code == 200 else None

# === OpenAI ===
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
        print(f"[ERRORE OpenAI] {e}")
        return "Ops! Qualcosa è andato storto."

# === Risposte ===
def send_messenger_reply(user_id, text):
    token = os.getenv("MESSENGER_TOKEN")
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={token}"
    data = {"recipient": {"id": user_id}, "message": {"text": text}}
    res = requests.post(url, json=data)
    if res.status_code != 200:
        print(f"[ERRORE] Messenger reply: {res.text}")

def send_instagram_reply(user_id, text):
    token = os.getenv("INSTAGRAM_TOKEN")
    url = f"https://graph.instagram.com/v18.0/me/messages?access_token={token}"
    data = {"recipient": {"id": user_id}, "message": {"text": text}}
    res = requests.post(url, json=data)
    if res.status_code != 200:
        print(f"[ERRORE] Instagram reply: {res.text}")

# === Funzione principale ===
def main(context):
    mode = context.req.query.get("hub.mode")
    challenge = context.req.query.get("hub.challenge")
    verify_token = context.req.query.get("hub.verify_token")

    if mode == "subscribe" and verify_token == os.getenv("VERIFY_TOKEN"):
        return context.res.text(challenge)

    # Stato messaggi
    processed = load_processed_ids()

    # === Messenger ===
    messenger_data = get_messenger_messages()
    if messenger_data and "data" in messenger_data:
        for conv in messenger_data["data"]:
            if "messages" in conv:
                for msg in conv["messages"]["data"]:
                    msg_id = msg["id"]
                    if msg_id in processed["messenger"]:
                        continue  # già risposto

                    user_id = msg["from"]["id"]
                    text = msg.get("message")
                    if text:
                        print(f"[Messenger] {text}")
                        reply = send_message_to_openai(text)
                        send_messenger_reply(user_id, reply)
                        processed["messenger"].append(msg_id)

    # === Instagram ===
    instagram_data = get_instagram_messages()
    if instagram_data and "data" in instagram_data:
        for conv in instagram_data["data"]:
            if "messages" in conv:
                for msg in conv["messages"]["data"]:
                    msg_id = msg["id"]
                    if msg_id in processed["instagram"]:
                        continue  # già risposto

                    user_id = msg["from"]["id"]
                    text = msg.get("message")
                    if text:
                        print(f"[Instagram] {text}")
                        reply = send_message_to_openai(text)
                        send_instagram_reply(user_id, reply)
                        processed["instagram"].append(msg_id)

    # === Salva nuovi ID
    save_processed_ids(processed)
    return context.res.text("Esecuzione completata.")
