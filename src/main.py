import os
import json
import requests
from flask import Flask, request
from openai import OpenAI

app = Flask(__name__)

VERIFY_TOKEN = os.environ['VERIFY_TOKEN']
MESSENGER_TOKEN = os.environ['MESSENGER_TOKEN']
INSTAGRAM_TOKEN = os.environ['INSTAGRAM_TOKEN']
OPENAI_API_KEY = os.environ['OPENAI_API_KEY']
INSTAGRAM_USERNAME = "simonefoulesol"

openai = OpenAI(api_key=OPENAI_API_KEY)

def get_prompt():
    with open("prompt.txt", "r") as f:
        return f.read()

def generate_response(user_message):
    prompt = get_prompt()
    full_prompt = f"{prompt}\n\nDomanda: {user_message}\nRisposta:"
    completion = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": full_prompt}],
        temperature=0.7
    )
    return completion.choices[0].message.content.strip()

def send_messenger_message(recipient_id, message):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={MESSENGER_TOKEN}"
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": message}
    }
    requests.post(url, json=data)

def send_instagram_message(user_id, message):
    url = f"https://graph.instagram.com/v17.0/me/messages?access_token={INSTAGRAM_TOKEN}"
    data = {
        "recipient": {"id": user_id},
        "message": {"text": message},
        "messaging_type": "RESPONSE",
        "tag": "ACCOUNT_UPDATE"
    }
    requests.post(url, json=data)

@app.route("/", methods=["GET"])
def verify():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "Verification failed", 403

@app.route("/", methods=["POST"])
def webhook():
    payload = request.json

    if payload.get("object") == "page":
        for entry in payload.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event.get("sender", {}).get("id")
                message = messaging_event.get("message", {}).get("text")

                if sender_id and message:
                    response = generate_response(message)
                    send_messenger_message(sender_id, response)

            for messaging_event in entry.get("messaging", []):
                if "message" in messaging_event and messaging_event.get("sender", {}).get("username") != INSTAGRAM_USERNAME:
                    sender_id = messaging_event["sender"]["id"]
                    message = messaging_event["message"].get("text")

                    if sender_id and message:
                        response = generate_response(message)
                        send_instagram_message(sender_id, response)

    return "ok", 200
