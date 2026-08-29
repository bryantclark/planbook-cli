"""To-do command callbacks."""

from __future__ import annotations

import argparse

from .. import api
from ..cli import client_from, emit


def cmd_todos_list(args: argparse.Namespace) -> None:
    emit(api.list_todos(client_from(args), class_id=args.class_id or "all"))


def cmd_todos_create(args: argparse.Namespace) -> None:
    emit(
        api.create_todo(
            client_from(args),
            text=args.text,
            start=args.start,
            due=args.due or "",
            priority=args.priority,
            done=args.done,
            repeats=args.repeats,
        )
    )


def cmd_todos_update(args: argparse.Namespace) -> None:
    emit(
        api.update_todo(
            client_from(args),
            todo_id=args.todo_id,
            text=args.text,
            start=args.start,
            due=args.due or "",
            priority=args.priority,
            done=args.done,
            repeats=args.repeats,
        )
    )


def cmd_todos_delete(args: argparse.Namespace) -> None:
    emit(api.delete_todo(client_from(args), todo_id=args.todo_id))
