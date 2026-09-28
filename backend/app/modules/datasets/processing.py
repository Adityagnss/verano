"""
File ingestion, background side: the passes that read a rows file (profile, validate,
import), plus the status updates the documents module uses while extracting text.

Each pass streams the file row by row through its reader, checks the parse deadline on
every row, and publishes progress every `progress_every_rows` rows. Validation and import
share one definition of a valid row (`domain.evaluate_row`) and of a duplicate, so the
import writes exactly the rows the report promised. The import replaces this file's items
in the project's draft dataset inside one transaction: if the worker dies halfway, nothing
is half-written, and running the job again gives the same result. Any failure leaves the
file `failed` with a message that says what to do.
"""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.container import Container
from app.core.errors import AppError, NotFound
from app.core.files import Deadline, zip_limits
from app.core.ids import uuid7
from app.core.progress import ProgressEvent, ProgressHub, ProgressStatus
from app.core.registry import load_plugins
from app.core.storage import Storage
from app.modules.datasets.domain import ItemDraft, ReportBuilder, duplicate_key, evaluate_row
from app.modules.datasets.ingest import channel
from app.modules.datasets.models import InputFile
from app.modules.datasets.plugins.importers.base import ROW_READERS, ProfileBuilder, ReadLimits, ReadOptions, RowStream
from app.modules.datasets.repository import DatasetRepository
from app.modules.datasets.schemas import (
    ColumnMapping,
    FileProfile,
    InputFileKind,
    InputFileStatus,
    ItemSource,
    ReviewStatus,
    StoredFile,
    ValidationReport,
)
from app.modules.datasets.service import DatasetService
from app.modules.prompts.service import PromptService
from app.modules.registry.service import RegistryService

load_plugins("app.modules.datasets.plugins.importers")

FILE_NOT_FOUND = "This file no longer exists."
NO_MAPPING = "This file has no confirmed column mapping yet."
SOURCE_FOR_KIND = {InputFileKind.GOLDEN_SET: ItemSource.GOLDEN, InputFileKind.RAW_INPUTS: ItemSource.INPUT_FILE}
REVIEW_FOR_KIND = {InputFileKind.GOLDEN_SET: ReviewStatus.TRUSTED, InputFileKind.RAW_INPUTS: ReviewStatus.DRAFT}


class Ticker:
    def __init__(self, deadline: Deadline, publish: Callable[[int], Awaitable[None]], every: int) -> None:
        self._deadline = deadline
        self._publish = publish
        self._every = every

    async def tick(self, count: int) -> None:
        self._deadline.check()
        if count % self._every == 0:
            await self._publish(count)


class FileProcessor:
    def __init__(
        self,
        session: AsyncSession,
        storage: Storage,
        progress: ProgressHub,
        settings: Settings,
        prompts: PromptService,
        datasets: DatasetService,
    ) -> None:
        self._session = session
        self._repo = DatasetRepository(session)
        self._storage = storage
        self._progress = progress
        self._settings = settings
        self._prompts = prompts
        self._datasets = datasets

    @classmethod
    def from_container(cls, session: AsyncSession, container: Container) -> "FileProcessor":
        prompts = PromptService(session, RegistryService(session, container), container.settings)
        datasets = DatasetService(session, container.settings)
        return cls(session, container.storage, container.progress, container.settings, prompts, datasets)

    async def run(self, stage: str, file_id: uuid.UUID, work: Callable[[uuid.UUID], Awaitable[None]]) -> None:
        try:
            await work(file_id)
        except AppError as exc:
            await self.fail(file_id, stage, exc.message)

    async def profile(self, file_id: uuid.UUID) -> None:
        row = await self._stage(file_id, InputFileStatus.PROFILING, "profile")
        ticker = self._ticker(row, "profile")
        async with self._rows(row) as stream:
            builder = ProfileBuilder(stream, self._limits())
            for count, source in enumerate(stream.rows, start=1):
                await ticker.tick(count)
                builder.add(source)
            profile = builder.build(row.format)
        values = {"status": InputFileStatus.READY, "profile": profile.model_dump(), "row_count": profile.row_count}
        await self._finish(row, values, self._done("profile", profile.row_count, profile.row_count))

    async def validate(self, file_id: uuid.UUID) -> None:
        row = await self._stage(file_id, InputFileStatus.VALIDATING, "validate")
        report = ReportBuilder(max_listed=self._settings.report_max_listed_rows)
        async with self._rows(row) as stream:
            async for _ in self._valid_items(row, stream, report, self._ticker(row, "validate")):
                pass
        built = self._report(row, stream, report)
        values = {"status": InputFileStatus.VALIDATED, "validation_report": built.model_dump()}
        await self._finish(row, values, self._done("validate", built.total_rows, row.row_count))

    async def import_rows(self, file_id: uuid.UUID) -> None:
        row = await self._stage(file_id, InputFileStatus.IMPORTING, "import")
        version = await self._datasets.ensure_draft(row.project_id)
        await self._repo.delete_file_items(version.id, row.id)
        position = await self._repo.next_position(version.id)
        report = ReportBuilder(max_listed=self._settings.report_max_listed_rows)
        batch: list[dict[str, Any]] = []
        async with self._rows(row) as stream:
            async for item in self._valid_items(row, stream, report, self._ticker(row, "import")):
                batch.append(self._item_values(row, version.id, item, position + len(batch)))
                if len(batch) >= self._settings.import_batch_size:
                    await self._repo.insert_items(batch)
                    position, batch = position + len(batch), []
        await self._repo.insert_items(batch)
        built = self._report(row, stream, report)
        values = {
            "status": InputFileStatus.IMPORTED,
            "validation_report": built.model_dump(),
            "imported_rows": built.valid_rows,
            "dataset_version_id": version.id,
        }
        await self._finish(row, values, self._done("import", built.valid_rows, built.total_rows))

    async def _valid_items(
        self, row: InputFile, stream: RowStream, report: ReportBuilder, ticker: Ticker
    ) -> AsyncIterator[ItemDraft]:
        if row.prompt_version_id is None or row.column_mapping is None:
            raise NotFound(NO_MAPPING)
        mapping = ColumnMapping.model_validate(row.column_mapping)
        required = (await self._prompts.get_version(row.project_id, row.prompt_version_id)).required_inputs
        default_category = self._settings.dataset_default_category
        seen: set[bytes] = set()
        for count, source in enumerate(stream.rows, start=1):
            await ticker.tick(count)
            outcome = evaluate_row(source, mapping, required, default_category)
            if isinstance(outcome, list):
                report.reject(source.number, outcome)
            elif (key := duplicate_key(outcome)) in seen:
                report.duplicate(source.number)
            else:
                seen.add(key)
                report.accept()
                yield outcome

    @staticmethod
    def _item_values(row: InputFile, version_id: uuid.UUID, item: ItemDraft, position: int) -> dict[str, Any]:
        return {
            "id": uuid7(),
            "dataset_version_id": version_id,
            "inputs": item.inputs,
            "expected_output": item.expected_output,
            "rubric": item.rubric,
            "category": item.category,
            "tags": item.tags,
            "source": SOURCE_FOR_KIND[row.kind],
            "review_status": REVIEW_FOR_KIND[row.kind],
            "split": None,
            "input_file_id": row.id,
            "source_row": item.source_row,
            "context": [],
            "extra": item.extra,
            "position": position,
        }

    @staticmethod
    def _report(row: InputFile, stream: RowStream, report: ReportBuilder) -> ValidationReport:
        profile = FileProfile.model_validate(row.profile)
        return report.build(row.kind, row.format, profile.encoding, stream.sheet, profile.warnings)

    def _limits(self) -> ReadLimits:
        settings = self._settings
        return ReadLimits(
            max_rows=settings.upload_max_rows,
            field_max_chars=settings.csv_field_max_chars,
            zip=zip_limits(settings),
            sample_rows=settings.profile_sample_rows,
        )

    @asynccontextmanager
    async def _rows(self, row: InputFile) -> AsyncIterator[RowStream]:
        async with self._storage.local_path(row.storage_key) as path:
            with ROW_READERS[row.format]().open(path, ReadOptions(sheet=row.sheet_name), self._limits()) as stream:
                yield stream

    def _ticker(self, row: InputFile, stage: str) -> Ticker:
        async def publish(count: int) -> None:
            event = ProgressEvent(stage=stage, status=ProgressStatus.RUNNING, processed=count, total=row.row_count)
            await self._progress.publish(channel(row.id), event)

        return Ticker(Deadline(self._settings.file_parse_timeout_s), publish, self._settings.progress_every_rows)

    @staticmethod
    def _done(stage: str, processed: int, total: int | None) -> ProgressEvent:
        return ProgressEvent(stage=stage, status=ProgressStatus.SUCCEEDED, processed=processed, total=total)

    async def _stage(self, file_id: uuid.UUID, status: InputFileStatus, stage: str) -> InputFile:
        row = await self._repo.file(file_id)
        if row is None:
            raise NotFound(FILE_NOT_FOUND)
        await self._repo.update_file(file_id, {"status": status, "error_message": None})
        await self._session.commit()
        started = ProgressEvent(stage=stage, status=ProgressStatus.RUNNING, total=row.row_count)
        await self._progress.publish(channel(file_id), started)
        return row

    async def _finish(self, row: InputFile, values: dict[str, Any], event: ProgressEvent) -> None:
        await self._repo.update_file(row.id, values)
        await self._session.commit()
        await self._progress.publish(channel(row.id), event)

    async def fail(self, file_id: uuid.UUID, stage: str, message: str) -> None:
        await self._session.rollback()
        await self._repo.update_file(file_id, {"status": InputFileStatus.FAILED, "error_message": message})
        await self._session.commit()
        await self._progress.publish(
            channel(file_id), ProgressEvent(stage=stage, status=ProgressStatus.FAILED, message=message)
        )

    async def stored_file(self, file_id: uuid.UUID) -> StoredFile:
        row = await self._repo.file(file_id)
        if row is None:
            raise NotFound(FILE_NOT_FOUND)
        return StoredFile(
            id=row.id, project_id=row.project_id, format=row.format, storage_key=row.storage_key, filename=row.filename
        )

    async def mark_extracting(self, file_id: uuid.UUID) -> None:
        await self._stage(file_id, InputFileStatus.EXTRACTING, "extract")

    async def mark_extracted(self, file_id: uuid.UUID, sections: int) -> None:
        row = await self._repo.file(file_id)
        if row is None:
            raise NotFound(FILE_NOT_FOUND)
        values = {"status": InputFileStatus.EXTRACTED, "section_count": sections}
        await self._finish(row, values, self._done("extract", sections, sections))
