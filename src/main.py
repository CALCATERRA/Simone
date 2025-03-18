import os
import requests
import openai
from appwrite.client import Client
from appwrite.exception import AppwriteException

# Funzione per leggere il prompt da un file
def read_prompt():
    prompt_path = os.path.join(os.path.dirname(__file__), "prompt.txt")
    try:
        with open(prompt_path, "r", encoding="utf-8") as file:
            return file.read().strip()
    except FileNotFoundError:
        print("Errore: Il file prompt.txt non è stato trovato.")
        return "Rispondi in modo professionale."

# Funzione per ottenere i messaggi da Instagram
def get_instagram_messages():
    token = os.getenv("INSTAGRAM_TOKEN")
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={token}"
    response = requests.get(url)

    if response.status_code == 200:
        return response.json()
    else:
        print("Errore nel recupero dei messaggi Instagram:", response.text)
        return None

# Funzione per generare una risposta con OpenAI
def send_message_to_openai(user_message):
    openai.api_key = os.getenv("OPENAI_API_KEY")
    prompt = read_prompt()  # Legge il prompt dal file
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": prompt},
                      {"role": "user", "content": user_message}]
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("Errore nella chiamata a OpenAI:", str(e))
        return "Mi dispiace, si è verificato un errore."

# Funzione per inviare una risposta su Instagram
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

# Funzione principale eseguita da Appwrite
def main(context):
    messages = get_instagram_messages()
    if messages and "data" in messages:
        for msg in messages["data"]:
            user_id = msg["sender"]["id"]
            user_message = msg["message"]["text"]
            response_text = send_message_to_openai(user_message)
            send_instagram_reply(user_id, response_text)

    return context.res.text("Execution complete.")

