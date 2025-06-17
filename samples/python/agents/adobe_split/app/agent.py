"""
Copyright 2024 Adobe
All Rights Reserved.

NOTICE: Adobe permits you to use, modify, and distribute this file in
accordance with the terms of the Adobe license agreement accompanying it.
"""

import logging
import os
from datetime import datetime
from typing import Any, Any, AsyncIterable

from adobe.pdfservices.operation.auth.service_principal_credentials import ServicePrincipalCredentials
from adobe.pdfservices.operation.exception.exceptions import ServiceApiException, ServiceUsageException, SdkException
from adobe.pdfservices.operation.io.stream_asset import StreamAsset
from adobe.pdfservices.operation.pdf_services import PDFServices
from adobe.pdfservices.operation.pdf_services_media_type import PDFServicesMediaType
from adobe.pdfservices.operation.pdfjobs.jobs.split_pdf_job import SplitPDFJob
from adobe.pdfservices.operation.pdfjobs.params.page_ranges import PageRanges
from adobe.pdfservices.operation.pdfjobs.params.split_pdf.split_pdf_params import SplitPDFParams
from adobe.pdfservices.operation.pdfjobs.result.split_pdf_result import SplitPDFResult

from google.adk.agents.llm_agent import LlmAgent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.tool_context import ToolContext
from google.genai import types

# Initialize the logger
logging.basicConfig(level=logging.INFO)

def split_pdf(file_path: str, page_ranges: list[str]) -> dict[str, Any]:
    """Splits a PDF file into multiple documents based on page ranges.

    This tool uses the Adobe PDF Services API to perform the splitting
    operation. Adobe PDF Services credentials are pre-loaded as
    environment variables:
    - PDF_SERVICES_CLIENT_ID
    - PDF_SERVICES_CLIENT_SECRET

    Args:
        file_path: The local path to the PDF file you want to split.
        page_ranges: A list of strings, where each string defines a page
                     range. For example: ["1-2", "4", "6-"] to split
                     a PDF into three files. The last range "6-" means
                     page 6 to the end of the document.

    Returns:
        A dictionary with a list of the output file paths, or an error
        message if the operation fails.
    """
    file_path = os.path.abspath(os.path.expanduser(file_path))
    print(f"Splitting PDF file at: {file_path} with page ranges: {page_ranges}")

    if not os.path.exists(file_path):
        logging.error(f"File not found at path: {file_path}")
        return {"error": f"File not found at path: {file_path}"}

    output_dir = os.path.join(os.path.dirname(file_path), "output")
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
        except OSError as e:
            logging.exception(f"Failed to create output directory: {e}")
            return {"error": f"Failed to create output directory: {e}"}
    
    try:
        with open(file_path, 'rb') as file:
            input_stream = file.read()

        # Initial setup, create credentials instance
        credentials = ServicePrincipalCredentials(
            client_id=os.getenv('PDF_SERVICES_CLIENT_ID'),
            client_secret=os.getenv('PDF_SERVICES_CLIENT_SECRET')
        )

        # Creates a PDF Services instance
        pdf_services = PDFServices(credentials=credentials)

        # Creates an asset from source file and upload
        input_asset = pdf_services.upload(input_stream=input_stream,
                                          mime_type=PDFServicesMediaType.PDF)

        # Parse page ranges from string format to Adobe SDK format
        parsed_page_ranges = _parse_page_ranges(page_ranges)

        # Create parameters for the job
        split_pdf_params = SplitPDFParams(page_ranges=parsed_page_ranges)

        # Creates a new job instance
        split_pdf_job = SplitPDFJob(input_asset, split_pdf_params)

        # Submit the job and gets the job result
        location = pdf_services.submit(split_pdf_job)
        pdf_services_response = pdf_services.get_job_result(location, SplitPDFResult)

        # Get content from the resulting asset(s)
        result_assets = pdf_services_response.get_result().get_assets()
        
        output_file_paths = []
        for i, result_asset in enumerate(result_assets):
            stream_asset: StreamAsset = pdf_services.get_content(result_asset)
            output_file_path = os.path.join(output_dir, f"split_{i+1}.pdf")
            
            with open(output_file_path, "wb") as file:
                file.write(stream_asset.get_input_stream())
            
            output_file_paths.append(output_file_path)

        return {"output_files": output_file_paths}

    except (ServiceApiException, ServiceUsageException, SdkException) as e:
        logging.exception(f'Exception encountered while executing operation: {e}')
        return {"error": str(e)}
    except Exception as e:
        logging.exception(f'Unexpected error: {e}')
        return {"error": str(e)}


def _parse_page_ranges(page_ranges: list[str]) -> PageRanges:
    """Parse page range strings into Adobe SDK PageRanges object."""
    parsed_ranges = PageRanges()
    
    for range_str in page_ranges:
        range_str = range_str.strip()
        
        if '-' in range_str:
            parts = range_str.split('-', 1)
            start = int(parts[0]) if parts[0] else 1
            
            if parts[1]:  # End page specified (e.g., "1-5")
                end = int(parts[1])
                if start == end:
                    parsed_ranges.add_single_page(start)
                else:
                    parsed_ranges.add_range(start, end)
            else:  # No end page (e.g., "6-")
                parsed_ranges.add_all_from(start)
        else:
            # Single page (e.g., "3")
            page = int(range_str)
            parsed_ranges.add_single_page(page)
    
    return parsed_ranges


class PdfSplitAgent:
    """An agent that handles splitting PDF files."""

    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self):
        self._agent = self._build_agent()
        self._user_id = "pdf_split_user"
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )

    def get_processing_message(self) -> str:
        return "Processing the PDF split request..."

    def _build_agent(self) -> LlmAgent:
        """Builds the LLM agent for the PDF splitter."""
        return LlmAgent(
            model="gemini-2.5-flash-preview-05-20",
            name="pdf_split_agent",
            description=(
                "This agent handles splitting a PDF document into multiple smaller "
                "documents based on specified page ranges."
            ),
            instruction="""
            You are a specialized assistant for splitting PDF files.
            Your sole purpose is to use the 'split_pdf' tool to split a PDF document.

            When a user asks you to split a PDF, you must have two pieces of information:
            1. The file path of the PDF.
            2. The page ranges for splitting.

            If you have both pieces of information, call the `split_pdf` tool.
            If you are missing information, ask the user for it.
            
            After calling the tool, report the results to the user, either confirming
            the paths of the newly created files or relaying any errors that occurred.
            """,
            tools=[
                split_pdf,
            ],
        )

    async def stream(self, query: str, session_id: str) -> AsyncIterable[dict[str, Any]]:
        """Streams the agent's response to a given query."""
        session = await self._runner.session_service.get_session(
            app_name=self._agent.name,
            user_id=self._user_id,
            session_id=session_id,
        )
        content = types.Content(
            role="user", parts=[types.Part.from_text(text=query)]
        )
        if session is None:
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                state={},
                session_id=session_id,
            )
        async for event in self._runner.run_async(
            user_id=self._user_id, session_id=session.id, new_message=content
        ):
            if event.is_final_response():
                response = ""
                if (
                    event.content
                    and event.content.parts
                    and event.content.parts[0].text
                ):
                    response = "\n".join(
                        [p.text for p in event.content.parts if p.text]
                    )
                yield {
                    "is_task_complete": True,
                    "content": response,
                }
            else:
                yield {
                    "is_task_complete": False,
                    "content": self.get_processing_message(),
                }
