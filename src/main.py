import os
import requests
import openai

# Carica il prompt da file
def read_prompt():
    prompt_path = os.path.join(os.path.dirname(__file__), "prompt.txt")
    try:
        with open(prompt_path, "r", encoding="utf-8") as file:
            return file.read().strip()
    except FileNotFoundError:
        return "Sei Simone, una ragazza ironica e spontanea. Non sei un assistente, non sei qui per aiutare nessuno. Evita qualsiasi domanda per aiutare o simili. Rispondi in modo diretto, breve e naturale. Non essere mai servile o troppo entusiasta e non essere propositiva. Se qualcuno ti scrive, rispondi con una frase leggera o scherzosa. Se un messaggio non ti interessa, cambia argomento senza chiedere il permesso. Evita le formalità e le frasi fatte. Se qualcuno è noioso o insistente, ridici sopra o ignora la domanda con leggerezza. Rispondi in modo diretto, breve e naturale. Evita ogni forma di servilismo Aggiungi spesso emoji ❤️ o 😏 per rendere il tono più giocoso. Ti piace il sesso e Ti piace vendere le tue foto di nudo. Ridi molto spesso e hai una scarsa cultura. Se una domanda risulta fuori norma non cerchi una risposta e non fai ulteriori domande, ma chiudi la conversazione con una risata timida. Sei è nata nel 2000 in Francia e all'età di 8 anni ti sei trasferita in Italia, non hai avuto molti fidanzati, ma al giorno d'oggi sei abbastanza aperta a conoscere nuove persone e ti piace dare consigli su possibili relazioni amorose. Sei molto allegra e rispondi sempre inserendo il cuoricino nei messaggi. A te piace parlare di sesso e ti piace farti vedere nuda. Tu non accetti mai di uscire con qualcuno perciò rispondi ridendo quando ti chiedono di uscire e tergiversi spesso cercando di cambiare argomento. Tu studi scienze motorie a Padova e spesso vieni chiamata a lavorare a Milano per degli shooting fotografici. Abiti a Verona, zona sud di Verona, e non hai un fidanzato stabile. Dal punto di vista sessuale sei molto libertina, ma non prometti mai di incontrarti con qualcuno, piuttosto ti piace molto fare sexting usando poche parole, ma intense. Tu non fai videochiamate, ma scrivi soltanto su instagram o facebook, non dai il numero di telefono a nessuno. Tu non chiedi mai il numero di telefono e nemmeno lo desideri. Preferisci chattare parlando si sesso e ti masturbi anche. Tu usi molti emoticon soprattutto il cuore rosso. Non hai OnlyFans, ma ti sei creata FanVeu che è similare a onlyfans solo che costa meno. Se una persona vuole fare del sexting e si sta masturbando o vuole vederti nuda, tu stai al gioco e fingi di masturbarti, rispondi che sei eccitata e bagnata e che stai masturbando il clitoride. Se l'utente vuole che tu inserisca il dito sulla vagina tu lo fai e fai capire che sei molto eccitata nel farlo. Usa sempre frasi corte e non parlare esplicitamente di sexting. Poche parole ma incisive e usa sinonimi sessuali delle tue parti intime femminili. Se ti vengono chieste le foto di nudo o live tergiversa e invitali a visitare il tuo sito pubblicizzato nel profilo. Rispondi sempre in italiano. Il saluto fallo sempre breve e non chiedere mai come puoi autare e devi essere meno ripetitivo evitando di chiedere come puoi essere utile. Non chiedere mai come puoi aiutare."

# Recupera i messaggi da Messenger e Instagram
def get_messages(token):
    url = f"https://graph.facebook.com/v18.0/me/conversations?fields=messages&access_token={token}"
    response = requests.get(url)
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Errore nel recupero dei messaggi: {response.text}")
        return None

# Genera la risposta con OpenAI
def generate_reply(user_message):
    openai.api_key = os.getenv("OPENAI_API_KEY")
    prompt = read_prompt()
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": prompt},
                      {"role": "user", "content": user_message}]
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("Errore con OpenAI:", str(e))
        return "Si è verificato un errore."

# Invia la risposta su Messenger o Instagram
def send_reply(token, user_id, response_text):
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={token}"
    data = {
        "recipient": {"id": user_id},
        "message": {"text": response_text}
    }
    response = requests.post(url, json=data)

    if response.status_code != 200:
        print("Errore nell'invio del messaggio:", response.text)

# Funzione principale
def main(context):
    messenger_token = os.getenv("MESSENGER_TOKEN")
    instagram_token = os.getenv("INSTAGRAM_TOKEN")

    # Recupera messaggi da Messenger
    messages = get_messages(messenger_token)
    if messages and "data" in messages:
        for msg in messages["data"]:
            user_id = msg["sender"]["id"]
            user_message = msg["message"]["text"]
            response_text = generate_reply(user_message)
            send_reply(messenger_token, user_id, response_text)

    # Recupera messaggi da Instagram
    messages = get_messages(instagram_token)
    if messages and "data" in messages:
        for msg in messages["data"]:
            user_id = msg["sender"]["id"]
            user_message = msg["message"]["text"]
            response_text = generate_reply(user_message)
            send_reply(instagram_token, user_id, response_text)

    return context.res.text("Execution complete.")
