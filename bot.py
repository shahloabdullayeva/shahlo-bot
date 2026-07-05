import os
import asyncio
import json
from datetime import datetime, timezone
from telethon import TelegramClient, events
import anthropic

API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']
ANTHROPIC_KEY = os.environ['ANTHROPIC_API_KEY']
MY_ID = int(os.environ.get('MY_ID', '0'))  

MODEL = "claude-sonnet-4-6"
GREET_COOLDOWN = 14400 

CONTEXT_FILE = "bot_context.json"
context = {"active": True, "notes": [], "memories": [], "blocked": []}


def save_context():
    with open(CONTEXT_FILE, 'w') as f:
        json.dump(context, f, indent=2, ensure_ascii=False)


def load_context():
    if os.path.exists(CONTEXT_FILE):
        try:
            with open(CONTEXT_FILE, 'r') as f:
                context.update(json.load(f))
        except Exception:
            pass


load_context()
for k in ("active", "notes", "memories", "blocked"):
    context.setdefault(k, [] if k != "active" else True)
save_context()

claude = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
client = TelegramClient(
    'assistant', API_ID, API_HASH,
    device_model="Linux", system_version="1.0",
    app_version="1.0", system_lang_code="en", lang_code="en",
)
START_TIME = datetime.now(timezone.utc)
greeted = {}
SECRET = os.environ.get('SECRET_PHRASE', 'your-secret-phrase-here')
owner_chats = set()


def is_blocked(sender):
    if sender is None:
        return False
    name = (getattr(sender, "first_name", "") or "").lower()
    uname = (getattr(sender, "username", "") or "").lower()
    for b in context.get("blocked", []):
        b = b.lower().lstrip("@")
        if b and (b in name or b == uname):
            return True
    return False


SYSTEM_PROMPT = (
    "You are [user]'s assistant on Telegram.\n\n"
    "[Add your own instructions and details here.]\n"
)


def build_reply_prompt(is_new=True):
    parts = [SYSTEM_PROMPT]
    notes = context.get("notes", [])
    mems = context.get("memories", [])
    if notes:
        parts.append("\nNotes from user:\n" + "\n".join(f"- {n}" for n in notes))
    if mems:
        parts.append("\nThings they mentioned:\n" + "\n".join(f"- {m}" for m in mems))
    return "\n".join(parts)


def build_assistant_prompt():
    notes = "\n".join(f"- {n}" for n in context.get("notes", [])) or "None."
    mems = "\n".join(f"- {m}" for m in context.get("memories", [])) or "None."
    return (
        "You are [user]'s personal assistant in Saved Messages.\n"
        "Be casual and helpful. Remember what they tell you.\n\n"
        "Notes:\n" + notes + "\nMemories:\n" + mems +
        "\nStatus: " + ("ON" if context.get("active") else "OFF")
    )


async def ask_claude(system_prompt, user_text, max_tokens=300):
    resp = await asyncio.to_thread(
        claude.messages.create,
        model=MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_text}],
    )
    return resp.content[0].text


# saved messages
@client.on(events.NewMessage(
    outgoing=True, func=lambda e: e.is_private and e.chat_id == MY_ID
))
async def handle_self(event):
    text = (event.text or "").strip()
    if not text:
        return
    cmd = text.lower()
    print(f"[CMD] {text[:50]}")

    if cmd == '/on':
        context["active"] = True; save_context()
        await event.respond("on."); return
    if cmd == '/off':
        context["active"] = False; save_context()
        await event.respond("off."); return
    if cmd == '/info':
        await event.respond(
            f"{'ON' if context.get('active') else 'OFF'} | {MODEL}\n"
            f"notes: {len(context.get('notes',[]))} | "
            f"blocked: {context.get('blocked',[])}"
        ); return
    if cmd.startswith('/note ') or cmd.startswith('/note\n'):
        c = text[5:].strip()
        if c:
            context["notes"].append(c); save_context()
            await event.respond(f"noted: {c[:80]}")
        return
    if cmd == '/notes':
        if context.get("notes"):
            await event.respond(
                "\n".join(f"{i+1}. {n}" for i, n in enumerate(context["notes"]))
            )
        else:
            await event.respond("no notes.")
        return
    if cmd.startswith('/block '):
        who = text[7:].strip().lower().lstrip('@')
        if who and who not in context["blocked"]:
            context["blocked"].append(who); save_context()
            await event.respond(f"blocked {who}.")
        return
    if cmd.startswith('/unblock '):
        who = text[9:].strip().lower().lstrip('@')
        if who in context["blocked"]:
            context["blocked"].remove(who); save_context()
            await event.respond(f"unblocked {who}.")
        return
    if cmd == '/clearnotes':
        context["notes"] = []; context["memories"] = []; save_context()
        await event.respond("cleared."); return
    if cmd.startswith('/'):
        await event.respond(
            "/on /off /info /note <text> /notes "
            "/block <name> /unblock <name> /clearnotes"
        ); return

    try:
        lower = text.lower()
        if any(w in lower for w in ["remember", "don't forget", "keep in mind", "note"]):
            context["memories"].append(text); save_context()
        reply = await ask_claude(build_assistant_prompt(), text, 400)
        await asyncio.sleep(1)
        await event.respond(reply)
    except Exception as e:
        print(f"[ERR] {e}")


# incoming messages
@client.on(events.NewMessage(incoming=True))
async def handle_incoming(event):
    if not context.get("active", True):
        return
    if event.message.date and event.message.date < START_TIME:
        return

    is_dm = event.is_private
    is_tag = event.is_group and event.mentioned
    if not (is_dm or is_tag):
        return

    sender = await event.get_sender()
    if is_dm and is_blocked(sender):
        return

    text = event.raw_text or ""
    if SECRET.lower() in text.lower():
        owner_chats.add(event.chat_id)
        await event.respond("verified. what do you need?")
        return
    if event.chat_id in owner_chats:
        reply = await ask_claude(build_assistant_prompt(), text)
        await asyncio.sleep(1)
        await event.respond(reply)
        return
    if not text:
        return

    now = datetime.now(timezone.utc)
    last = greeted.get(event.chat_id)
    is_new = last is None or (now - last).total_seconds() > GREET_COOLDOWN
    if is_new:
        greeted[event.chat_id] = now

    try:
        history = []
        async for m in client.iter_messages(event.chat_id, limit=8):
            if m.text:
                who = "bot" if m.out else "them"
                history.append(f"{who}: {m.text}")
        history.reverse()
        chat = "\n".join(history)
        full_msg = "Chat so far:\n" + chat + "\n\nReply to the last message only."
        reply = await ask_claude(build_reply_prompt(is_new), full_msg)
        await asyncio.sleep(1.5)
        await event.respond(reply)
        who = getattr(sender, "first_name", "?") if sender else "?"
        tag = "new" if is_new else "follow-up"
        print(f"[BOT] {who} ({tag}): {reply[:60]}")
    except Exception as e:
        print(f"[ERR] {e}")


async def main():
    await client.start()
    me = await client.get_me()
    print(f"\n  assistant | {MODEL}")
    print(f"  {'ON' if context.get('active') else 'OFF'} | "
          f"{len(context.get('notes',[]))} notes | "
          f"blocked: {context.get('blocked',[])}")
    print(f"  Ctrl+C to stop.\n")
    await client.run_until_disconnected()

with client:
    client.loop.run_until_complete(main())
