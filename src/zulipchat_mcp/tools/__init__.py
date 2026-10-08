"""MCP tool registrars for ZulipChat MCP."""

from fastmcp import FastMCP

from .ai_analytics import register_ai_analytics_tools
from .emoji_messaging import register_emoji_messaging_tools
from .event_management import register_event_management_tools
from .files import register_files_tools
from .mark_messaging import register_mark_messaging_tools
from .messaging import register_messaging_tools
from .registration import optional_background_task, register_tool
from .schedule_messaging import register_schedule_messaging_tools
from .search import register_search_tools
from .stream_management import register_stream_management_tools
from .system import register_system_tools
from .topic_management import register_topic_management_tools
from .users import register_users_tools

__all__ = [
    "register_messaging_tools",
    "register_schedule_messaging_tools",
    "register_emoji_messaging_tools",
    "register_mark_messaging_tools",
    "register_search_tools",
    "register_stream_management_tools",
    "register_topic_management_tools",
    "register_event_management_tools",
    "register_ai_analytics_tools",
    "register_users_tools",
    "register_files_tools",
    "register_system_tools",
    "register_core_tools",
    "register_extended_tools",
]


def register_core_tools(
    mcp: FastMCP,
    read_only: bool = False,
    disable_agents: bool = False,
) -> None:
    """Register the default tool surface with optional mode restrictions.

    Args:
        mcp: FastMCP instance
        read_only: If True, only register read/search tools
        disable_agents: If True, skip all agent tools
    """
    from .emoji_messaging import add_reaction
    from .mark_messaging import manage_message_flags
    from .messaging import edit_message, get_message, send_message
    from .search import search_messages
    from .stream_management import get_stream_info, get_streams
    from .system import server_info, switch_identity
    from .topic_management import get_stream_topics
    from .users import get_own_user, get_users, resolve_user

    # --- Read/Search tools (always registered) ---

    # Search & Discovery (4)
    mcp.tool(
        name="search_messages",
        description=(
            "Search messages with filters for stream, topic, sender, time, and "
            "content, with fuzzy sender resolution. Returns "
            "{status, messages[], found, anchor, narrow_applied, sort_by}; each "
            "message has id, sender, email, timestamp, content, type, stream, "
            "topic, reactions, flags."
        ),
    )(search_messages)
    mcp.tool(
        name="get_streams",
        description=(
            "List available streams/channels. Returns "
            "{status, streams[], count}, where each stream is a Zulip stream "
            "object (stream_id, name, description, invite_only, ...)."
        ),
    )(get_streams)
    mcp.tool(
        name="get_stream_info",
        description=(
            "Get detailed information about one stream. Returns "
            "{status, stream_id, name, description, invite_only, is_web_public}, "
            "plus subscribers[]+subscriber_count and/or topics[]+topic_count when "
            "requested."
        ),
    )(get_stream_info)
    mcp.tool(
        name="get_stream_topics",
        description=(
            "List recent topics in a stream. Returns "
            "{status, stream_id, topics[], count}, where count is the total "
            "topics found (may exceed the truncated topics[])."
        ),
    )(get_stream_topics)

    # Users (3)
    mcp.tool(
        name="resolve_user",
        description=(
            "Resolve a display name to a Zulip account with fuzzy matching. "
            "Returns {status: 'success', email, matched, confidence} on a hit, "
            "or {status: 'not_found', query, suggestion}."
        ),
    )(resolve_user)
    mcp.tool(
        name="get_users",
        description=(
            "List users in the organization. Returns "
            "{status, users[], count, client_gravatar, "
            "include_custom_profile_fields}; each user is a Zulip user object."
        ),
    )(get_users)
    mcp.tool(
        name="get_own_user",
        description=(
            "Get the current authenticated user's profile. Returns "
            "{status, user:{user_id, email, full_name, avatar_url, is_admin, "
            "is_owner, is_bot, role, delivery_email, profile_data}}."
        ),
    )(get_own_user)

    # Read-only message retrieval (1)
    mcp.tool(
        name="get_message",
        description=(
            "Retrieve a single message by ID. Returns "
            "{status, message:{...full Zulip message object...}}."
        ),
    )(get_message)

    # System (1 — server_info is always safe)
    mcp.tool(
        name="server_info",
        description=(
            "Get server version and capabilities. Returns "
            "{status, server_name, version, available_identities:{user, bot}, "
            "features[], zulip_site}."
        ),
    )(server_info)

    # --- Write tools (skipped in read-only mode) ---
    if not read_only:
        # Messaging (3)
        mcp.tool(
            name="send_message", description="Send a message to a stream or user."
        )(send_message)
        mcp.tool(
            name="edit_message",
            description="Edit message content, topic, or move between streams.",
        )(edit_message)
        mcp.tool(name="add_reaction", description="Add emoji reaction to a message.")(
            add_reaction
        )

        # Identity switching (1)
        mcp.tool(
            name="switch_identity",
            description="Switch between user and bot identities.",
        )(switch_identity)

        # Message flags (1 — can mark as read, which is a write)
        mcp.tool(
            name="manage_message_flags",
            description="Mark messages as read/unread or star/unstar.",
        )(manage_message_flags)

    # --- Agent tools (skipped when agents disabled OR read-only) ---
    if not disable_agents and not read_only:
        from .agents import (
            agent_message,
            ensure_agent_session,
            register_agent,
            request_user_input,
            teleport_chat,
            wait_for_response,
        )

        interactive_task = optional_background_task(poll_seconds=2)

        # Agent Communication (6)
        register_tool(
            mcp,
            teleport_chat,
            name="teleport_chat",
            description="Send message to user or channel with fuzzy name resolution.",
            task=interactive_task,
        )
        mcp.tool(
            name="register_agent",
            description="Register or update a stable agent profile for Zulip control.",
        )(register_agent)
        mcp.tool(
            name="ensure_agent_session",
            description="Create or refresh the Zulip topic binding for an agent session.",
        )(ensure_agent_session)
        mcp.tool(
            name="agent_message",
            description="Send a session-scoped message into the bound Zulip topic.",
        )(agent_message)
        mcp.tool(
            name="request_user_input",
            description="Request a question or approval response from the owner in-topic.",
        )(request_user_input)
        register_tool(
            mcp,
            wait_for_response,
            name="wait_for_response",
            description="Wait for a persisted agent request response.",
            task=interactive_task,
        )


def register_extended_tools(
    mcp: FastMCP,
    read_only: bool = False,
    disable_agents: bool = False,
) -> None:
    """Register extended tools with optional mode restrictions.

    Call after register_core_tools() to add the full tool set.
    Core tools are already registered; this adds the rest.

    Args:
        mcp: FastMCP instance
        read_only: If True, only register read/search tools
        disable_agents: If True, skip all agent tools
    """
    from .ai_analytics import (
        analyze_stream_with_llm,
        analyze_team_activity_with_llm,
        get_daily_summary,
        intelligent_report_generator,
    )
    from .search import advanced_search, check_messages_match_narrow, construct_narrow
    from .users import (
        get_presence,
        get_user,
        get_user_group_members,
        get_user_groups,
        get_user_presence,
        get_user_status,
        is_user_group_member,
    )

    # --- Read tools (always registered) ---

    # Users — read-only (7)
    mcp.tool(name="get_user", description="Look up a user by ID or email.")(get_user)
    mcp.tool(name="get_user_status", description="Get user's status text and emoji.")(
        get_user_status
    )
    mcp.tool(
        name="get_user_presence", description="Get presence info for a specific user."
    )(get_user_presence)
    mcp.tool(name="get_presence", description="Get presence info for all users.")(
        get_presence
    )
    mcp.tool(name="get_user_groups", description="Get all user groups.")(
        get_user_groups
    )
    mcp.tool(name="get_user_group_members", description="Get members of a user group.")(
        get_user_group_members
    )
    mcp.tool(name="is_user_group_member", description="Check if user is in a group.")(
        is_user_group_member
    )

    # Search (3)
    mcp.tool(
        name="advanced_search",
        description="Multi-faceted search across messages, users, streams.",
    )(advanced_search)
    mcp.tool(
        name="construct_narrow", description="Build a narrow filter for Zulip API."
    )(construct_narrow)
    mcp.tool(
        name="check_messages_match_narrow",
        description="Check if messages match a narrow filter.",
    )(check_messages_match_narrow)

    # AI Analytics — read-only (4)
    mcp.tool(name="get_daily_summary", description="Get daily message summary.")(
        get_daily_summary
    )
    mcp.tool(
        name="analyze_stream_with_llm",
        description="Analyze stream data with LLM insights.",
    )(analyze_stream_with_llm)
    mcp.tool(
        name="analyze_team_activity_with_llm",
        description="Analyze team activity across streams with LLM.",
    )(analyze_team_activity_with_llm)
    mcp.tool(
        name="intelligent_report_generator",
        description="Generate reports using LLM analysis.",
    )(intelligent_report_generator)

    # Commands — read-only (1)
    from .commands import list_command_types

    mcp.tool(name="list_command_types", description="List available command types.")(
        list_command_types
    )

    # --- Write tools (skipped in read-only mode) ---
    if not read_only:
        from .commands import execute_chain
        from .emoji_messaging import toggle_reaction
        from .event_management import (
            deregister_events,
            get_events,
            listen_events,
            register_events,
        )
        from .files import manage_files, upload_file
        from .mark_messaging import update_message_flags_for_narrow
        from .messaging import cross_post_message
        from .schedule_messaging import (
            get_scheduled_messages,
            manage_scheduled_message,
        )
        from .topic_management import agents_channel_topic_ops
        from .users import (
            manage_user_mute,
            update_status,
        )

        listener_task = optional_background_task(poll_seconds=5)

        # Users — write (2)
        mcp.tool(name="update_status", description="Update your own status and emoji.")(
            update_status
        )
        mcp.tool(name="manage_user_mute", description="Mute or unmute a user.")(
            manage_user_mute
        )

        # Messaging (2)
        mcp.tool(
            name="cross_post_message", description="Share a message across streams."
        )(cross_post_message)
        mcp.tool(
            name="toggle_reaction", description="Add or remove an emoji reaction."
        )(toggle_reaction)

        # Scheduled Messages (2)
        mcp.tool(
            name="get_scheduled_messages", description="Get all scheduled messages."
        )(get_scheduled_messages)
        mcp.tool(
            name="manage_scheduled_message",
            description="Create, update, or delete a scheduled message.",
        )(manage_scheduled_message)

        # Events (4)
        mcp.tool(
            name="register_events", description="Register for real-time event streams."
        )(register_events)
        mcp.tool(name="get_events", description="Poll events from a registered queue.")(
            get_events
        )
        register_tool(
            mcp,
            listen_events,
            name="listen_events",
            description="Listen for events with auto queue management.",
            task=listener_task,
        )
        mcp.tool(name="deregister_events", description="Deregister an event queue.")(
            deregister_events
        )

        # Files (2)
        mcp.tool(name="upload_file", description="Upload a file to Zulip.")(upload_file)
        mcp.tool(
            name="manage_files", description="List, delete, share, or download files."
        )(manage_files)

        # Topics (1)
        mcp.tool(
            name="agents_channel_topic_ops",
            description="Topic operations in Agents-Channel (bot only).",
        )(agents_channel_topic_ops)

        # Commands — write (1)
        mcp.tool(name="execute_chain", description="Execute a command chain workflow.")(
            execute_chain
        )

        # Raw flag API for power users (1)
        mcp.tool(
            name="update_message_flags_for_narrow",
            description="Update message flags for a narrow (raw API).",
        )(update_message_flags_for_narrow)

    # --- Agent extended tools (skipped when agents disabled OR read-only) ---
    if not disable_agents and not read_only:
        from .agents import (
            close_agent_session,
            list_instances,
            list_sessions,
            manage_task,
            poll_agent_events,
            send_agent_status,
        )

        mcp.tool(name="send_agent_status", description="Send agent status update.")(
            send_agent_status
        )
        mcp.tool(name="manage_task", description="Start, update, or complete a task.")(
            manage_task
        )
        mcp.tool(name="list_sessions", description="List known agent sessions.")(
            list_sessions
        )
        mcp.tool(
            name="list_instances",
            description="Compatibility alias for listing sessions.",
        )(list_instances)
        mcp.tool(
            name="close_agent_session",
            description="Close a session binding and optionally announce the result.",
        )(close_agent_session)
        mcp.tool(
            name="poll_agent_events",
            description="Poll unacknowledged inbound session events.",
        )(poll_agent_events)
