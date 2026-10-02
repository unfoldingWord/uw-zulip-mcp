# Tool Categories

## Mode-restricted registration

Tools are registered based on `--read-only` and `--disable-agents` flags:

| Tool | Default | Read-only | Agents disabled |
|------|---------|-----------|-----------------|
| Search/read tools | Yes | Yes | Yes |
| Write tools | Yes | **No** | Yes |
| Agent tools | Yes | **No** | **No** |

## Core mode (20 tools default, 9 in read-only)

### Always registered (read/search — 9)

- `search_messages`
- `get_streams`
- `get_stream_info`
- `get_stream_topics`
- `resolve_user`
- `get_users`
- `get_own_user`
- `get_message`
- `server_info`

### Write tools (skipped in read-only — 5)

- `send_message`
- `edit_message`
- `add_reaction`
- `switch_identity`
- `manage_message_flags`

### Agent tools (skipped when agents disabled or read-only — 6)

- `teleport_chat`
- `register_agent`
- `ensure_agent_session`
- `agent_message`
- `request_user_input`
- `wait_for_response` (configurable timeout via `ZULIPCHAT_AGENT_TIMEOUT`)

## Extended additions

### Always registered (read — 12)

- `get_user`, `get_user_status`, `get_user_presence`, `get_presence`
- `get_user_groups`, `get_user_group_members`, `is_user_group_member`
- `advanced_search`, `construct_narrow`, `check_messages_match_narrow`
- `get_daily_summary`, `analyze_stream_with_llm`, `analyze_team_activity_with_llm`, `intelligent_report_generator`
- `list_command_types`

### Write tools (skipped in read-only — 14)

- `update_status`, `manage_user_mute`
- `cross_post_message`, `toggle_reaction`
- `get_scheduled_messages`, `manage_scheduled_message`
- `register_events`, `get_events`, `listen_events`, `deregister_events`
- `upload_file`, `manage_files`
- `agents_channel_topic_ops`
- `execute_chain`
- `update_message_flags_for_narrow`

### Agent extensions (skipped when agents disabled or read-only — 6)

- `send_agent_status`, `manage_task`
- `list_sessions`, `list_instances` (compatibility alias)
- `close_agent_session`, `poll_agent_events`

## Channel filter interaction

All tools that access streams or messages are filtered by the channel filter at the client wrapper level. Tools don't need individual filter logic — it's enforced in `client.py` before results are returned.

## Design intent

- Keep common workflows on a compact default registry.
- Move heavier or specialized operations to explicit extended mode.
- Read-only and agent-disable modes reduce the tool surface for organizational deployments.
