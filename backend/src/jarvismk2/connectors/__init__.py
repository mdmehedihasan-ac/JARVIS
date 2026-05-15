"""External data sources (knowledge in)."""

from jarvismk2.connectors.obsidian import ObsidianConnector
from jarvismk2.connectors.webbridge import WebBridgeConnector, get_webbridge

__all__ = ["ObsidianConnector", "WebBridgeConnector", "get_webbridge"]
