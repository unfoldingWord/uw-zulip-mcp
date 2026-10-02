"""ZulipChat MCP Server - zuliprc-first configuration."""

import argparse
import os
from collections.abc import AsyncIterator
from typing import Any, Literal, cast

from fastmcp import FastMCP
from fastmcp.server.lifespan import lifespan

from . import __version__
from .config import ConfigManager, init_config_manager
from .core import hosted_config
from .core.audit import init_audit_logging, is_audit_enabled
from .core.auth_provider import AuthConfigurationError, build_auth_provider
from .core.channel_filter import init_channel_filter
from .core.hosted_middleware import ZulipCredentialMiddleware
from .core.request_credentials import set_hosted_mode
from .core.security import set_unsafe_mode

# Optional: Anthropic sampling handler for LLM analytics fallback
try:
    from fastmcp.client.sampling.handlers.anthropic import AnthropicSamplingHandler

    anthropic_available = True
except ImportError:
    anthropic_available = False

# Optional service manager for background services
try:
    from .core.service_manager import init_service_manager, shutdown_service_manager

    service_manager_available = True
except ImportError:
    service_manager_available = False

from .tools import register_core_tools, register_extended_tools

try:
    from .utils.database import init_database

    database_available = True
except ImportError:
    database_available = False

from .utils.env import env_bool
from .utils.logging import get_logger, setup_structured_logging


def _build_server_lifespan(config_manager: ConfigManager, enable_listener: bool) -> Any:
    """Build a FastMCP lifespan for ZulipChat background services."""

    @lifespan
    async def server_lifespan(server: FastMCP[Any]) -> AsyncIterator[dict[str, Any]]:
        if not service_manager_available:
            yield {}
            return

        svc = init_service_manager(config_manager, enable_listener=enable_listener)
        if enable_listener:
            svc.start()
        try:
            yield {"service_manager": svc}
        finally:
            shutdown_service_manager()

    return server_lifespan


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
        help="Register all tools (56) instead of the core set (20).",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Restrict to read/search tools only. No sending, editing, or reactions.",
    )
    parser.add_argument(
        "--disable-agents",
        action="store_true",
        help="Disable all agent tools (registration, sessions, messaging, events).",
    )
    parser.add_argument(
        "--hosted",
        action="store_true",
        help=(
            "Hosted multi-user mode (OAuth2-only): clients authenticate with "
            "OAuth; the server resolves each user's Zulip API key from the "
            "OpenBao/Vault store and caches it per identity. New users add "
            "their key via the /enroll web page. Requires a network transport, "
            "ZULIP_SITE, an auth provider (ZULIPCHAT_AUTH_MODE), and OpenBao."
        ),
    )

    # Transport options
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "http", "streamable-http"],
        default="stdio",
        help=(
            "Transport protocol (default: stdio). "
            "Use 'http'/'streamable-http' for persistent network deployments, "
            "'sse' for legacy SSE clients."
        ),
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Host to bind to in SSE/HTTP mode (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to listen on in SSE/HTTP mode (default: 3000, or MCP_PORT env var).",
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

    # Hosted multi-user mode: per-request client credentials, none at rest
    hosted = args.hosted or env_bool("ZULIPCHAT_HOSTED")
    set_hosted_mode(hosted)

    # Validate configuration
    if hosted:
        if args.transport == "stdio" and not os.getenv("ZULIPCHAT_TRANSPORT"):
            logger.error(
                "Hosted mode requires a network transport. "
                "Use --transport http (or sse)."
            )
            return
        if not config_manager.validate_hosted_config():
            logger.error(
                "Hosted mode requires ZULIP_SITE to be set server-side. "
                "User credentials are supplied per-request by clients."
            )
            return
        if hosted_config.vault_enabled():
            logger.info(
                "HOSTED MODE (OAuth2-only) - user API keys resolved from the "
                "OpenBao/Vault store, cached per identity; enrollment via the "
                "/enroll web page"
            )
        else:
            logger.warning(
                "HOSTED MODE but OpenBao/Vault is not configured "
                "(set OPENBAO_TOKEN or OPENBAO_ROLE_ID/OPENBAO_SECRET_ID). "
                "Authenticated users with no stored key cannot be served."
            )
    elif not config_manager.validate_config():
        logger.error(
            "Invalid configuration. Please run 'uv run zulipchat-mcp-setup' first."
        )
        return

    logger.info("Configuration loaded successfully")

    # Set global safety mode context
    set_unsafe_mode(args.unsafe)
    if args.unsafe:
        logger.warning("RUNNING IN UNSAFE MODE - Dangerous tools enabled")

    # Initialize audit logging
    init_audit_logging()
    if is_audit_enabled():
        logger.info("Audit logging ENABLED")

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

    # OAuth 2.1 auth provider for the user -> MCP server hop (env-driven)
    try:
        auth_provider = build_auth_provider()
    except AuthConfigurationError as e:
        logger.error("Auth configuration error: %s", e)
        return
    if auth_provider is not None:
        logger.info(
            "Auth ENABLED (%s) - clients must authenticate to reach this server",
            os.getenv("ZULIPCHAT_AUTH_MODE"),
        )
    elif hosted:
        logger.warning(
            "Hosted mode without ZULIPCHAT_AUTH_MODE - the server relies "
            "solely on per-request Zulip credentials. Enable OAuth (jwt/"
            "google/oidc) or front with an authenticating proxy."
        )

    if hosted and not hosted_config.identity_allowlist_configured():
        logger.warning(
            "No identity allowlist set - ALL authenticated identities will be "
            "REJECTED (fail-closed). Set ZULIPCHAT_ALLOWED_EMAIL_DOMAINS and/or "
            "ZULIPCHAT_ALLOWED_EMAILS to grant access."
        )

    # Initialize MCP with modern configuration
    mcp = FastMCP(
        "ZulipChat MCP",
        version=__version__,
        website_url="https://github.com/akougkas/zulipchat-mcp",
        instructions=(
            "Use ZulipChat MCP to bind coding agents to Zulip topics, send lifecycle "
            "updates, request approvals, and read steering commands from the topic owner."
        ),
        on_duplicate="warn",
        # FastMCP protocol tasks are enabled per long-running tool. Keeping the
        # server default forbidden prevents sync/fast tools from being advertised
        # as task-capable by accident.
        tasks=False,
        lifespan=_build_server_lifespan(config_manager, args.enable_listener),
        sampling_handler=sampling_handler,
        sampling_handler_behavior="fallback",  # Use only when client doesn't support sampling
        auth=auth_provider,
    )

    # Bind per-request Zulip credentials (OAuth identity -> cache/vault) around
    # every tool call. No-op on stdio, where there is no OAuth identity.
    mcp.add_middleware(ZulipCredentialMiddleware())

    # Serve the browser enrollment page when hosted with a vault configured.
    if hosted and hosted_config.vault_enabled():
        from .core.enrollment_routes import register_enrollment_routes

        register_enrollment_routes(mcp)
        if auth_provider is None:
            logger.error(
                "OAuth2-only hosted mode needs an auth provider to identify "
                "users. Set ZULIPCHAT_AUTH_MODE (google/oidc/jwt) or front the "
                "server with an authenticating proxy."
            )
        if hosted_config.public_base_url() is None:
            logger.warning(
                "ZULIPCHAT_PUBLIC_URL is not set - enrollment links will be "
                "relative paths. Set it to this server's public URL."
            )

        # Probe the vault at startup: CA file readable, TLS reachable, auth OK.
        # Uses a throwaway client so the request-time singleton is untouched.
        import asyncio

        from .core.secret_store import SecretStore

        async def _probe_vault() -> bool:
            probe = SecretStore()
            try:
                return await probe.selfcheck()
            finally:
                await probe.aclose()

        try:
            vault_ok = asyncio.run(_probe_vault())
        except Exception as e:  # never block startup on the probe itself
            logger.error("OpenBao startup selfcheck crashed: %s", e)
            vault_ok = False

        if not vault_ok and hosted_config.openbao_startup_required():
            logger.error(
                "OpenBao self-check failed and OPENBAO_STARTUP_REQUIRED is set; "
                "refusing to start. Fix OpenBao connectivity/credentials, or "
                "unset OPENBAO_STARTUP_REQUIRED to boot anyway."
            )
            return

    logger.info("FastMCP initialized successfully")

    # Determine tool modes
    extended = args.extended_tools or env_bool("ZULIPCHAT_EXTENDED_TOOLS")
    read_only = args.read_only or env_bool("ZULIPCHAT_READ_ONLY")
    disable_agents = args.disable_agents or env_bool("ZULIPCHAT_DISABLE_AGENTS")

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

    # Warm user/stream caches for fast fuzzy resolution. Skipped in hosted
    # mode: there is no server-side user identity to warm caches for.
    if not hosted:
        try:
            from .config import get_client

            _warmup_client = get_client()
            _warmup_client.get_users()  # populates user_cache via client wrapper
            _warmup_client.get_streams()  # populates stream_cache via client wrapper
            logger.info("User and stream caches warmed")
        except Exception as e:
            logger.debug(f"Cache warmup skipped: {e}")

    # Privacy notice on stderr (visible to operator, not to MCP client)
    quiet = env_bool("ZULIPCHAT_QUIET")
    if not quiet:
        import sys

        lines = [
            "",
            "=" * 60,
            "  ZulipChat MCP Server — Privacy Notice",
            "=" * 60,
            "",
            "  Messages accessed via this MCP server will be sent to",
            "  your configured LLM provider for processing. Review your",
            "  provider's data retention policy before use.",
            "",
        ]
        if channel_filter.config.enabled:
            n_allow = len(channel_filter.config.jd_allow_areas)
            n_exclude = len(channel_filter.config.channel_exclude)
            n_include = len(channel_filter.config.channel_include)
            lines.append("  Channel filter:  ENABLED")
            if n_allow:
                areas = ", ".join(
                    f"{lo}-{hi}" if lo != hi else str(lo)
                    for lo, hi in channel_filter.config.jd_allow_areas
                )
                lines.append(f"  Allowed areas:   {areas}")
            if n_exclude:
                lines.append(f"  Excluded:        {n_exclude} channel(s)")
            if n_include:
                lines.append(f"  Included:        {n_include} override(s)")
            lines.append(
                f"  Private chans:   {'excluded' if channel_filter.config.exclude_private else 'allowed'}"
            )
            lines.append(
                f"  DMs:             {'excluded' if channel_filter.config.exclude_dms else 'allowed'}"
            )
            lines.append(
                f"  Non-JD chans:    {'excluded' if channel_filter.config.exclude_non_jd else 'allowed'}"
            )
            if channel_filter.config.deny_unknown_stream_ids:
                lines.append("  Unknown IDs:     denied (fail-closed)")
            else:
                lines.append("  Unknown IDs:     ALLOWED (fail-open)")
                lines.append("")
                lines.append("  *** WARNING: Unknown stream IDs are NOT blocked. ***")
                lines.append("  *** Set ZULIPCHAT_DENY_UNKNOWN_STREAM_IDS=true   ***")
                lines.append("  *** for fail-closed enforcement.                  ***")
        else:
            lines.append("  Channel filter:  DISABLED (all channels accessible)")

        lines.append(f"  Read-only mode:  {'YES' if read_only else 'no'}")
        lines.append(
            f"  Agent tools:     {'disabled' if disable_agents else 'enabled'}"
        )
        if hosted:
            lines.append("  Hosted mode:     YES (OAuth2 identity; per-user")
            lines.append("                   Zulip keys stored in OpenBao/Vault)")
            lines.append(
                f"  Vault:           {'configured' if hosted_config.vault_enabled() else 'NOT configured'}"
            )
            lines.append(
                f"  Server auth:     {os.getenv('ZULIPCHAT_AUTH_MODE', 'none')}"
            )
            if hosted_config.identity_allowlist_configured():
                domains = sorted(hosted_config.allowed_email_domains())
                n_emails = len(hosted_config.allowed_emails())
                desc = ", ".join("@" + d for d in domains)
                if n_emails:
                    extra = f"{n_emails} address(es)"
                    desc = f"{desc} + {extra}" if desc else extra
                lines.append(f"  Identity allow:  {desc}")
            else:
                lines.append("  Identity allow:  NONE (no allowlist set)")
                lines.append("")
                lines.append(
                    "  *** WARNING: fail-closed - ALL identities rejected. ***"
                )
                lines.append(
                    "  *** Set ZULIPCHAT_ALLOWED_EMAIL_DOMAINS / _EMAILS.    ***"
                )
        lines.append("")
        lines.append("=" * 60)
        lines.append("")

        sys.stderr.write("\n".join(lines) + "\n")
        sys.stderr.flush()

    transport = args.transport or os.getenv("ZULIPCHAT_TRANSPORT", "stdio")
    if transport not in ("stdio", "sse", "http", "streamable-http"):
        logger.error(
            "Invalid transport %r; expected stdio, sse, http, or streamable-http",
            transport,
        )
        return
    transport = cast(Literal["stdio", "sse", "http", "streamable-http"], transport)
    logger.info("Starting ZulipChat MCP server (transport=%s)...", transport)

    if transport == "stdio":
        mcp.run()
    else:
        host = args.host or os.getenv("ZULIPCHAT_HOST", "127.0.0.1")
        port = args.port or config_manager.config.port  # MCP_PORT env var, default 3000
        mcp.run(transport=transport, host=host, port=port)


if __name__ == "__main__":
    main()
