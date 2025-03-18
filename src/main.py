import os
import requests
import openai
from appwrite.client import Client
from appwrite.exception import AppwriteException

def get_instagram_messages():
    token = os.getenv("INSTAGRAM_TOKEN")
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={token}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        print("Errore nel recupero dei messaggi Instagram:", response.text)
        return None

def send_message_to_openai(user_message):
    openai.api_key = os.getenv("OPENAI_API_KEY")
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "system", "content": "Rispondi in modo chiaro e professionale."},
                  {"role": "user", "content": user_message}]
    )
    return response["choices"][0]["message"]["content"].strip()

def send_instagram_reply(user_id, response_text):
    token = os.getenv("INSTAGRAM_TOKEN")
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={token}"
    data = {
        "recipient": {"id": user_id},
        "message": {"text": response_text}
    }
    response = requests.post(url, json=data)
    if response.status_code != 200:
        print("Errore nell'invio del messaggio:", response.text)

def main(context):
    # **Gestione della verifica del webhook di Meta**
    mode = context.req.query.get("hub.mode")
    challenge = context.req.query.get("hub.challenge")
    verify_token = context.req.query.get("hub.verify_token")

    if mode == "subscribe" and verify_token == os.getenv("VERIFY_TOKEN"):
        return context.res.text(challenge)  #  RESTITUISCE IL CHALLENGE A META PER COMPLETARE LA VERIFICA

    # **Dopo la verifica, gestisci i messaggi di Instagram**
    messages = get_instagram_messages()
    if messages and "data" in messages:
        for msg in messages["data"]:
            user_id = msg["sender"]["id"]
            user_message = msg["message"]["text"]
            response_text = send_message_to_openai(user_message)
            send_instagram_reply(user_id, response_text)

    return context.res.text("Execution complete.")
