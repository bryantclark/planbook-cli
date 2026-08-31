"""Commands for students, attendance, grades and templates."""

from __future__ import annotations

import argparse

from ..cli_support import client_from, emit, emit_created, teacher_id_from
from ..resources.people import (
    create_student,
    delete_student,
    get_attendance,
    get_scores,
    list_students,
    list_templates,
    raw_templates,
    update_student,
)


def cmd_students_list(args: argparse.Namespace) -> None:
    emit(list_students(client_from(args), class_id=args.class_id))


def cmd_students_create(args: argparse.Namespace) -> None:
    client = None if args.dry_run else client_from(args)
    emit_created(
        args,
        create_student(
            client,
            dry_run=args.dry_run,
            first_name=args.first_name,
            last_name=args.last_name,
            code=args.code or "",
            email=args.email or "",
            phone=args.phone or "",
            parent_email=args.parent_email or "",
            birthdate=args.birthdate or "",
            middle_name=args.middle_name or "",
        ),
    )


def cmd_students_update(args: argparse.Namespace) -> None:
    emit(
        update_student(
            client_from(args),
            student_id=args.student_id,
            class_id=args.class_id,
            dry_run=args.dry_run,
            first_name=args.first_name,
            last_name=args.last_name,
            code=args.code,
            email=args.email,
            phone=args.phone,
            parent_email=args.parent_email,
            birthdate=args.birthdate,
            middle_name=args.middle_name,
        )
    )


def cmd_students_delete(args: argparse.Namespace) -> None:
    emit(
        delete_student(
            client_from(args),
            student_id=args.student_id,
            class_id=args.class_id,
            dry_run=args.dry_run,
        )
    )


def cmd_attendance(args: argparse.Namespace) -> None:
    emit(get_attendance(client_from(args), class_id=args.class_id, date=args.date))


def cmd_grades(args: argparse.Namespace) -> None:
    emit(get_scores(client_from(args), class_id=args.class_id))


def cmd_templates(args: argparse.Namespace) -> None:
    emit(
        (raw_templates if args.raw else list_templates)(
            client_from(args), teacher_id=teacher_id_from(args)
        )
    )
