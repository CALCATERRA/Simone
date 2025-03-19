import os
import requests
import openai

# Funzione per leggere il prompt da un file esterno
def get_prompt():
    try:
        with open("prompt.txt", "r", encoding="utf-8") as file:
            return file.read().strip()
    except Exception as e:
        print(f"Errore nella lettura del prompt.txt: {e}")
        return "Rispondi in modo chiaro e professionale."

# Funzione per ottenere i messaggi da Messenger
def get_messenger_messages():
    token = os.getenv("MESSENGER_TOKEN")
    url = f"https://graph.facebook.com/v18.0/me/conversations?fields=messages&access_token={token}"
    response = requests.get(url)

    if response.status_code == 200:
        return response.json()
    else:
        print("Errore nel recupero dei messaggi Messenger:", response.text)
        return None

# Funzione per ottenere i messaggi da Instagram
def get_instagram_messages():
    token = os.getenv("INSTAGRAM_TOKEN")
    url = f"https://graph.facebook.com/v18.0/me/conversations?fields=messages&access_token={token}"
    response = requests.get(url)

    if response.status_code == 200:
        return response.json()
    else:
        print("Errore nel recupero dei messaggi Instagram:", response.text)
        return None

# Funzione per inviare il messaggio a OpenAI
def send_message_to_openai(user_message):
    openai.api_key = os.getenv("OPENAI_API_KEY")
    system_prompt = get_prompt()  # Legge il prompt personalizzato


    with open("prompt.txt", "r", encoding="utf-8") as f:
    custom_prompt = f.read().strip()
    
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "system", "content": custom_prompt},
                  {"role": "user", "content": user_message}]
    )

    return response["choices"][0]["message"]["content"].strip()

# Funzione per inviare la risposta su Messenger
def send_messenger_reply(user_id, response_text):
    token = os.getenv("MESSENGER_TOKEN")
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={token}"

    data = {
        "recipient": {"id": user_id},
        "message": {"text": response_text}
    }

    response = requests.post(url, json=data)
    if response.status_code != 200:
        print("Errore nell'invio del messaggio su Messenger:", response.text)

# Funzione per inviare la risposta su Instagram
def send_instagram_reply(user_id, response_text):
    token = os.getenv("INSTAGRAM_TOKEN")
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={token}"

    data = {
        "recipient": {"id": user_id},
        "message": {"text": response_text}
    }

    response = requests.post(url, json=data)
    if response.status_code != 200:
        print("Errore nell'invio del messaggio su Instagram:", response.text)

# Funzione principale
def main(context):
    # Gestione della verifica del webhook di Meta
    mode = context.req.query.get("hub.mode")
    challenge = context.req.query.get("hub.challenge")
    verify_token = context.req.query.get("hub.verify_token")

    if mode == "subscribe" and verify_token == os.getenv("VERIFY_TOKEN"):
        return context.res.text(challenge)

    # Recupero e risposta ai messaggi Messenger
    messenger_messages = get_messenger_messages()
    if messenger_messages and "data" in messenger_messages:
        for msg in messenger_messages["data"]:
            user_id = msg.get("id")  
            user_message = msg.get("message", {}).get("text", "")

            if user_id and user_message:
                response_text = send_message_to_openai(user_message)
                send_messenger_reply(user_id, response_text)

    # Recupero e risposta ai messaggi Instagram
    instagram_messages = get_instagram_messages()
    if instagram_messages and "data" in instagram_messages:
        for msg in instagram_messages["data"]:
            user_id = msg.get("id")  
            user_message = msg.get("message", {}).get("text", "")

            if user_id and user_message:
                response_text = send_message_to_openai(user_message)
                send_instagram_reply(user_id, response_text)

    return context.res.text("Execution complete.")
