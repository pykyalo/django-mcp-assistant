"""
MCP Server definitions - these are the tools and resources Claude will use
"""

import resource
from typing import List, Dict, Any
import json
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class MCPServer:
    """Base Class for MCP Server"""

    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description

    def get_tools(self) -> List[Dict[str, Any]]:
        """Return list of tools this server provides"""
        return NotImplementedError

    def get_resources(self) -> List[Dict[str, Any]]:
        """Return list of resources this server provides"""
        return NotImplementedError

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool call"""
        return NotImplementedError

    async def read_resource(self, uri: str) -> str:
        """Read a resource"""
        return NotImplementedError


class VOIPDocsServer(MCPServer):
    """MCP server for VOIP documentation"""

    def __init__(self, docs_dir: str) -> None:
        super().__init__(
            name="voip-docs",
            description="Access to VoIP and SIP protocol documentation",
        )
        self.docs_dir = Path(docs_dir)

    def get_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "search_voip_docs",
                "description": "Search through VoIP documentation for specific topic. Returns relevant excerpts from SIP RFCs, FreeSWITCH docs, etc.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (e.g., 'SIP INVITE method', 'FreeSWITCH dialplan')",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 3)",
                            "default": 3,
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_sip_message_example",
                "description": "Get example SIP messages for different scenarios (INVITE, REGISTER, BYE, etc.)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "message_type": {
                            "type": "string",
                            "enum": [
                                "INVITE",
                                "REGISTER",
                                "BYE",
                                "CANCEL",
                                "ACK",
                                "OPTIONS",
                            ],
                            "description": "Type of SIP message",
                        }
                    },
                    "required": ["message_type"],
                },
            },
        ]

    def get_resources(self) -> List[Dict[str, Any]]:
        """List available documentation files"""
        resources = []

        if self.docs_dir.exists():
            for doc_file in self.docs_dir.glob("*.txt"):
                resources.append(
                    {
                        "uri": f"file://{doc_file}",
                        "name": doc_file.stem,
                        "description": f"VoIP documentation: {doc_file.stem}",
                        "mimeType": "text/plain",
                    }
                )

        return resources

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute tool calls"""

        if tool_name == "search_voip_docs":
            return await self._search_docs(
                arguments["query"], arguments.get("max_results", 3)
            )
        elif tool_name == "get_sip_message_example":
            return await self._get_sip_message_example(arguments["message_type"])

        else:
            return {"error": f"Unknown tool: {tool_name}"}

    async def _search_docs(self, query: str, max_results: int) -> List[str]:
        """Search through documentation files"""
        results = []
        query_lower = query.lower()

        if not self.docs_dir.exists():
            return {"results": [], "message": "Documentation directory not found"}

        # Simple search through text files in the docs directory
        for doc_file in self.docs_dir.glob("*.txt"):
            try:
                content = doc_file.read_text()

                # Search for query in content
                if query_lower in content.lower():
                    # Get context around the match
                    lines = content.split("\n")
                    matches = []

                    for i, line in enumerate(lines):
                        if query_lower in line.lower():
                            # Get sorrounding lines for context
                            start = max(0, i - 2)
                            end = min(len(lines), i + 3)
                            context = "\n".join(lines[start:end])
                            matches.append(context)

                            if len(matches) >= max_results:
                                break

                    if matches:
                        results.append({"file": doc_file.name, "matches": matches})

            except Exception as e:
                logger.error(f"Error reading file {doc_file}: {e}")
                continue

        return {
            "results": results[:max_results],
            "query": query,
            "total_found": len(results),
        }

    def _get_sip_example(self, message_type: str) -> str:
        """Return example SIP messages"""
        examples = {
            "INVITE": """INVITE sip:bob@biloxi.com SIP/2.0
            Via: SIP/2.0/UDP pc33.atlanta.com;branch=z9hG4bKnashds8
            Max-Forwards: 70
            To: Bob <sip:bob@biloxi.com>
            From: Alice <sip:alice@atlanta.com>;tag=1928301774
            Call-ID: a84b4c76e66710@pc33.atlanta.com
            CSeq: 314159 INVITE
            Contact: <sip:alice@pc33.atlanta.com>
            Content-Type: application/sdp
            Content-Length: 142

            (SDP content here)""",
            "REGISTER": """REGISTER sip:registrar.biloxi.com SIP/2.0
            Via: SIP/2.0/UDP bobspc.biloxi.com:5060;branch=z9hG4bKnashds7
            Max-Forwards: 70
            To: Bob <sip:bob@biloxi.com>
            From: Bob <sip:bob@biloxi.com>;tag=456248
            Call-ID: 843817637684230@998sdasdh09
            CSeq: 1826 REGISTER
            Contact: <sip:bob@192.0.2.4>
            Expires: 7200
            Content-Length: 0""",
            "BYE": """BYE sip:alice@pc33.atlanta.com SIP/2.0
            Via: SIP/2.0/UDP 192.0.2.4;branch=z9hG4bKnashds10
            Max-Forwards: 70
            From: Bob <sip:bob@biloxi.com>;tag=a6c85cf
            To: Alice <sip:alice@atlanta.com>;tag=1928301774
            Call-ID: a84b4c76e66710
            CSeq: 231 BYE
            Content-Length: 0""",
            "ACK": """ACK sip:bob@192.0.2.4 SIP/2.0
            Via: SIP/2.0/UDP pc33.atlanta.com;branch=z9hG4bKnashds9
            Max-Forwards: 70
            To: Bob <sip:bob@biloxi.com>;tag=a6c85cf
            From: Alice <sip:alice@atlanta.com>;tag=1928301774
            Call-ID: a84b4c76e66710@pc33.atlanta.com
            CSeq: 314159 ACK
            Content-Length: 0""",
            "CANCEL": """CANCEL sip:bob@biloxi.com SIP/2.0
            Via: SIP/2.0/UDP pc33.atlanta.com;branch=z9hG4bKnashds8
            Max-Forwards: 70
            To: Bob <sip:bob@biloxi.com>
            From: Alice <sip:alice@atlanta.com>;tag=1928301774
            Call-ID: a84b4c76e66710@pc33.atlanta.com
            CSeq: 314159 CANCEL
            Content-Length: 0""",
            "OPTIONS": """OPTIONS sip:bob@biloxi.com SIP/2.0
            Via: SIP/2.0/UDP pc33.atlanta.com;branch=z9hG4bKnashds11
            Max-Forwards: 70
            To: <sip:bob@biloxi.com>
            From: Alice <sip:alice@atlanta.com>;tag=1928301774
            Call-ID: a84b4c76e66710
            CSeq: 63104 OPTIONS
            Contact: <sip:alice@pc33.atlanta.com>
            Accept: application/sdp
            Content-Length: 0""",
        }

        return examples.get(message_type, f"No example available for {message_type}")

    async def read_resource(self, uri: str) -> str:
        """Read a documentation file"""
        # Extract path from file:// URI
        path = uri.replace("file://", "")

        try:
            with open(path, "r") as f:
                return f.read()
        except Exception as e:
            return f"Error reading resource: {str(e)}"


class WeatherServer(MCPServer):
    """MCP Server for weather data - demonstrates external API integrations"""

    def __init__(self):
        super().__init__(name="weather", description="Get current weather information")

    def get_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "get_weather",
                "description": "Get current weather for a location using Open-Meteo API",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "latitude": {
                            "type": "number",
                            "description": "Latitude coordinate",
                        },
                        "longitude": {
                            "type": "number",
                            "description": "Longitude coordinate",
                        },
                        "location_name": {
                            "type": "string",
                            "description": "Human-readable location name (optional)",
                        },
                    },
                    "required": ["latitude", "longitude", "location_name"],
                },
            }
        ]

    def get_resources(self) -> List[Dict[str, Any]]:
        return []  # No resources, only tools

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if tool_name == "get_weather":
            return await self._get_weather(
                arguments["latitude"],
                arguments["longitude"],
                arguments.get("location_name", "Unknown"),
            )

        return {"error": f"Unknown tool: {tool_name}"}

    async def _get_weather(
        self, lat: float, lon: float, location: str
    ) -> Dict[str, Any]:
        """Fetch weather data from Open-Meteo API"""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
                        "temperature_unit": "celsius",
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    current = data.get("current", {})

                    return {
                        "location": location,
                        "temperature": f"{current.get('temperature_2m')}°C",
                        "humidity": f"{current.get('relative_humidity_2m')}%",
                        "wind_speed": f"{current.get('wind_speed_10m')} km/h",
                        "coordinates": {"lat": lat, "lon": lon},
                    }
                else:
                    return {"error": f"API error: {response.status_code}"}

        except Exception as e:
            return {"error": f"Failed to fetch weather: {str(e)}"}
