import logging
import os
import sys

import click
import httpx
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryPushNotifier, InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from dotenv import load_dotenv

from app.agent import PdfSplitAgent
from app.agent_executor import PdfSplitAgentExecutor


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MissingAPIKeyError(Exception):
    """Exception for missing API key."""


@click.command()
@click.option('--host', 'host', default='localhost')
@click.option('--port', 'port', default=10100)
def main(host, port):
    """Starts the PDF Split Agent server."""
    try:
        if not os.getenv('GOOGLE_API_KEY'):
            raise MissingAPIKeyError(
                'GOOGLE_API_KEY environment variable not set.'
            )
        
        if not os.getenv('PDF_SERVICES_CLIENT_ID'):
            raise MissingAPIKeyError(
                'PDF_SERVICES_CLIENT_ID environment variable not set.'
            )
        
        if not os.getenv('PDF_SERVICES_CLIENT_SECRET'):
            raise MissingAPIKeyError(
                'PDF_SERVICES_CLIENT_SECRET environment variable not set.'
            )

        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        skill = AgentSkill(
            id='split_pdf',
            name='PDF Split Tool',
            description='Splits PDF documents into multiple smaller documents based on page ranges',
            tags=['pdf', 'document splitting', 'adobe pdf services'],
            examples=[
                'Split document.pdf into pages 1-5 and 6-10',
                'Split my presentation.pdf at pages 1-3, 4-7, and 8 to end'
            ],
        )
        agent_card = AgentCard(
            name='PDF Split Agent',
            description='Splits PDF documents into multiple smaller documents using Adobe PDF Services',
            url=f'http://{host}:{port}/',
            version='1.0.0',
            defaultInputModes=PdfSplitAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=PdfSplitAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )

        # --8<-- [start:DefaultRequestHandler]
        httpx_client = httpx.AsyncClient()
        request_handler = DefaultRequestHandler(
            agent_executor=PdfSplitAgentExecutor(),
            task_store=InMemoryTaskStore(),
            push_notifier=InMemoryPushNotifier(httpx_client),
        )
        server = A2AStarletteApplication(
            agent_card=agent_card, http_handler=request_handler
        )

        uvicorn.run(server.build(), host=host, port=port)
        # --8<-- [end:DefaultRequestHandler]

    except MissingAPIKeyError as e:
        logger.error(f'Error: {e}')
        sys.exit(1)
    except Exception as e:
        logger.error(f'An error occurred during server startup: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
