---
name: zulipchat-notifyme
description: Send a deterministic message into the current Zulip-bound session topic.
disable-model-invocation: true
---

# Zulip notify me

Use this skill when you explicitly want to post to the bound Zulip topic outside the
default lifecycle hooks.

## Required setup

1. Read `ZULIPCHAT_SESSION_ID` from the shell.
2. If it is empty, stop and explain that there is no active Zulip-bound Claude
   session.

## Invocation contract

Interpret `$ARGUMENTS` as either:

- `<category> :: <message>`
- `<message>` for a plain `message` category

Supported categories:

- `message`
- `started`
- `blocked`
- `waiting`
- `completed`
- `failed`

## Execution

1. Parse the category and message.
2. Call `agent_message(session_id=..., category=..., content=...)`.
3. Keep the Zulip post concise and operational.
4. If the owner explicitly needs to reply with a choice, use
   `request_user_input(...)` instead.
