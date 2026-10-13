"""
File ingestion, user-facing side: upload, sheet choice, column mapping, import and progress.

An upload is streamed to storage (never held in memory), its type is checked against the
card it was dropped on and against its own leading bytes, and it is queued for profiling
(rows files) or text extraction (documents). A status change is committed before its job
is queued, so a worker can never pick up a file the database doesn't show yet. Mapping
problems are reported all at once, before any row is read. Progress for every stage
streams from the shared progress hub on the file's channel; a file whose work already
finished is answered from the database.
The background passes themselves are in `processing.py`.
"""

import uuid
from collections.abc import AsyncIterator
from pathlib import Path, PurePath

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.container import Container
from app.core.datafiles import load_yaml
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.files import UnsafeFile, check_magic
from app.core.ids import uuid7
from app.core.jobs import JobQueue
from app.core.pagination import Page, PageParams, to_page
from app.core.progress import ProgressEvent, ProgressHub, ProgressStatus
from app.core.security import Principal
from app.core.storage import Storage
from app.modules.datasets.domain import ColumnSynonyms, mapping_problems, suggest_mapping
from app.modules.datasets.models import InputFile
from app.modules.datasets.repository import DatasetRepository
from app.modules.datasets.schemas import (
    FileFormat,
    FileProfile,
    InputFileKind,
    InputFileOut,
    InputFileStatus,
    MappingRequest,
    MappingSuggestion,
    UploadPurpose,
)
from app.modules.projects.schemas import ProjectOut

CONFIG = Path(__file__).parent / "config"
FILE_NOT_FOUND = "This file doesn't exist in this project."
UNKNOWN_TYPE = "'{name}' isn't a supported file type. Use {labels}."
WRONG_CARD = "This card takes {labels} files."
NOT_READY = "This file isn't ready for that yet (it is {status})."
MAPPING_INVALID = "The column mapping needs a few fixes before the entries can be checked."
FILENAME_MAX = 500
TERMINAL = {
    InputFileStatus.READY: "profile",
    InputFileStatus.VALIDATED: "validate",
    InputFileStatus.IMPORTED: "import",
    InputFileStatus.EXTRACTED: "extract",
    InputFileStatus.FAILED: "failed",
}
MAPPABLE = {InputFileStatus.READY, InputFileStatus.VALIDATED, InputFileStatus.IMPORTED, InputFileStatus.FAILED}
JOB_FOR_PURPOSE = {
    UploadPurpose.INPUT: "datasets.attach_file",
    UploadPurpose.INPUT_ROWS: "datasets.attach_rows",
    UploadPurpose.GOLDEN: "datasets.profile_file",
    UploadPurpose.DOCUMENT: "documents.extract",
}
KIND_FOR_PURPOSE = {
    UploadPurpose.INPUT: InputFileKind.RAW_INPUTS,
    UploadPurpose.INPUT_ROWS: InputFileKind.RAW_INPUTS,
    UploadPurpose.GOLDEN: InputFileKind.GOLDEN_SET,
    UploadPurpose.DOCUMENT: InputFileKind.REFERENCE_DOCUMENT,
}


class FormatSpec(BaseModel):
    purposes: list[UploadPurpose]
    label: str
    extensions: list[str]
    signature: str | None = None


class FormatCatalog(BaseModel):
    formats: dict[FileFormat, FormatSpec]

    def detect(self, filename: str) -> tuple[FileFormat, FormatSpec] | None:
        suffix = PurePath(filename).suffix.lower()
        return next(((fmt, spec) for fmt, spec in self.formats.items() if suffix in spec.extensions), None)

    def labels(self, purpose: UploadPurpose | None = None) -> str:
        return ", ".join(spec.label for spec in self.formats.values() if purpose is None or purpose in spec.purposes)


def channel(file_id: uuid.UUID) -> str:
    return f"input-file:{file_id}"


def file_out(row: InputFile) -> InputFileOut:
    return InputFileOut.model_validate(row)


class FileIngestService:
    def __init__(
        self,
        session: AsyncSession,
        storage: Storage,
        jobs: JobQueue,
        progress: ProgressHub,
        settings: Settings,
    ) -> None:
        self._session = session
        self._repo = DatasetRepository(session)
        self._storage = storage
        self._jobs = jobs
        self._progress = progress
        self._settings = settings
        self.formats = load_yaml(CONFIG / "formats.yaml", FormatCatalog)
        self._synonyms = load_yaml(CONFIG / "column_synonyms.yaml", ColumnSynonyms)

    @classmethod
    def from_container(cls, session: AsyncSession, container: Container) -> "FileIngestService":
        return cls(session, container.storage, container.jobs, container.progress, container.settings)

    async def upload(
        self,
        project: ProjectOut,
        principal: Principal,
        purpose: UploadPurpose,
        filename: str,
        content_type: str,
        chunks: AsyncIterator[bytes],
    ) -> InputFileOut:
        detected = self.formats.detect(filename)
        if detected is None:
            raise ValidationFailed(UNKNOWN_TYPE.format(name=filename, labels=self.formats.labels()))
        file_format, spec = detected
        if purpose not in spec.purposes:
            raise ValidationFailed(WRONG_CARD.format(labels=self.formats.labels(purpose)))
        file_id = uuid7()
        prefix = f"projects/{project.id}/input-files/{file_id}"
        stored = await self._storage.write_stream(
            f"{prefix}/original{PurePath(filename).suffix.lower()}", chunks, self._settings.upload_max_bytes
        )
        await self._check_signature(stored.key, prefix, spec)
        row = InputFile(
            id=file_id,
            project_id=project.id,
            kind=KIND_FOR_PURPOSE[purpose],
            status=InputFileStatus.UPLOADED,
            format=file_format,
            filename=PurePath(filename).name[:FILENAME_MAX],
            content_type=content_type[:200],
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
            storage_key=stored.key,
            created_by=principal.user_id,
        )
        await self._repo.add(row)
        await self._session.commit()
        self._jobs.enqueue(JOB_FOR_PURPOSE[purpose], file_id=str(file_id))
        return file_out(row)

    async def _check_signature(self, key: str, prefix: str, spec: FormatSpec) -> None:
        try:
            async with self._storage.local_path(key) as path:
                check_magic(path, bytes.fromhex(spec.signature) if spec.signature else None, spec.label)
        except UnsafeFile:
            await self._storage.delete_prefix(prefix)
            raise

    async def list_files(self, project: ProjectOut, page: PageParams) -> Page[InputFileOut]:
        rows = await self._repo.files(project.id, page)
        return to_page([file_out(row) for row in rows], page, lambda item: item.id)

    async def get_file(self, project: ProjectOut, file_id: uuid.UUID) -> InputFileOut:
        return file_out(await self._file(file_id, project.id))

    async def delete_file(self, project: ProjectOut, file_id: uuid.UUID) -> None:
        row = await self._file(file_id, project.id)
        if row.dataset_version_id is not None:
            await self._repo.delete_file_items(row.dataset_version_id, row.id)
            if row.kind is InputFileKind.GOLDEN_SET:
                await self._repo.unpair_golden(row.dataset_version_id, row.id, self._settings.dataset_default_category)
        await self._repo.delete_file(row.id)
        await self._storage.delete_prefix(str(PurePath(row.storage_key).parent))

    async def select_sheet(self, project: ProjectOut, file_id: uuid.UUID, sheet: str) -> InputFileOut:
        row = await self._require(file_id, project.id, MAPPABLE)
        await self._repo.update_file(row.id, {"status": InputFileStatus.PROFILING, "sheet_name": sheet})
        await self._session.commit()
        self._jobs.enqueue("datasets.profile_file", file_id=str(row.id))
        return file_out(await self._file(row.id))

    async def suggest_mapping(self, project: ProjectOut, file_id: uuid.UUID) -> MappingSuggestion:
        row = await self._require(file_id, project.id, MAPPABLE)
        return MappingSuggestion(mapping=suggest_mapping(self._profile(row).columns, self._synonyms))

    async def submit_mapping(self, project: ProjectOut, file_id: uuid.UUID, body: MappingRequest) -> InputFileOut:
        row = await self._require(file_id, project.id, MAPPABLE)
        problems = mapping_problems(body.mapping, self._profile(row).columns)
        if problems:
            raise ValidationFailed(MAPPING_INVALID, {"problems": problems})
        values = {
            "column_mapping": body.mapping.model_dump(),
            "status": InputFileStatus.VALIDATING,
            "validation_report": None,
            "error_message": None,
        }
        await self._repo.update_file(row.id, values)
        await self._session.commit()
        self._jobs.enqueue("datasets.validate_file", file_id=str(row.id))
        return file_out(await self._file(row.id))

    async def start_import(self, project: ProjectOut, file_id: uuid.UUID) -> InputFileOut:
        row = await self._require(file_id, project.id, {InputFileStatus.VALIDATED, InputFileStatus.IMPORTED})
        await self._repo.update_file(row.id, {"status": InputFileStatus.IMPORTING})
        await self._session.commit()
        self._jobs.enqueue("datasets.import_file", file_id=str(row.id))
        return file_out(await self._file(row.id))

    async def progress(self, project: ProjectOut, file_id: uuid.UUID) -> AsyncIterator[ProgressEvent | None]:
        """Reads the file before streaming starts; the stream itself only reads the progress hub."""
        row = await self._file(file_id, project.id)
        if row.status in TERMINAL and await self._progress.snapshot(channel(row.id)) is None:
            return _once(self._settled_event(row))
        return self._progress.stream(channel(row.id), self._settings.sse_keepalive_s)

    @staticmethod
    def _settled_event(row: InputFile) -> ProgressEvent:
        failed = row.status is InputFileStatus.FAILED
        return ProgressEvent(
            stage=TERMINAL[row.status],
            status=ProgressStatus.FAILED if failed else ProgressStatus.SUCCEEDED,
            processed=row.imported_rows or row.row_count or 0,
            total=row.row_count,
            message=row.error_message,
        )

    def _profile(self, row: InputFile) -> FileProfile:
        if row.profile is None:
            raise Conflict(NOT_READY.format(status=row.status.value))
        return FileProfile.model_validate(row.profile)

    async def _require(self, file_id: uuid.UUID, project_id: uuid.UUID, allowed: set[InputFileStatus]) -> InputFile:
        row = await self._file(file_id, project_id)
        if row.status not in allowed:
            raise Conflict(NOT_READY.format(status=row.status.value))
        return row

    async def _file(self, file_id: uuid.UUID, project_id: uuid.UUID | None = None) -> InputFile:
        row = await self._repo.file(file_id, project_id)
        if row is None:
            raise NotFound(FILE_NOT_FOUND)
        return row


async def _once(event: ProgressEvent) -> AsyncIterator[ProgressEvent | None]:
    yield event
