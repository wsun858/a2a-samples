# import asyncio
# import json
# import logging
# from contextlib import asynccontextmanager
# from typing import Any, Dict

# import httpx
# import uvicorn
# from fastapi import FastAPI
# from fastapi.responses import StreamingResponse
# from mcp import ClientSession, StdioServerParameters
# from mcp.client.stdio import stdio_client

# # Configure logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)


# class MCPExchangeRateServer:
#     """MCP Server implementation for exchange rate tool."""
    
#     def __init__(self):
#         self.session: ClientSession | None = None
    
#     async def start_server(self):
#         """Start the MCP server session."""
#         server_params = StdioServerParameters(
#             command="python",
#             args=["-m", "mcp_exchange_server"],
#             env=None
#         )
        
#         self.session = await stdio_client(server_params)
#         await self.session.initialize()
        
#         # Register the exchange rate tool
#         await self.session.create_message({
#             "jsonrpc": "2.0",
#             "id": 1,
#             "method": "tools/list",
#             "params": {}
#         })
    
#     async def get_exchange_rate(
#         self,
#         currency_from: str = "USD",
#         currency_to: str = "EUR", 
#         currency_date: str = "latest"
#     ) -> Dict[str, Any]:
#         """Get exchange rate using MCP tool call."""
#         try:
#             if not self.session:
#                 await self.start_server()
            
#             # Call the MCP tool
#             response = await self.session.call_tool(
#                 "get_exchange_rate",
#                 {
#                     "currency_from": currency_from,
#                     "currency_to": currency_to,
#                     "currency_date": currency_date
#                 }
#             )
            
#             return response.content[0].text if response.content else {"error": "No response from MCP tool"}
            
#         except Exception as e:
#             logger.error(f"MCP tool call failed: {e}")
#             # Fallback to direct API call
#             return await self._direct_api_call(currency_from, currency_to, currency_date)
    
#     async def _direct_api_call(
#         self,
#         currency_from: str,
#         currency_to: str, 
#         currency_date: str
#     ) -> Dict[str, Any]:
#         """Direct API call as fallback."""
#         try:
#             async with httpx.AsyncClient() as client:
#                 response = await client.get(
#                     f'https://api.frankfurter.app/{currency_date}',
#                     params={'from': currency_from, 'to': currency_to},
#                 )
#                 response.raise_for_status()
                
#                 data = response.json()
#                 if 'rates' not in data:
#                     return {'error': 'Invalid API response format.'}
#                 return data
#         except httpx.HTTPError as e:
#             return {'error': f'API request failed: {e}'}
#         except ValueError:
#             return {'error': 'Invalid JSON response from API.'}


# # Global MCP server instance
# mcp_server = MCPExchangeRateServer()


# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     """Manage MCP server lifecycle."""
#     try:
#         await mcp_server.start_server()
#         logger.info("MCP Exchange Rate Server started")
#         yield
#     finally:
#         if mcp_server.session:
#             await mcp_server.session.close()
#         logger.info("MCP Exchange Rate Server stopped")


# # FastAPI app with SSE support
# app = FastAPI(title="MCP Exchange Rate SSE Server", lifespan=lifespan)


# @app.get("/")
# async def health_check():
#     """Health check endpoint."""
#     return {"status": "healthy", "service": "MCP Exchange Rate SSE Server"}


# @app.get("/exchange-rate/stream")
# async def stream_exchange_rate(
#     currency_from: str = "USD",
#     currency_to: str = "EUR",
#     currency_date: str = "latest"
# ):
#     """Stream exchange rate data via SSE."""
    
#     async def event_stream():
#         try:
#             # Send initial status
#             yield f"data: {json.dumps({'status': 'processing', 'message': 'Fetching exchange rate...'})}\n\n"
            
#             # Get exchange rate using MCP tool
#             result = await mcp_server.get_exchange_rate(currency_from, currency_to, currency_date)
            
#             # Send result
#             if 'error' in result:
#                 yield f"data: {json.dumps({'status': 'error', 'error': result['error']})}\n\n"
#             else:
#                 yield f"data: {json.dumps({'status': 'success', 'data': result})}\n\n"
            
#             # Send completion event
#             yield f"data: {json.dumps({'status': 'completed'})}\n\n"
            
#         except Exception as e:
#             logger.error(f"Stream error: {e}")
#             yield f"data: {json.dumps({'status': 'error', 'error': str(e)})}\n\n"
    
#     return StreamingResponse(
#         event_stream(),
#         media_type="text/event-stream",
#         headers={
#             "Cache-Control": "no-cache",
#             "Connection": "keep-alive",
#             "Access-Control-Allow-Origin": "*",
#             "Access-Control-Allow-Headers": "*",
#         }
#     )


# @app.post("/exchange-rate")
# async def get_exchange_rate_endpoint(
#     currency_from: str = "USD",
#     currency_to: str = "EUR",
#     currency_date: str = "latest"
# ):
#     """Get exchange rate via regular HTTP endpoint."""
#     result = await mcp_server.get_exchange_rate(currency_from, currency_to, currency_date)
#     return result


# if __name__ == "__main__":
#     uvicorn.run(
#         "mcp_sse_server:app",
#         host="0.0.0.0",
#         port=8000,
#         reload=True,
#         log_level="info"
#     )