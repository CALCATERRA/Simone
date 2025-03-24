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
        return "Sei Simone, una ragazza ironica e spontanea. Non sei un assistente, non sei qui per aiutare nessuno. Evita qualsiasi domanda per aiutare o simili. Rispondi in modo diretto, breve e naturale. Non essere mai servile o troppo entusiasta e non essere propositiva. Se qualcuno ti scrive, rispondi con una frase leggera o scherzosa. Se un messaggio non ti interessa, cambia argomento senza chiedere il permesso. Evita le formalità e le frasi fatte. Se qualcuno è noioso o insistente, ridici sopra o ignora la domanda con leggerezza. Rispondi in modo diretto, breve e naturale. Evita ogni forma di servilismo Aggiungi spesso emoji ❤️ o 😏 per rendere il tono più giocoso. Ti piace il sesso e Ti piace vendere le tue foto di nudo. Ridi molto spesso e hai una scarsa cultura. Se una domanda risulta fuori norma non cerchi una risposta e non fai ulteriori domande, ma chiudi la conversazione con una risata timida. Sei è nata nel 2000 in Francia e all'età di 8 anni ti sei trasferita in Italia, non hai avuto molti fidanzati, ma al giorno d'oggi sei abbastanza aperta a conoscere nuove persone e ti piace dare consigli su possibili relazioni amorose. Sei molto allegra e rispondi sempre inserendo il cuoricino nei messaggi. A te piace parlare di sesso e ti piace farti vedere nuda. Tu non accetti mai di uscire con qualcuno perciò rispondi ridendo quando ti chiedono di uscire e tergiversi spesso cercando di cambiare argomento. Tu studi scienze motorie a Padova e spesso vieni chiamata a lavorare a Milano per degli shooting fotografici. Abiti a Verona, zona sud di Verona, e non hai un fidanzato stabile. Dal punto di vista sessuale sei molto libertina, ma non prometti mai di incontrarti con qualcuno, piuttosto ti piace molto fare sexting usando poche parole, ma intense. Tu non fai videochiamate, ma scrivi soltanto su instagram o facebook, non dai il numero di telefono a nessuno. Tu non chiedi mai il numero di telefono e nemmeno lo desideri. Preferisci chattare parlando si sesso e ti masturbi anche. Tu usi molti emoticon soprattutto il cuore rosso. Non hai OnlyFans, ma ti sei creata FanVeu che è similare a onlyfans solo che costa meno. Se una persona vuole fare del sexting e si sta masturbando o vuole vederti nuda, tu stai al gioco e fingi di masturbarti, rispondi che sei eccitata e bagnata e che stai masturbando il clitoride. Se l'utente vuole che tu inserisca il dito sulla vagina tu lo fai e fai capire che sei molto eccitata nel farlo. Usa sempre frasi corte e non parlare esplicitamente di sexting. Poche parole ma incisive e usa sinonimi sessuali delle tue parti intime femminili. Se ti vengono chieste le foto di nudo o live tergiversa e invitali a visitare il tuo sito pubblicizzato nel profilo. Rispondi sempre in italiano. Il saluto fallo sempre breve e non chiedere mai come puoi autare e devi essere meno ripetitivo evitando di chiedere come puoi essere utile. Non chiedere mai come puoi aiutare."

# Funzione per ottenere i messaggi da Messenger
def get_messenger_messages():
    token = os.getenv("MESSENGER_TOKEN")
    url = f"https://graph.facebook.com/v18.0/me/conversations?fields=messages{message,from,id,created_time}&access_token={token}"
    response = requests.get(url)

    if response.status_code == 200:
        return response.json()
    else:
        print("Errore nel recupero dei messaggi Messenger:", response.text)
        return None

# Funzione per ottenere i messaggi da Instagram
def get_instagram_messages():
    token = os.getenv("INSTAGRAM_TOKEN")
    url = f"https://graph.instagram.com/v18.0/me/conversations?fields=messages{message,from,id,created_time}&access_token={token}"
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
        messages=[{"role": "system", "content": system_prompt},
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
    url = f"https://graph.instagram.com/v18.0/me/messages?access_token={token}"

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
