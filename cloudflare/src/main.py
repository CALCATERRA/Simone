```python
from workers import WorkerEntrypoint, Response

from datetime import datetime, timezone
import json
import time

from js import fetch, Headers


# =========================================================
# 🌤️ CONTEXT ENGINE: METEO
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
# 🔁 ROTAZIONE GEMINI KEYS
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
        index = 4
    elif 22 <= hour or hour < 2:
        index = 5
    else:
        return None

    return getattr(
        env,
        f"GEMINI_API_KEY_{index}",
        None
    )


# =========================================================
# 📄 CARICAMENTO PROMPT
# =========================================================
async def load_prompt(env):
    response = await env.ASSETS.fetch(
        "https://assets/prompt.json"
    )

    if not response.ok:
        raise RuntimeError(
            f"Impossibile caricare prompt.json: "
            f"HTTP {response.status}"
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
        "v1beta/models/gemini-3.1-flash-lite-preview:"
        "generateContent"
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
    headers.set(
        "Content-Type",
        "application/json"
    )
    headers.set(
        "x-goog-api-key",
        api_key
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
            f"Gemini HTTP {response.status}: "
            f"{error_text}"
        )

    data = await response.json()
    data = data.to_py()

    candidates = data.get("candidates", [])

    if not candidates:
        raise ValueError(
            "No response candidates"
        )

    parts = (
        candidates[0]
        .get("content", {})
        .get("parts", [])
    )

    if not parts:
        raise ValueError(
            "No response parts"
        )

    text_parts = []

    for part in parts:
        if "text" in part:
            text_parts.append(
                part["text"]
            )

    reply_text = "".join(
        text_parts
    ).strip()

    if not reply_text:
        raise ValueError(
            "Empty Gemini response"
        )

    return reply_text


# =========================================================
# 🚫 DEDUPLICAZIONE PERSISTENTE D1
# =========================================================
async def is_message_processed(
    db,
    message_id
):
    result = await db.prepare(
        """
        SELECT instagram_message_id
        FROM processed_messages
        WHERE instagram_message_id = ?
        LIMIT 1
        """
    ).bind(
        message_id
    ).run()

    return bool(result.results)


async def mark_message_processed(
    db,
    message_id
):
    await db.prepare(
        """
        INSERT OR IGNORE INTO processed_messages (
            instagram_message_id
        )
        VALUES (?)
        """
    ).bind(
        message_id
    ).run()


# =========================================================
# 💾 SALVATAGGIO MESSAGGIO D1
# =========================================================
async def save_message(
    db,
    instagram_message_id,
    instagram_user_id,
    role,
    content
):
    try:
        await db.prepare(
            """
            INSERT INTO messages (
                instagram_message_id,
                instagram_user_id,
                role,
                content
            )
            VALUES (?, ?, ?, ?)
            """
        ).bind(
            instagram_message_id,
            instagram_user_id,
            role,
            content
        ).run()

    except Exception as error:
        print(
            f"D1 save message error: {error}"
        )


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
                last_seen = CURRENT_TIMESTAMP
            """
        ).bind(
            instagram_user_id
        ).run()

    except Exception as error:
        print(
            f"D1 save user error: {error}"
        )


# =========================================================
# 🧠 RECUPERO CRONOLOGIA DA D1
# =========================================================
async def get_recent_messages(
    db,
    instagram_user_id,
    limit=10
):
    try:
        result = await db.prepare(
            """
            SELECT role, content, created_at
            FROM messages
            WHERE instagram_user_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """
        ).bind(
            instagram_user_id,
            limit
        ).run()

        messages = list(result.results)

        messages.reverse()

        return messages

    except Exception as error:
        print(
            f"D1 history error: {error}"
        )

        return []


# =========================================================
# 📤 INVIO INSTAGRAM
# =========================================================
async def send_instagram_message(
    instagram_token,
    user_id,
    reply_text
):
    send_url = (
        "https://graph.instagram.com/v18.0/me/messages"
    )

    payload = {
        "recipient": {
            "id": user_id
        },
        "message": {
            "text": reply_text
        }
    }

    headers = Headers.new()
    headers.set(
        "Content-Type",
        "application/json"
    )

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
# 🔐 WEBHOOK VERIFICATION
# =========================================================
async def handle_webhook_verification(
    request,
    env
):
    url = request.url

    query_string = ""

    if "?" in url:
        query_string = url.split("?", 1)[1]

    params = {}

    for item in query_string.split("&"):
        if "=" in item:
            key, value = item.split("=", 1)
            params[key] = value

    mode = params.get("hub.mode")
    verify_token = params.get(
        "hub.verify_token"
    )
    challenge = params.get(
        "hub.challenge"
    )

    expected_token = getattr(
        env,
        "META_VERIFY_TOKEN",
        None
    )

    if (
        mode == "subscribe"
        and verify_token
        and expected_token
        and verify_token == expected_token
        and challenge
    ):
        print(
            "Webhook Meta verificato correttamente"
        )

        return Response(
            challenge,
            status=200
        )

    print(
        "Verifica webhook Meta fallita"
    )

    return Response(
        "Forbidden",
        status=403
    )


# =========================================================
# 📩 ESTRAZIONE MESSAGGIO WEBHOOK
# =========================================================
def extract_instagram_message(payload):
    """
    Estrae il primo messaggio utile dal payload
    webhook Instagram/Meta.
    """

    entries = payload.get(
        "entry",
        []
    )

    if not entries:
        return None

    for entry in entries:

        messaging = entry.get(
            "messaging",
            []
        )

        for event in messaging:

            sender = event.get(
                "sender",
                {}
            )

            message = event.get(
                "message",
                {}
            )

            if not sender or not message:
                continue

            message_id = message.get(
                "mid"
            )

            text = message.get(
                "text"
            )

            sender_id = sender.get(
                "id"
            )

            timestamp = event.get(
                "timestamp"
            )

            if (
                not message_id
                or not text
                or not sender_id
            ):
                continue

            return {
                "id": str(message_id),
                "user_id": str(sender_id),
                "text": str(text),
                "timestamp": timestamp
            }

    return None


# =========================================================
# 🤖 ELABORAZIONE MESSAGGIO
# =========================================================
async def process_instagram_message(
    worker,
    message_data
):
    instagram_token = worker.env.INSTAGRAM_TOKEN

    openweather_api_key = getattr(
        worker.env,
        "OPENWEATHER_API_KEY",
        None
    )

    message_id = message_data["id"]
    user_id = message_data["user_id"]
    user_text = message_data["text"]

    # =====================================================
    # 🚫 DEDUPLICAZIONE
    # =====================================================
    try:
        already_processed = (
            await is_message_processed(
                worker.env.DB,
                message_id
            )
        )

        if already_processed:
            print(
                "Duplicato ignorato."
            )

            return Response(
                "OK",
                status=200
            )

        await mark_message_processed(
            worker.env.DB,
            message_id
        )

    except Exception as error:
        print(
            f"D1 deduplication error: {error}"
        )

    # =====================================================
    # 👤 SALVATAGGIO UTENTE
    # =====================================================
    await save_user(
        worker.env.DB,
        user_id
    )

    # =====================================================
    # ⏱️ ORARIO
    # =====================================================
    now = datetime.now(
        timezone.utc
    )

    # =====================================================
    # 🧠 CONTEXT ENGINE
    # =====================================================
    context_block = f"""
📅 Data: {now.strftime('%d/%m/%Y')}
🕒 Ora: {now.strftime('%H:%M')}
"""

    # =====================================================
    # 🌤️ METEO INTELLIGENTE
    # =====================================================
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
                + "\n".join(
                    weather_lines
                )
            )

    # =====================================================
    # 🧠 CRONOLOGIA D1
    # =====================================================
    recent_messages = (
        await get_recent_messages(
            worker.env.DB,
            user_id,
            10
        )
    )

    # =====================================================
    # 🧠 PROMPT
    # =====================================================
    prompt_data = await load_prompt(
        worker.env
    )

    prompt_parts = [
        {
            "text":
                prompt_data["system_instruction"]
                + "\n"
                + context_block
                + "\n"
        }
    ]

    # =====================================================
    # 💬 CONVERSAZIONE RECENTE
    # =====================================================
    chat_block = (
        "\nCONVERSAZIONE RECENTE:\n"
    )

    for message in recent_messages:

        if message["role"] == "assistant":
            role = "ASSISTANT"
        else:
            role = "USER"

        chat_block += (
            f"{role}: "
            f"{message['content']}\n"
        )

    # Aggiungiamo il messaggio appena ricevuto
    # perché il salvataggio D1 avviene dopo Gemini.
    chat_block += (
        f"USER: {user_text}\n"
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

    # =====================================================
    # 🎯 COMPITO
    # =====================================================
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

    # =====================================================
    # 🔁 ROTAZIONE GEMINI
    # =====================================================
    gemini_api_key = get_rotated_gemini_key(
        worker.env
    )

    if not gemini_api_key:
        print(
            "Orario Gemini inattivo."
        )

        return Response(
            "OK",
            status=200
        )

    # =====================================================
    # 🤖 GENERAZIONE GEMINI
    # =====================================================
    try:

        print(
            "PRIMA DI GEMINI"
        )

        reply_text = (
            await generate_gemini_response(
                gemini_api_key,
                prompt_parts
            )
        )

        print(
            "DOPO GEMINI"
        )

    except Exception as error:

        print(
            f"Gemini error: {error}"
        )

        reply_text = "😘"

    # =====================================================
    # ✂️ LIMITAZIONE RISPOSTA
    # =====================================================
    if len(reply_text.split()) > 60:

        reply_text = (
            " ".join(
                reply_text.split()[:60]
            )
            + "..."
        )

    # =====================================================
    # 💾 SALVATAGGIO D1
    # =====================================================
    try:

        await save_message(
            worker.env.DB,
            message_id,
            user_id,
            "user",
            user_text
        )

        await save_message(
            worker.env.DB,
            str(time.time_ns()),
            user_id,
            "assistant",
            reply_text
        )

    except Exception as error:

        print(
            f"D1 messages error: {error}"
        )

    # =====================================================
    # 📤 RISPOSTA INSTAGRAM
    # =====================================================
    await send_instagram_message(
        instagram_token,
        user_id,
        reply_text
    )

    return Response(
        "OK",
        status=200
    )


# =========================================================
# 🤖 MAIN WORKER
# =========================================================
class Default(WorkerEntrypoint):

    async def fetch(self, request):

        try:

            print(
                f"Funzione avviata: "
                f"{request.method} {request.url}"
            )

            # =================================================
            # 🌐 HEALTH CHECK
            # =================================================
            if request.method == "GET":

                # La GET /webhook viene usata da Meta
                # per verificare il webhook.
                if "/webhook" in request.url:
                    return await handle_webhook_verification(
                        request,
                        self.env
                    )

                return Response(
                    "Simone Worker OK",
                    status=200
                )

            # =================================================
            # 📩 WEBHOOK POST
            # =================================================
            if (
                request.method == "POST"
                and "/webhook" in request.url
            ):

                payload = await request.json()
                payload = payload.to_py()

                print(
                    "Webhook Instagram ricevuto"
                )

                message_data = (
                    extract_instagram_message(
                        payload
                    )
                )

                # Eventi non-message:
                # li consideriamo ricevuti correttamente.
                if not message_data:

                    print(
                        "Webhook senza messaggio utile."
                    )

                    return Response(
                        "OK",
                        status=200
                    )

                return await process_instagram_message(
                    self,
                    message_data
                )

            # =================================================
            # 🚫 ALTRI POST
            # =================================================
            return Response(
                "Not Found",
                status=404
            )

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
```
