"""
Base Repository Pattern with Common Query Operations.

Provides generic CRUD operations and query helpers.

AGPL-3.0 License - See LICENSE file for details.
"""
import uuid
from typing import TypeVar, Generic, Type, Optional, List, Dict, Any
from sqlalchemy.orm import Session, Query
from sqlalchemy import func, or_
from app.core.database import Base

T = TypeVar('T', bound=Base)


class BaseRepository(Generic[T]):
    """
    Generic repository base class providing common database operations.

    Usage:
        class TrackRepository(BaseRepository[Track]):
            def __init__(self, db: Session):
                super().__init__(db, Track)
    """

    def __init__(self, db: Session, model: Type[T]):
        self.db = db
        self.model = model

    # ==================== BASIC CRUD ====================

    def get_by_id(self, entity_id: uuid.UUID, eager_load: List = None) -> Optional[T]:
        """Get entity by ID with optional eager loading."""
        query = self.db.query(self.model).filter(self.model.id == entity_id)

        if eager_load:
            query = query.options(*eager_load)

        return query.first()

    def get_all(self, eager_load: List = None, order_by=None) -> List[T]:
        """Get all entities with optional eager loading and ordering."""
        query = self.db.query(self.model)

        if eager_load:
            query = query.options(*eager_load)

        if order_by is not None:
            query = query.order_by(order_by)

        return query.all()

    def create(self, **kwargs) -> T:
        """Create a new entity."""
        entity = self.model(**kwargs)
        self.db.add(entity)
        self.db.flush()
        return entity

    def update(self, entity: T, **kwargs) -> T:
        """Update an existing entity."""
        for key, value in kwargs.items():
            setattr(entity, key, value)
        self.db.flush()
        return entity

    def delete(self, entity: T) -> None:
        """Delete an entity."""
        self.db.delete(entity)
        self.db.flush()

    def delete_by_id(self, entity_id: uuid.UUID) -> bool:
        """Delete entity by ID. Returns True if deleted, False if not found."""
        entity = self.get_by_id(entity_id)
        if entity:
            self.delete(entity)
            return True
        return False

    def commit(self):
        """Commit the current transaction."""
        self.db.commit()

    def rollback(self):
        """Rollback the current transaction."""
        self.db.rollback()

    def flush(self):
        """Flush pending changes without committing."""
        self.db.flush()

    # ==================== QUERY BUILDING HELPERS ====================

    def _build_base_query(self, eager_load: List = None) -> Query:
        """Build a base query with optional eager loading."""
        query = self.db.query(self.model)

        if eager_load:
            query = query.options(*eager_load)

        return query

    def _apply_filters(self, query: Query, filters: Dict[str, Any]) -> Query:
        """Apply multiple filters to a query."""
        for key, value in filters.items():
            if value is not None:
                column = getattr(self.model, key)
                query = query.filter(column == value)
        return query

    # ==================== EXISTENCE CHECKS ====================

    def exists(self, **filters) -> bool:
        """Check if entity exists with given filters."""
        query = self.db.query(self.model.id)
        query = self._apply_filters(query, filters)
        return query.first() is not None

    def count(self, filters: Dict[str, Any] = None) -> int:
        """Count entities with optional filters."""
        query = self.db.query(func.count(self.model.id))

        if filters:
            query = self._apply_filters(query, filters)

        return query.scalar()

    # ==================== FIND OPERATIONS ====================

    def find_one(self, filters: Dict[str, Any], eager_load: List = None) -> Optional[T]:
        """Find a single entity matching filters."""
        query = self._build_base_query(eager_load=eager_load)
        query = self._apply_filters(query, filters)
        return query.first()

    def find_all(
        self,
        filters: Dict[str, Any] = None,
        eager_load: List = None,
        order_by=None,
        limit: int = None
    ) -> List[T]:
        """Find all entities matching filters."""
        query = self._build_base_query(eager_load=eager_load)

        if filters:
            query = self._apply_filters(query, filters)

        if order_by is not None:
            query = query.order_by(order_by)

        if limit:
            query = query.limit(limit)

        return query.all()
