from collections.abc import AsyncIterable
from typing import Any, Literal

import httpx

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel


memory = MemorySaver()


@tool
def convert_units(
    value: float,
    from_unit: str,
    to_unit: str,
):
    """Use this to convert between different units of measurement.
    This tool utilizes the UCUM (Unified Code for Units of Measure) web service for conversions.
    Refer to UCUM documentation for valid unit notations (e.g., 'm' for meter, 'km' for kilometer, '[ft_i]' for international foot, 'cel' for Celsius, 'degF' for Fahrenheit).

    Args:
        value: The numeric value to convert.
        from_unit: The unit to convert from (e.g., "m", "kg", "cel", "[ft_i]").
        to_unit: The unit to convert to (e.g., "ft", "lb", "degF", "cm").

    Returns:
        A dictionary containing the conversion result, or an error message if
        the conversion fails.
    """
    try:
        # Construct the UCUM API URL
        # The value is placed directly in the URL path for UCUM
        url = f'https://ucum.nlm.nih.gov/ucum-service/v1/ucumtransform/{value}/from/{from_unit}/to/{to_unit}'
        
        response = httpx.get(url)
        response.raise_for_status()

        # UCUM API returns a plain text string with the result (e.g., "1.0 [in_i] = 2.54 cm")
        # We need to parse this string to extract the converted value.
        data = response.text.strip()
        print(f"UCUM API Raw Response: {data}")

        if "Result:" in data:
            # Example: "Result: 1.0 [in_i] = 2.54 cm"
            parts = data.split("=")
            if len(parts) == 2:
                converted_string = parts[1].strip()
                # Extract the numeric value from the converted string
                # This is a bit of a naive parse and might need refinement for complex cases
                converted_value_str = ""
                for char in converted_string:
                    if char.isdigit() or char == '.' or char == '-':
                        converted_value_str += char
                    elif converted_value_str: # Stop if we encounter a non-numeric character after numbers
                        break
                
                try:
                    converted_value = float(converted_value_str)
                except ValueError:
                    return {'error': f'Could not parse converted value from API response: {converted_string}'}
                
                return {
                    'original_value': value,
                    'from_unit': from_unit,
                    'to_unit': to_unit,
                    'converted_value': converted_value,
                    'conversion': data.replace("Result: ", "") # Clean up the "Result: " prefix
                }
            else:
                return {'error': f'Unexpected UCUM API response format: {data}'}
        else:
            # The UCUM service returns an error message if the conversion fails
            return {'error': f'UCUM API conversion failed: {data}'}

    except httpx.HTTPError as e:
        return {'error': f'API request failed: {e}'}
    except ValueError:
        return {'error': 'Invalid JSON response from API.'} # This error is less likely for UCUM as it's not JSON
    except Exception as e:
        return {'error': f'An unexpected error occurred: {e}'}


class ResponseFormat(BaseModel):
    """Respond to the user in this format."""

    status: Literal['input_required', 'completed', 'error'] = 'input_required'
    message: str


class UnitConversionAgent:
    """UnitConversionAgent - a specialized assistant for unit conversions.
    
    This agent uses the UCUM (Unified Code for Units of Measure) web service 
    to perform accurate unit conversions between different measurement systems.
    
    Capabilities:
        - Convert between length, weight, temperature, volume, area units
        - Supports UCUM notation (e.g., 'm' for meter, 'cel' for Celsius, '[ft_i]' for foot)
        - Handles error cases and provides informative responses
    
    Limitations:
        - Only performs unit conversions, cannot assist with other topics
        - Requires valid UCUM unit notation for accurate conversions
    """

    SYSTEM_INSTRUCTION = (
        'You are a specialized assistant for unit conversions using the UCUM (Unified Code for Units of Measure) system. '
        "Your sole purpose is to use the 'convert_units' tool to answer questions about converting between different units of measurement. "
        'You can convert between length, weight, temperature, volume, area, and other measurement units using valid UCUM notation. '
        'Automatically use the appropriate UCUM notation for the units provided by the user if the unit exists in the UCUM service. '
        'Examples of valid UCUM units: "m" (meter), "km" (kilometer), "[ft_i]" (international foot), "cel" (Celsius), "degF" (Fahrenheit), "kg" (kilogram), "lb" (pound). '
        'If the user asks about anything other than unit conversion, politely state that you cannot help with that topic and can only assist with unit conversion queries. '
        'Do not attempt to answer unrelated questions or use tools for other purposes. '
        'Set response status to input_required if the user needs to provide more information (like specifying units or values). '
        'Set response status to error if there is an error while processing the request. '
        'Set response status to completed if the conversion request is successfully processed.'
    )

    def __init__(self):
        self.model = ChatGoogleGenerativeAI(model='gemini-2.0-flash')
        self.tools = [convert_units]

        self.graph = create_react_agent(
            self.model,
            tools=self.tools,
            checkpointer=memory,
            prompt=self.SYSTEM_INSTRUCTION,
            response_format=ResponseFormat,
        )

    def invoke(self, query, context_id) -> str:
        config = {'configurable': {'thread_id': context_id}}
        self.graph.invoke({'messages': [('user', query)]}, config)
        return self.get_agent_response(config)

    async def stream(self, query, context_id) -> AsyncIterable[dict[str, Any]]:
        inputs = {'messages': [('user', query)]}
        config = {'configurable': {'thread_id': context_id}}

        for item in self.graph.stream(inputs, config, stream_mode='values'):
            message = item['messages'][-1]
            if (
                isinstance(message, AIMessage)
                and message.tool_calls
                and len(message.tool_calls) > 0
            ):
                yield {
                    'is_task_complete': False,
                    'require_user_input': False,
                    'content': 'Converting units...',
                }
            elif isinstance(message, ToolMessage):
                yield {
                    'is_task_complete': False,
                    'require_user_input': False,
                    'content': 'Processing the conversion...',
                }

        yield self.get_agent_response(config)

    def get_agent_response(self, config):
        current_state = self.graph.get_state(config)
        structured_response = current_state.values.get('structured_response')
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
