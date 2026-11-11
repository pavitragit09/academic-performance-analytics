/* APAS web UI (APAS-NF-004). Plain JavaScript, no build step.
 * All server data is inserted as text nodes, never parsed as HTML, so names cannot inject markup.
 */
"use strict";

const API = "/api/v1";
const view = document.getElementById("view");
const statusRegion = document.getElementById("status");
const accountNav = document.getElementById("account-nav");
const signedInAs = document.getElementById("signed-in-as");

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

/* Build an element: h("p", {class: "muted"}, "text", child, ...). */
function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "style") Object.assign(el.style, value);
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

function announce(message) {
  statusRegion.textContent = "";
  window.setTimeout(() => {
    statusRegion.textContent = message;
  }, 50);
}

async function api(path, options = {}) {
  const response = await fetch(API + path, {
    credentials: "same-origin",
    headers: options.body ? { "Content-Type": "application/json" } : {},
    ...options,
  });

  if (response.status === 204) return null;

  let body = null;
  try {
    body = await response.json();
  } catch (_) {
    body = null;
  }

  if (!response.ok) {
    const message =
      (body && body.error && body.error.message) ||
      `Request failed (${response.status})`;

    if (response.status === 401 && !path.startsWith("/auth/")) {
      showLogin("Your session has ended. Please log in again.");
    }

    throw new ApiError(response.status, message);
  }

  return body;
}

function fmt(value, suffix = "") {
  return value === null || value === undefined ? "–" : `${value}${suffix}`;
}

let firstView = true;

function show(title, subtitle, ...content) {
  view.replaceChildren(
    h("h1", { id: "page-title", tabindex: "-1" }, title),
    subtitle ? h("p", { class: "muted" }, subtitle) : null,
    ...content,
  );

  document.title = `${title} – APAS`;

  if (!firstView) {
    document.getElementById("page-title").focus();
  }

  firstView = false;
}

function card(label, value) {
  return h(
    "div",
    { class: "card" },
    h("p", { class: "label" }, label),
    h("p", { class: "value" }, value),
  );
}

function riskBadge(atRisk) {
  return atRisk
    ? h("span", { class: "badge badge-risk" }, "⚠ At risk")
    : h("span", { class: "badge badge-ok" }, "✓ On track");
}

let tableCount = 0;

/* columns: [{label, value(row), num}] */
function table(caption, columns, rows, emptyText) {
  if (!rows.length) {
    return h("p", { class: "empty" }, emptyText || "No data yet.");
  }

  const id = `table-caption-${++tableCount}`;

  return h(
    "div",
    {
      class: "table-wrap",
      role: "region",
      "aria-labelledby": id,
      tabindex: "0",
    },
    h(
      "table",
      {},
      h("caption", { id }, caption),
      h(
        "thead",
        {},
        h(
          "tr",
          {},
          columns.map((c) =>
            h("th", { scope: "col", class: c.num ? "num" : null }, c.label),
          ),
        ),
      ),
      h(
        "tbody",
        {},
        rows.map((row) =>
          h(
            "tr",
            {},
            columns.map((c, i) => {
              const cell = c.value(row);
              return i === 0
                ? h("th", { scope: "row", class: c.num ? "num" : null }, cell)
                : h("td", { class: c.num ? "num" : null }, cell);
            }),
          ),
        ),
      ),
    ),
  );
}

/* ---------------- Login ---------------- */

function showLogin(message) {
  accountNav.hidden = true;

  const error = h(
    "div",
    { class: "alert", role: "alert", id: "login-error" },
    message || "",
  );

  const username = h("input", {
    id: "username",
    name: "username",
    autocomplete: "username",
    required: true,
  });

  const password = h("input", {
    id: "password",
    name: "password",
    type: "password",
    autocomplete: "current-password",
    required: true,
    "aria-describedby": "password-hint",
  });

  const submit = h("button", { type: "submit", class: "button" }, "Log in");

  const form = h(
    "form",
    {
      class: "panel login-panel",
      novalidate: true,
      "aria-labelledby": "page-title",
    },
    error,
    h(
      "div",
      { class: "field" },
      h("label", { for: "username" }, "Username"),
      username,
    ),
    h(
      "div",
      { class: "field" },
      h("label", { for: "password" }, "Password"),
      password,
      h(
        "p",
        { class: "hint", id: "password-hint" },
        "Accounts lock for 15 minutes after 5 failed attempts.",
      ),
    ),
    submit,
  );

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.textContent = "";

    if (!username.value.trim() || !password.value) {
      error.textContent = "Enter your username and password.";
      (username.value.trim() ? password : username).focus();
      return;
    }

    submit.disabled = true;
    announce("Logging in");

    try {
      await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          username: username.value.trim(),
          password: password.value,
        }),
      });

      await start();
    } catch (err) {
      error.textContent = err.message;
      password.value = "";
      password.focus();
    } finally {
      submit.disabled = false;
    }
  });

  show("Log in", "Academic Performance Analytics System", form);
}

async function logout() {
  try {
    await api("/auth/logout", { method: "POST" });
  } catch (_) {
    /* already logged out */
  }

  showLogin("You have logged out.");
}

/* ---------------- Student Trend Charts (APAS-F-034) ---------------- */

function createTrendChart(title, records, getValue, valueLabel) {
  const section = h("section", {
    class: "trend-card",
    "aria-label": title,
  });

  section.append(h("h3", {}, title));

  if (records.length < 2) {
    section.append(
      h(
        "p",
        { class: "empty" },
        "At least two records are required to display a trend.",
      ),
    );
    return section;
  }

  const width = 640;
  const height = 240;
  const left = 55;
  const right = 20;
  const top = 20;
  const bottom = 55;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;

  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");

  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", title);
  svg.setAttribute("class", "trend-chart");

  const values = records.map(getValue);
  const minValue = Math.min(0, ...values);
  const maxValue = Math.max(100, ...values);

  const x = (index) =>
    left + (index / (records.length - 1)) * plotWidth;

  const y = (value) =>
    top + ((maxValue - value) / (maxValue - minValue)) * plotHeight;

  /* Horizontal grid lines and percentage labels. */
  [0, 25, 50, 75, 100].forEach((value) => {
    const line = document.createElementNS(svgNS, "line");

    line.setAttribute("x1", left);
    line.setAttribute("x2", width - right);
    line.setAttribute("y1", y(value));
    line.setAttribute("y2", y(value));
    line.setAttribute("class", "chart-grid");

    svg.append(line);

    const label = document.createElementNS(svgNS, "text");

    label.setAttribute("x", left - 10);
    label.setAttribute("y", y(value) + 4);
    label.setAttribute("text-anchor", "end");
    label.setAttribute("class", "chart-label");
    label.textContent = `${value}%`;

    svg.append(label);
  });

  /* Draw the trend line. */
  const path = document.createElementNS(svgNS, "polyline");

  path.setAttribute(
    "points",
    records
      .map((record, index) => `${x(index)},${y(getValue(record))}`)
      .join(" "),
  );

  path.setAttribute("class", "chart-line");
  svg.append(path);

  /* Draw points and accessible value labels. */
  records.forEach((record, index) => {
    const value = getValue(record);

    const circle = document.createElementNS(svgNS, "circle");

    circle.setAttribute("cx", x(index));
    circle.setAttribute("cy", y(value));
    circle.setAttribute("r", "5");
    circle.setAttribute("class", "chart-point");

    const pointTitle = document.createElementNS(svgNS, "title");
    pointTitle.textContent = `${record.date}: ${valueLabel(value)}`;
    circle.append(pointTitle);

    svg.append(circle);

    const dateLabel = document.createElementNS(svgNS, "text");

    dateLabel.setAttribute("x", x(index));
    dateLabel.setAttribute("y", height - 25);
    dateLabel.setAttribute("text-anchor", "middle");
    dateLabel.setAttribute("class", "chart-label");
    dateLabel.textContent =
      record.date.length > 10 ? record.date.slice(0, 10) : record.date;

    svg.append(dateLabel);
  });

  section.append(svg);

  /* Provide a readable data table alongside the visual chart. */
  section.append(
    table(
      title + " data",
      [
        { label: "Date", value: (item) => item.date },
        {
          label: "Value",
          num: true,
          value: (item) => valueLabel(item.value),
        },
      ],
      records.map((record) => ({
        date: record.date,
        value: getValue(record),
      })),
      "No trend data available.",
    ),
  );

  return section;
}

function studentTrendCharts(data) {
  const section = h("section", {
    "aria-labelledby": "trend-heading",
  });

  section.append(
    h("h2", { id: "trend-heading" }, "Course-wise trends"),
    h(
      "p",
      { class: "muted" },
      "Track your marks and attendance separately for each course.",
    ),
  );

  const courseCodes = [
    ...new Set([
      ...data.marks.map((item) => item.course_code),
      ...data.attendance.map((item) => item.course_code),
    ]),
  ]
    .filter(Boolean)
    .sort();

  if (!courseCodes.length) {
    section.append(
      h("p", { class: "empty" }, "No course trend data is available yet."),
    );
    return section;
  }

  courseCodes.forEach((code) => {
    const marks = data.marks
      .filter((item) => item.course_code === code)
      .sort((a, b) => a.held_on.localeCompare(b.held_on))
      .map((item) => ({
        date: item.held_on,
        value:
          item.max_marks > 0
            ? Math.round((item.marks / item.max_marks) * 1000) / 10
            : 0,
      }));

    const attendanceRecords = data.attendance
      .filter((item) => item.course_code === code)
      .sort((a, b) => a.session_date.localeCompare(b.session_date));

    /* Cumulative attendance percentage after each session. */
    let presentCount = 0;

    const attendance = attendanceRecords.map((item, index) => {
      if (item.present) presentCount += 1;

      return {
        date: item.session_date,
        value: Math.round((presentCount / (index + 1)) * 1000) / 10,
      };
    });

    const courseTitle =
      data.marks.find((item) => item.course_code === code)?.course_title ||
      data.attendance.find((item) => item.course_code === code)?.course_title ||
      code;

    section.append(
      h("h3", { class: "course-trend-title" }, `${code} – ${courseTitle}`),

      createTrendChart(
        "Marks trend (%)",
        marks,
        (item) => item.value,
        (value) => `${value}%`,
      ),

      createTrendChart(
        "Cumulative attendance trend (%)",
        attendance,
        (item) => item.value,
        (value) => `${value}%`,
      ),
    );
  });

  return section;
}

/* ---------------- Student ---------------- */

async function showStudent() {
  const data = await api("/student/dashboard");
  const s = data.student;

  const present = data.attendance.filter((a) => a.present).length;

  const attendancePct = data.attendance.length
    ? Math.round((present / data.attendance.length) * 1000) / 10
    : null;

  const percents = data.marks
    .filter((m) => m.max_marks > 0)
    .map((m) => (m.marks / m.max_marks) * 100);

  const averagePct = percents.length
    ? Math.round(
        (percents.reduce((a, b) => a + b, 0) / percents.length) * 10,
      ) / 10
    : null;

  const submitted = data.assignments.filter((a) => a.submitted).length;

  const marks = [...data.marks].sort((a, b) =>
    a.held_on.localeCompare(b.held_on),
  );

  show(
    `Hello, ${s.name}`,
    `${s.usn} · ${s.department} · Semester ${s.semester}`,

    h(
      "section",
      { "aria-labelledby": "summary-heading" },
      h("h2", { id: "summary-heading" }, "Summary"),
      h(
        "div",
        { class: "cards" },
        card("Attendance", fmt(attendancePct, "%")),
        card("Average marks", fmt(averagePct, "%")),
        card(
          "Assignments submitted",
          `${submitted} of ${data.assignments.length}`,
        ),
        card("Exams recorded", String(data.exam_results.length)),
      ),
    ),

    /* New feature: separate marks and attendance trends for each course. */
    studentTrendCharts(data),

    h(
      "section",
      { "aria-labelledby": "marks-heading" },
      h("h2", { id: "marks-heading" }, "Marks over time"),
      table(
        "Your marks, oldest first",
        [
          { label: "Date", value: (m) => m.held_on },
          { label: "Course", value: (m) => m.course_code },
          { label: "Assessment", value: (m) => m.assessment },
          {
            label: "Marks",
            num: true,
            value: (m) => `${m.marks} / ${m.max_marks}`,
          },
          {
            label: "Percent",
            num: true,
            value: (m) =>
              `${Math.round((m.marks / m.max_marks) * 1000) / 10}%`,
          },
        ],
        marks,
        "No marks recorded yet.",
      ),
    ),

    h(
      "section",
      { "aria-labelledby": "assign-heading" },
      h("h2", { id: "assign-heading" }, "Assignments"),
      table(
        "Your assignments",
        [
          { label: "Assignment", value: (a) => a.title },
          { label: "Course", value: (a) => a.course_code },
          { label: "Due", value: (a) => a.due_date },
          {
            label: "Status",
            value: (a) => String(a.status || "missing").toLowerCase(),
          },
          {
            label: "Score",
            num: true,
            value: (a) =>
              a.score === null || a.score === undefined
                ? "–"
                : `${a.score} / ${a.max_score}`,
          },
        ],
        data.assignments,
        "No assignments yet.",
      ),
    ),

    h(
      "section",
      { "aria-labelledby": "exam-heading" },
      h("h2", { id: "exam-heading" }, "Exam results"),
      table(
        "Your exam results",
        [
          { label: "Exam", value: (e) => e.exam_type },
          { label: "Course", value: (e) => e.course_code },
          {
            label: "Marks",
            num: true,
            value: (e) => `${e.marks} / ${e.max_marks}`,
          },
        ],
        data.exam_results,
        "No exam results yet.",
      ),
    ),
  );
}

/* ---------------- Faculty / admin course dashboard ---------------- */

function distribution(dist) {
  const total = Object.values(dist).reduce((a, b) => a + b, 0) || 1;

  return table(
    "Students by average marks band",
    [
      { label: "Band", value: ([band]) => `${band}%` },
      {
        label: "Students",
        num: true,
        value: ([, count]) => String(count),
      },
      {
        label: "Share",
        value: ([, count]) =>
          h(
            "div",
            { class: "bar-cell" },
            h("div", {
              class: "bar",
              style: { width: `${Math.round((count / total) * 100)}%` },
              "aria-hidden": "true",
            }),
          ),
      },
    ],
    Object.entries(dist),
  );
}

async function courseDashboard(container, courseId) {
  container.replaceChildren(h("p", { class: "muted" }, "Loading course…"));
  announce("Loading course dashboard");

  let d;

  try {
    d = await api(`/dashboard/courses/${encodeURIComponent(courseId)}`);
  } catch (err) {
    container.replaceChildren(
      h("div", { class: "alert", role: "alert" }, err.message),
    );
    return;
  }

  const report = (format) =>
    `${API}/reports/courses/${encodeURIComponent(courseId)}?format=${format}`;

  container.replaceChildren(
    h("h2", { id: "course-heading" }, `${d.courseCode} – ${d.courseTitle}`),

    h(
      "div",
      { class: "button-row" },
      h(
        "a",
        {
          class: "button button-secondary",
          href: report("csv"),
          download: "",
        },
        "Download CSV report",
      ),
      h(
        "a",
        {
          class: "button button-secondary",
          href: report("pdf"),
          download: "",
        },
        "Download PDF report",
      ),
    ),

    h(
      "div",
      { class: "cards spaced" },
      card("Enrolled", String(d.enrolled)),
      card("Class average", fmt(d.classAverage, "%")),
      card("At risk", String(d.atRisk.length)),
      card("Low assignment completion", String(d.lowCompletion.length)),
    ),

    h("h2", {}, "At-risk students"),

    d.atRisk.length
      ? h(
          "ul",
          { class: "risk-list" },
          d.atRisk.map((r) =>
            h(
              "li",
              {},
              h("strong", {}, `${r.name} (${r.usn})`),
              ": ",
              r.reasons.join(", "),
            ),
          ),
        )
      : h("p", { class: "empty" }, "No students are at risk."),

    h("h2", {}, "Marks distribution"),
    distribution(d.marksDistribution),

    h("h2", {}, "Exams"),

    table(
      "Exam summaries in percent",
      [
        { label: "Exam", value: (e) => e.examType },
        { label: "Count", num: true, value: (e) => String(e.count) },
        { label: "Highest", num: true, value: (e) => `${e.highest}%` },
        { label: "Lowest", num: true, value: (e) => `${e.lowest}%` },
        { label: "Average", num: true, value: (e) => `${e.average}%` },
        { label: "Pass rate", num: true, value: (e) => `${e.pass_rate}%` },
      ],
      d.exams,
      "No exam results yet.",
    ),

    h("h2", {}, "Students"),

    table(
      "All students in this course",
      [
        { label: "Name", value: (s) => `${s.name} (${s.usn})` },
        {
          label: "Attendance",
          num: true,
          value: (s) => fmt(s.attendancePct, "%"),
        },
        {
          label: "Average",
          num: true,
          value: (s) => fmt(s.averageMarks, "%"),
        },
        {
          label: "Trend",
          value: (s) => (s.declining ? "↓ Declining" : "Stable"),
        },
        {
          label: "Assignments",
          num: true,
          value: (s) => fmt(s.assignmentCompletionPct, "%"),
        },
        { label: "Status", value: (s) => riskBadge(s.atRisk) },
      ],
      d.students,
      "No students enrolled.",
    ),
  );

  announce(`${d.courseCode} dashboard loaded`);
}

function courseSection(courses) {
  const output = h("div", { id: "course-output", "aria-live": "off" });

  if (!courses.length) {
    return h("p", { class: "empty" }, "No courses are assigned to you yet.");
  }

  const select = h(
    "select",
    { id: "course-select" },
    courses.map((c) =>
      h("option", { value: c.courseId }, `${c.code} – ${c.title}`),
    ),
  );

  select.addEventListener("change", () =>
    courseDashboard(output, select.value),
  );

  courseDashboard(output, select.value);

  return h(
    "section",
    { "aria-label": "Course dashboard" },
    h(
      "div",
      { class: "toolbar" },
      h(
        "div",
        { class: "field" },
        h("label", { for: "course-select" }, "Course"),
        select,
      ),
    ),
    output,
  );
}

async function showFaculty(me) {
  const { courses } = await api("/dashboard/my-courses");
  show("Faculty dashboard", `Signed in as ${me.username}`, courseSection(courses));
}

/* ---------------- Admin ---------------- */

async function departmentSummary(container, department) {
  container.replaceChildren(h("p", { class: "muted" }, "Loading department…"));

  let s;

  try {
    s = await api(`/dashboard/departments/${encodeURIComponent(department)}`);
  } catch (err) {
    container.replaceChildren(
      h("div", { class: "alert", role: "alert" }, err.message),
    );
    return;
  }

  container.replaceChildren(
    h(
      "div",
      { class: "cards" },
      card("Courses", String(s.totals.courses)),
      card("Enrolments", String(s.totals.enrolled)),
      card("Average marks", fmt(s.totals.average, "%")),
      card("At risk", String(s.totals.atRiskCount)),
    ),

    h(
      "div",
      { class: "spaced" },
      table(
        `Courses in ${s.department}`,
        [
          { label: "Course", value: (c) => `${c.code} – ${c.title}` },
          { label: "Enrolled", num: true, value: (c) => String(c.enrolled) },
          { label: "Average", num: true, value: (c) => fmt(c.average, "%") },
          { label: "At risk", num: true, value: (c) => String(c.atRiskCount) },
        ],
        s.courses,
        "No courses.",
      ),
    ),
  );

  announce(`${s.department} summary loaded`);
}

async function showAdmin(me) {
  const [{ departments }, { courses }] = await Promise.all([
    api("/dashboard/departments"),
    api("/dashboard/my-courses"),
  ]);

  const deptOutput = h("div", {});
  let deptSection;

  if (departments.length) {
    const select = h(
      "select",
      { id: "department-select" },
      departments.map((d) => h("option", { value: d }, d)),
    );

    select.addEventListener("change", () =>
      departmentSummary(deptOutput, select.value),
    );

    departmentSummary(deptOutput, select.value);

    deptSection = [
      h(
        "div",
        { class: "toolbar" },
        h(
          "div",
          { class: "field" },
          h("label", { for: "department-select" }, "Department"),
          select,
        ),
      ),
      deptOutput,
    ];
  } else {
    deptSection = [
      h("p", { class: "empty" }, "No departments have courses yet."),
    ];
  }

  show(
    "Administrator summary",
    `Signed in as ${me.username}`,
    h(
      "section",
      { "aria-labelledby": "dept-heading" },
      h("h2", { id: "dept-heading" }, "Department summary"),
      deptSection,
    ),
    h(
      "section",
      { "aria-labelledby": "courses-heading" },
      h("h2", { id: "courses-heading" }, "Course dashboards"),
      courseSection(courses),
    ),
  );
}

/* ---------------- Start ---------------- */

async function start() {
  let me;

  try {
    me = await api("/auth/me");
  } catch (_) {
    showLogin();
    return;
  }

  accountNav.hidden = false;
  signedInAs.textContent = `${me.username} (${me.role.toLowerCase()})`;

  try {
    if (me.role === "STUDENT") await showStudent();
    else if (me.role === "FACULTY") await showFaculty(me);
    else await showAdmin(me);
  } catch (err) {
    if (err.status !== 401) {
      show(
        "Something went wrong",
        null,
        h("div", { class: "alert", role: "alert" }, err.message),
      );
    }
  }
}

document.getElementById("logout-button").addEventListener("click", logout);
start();