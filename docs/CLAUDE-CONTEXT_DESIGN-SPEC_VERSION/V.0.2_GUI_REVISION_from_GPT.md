# AI Companion
# v0.2 Desktop GUI Revision
## Design Philosophy Revision

---

# Purpose

This document revises the original v0.2 GUI specification.

The goal is NOT to redesign the GUI.

Instead, this document introduces architectural improvements that will make the project scalable until v1.0.

Everything written here is an addition to the original specification.

---

# Core Philosophy

The Desktop GUI is NOT the application.

The Desktop GUI is ONLY a presentation layer.

The real application is AICompanion.

Future interfaces should all use the same backend.

Examples:

Desktop GUI

↓

AICompanion

↓

Gemini

-------------------------

Voice Interface

↓

AICompanion

↓

Gemini

-------------------------

Discord Bot

↓

AICompanion

↓

Gemini

-------------------------

Web Interface

↓

AICompanion

↓

Gemini

Only the frontend changes.

The backend remains identical.

---

# Desktop Shell Philosophy

Do NOT think of v0.2 as a Chat Window.

Think of it as a Desktop Shell.

The Desktop Shell will eventually contain:

Chat

Memory

Voice

Avatar

Settings

Emotion

Vision

Automation

Most of these features will not exist yet.

The architecture should simply be ready.

---

# Sidebar

Instead of making a single chat window,

design the main window with a permanent sidebar.

Example:

+----------------------------------------------------------+
| Menu Bar                                                 |
+----------------------------------------------------------+
| Sidebar |                                                |
|         |                Chat Area                       |
|         |                                                |
|         |                                                |
|         |                                                |
|         |----------------------------------------------- |
|         | Input................................. [Send]  |
+----------------------------------------------------------+
| Status Bar                                               |
+----------------------------------------------------------+

The sidebar does NOT need to be functional.

Placeholder items are enough.

Example:

Chat

Memory (Coming Soon)

Voice (Coming Soon)

Avatar (Coming Soon)

Settings

---

# Main Window

MainWindow should become the root container of the application.

Avoid placing all logic inside window.py.

Window should only coordinate widgets.

Business logic must remain inside AICompanion.

---

# Future Widget Layout

Current ui/

window.py

chat.py

Future expansion should look like:

ui/

window.py

chat.py

navigation.py

statusbar.py

dialogs.py

theme.py

Do NOT implement everything now.

Only organize the project so expansion is easy.

---

# Chat Bubble

Avoid plain QTextEdit conversations.

Each message should become an individual chat bubble.

Teacher

Right aligned.

Arona

Left aligned.

Future System Messages

Centered.

Future Error Messages

Highlighted.

---

# Status Bar

StatusBar should become the global application status.

Examples:

Ready

Thinking...

Connected

Disconnected

Listening...

Speaking...

Memory Updated

StatusBar should NOT only display text.

It should become the application's state indicator.

---

# Window Size

Recommended default:

1000 x 700

Minimum:

900 x 600

Resizable.

---

# Theme

Keep the interface minimal.

Professional.

Dark Theme.

Soft blue accent.

Avoid heavy anime decorations.

The character itself should become the visual focus in future versions,

not the GUI.

---

# Reserved Areas

Do NOT implement.

Only reserve architecture.

Future reserved features:

Avatar Panel

Emotion Indicator

Microphone Button

Settings Dialog

Voice Indicator

Typing Indicator

Memory Indicator

---

# Avatar

DO NOT implement Live2D.

DO NOT implement VTube Studio.

Do NOT even place placeholder images.

The GUI should remain chat-focused.

Avatar integration belongs to v0.5.

---

# Threading

Every Gemini request must run outside the UI thread.

The GUI must never freeze.

The recommended approach is:

Main Thread

↓

Worker Thread

↓

AICompanion

↓

Gemini

↓

Return Result

↓

Update GUI

---

# Commands

The existing command system must remain unchanged.

Commands should work identically in GUI.

Supported commands:

/help

/history

/clear

/version

/exit

The GUI should not replace these commands with buttons.

Buttons are optional.

Commands remain first-class features.

---

# Startup Sequence

Application Start

↓

Logger

↓

Configuration

↓

Prompt Loader

↓

Prompt Builder

↓

AICompanion

↓

MainWindow

↓

Show Window

This sequence should remain deterministic.

---

# Shutdown Sequence

Window Close

↓

Flush Logger

↓

Cleanup Conversation

↓

Safe Exit

---

# Future Compatibility

This GUI must remain compatible with:

v0.3 SQLite Memory

v0.4 Voice

v0.5 VTube Studio

v0.6 Emotion Engine

v0.7 Vision

Avoid any design that would require rewriting the GUI later.

---

# UI Independence

Never import PySide6 outside ui/.

Forbidden examples:

ai/gemini.py importing Qt

conversation.py importing Qt

companion.py importing Qt

PromptBuilder importing Qt

The backend must never know that a GUI exists.

---

# Performance Goals

Support:

Hundreds of chat messages.

Long conversations.

Fast scrolling.

Responsive interface.

No unnecessary widget recreation.

---

# Code Style

Python 3.12+

PySide6

Small widgets.

Small methods.

Composition over inheritance.

Readable code.

No overengineering.

---

# Design Goal

The GUI should feel closer to:

Discord Desktop

Telegram Desktop

VS Code

than to:

Anime launchers

Game launchers

Heavy visual novel interfaces

The interface should disappear into the background,

allowing the conversation with Arona to become the main focus.

---

# Final Goal

When v0.2 is complete,

users should feel like they are talking to Arona inside a desktop application,

not using a chatbot inside a window.

The interface should be calm,

responsive,

minimal,

and prepared for future AI Companion features without requiring architectural rewrites.