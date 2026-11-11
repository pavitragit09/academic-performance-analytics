"""Course performance report export as CSV and PDF (APAS-F-033).

Both formats are built from the course dashboard response, so the exported figures are
exactly the figures on the dashboard (TC-Dash-04).
"""

import csv
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

CSV_COLUMNS = [
    "usn",
    "name",
    "attendancePct",
    "averageMarks",
    "declining",
    "assignmentCompletionPct",
    "atRisk",
    "riskReasons",
]

# Spreadsheet apps run cells that start with these characters as formulas.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _cell(value) -> str:
    """Blank for no data, plain text otherwise, never a spreadsheet formula."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    if text.startswith(FORMULA_PREFIXES):
        return "'" + text
    return text


def _reasons_by_usn(dashboard: dict) -> dict:
    return {row["usn"]: row["reasons"] for row in dashboard["atRisk"]}


def report_filename(dashboard: dict, extension: str) -> str:
    safe_code = "".join(ch for ch in dashboard["courseCode"] if ch.isalnum() or ch in "-_")
    return f"{safe_code or 'course'}_report.{extension}"


def course_report_csv(dashboard: dict) -> str:
    """One row per student with the same values as the dashboard's students list."""
    reasons = _reasons_by_usn(dashboard)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for student in dashboard["students"]:
        writer.writerow([
            _cell(student["usn"]),
            _cell(student["name"]),
            _cell(student["attendancePct"]),
            _cell(student["averageMarks"]),
            _cell(student["declining"]),
            _cell(student["assignmentCompletionPct"]),
            _cell(student["atRisk"]),
            _cell("; ".join(reasons.get(student["usn"], []))),
        ])
    return buffer.getvalue()


def _show(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _table(rows: list[list], widths: list[float] | None = None) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3A5F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#B0B7C3")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def course_report_pdf(dashboard: dict) -> bytes:
    """A printable report: course summary, marks bands, exams, at-risk list, student table."""
    styles = getSampleStyleSheet()
    buffer = io.BytesIO()
    # Uncompressed and invariant so the file is reproducible and its text is checkable.
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"{dashboard['courseCode']} performance report",
        pageCompression=0,
        invariant=1,
    )
    reasons = _reasons_by_usn(dashboard)
    story = [
        Paragraph(f"Performance report: {dashboard['courseCode']}", styles["Title"]),
        Paragraph(dashboard["courseTitle"], styles["Heading2"]),
        Paragraph(
            f"Enrolled: {dashboard['enrolled']} &nbsp;&nbsp; "
            f"Class average: {_show(dashboard['classAverage'])} &nbsp;&nbsp; "
            f"At risk: {len(dashboard['atRisk'])}",
            styles["Normal"],
        ),
        Spacer(1, 6 * mm),
        Paragraph("Marks distribution (average %)", styles["Heading3"]),
        _table([
            list(dashboard["marksDistribution"].keys()),
            [str(count) for count in dashboard["marksDistribution"].values()],
        ]),
    ]

    if dashboard["exams"]:
        story += [
            Spacer(1, 4 * mm),
            Paragraph("Exam summaries (%)", styles["Heading3"]),
            _table(
                [["Exam", "Count", "Highest", "Lowest", "Average", "Pass rate"]]
                + [
                    [e["examType"], e["count"], e["highest"], e["lowest"], e["average"],
                     e["pass_rate"]]
                    for e in dashboard["exams"]
                ]
            ),
        ]

    story += [
        Spacer(1, 4 * mm),
        Paragraph("Students", styles["Heading3"]),
        _table(
            [["USN", "Name", "Attendance %", "Average %", "Declining",
              "Assignments %", "At risk", "Reasons"]]
            + [
                [s["usn"], s["name"], _show(s["attendancePct"]), _show(s["averageMarks"]),
                 _show(s["declining"]), _show(s["assignmentCompletionPct"]), _show(s["atRisk"]),
                 Paragraph(", ".join(reasons.get(s["usn"], [])) or "-", styles["BodyText"])]
                for s in dashboard["students"]
            ],
            widths=[32 * mm, 40 * mm, 26 * mm, 24 * mm, 22 * mm, 28 * mm, 18 * mm, 77 * mm],
        ),
    ]
    document.build(story)
    return buffer.getvalue()
