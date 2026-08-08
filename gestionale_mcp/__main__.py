"""CLI entrypoint: python -m gestionale_mcp [--transport stdio|http]."""

from __future__ import annotations

import argparse

from mcp.server.transport_security import TransportSecuritySettings

from .config import MCPConfig
from .server import create_server


def main() -> None:
    parser = argparse.ArgumentParser(description="GestionaleCloud MCP gateway")
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    args = parser.parse_args()
    config = MCPConfig.from_env()
    if args.transport == "stdio":
        create_server(config).run("stdio")
        return
    server = create_server(config, authenticated_http=True)
    server.run(
        "streamable-http",
        host=config.host,
        port=config.port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        max_request_body_size=1_048_576,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(config.allowed_hosts),
            allowed_origins=list(config.allowed_origins),
        ),
    )


if __name__ == "__main__":
    main()
