"""SQLAlchemy tenant scoping, applied to every owner-scoped model."""
from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from backend.auth import current_owner_id
from backend.db.models import OwnerScoped, Subscription


@event.listens_for(Session, "do_orm_execute")
def _scope_orm_reads(execute_state):
    if not (execute_state.is_select or execute_state.is_update or execute_state.is_delete):
        return
    if execute_state.execution_options.get("skip_owner_scope"):
        return
    owner_id = current_owner_id()
    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            OwnerScoped,
            lambda model: model.owner_id == owner_id,
            include_aliases=True,
        )
    )


@event.listens_for(Session, "before_flush")
def _set_and_validate_owner(session, _flush_context, _instances):
    owner_id = current_owner_id()
    for obj in (*session.new, *session.dirty):
        if isinstance(obj, OwnerScoped):
            if obj.owner_id is None:
                obj.owner_id = owner_id
            elif obj.owner_id != owner_id:
                raise PermissionError("Cannot write data owned by another account")
            if isinstance(obj, Subscription) and obj.id and owner_id != "local-owner":
                prefix = f"{owner_id}:"
                if not obj.id.startswith(prefix):
                    obj.id = prefix + obj.id
