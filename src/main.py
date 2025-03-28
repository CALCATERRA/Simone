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
        print(f"[ERRORE] Lettura prompt.txt: {e}")
        return "Sei Simone, una ragazza ironica e spontanea. Non chiedere mai come puoi aiutare."

# === Stato: caricamento/salvataggio ===
def load_processed_ids():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"instagram": []}

def save_processed_ids(data):
    with open(STATE_FILE, "w") as f:
        json.dump(data, f)

# === Instagram: recupero messaggi ===
def get_instagram_messages():
    print("[INFO] Chiamata a get_instagram_messages()")
    token = os.getenv("INSTAGRAM_TOKEN")
    url = f"https://graph.instagram.com/v18.0/me/conversations?fields=messages{{id,message,from,created_time}}&access_token={token}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        print("[ERRORE] Recupero messaggi Instagram:", response.text)
        return None

# === OpenAI: invio prompt ===
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
        print("[ERRORE] OpenAI:", e)
        return "Ops! Qualcosa è andato storto."

# === Instagram: invia risposta ===
def send_instagram_reply(user_id, text):
    token = os.getenv("INSTAGRAM_TOKEN")
    url = f"https://graph.instagram.com/v18.0/me/messages?access_token={token}"
    data = {
        "recipient": {"id": user_id},
        "message": {"text": text}
    }
    response = requests.post(url, json=data)
    if response.status_code != 200:
        print("[ERRORE] Invio messaggio Instagram:", response.text)

# === Funzione principale ===
def main(context):
    # Verifica webhook Meta
    mode = context.req.query.get("hub.mode")
    challenge = context.req.query.get("hub.challenge")
    verify_token = context.req.query.get("hub.verify_token")

    if mode == "subscribe" and verify_token == os.getenv("VERIFY_TOKEN"):
        return context.res.text(challenge)

    processed = load_processed_ids()
    page_id = os.getenv("INSTAGRAM_PAGE_ID")

    # === Lettura e risposta ai messaggi Instagram ===
    instagram_data = get_instagram_messages()
    if instagram_data and "data" in instagram_data:
        for conv in instagram_data["data"]:
            if "messages" in conv:
                for msg in conv["messages"]["data"]:
                    msg_id = msg["id"]
                    sender_id = msg["from"]["id"]

                    # Evita di rispondere ai propri messaggi
                    if sender_id == page_id:
                        continue

                    if msg_id in processed["instagram"]:
                        continue

                    text = msg.get("message")
                    if text:
                        print(f"[Instagram] Nuovo messaggio da {sender_id}: {text}")
                        reply = send_message_to_openai(text)
                        send_instagram_reply(sender_id, reply)
                        processed["instagram"].append(msg_id)

    save_processed_ids(processed)
    return context.res.text("Esecuzione completata.")
