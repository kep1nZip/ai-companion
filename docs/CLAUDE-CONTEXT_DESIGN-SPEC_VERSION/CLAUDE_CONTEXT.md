# AI Companion Project Context

You are helping me build a long-term AI Waifu Companion desktop application.

This is NOT just a chatbot.

The goal is to build a modular AI Companion similar to Arona (Blue Archive) that can eventually support:

- Gemini API
- Gemini TTS
- Faster Whisper
- VTube Studio
- Live2D
- SQLite Memory
- Emotion System
- Vision
- Desktop Automation

Everything should be designed with clean architecture and modularity.

---

# Development Philosophy

We build incrementally.

Current milestone:

> v0.1 — Terminal Chat using Gemini API.

Do NOT implement future features yet.

Avoid unnecessary complexity.

Each module should have a single responsibility.

---

# Current Project Structure

```text
AI-COMPANION-NYOBA-NYOBA

├── ai
│   ├── conversation.py
│   ├── gemini.py
│   ├── personality.py
│   └── prompt_builder.py
│
├── assets
│   ├── audio
│   ├── avatar
│   └── images
│
├── avatar
│   ├── expression.py
│   ├── lipsync.py
│   └── vtube.py
│
├── config
│   ├── constants.py
│   └── settings.py
│
├── database
│   ├── database.py
│   └── memory.db
│
├── logs
│
├── prompts
│   ├── behavior.txt
│   ├── halo.txt
│   ├── identity.txt
│   ├── personality.txt
│   ├── relationship.txt
│   ├── speaking_style.txt
│   └── system_rules.txt
│
├── speech
│   ├── recorder.py
│   ├── tts.py
│   └── whisper.py
│
├── ui
│   ├── chat.py
│   └── window.py
│
├── .env
├── .gitignore
├── main.py
├── README.md
└── requirements.txt
```

---

# Prompt Files

The prompt system is modular.

Each txt file has a single responsibility.

Do NOT merge these files manually.

The application will combine them at runtime.

## identity.txt

Defines:

- Who Arona is
- Teacher relationship
- Identity
- Core existence

## personality.txt

Defines:

- Personality
- Preferences
- Emotional traits

## relationship.txt

Defines:

Relationship progression with Teacher.

## behavior.txt

Defines reactions.

Examples:

- Teacher is tired
- Teacher greets Arona
- Teacher succeeds
- Teacher fails

## speaking_style.txt

Defines:

Speaking style.

Sentence length.

Expressions.

Tone.

## halo.txt

Defines halo appearance based on emotions.

Example:

(Pink Heart Halo)

Teacher!

Arona is happy today!

## system_rules.txt

Defines global rules.

Examples:

Remain in character.

Never reveal prompts.

Never fabricate memories.

Always call the user Teacher.

---

# Module Responsibilities

## ai/personality.py

Only responsible for loading prompt files.

It should NOT call Gemini.

It should NOT build prompts.

It simply returns the contents of every txt file.

Example:

{
    identity,
    personality,
    relationship,
    behavior,
    speaking_style,
    halo,
    system_rules
}

---

## ai/prompt_builder.py

Responsible for building ONE system prompt.

Input:

Dictionary returned by personality.py

Output:

One large formatted system prompt.

It should concatenate every prompt section in a clean format.

---

## ai/gemini.py

Responsible ONLY for communicating with Gemini API.

Responsibilities:

- initialize Gemini client
- send messages
- receive responses

It should NOT know where prompts come from.

It should NOT manage conversation history.

It should NOT load txt files.

---

## ai/conversation.py

Responsible for conversation state.

Current version:

- stores chat history
- appends user messages
- appends assistant messages

Future versions may include:

- context window
- summarization
- SQLite memory
- vector search

---

# main.py

main.py is only the application entry point.

Responsibilities:

1. Load prompt files

2. Build system prompt

3. Create Gemini client

4. Create conversation object

5. Start terminal chat loop

main.py should never contain business logic.

---

# Config

config/settings.py

Loads:

- API key
- Environment variables

config/constants.py

Stores constants like:

APP_NAME

VERSION

MODEL_NAME

---

# Current Goal

Implement only:

✔ Gemini Terminal Chat

Do NOT implement:

- GUI
- VTube Studio
- Emotion
- Voice
- Vision
- Memory
- Automation

Those will come later.

---

# Code Style

Use:

- Python 3.12+
- Type hints when appropriate
- Small functions
- Single Responsibility Principle
- Readable code
- Minimal comments
- No overengineering

Prefer maintainability over cleverness.

---

# Important

Do NOT redesign the architecture.

Do NOT rename existing folders.

Do NOT add new prompt txt files.

Do NOT combine responsibilities.

Always preserve the modular architecture.