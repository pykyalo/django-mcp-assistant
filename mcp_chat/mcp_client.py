"""
MCP Client - manages conversation with Claude and routes tool calls to MCP servers
"""

import os
import anthropic
from typing import List, Dict, Any, Optional
import json
from django.conf import settings
import logging

from .mcp_servers import MCPServer, VoIPDocsServer, WeatherServer


logger = logging.getLogger(__name__)


class MCPClient:
    """
    Handles the conversation loop with Claude, including tool calling.
    This is the 'smart' part that routes Claude's tool requests to MCP servers.
    """

    def __init__(self) -> None:
        self.client = anthropic.Client(
            api_key=settings.ANTHROPIC_API_KEY,
            max_retries=3,
            timeout=60,
        )
        self.model = settings.ANTHROPIC_MODEL

        # Initialize MCP servers
        self.servers: Dict[str, MCPServer] = {}
        self._initialize_servers()

    def _initialize_servers(self) -> None:
        """
        Setup all servers based on settings.
        """

        # VoIp documentation server
        docs_dir = os.getenv("VOIP_DOCS_DIR", "/tmp/voip_docs")
        os.makedirs(docs_dir, exist_ok=True)
        self.servers["voip-docs"] = VoIPDocsServer(docs_dir)

        # Weather server
        self.servers["weather"] = WeatherServer()

        logger.info("MCP servers initialized:")
        for server_name, server in self.servers.items():
            tools = server.get_tools()
            logger.info(f" * {server_name}: {len(tools)} tools")

    def get_all_tools(self) -> List[Dict[str, Any]]:
        """Aggregate all tools from all servers."""
        all_tools = []

        for server_name, server in self.servers.items():
            tools = server.get_tools()

            # Add server metadata to each tool
            for tool in tools:
                tool["_server"] = server_name  # Track which server owns this tool
                all_tools.append(tool)
        return all_tools

    def get_clean_tools_for_api(self) -> List[Dict[str, Any]]:
        """Get tools without internal metadata for Anthropic API."""
        clean_tools = []

        for server_name, server in self.servers.items():
            tools = server.get_tools()

            for tool in tools:
                # Create a clean copy without internal fields
                clean_tool = {k: v for k, v in tool.items() if not k.startswith("_")}
                clean_tools.append(clean_tool)

        return clean_tools

    def get_all_resources(self) -> List[Dict[str, Any]]:
        """Aggregate all resources from all the servers, filtering for FreeSWITCH/SIP"""
        all_resources = []

        for server_name, server in self.servers.items():
            resources = server.get_resources()

            # Add server metadata to each resource and filter by name
            for resource in resources:
                resource_name = resource.get("name", "").lower()
                # Only include resources with FreeSWITCH or SIP in their names
                if "freeswitch" in resource_name or "sip" in resource_name:
                    resource["_server"] = (
                        server_name  # Track which server owns this resource
                    )
                    all_resources.append(resource)
        return all_resources

    async def handle_tool_call(
        self, tool_name: str, tool_input: Dict[str, Any], server_name: str
    ) -> Any:
        """Handle tool calling by routing to the appropriate server."""

        if server_name not in self.servers:
            return {"error": f"Unknown server: {server_name}"}

        server = self.servers[server_name]

        logger.info(f"Calling tool {tool_name} on server {server_name}")
        logger.info(f" tool input: {tool_input}")

        result = await server.call_tool(tool_name, tool_input)

        logger.info(f"  Result: {str(result)[:200]}...")

        return result

    async def send_message(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Send message to Claude with MCP tool support.
        Handles the full conversation loop including tool calls.

        Returns:
            {
            'response': str, # Final assistance response
            'tool_calls': List[Dict], # Tolls that were called
            'conversation': List[Dict] # Full conversation including tool use
            }
        """

        if conversation_history is None:
            conversation_history = []

        # Add user message
        messages = conversation_history + [{"role": "user", "content": user_message}]

        # Get clean tools for API (without internal metadata)
        clean_tools = self.get_clean_tools_for_api()

        # Get tools with metadata for server routing
        tools_with_metadata = self.get_all_tools()

        # Build system prompt with resource information
        resources = self.get_all_resources()
        resource_info = self._format_resources(resources)

        system_prompt = f"""You are a helpful assistant with access to multiple tools and resources.

        Available Resources:
        {resource_info}

        Tool Usage Guidelines:
        - For weather-related queries: Use weather tools (get_weather, etc.)
        - For VoIP, SIP, FreeSWITCH, or telephony topics: Use search_voip_docs tool and get_sip_message_example
        - Always choose the most appropriate tool based on the user's question topic
        - When using documentation, cite specific sources

        Choose tools carefully based on the user's actual question topic.
        """

        # Track tool calls made
        tool_calls_made = []

        # Conversation loop - handle multiple tool calls
        max_iterations = 5  # Prevent infinite loops
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            logger.info(f"\n API Call #{iteration}")

            # Call Claude
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                tools=clean_tools,
                messages=messages,
            )

            logger.info(f"Response - Stop reason: {response.stop_reason}")

            # Add assistant response to conversation
            messages.append({"role": "assistant", "content": response.content})

            # Check if Claude wants to use tools
            if response.stop_reason == "tool_use":
                # Claude wants to call one or more tools
                tool_results = []

                for content_block in response.content:
                    if content_block.type == "tool_use":
                        tool_name = content_block.name
                        tool_input = content_block.input
                        tool_use_id = content_block.id

                        # Find which server owns this tool
                        server_name = None
                        for tool_def in tools_with_metadata:
                            if tool_def["name"] == tool_name:
                                server_name = tool_def.get("_server")
                                break

                        if not server_name:
                            result = {"error": f"Tool {tool_name} not found"}
                        else:
                            # Execute the tool
                            result = await self.handle_tool_call(
                                tool_name, tool_input, server_name
                            )

                        # Track this tool call
                        tool_calls_made.append(
                            {"tools": tool_name, "input": tool_input, "result": result}
                        )

                        # Add tool result to conversation
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use_id,
                                "content": json.dumps(result, indent=2),
                            }
                        )

                # Send tool results back to Claude
                messages.append({"role": "user", "content": tool_results})

                # Continue loop - Claude will process tool results
                continue

            else:
                # Claude is done (stop_reason is "end_turn")
                # Extract final text response

                final_response = ""
                for content_block in response.content:
                    if hasattr(content_block, "text"):
                        final_response += content_block.text

                return {
                    "response": final_response,
                    "tool_calls": tool_calls_made,
                    "conversation": messages,
                }

    def _format_resources(self, resources: List[Dict[str, Any]]) -> str:
        """Format resources for system prompt"""
        if not resources:
            return "No resources currently available."

        formatted = []
        for resource in resources:
            formatted.append(f"- {resource['name']}: {resource['description']}")

        return "\n".join(formatted)
