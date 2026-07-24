# 🌸 Arona AI Companion

> A modular desktop AI Companion powered by Google Gemini, featuring memory, emotions, voice, vision, and Live2D avatar integration.

![Python](https://img.shields.io/badge/Python-3.13-blue)
![Gemini](https://img.shields.io/badge/Google-Gemini%202.5-orange)
![PySide6](https://img.shields.io/badge/GUI-PySide6-green)
![Status](https://img.shields.io/badge/Status-Active-success)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

---

## ✨ Overview

**Arona AI Companion** is a personal desktop AI assistant inspired by *Blue Archive's Arona*.

Unlike a traditional chatbot, Arona is designed as a long-term AI companion capable of:

- 💬 Natural conversation
- 🧠 Persistent memory
- ❤️ Dynamic emotions
- 🤝 Relationship growth
- 🎙️ Voice interaction
- 👀 Vision understanding
- 🎭 Live2D / VTube Studio integration

The project focuses on **AI Software Engineering**, emphasizing modular architecture, maintainability, and extensibility rather than simply wrapping an LLM API.

---

# 🎯 Goals

This project aims to explore how to build a modern AI Companion using:

- Large Language Models
- Runtime Context Injection
- Behavioral AI
- Memory Systems
- Voice Interfaces
- Computer Vision
- Avatar Animation

while maintaining clean software architecture.

---

# 🏗 Architecture

```
Teacher
        │
        ▼
 Companion
        │
        ├──────────────┐
        ▼              ▼
Behavior Engine     Vision
        │              │
        └──────┬───────┘
               ▼
        Context Builder
               │
               ▼
            Gemini
               │
       ┌───────┴────────┐
       ▼                ▼
   Voice Manager    Avatar Manager
       ▼                ▼
      Audio         VTube Studio
```

The Companion acts as the application orchestrator.

Each subsystem is independent and follows the Single Responsibility Principle.

---

# 🚀 Features

## Core

- Google Gemini 2.5 Flash
- Modular Prompt System
- Conversation Manager
- Context Builder
- Logging
- Error Handling

---

## Memory

- SQLite Memory
- Persistent Conversations
- Long-term User Information

---

## Behavior Engine

- Emotion System
- Relationship System
- Mood
- Energy
- Curiosity
- Initiative

Behavior dynamically affects responses through **Ephemeral Context Injection**.

---

## Voice

- Speech-to-Text
- Gemini Native TTS
- Voice Manager
- Audio Playback

---

## Avatar

- VTube Studio Integration
- Lip Sync
- Halo System
- Facial Expressions
- Idle Animation

---

## Vision

(Currently in development)

- Screen Capture
- Gemini Vision
- Runtime Vision Context

---

# 📁 Project Structure

```
ai/
avatar/
behavior/
config/
database/
docs/
memory/
prompts/
speech/
ui/
vision/
```

Each module is isolated and independently testable.

---

# 🛠 Tech Stack

| Category | Technology |
|-----------|------------|
| Language | Python 3.13 |
| AI | Google Gemini 2.5 Flash |
| Vision | Gemini Vision |
| TTS | Gemini Native TTS |
| STT | Whisper |
| GUI | PySide6 |
| Database | SQLite |
| Avatar | VTube Studio |
| Logging | Loguru |

---

# 📌 Current Roadmap

## ✅ Phase 1 — Foundation

- Chat
- GUI
- Memory
- Voice
- Avatar

---

## ✅ Phase 2 — Behavior

- Emotion
- Relationship
- Internal State
- Behavior Integration

---

## 🚧 Phase 3 — Intelligence

- Vision System
- Routine System
- Autonomous Behaviors

---

## 🔮 Phase 4 — Release

- Plugin/API Support
- Performance Optimization
- v1.0 Stable

---

# 📚 Documentation

Project documentation is located in:

```
docs/
```

Including:

- Architecture
- Roadmap
- Changelog
- Technical Stack
- Design Specifications

---

# 💡 Design Principles

This project follows:

- SOLID Principles
- Separation of Concerns
- Dependency Injection
- Composition over Inheritance
- Modular Architecture
- Ephemeral Context Injection
- Context Builder Separation
- Single Source of Truth

---

# 📸 Screenshots

> Coming soon.

---

# 🎥 Demo

> Coming soon.

---

# 🚀 Getting Started

Clone the repository

```bash
git clone https://github.com/yourusername/arona-ai-companion.git
```

Install dependencies

```bash
pip install -r requirements.txt
```

Create

```
.env
```

Example

```env
GEMINI_API_KEY=YOUR_API_KEY
```

Run

```bash
python main.py
```

---

# 📖 Inspiration

- Blue Archive
- Google Gemini
- VTube Studio
- Modern AI Companion Architecture

---

# 📄 License

MIT License

---

# ❤️ Author

Developed by **kep1nZip**

Made with ❤️ and lots of coffee.