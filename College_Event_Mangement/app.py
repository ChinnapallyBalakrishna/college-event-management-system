import os
import sqlite3
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, g
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key-before-deployment")


@app.after_request
def prevent_dashboard_caching(response):
    """Prevent browsers from caching dashboard pages."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


DATABASE = os.path.join(os.path.dirname(__file__), "college_events.db")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL COLLATE NOCASE,
        department TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        category TEXT NOT NULL,
        event_date TEXT NOT NULL,
        location TEXT NOT NULL,
        capacity INTEGER NOT NULL CHECK(capacity > 0),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS registrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        student_name TEXT NOT NULL,
        student_email TEXT NOT NULL,
        student_department TEXT NOT NULL,
        registered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,
        UNIQUE(event_id, student_email)
    );
        CREATE TABLE IF NOT EXISTS hr_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS coordinators (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        phone TEXT NOT NULL,
        department TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)
    # Demo account for local college-project use. Change the password before deployment.
    existing = db.execute("SELECT id FROM admins WHERE username = ?", ("admin",)).fetchone()
    if not existing:
        db.execute("INSERT INTO admins (username, password_hash) VALUES (?, ?)",
                   ("admin", generate_password_hash("admin123")))
    hr_existing = db.execute("SELECT id FROM hr_users WHERE username = ?", ("hr",)).fetchone()
    if not hr_existing:
        db.execute("INSERT INTO hr_users (username, password_hash) VALUES (?, ?)",
                   ("hr", generate_password_hash("hr12345")))
    count = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    if count == 0:
        db.executemany("""
            INSERT INTO events (title, description, category, event_date, location, capacity)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [
            ("TechFest 2026", "A day of coding, quizzes, and technology talks.", "Technical", "2026-11-20T10:00", "Main Auditorium", 120),
            ("Cultural Night", "Music, dance, and performances by college students.", "Cultural", "2026-12-05T17:00", "Open Ground", 200),
            ("Web Development Workshop", "Learn the basics of building websites.", "Workshop", "2026-11-28T14:00", "Computer Lab 2", 40),
        ])
    db.commit()
    db.close()

def student_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("student_id"):
            flash("Please log in with your student account first.", "warning")
            return redirect(url_for("student_login"))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            flash("Please log in as an admin first.", "warning")
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped

def hr_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("hr_id"):
            flash("Please log in as HR first.", "warning")
            return redirect(url_for("hr_login"))
        return view(*args, **kwargs)
    return wrapped

@app.route("/")
def index():
    db = get_db()
    events = db.execute("""
        SELECT e.*, COUNT(r.id) AS registered_count
        FROM events e LEFT JOIN registrations r ON e.id = r.event_id
        GROUP BY e.id ORDER BY e.event_date
    """).fetchall()
    return render_template("index.html", events=events)
@app.route("/register/<int:event_id>", methods=["GET", "POST"])
def register(event_id):
    db = get_db()

    event = db.execute("""
        SELECT e.*, COUNT(r.id) AS registered_count
        FROM events e
        LEFT JOIN registrations r ON e.id = r.event_id
        WHERE e.id = ?
        GROUP BY e.id
    """, (event_id,)).fetchone()

    if event is None:
        flash("Event not found.", "danger")
        return redirect(url_for("index"))

    if not session.get("student_id"):
        flash("Please sign in or create a student account to register for events.", "warning")
        return redirect(url_for(
            "student_login",
            next=url_for("register", event_id=event_id)
        ))

    student = db.execute(
        "SELECT * FROM students WHERE id = ?",
        (session["student_id"],)
    ).fetchone()

    # Check whether the student still exists
    if student is None:
        session.pop("student_id", None)
        flash("Student account not found. Please sign in again.", "warning")
        return redirect(url_for("student_login"))

    existing = db.execute("""
        SELECT id FROM registrations
        WHERE event_id = ?
        AND lower(student_email) = lower(?)
    """, (event_id, student["email"])).fetchone()

    if request.method == "POST":
        if existing:
            flash("You are already registered for this event.", "warning")

        elif event["registered_count"] >= event["capacity"]:
            flash("Sorry, this event is full.", "danger")

        else:
            try:
                db.execute("""
                    INSERT INTO registrations
                    (event_id, student_name, student_email, student_department)
                    VALUES (?, ?, ?, ?)
                """, (
                    event_id,
                    student["full_name"],
                    student["email"].lower(),
                    student["department"]
                ))

                db.commit()
                flash("Registration successful! You can see it in your student dashboard.", "success")
                return redirect(url_for("student_dashboard"))

            except sqlite3.IntegrityError:
                flash("You are already registered for this event.", "warning")

    return render_template(
        "register.html",
        event=event,
        student=student,
        already_registered=bool(existing)
    )
@app.route("/student/signup", methods=["GET", "POST"])
def student_signup():
    if session.get("student_id"):
        return redirect(url_for("student_dashboard"))
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        department = request.form.get("department", "").strip()
        password = request.form.get("password", "")
        if not all([name, email, department, password]):
            flash("Please fill in every field.", "danger")
        elif len(password) < 8:
            flash("Password must be at least 8 characters long.", "danger")
        else:
            try:
                db = get_db()
                cursor = db.execute("INSERT INTO students (full_name, email, department, password_hash) VALUES (?, ?, ?, ?)",
                                    (name, email, department, generate_password_hash(password)))
                db.commit()
                session["student_id"] = cursor.lastrowid
                session["student_name"] = name
                session["student_email"] = email
                flash("Your student account is ready!", "success")
                return redirect(url_for("student_dashboard"))
            except sqlite3.IntegrityError:
                flash("An account with this email already exists. Please log in.", "warning")
    return render_template("student_signup.html")

@app.route("/student/login", methods=["GET", "POST"])
def student_login():
    if session.get("student_id"):
        return redirect(url_for("student_dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        student = get_db().execute("SELECT * FROM students WHERE lower(email) = lower(?)", (email,)).fetchone()
        if student and check_password_hash(student["password_hash"], password):
            next_url = request.args.get("next", "")
            session["student_id"] = student["id"]
            session["student_name"] = student["full_name"]
            session["student_email"] = student["email"]
            if next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect(url_for("student_dashboard"))
        flash("Incorrect email or password.", "danger")
    return render_template("student_login.html")

@app.route("/student/dashboard")
@student_required
def student_dashboard():
    db = get_db()

    student = db.execute(
        "SELECT * FROM students WHERE id = ?",
        (session["student_id"],)
    ).fetchone()

    # Check whether the student exists
    if student is None:
        session.pop("student_id", None)
        flash("Student account not found. Please log in again.", "warning")
        return redirect(url_for("student_login"))

    registrations = db.execute("""
        SELECT r.id AS registration_id, r.registered_at, e.*
        FROM registrations r
        JOIN events e ON e.id = r.event_id
        WHERE lower(r.student_email) = lower(?)
        ORDER BY e.event_date
    """, (student["email"],)).fetchall()

    events = db.execute("""
        SELECT e.*, COUNT(r.id) AS registered_count
        FROM events e
        LEFT JOIN registrations r ON r.event_id = e.id
        GROUP BY e.id
        ORDER BY e.event_date
    """).fetchall()

    return render_template(
        "student_dashboard.html",
        student=student,
        registrations=registrations,
        events=events
    )

@app.route("/student/cancel/<int:registration_id>", methods=["POST"])
@student_required
def cancel_student_registration(registration_id):
    db = get_db()
    db.execute("DELETE FROM registrations WHERE id = ? AND lower(student_email) = lower(?)",
               (registration_id, session.get("student_email", "")))
    db.commit()
    flash("Your event registration has been cancelled.", "success")
    return redirect(url_for("student_dashboard"))

@app.route("/student/logout")
def student_logout():
    session.pop("student_id", None)
    session.pop("student_name", None)
    session.pop("student_email", None)
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_id"):
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        admin = get_db().execute("SELECT * FROM admins WHERE username = ?", (username,)).fetchone()
        if admin and check_password_hash(admin["password_hash"], password):
            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]
            return redirect(url_for("admin_dashboard"))
        flash("Incorrect username or password.", "danger")
    return render_template("login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_id", None)
    session.pop("admin_username", None)
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    events = db.execute("""
        SELECT e.*, COUNT(r.id) AS registered_count
        FROM events e LEFT JOIN registrations r ON e.id = r.event_id
        GROUP BY e.id ORDER BY e.event_date
    """).fetchall()
    total_students = db.execute("SELECT COUNT(*) FROM registrations").fetchone()[0]
    return render_template("admin.html", events=events, total_students=total_students)

def validate_event_form():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    category = request.form.get("category", "").strip()
    event_date = request.form.get("event_date", "").strip()
    location = request.form.get("location", "").strip()
    capacity_text = request.form.get("capacity", "").strip()
    if not all([title, description, category, event_date, location, capacity_text]):
        return None, "Please fill in every field."
    try:
        parsed = datetime.fromisoformat(event_date)
        capacity = int(capacity_text)
        if capacity < 1:
            raise ValueError
    except ValueError:
        return None, "Enter a valid date and a capacity greater than zero."
    return (title, description, category, parsed.strftime("%Y-%m-%dT%H:%M"), location, capacity), None

@app.route("/admin/events/new", methods=["GET", "POST"])
@admin_required
def new_event():
    if request.method == "POST":
        data, error = validate_event_form()
        if error:
            flash(error, "danger")
        else:
            db = get_db()
            db.execute("""
                INSERT INTO events (title, description, category, event_date, location, capacity)
                VALUES (?, ?, ?, ?, ?, ?)
            """, data)
            db.commit()
            flash("Event created.", "success")
            return redirect(url_for("admin_dashboard"))
    return render_template("event_form.html", event=None, page_title="Add event")

@app.route("/admin/events/<int:event_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_event(event_id):
    db = get_db()
    event = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if event is None:
        flash("Event not found.", "danger")
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        data, error = validate_event_form()
        if error:
            flash(error, "danger")
        else:
            db.execute("""
                UPDATE events SET title=?, description=?, category=?, event_date=?, location=?, capacity=?
                WHERE id=?
            """, (*data, event_id))
            db.commit()
            flash("Event updated.", "success")
            return redirect(url_for("admin_dashboard"))
    return render_template("event_form.html", event=event, page_title="Edit event")

@app.route("/admin/events/<int:event_id>/delete", methods=["POST"])
@admin_required
def delete_event(event_id):
    db = get_db()
    db.execute("DELETE FROM events WHERE id = ?", (event_id,))
    db.commit()
    flash("Event and its registrations were deleted.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/events/<int:event_id>/registrations")
@admin_required
def registrations(event_id):
    db = get_db()
    event = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if event is None:
        flash("Event not found.", "danger")
        return redirect(url_for("admin_dashboard"))
    students = db.execute("""
        SELECT
    id AS registration_id,
    student_name,
    student_email,
    student_department,
    registered_at
FROM registrations
WHERE event_id = ?
ORDER BY registered_at DESC
    """, (event_id,)).fetchall()
    return render_template("registrations.html", event=event, students=students)


@app.route("/admin/registrations/delete/<int:registration_id>", methods=["POST"])
@admin_required
def admin_delete_registration(registration_id):
    db = get_db()

    registration = db.execute(
        "SELECT id, event_id FROM registrations WHERE id = ?",
        (registration_id,)
    ).fetchone()

    if registration is None:
        flash("Registration not found.", "danger")
        return redirect(url_for("admin_dashboard"))

    event_id = registration["event_id"]

    db.execute(
        "DELETE FROM registrations WHERE id = ?",
        (registration_id,)
    )
    db.commit()

    flash("Registration deleted successfully.", "success")

    return redirect(url_for("registrations", event_id=event_id))



@app.route("/hr/login", methods=["GET", "POST"])
def hr_login():
    if session.get("hr_id"):
        return redirect(url_for("hr_dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        hr_user = get_db().execute(
            "SELECT * FROM hr_users WHERE username = ?", (username,)
        ).fetchone()
        if hr_user and check_password_hash(hr_user["password_hash"], password):
            session["hr_id"] = hr_user["id"]
            session["hr_username"] = hr_user["username"]
            return redirect(url_for("hr_dashboard"))
        flash("Incorrect HR username or password.", "danger")
    return render_template("hr_login.html")


@app.route("/hr/logout")
def hr_logout():
    session.pop("hr_id", None)
    session.pop("hr_username", None)
    flash("HR has been logged out.", "success")
    return redirect(url_for("hr_login"))



def get_department_summary(db):
    return db.execute("""
        SELECT
            d.department,

            (SELECT c.id
             FROM coordinators c
             WHERE lower(c.department) = lower(d.department)
             ORDER BY c.id
             LIMIT 1) AS coordinator_id,

            (SELECT c.full_name
             FROM coordinators c
             WHERE lower(c.department) = lower(d.department)
             ORDER BY c.id
             LIMIT 1) AS coordinator_name,

            (SELECT c.email
             FROM coordinators c
             WHERE lower(c.department) = lower(d.department)
             ORDER BY c.id
             LIMIT 1) AS coordinator_email,

            (SELECT COUNT(DISTINCT r.student_email)
             FROM registrations r
             WHERE lower(r.student_department) = lower(d.department))
             AS student_count,

            (SELECT COUNT(*)
             FROM registrations r
             WHERE lower(r.student_department) = lower(d.department))
             AS registration_count,

            (SELECT COUNT(DISTINCT r.event_id)
             FROM registrations r
             WHERE lower(r.student_department) = lower(d.department))
             AS event_count

        FROM (
            SELECT department FROM students
            UNION
            SELECT department FROM coordinators
        ) AS d

        ORDER BY d.department COLLATE NOCASE
    """).fetchall()


@app.route("/hr")
@hr_required
def hr_dashboard():
    db = get_db()

    departments = get_department_summary(db)

    total_departments = len(departments)

    total_coordinators = db.execute(
        "SELECT COUNT(*) FROM coordinators"
    ).fetchone()[0]

    total_students = db.execute("""
        SELECT COUNT(DISTINCT student_email)
        FROM registrations
    """).fetchone()[0]

    total_events = db.execute(
        "SELECT COUNT(*) FROM events"
    ).fetchone()[0]

    return render_template(
        "hr_dashboard.html",
        departments=departments,
        total_departments=total_departments,
        total_coordinators=total_coordinators,
        total_students=total_students,
        total_events=total_events
    )

@app.route("/hr/students")
@hr_required
def hr_students():
    db = get_db()

    students = db.execute("""
        SELECT id, full_name, email, department, created_at
        FROM students
        ORDER BY full_name COLLATE NOCASE
    """).fetchall()

    total_students = db.execute(
        "SELECT COUNT(*) FROM students"
    ).fetchone()[0]

    return render_template(
        "hr_students.html",
        students=students,
        total_students=total_students
    )

@app.route("/hr/registrations/<int:registration_id>/delete", methods=["POST"])
@hr_required
def hr_delete_registration(registration_id):
    db = get_db()

    registration = db.execute(
        "SELECT id FROM registrations WHERE id = ?",
        (registration_id,)
    ).fetchone()

    if registration is None:
        flash("Registration not found.", "danger")
    else:
        db.execute(
            "DELETE FROM registrations WHERE id = ?",
            (registration_id,)
        )
        db.commit()
        flash("Registration deleted successfully.", "success")

    return redirect(request.referrer or url_for("hr_dashboard"))

@app.route("/hr/students/<int:student_id>/edit", methods=["GET", "POST"])
@hr_required
def hr_edit_student(student_id):
    db = get_db()

    student = db.execute(
        "SELECT * FROM students WHERE id = ?",
        (student_id,)
    ).fetchone()

    if student is None:
        flash("Student not found.", "danger")
        return redirect(url_for("hr_students"))

    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        department = request.form.get("department", "").strip()

        if not all([name, email, department]):
            flash("Please fill in all fields.", "danger")
        else:
            duplicate = db.execute("""
                SELECT id FROM students
                WHERE email = ? COLLATE NOCASE AND id != ?
            """, (email, student_id)).fetchone()

            if duplicate:
                flash("Email already exists.", "danger")
            else:
                db.execute("""
                    UPDATE students
                    SET full_name = ?, email = ?, department = ?
                    WHERE id = ?
                """, (name, email, department, student_id))

                db.commit()
                flash("Student updated successfully.", "success")
                return redirect(url_for("hr_students"))

    return render_template("hr_student_form.html", student=student)

@app.route("/hr/students/<int:student_id>/delete", methods=["POST"])
@hr_required
def hr_delete_student(student_id):
    db = get_db()

    student = db.execute(
        "SELECT id FROM students WHERE id = ?",
        (student_id,)
    ).fetchone()

    if student:
        db.execute(
            "DELETE FROM students WHERE id = ?",
            (student_id,)
        )
        db.commit()
        flash("Student deleted successfully.", "success")
    else:
        flash("Student not found.", "danger")

    return redirect(url_for("hr_students"))



@app.route("/hr/departments")
@hr_required
def hr_departments():
    departments = get_department_summary(get_db())
    return render_template("hr_departments.html", departments=departments)
@app.route("/hr/coordinators/new", methods=["GET", "POST"])
@hr_required
def hr_add_coordinator():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        department = request.form.get("department", "").strip()
        if not all([name, email, phone, department]):
            flash("Please fill in every coordinator field.", "danger")
        else:
            try:
                db.execute("""
                    INSERT INTO coordinators (full_name, email, phone, department)
                    VALUES (?, ?, ?, ?)
                """, (name, email, phone, department))
                db.commit()
                flash("Department coordinator added successfully.", "success")
                return redirect(url_for("hr_dashboard"))
            except sqlite3.IntegrityError:
                flash("A coordinator with this email already exists.", "warning")
    departments = db.execute("""
        SELECT department FROM students
        UNION SELECT department FROM coordinators
        ORDER BY department COLLATE NOCASE
    """).fetchall()
    selected_department = request.args.get("department", "").strip()

    return render_template(
        "hr_coordinator_form.html",
        coordinator=None,
        departments=departments,
        selected_department=selected_department
    )
@app.route("/hr/coordinators/<int:coordinator_id>/edit", methods=["GET", "POST"])
@hr_required
def hr_edit_coordinator(coordinator_id):
    db = get_db()
    coordinator = db.execute(
        "SELECT * FROM coordinators WHERE id = ?", (coordinator_id,)
    ).fetchone()
    if coordinator is None:
        flash("Coordinator not found.", "danger")
        return redirect(url_for("hr_dashboard"))
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        department = request.form.get("department", "").strip()
        if not all([name, email, phone, department]):
            flash("Please fill in every coordinator field.", "danger")
        else:
            try:
                db.execute("""
                    UPDATE coordinators
                    SET full_name=?, email=?, phone=?, department=?
                    WHERE id=?
                """, (name, email, phone, department, coordinator_id))
                db.commit()
                flash("Coordinator details updated.", "success")
                return redirect(url_for("hr_department_details",
                                         department=department))
            except sqlite3.IntegrityError:
                flash("Another coordinator already uses this email.", "warning")
    departments = db.execute("""
        SELECT department FROM students
        UNION SELECT department FROM coordinators
        ORDER BY department COLLATE NOCASE
    """).fetchall()
    return render_template("hr_coordinator_form.html",
                           coordinator=coordinator, departments=departments)


@app.route("/hr/coordinators/<int:coordinator_id>/delete", methods=["POST"])
@hr_required
def hr_delete_coordinator(coordinator_id):
    db = get_db()
    coordinator = db.execute(
        "SELECT department FROM coordinators WHERE id = ?", (coordinator_id,)
    ).fetchone()
    if coordinator:
        db.execute("DELETE FROM coordinators WHERE id = ?", (coordinator_id,))
        db.commit()
        flash("Coordinator deleted.", "success")
        return redirect(url_for("hr_department_details",
                                 department=coordinator["department"]))
    flash("Coordinator not found.", "warning")
    return redirect(url_for("hr_dashboard"))


@app.route("/hr/departments/<path:department>")
@hr_required
def hr_department_details(department):
    """Show department details using the shared coordinator-details template."""
    db = get_db()

    # A department can have no coordinator, or more than one. Use the first
    # coordinator for the contact panel; show a safe placeholder if none exists.
    coordinator = db.execute("""
        SELECT id, full_name AS coordinator_name, email, phone, department
        FROM coordinators
        WHERE lower(department) = lower(?)
        ORDER BY full_name COLLATE NOCASE
        LIMIT 1
    """, (department,)).fetchone()

    if coordinator is None:
        coordinator = {
            "id": None,
            "coordinator_name": "Not Assigned",
            "email": "—",
            "phone": "—",
            "department": department,
        }
    registrations = db.execute("""
        SELECT r.id AS registration_id,
            r.student_name,
            r.student_email,
            r.student_department,
            r.registered_at,
            e.title
        FROM registrations r
        JOIN events e ON e.id = r.event_id
        WHERE lower(r.student_department) = lower(?)
        ORDER BY r.registered_at DESC
    """, (department,)).fetchall()
    summary = db.execute("""
        SELECT COUNT(DISTINCT student_email) AS total_students,
               COUNT(*) AS total_registrations
        FROM registrations
        WHERE lower(student_department) = lower(?)
    """, (department,)).fetchone()

    event_totals = db.execute("""
        SELECT e.title, COUNT(r.id) AS total
        FROM events e
        JOIN registrations r ON r.event_id = e.id
        WHERE lower(r.student_department) = lower(?)
        GROUP BY e.id, e.title
        ORDER BY e.title
    """, (department,)).fetchall()

    return render_template(
        "hr_coordinator_details.html",
        coordinator=coordinator,
        total_students=summary["total_students"],
        total_registrations=summary["total_registrations"],
        registrations=registrations,
        event_totals=event_totals
    )


@app.context_processor
def inject_year():
    return {"current_year": datetime.now().year}



@app.route("/hr/coordinators/<int:coordinator_id>")
@hr_required
def hr_coordinator_details(coordinator_id):
    db = get_db()

    coordinator = db.execute("""
        SELECT
            id,
            full_name AS coordinator_name,
            email,
            phone,
            department
        FROM coordinators
        WHERE id = ?
    """, (coordinator_id,)).fetchone()

    if coordinator is None:
        flash("Coordinator not found.", "error")
        return redirect(url_for("hr_departments"))

    registrations = db.execute("""
        SELECT
            r.id,
            r.student_name,
            r.student_email,
            r.student_department,
            r.registered_at,
            e.title
        FROM registrations r
        JOIN events e ON e.id = r.event_id
        WHERE lower(r.student_department) = lower(?)
        ORDER BY r.registered_at DESC
    """, (coordinator["department"],)).fetchall()

    summary = db.execute("""
        SELECT
            COUNT(DISTINCT student_email) AS total_students,
            COUNT(*) AS total_registrations
        FROM registrations
        WHERE lower(student_department) = lower(?)
    """, (coordinator["department"],)).fetchone()

    event_totals = db.execute("""
        SELECT
            e.title,
            COUNT(r.id) AS total
        FROM events e
        JOIN registrations r ON r.event_id = e.id
        WHERE lower(r.student_department) = lower(?)
        GROUP BY e.id, e.title
        ORDER BY e.title
    """, (coordinator["department"],)).fetchall()

    return render_template(
        "hr_coordinator_details.html",
        coordinator=coordinator,
        total_students=summary["total_students"],
        total_registrations=summary["total_registrations"],
        registrations=registrations,
        event_totals=event_totals
    )

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
