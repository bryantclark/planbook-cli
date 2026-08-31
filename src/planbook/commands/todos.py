"""To-do command callbacks."""

from __future__ import annotations

import argparse

from ..cli_support import client_from, emit, emit_created, resolve_stdin
from ..resources.todos import (
    create_todo,
    delete_todo,
    list_todos,
    raw_todos,
    update_todo,
)


def cmd_todos_list(args: argparse.Namespace) -> None:
    emit(
        (raw_todos if args.raw else list_todos)(
            client_from(args), class_id=args.class_id or "all"
        )
    )


def cmd_todos_create(args: argparse.Namespace) -> None:
    resolve_stdin(args, "text")
    client = None if args.dry_run else client_from(args)
    emit_created(
        args,
        create_todo(
            client,
            text=args.text,
            start=args.start,
            due=args.due or "",
            priority=args.priority,
            done=args.done,
            repeats=args.repeats,
            dry_run=args.dry_run,
        ),
    )


def cmd_todos_update(args: argparse.Namespace) -> None:
    resolve_stdin(args, "text")
    emit(
        update_todo(
            client_from(args),
            todo_id=args.todo_id,
            text=args.text,
            start=args.start,
            due=args.due,
            priority=args.priority,
            done=args.done,
            repeats=args.repeats,
            dry_run=args.dry_run,
        )
    )


def cmd_todos_delete(args: argparse.Namespace) -> None:
    emit(
        delete_todo(
            client_from(args),
            todo_id=args.todo_id,
            dry_run=args.dry_run,
        )
    )
