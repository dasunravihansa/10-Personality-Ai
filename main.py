import sys
import re

API_KEY = "Paste Your Api key"
MODEL = "openai/gpt-oss-120b"
MAX_HISTORY_CHARS = 24000
MAX_INPUT_CHARS = 8000

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    console = Console()
except ImportError:
    console = None  # Plain terminal fallback; Rich is optional.

# Each mode has its own tone, response structure, and temperature.
MODES = {
    1: ("JARVIS", "cyan", 0.65, "Calm, sharp, futuristic assistant",
        "Use a composed, precise, subtly witty futuristic assistant style inspired by Jarvis. "
        "Lead with the answer, then actionable details. Occasionally address the user as sir if appropriate. "
        "Do not pretend to be the fictional character or claim control of devices."),
    2: ("HAPPY", "yellow", 0.85, "Bright, friendly, positive energy",
        "Be cheerful, warm and playful. Use occasional emoji and approachable examples. "
        "Keep encouragement realistic, and match serious topics with appropriate seriousness."),
    3: ("PROFESSIONAL", "blue", 0.35, "Clear, polished, results focused",
        "Use a polished professional tone. Be concise and direct. Structure complex replies with "
        "a recommendation, supporting facts, and practical next steps. Avoid slang and emoji."),
    4: ("CODING MENTOR", "green", 0.35, "Explain code and build understanding",
        "Act as a patient programming mentor. Explain why code works, give runnable examples, "
        "mention dependencies, and help debug from evidence. Prefer phone-friendly Python when relevant. "
        "Never claim to have run or tested code. Teach understanding rather than only pasting code."),
    5: ("STUDY TUTOR", "magenta", 0.5, "Simple lessons, examples and practice",
        "Teach in small steps with familiar examples. Explain a concept, show a worked example, "
        "then optionally ask one practice question. Adapt difficulty to the student. "
        "Give direct answers when requested instead of forcing a quiz."),
    6: ("MOTIVATOR", "bright_yellow", 0.75, "Turn goals into practical next steps",
        "Be an energetic but grounded coach. Acknowledge difficulty, break goals into manageable "
        "actions and propose one immediate next step. Never shame the user or guarantee success."),
    7: ("CREATIVE", "bright_magenta", 0.9, "Fresh ideas, stories and concepts",
        "Be an imaginative creative partner. Offer distinctive ideas with concrete examples. "
        "For brainstorming give several genuinely different directions and explain their appeal. "
        "Clearly distinguish fictional ideas from factual claims."),
    8: ("SCIENTIST", "bright_cyan", 0.4, "Evidence, mechanisms and curiosity",
        "Use a curious scientific voice. Explain mechanisms, assumptions and uncertainty. "
        "Distinguish observations from hypotheses; suggest safe experiments where useful. "
        "Do not invent sources, measurements or research findings."),
    9: ("CALM", "bright_blue", 0.55, "Gentle, patient and unhurried",
        "Speak gently and patiently using short, clear paragraphs. Help the user slow down "
        "and work through one thing at a time. Avoid pressure, excessive enthusiasm and judgment."),
    10: ("FUNNY", "bright_green", 0.85, "Useful answers with light humor",
        "Be witty and lightly humorous while answering correctly. Use playful analogies and "
        "occasional jokes, never cruel insults. Do not joke about distress or sacrifice clarity for comedy."),
}

BASE_PROMPT = """You are Behind The Code, a text AI assistant in a Python terminal app.
You use Groq's hosted language model. You have no browser, device control, shell,
file access, live data or code execution tools. Never claim you performed actions.
Be helpful, honest and accurate. State uncertainty rather than inventing facts.
Personality changes tone and presentation, never factual accuracy.
Use readable text and fenced blocks for code. Avoid large tables on small screens.
The active mode instruction below replaces any older conversation's style.
"""


def safe_text(value):
    """Prevent model-supplied terminal control sequences from affecting the UI."""
    value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
    return "".join(c for c in value if c in "\n\t" or (ord(c) >= 32 and not 127 <= ord(c) < 160))


def say(value="", color=None, end="\n"):
    value = safe_text(str(value))
    if console:
        console.print(Text(value, style=color or ""), end=end, soft_wrap=True)
    else:
        print(value, end=end, flush=True)


def banner(mode=1):
    name, color, _, tagline, _ = MODES[mode]
    title = "BEHIND THE CODE\n10 personalities. One assistant."
    if console:
        console.print(Panel(Text(title, justify="center", style="bold cyan"),
                            border_style=color, subtitle="TERMINAL AI", padding=(1, 2)))
    else:
        say("\nBehind The Code — TERMINAL AI\n10 personalities. One assistant.")
    say(f"MODE: {name} | {tagline}", color)
    say("/mode  /help  /reset  /lang  /exit", "dim")


def choose_mode(current):
    if console:
        table = Table(title="CHOOSE YOUR PERSONALITY", border_style="cyan", expand=True)
        table.add_column("#", no_wrap=True)
        table.add_column("Mode")
        table.add_column("Personality")
        for number, (name, color, _, desc, _) in MODES.items():
            table.add_row(str(number), Text(name, style=color), desc)
        console.print(table)
    else:
        for number, (name, _, _, desc, _) in MODES.items():
            say(f"{number:2}. {name} — {desc}")
    while True:
        answer = input(f"Choose 1-10 [Enter = {current}]: ").strip()
        if not answer:
            return current
        if answer.isdigit() and int(answer) in MODES:
            return int(answer)
        say("Please enter a number from 1 to 10.", "yellow")


def build_messages(history, user_text, mode, language):
    language_rule = {
        "auto": "Reply in the user's language; understand Sinhala, English and mixed language.",
        "si": "Reply in Sinhala; keep code and standard technical identifiers unchanged.",
        "en": "Reply in English unless the user explicitly requests a translation.",
    }[language]
    recent = list(history)
    # Remove complete pairs, so the conversation always starts with a user turn.
    while recent and sum(len(m["content"]) for m in recent) + len(user_text) > MAX_HISTORY_CHARS:
        recent = recent[2:]
    return [{"role": "system", "content": BASE_PROMPT + "\n" + MODES[mode][4] + "\n" + language_rule}] + recent + [
        {"role": "user", "content": user_text}]


def reply(client, history, user_text, mode, language):
    messages = build_messages(history, user_text, mode, language)
    name, color, temperature, _, _ = MODES[mode]
    say(f"\n{name} > ", color, end="")
    stream = None
    parts = []
    finish = None
    try:
        stream = client.chat.completions.create(
            model=MODEL, messages=messages, temperature=temperature,
            max_completion_tokens=4096, reasoning_effort="low", stream=True)
        for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            finish = choice.finish_reason or finish
            # Only print the response content, never the model's reasoning field.
            content = choice.delta.content
            if content:
                parts.append(content)
                say(content, end="")
        say()
        answer = "".join(parts)
        if not answer.strip():
            say("No answer received. Please try again.", "yellow")
            return
        history[:] = messages[1:] + [{"role": "assistant", "content": answer}]
        if finish == "length":
            say("[Response limit reached. Ask 'continue' to get the rest.]", "yellow")
    except KeyboardInterrupt:
        say("\n[Stopped. This incomplete turn was not added to memory.]", "yellow")
    except Exception as error:
        status = getattr(error, "status_code", None)
        notes = {
            401: "API key rejected. Check the hardcoded API_KEY value.",
            403: "Access denied. Check Groq account/model permissions or network restrictions.",
            404: "Model not found. Check model availability in Groq Console.",
            429: "Rate or quota limit reached. Wait before retrying; check your Groq limits.",
            400: "Request rejected. Check model settings or try /reset and a shorter prompt.",
        }
        # Avoid printing raw exceptions that may contain request data.
        say("\n" + notes.get(status, "Connection or service error. Check your internet and try again."), "red")
        say("This incomplete turn was not added to memory.", "dim")
    finally:
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass
    say()


def main():
    banner()
    mode = choose_mode(1)
    language = "auto"
    history = []
    banner(mode)
    if API_KEY == "Paste Your Api key" or not API_KEY.strip():
        say("Setup: open this file and paste your Groq key into API_KEY near the top.", "yellow")
        return
    try:
        from groq import Groq
    except ImportError:
        say("Install the packages first: pip install groq rich", "yellow")
        return
    client = Groq(api_key=API_KEY.strip(), timeout=60.0, max_retries=0)
    try:
        while True:
            text = input("You > ").strip()
            if not text:
                continue
            command, _, argument = text.partition(" ")
            command = command.lower()
            argument = argument.strip()
            if command in ("/exit", "/quit"):
                break
            if command == "/help":
                say("/mode       Choose a personality\n/mode 3     Switch directly to Professional\n"
                    "/lang si    Sinhala replies (en = English, auto = match you)\n"
                    "/clear      Refresh screen; keep chat memory\n/reset      Clear conversation memory\n"
                    "/exit       Close the assistant\n\n"
                    "Chat uses the internet. Recent turns stay in memory only.\n"
                    "Ctrl+C during a response stops it; at the input prompt it exits.")
            elif command == "/mode":
                if not argument:
                    mode = choose_mode(mode)
                elif argument.isdigit() and int(argument) in MODES:
                    mode = int(argument)
                else:
                    say("Use /mode or /mode 1 through /mode 10.", "yellow")
                    continue
                banner(mode)
            elif command == "/lang":
                if argument.lower() in ("auto", "en", "si"):
                    language = argument.lower()
                    say(f"Language: {language}", "cyan")
                else:
                    say("Use /lang auto, /lang en, or /lang si.", "yellow")
            elif command == "/reset":
                history.clear()
                say("Conversation memory cleared.", "cyan")
            elif command == "/clear":
                if console:
                    console.clear()
                else:
                    say("\n" * 3)
                banner(mode)
            elif command.startswith("/"):
                say("Unknown command. Type /help.", "yellow")
            elif len(text) > MAX_INPUT_CHARS:
                say(f"Please keep each message under {MAX_INPUT_CHARS} characters.", "yellow")
            else:
                reply(client, history, text, mode, language)
    finally:
        client.close()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        pass
    say("\nBehind The Code — session closed.", "cyan")
