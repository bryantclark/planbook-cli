"""Registry of every endpoint observed on the wire.

`status` is what this CLI knows, not what Planbook supports:

  mapped    request and response are both understood and wrapped in a command
  partial   the call works, the response shape is not fully decoded
  observed  seen in browser traffic, not yet wired up - reach it with `raw`

Anything not listed here may still exist. `planbook raw` will POST to any
path, which is the honest way to cover an API nobody has documented.
"""

ENDPOINTS = [
    ("/getClasses2", "mapped", "Classes, current year id, lesson banks"),
    ("/updateLesson", "mapped", "Upsert a lesson by class + date"),
    ("/addClass", "mapped", "Create a class"),
    ("/getSpecialDays", "mapped", "Holidays / non-teaching days"),
    ("/getSettings", "partial", "Account and display settings"),
    ("/getStandards", "partial", "Standards available to the account"),
    ("/getLessonsEvents", "partial", "Lessons+events by week; `days` shape undecoded"),
    ("/getAssignments", "observed", "Assignments"),
    ("/getAssessments", "observed", "Assessments"),
    ("/getCommentsTo", "observed", "Comments addressed to the user"),
    ("/getAttachmentList", "observed", "Attachments (teacherId, isFolderStructured, withAllFolders)"),
    ("/services/planbook/template/get", "observed", "Lesson templates"),
    ("/services/api/stickers", "observed", "Stickers"),
    ("/services/api/referencedata/maintenanceData", "observed", "Reference data"),
    ("/services/api/feature-flags", "observed", "Feature flags - requires an API key"),
    ("/services/api/global-vars", "observed", "Global vars - requires an API key"),
    ("/services/planbook/oneRosterClient/getAllRosteredItems", "observed", "OneRoster sync"),
]
