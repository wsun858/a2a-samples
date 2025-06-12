from collections.abc import AsyncIterable
from typing import Any, Literal

import httpx
import os

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel

# Create server parameters for stdio connection
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools
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
        # 'Set response status to input_required if the user needs to provide more information.'
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
        
        self.server_params = StdioServerParameters(
            command="python",
            args=["/Users/wsun/Desktop/UW/Research/a2a-samples/samples/python/agents/langgraph/app/mcp_currency_server.py"],
        )
        
        # Store session and tools references
        self.session = None
        self.tools = None
        self.graph = None

    async def _initialize_tools(self):
        """Initialize MCP tools and keep the session alive."""
        if self.tools is None:
            # Store the context manager itself, not just the streams
            self.stdio_client_cm = stdio_client(self.server_params)
            self.read, self.write = await self.stdio_client_cm.__aenter__()
            
            self.session_cm = ClientSession(self.read, self.write)
            self.session = await self.session_cm.__aenter__()
            
            await self.session.initialize()
            self.tools = await load_mcp_tools(self.session)
            print(f"Loaded tools: {self.tools}")
            
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
            if hasattr(self, 'session_cm') and self.session_cm:
                await self.session_cm.__aexit__(None, None, None)
                self.session_cm = None
                self.session = None
        except Exception as e:
            print(f"Error cleaning up session: {e}")
        
        try:
            if hasattr(self, 'stdio_client_cm') and self.stdio_client_cm:
                await self.stdio_client_cm.__aexit__(None, None, None)
                self.stdio_client_cm = None
                if hasattr(self, 'read'):
                    self.read = None
                if hasattr(self, 'write'):
                    self.write = None
        except Exception as e:
            print(f"Error cleaning up stdio client: {e}")

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
