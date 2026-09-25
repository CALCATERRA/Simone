from workers import WorkerEntrypoint, Response

from datetime import datetime, timezone
from pathlib import Path
import json
import time

from js import fetch, Headers
from pyodide.ffi import to_js


# =========================================================
# 🌤️ CONTEXT ENGINE: METEO (INVARIATO)
# =========================================================
async def get_weather(api_key, city):
    try:
        if not api_key:
            return None

        url = "https://api.openweathermap.org/data/2.5/weather"

        params = (
            f"?q={city}"
            f"&appid={api_key}"
            f"&units=metric"
            f"&lang=it"
        )

        response = await fetch(url + params)

        if not response.ok:
            return None

        data = await response.json()
        data = data.to_py()

        temp = data["main"]["temp"]
        desc = data["weather"][0]["description"]

        return f"{temp}°C, {desc}"

    except Exception:
        return None


# =========================================================
# 🔁 ROTAZIONE GEMINI KEYS (INVARIATO)
# =========================================================
def get_rotated_gemini_key(env):
    now = datetime.now()
    hour = now.hour

    if 6 <= hour < 10:
        index = 1
    elif 10 <= hour < 15:
        index = 2
    elif 15 <= hour < 18:
        index = 3
    elif 18 <= hour < 22:
        index = 5
    elif 22 <= hour or hour < 2:
        index = 5
    else:
        return None

    return getattr(env, f"GEMINI_API_KEY_{index}", None)


# =========================================================
# 📄 CARICAMENTO PROMPT
# =========================================================
async def load_prompt(env):
    response = await env.ASSETS.fetch(
        "https://assets/prompt.json"
    )

    if not response.ok:
        raise RuntimeError(
            f"Impossibile caricare prompt.json: HTTP {response.status}"
        )

    data = await response.json()
    return data


# =========================================================
# 🤖 GEMINI HTTP API
# =========================================================
async def generate_gemini_response(
    api_key,
    prompt_parts
):
    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/gemini-3.1-flash-lite-preview:generateContent"
    )

    payload = {
        "contents": [
            {
                "parts": prompt_parts
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 120,
            "topK": 64,
            "topP": 0.95
        }
    }

    headers = Headers.new()
    headers.set("Content-Type", "application/json")
    headers.set("x-goog-api-key", api_key)

    response = await fetch(
        url,
        {
            "method": "POST",
            "headers": headers,
            "body": json.dumps(payload)
        }
    )

    if not response.ok:
        error_text = await response.text()
        raise RuntimeError(
            f"Gemini HTTP {response.status}: {error_text}"
        )

    data = await response.json()
    data = data.to_py()

    candidates = data.get("candidates", [])

    if not candidates:
        raise ValueError("No response candidates")

    parts = candidates[0].get("content", {}).get("parts", [])

    if not parts:
        raise ValueError("No response parts")

    text_parts = []

    for part in parts:
        if "text" in part:
            text_parts.append(part["text"])

    reply_text = "".join(text_parts).strip()

    if not reply_text:
        raise ValueError("Empty Gemini response")

    return reply_text


# =========================================================
# 📩 RECUPERO CONVERSAZIONI INSTAGRAM
# =========================================================
async def get_instagram_conversations(instagram_token):
    convo_url = "https://graph.instagram.com/v18.0/me/conversations"

    url = (
        f"{convo_url}"
        "?fields=messages{message,from,id,created_time}"
        f"&access_token={instagram_token}"
    )

    response = await fetch(url)

    if not response.ok:
        error_text = await response.text()
        raise RuntimeError(
            f"Instagram conversations HTTP "
            f"{response.status}: {error_text}"
        )

    return (await response.json()).to_py()


# =========================================================
# 🆔 RECUPERO ID PAGINA INSTAGRAM
# =========================================================
async def get_instagram_page_id(instagram_token):
    url = (
        "https://graph.instagram.com/me"
        "?fields=id"
        f"&access_token={instagram_token}"
    )

    response = await fetch(url)

    if not response.ok:
        error_text = await response.text()
        raise RuntimeError(
            f"Instagram page ID HTTP "
            f"{response.status}: {error_text}"
        )

    data = (await response.json()).to_py()

    return data.get("id")


# =========================================================
# 🚫 DEDUPLICAZIONE PERSISTENTE D1
# =========================================================
async def is_message_processed(db, message_id):
    result = await db.prepare(
        """
        SELECT message_id
        FROM processed_messages
        WHERE message_id = ?
        LIMIT 1
        """
    ).bind(message_id).run()

    return bool(result.results)


async def mark_message_processed(db, message_id):
    await db.prepare(
        """
        INSERT OR IGNORE INTO processed_messages (message_id)
        VALUES (?)
        """
    ).bind(message_id).run()


# =========================================================
# 💾 SALVATAGGIO MESSAGGIO D1
# =========================================================
async def save_message(
    db,
    instagram_user_id,
    role,
    content
):
    try:
        await db.prepare(
            """
            INSERT INTO messages (
                instagram_user_id,
                role,
                content
            )
            VALUES (?, ?, ?)
            """
        ).bind(
            instagram_user_id,
            role,
            content
        ).run()

    except Exception as error:
        print(f"D1 save message error: {error}")


# =========================================================
# 👤 AGGIORNAMENTO UTENTE D1
# =========================================================
async def save_user(
    db,
    instagram_user_id
):
    try:
        await db.prepare(
            """
            INSERT INTO users (
                instagram_user_id
            )
            VALUES (?)
            ON CONFLICT(instagram_user_id)
            DO UPDATE SET
                updated_at = CURRENT_TIMESTAMP
            """
        ).bind(
            instagram_user_id
        ).run()

    except Exception as error:
        print(f"D1 save user error: {error}")


# =========================================================
# 📤 INVIO INSTAGRAM
# =========================================================
async def send_instagram_message(
    instagram_token,
    user_id,
    reply_text
):
    send_url = "https://graph.instagram.com/v18.0/me/messages"

    payload = {
        "recipient": {
            "id": user_id
        },
        "message": {
            "text": reply_text
        }
    }

    headers = Headers.new()
    headers.set("Content-Type", "application/json")

    url = (
        f"{send_url}"
        f"?access_token={instagram_token}"
    )

    response = await fetch(
        url,
        {
            "method": "POST",
            "headers": headers,
            "body": json.dumps(payload)
        }
    )

    if not response.ok:
        error_text = await response.text()

        raise RuntimeError(
            f"Instagram send HTTP "
            f"{response.status}: {error_text}"
        )


# =========================================================
# 🤖 MAIN WORKER
# =========================================================
class Default(WorkerEntrypoint):

    async def fetch(self, request):

        try:
            print("Funzione avviata")

            # =========================================================
            # 🔐 RECUPERO SECRET
            # =========================================================
            instagram_token = self.env.INSTAGRAM_TOKEN

            openweather_api_key = getattr(
                self.env,
                "OPENWEATHER_API_KEY",
                None
            )

            if not instagram_token:
                print("INSTAGRAM_TOKEN mancante")

                return Response.json(
                    {
                        "ok": False,
                        "error": "Configurazione Instagram mancante"
                    },
                    status=500
                )

            # =========================================================
            # 📄 CARICAMENTO PROMPT
            # =========================================================
            prompt_data = await load_prompt(self.env)

            # =========================================================
            # 🔁 ROTAZIONE GEMINI
            # =========================================================
            gemini_api_key = get_rotated_gemini_key(self.env)

            if not gemini_api_key:
                return Response(
                    "Orario inattivo."
                )

            # =========================================================
            # 📩 RECUPERO CONVERSAZIONI
            # =========================================================
            convo_data = await get_instagram_conversations(
                instagram_token
            )

            if (
                "data" not in convo_data
                or not convo_data["data"]
            ):
                return Response(
                    "Nessun messaggio."
                )

            last_convo = convo_data["data"][0]

            messages = (
                last_convo
                .get("messages", {})
                .get("data", [])
            )

            if not messages:
                return Response(
                    "Nessun messaggio utile."
                )

            # =========================================================
            # 🧠 ORDINE SICURO MESSAGGI
            # =========================================================
            sorted_messages = sorted(
                messages,
                key=lambda m: m["created_time"]
            )

            # =========================================================
            # 🆔 RECUPERO ID PAGINA
            # =========================================================
            page_id = await get_instagram_page_id(
                instagram_token
            )

            if not page_id:
                return Response(
                    "Errore ID pagina."
                )

            last_msg = sorted_messages[-1]

            user_id = last_msg["from"]["id"]
            user_text = last_msg["message"]

            msg_time = datetime.fromisoformat(
                last_msg["created_time"]
                .replace("Z", "+00:00")
            )

            # =========================================================
            # 🚫 SELF MESSAGE CHECK
            # =========================================================
            if user_id == page_id:
                return Response(
                    "Ignorato self message."
                )

            # =========================================================
            # 🚫 DEDUPLICAZIONE ROBUSTA
            # =========================================================
            try:
                already_processed = await is_message_processed(
                    self.env.DB,
                    last_msg["id"]
                )

                if already_processed:
                    return Response(
                        "Duplicato ignorato."
                    )

                await mark_message_processed(
                    self.env.DB,
                    last_msg["id"]
                )

            except Exception as error:
                # D1 non deve bloccare Simone.
                print(
                    f"D1 deduplication error: {error}"
                )

            # =========================================================
            # 👤 SALVATAGGIO UTENTE
            # =========================================================
            try:
                await save_user(
                    self.env.DB,
                    user_id
                )
            except Exception as error:
                print(
                    f"D1 user error: {error}"
                )

            # =========================================================
            # ⏱️ TIMING
            # =========================================================
            now = datetime.now(timezone.utc)

            diff_sec = (
                now - msg_time
            ).total_seconds()

            if diff_sec < 5:
                print(
                    "Messaggio troppo recente."
                )

            # =========================================================
            # 🧠 CONTEXT ENGINE
            # =========================================================
            context_block = f"""
📅 Data: {now.strftime('%d/%m/%Y')}
🕒 Ora: {now.strftime('%H:%M')}
"""

            # =========================================================
            # 🌤️ METEO INTELLIGENTE
            # =========================================================
            trigger_words = [
                "meteo",
                "pioggia",
                "sole",
                "tempo",
                "domani",
                "oggi",
                "uscire",
                "evento",
                "viaggio"
            ]

            include_weather = any(
                word in user_text.lower()
                for word in trigger_words
            )

            if include_weather:

                cities = [
                    "Verona",
                    "Padova",
                    "Milano"
                ]

                weather_lines = []

                for city in cities:

                    weather = await get_weather(
                        openweather_api_key,
                        city
                    )

                    if weather:
                        weather_lines.append(
                            f"{city}: {weather}"
                        )

                if weather_lines:

                    context_block += (
                        "\n🌤️ Meteo:\n"
                        + "\n".join(weather_lines)
                    )

            # =========================================================
            # 🧠 PROMPT BUILDING
            # =========================================================
            prompt_parts = [
                {
                    "text":
                        prompt_data["system_instruction"]
                        + "\n"
                        + context_block
                        + "\n"
                }
            ]

            # =========================================================
            # 💬 CHAT STRUCTURE MIGLIORATA
            # =========================================================
            last_10 = sorted_messages[-10:]

            chat_block = (
                "\nCONVERSAZIONE RECENTE:\n"
            )

            for message in last_10:

                role = (
                    "ASSISTANT"
                    if message["from"]["id"] == page_id
                    else "USER"
                )

                chat_block += (
                    f"{role}: "
                    f"{message['message']}\n"
                )

            chat_block += (
                "\nRispondi in modo coerente "
                "all'ultimo messaggio dell'utente "
                "mantenendo il contesto della "
                "conversazione.\n"
            )

            prompt_parts.append(
                {
                    "text": chat_block
                }
            )

            prompt_parts.append(
                {
                    "text": f"""
🎯 COMPITO

Analizza il messaggio dell’utente e determina se contiene una richiesta reale.

MESSAGGIO UTENTE:
{user_text}

REGOLE:

1. Se il messaggio è una domanda o richiesta → rispondi direttamente e in modo pertinente.

2. Se il messaggio è solo:
- "ok"
- "si"
- emoji
- risposta minimale
→ NON inventare contenuti nuovi
→ rispondi in modo breve e neutro

3. NON continuare storie o conversazioni inventate
4. NON espandere emozioni o scenari non presenti nel messaggio

STILE:
Simone può essere presente, ma non deve mai sostituire la risposta logica.
"""
                }
            )

            # =========================================================
            # 🤖 GENERAZIONE RISPOSTA
            # =========================================================
            try:

                print("PRIMA DI GEMINI")

                reply_text = await generate_gemini_response(
                    gemini_api_key,
                    prompt_parts
                )

                print("DOPO GEMINI")

            except Exception as error:

                print(
                    f"Gemini error: {error}"
                )

                reply_text = "😘"

            # =========================================================
            # ✂️ LIMITAZIONE RISPOSTA
            # =========================================================
            if len(reply_text.split()) > 60:

                reply_text = (
                    " ".join(
                        reply_text.split()[:60]
                    )
                    + "..."
                )

            # =========================================================
            # 💾 SALVATAGGIO MESSAGGI D1
            # =========================================================
            try:

                await save_message(
                    self.env.DB,
                    user_id,
                    "user",
                    user_text
                )

                await save_message(
                    self.env.DB,
                    user_id,
                    "assistant",
                    reply_text
                )

            except Exception as error:

                print(
                    f"D1 messages error: {error}"
                )

            # =========================================================
            # 📤 INVIO INSTAGRAM
            # =========================================================
            await send_instagram_message(
                instagram_token,
                user_id,
                reply_text
            )

            return Response("OK")

        except Exception as error:

            print(
                f"Errore generale: {error}"
            )

            return Response.json(
                {
                    "ok": False,
                    "error": "Errore interno"
                },
                status=500
            )
