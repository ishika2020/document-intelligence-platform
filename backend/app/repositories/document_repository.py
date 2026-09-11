"""Persistence layer for processed document results."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import ProcessedDocument


def save_result(db: Session, result: dict) -> ProcessedDocument:
    row = ProcessedDocument(
        document_name=result["document_name"],
        document_type=result["document_type"],
        processing_status=result["processing_status"],
        overall_confidence=result.get("overall_confidence"),
        file_validation=result["file_validation"],
        extracted_data=result["extracted_data"],
        validation=result["validation"],
        processing_metadata=result["processing_metadata"],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_latest_by_name(db: Session, document_name: str) -> ProcessedDocument | None:
    stmt = (
        select(ProcessedDocument)
        .where(ProcessedDocument.document_name == document_name)
        .order_by(ProcessedDocument.created_at.desc(), ProcessedDocument.id.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def list_latest_documents(db: Session, limit: int = 200) -> list[ProcessedDocument]:
    """Latest processing result per distinct document_name, newest first."""
    latest_ids_subquery = (
        select(
            ProcessedDocument.document_name,
            func.max(ProcessedDocument.id).label("latest_id"),
        )
        .group_by(ProcessedDocument.document_name)
        .subquery()
    )
    stmt = (
        select(ProcessedDocument)
        .join(latest_ids_subquery, ProcessedDocument.id == latest_ids_subquery.c.latest_id)
        .order_by(ProcessedDocument.created_at.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


def count_documents(db: Session) -> int:
    stmt = select(func.count(func.distinct(ProcessedDocument.document_name)))
    return db.execute(stmt).scalar_one()
