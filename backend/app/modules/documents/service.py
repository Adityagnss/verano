"""
Reference-document use cases: extract a document's text into sections (a background job),
list a document's sections, and the project's sections the Eval Generator grounds cases in.

Extraction reads the stored upload through its format's extractor, which enforces the
page, text and zip limits and the parse deadline, splits the text into sections, and
replaces the document's sections in one transaction. The file's status lives with the
datasets module, which this service updates through its processor; failures are recorded
there with a clear message. Sections are what generated test cases are grounded in.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.container import Container
from app.core.errors import AppError
from app.core.files import Deadline, zip_limits
from app.core.ids import uuid7
from app.core.pagination import Page, PageParams, to_page
from app.core.registry import load_plugins
from app.core.storage import Storage
from app.modules.datasets.ingest import FileIngestService
from app.modules.datasets.processing import FileProcessor
from app.modules.documents.domain import split_sections
from app.modules.documents.plugins.base import DOCUMENT_EXTRACTORS, DocumentLimits
from app.modules.documents.repository import DocumentRepository
from app.modules.documents.schemas import SectionOut
from app.modules.projects.schemas import ProjectOut

load_plugins("app.modules.documents.plugins")


class DocumentService:
    def __init__(
        self,
        session: AsyncSession,
        storage: Storage,
        settings: Settings,
        files: FileIngestService,
        processor: FileProcessor,
    ) -> None:
        self._session = session
        self._repo = DocumentRepository(session)
        self._storage = storage
        self._settings = settings
        self._files = files
        self._processor = processor

    @classmethod
    def from_container(cls, session: AsyncSession, container: Container) -> "DocumentService":
        files = FileIngestService.from_container(session, container)
        processor = FileProcessor.from_container(session, container)
        return cls(session, container.storage, container.settings, files, processor)

    def _limits(self) -> DocumentLimits:
        settings = self._settings
        return DocumentLimits(
            max_pages=settings.document_max_pages, max_chars=settings.document_max_chars, zip=zip_limits(settings)
        )

    async def extract(self, file_id: uuid.UUID) -> None:
        try:
            await self._extract(file_id)
        except AppError as exc:
            await self._processor.fail(file_id, "extract", exc.message)

    async def _extract(self, file_id: uuid.UUID) -> None:
        stored = await self._processor.stored_file(file_id)
        await self._processor.mark_extracting(file_id)
        deadline = Deadline(self._settings.file_parse_timeout_s)
        async with self._storage.local_path(stored.storage_key) as path:
            blocks = DOCUMENT_EXTRACTORS[stored.format]().extract(path, self._limits(), deadline)
        sections = split_sections(blocks, self._settings.document_section_max_chars)
        rows = [
            {
                "id": uuid7(),
                "input_file_id": file_id,
                "position": position,
                "title": section.title,
                "text": section.text,
                "char_count": len(section.text),
            }
            for position, section in enumerate(sections)
        ]
        await self._repo.replace_sections(file_id, rows)
        await self._processor.mark_extracted(file_id, len(rows))

    async def sections(self, project: ProjectOut, file_id: uuid.UUID, page: PageParams) -> Page[SectionOut]:
        await self._files.get_file(project, file_id)
        rows = await self._repo.sections(file_id, page)
        return to_page([SectionOut.model_validate(row) for row in rows], page, lambda item: item.id)

    async def project_sections(self, project_id: uuid.UUID, limit: int) -> list[SectionOut]:
        return [SectionOut.model_validate(row) for row in await self._repo.project_sections(project_id, limit)]
