# College Event Management System

A beginner-friendly college project built with Python, Flask, SQLite, HTML, and CSS.

## Features
- View upcoming events
- Student signup and login with hashed passwords
- Student dashboard with registered events and cancellation
- Student event registration linked to the student account
- Prevent duplicate registration by email for the same event
- Capacity limit for each event
- Admin login
- Create, edit, and delete events
- View the registration list for each event
- SQLite database created automatically

## Requirements
- Python 3.10 or newer
- Internet connection only for the first installation of Flask
- VS Code or another code editor (optional)

## Run on Windows
1. Extract the ZIP file.
2. Open the extracted folder in VS Code.
3. Open Terminal > New Terminal.
4. Create a virtual environment:
   ```bash
   py -m venv .venv
   ```
5. Activate it:
   ```bash
   .venv\Scripts\activate
   ```
6. Install Flask:
   ```bash
   pip install -r requirements.txt
   ```
7. Start the project:
   ```bash
   python app.py
   ```
8. Open `http://127.0.0.1:5000` in your browser.

## Run on macOS or Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Then open `http://127.0.0.1:5000`.

## Student account
Open the website and choose **Student signup** to create a student account. Then log in to view the student dashboard, register for events, and cancel your registrations. There is no default student account.

## Demo admin login
- Username: `admin`
- Password: `admin123`

This is a demo account for local learning only. Do not deploy the project publicly with the demo password or default secret key. Set a strong `SECRET_KEY` environment variable and change the admin password before deployment.

## Folder structure
```text
college_event_management/
├── app.py
├── requirements.txt
├── README.md
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── register.html
│   ├── login.html
│   ├── student_login.html
│   ├── student_signup.html
│   ├── student_dashboard.html
│   ├── admin.html
│   ├── event_form.html
│   └── registrations.html
└── static/
    └── style.css
```

The database file `college_events.db` is created automatically when you run `python app.py`.

## Important note
This is a student/demo project, not a production-ready service. For public deployment, add CSRF protection, stronger secret management, password-change functionality, rate limiting, and more robust validation.
