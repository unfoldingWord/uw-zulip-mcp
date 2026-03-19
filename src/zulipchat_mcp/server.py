"""ZulipChat MCP Server - zuliprc-first configuration."""

import argparse
import os

from fastmcp import FastMCP

from . import __version__
from .config import init_config_manager
from .core.channel_filter import init_channel_filter
from .core.security import set_unsafe_mode

# Optional: Anthropic sampling handler for LLM analytics fallback
try:
    from fastmcp.client.sampling.handlers.anthropic import AnthropicSamplingHandler

    anthropic_available = True
except ImportError:
    anthropic_available = False

# Optional service manager for background services
try:
    from .core.service_manager import init_service_manager

    service_manager_available = True
except ImportError:
    service_manager_available = False

from .tools import register_core_tools, register_extended_tools

try:
    from .utils.database import init_database

    database_available = True
except ImportError:
    database_available = False

from .utils.logging import get_logger, setup_structured_logging


def main() -> None:
    """Main entry point for the MCP server."""
    parser = argparse.ArgumentParser(
        description="ZulipChat MCP Server - Integrates Zulip Chat with AI assistants",
        epilog=(
            "Configuration requires either a zuliprc file "
            "(explicit or auto-discovered) or environment variables "
            "(ZULIP_EMAIL, ZULIP_API_KEY, ZULIP_SITE)."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    # Configuration Files
    parser.add_argument(
        "--zulip-config-file",
        help="Path to user zuliprc file (default: searches standard locations)",
    )
    parser.add_argument(
        "--zulip-bot-config-file",
        help="Path to bot zuliprc file (optional, for dual identity)",
    )

    # Safety & Operational Options
    parser.add_argument(
        "--unsafe",
        action="store_true",
        help="Enable dangerous tools (delete messages/users, mass unsubscribe). Default: SAFE mode.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--enable-listener", action="store_true", help="Enable message listener service"
    )
    parser.add_argument(
        "--extended-tools",
        action="store_true",
        help="Register all tools (~55) instead of core set (19).",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Restrict to read/search tools only. No sending, editing, or reactions.",
    )
    parser.add_argument(
        "--disable-agents",
        action="store_true",
        help="Disable all agent tools (registration, messaging, AFK, events).",
    )

    args = parser.parse_args()

    # Setup logging
    setup_structured_logging("DEBUG" if args.debug else "INFO")
    logger = get_logger(__name__)

    # Initialize configuration (zuliprc files and/or env credentials)
    config_manager = init_config_manager(
        config_file=args.zulip_config_file,
        bot_config_file=args.zulip_bot_config_file,
        debug=args.debug,
    )

    # Validate configuration
    if not config_manager.validate_config():
        logger.error(
            "Invalid configuration. Please run 'uv run zulipchat-mcp-setup' first."
        )
        return

    logger.info("Configuration loaded successfully")

    # Set global safety mode context
    set_unsafe_mode(args.unsafe)
    if args.unsafe:
        logger.warning("RUNNING IN UNSAFE MODE - Dangerous tools enabled")

    # Initialize channel filter (JD taxonomy-based access control)
    try:
        channel_filter = init_channel_filter()
        if channel_filter.config.enabled:
            logger.info("Channel filter ENABLED - access restricted by configuration")
        else:
            logger.info("Channel filter disabled - all channels accessible")
    except ValueError as e:
        logger.error(
            "Channel filter configuration error: %s. "
            "Fix the environment variables or remove them to disable filtering.",
            e,
        )
        return

    # Initialize database (optional for agent features)
    if database_available:
        try:
            init_database()
            logger.info("Database initialized")
        except Exception as e:
            logger.warning(f"Database initialization failed: {e}")
    else:
        logger.info("Database not available (agent features disabled)")

    # Configure sampling handler for LLM analytics (fallback when client doesn't support)
    sampling_handler = None
    if anthropic_available and os.getenv("ANTHROPIC_API_KEY"):
        sampling_handler = AnthropicSamplingHandler(
            default_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        )
        logger.info("Anthropic sampling handler configured (fallback mode)")
    elif anthropic_available:
        logger.debug(
            "ANTHROPIC_API_KEY not set - LLM analytics will require client sampling support"
        )

    # Initialize MCP with modern configuration
    mcp = FastMCP(
        "ZulipChat MCP",
        on_duplicate="warn",
        sampling_handler=sampling_handler,
        sampling_handler_behavior="fallback",  # Use only when client doesn't support sampling
    )

    logger.info("FastMCP initialized successfully")

    # Determine tool modes
    extended = args.extended_tools or os.getenv("ZULIPCHAT_EXTENDED_TOOLS", "0") in (
        "1",
        "true",
        "True",
    )
    read_only = args.read_only or os.getenv("ZULIPCHAT_READ_ONLY", "0") in (
        "1",
        "true",
        "True",
    )
    disable_agents = args.disable_agents or os.getenv(
        "ZULIPCHAT_DISABLE_AGENTS", "0"
    ) in ("1", "true", "True")

    if read_only:
        logger.info("READ-ONLY MODE - write tools will not be registered")
    if disable_agents:
        logger.info("AGENTS DISABLED - agent tools will not be registered")

    # Register tools with mode restrictions
    register_core_tools(mcp, read_only=read_only, disable_agents=disable_agents)

    if extended:
        register_extended_tools(mcp, read_only=read_only, disable_agents=disable_agents)
        logger.info("Registered extended tool set")
    else:
        logger.info("Registered core tool set")

    # Warm user/stream caches for fast fuzzy resolution
    try:
        from .config import get_client

        _warmup_client = get_client()
        _warmup_client.get_users()  # populates user_cache via client wrapper
        _warmup_client.get_streams()  # populates stream_cache via client wrapper
        logger.info("User and stream caches warmed")
    except Exception as e:
        logger.debug(f"Cache warmup skipped: {e}")

    # Initialize background services singleton. The listener starts eagerly only with
    # --enable-listener; otherwise it lazy-starts on first agent tool call via ensure_listener().
    # Skip entirely if agents are disabled — no background services needed.
    if service_manager_available and not disable_agents:
        try:
            svc = init_service_manager(config_manager, enable_listener=args.enable_listener)
            if args.enable_listener:
                svc.start()
            logger.info(
                "Background services %s",
                "started (listener enabled)" if args.enable_listener else "ready (listener lazy)",
            )
        except Exception as e:
            logger.warning(f"Could not initialize background services: {e}")
    elif disable_agents:
        logger.info("Background services skipped (agents disabled)")

    logger.info("Starting ZulipChat MCP server...")
    mcp.run()


if __name__ == "__main__":
    main()
