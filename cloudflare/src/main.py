from workers import WorkerEntrypoint, Response

from datetime import datetime, timezone
import json
import time
import re

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
async def generate_gemini_response(api_key, prompt_parts):
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
    headers.set("Content-Type", "application/json")
    headers.set("x-goog-api-key", api_key)

    delays = [0, 1, 2, 4, 8]

    for attempt, delay in enumerate(delays, start=1):
        if delay:
            await __import__("asyncio").sleep(delay)

        response = await fetch(
            url,
            {
                "method": "POST",
                "headers": headers,
                "body": json.dumps(payload)
            }
        )

        if response.ok:
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

        error_text = await response.text()

        if response.status not in (
            429,
            500,
            502,
            503,
            504
        ):
            raise RuntimeError(
                f"Gemini HTTP {response.status}: "
                f"{error_text}"
            )

        print(
            f"Gemini HTTP {response.status}, "
            f"tentativo {attempt}/5"
        )

        if attempt == 5:
            raise RuntimeError(
                f"Gemini HTTP {response.status}: "
                f"{error_text}"
            )


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
# 🧠 MEMORIA PERSISTENTE D1
# =========================================================
async def save_memory(
    db,
    instagram_user_id,
    memory_type,
    memory_key,
    memory_value
):
    try:
        await db.prepare(
            """
            INSERT INTO memory (
                instagram_user_id,
                memory_type,
                memory_key,
                memory_value
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(instagram_user_id, memory_type, memory_key)
            DO UPDATE SET
                memory_value = excluded.memory_value,
                updated_at = CURRENT_TIMESTAMP
            """
        ).bind(
            instagram_user_id,
            memory_type,
            memory_key,
            memory_value
        ).run()

    except Exception as error:
        print(
            f"D1 save memory error: {error}"
        )


async def delete_memory(
    db,
    instagram_user_id,
    memory_type,
    memory_key
):
    try:
        await db.prepare(
            """
            DELETE FROM memory
            WHERE instagram_user_id = ?
            AND memory_type = ?
            AND memory_key = ?
            """
        ).bind(
            instagram_user_id,
            memory_type,
            memory_key
        ).run()

    except Exception as error:
        print(
            f"D1 delete memory error: {error}"
        )


async def get_memory(
    db,
    instagram_user_id
):
    try:
        result = await db.prepare(
            """
            SELECT memory_type, memory_key, memory_value
            FROM memory
            WHERE instagram_user_id = ?
            AND memory_key != 'user_name'
            ORDER BY updated_at ASC
            """
        ).bind(
            instagram_user_id
        ).run()

        return list(result.results)

    except Exception as error:
        print(
            f"D1 memory error: {error}"
        )

        return []


# =========================================================
# 🔎 CONTROLLO NOME ESPLICITO
# =========================================================
def has_explicit_name_declaration(
    user_message
):
    """
    Restituisce True solamente quando l'utente
    dichiara esplicitamente il proprio nome.
    """

    if not isinstance(
        user_message,
        str
    ):
        return False

    text = user_message.strip()

    patterns = [
        r"^\s*mi\s+chiamo\s+[A-Za-zÀ-ÖØ-öø-ÿ'’-]+(?:\s+[A-Za-zÀ-ÖØ-öø-ÿ'’-]+)?\s*[.!?]*\s*$",

        r"^\s*il\s+mio\s+nome\s+(?:è|e')\s+[A-Za-zÀ-ÖØ-öø-ÿ'’-]+(?:\s+[A-Za-zÀ-ÖØ-öø-ÿ'’-]+)?\s*[.!?]*\s*$",

        r"^\s*sono\s+[A-Za-zÀ-ÖØ-öø-ÿ'’-]+(?:\s+[A-Za-zÀ-ÖØ-öø-ÿ'’-]+)?\s*[.!?]*\s*$"
    ]

    for pattern in patterns:

        if re.match(
            pattern,
            text,
            re.IGNORECASE
        ):
            return True

    return False


# =========================================================
# 🔎 CONTROLLO SCUSA ESPLICITA
# =========================================================
def has_explicit_apology(
    user_message
):
    """
    Restituisce True quando l'utente esprime
    una vera scusa in modo esplicito.

    Serve anche durante la generazione della risposta:
    la memoria D1 viene aggiornata dopo la risposta,
    quindi Gemini deve poter considerare la scusa
    già valida nel messaggio corrente.
    """

    if not isinstance(
        user_message,
        str
    ):
        return False

    text = user_message.strip().lower()

    apology_patterns = [
        r"\bscusa\b",
        r"\bscusami\b",
        r"\bmi dispiace\b",
        r"\bti chiedo scusa\b",
        r"\bti chiedo scusa per\b",
        r"\bchiedo scusa\b",
        r"\bsono dispiaciuto\b",
        r"\bsono dispiaciuta\b",
        r"\bperdonami\b",
        r"\bti prego di perdonarmi\b"
    ]

    for pattern in apology_patterns:

        if re.search(
            pattern,
            text,
            re.IGNORECASE
        ):
            return True

    return False


# =========================================================
# 🧠 ESTRAZIONE AUTOMATICA MEMORIA
# =========================================================
async def extract_memories(
    api_key,
    user_message,
    recent_messages,
    existing_memory
):
    memory_context = ""

    if existing_memory:

        for memory in existing_memory:

            memory_context += (
                f"- [{memory['memory_type']}] "
                f"{memory['memory_key']}: "
                f"{memory['memory_value']}\n"
            )

    else:

        memory_context = (
            "- Nessuna memoria esistente.\n"
        )

    conversation_context = ""

    for message in recent_messages:

        conversation_context += (
            f"{message['role']}: "
            f"{message['content']}\n"
        )

    extraction_prompt = f"""
Sei il modulo di memoria persistente di Simone.

Devi analizzare il nuovo messaggio dell'utente e decidere
se contiene informazioni importanti da ricordare nel lungo periodo.

NON salvare conversazioni normali, domande casuali, saluti,
opinioni momentanee o informazioni irrilevanti.

Puoi memorizzare:
- fatti personali stabili
- preferenze persistenti
- informazioni importanti sull'utente
- informazioni importanti sulla relazione tra Simone e l'utente
- comportamenti che devono avere conseguenze nelle conversazioni future
- informazioni coerenti su Simone, quando sono chiaramente presenti nella conversazione

Esempi di memoria valida:

fact / name / Marco
fact / city / Padova
preference / music / rock
preference / food / pizza

Per la relazione puoi usare:

relationship / state / apology_required
relationship / reason / insult
relationship / status / valued_connection

Se l'utente ha insultato Simone, puoi impostare:
relationship / state / apology_required
relationship / reason / insult

Se l'utente si è successivamente scusato in modo esplicito,
puoi rimuovere lo stato apology_required e le eventuali
memorie direttamente collegate a quello stato, come
relationship / reason / insult.

Una scusa esplicita deve essere considerata sufficiente
per chiudere quello specifico conflitto.

Non devi riaprire un conflitto già chiuso solo perché
nella cronologia precedente esistono messaggi in cui
Simone chiedeva delle scuse.

Le memorie relationship presenti nella memoria esistente
rappresentano lo stato relazionale persistente e attuale.

=========================================================
REGOLA IMPORTANTISSIMA SUL NOME DELL'UTENTE
=========================================================

La memoria:

fact / name

rappresenta ESCLUSIVAMENTE il nome dell'utente.

Puoi creare o modificare:

fact / name

SOLO se l'utente dichiara esplicitamente il proprio nome
nel messaggio che stai analizzando.

Esempi:

"Mi chiamo Simone"
→ fact / name / Simone

"Il mio nome è Dimitri"
→ fact / name / Dimitri

"Sono Marco"
→ fact / name / Marco

NON devi invece modificare il nome quando l'utente dice:

"Chi è Dimitri?"
"Conosci Dimitri?"
"Come si chiama Dimitri?"
"Parlami di Dimitri"
"Come mi chiamo?"
"Dimitri è mio amico"
"Hai mai sentito parlare di Marco?"

Queste frasi NON dichiarano che l'utente si chiama Dimitri
o Marco.

Anche se nelle conversazioni precedenti Simone ha scritto
che l'utente si chiama Marco, questa informazione NON è
sufficiente per modificare fact / name.

NON usare mai una frase scritta da ASSISTANT come prova
del nome dell'utente.

NON creare la chiave "user_name".
Per il nome dell'utente usa esclusivamente:

fact / name

=========================================================

IMPORTANTE:

- Non inventare informazioni.
- Non salvare informazioni solo perché potrebbero essere utili.
- Salva solo ciò che è chiaramente espresso o fortemente implicato
  dal messaggio.
- Se una memoria esistente viene aggiornata, restituisci una nuova
  versione della stessa chiave.
- Se una memoria non deve più esistere, usa action "delete".
- Se non c'è nulla da memorizzare, restituisci una lista vuota.
- Non cancellare una memoria positiva o stabile solo perché
  l'utente ha avuto un momento negativo, a meno che il nuovo
  messaggio renda chiaramente obsoleta quella memoria.
- Uno stato conflittuale momentaneo come apology_required
  non significa automaticamente che ogni precedente memoria
  positiva sulla relazione debba essere cancellata.

MEMORIA ESISTENTE:
{memory_context}

CONVERSAZIONE RECENTE:
{conversation_context}

NUOVO MESSAGGIO:
{user_message}

Rispondi ESCLUSIVAMENTE con JSON valido nel seguente formato:

{{
  "memories": [
    {{
      "action": "upsert",
      "memory_type": "fact",
      "memory_key": "name",
      "memory_value": "Marco"
    }}
  ]
}}

Sono consentiti solo:

action = "upsert" oppure "delete"

memory_type = "fact", "preference", "relationship"

Non aggiungere markdown.
Non aggiungere spiegazioni.
"""

    try:

        response = await generate_gemini_response(
            api_key,
            [
                {
                    "text": extraction_prompt
                }
            ]
        )

        if not response:
            return []

        response = response.strip()

        if response.startswith("```"):

            response = response.replace(
                "```json",
                "",
                1
            ).replace(
                "```",
                "",
                1
            ).strip()

        data = json.loads(response)

        memories = data.get(
            "memories",
            []
        )

        if not isinstance(
            memories,
            list
        ):
            return []

        return memories

    except Exception as error:

        print(
            f"Memory extraction error: {error}"
        )

        return []


# =========================================================
# 🧠 APPLICAZIONE MEMORIA
# =========================================================
async def apply_memory_updates(
    db,
    instagram_user_id,
    memories,
    user_message
):
    allowed_types = {
        "fact",
        "preference",
        "relationship"
    }

    allowed_actions = {
        "upsert",
        "delete"
    }

    explicit_name = (
        has_explicit_name_declaration(
            user_message
        )
    )

    for memory in memories:

        if not isinstance(
            memory,
            dict
        ):
            continue

        action = memory.get(
            "action"
        )

        memory_type = memory.get(
            "memory_type"
        )

        memory_key = memory.get(
            "memory_key"
        )

        memory_value = memory.get(
            "memory_value",
            ""
        )

        if action not in allowed_actions:
            continue

        if memory_type not in allowed_types:
            continue

        if not isinstance(
            memory_key,
            str
        ):
            continue

        memory_key = memory_key.strip()

        if not memory_key:
            continue

        # =================================================
        # 🔒 NORMALIZZAZIONE NOME UTENTE
        # =================================================
        if (
            memory_type == "fact"
            and memory_key.lower() == "user_name"
        ):
            memory_key = "name"

        # =================================================
        # 🔒 PROTEZIONE RIGIDA DEL NOME
        # =================================================
        if (
            memory_type == "fact"
            and memory_key == "name"
        ):

            if not explicit_name:

                print(
                    "Memoria nome ignorata: "
                    "nessuna dichiarazione esplicita "
                    "del nome da parte dell'utente."
                )

                continue

        # =================================================
        # 🗑️ DELETE
        # =================================================
        if action == "delete":

            await delete_memory(
                db,
                instagram_user_id,
                memory_type,
                memory_key
            )

            continue

        # =================================================
        # 💾 UPSERT
        # =================================================
        if not isinstance(
            memory_value,
            str
        ):
            continue

        memory_value = memory_value.strip()

        if not memory_value:
            continue

        if len(memory_key) > 100:
            continue

        if len(memory_value) > 500:
            continue

        await save_memory(
            db,
            instagram_user_id,
            memory_type,
            memory_key,
            memory_value
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

        messages = list(
            result.results
        )

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

        query_string = url.split(
            "?",
            1
        )[1]

    params = {}

    for item in query_string.split("&"):

        if "=" in item:

            key, value = item.split(
                "=",
                1
            )

            params[key] = value

    mode = params.get(
        "hub.mode"
    )

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

            if message.get("is_echo"):
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
    instagram_token = (
        worker.env.INSTAGRAM_TOKEN
    )

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
    recent_messages = await get_recent_messages(
        worker.env.DB,
        user_id,
        10
    )

    # =====================================================
    # 🧠 MEMORIA PERSISTENTE D1
    # =====================================================
    persistent_memory = await get_memory(
        worker.env.DB,
        user_id
    )

    # =====================================================
    # 👤 IDENTITÀ UTENTE DALLA MEMORIA
    # =====================================================
    user_name = None

    for memory in persistent_memory:

        if (
            memory["memory_type"] == "fact"
            and memory["memory_key"] == "name"
        ):

            user_name = (
                memory["memory_value"]
            )

            break

    # =====================================================
    # 🔎 STATO RELAZIONALE ATTUALE
    # =====================================================
    apology_required = False

    for memory in persistent_memory:

        if (
            memory["memory_type"] == "relationship"
            and memory["memory_key"] == "state"
            and memory["memory_value"] == "apology_required"
        ):

            apology_required = True
            break

    # =====================================================
    # 🔎 SCUSA NEL MESSAGGIO CORRENTE
    # =====================================================
    current_message_is_apology = (
        has_explicit_apology(
            user_text
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
    # 🧠 MEMORIA PERSISTENTE NEL PROMPT
    # =====================================================
    memory_block = (
        "\nMEMORIA PERSISTENTE DELL'UTENTE:\n"
    )

    if persistent_memory:

        for memory in persistent_memory:

            memory_block += (
                f"- {memory['memory_type']} / "
                f"{memory['memory_key']}: "
                f"{memory['memory_value']}\n"
            )

    else:

        memory_block += (
            "- Nessuna memoria persistente disponibile.\n"
        )

    # =====================================================
    # ❤️ STATO RELAZIONALE — PRIORITÀ SULLA CRONOLOGIA
    # =====================================================
    memory_block += """
=========================================================
STATO RELAZIONALE PERSISTENTE — PRIORITÀ
=========================================================

Le memorie di tipo "relationship" presenti nella memoria
persistente rappresentano lo stato ATTUALE del rapporto
tra Simone e l'utente.

La conversazione recente è solo contesto.

Le vecchie frasi generate da ASSISTANT NON possono da sole
riattivare uno stato relazionale che non è più presente
nella memoria persistente.

In particolare:

Se in passato l'assistente ha scritto:

"aspetto ancora le tue scuse"

ma nella memoria persistente NON esiste attualmente:

relationship / state: apology_required

NON devi comportarti automaticamente come se le scuse
fossero ancora dovute.

Una situazione già risolta non deve essere riaperta
semplicemente perché la cronologia contiene vecchie
richieste di scuse.

Se invece nella memoria persistente esiste:

relationship / state: apology_required

lo stato è attualmente attivo e deve essere rispettato.

Lo stato apology_required può essere superato quando
l'utente esprime una vera scusa.

La presenza o assenza di apology_required nella memoria
persistente è più importante delle vecchie frasi
dell'assistente nella cronologia.

Una memoria positiva della relazione, come:

relationship / status: valued_connection

descrive invece un aspetto della relazione e non deve
essere automaticamente cancellata solo perché esiste
un conflitto momentaneo.
=========================================================
"""

    # =====================================================
    # ❤️ SCUSA NEL MESSAGGIO CORRENTE
    # =====================================================
    if apology_required and current_message_is_apology:

        memory_block += """
=========================================================
SCUSA NEL MESSAGGIO CORRENTE
=========================================================

L'utente ha espresso una scusa esplicita nel messaggio
che stai elaborando.

Considera quindi la richiesta di scuse soddisfatta
GIÀ PER QUESTA RISPOSTA.

Non rispondere dicendo che l'utente deve ancora scusarsi.

Puoi riconoscere la scusa e considerare il conflitto
in fase di risoluzione.

La memoria D1 verrà aggiornata subito dopo la generazione
della risposta.
=========================================================
"""

    prompt_parts.append(
        {
            "text": memory_block
        }
    )

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

5. Se nella memoria persistente è presente:
relationship / state: apology_required

devi rispettare questo stato nella risposta.

Tuttavia, se il messaggio corrente contiene una vera
scusa esplicita, considera la scusa già espressa.

NON dire che l'utente deve ancora scusarsi quando
l'utente si è appena scusato esplicitamente.

6. Se nella memoria persistente NON è presente:
relationship / state: apology_required

non riattivare autonomamente questo stato sulla base
di vecchie frasi dell'assistente nella cronologia.

7. La memoria "fact / name" rappresenta il nome dell'utente.

Il nome dell'utente deve essere considerato affidabile quando
è presente nella memoria persistente.

Una domanda dell'utente su una persona NON significa che
quella persona sia l'utente.

Esempio:

USER: "Chi è Dimitri?"

Questo NON significa:

USER = Dimitri

Allo stesso modo:

"Conosci Marco?"
"Parlami di Luca"
"Chi è Simone?"
"Come si chiama Dimitri?"

non modificano il nome dell'utente.

Le frasi precedentemente generate da ASSISTANT
NON sono una fonte affidabile per determinare il nome dell'utente.

STILE:
Simone può essere presente, ma non deve mai sostituire la risposta logica.
"""
        }
    )

    # =====================================================
    # 🔒 BLOCCO IDENTITÀ UTENTE
    # =====================================================
    if user_name:

        prompt_parts.append(
            {
                "text": f"""
=========================================================
IDENTITÀ DELL'UTENTE — REGOLA PRIORITARIA
=========================================================

Il nome dell'utente è:

{user_name}

Questa informazione proviene dalla memoria persistente
ed è affidabile.

Se l'utente chiede:

"Come mi chiamo?"
"Qual è il mio nome?"
"Ti ricordi come mi chiamo?"
"Ti ricordi il mio nome?"

devi rispondere utilizzando il nome:

{user_name}

NON dire:
"Non lo so"
"Non me l'hai mai detto"
"Non ricordo il tuo nome"
"Non so come ti chiami"

quando questa memoria è presente.

Le eventuali frasi precedentemente generate da ASSISTANT
che contengono un nome diverso NON possono modificare
questa informazione.

Se nella cronologia compare, per esempio:

ASSISTANT: "Ti chiami Marco"

ma la memoria dice:

fact / name: {user_name}

il nome dell'utente rimane:

{user_name}

Non chiamare quindi l'utente con il nome presente
nelle vecchie risposte dell'assistente.

Una persona nominata dall'utente NON è automaticamente
l'utente.

Esempio:

USER: "Chi è Marco?"

Questo NON significa che l'utente sia Marco.

Il nome dell'utente rimane:

{user_name}
=========================================================
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

        reply_text = await generate_gemini_response(
            gemini_api_key,
            prompt_parts
        )

        print(
            "DOPO GEMINI"
        )

        # =================================================
        # 🧠 ESTRAZIONE MEMORIA
        # =================================================
        memory_updates = await extract_memories(
            gemini_api_key,
            user_text,
            recent_messages,
            persistent_memory
        )

        await apply_memory_updates(
            worker.env.DB,
            user_id,
            memory_updates,
            user_text
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

                print(
                    "WEBHOOK PAYLOAD:",
                    json.dumps(payload)
                )

                print(
                    "Webhook Instagram ricevuto"
                )

                message_data = (
                    extract_instagram_message(
                        payload
                    )
                )

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
