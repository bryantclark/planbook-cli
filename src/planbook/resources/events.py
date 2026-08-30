"""Calendar event resource operations."""

from __future__ import annotations

from typing import Any, cast

from ..client import PlanbookClient
from ..errors import UsageError
from ..wire import intish, parse_time
from .lessons import lessons_between

EVENT_TYPES = '["Teacher","School","District"]'
EVENT_SCHEDULES = '["School","NoSchool"]'


def list_events(
    client: PlanbookClient,
    *,
    start: str = "",
    end: str = "",
    limit: int = 75,
    search: str = "",
) -> Any:
    body = client.post(
        "/getEvents",
        {
            "userMode": "T",
            "currentSchoolId": "0",
            "start": start,
            "end": end,
            "limit": str(limit),
            "searchText": search,
            "showEventTypes": EVENT_TYPES,
            "showEventSchedules": EVENT_SCHEDULES,
        },
    )
    if isinstance(body, dict) and set(body) == {"events"}:
        return body["events"]
    return body


def event_payload(
    event: dict[str, Any], *, current_date: str | None = None, shift: str = "N"
) -> dict[str, str]:
    """Flatten an event record into the form fields the server expects.

    Three fields fail silently when wrong - the server answers `{"events": []}`
    with no error and does nothing:

      eventCurrentDate  empty when creating; the occurrence date when deleting
      shiftLessons      "N" when creating; "false" when deleting
      verifyShift       "true" only runs a conflict check and commits nothing;
                        the app sends "true" then "false" to confirm
    """
    return {
        "eventId": intish(event.get("eventId") or event.get("id")),
        "googleId": event.get("googleId") or "",
        "googleCalendarId": event.get("googleCalendarId") or "",
        "customEventId": intish(event.get("customEventId")),
        "eventDate": event.get("eventDate") or "",
        "endDate": event.get("endDate") or event.get("eventDate") or "",
        "repeats": event.get("repeats") or "daily",
        "eventText": event.get("eventText") or "",
        "eventStartTime": parse_time(event.get("eventStartTime")),
        "eventEndTime": parse_time(event.get("eventEndTime")),
        "eventTitle": event.get("eventTitle") or "",
        "eventCurrentDate": current_date if current_date is not None else "",
        "specialDayId": intish(event.get("specialDayId")),
        "schoolId": intish(event.get("schoolId")),
        "districtId": intish(event.get("districtId")),
        "noSchool": "true" if event.get("noSchool") else "false",
        "noCycle": "true" if event.get("noCycle") else "false",
        "privateFlag": "true" if event.get("privateFlag") else "false",
        "shiftLessons": shift,
        # "false" means commit. See the note above.
        "verifyShift": "false",
        "stickerId": intish(event.get("stickerId")),
        "limit": "75",
        "userMode": "T",
    }


def new_event_payload(
    *,
    title: str,
    date: str,
    end_date: str | None = None,
    text: str = "",
    start_time: str = "",
    end_time: str = "",
    private: bool = False,
    no_school: bool = False,
    repeats: str = "daily",
) -> dict[str, str]:
    """The exact form /addEvent receives.

    One builder so that --dry-run cannot drift from the real write; the
    preview used to omit updatedFields and updateCurrentEvent.
    """
    payload = event_payload(
        {
            "repeats": repeats,
            "eventTitle": title,
            "eventDate": date,
            "endDate": end_date or date,
            "eventText": text,
            "eventStartTime": start_time,
            "eventEndTime": end_time,
            "privateFlag": private,
            "noSchool": no_school,
        }
    )
    payload["updatedFields"] = "extraDays"
    payload["updateCurrentEvent"] = "false"
    return payload


def create_event(
    client: PlanbookClient,
    *,
    title: str,
    date: str,
    end_date: str | None = None,
    text: str = "",
    start_time: str = "",
    end_time: str = "",
    private: bool = False,
    no_school: bool = False,
    repeats: str = "daily",
    force: bool = False,
) -> Any:
    if no_school and not force:
        # Marking a day no-school DELETES the lessons on it, permanently -
        # removing the event afterwards does not bring them back.
        doomed = lessons_between(client, start=date, end=end_date or date)
        if doomed:
            names = ", ".join(sorted({str(x["class_name"]) for x in doomed}))
            raise UsageError(
                f"{len(doomed)} lesson(s) already exist on {date}"
                + (f"-{end_date}" if end_date and end_date != date else "")
                + f" ({names}).\nMarking the day no-school deletes them "
                "permanently; deleting the event later does not restore them. "
                "Pass --force if that is what you want."
            )
    payload = new_event_payload(
        title=title,
        date=date,
        end_date=end_date,
        text=text,
        start_time=start_time,
        end_time=end_time,
        private=private,
        no_school=no_school,
        repeats=repeats,
    )

    # /addEvent does not report the id it created, so diff the list around the
    # write to hand back a reference the caller can delete or update.
    def event_ids(records: Any) -> list[dict[str, Any]]:
        return [r for r in records or [] if isinstance(r, dict)]

    end = end_date or date
    before = {
        str(e.get("eventId") or e.get("id"))
        for e in event_ids(list_events(client, start=date, end=end))
    }
    client.post("/addEvent", payload)
    created = [
        e
        for e in event_ids(list_events(client, start=date, end=end))
        if str(e.get("eventId") or e.get("id")) not in before
    ]
    result: dict[str, Any] = {"ok": True, "title": title, "date": date}
    result["event_id"] = created[0].get("eventId") if len(created) == 1 else None
    return result


def find_event(client: PlanbookClient, event_id: Any) -> dict[str, Any]:
    wanted = str(event_id)
    # No date window: the server's default range would hide events outside it
    # and this would report "no such event" for one that exists.
    for event in list_events(client, start="", end="", limit=1000) or []:
        if str(event.get("eventId") or event.get("id")) == wanted:
            return cast(dict[str, Any], event)
    raise UsageError(f"No event with id {event_id}. Run `planbook events list`.")


def delete_event(
    client: PlanbookClient,
    *,
    event_id: Any,
    occurrence_only: bool = False,
) -> Any:
    """Delete an event.

    By default this removes the whole series. `occurrence_only` drops just
    the one date, which matters for a repeating event.
    """
    event = find_event(client, event_id)
    payload = event_payload(
        event,
        current_date=event.get("eventCurrentDate") or event.get("eventDate") or "",
        shift="false",
    )
    payload["deleteCurrentEvent"] = "true" if occurrence_only else "false"
    payload["currentSchoolId"] = "0"
    client.post("/deleteEvent", payload)
    return {
        "ok": True,
        "deleted_event_id": payload["eventId"],
        "title": payload["eventTitle"],
        "scope": "occurrence" if occurrence_only else "series",
    }
