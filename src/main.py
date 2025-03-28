def main(context):
    # Verifica webhook Meta
    mode = context.req.query.get("hub.mode")
    challenge = context.req.query.get("hub.challenge")
    verify_token = context.req.query.get("hub.verify_token")

    if mode == "subscribe" and verify_token == os.getenv("VERIFY_TOKEN"):
        return context.res.text(challenge)

    processed = load_processed_ids()

    instagram_data = get_instagram_messages()
    if instagram_data and "data" in instagram_data:
        for conv in instagram_data["data"]:
            if "messages" in conv:
                for msg in conv["messages"]["data"]:
                    msg_id = msg.get("id")
                    sender_id = msg.get("from", {}).get("id")
                    text = msg.get("message", "")

                    print(f"\n[DEBUG] ID messaggio: {msg_id}")
                    print(f"[DEBUG] Mittente ID: {sender_id}")
                    print(f"[DEBUG] Contenuto: {text}")

                    if msg_id in processed["instagram"]:
                        print("[DEBUG] Già risposto. Skip.")
                        continue

                    if sender_id == MY_INSTAGRAM_ID:
                        print("[DEBUG] Messaggio inviato da me. Ignorato.")
                        processed["instagram"].append(msg_id)
                        continue

                    if text:
                        reply = send_message_to_openai(text)

                        # Rispondi solo se effettivamente ricevuto qualcosa da OpenAI
                        if reply:
                            send_instagram_reply(sender_id, reply)
                        else:
                            print("[DEBUG] Nessuna risposta valida da OpenAI.")

                    # In ogni caso, segna il messaggio come gestito per evitare loop
                    processed["instagram"].append(msg_id)

    save_processed_ids(processed)
    return context.res.text("Esecuzione completata.")
