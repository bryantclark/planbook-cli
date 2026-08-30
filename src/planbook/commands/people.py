"""Commands for students, attendance, grades and templates."""

from __future__ import annotations

import argparse

from .. import api
from ..cli_support import client_from, emit, teacher_id_from


def cmd_students_list(args: argparse.Namespace) -> None:
    emit(api.list_students(client_from(args), class_id=args.class_id))


def cmd_students_create(args: argparse.Namespace) -> None:
    emit(
        api.create_student(
            client_from(args),
            first_name=args.first_name,
            last_name=args.last_name,
            code=args.code or "",
            email=args.email or "",
            phone=args.phone or "",
            parent_email=args.parent_email or "",
            birthdate=args.birthdate or "",
            middle_name=args.middle_name or "",
        )
    )


def cmd_students_update(args: argparse.Namespace) -> None:
    emit(
        api.update_student(
            client_from(args),
            student_id=args.student_id,
            class_id=args.class_id,
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
    emit(api.delete_student(client_from(args), student_id=args.student_id))


def cmd_attendance(args: argparse.Namespace) -> None:
    emit(api.get_attendance(client_from(args), class_id=args.class_id, date=args.date))


def cmd_grades(args: argparse.Namespace) -> None:
    emit(api.get_scores(client_from(args), class_id=args.class_id))


def cmd_templates(args: argparse.Namespace) -> None:
    emit(api.list_templates(client_from(args), teacher_id=teacher_id_from(args)))
