"""Calendar event resource operations."""

from __future__ import annotations

from .. import projection
from ..client import PlanbookClient
from ..errors import UsageError
from ..mutations import (
    Mutation,
    Request,
    commit,
    preview,
    require_intent,
    resolve_created,
)
from ..narrow import flag, records, string, text
from ..types import (
    Event,
    FormPayload,
    Id,
    JsonObject,
    JsonRecord,
    JsonValue,
    Result,
)
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
) -> list[Event]:
    """Events, projected to readable keys."""
    return [
        projection.event(e)
        for e in wire_events(client, start=start, end=end, limit=limit, search=search)
    ]


def wire_events(
    client: PlanbookClient,
    *,
    start: str = "",
    end: str = "",
    limit: int = 75,
    search: str = "",
) -> list[JsonObject]:
    """The wire records. Deletes resend the whole record, so they need these."""
    return _event_records(
        raw_events(client, start=start, end=end, limit=limit, search=search)
    )


def _event_records(body: JsonValue) -> list[JsonObject]:
    inner: JsonValue = (
        body["events"] if isinstance(body, dict) and "events" in body else body
    )
    return records(inner, where="getEvents.events")


def raw_events(
    client: PlanbookClient,
    *,
    start: str = "",
    end: str = "",
    limit: int = 75,
    search: str = "",
) -> JsonValue:
    return client.post(
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


def event_payload(
    event: JsonObject, *, current_date: str | None = None, shift: str = "N"
) -> FormPayload:
    """Flatten an event record into the form fields the server expects.

    Three fields fail silently when wrong - the server answers `{"events": []}`
    and does nothing:

      eventCurrentDate  empty when creating; the occurrence date when deleting
      shiftLessons      "N" when creating; "false" when deleting
      verifyShift       "true" validates and commits nothing; "false" commits
    """
    return {
        "eventId": intish(event.get("eventId") or event.get("id")),
        "googleId": string(event, "googleId"),
        "googleCalendarId": string(event, "googleCalendarId"),
        "customEventId": intish(event.get("customEventId")),
        "eventDate": string(event, "eventDate"),
        "endDate": string(event, "endDate") or string(event, "eventDate"),
        "repeats": string(event, "repeats", "daily"),
        "eventText": string(event, "eventText"),
        "eventStartTime": parse_time(text(event, "eventStartTime")),
        "eventEndTime": parse_time(text(event, "eventEndTime")),
        "eventTitle": string(event, "eventTitle"),
        "eventCurrentDate": current_date if current_date is not None else "",
        "specialDayId": intish(event.get("specialDayId")),
        "schoolId": intish(event.get("schoolId")),
        "districtId": intish(event.get("districtId")),
        "noSchool": "true" if flag(event.get("noSchool")) else "false",
        "noCycle": "true" if flag(event.get("noCycle")) else "false",
        "privateFlag": "true" if flag(event.get("privateFlag")) else "false",
        "shiftLessons": shift,
        "verifyShift": "false",  # "true" would validate and commit nothing
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
) -> FormPayload:
    """The exact form /addEvent receives.

    One builder, so `--dry-run` cannot drift from the real write.
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
    client: PlanbookClient | None,
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
    confirmed: bool = False,
    dry_run: bool = False,
) -> Result:
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
    mutation = Mutation(
        resource="event",
        operation="create",
        requests=[Request("/addEvent", payload)],
    )

    # A no-school day permanently deletes every lesson in range, so count them
    # first. --yes already means "delete whatever is there", so the count is
    # only worth a request for a preview or a run that still needs it.
    if no_school and (dry_run or not confirmed):
        assert client is not None  # the caller only omits it for an offline preview
        doomed = lessons_between(client, start=date, end=end_date or date)
        if doomed:
            mutation.cascade = {
                "lessons": len(doomed),
                "classes": sorted({str(x["class_name"]) for x in doomed}),
                "dates": sorted({str(x.get("date", date)) for x in doomed}),
            }
    if dry_run:
        return preview(mutation)
    require_intent(mutation, confirmed=confirmed)
    assert client is not None  # only an offline preview runs without one

    # /addEvent does not report the id it created, so diff the list around the
    # write and narrow by what was written.
    end = end_date or date
    before = {str(event_id_of(e)) for e in wire_events(client, start=date, end=end)}
    result = commit(client, mutation)
    event_id = resolve_created(
        resource="event",
        before=before,
        after=wire_events(client, start=date, end=end),
        id_of=event_id_of,
        matches=lambda e: (
            str(e.get("eventTitle")) == str(title)
            and str(e.get("eventDate")) == str(date)
        ),
        list_command=f"planbook events list --start {date} --end {end}",
    )
    return {
        **result,
        "title": title,
        "date": date,
        "id": event_id,
    }


def event_id_of(record: JsonRecord) -> object:
    """An event's id. Some responses key it `eventId`, some just `id`."""
    return record.get("eventId") or record.get("id")


def all_events(client: PlanbookClient) -> list[JsonObject]:
    """Every event on the account.

    No date window: the server's default range hides events outside it, so a
    lookup by id would miss one that exists.
    """
    return wire_events(client, start="", end="", limit=1000)


def find_event(client: PlanbookClient, event_id: Id) -> JsonObject:
    return _match(all_events(client), event_id)


def _match(events: list[JsonObject], event_id: Id) -> JsonObject:
    for event in events:
        if str(event_id_of(event)) == str(event_id):
            return event
    raise UsageError(f"No event with id {event_id}. Run `planbook events list`.")


def delete_event(
    client: PlanbookClient,
    *,
    event_id: Id,
    occurrence_only: bool = False,
    dry_run: bool = False,
    confirmed: bool = False,
) -> Result:
    """Delete an event.

    By default this removes the whole series. `occurrence_only` drops just
    the one date, which matters for a repeating event.
    """
    events = all_events(client)
    event = _match(events, event_id)
    payload = event_payload(
        event,
        current_date=string(event, "eventCurrentDate") or string(event, "eventDate"),
        shift="false",
    )
    payload["deleteCurrentEvent"] = "true" if occurrence_only else "false"
    payload["currentSchoolId"] = "0"
    doomed_date = str(payload["eventCurrentDate"])
    mutation = Mutation(
        resource="event",
        operation="delete",
        requests=[Request("/deleteEvent", payload)],
        before=projection.event(event),
        effects={"scope": "occurrence" if occurrence_only else "series"},
    )
    if not occurrence_only:
        # A series delete removes dates the caller never named, so count them.
        # A date range counts as a series even when one occurrence comes back:
        # the list endpoint does not always expand a repeat.
        occurrences = _series_dates(events, event_id)
        spans_days = bool(event.get("endDate")) and str(event.get("endDate")) != str(
            event.get("eventDate")
        )
        if len(occurrences) > 1 or spans_days:
            mutation.cascade = {
                "occurrences": max(len(occurrences), 2 if spans_days else 0),
                "dates": occurrences,
            }
    if dry_run:
        return preview(mutation)
    require_intent(mutation, confirmed=confirmed)
    # An occurrence delete leaves the rest of the series behind, and every
    # occurrence carries the same event id - so the read-back has to ask
    # whether this date is gone, not whether the id is.
    result = commit(
        client,
        mutation,
        verify=(
            (lambda: _occurrence_or_none(client, event_id, doomed_date))
            if occurrence_only
            else (lambda: _find_or_none(client, event_id))
        ),
    )
    return {
        **result,
        "deleted_event_id": payload["eventId"],
        "title": payload["eventTitle"],
        "scope": "occurrence" if occurrence_only else "series",
    }


def _series_dates(events: list[JsonObject], event_id: Id) -> list[str]:
    """Every date the series occupies, out of a listing already fetched."""
    wanted = str(event_id)
    dates = {
        str(e.get("eventCurrentDate") or e.get("eventDate"))
        for e in events
        if str(event_id_of(e)) == wanted
        and (e.get("eventCurrentDate") or e.get("eventDate"))
    }
    return sorted(dates)


def _occurrence_or_none(
    client: PlanbookClient, event_id: Id, date: str
) -> JsonObject | None:
    """The one occurrence on `date`, or None once it is gone."""
    for event in all_events(client):
        if str(event_id_of(event)) == str(event_id) and (
            str(event.get("eventCurrentDate") or event.get("eventDate")) == date
        ):
            return event
    return None


def _find_or_none(client: PlanbookClient, event_id: Id) -> JsonObject | None:
    try:
        return find_event(client, event_id)
    except UsageError:
        return None
