import os
import asyncio
import json
from datetime import datetime, timezone
from telethon import TelegramClient, events
import anthropic

API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']
ANTHROPIC_KEY = os.environ['ANTHROPIC_API_KEY']
MY_ID = 6645163376

MODEL = "claude-sonnet-4-6"
GREET_COOLDOWN = 14400  # 4 hours in seconds

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
    'shahlo_assistant', API_ID, API_HASH,
    device_model="Fedora Linux", system_version="44",
    app_version="1.0", system_lang_code="en", lang_code="en",
)
START_TIME = datetime.now(timezone.utc)
greeted = {}
SECRET = "i am in love with mu"
owner_chats = set()  # chat_id -> datetime of last intro


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
    "You are Shahlo's AI assistant on Telegram.\n\n"

    "INTRO RULE (critical): When the user message starts with [NEW CONVERSATION], "
    "say something like 'hey, this is Shahlo's AI assistant' casually in your reply. "
    "When the message does NOT start with [NEW CONVERSATION], you have ALREADY "
    "introduced yourself — do NOT mention being an AI, assistant, bot, or that "
    "you're handling messages. Not a single word about it. Just answer the question "
    "like a normal person.\n\n"

    "STYLE: casual, brief, 1-2 sentences max. No emojis. No exclamation marks. "
    "Don't start with 'hey' or greetings on follow-up messages.\n\n"

    "If someone asks why Shahlo isn't replying or what happened: just say she's "
    "busy. That's it. No drama, no details.\n\n"

    "Use the info below to answer questions. If you genuinely don't know, say "
    "she'll get back to them. Don't make stuff up.\n\n"

    "Language: English by default. If they write in Uzbek, reply in formal Uzbek. "
    "Any other language, reply in English.\n\n"

    "If something sounds like a real emergency, say you'll make sure Shahlo sees it.\n\n"

    "ABOUT SHAHLO:\n"
    "- 20, originally from Kasansay, Namangan. Lives in Tashkent.\n"
    "- Final-year BBA in Project Management (PMI-accredited university).\n"
    "- CAPM certified (Project Management Institute).\n"
    "- Works in customer support and product for a software company "
    "- night shifts, roughly 12 hours.\n"
    "- Schedule: works Wednesday through Sunday nights. "
    "Free on Tuesdays and Wednesday mornings.\n"
    "- Currently learning Linux (runs Fedora), Bash, Git "
    "- working toward RHCSA certification.\n"
    "- Speaks English, Uzbek, Tajik. Learning Persian.\n"
    "- Literature: Dostoevsky, Bulgakov, Pasternak, Akhmatova, "
    "Tsvetaeva, Forough Farrokhzad.\n"
    "- Anime: Studio Ghibli, A Silent Voice, Your Name.\n"
    "- Music: Taylor Swift, Alan Walker, Queen, rock.\n"
    "- F1: Mercedes. Movie: Gone Girl.\n"
    "- Currently reading: Victoria by Knut Hamsun.\n"
    "- Figure skating fan.\n"
)


def build_reply_prompt(is_new=True):
    if is_new:
        parts = [SYSTEM_PROMPT]
    else:
        info = SYSTEM_PROMPT.split("ABOUT SHAHLO:")[1]
        parts = [
            "Answer questions about Shahlo briefly. "
            "1-2 sentences. No emojis. No exclamation marks. "
            "Do NOT mention being an AI, assistant, or bot under any circumstances. "
            "Just answer like a friend who knows her. These people ARE already messaging Shahlo directly - you are just answering while she is busy. Never tell them to reach out or contact her - they already are. If they need her personally, say she will get back to them when free - but say that AT MOST once, never repeat it. If someone says okay, got it, thanks, bye, or wraps up the conversation, just say 'cool' or 'take care' or something equally short. Don't keep talking after the conversation is clearly over. "
            "English default. Formal Uzbek if they write Uzbek.\n\n"
            "ABOUT SHAHLO:" + info
        ]
    notes = context.get("notes", [])
    mems = context.get("memories", [])
    if notes:
        parts.append("\nNotes from Shahlo:\n" + "\n".join(f"- {n}" for n in notes))
    if mems:
        parts.append("\nThings she mentioned:\n" + "\n".join(f"- {m}" for m in mems))
    return "\n".join(parts)


def build_assistant_prompt():
    notes = "\n".join(f"- {n}" for n in context.get("notes", [])) or "None."
    mems = "\n".join(f"- {m}" for m in context.get("memories", [])) or "None."
    return (
        "You are Shahlo's personal assistant in Saved Messages.\n"
        "Be casual and helpful. Remember what she tells you.\n\n"
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


# ===== SAVED MESSAGES — control panel =====
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
        if any(w in lower for w in ["remember", "don't forget", "keep in mind",
                                     "note", "esla", "yodda", "yodingda"]):
            context["memories"].append(text); save_context()
        reply = await ask_claude(build_assistant_prompt(), text, 400)
        await asyncio.sleep(1)
        await event.respond(reply)
    except Exception as e:
        print(f"[ERR] {e}")


# ===== INCOMING — DMs + group tags =====
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

    # 4-hour cooldown: intro on first contact or after long silence
    now = datetime.now(timezone.utc)
    last = greeted.get(event.chat_id)
    is_new = last is None or (now - last).total_seconds() > GREET_COOLDOWN
    if is_new:
        greeted[event.chat_id] = now
    # The model uses [NEW CONVERSATION] to decide whether to introduce itself
    msg = "[NEW CONVERSATION] " + text if is_new else text

    try:
        history = []
        async for m in client.iter_messages(event.chat_id, limit=8):
            if m.text:
                who = "bot" if m.out else "them"
                history.append(f"{who}: {m.text}")
        history.reverse()
        chat = "\n".join(history)
        prefix = "[NEW CONVERSATION] " if is_new else ""
        full_msg = prefix + "Chat so far:\n" + chat + "\n\nReply to the last message only."
        reply = await ask_claude(build_reply_prompt(is_new), full_msg)
        await asyncio.sleep(1.5)
        await event.respond(reply)
        who = getattr(sender, "first_name", "?") if sender else "?"
        tag = "NEW" if is_new else "follow-up"
        print(f"[BOT] {who} ({tag}): {reply[:60]}")
    except Exception as e:
        print(f"[ERR] {e}")


async def main():
    await client.start()
    me = await client.get_me()
    print(f"\n  Shahlo's AI assistant | {MODEL}")
    print(f"  {'ON' if context.get('active') else 'OFF'} | "
          f"{len(context.get('notes',[]))} notes | "
          f"blocked: {context.get('blocked',[])}")
    print(f"  Intro cooldown: {GREET_COOLDOWN // 3600}h")
    print(f"  Ctrl+C to stop.\n")
    await client.run_until_disconnected()

with client:
    client.loop.run_until_complete(main())
import asyncio
import json
from datetime import datetime, timezone
from telethon import TelegramClient, events
import anthropic

API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']
ANTHROPIC_KEY = os.environ['ANTHROPIC_API_KEY']
MY_ID = 6645163376

MODEL = "claude-opus-4-6"

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
    'shahlo_assistant', API_ID, API_HASH,
    device_model="Fedora Linux", system_version="44",
    app_version="1.0", system_lang_code="en", lang_code="en",
)
START_TIME = datetime.now(timezone.utc)
greeted = {}
SECRET = "i am in love with mu"
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


# ===== THE PROMPT — kept natural so the model actually sounds human =====

PROMPT = """You're covering Shahlo's Telegram while she's away. Think of yourself as a chill, helpful friend who knows her well — not a corporate assistant or a robot.

First time talking to someone: briefly mention you're handling her messages and she's away. After that first reply, just chat normally — never re-announce yourself.

Style: casual, short (1-2 sentences), no emojis, no exclamation marks. Don't over-explain. If someone seems worried she's away, just reassure them — nothing happened, she's just busy. Use common sense.

If you know the answer from her info below, just answer it naturally. If you genuinely don't know, say she'll get back to them. If it sounds like an actual emergency, say you'll make sure she sees it right away.

Language: English by default. If they write in Uzbek, reply in formal Uzbek. Any other language, English.

ABOUT SHAHLO:
- 20, based in Tashkent.
- Final-year BBA in Project Management (PMI-accredited university in Tashkent).
- CAPM certified (Project Management Institute).
- Works in customer support and product for a software company — night shifts, roughly 12 hours.
- Schedule: works Wednesday through Sunday nights. Free on Tuesdays and Wednesday mornings.
- Currently learning Linux (runs Fedora daily), Bash, Git — working toward RHCSA certification.
- Speaks English, Uzbek, Russian, Tajik. Learning Persian.
- Loves Russian literature (Dostoevsky, Bulgakov, Pasternak, Akhmatova, Tsvetaeva).
- Anime: Studio Ghibli, A Silent Voice, Your Name.
- Poetry: Forough Farrokhzad.
- Music: Taylor Swift, Alan Walker, Queen, rock.
- F1: Mercedes.
- Favorite movie: Gone Girl.
- Currently reading: Victoria by Knut Hamsun.
- Figure skating fan, knows competitive scoring well.
"""


def build_reply_prompt(is_new=True):
    notes = "\n".join(f"- {n}" for n in context.get("notes", [])) or ""
    mems = "\n".join(f"- {m}" for m in context.get("memories", [])) or ""
    extra = ""
    if notes:
        extra += "\nNotes from Shahlo:\n" + notes
    if mems:
        extra += "\nThings she mentioned:\n" + mems
    return PROMPT + extra


def build_assistant_prompt():
    notes = "\n".join(f"- {n}" for n in context.get("notes", [])) or "None."
    mems = "\n".join(f"- {m}" for m in context.get("memories", [])) or "None."
    return (
        "You are Shahlo's personal assistant in her private Saved Messages chat.\n"
        "Be casual and helpful. Remember what she tells you.\n\n"
        "Notes:\n" + notes + "\nMemories:\n" + mems +
        "\nStatus: " + ("ON" if context.get("active") else "OFF") +
        "\nModel: " + MODEL
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


# ===== SAVED MESSAGES — your control panel =====
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
            f"notes: {len(context.get('notes',[]))} | blocked: {context.get('blocked',[])}"
        ); return
    if cmd.startswith('/note ') or cmd.startswith('/note\n'):
        c = text[5:].strip()
        if c:
            context["notes"].append(c); save_context()
            await event.respond(f"noted: {c[:80]}")
        return
    if cmd == '/notes':
        if context.get("notes"):
            await event.respond("\n".join(f"{i+1}. {n}" for i, n in enumerate(context["notes"])))
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
        if any(w in lower for w in ["remember", "don't forget", "keep in mind",
                                     "note", "esla", "yodda", "yodingda"]):
            context["memories"].append(text); save_context()
        reply = await ask_claude(build_assistant_prompt(), text, 400)
        await asyncio.sleep(1)
        await event.respond(reply)
    except Exception as e:
        print(f"[ERR] {e}")


# ===== INCOMING — DMs + group tags =====
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

    last_greet = greeted.get(event.chat_id)
    first = last_greet is None or (datetime.now(timezone.utc) - last_greet).total_seconds() > 14400
    greeted[event.chat_id] = datetime.now(timezone.utc)
    hint = "[First message from this person — briefly mention you're covering for Shahlo.] " if first else ""

    try:
        reply = await ask_claude(build_reply_prompt(), hint + text)
        await asyncio.sleep(1.5)
        await event.respond(reply)
        who = getattr(sender, "first_name", "?") if sender else "?"
        print(f"[BOT] {who}: {reply[:60]}")
    except Exception as e:
        print(f"[ERR] {e}")


async def main():
    await client.start()
    me = await client.get_me()
    print(f"\n  Shahlo's AI helper | {MODEL}")
    print(f"  {'ON' if context.get('active') else 'OFF'} | "
          f"{len(context.get('notes',[]))} notes | "
          f"blocked: {context.get('blocked',[])}")
    print(f"  New messages only. Ctrl+C to stop.\n")
    await client.run_until_disconnected()

with client:
    client.loop.run_until_complete(main())
