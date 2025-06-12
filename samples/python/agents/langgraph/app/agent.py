from collections.abc import AsyncIterable
from typing import Any, Literal

import os
import httpx
from langchain_mcp_adapters.client import MultiServerMCPClient

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel

import asyncio

memory = MemorySaver()

class ResponseFormat(BaseModel):
    """Respond to the user in this format."""

    status: Literal['input_required', 'completed', 'error'] = 'input_required'
    message: str


class CurrencyAgent:
    """CurrencyAgent - a specialized assistant for currency convesions."""

    SYSTEM_INSTRUCTION = (
        'You are a specialized assistant for currency conversions. '
        "You will use the available tool to answer questions about currency exchanges. "
        'If the user asks about anything other than currency conversion or exchange rates, '
        'politely state that you cannot help with that topic and can only assist with currency-related queries. '
        'Do not attempt to answer unrelated questions or use tools for other purposes.'
        'Set response status to error if there is an error while processing the request and explain what the error is.'
        'Set response status to completed if the request is complete.'
    )

    def __init__(self):
        model_source = os.getenv("model_source", "google")
        if model_source == "google":
            self.model = ChatGoogleGenerativeAI(model='gemini-2.0-flash')
        else:
            self.model = ChatOpenAI(
                 model=os.getenv("TOOL_LLM_NAME"),
                 openai_api_key=os.getenv("API_KEY", "EMPTY"),
                 openai_api_base=os.getenv("TOOL_LLM_URL"),
                 temperature=0
             )
        
        # Use the correct URL for streamable-http transport
        self.server_url = "http://localhost:8000"
        
        # Store client and tools references
        self.client = None
        self.tools = None
        self.graph = None

    async def _initialize_tools(self):
        """Initialize MCP tools using MultiServerMCPClient."""
        if self.tools is None:
            # Use MultiServerMCPClient for streamable-http transport
            self.client = MultiServerMCPClient(
                {
                    "currency": {
                        "url": f"{self.server_url}/mcp/",
                        "transport": "streamable_http",
                    }
                }
            )
            
            self.tools = await self.client.get_tools()
            
            self.graph = create_react_agent(
                self.model,
                tools=self.tools,
                checkpointer=memory,
                prompt=self.SYSTEM_INSTRUCTION,
                response_format=ResponseFormat,
            )

    async def invoke(self, query, context_id) -> str:
        await self._initialize_tools()
        config = {'configurable': {'thread_id': context_id}}
        await self.graph.ainvoke({'messages': [('user', query)]}, config)
        return self.get_agent_response(config)

    async def stream(self, query, context_id) -> AsyncIterable[dict[str, Any]]:
        await self._initialize_tools()
        inputs = {'messages': [('user', query)]}
        config = {'configurable': {'thread_id': context_id}}

        async for item in self.graph.astream(inputs, config, stream_mode='values'):
            message = item['messages'][-1]
            if (
                isinstance(message, AIMessage)
                and message.tool_calls
                and len(message.tool_calls) > 0
            ):
                yield {
                    'is_task_complete': False,
                    'require_user_input': False,
                    'content': 'Looking up the exchange rates...',
                }
            elif isinstance(message, ToolMessage):
                yield {
                    'is_task_complete': False,
                    'require_user_input': False,
                    'content': 'Processing the exchange rates..',
                }

        yield self.get_agent_response(config)

    async def cleanup(self):
        """Clean up resources when done."""
        try:
            if self.client:
                await self.client.cleanup()
                self.client = None
                self.tools = None
        except Exception as e:
            print(f"Error cleaning up client: {e}")

    def get_agent_response(self, config):
        current_state = self.graph.get_state(config)
        structured_response = current_state.values.get('structured_response')
        print(f"Current state: {current_state}")
        print(f"Structured response: {structured_response}")
        if structured_response and isinstance(
            structured_response, ResponseFormat
        ):
            if structured_response.status == 'input_required':
                return {
                    'is_task_complete': False,
                    'require_user_input': True,
                    'content': structured_response.message,
                }
            if structured_response.status == 'error':
                return {
                    'is_task_complete': False,
                    'require_user_input': True,
                    'content': structured_response.message,
                }
            if structured_response.status == 'completed':
                return {
                    'is_task_complete': True,
                    'require_user_input': False,
                    'content': structured_response.message,
                }
        return {
            'is_task_complete': False,
            'require_user_input': True,
            'content': (
                'We are unable to process your request at the moment. '
                'Please try again.'
            ),
        }

    SUPPORTED_CONTENT_TYPES = ['text', 'text/plain']
