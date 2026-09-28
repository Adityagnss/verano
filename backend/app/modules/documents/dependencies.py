"""FastAPI wiring for the documents service."""

from typing import Annotated

from fastapi import Depends

from app.core.container import ContainerDep
from app.core.database import SessionDep
from app.modules.documents.service import DocumentService


def get_document_service(session: SessionDep, container: ContainerDep) -> DocumentService:
    return DocumentService.from_container(session, container)


DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
