"""Registry of every endpoint observed on the wire.

`status` describes what this CLI knows, not what Planbook supports:

  mapped    request and response understood, wrapped in a command, and
            exercised against a live account
  partial   the call works, the response shape is not fully decoded
  observed  seen in browser traffic, not yet wired up - reach it with `raw`
  blocked   exists, but demands a parameter the server refuses to name;
            needs a captured browser request before it can be mapped
  absent    probed and does not exist under this name

Anything not listed may still exist. `planbook raw` will POST to any path,
which is the honest way to cover an API nobody has documented.
"""

ENDPOINTS = [
    # Classes
    ("/getClasses2", "mapped", "Classes, current year id, lesson banks"),
    ("/getClass", "mapped", "One class by id"),
    ("/addClass", "mapped", "Create a class"),
    ("/updateClass/v10", "mapped", "Update a class; needs scheduleChange=true"),
    ("/deleteClass", "mapped", "Delete a class and all of its lessons"),
    # Lessons
    ("/updateLesson", "mapped", "Upsert a lesson by class + date"),
    ("/deleteLesson", "mapped", "Clear the lesson on one date"),
    ("/getLessonsEvents", "mapped", "Lessons and events by week, grouped by day"),
    ("/copyLesson", "absent", "Not a real path - answers with the SPA page"),
    ("/bumpLesson", "blocked", "Bump/shift lessons"),
    # Units
    ("/getUnits", "mapped", "Units"),
    ("/updateUnit", "mapped", "Add/update/delete a unit via action=A|U|D"),
    # Events
    ("/getEvents", "mapped", "Events, filterable by date window"),
    ("/addEvent", "mapped", "Create an event; verifyShift=false to commit"),
    ("/deleteEvent", "mapped", "Delete an event; echo the whole record back"),
    ("/updateEvent", "observed", "Update an event"),
    ("/getSpecialDays", "mapped", "Holidays / non-teaching days"),
    # To-dos and notes
    ("/getToDos", "mapped", "To-dos (classId=all for everything)"),
    ("/updateToDo", "mapped", "Add/update/delete a to-do via action=A|U|D"),
    (
        "/services/planbook/newNote/filterNotes",
        "blocked",
        "Notes; wants an unnamed long (getLong returned null)",
    ),
    ("/addNote", "observed", "Create a note"),
    ("/updateNote", "observed", "Update a note"),
    # Other reads
    ("/getSettings", "partial", "Account and display settings"),
    ("/getStandards", "partial", "Standards available to the account"),
    ("/getStandardsReport", "blocked", "Standards coverage; wants an unnamed int"),
    ("/getAssignments", "mapped", "Assignments"),
    ("/getAssessments", "mapped", "Assessments"),
    ("/getSchools", "mapped", "Schools"),
    ("/getCommentsTo", "mapped", "Comments addressed to the user"),
    ("/getAttachmentList", "mapped", "Uploaded resources"),
    ("/services/planbook/template/get", "mapped", "Lesson templates (GET, teacherId)"),
    (
        "/services/planbook/student/getAllFromSchool",
        "mapped",
        "Every student on the account",
    ),
    (
        "/services/planbook/unarchiveYear/getUnarchivalStatus",
        "observed",
        "Year unarchival",
    ),
    ("/services/planbook/googleclassroom", "observed", "Google Classroom link"),
    ("/connectServlet", "observed", "Third-party connect flow"),
    # People
    ("/getStudentsServlet", "mapped", "Students in one class"),
    ("/addStudentServlet", "mapped", "Create a student"),
    ("/updateStudentServlet", "mapped", "Update a student"),
    ("/deleteStudentServlet", "mapped", "Delete a student"),
    ("/getStudentScoresServlet", "mapped", "Grade periods and scored assignments"),
    ("/services/planbook/attendance/get", "mapped", "Attendance (GET; read-only)"),
    (
        "/services/planbook/attendance/getLessonsByDate",
        "observed",
        "Attendance day view",
    ),
    ("/services/planbook/student/studentsTagged", "observed", "Tagged students (GET)"),
    ("/addTemplate", "observed", "Create a lesson template"),
    ("/updateTemplate", "observed", "Update a lesson template"),
    ("/deleteTemplate", "observed", "Delete a lesson template"),
    ("/extendLesson", "blocked", "Extend a lesson; wants an unnamed Integer"),
    # Gated
    ("/services/api/stickers", "observed", "Stickers"),
    ("/services/api/referencedata/maintenanceData", "observed", "Reference data"),
    ("/services/api/feature-flags", "observed", "Feature flags - needs an API key"),
    ("/services/api/global-vars", "observed", "Global vars - needs an API key"),
    (
        "/services/planbook/oneRosterClient/getAllRosteredItems",
        "observed",
        "OneRoster sync",
    ),
]
