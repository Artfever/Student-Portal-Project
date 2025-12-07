from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
from datetime import datetime
import re
from flask_socketio import SocketIO, emit, join_room
from flask import request
import pandas as pd
import sqlite3
import math
import random
import string
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
from datetime import datetime, timezone
import re
from flask_socketio import SocketIO, emit, join_room
from werkzeug.utils import secure_filename
import os
import uuid


def get_db():
    """Main DB (flake.db) connection."""
    conn = sqlite3.connect('flake.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_ann_db():
    """Announcements DB (announcements.db) connection."""
    conn = sqlite3.connect('announcements.db')
    conn.row_factory = sqlite3.Row
    return conn


def get_db():
    """Create a database connection with row factory for dictionary-like access"""
    conn = sqlite3.connect('flake.db')
    conn.row_factory = sqlite3.Row  # This allows accessing columns by name
    return conn

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")
app.secret_key = "supersecretkey"  # Needed for session handling

@app.route('/')
def home():
    return render_template('main.html')  # your first "What are you?" page

# ---------- TEACHER LOGIN ----------
@app.route('/login_T.html', methods=['GET', 'POST'])
def teacher_login():
    if request.method == 'POST':
        tid = request.form['teacher_id']
        password = request.form['password']

        conn = sqlite3.connect('flake.db')
        cur = conn.cursor()
        cur.execute("SELECT Name, Teacher_ID FROM teachers WHERE Teacher_ID=?", (tid,))
        teacher = cur.fetchone()
        conn.close()

        if teacher:
            real_pass = ''.join([ch for ch in tid if ch.isdigit()])[-4:]
            if password == real_pass:
                session['user'] = tid
                session['user_name'] = teacher[0]
                session['Teacher_ID'] = teacher[1]   # ✅ FIX ADDED
                session['user_type'] = 'teacher'
                return redirect(url_for('teacher_home'))
            else:
                flash("Invalid ID or Password", "danger")
        else:
            flash("Invalid ID or Password", "danger")

    return render_template('login_T.html')

# ---------- STUDENT LOGIN ----------
@app.route('/login_S.html', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        sid = request.form['student_id']
        password = request.form['password']

        conn = sqlite3.connect('flake.db')
        cur = conn.cursor()
        cur.execute("SELECT Name FROM students WHERE Roll_No=? AND password=?", (sid, password))
        student = cur.fetchone()
        conn.close()

        if student:
            session['user'] = sid
            session['user_name'] = student[0]  # store name in session
            session['user_type'] = 'student'
            return redirect(url_for('student_home'))
        else:
            flash("Invalid ID or Password", "danger")

    return render_template('login_S.html')


# ---------- ADMIN LOGIN ----------
@app.route('/login_A.html', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        aid = request.form['admin_id'].strip()
        password = request.form['password'].strip()

        conn = sqlite3.connect('flake.db')
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM admins WHERE admin_id=? AND password=?", (aid, password))
        admin = cur.fetchone()
        conn.close()

        if admin:
            # Store admin ID and type in session
            session['user'] = aid
            session['user_type'] = 'admin'

            return redirect(url_for('admin_dashboard'))
        else:
            flash("Invalid ID or Password", "danger")

    return render_template('login_A.html')



@app.route('/teacher_dashboard')
def teacher_dashboard():
    return render_template(
        'teacher_dashboard.html',
        user=session.get('user'),
        user_name=session.get('user_name')
    )


@app.route('/student_dashboard')
def student_dashboard():
    return render_template(
        'student_dashboard.html',
        user=session.get('user'),
        user_name=session.get('user_name')
    )


@app.route('/admin_dashboard')
def admin_dashboard():
    return render_template('admin_dashboard.html', user=session.get('user'))


# ---------- LOGOUT ----------
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))


# ---------- CHANGE PASSWORD ----------
@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    # Require logged-in user
    if 'user' not in session:
        return redirect(url_for('home'))

    # GET: render the change password page
    if request.method == 'GET':
        return render_template('change_p.html')

    # POST: handle AJAX actions (verify_old, set_new)
    data = request.get_json(silent=True) or {}
    action = data.get('action')

    user = session.get('user')
    user_type = session.get('user_type')

    # Only students and admins have editable passwords in this app
    if user_type == 'student':
        table = 'students'
        id_col = 'Roll_No'
        pass_col = 'password'
    elif user_type == 'admin':
        table = 'admins'
        id_col = 'admin_id'
        pass_col = 'password'
    else:
        return jsonify({'status': 'error', 'message': 'Password change not supported for this account type.'})

    conn = get_db()
    cur = conn.cursor()
    # fetch current password
    try:
        cur.execute(f"SELECT {pass_col} FROM {table} WHERE {id_col} = ?", (user,))
        row = cur.fetchone()
    except Exception as e:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Database error.'})

    if not row:
        conn.close()
        return jsonify({'status': 'error', 'message': 'User not found.'})

    current_pass = row[0]

    if action == 'verify_old':
        old = data.get('old_password', '')
        conn.close()
        if old == current_pass:
            return jsonify({'status': 'ok'})
        else:
            return jsonify({'status': 'error', 'message': 'Incorrect current password.'})

    if action == 'set_new':
        new = data.get('new_password', '')
        if not new or len(new) < 4:
            conn.close()
            return jsonify({'status': 'error', 'message': 'New password must be at least 4 characters.'})

        try:
            cur.execute(f"UPDATE {table} SET {pass_col} = ? WHERE {id_col} = ?", (new, user))
            conn.commit()
        except Exception as e:
            conn.close()
            return jsonify({'status': 'error', 'message': 'Failed to update password.'})

        conn.close()
        return jsonify({'status': 'ok'})

    conn.close()
    return jsonify({'status': 'error', 'message': 'Invalid action.'})


# ---------- STUDENT HOME -----------
@app.route('/student_home')
def student_home():
    if 'user' not in session:
        return redirect(url_for('student_login'))

    sid = session['user']

    conn = sqlite3.connect('flake.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM students WHERE Roll_No = ?", (sid,))
    student = cur.fetchone()
    conn.close()

    # -------------------------------
    # Extract batch, degree, and section from Roll_No
    # Example Roll_No: FA23-SE-A-1234
    # -------------------------------
    roll_no = student['Roll_No']
    roll_parts = roll_no.split('-')

    batch = roll_parts[1] if len(roll_parts) > 1 else "N/A"
    degree_code = roll_parts[2] if len(roll_parts) > 2 else "N/A"
    section = roll_parts[3][0] if len(roll_parts) > 3 else "N/A"

    degree_map = {
        'SE': 'Software Engineering',
        'AI': 'Artificial Intelligence',
        'DS': 'Data Science',
        'CY': 'Cyber Security'
    }
    degree_name = degree_map.get(degree_code, degree_code)

    return render_template(
        'home_S.html',
        student=student,
        batch=batch,
        degree_name=degree_name,
        section=section
    )


# -------------- TENTATIVE STUDY PLAN -----------------------
@app.route('/student_study_plan')
def student_study_plan():
    return render_template('tentativeStudyPlan.html')


# ------------------ TEACHER HOME -----------------------
@app.route('/teacher_home')
def teacher_home():
    if 'user' not in session:
        return redirect(url_for('teacher_login'))

    tid = session['user']  # Example: T-M-SE-CS-1001

    conn = sqlite3.connect('flake.db')
    cur = conn.cursor()
    cur.execute("""
        SELECT Teacher_ID, Name, Gender, DOB, CNIC, Email, Mobile_No,
               Current_Address, Permanent_Address, Home_Phone, Postal_Code,
               Department, Course_Name
        FROM teachers
        WHERE Teacher_ID = ?
    """, (tid,))
    row = cur.fetchone()
    conn.close()

    if not row:
        flash("Teacher not found", "danger")
        return redirect(url_for('teacher_dashboard'))

    # Convert fetched row into dictionary
    teacher = {
        'Teacher_ID': row[0],
        'Name': row[1],
        'Gender': row[2],
        'DOB': row[3],
        'CNIC': row[4],
        'Email': row[5],
        'Mobile_No': row[6],
        'Current_Address': row[7],
        'Permanent_Address': row[8],
        'Home_Phone': row[9],
        'Postal_Code': row[10],
        'Department': row[11],
        'Course_Name': row[12]
    }

    # ---------- Extract domain from Teacher_ID ----------
    parts = tid.split('-')
    domain_code = parts[3].upper() if len(parts) > 3 else ""
    domain_map = {
        "CS": "Computing",
        "MT": "Mathematics",
        "CL": "Computing",
        "SS": "Social Sciences"
    }
    domain = domain_map.get(domain_code, "Unknown")

    # ---------- Courses (from same table) ----------
    courses = [teacher['Course_Name']] if teacher['Course_Name'] else ["No courses assigned"]

    return render_template(
        'home_T.html',
        teacher=teacher,
        department=teacher['Department'],
        domain=domain,
        courses=courses
    )


from datetime import datetime

# ---------- STUDENT ATTENDANCE (already mostly there) ----------
@app.route('/student_attendance')
def student_attendance():
    if 'user' not in session:
        return redirect(url_for('student_login'))

    roll_no = session['user']

    conn = get_db()
    cur = conn.cursor()

    # courses for this student
    cur.execute("""
        SELECT c.Course_Code, c.Course_Name
        FROM enrollments e
        JOIN courses c ON e.Course_Code = c.Course_Code
        WHERE e.Roll_No = ?
    """, (roll_no,))
    courses = cur.fetchall()

    # attendance rows
    cur.execute("""
        SELECT Course_Code, Date, Attendance
        FROM attendance
        WHERE Roll_No = ?
        ORDER BY Date
    """, (roll_no,))
    attendance_records = cur.fetchall()
    conn.close()

    attendance = {}
    for record in attendance_records:
        course_code = record['Course_Code']
        course_name = next(
            (c['Course_Name'] for c in courses if c['Course_Code'] == course_code),
            course_code
        )

        if course_name not in attendance:
            attendance[course_name] = []

        status_raw = (record['Attendance'] or '').strip().lower()
        if status_raw in ['present', 'p', '1']:
            short = 'P'
        elif status_raw in ['absent', 'a', '0']:
            short = 'A'
        elif status_raw in ['leave', 'l']:
            short = 'L'
        else:
            short = '-'

        date_value = record['Date']
        # keep as stored string, or normalize if you want
        if isinstance(date_value, str):
            date_value = date_value.split(' ')[0]
        attendance[course_name].append({'Date': date_value, 'Status': short})

    return render_template('attendance_S.html',
                           courses=courses,
                           attendance=attendance)


# ---------- TEACHER ATTENDANCE HOME ----------
@app.route('/teacher/attendance')
def teacher_attendance():
    if 'user' not in session:
        return redirect(url_for('teacher_login'))

    teacher_id = session.get('Teacher_ID')

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT c.Course_Code, c.Course_Name
        FROM teacher_courses tc
        JOIN courses c ON tc.Course_Code = c.Course_Code
        WHERE tc.Teacher_ID = ?
    """, (teacher_id,))
    courses = cur.fetchall()
    conn.close()

    return render_template('teacher_attendance.html', courses=courses)


# ---------- TEACHER TAKE ATTENDANCE ----------
@app.route('/teacher/attendance/take/<course_code>', methods=['GET', 'POST'])
def teacher_take_attendance(course_code):
    if 'user' not in session:
        return redirect(url_for('teacher_login'))

    conn = get_db()
    cur = conn.cursor()

    # course info
    cur.execute("SELECT Course_Code, Course_Name FROM courses WHERE Course_Code = ?", (course_code,))
    course = cur.fetchone()
    if not course:
        conn.close()
        flash("Course not found", "danger")
        return redirect(url_for('teacher_attendance'))

    # enrolled students
    cur.execute("""
        SELECT s.Roll_No, s.Name
        FROM enrollments e
        JOIN students s ON e.Roll_No = s.Roll_No
        WHERE e.Course_Code = ?
        ORDER BY s.Roll_No
    """, (course_code,))
    students = cur.fetchall()

    selected_date = None
    selected_class_no = None

    if request.method == 'POST':
        selected_date = request.form['date']
        selected_class_no = int(request.form['class_no'])

        # save each student's status
        for s in students:
            roll = s['Roll_No']
            status = request.form.get(f'status_{roll}', 'P')

            # map P/A/L to text if you want
            if status == 'P':
                status_text = 'Present'
            elif status == 'A':
                status_text = 'Absent'
            else:
                status_text = 'Leave'

            # upsert
            cur.execute("""
                SELECT 1 FROM attendance
                WHERE Roll_No=? AND Course_Code=? AND Date=? AND Class_No=?
            """, (roll, course_code, selected_date, selected_class_no))
            exists = cur.fetchone()

            if exists:
                cur.execute("""
                    UPDATE attendance
                    SET Attendance=?
                    WHERE Roll_No=? AND Course_Code=? AND Date=? AND Class_No=?
                """, (status_text, roll, course_code, selected_date, selected_class_no))
            else:
                cur.execute("""
                    INSERT INTO attendance (Roll_No, Name, Date, Course_Code, Class_No, Attendance)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (roll, s['Name'], selected_date, course_code,
                      selected_class_no, status_text))

        conn.commit()
        conn.close()
        flash("Attendance saved.", "success")
        return redirect(url_for('teacher_view_attendance', course_code=course_code))

    # GET: default date today, class_no = 1; no pre-status loaded
    conn.close()
    students_with_status = [{'Roll_No': s['Roll_No'], 'Name': s['Name'], 'status': 'P'}
                            for s in students]

    return render_template('teacher_take_attendance.html',
                           course=course,
                           students=students_with_status,
                           selected_date=selected_date,
                           selected_class_no=selected_class_no)


# ---------- TEACHER VIEW ATTENDANCE LIST ----------
@app.route('/teacher/attendance/view/<course_code>')
def teacher_view_attendance(course_code):
    if 'user' not in session:
        return redirect(url_for('teacher_login'))

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT Course_Code, Course_Name FROM courses WHERE Course_Code = ?", (course_code,))
    course = cur.fetchone()
    if not course:
        conn.close()
        flash("Course not found", "danger")
        return redirect(url_for('teacher_attendance'))

    cur.execute("""
        SELECT Date, Class_No
        FROM attendance
        WHERE Course_Code=?
        GROUP BY Date, Class_No
        ORDER BY Date, Class_No
    """, (course_code,))
    sessions = cur.fetchall()

    conn.close()
    return render_template('teacher_view_attendance.html',
                           course=course,
                           sessions=sessions)


# ---------- TEACHER EDIT SINGLE SESSION ----------
@app.route('/teacher/attendance/edit/<course_code>/<date>/<int:class_no>',
           methods=['GET', 'POST'])
def teacher_edit_attendance_session(course_code, date, class_no):
    if 'user' not in session:
        return redirect(url_for('teacher_login'))

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT Course_Code, Course_Name FROM courses WHERE Course_Code = ?", (course_code,))
    course = cur.fetchone()
    if not course:
        conn.close()
        flash("Course not found", "danger")
        return redirect(url_for('teacher_attendance'))

    # enrolled students
    cur.execute("""
        SELECT s.Roll_No, s.Name
        FROM enrollments e
        JOIN students s ON e.Roll_No = s.Roll_No
        WHERE e.Course_Code = ?
        ORDER BY s.Roll_No
    """, (course_code,))
    students = cur.fetchall()

    if request.method == 'POST':
        for s in students:
            roll = s['Roll_No']
            status = request.form.get(f'status_{roll}', 'P')

            if status == 'P':
                status_text = 'Present'
            elif status == 'A':
                status_text = 'Absent'
            else:
                status_text = 'Leave'

            cur.execute("""
                UPDATE attendance
                SET Attendance=?
                WHERE Roll_No=? AND Course_Code=? AND Date=? AND Class_No=?
            """, (status_text, roll, course_code, date, class_no))

        conn.commit()
        conn.close()
        flash("Attendance updated.", "success")
        return redirect(url_for('teacher_view_attendance', course_code=course_code))

    # GET: load current statuses
    students_with_status = []
    for s in students:
        roll = s['Roll_No']
        cur.execute("""
            SELECT Attendance
            FROM attendance
            WHERE Roll_No=? AND Course_Code=? AND Date=? AND Class_No=?
        """, (roll, course_code, date, class_no))
        r = cur.fetchone()
        status_raw = (r['Attendance'] if r else 'Present').lower()

        if status_raw.startswith('p'):
            code = 'P'
        elif status_raw.startswith('a'):
            code = 'A'
        elif status_raw.startswith('l'):
            code = 'L'
        else:
            code = 'P'

        students_with_status.append({
            'Roll_No': roll,
            'Name': s['Name'],
            'status': code
        })

    conn.close()
    return render_template('teacher_edit_attendance_session.html',
                           course=course,
                           date=date,
                           class_no=class_no,
                           students=students_with_status)



# ------------------ STUDENT INBOX ----------------
@app.route('/student_inbox')
def student_inbox():
    if 'user' not in session:
        return redirect(url_for('student_login'))

    sid = session['user']

    conn = sqlite3.connect('flake.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # --- Get student info ---
    cur.execute("""
        SELECT Roll_No, Name
        FROM students
        WHERE Roll_No = ?
    """, (sid,))
    student = cur.fetchone()

    if not student:
        conn.close()
        flash("Student not found!", "danger")
        return redirect(url_for('student_home'))

    stu_name = student['Name']
    roll_no = student['Roll_No']

    # --- Extract Department from Roll_No ---
    parts = roll_no.split('-')
    dept = None

    if len(parts) >= 2:
        p1 = parts[1]
        if '_' in p1:
            sub = p1.split('_')
            if len(sub) >= 2:
                dept = sub[1]
        else:
            if len(parts) >= 3:
                if '_' in parts[2]:
                    dept = parts[2].split('_')[0]
                else:
                    dept = ''.join([ch for ch in parts[2] if ch.isalpha()])

    # Fallback
    if not dept:
        tokens = re.split(r'[_\-]', roll_no)
        for t in tokens:
            if re.fullmatch(r'[A-Za-z]{2,}', t):
                dept = t
                break

    if not dept:
        dept = ''

    # --- Get enrolled course codes for this student ---
    cur.execute("""
        SELECT Course_Code
        FROM enrollments
        WHERE Roll_No = ?
    """, (sid,))
    
    enrolled_courses = [row['Course_Code'] for row in cur.fetchall()]

    # --- If no enrollments, show no teachers ---
    if not enrolled_courses:
        contacts = []
        conn.close()
        return render_template('inbox_S.html', user=sid, user_name=stu_name, contacts=contacts)

    # --- Query teachers by enrolled course codes AND department ---
    placeholders = ','.join(['?' for _ in enrolled_courses])
    query = f"""
        SELECT DISTINCT t.Teacher_ID, t.Name, t.Course_Code, t.Course_Name
        FROM teachers t
        WHERE t.Course_Code IN ({placeholders})
          AND t.Department = ?
    """
    
    cur.execute(query, tuple(enrolled_courses) + (dept,))
    teachers = cur.fetchall()

    # --- Build inbox contact list ---
    contacts = []
    for t in teachers:
        contacts.append({
            'id': t['Teacher_ID'],
            'name': t['Name'],
            'course_code': t['Course_Code'],
            'course': t['Course_Name'],
            'last_msg': 'No messages yet',
            'last_time': '',
            'unread': 0
        })

    conn.close()

    return render_template(
        'inbox_S.html',
        user=sid,
        user_name=stu_name,
        contacts=contacts
    )

# ------------------- Teacher Inbox ---------------------------

@app.route('/teacher_inbox')
def teacher_inbox():
    if 'user' not in session:
        return redirect(url_for('teacher_login'))

    tid = session['user']  # Teacher ID, e.g., T-M-SE-CS-1001

    conn = sqlite3.connect('flake.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # --- Get teacher info ---
    cur.execute("""
        SELECT Teacher_ID, Name, Department, Course_Code
        FROM teachers
        WHERE Teacher_ID = ?
    """, (tid,))
    teacher = cur.fetchone()

    if not teacher:
        conn.close()
        flash("Teacher not found!", "danger")
        return redirect(url_for('teacher_home'))

    teacher_name = teacher['Name']
    department = teacher['Department']
    course_code = teacher['Course_Code']

    # --- Get students enrolled in this teacher's course ---
    cur.execute("""
        SELECT DISTINCT e.Roll_No
        FROM enrollments e
        WHERE e.Course_Code = ?
    """, (course_code,))
    
    enrolled_roll_nos = [row['Roll_No'] for row in cur.fetchall()]

    # --- If no enrollments, show no students ---
    if not enrolled_roll_nos:
        contacts = []
        sections = []
        conn.close()
        return render_template('inbox_T.html', user=tid, user_name=teacher_name, contacts=contacts, sections=sections)

    # --- Filter students by department (from Roll_No) and get their details ---
    placeholders = ','.join(['?' for _ in enrolled_roll_nos])
    query = f"""
        SELECT Roll_No, Name
        FROM students
        WHERE Roll_No IN ({placeholders})
    """
    
    cur.execute(query, tuple(enrolled_roll_nos))
    students_raw = cur.fetchall()

    # --- Build inbox contact list (filter by department) ---
    contacts = []
    sections_set = set()
    
    for s in students_raw:
        roll_no = s['Roll_No']
        
        # Extract department from Roll_No (e.g., M-22_SE-A-3001 -> SE)
        parts = roll_no.split('-')
        student_dept = None
        section = None  # This will be A, B, C, etc.
        
        if len(parts) >= 2:
            p1 = parts[1]
            if '_' in p1:
                sub = p1.split('_')
                if len(sub) >= 2:
                    student_dept = sub[1]
        
        # Extract section (A, B, C) from third part
        # Roll_No format: M-22_SE-A-3001
        # parts[2] should be 'A' (the section letter)
        if len(parts) >= 3:
            # parts[2] is like 'A' or could have other chars
            section_part = parts[2]
            # Extract only alphabetic characters (should be single letter like A, B, C)
            section = ''.join([ch for ch in section_part if ch.isalpha()])
            if not section:
                section = None
        
        # Fallback for department
        if not student_dept:
            tokens = re.split(r'[_\-]', roll_no)
            for t in tokens:
                if re.fullmatch(r'[A-Za-z]{2,}', t):
                    student_dept = t
                    break
        
        # Only add if department matches
        if student_dept == department:
            if section:
                sections_set.add(section)
            
            display_name = f"{s['Name']}" + (f" (Sec {section})" if section else "")
            
            contacts.append({
                'id': roll_no,
                'name': s['Name'],  # Just name without section
                'display_name': display_name,  # Name with section for display
                'roll_no': roll_no,
                'section': section if section else '',
                'last_msg': 'No messages yet',
                'last_time': '',
                'unread': 0
            })

    conn.close()
    
    # Sort sections alphabetically
    sections = sorted(list(sections_set))

    return render_template(
        'inbox_T.html',
        user=tid,
        user_name=teacher_name,
        contacts=contacts,
        sections=sections
    )

# ------------------- Admin Inbox ---------------------------

@app.route('/inbox_A')
def inbox_A():
    if 'user' not in session:
        return redirect(url_for('admin_login'))

    aid = session['user']  # Admin ID

    conn = sqlite3.connect('flake.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # --- Get admin info ---
    cur.execute("""
        SELECT admin_id FROM admins WHERE admin_id = ?
    """, (aid,))
    admin = cur.fetchone()

    if not admin:
        conn.close()
        flash("Admin not found!", "danger")
        return redirect(url_for('admin_dashboard'))

    # --- Get ALL students ---
    cur.execute("""
        SELECT Roll_No, Name FROM students ORDER BY Name
    """)
    students_raw = cur.fetchall()

    # --- Get ALL teachers ---
    cur.execute("""
        SELECT Teacher_ID, Name, Department, Course_Code FROM teachers ORDER BY Name
    """)
    teachers_raw = cur.fetchall()

    conn.close()

    # --- Build contacts list ---
    contacts = []

    # Add all students
    for s in students_raw:
        roll_no = s['Roll_No']
        
        # Extract section from Roll_No
        parts = roll_no.split('-')
        section = ''
        department = ''
        
        if len(parts) >= 2:
            p1 = parts[1]
            if '_' in p1:
                sub = p1.split('_')
                if len(sub) >= 2:
                    department = sub[1]
        
        if len(parts) >= 3:
            section_part = parts[2]
            section = ''.join([ch for ch in section_part if ch.isalpha()])
        
        display_name = f"{s['Name']}" + (f" (Sec {section})" if section else "")
        
        contacts.append({
            'id': roll_no,
            'name': s['Name'],
            'display_name': display_name,
            'roll_no': roll_no,
            'type': 'student',
            'department': department,
            'section': section,
            'last_msg': 'No messages yet',
            'last_time': '',
            'unread': 0
        })

    # Add all teachers
    for t in teachers_raw:
        teacher_id = t['Teacher_ID']
        department = t['Department']
        course_code = t['Course_Code']
        
        display_name = f"{t['Name']} (Teacher - {department})"
        
        contacts.append({
            'id': teacher_id,
            'name': t['Name'],
            'display_name': display_name,
            'roll_no': teacher_id,
            'type': 'teacher',
            'department': department,
            'section': '',
            'course_code': course_code,
            'last_msg': 'No messages yet',
            'last_time': '',
            'unread': 0
        })

    # Get unique departments and sections for filters
    departments = sorted(list(set([c['department'] for c in contacts if c['department']])))
    sections = sorted(list(set([c['section'] for c in contacts if c['section']])))

    return render_template(
        'inbox_A.html',
        user=aid,
        user_name='Admin',
        contacts=contacts,
        departments=departments,
        sections=sections
    )


# -------------------- TEACHER TIMETABLE --------------------
@app.route('/teacher_timetable')
def teacher_timetable():
    """Display teacher's class schedule - Only for logged-in teachers"""
    if 'user' not in session:
        return redirect(url_for('teacher_login'))
    
    tid = session['user']
    
    try:
        conn = sqlite3.connect('flake.db')
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # Get teacher information
        cur.execute("""
            SELECT Teacher_ID, Name, Gender, DOB, CNIC, Email, Mobile_No,
                   Current_Address, Permanent_Address, Home_Phone, Postal_Code,
                   Department, Course_Code, Course_Name
            FROM teachers
            WHERE Teacher_ID = ?
        """, (tid,))
        teacher_row = cur.fetchone()
        
        if not teacher_row:
            conn.close()
            flash("Teacher not found", "danger")
            return redirect(url_for('teacher_home'))
        
        # Convert to dictionary
        teacher = dict(teacher_row)
        
        # Get timetable for this teacher
        cur.execute("""
            SELECT 
                t.Day,
                t.Start_Time,
                t.End_Time,
                t.Room,
                t.Section,
                t.Class_Type,
                t.Course_Code,
                c.Course_Name,
                c.Credit_Hr
            FROM timetable t
            JOIN courses c ON t.Course_Code = c.Course_Code
            WHERE t.Teacher_ID = ?
            ORDER BY 
                CASE t.Day
                    WHEN 'Monday' THEN 1
                    WHEN 'Tuesday' THEN 2
                    WHEN 'Wednesday' THEN 3
                    WHEN 'Thursday' THEN 4
                    WHEN 'Friday' THEN 5
                    WHEN 'Saturday' THEN 6
                END,
                t.Start_Time
        """, (tid,))
        
        schedule_rows = cur.fetchall()
        
        # Get student enrollment count
        cur.execute("""
            SELECT COUNT(DISTINCT Roll_No) as count
            FROM enrollments
            WHERE Course_Code = ?
        """, (teacher['Course_Code'],))
        
        enrollment_result = cur.fetchone()
        student_count = enrollment_result['count'] if enrollment_result else 0
        
        conn.close()
        
        # Organize schedule by day
        schedule = {}
        for row in schedule_rows:
            day = row['Day']
            if day not in schedule:
                schedule[day] = []
            
            schedule[day].append({
                'start_time': row['Start_Time'],
                'end_time': row['End_Time'],
                'course_code': row['Course_Code'],
                'course_name': row['Course_Name'],
                'room': row['Room'],
                'section': row['Section'],
                'type': row['Class_Type'],
                'credits': row['Credit_Hr'],
                'students': student_count
            })


        
        # Calculate statistics
        total_classes = len(schedule_rows)
        
        # Calculate total hours
        total_hours = 0
        for classes in schedule.values():
            for cls in classes:
                start_parts = cls['start_time'].split(':')
                end_parts = cls['end_time'].split(':')
                start_minutes = int(start_parts[0]) * 60 + int(start_parts[1])
                end_minutes = int(end_parts[0]) * 60 + int(end_parts[1])
                hours = (end_minutes - start_minutes) / 60
                total_hours += hours
        
        statistics = {
            'total_classes': total_classes,
            'total_hours': round(total_hours, 1),
            'total_students': student_count
        }
        
        return render_template(
            'teacher_timetable.html',
            teacher=teacher,
            schedule=schedule,
            statistics=statistics,
            user=tid,
            user_name=teacher['Name']
        )
    
    except Exception as e:
        print(f"Error loading teacher timetable: {e}")
        import traceback
        traceback.print_exc()
        flash("Error loading timetable", "danger")
        return redirect(url_for('teacher_home'))
    

    # ADD THIS TEMPORARILY - Put it right after your teacher_timetable route
@app.route('/test_timetable')
def test_timetable():
    return "Timetable route is working!"

# ------------------- Course Registration ---------------------
# Add these utility functions and routes to your app.py file

def extract_student_info(roll_no):
    """
    Extract batch, degree, section from Roll_No
    Example Roll_No formats:
    - FA23-SE-A-1234 (Format 1)
    - M-22_SE-A-3001 (Format 2)
    
    Returns dict with: batch, degree_code, degree_name, section
    """
    try:
        degree_map = {
            'SE': 'Software Engineering',
            'AI': 'Artificial Intelligence',
            'DS': 'Data Science',
            'CY': 'Cyber Security'
        }
        
        parts = roll_no.split('-')
        batch = None
        degree_code = None
        section = None
        
        # Handle Format 1: FA23-SE-A-1234
        if len(parts) >= 3 and len(parts[0]) >= 2:
            prefix = parts[0]
            batch = ''.join([ch for ch in prefix if ch.isdigit()])
            if len(parts) > 1 and parts[1] in degree_map:
                degree_code = parts[1]
            if len(parts) > 2:
                section = parts[2]
        
        # Handle Format 2: M-22_SE-A-3001
        elif len(parts) >= 2 and '_' in parts[1]:
            sub_parts = parts[1].split('_')
            if len(sub_parts) >= 1:
                batch = sub_parts[0]
            if len(sub_parts) >= 2 and sub_parts[1] in degree_map:
                degree_code = sub_parts[1]
            if len(parts) > 2:
                section = parts[2]
        
        # Fallback
        if not batch or not degree_code:
            tokens = roll_no.replace('_', '-').split('-')
            for token in tokens:
                if not batch and len(token) >= 2 and token[-2:].isdigit():
                    batch = token[-2:]
                if not degree_code:
                    alpha_only = ''.join([ch for ch in token if ch.isalpha()])
                    if len(alpha_only) == 2 and alpha_only in degree_map:
                        degree_code = alpha_only
        
        degree_name = degree_map.get(degree_code, degree_code if degree_code else 'N/A')
        
        return {
            'batch': batch or 'N/A',
            'degree_code': degree_code or 'N/A',
            'degree_name': degree_name,
            'section': section or 'N/A'
        }
    
    except Exception as e:
        print(f"Error extracting student info: {e}")
        return {'batch': 'N/A', 'degree_code': 'N/A', 'degree_name': 'N/A', 'section': 'N/A'}


def batch_to_semester(batch):
    """
    Convert batch year to current semester (Based on app.py logic)
    
    Mapping (for 2025):
    - 2022 batch (22) -> Semester 7
    - 2023 batch (23) -> Semester 5
    - 2024 batch (24) -> Semester 3
    - 2025 batch (25) -> Semester 1
    """
    batch_to_sem = {
        '22': 7,
        '23': 5,
        '24': 3,
        '25': 1
    }
    return batch_to_sem.get(str(batch), None)


def semester_to_course_digit(semester):
    """
    Convert semester number to course code digit
    
    Special rule (from app.py student_inbox logic):
    - Semester 1 is encoded as '0' in Course_Code
    - Semester 3 is encoded as '3' (or '30', '31', etc.)
    - Semester 5 is encoded as '5' (or '50', '51', etc.)
    - Semester 7 is encoded as '7' (or '70', '71', etc.)
    
    Returns the digit that appears after '-' in course code
    """
    if semester == 1:
        return '0'
    else:
        return str(semester)


# -------------------- COURSE REGISTRATION --------------------
@app.route('/Course_Registration')
def course_registration():
    """
    Display course registration page with intelligent course offering:
    1. Show ALL courses for current semester (even if prerequisites not met)
    2. If prerequisite not met, also offer the prerequisite course for retake
    3. Include failed courses that need to be retaken
    """
    if 'user' not in session:
        return redirect(url_for('student_login'))
    
    sid = session['user']
    
    try:
        conn = sqlite3.connect('flake.db')
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # Get student info
        cur.execute("""
            SELECT Roll_No, Name FROM students WHERE Roll_No = ?
        """, (sid,))
        student_row = cur.fetchone()
        
        if not student_row:
            conn.close()
            flash("Student not found", "danger")
            return redirect(url_for('student_home'))
        
        # Extract batch and degree from Roll_No
        roll_no = student_row['Roll_No']
        roll_parts = roll_no.split('-')
        
        # Extract batch (e.g., from M-22_SE-A-3001, extract '22')
        batch = None
        if len(roll_parts) >= 2:
            p1 = roll_parts[1]
            if '_' in p1:
                batch = p1.split('_')[0]
            else:
                batch = p1
        
        # Map batch to current semester
        batch_to_sem = {
            '22': 7,
            '23': 5,
            '24': 3,
            '25': 1
        }
        current_semester = batch_to_sem.get(batch, None)
        
        if current_semester is None:
            conn.close()
            flash("Unable to determine your current semester", "danger")
            return redirect(url_for('student_home'))
        
        # Convert semester to course code digit
        # Semester 1 → '0', all others → their number
        if current_semester == 1:
            code_digit = '0'
        else:
            code_digit = str(current_semester)
        
        # DEBUG: Print to console
        print(f"\n{'='*60}")
        print(f"🔍 DEBUG - Student: {sid}, Batch: {batch}, Semester: {current_semester}, Code Digit: {code_digit}")
        print(f"{'='*60}")
        
        # Get all courses for this semester
        cur.execute("""
            SELECT Course_Code, Course_Name, Credit_Hr, Prerequisite
            FROM courses
            WHERE substr(Course_Code, instr(Course_Code, '-') + 1, 1) = ?
            ORDER BY Course_Code
        """, (code_digit,))
        
        current_sem_courses_raw = cur.fetchall()
        
        print(f"\n📚 Found {len(current_sem_courses_raw)} courses for semester {current_semester}:")
        for c in current_sem_courses_raw:
            print(f"  - {c['Course_Code']}: {c['Course_Name']} (Prereq: {c['Prerequisite'] or 'None'})")
        
        # Get enrolled courses for this student
        cur.execute("""
            SELECT Course_Code FROM enrollments WHERE Roll_No = ?
        """, (sid,))
        enrolled = [row['Course_Code'] for row in cur.fetchall()]
        
        # Get passed courses (prerequisites met)
        cur.execute("""
            SELECT Course_Code FROM passed_courses WHERE Roll_No = ?
        """, (sid,))
        passed = [row['Course_Code'] for row in cur.fetchall()]
        
        print(f"\n✅ Passed courses: {passed}")
        print(f"📝 Enrolled courses: {enrolled}")
        
        # Build the courses list - SHOW ALL COURSES
        courses_to_offer = []
        prerequisite_courses_to_retake = set()
        
        for c in current_sem_courses_raw:
            code = c['Course_Code']
            prerequisite = c['Prerequisite']
            
            # Check if student has passed the prerequisite
            prerequisite_met = (not prerequisite or prerequisite in passed)
            
            # Extract semester info
            code_parts = code.split('-')
            sem_digit = code_parts[1][0] if len(code_parts) > 1 else '0'
            
            if sem_digit == '0':
                semester = 1
            else:
                semester = int(sem_digit) if sem_digit.isdigit() else 1
            
            department = code_parts[0] if len(code_parts) > 0 else 'CS'
            
            # ADD ALL CURRENT SEMESTER COURSES (show all, regardless of prerequisites)
            courses_to_offer.append({
                'code': code,
                'name': c['Course_Name'],
                'credits': c['Credit_Hr'],
                'semester': semester,
                'prerequisite': prerequisite,
                'department': department,
                'type': 'current'  # Current semester course
            })
            
            # Track prerequisites that need retaking
            if not prerequisite_met and prerequisite:
                print(f"⚠️  {code} requires {prerequisite} which is not passed - adding {prerequisite} to retake list")
                prerequisite_courses_to_retake.add(prerequisite)
        
        # Add prerequisite courses that need to be retaken
        if prerequisite_courses_to_retake:
            print(f"\n🔄 Fetching {len(prerequisite_courses_to_retake)} prerequisite course(s) for retake:")
            for prereq in prerequisite_courses_to_retake:
                print(f"  - {prereq}")
            
            placeholders = ','.join(['?' for _ in prerequisite_courses_to_retake])
            cur.execute(f"""
                SELECT Course_Code, Course_Name, Credit_Hr, Prerequisite
                FROM courses
                WHERE Course_Code IN ({placeholders})
            """, tuple(prerequisite_courses_to_retake))
            
            prereq_courses_raw = cur.fetchall()
            
            print(f"\n📋 Found {len(prereq_courses_raw)} prerequisite course(s) in database:")
            
            for c in prereq_courses_raw:
                code = c['Course_Code']
                code_parts = code.split('-')
                sem_digit = code_parts[1][0] if len(code_parts) > 1 else '0'
                
                if sem_digit == '0':
                    semester = 1
                else:
                    semester = int(sem_digit) if sem_digit.isdigit() else 1
                
                department = code_parts[0] if len(code_parts) > 0 else 'CS'
                
                print(f"  ✓ Adding {code}: {c['Course_Name']} as RETAKE course")
                
                courses_to_offer.append({
                    'code': code,
                    'name': c['Course_Name'],
                    'credits': c['Credit_Hr'],
                    'semester': semester,
                    'prerequisite': c['Prerequisite'],
                    'department': department,
                    'type': 'retake'  # Prerequisite course to retake
                })
        
        conn.close()
        
        # Sort: current semester courses first, then retake courses
        courses_sorted = sorted(courses_to_offer, key=lambda x: (x['type'] != 'current', x['code']))
        
        print(f"\n🎯 FINAL OFFERING - Total courses: {len(courses_sorted)}")
        print(f"  📅 Current semester courses: {len([c for c in courses_sorted if c['type'] == 'current'])}")
        print(f"  ⚠️  Retake courses: {len([c for c in courses_sorted if c['type'] == 'retake'])}")
        print(f"\nCourses being offered:")
        for c in courses_sorted:
            badge = "📅 CURRENT" if c['type'] == 'current' else "⚠️  RETAKE"
            print(f"  {badge} | {c['code']}: {c['name']}")
        print(f"{'='*60}\n")
        
        # Extract degree info for template
        degree_code = None
        if len(roll_parts) >= 2:
            p1 = roll_parts[1]
            if '_' in p1:
                degree_code = p1.split('_')[1] if len(p1.split('_')) > 1 else None
        
        student_info = {
            'batch': batch,
            'degree_code': degree_code
        }
        
        return render_template(
            'course_registration.html',
            user=sid,
            user_name=student_row['Name'],
            student_info=student_info,
            current_semester=current_semester,
            courses=courses_sorted,
            enrolled_courses=enrolled,
            passed_courses=passed
        )
    
    except Exception as e:
        print(f"❌ Error loading course registration: {e}")
        import traceback
        traceback.print_exc()
        flash("Error loading course registration", "danger")
        return redirect(url_for('student_home'))


@app.route('/api/register-courses', methods=['POST'])
def register_courses():
    """Register student for selected courses"""
    if 'user' not in session:
        return {'success': False, 'error': 'Not logged in'}, 401
    
    sid = session['user']
    data = request.get_json()
    courses = data.get('courses', [])
    
    if not courses:
        return {'success': False, 'error': 'No courses selected'}, 400
    
    try:
        conn = sqlite3.connect('flake.db')
        cur = conn.cursor()
        
        # Delete existing enrollments for this student
        cur.execute("DELETE FROM enrollments WHERE Roll_No = ?", (sid,))
        
        # Insert new enrollments
        for course_code in courses:
            # Validate course exists
            cur.execute("SELECT Course_Code FROM courses WHERE Course_Code = ?", (course_code,))
            if not cur.fetchone():
                conn.close()
                return {'success': False, 'error': f'Invalid course code: {course_code}'}, 400
            
            cur.execute("INSERT INTO enrollments VALUES (?, ?)", (sid, course_code))
        
        conn.commit()
        conn.close()
        
        return {
            'success': True,
            'message': f'Successfully registered for {len(courses)} course(s)'
        }
    
    except Exception as e:
        print(f"Error registering courses: {e}")
        return {'success': False, 'error': 'Registration failed'}, 500
    


from datetime import datetime

# ============ STUDENT FEEDBACK ROUTES ============

@app.route('/student/feedback', methods=['GET'])
def student_feedback_form():
    if 'user' not in session:
        flash('Please login as student', 'error')
        return redirect(url_for('student_login'))
    
    roll_no = session['user']

    conn = sqlite3.connect('flake.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get student info
    cur.execute("""
        SELECT Roll_No, Name
        FROM students
        WHERE Roll_No = ?
    """, (roll_no,))
    student = cur.fetchone()

    if not student:
        conn.close()
        flash("Student not found!", "danger")
        return redirect(url_for('student_home'))


        # ✅ Get enrolled courses without duplicates
    cur.execute("""
        SELECT DISTINCT 
               e.Course_Code, 
               c.Course_Name, 
               c.Credit_Hr,
               t.Teacher_ID, 
               t.Name AS Teacher_Name,
               CASE 
                    WHEN f.id IS NOT NULL THEN 'Feedback Submitted'
                    ELSE 'Submit Feedback'
               END AS Status
        FROM enrollments e
        JOIN courses c ON e.Course_Code = c.Course_Code
        LEFT JOIN teacher_courses tc ON c.Course_Code = tc.Course_Code
        LEFT JOIN teachers t ON tc.Teacher_ID = t.Teacher_ID
        LEFT JOIN feedback f ON e.Roll_No = f.Roll_No AND e.Course_Code = f.Course_Code
        WHERE e.Roll_No = ?
        GROUP BY e.Course_Code
    """, (roll_no,))

    
    courses = cur.fetchall()
    conn.close()

    return render_template('student_feedback_list.html', courses=courses)




@app.route('/student/feedback/form/<course_code>', methods=['GET'])
def student_feedback_form_detail(course_code):
    if 'user' not in session:
        flash('Please login as student', 'error')
        return redirect(url_for('student_login'))
    
    roll_no = session['user']
    conn = get_db()

    # Prevent duplicate submission
    existing = conn.execute(
        'SELECT id FROM feedback WHERE Roll_No = ? AND Course_Code = ?',
        (roll_no, course_code)
    ).fetchone()

    if existing:
        flash('You have already submitted feedback for this course', 'warning')
        conn.close()
        return redirect(url_for('student_feedback_form'))

    # ✅ Correct query to fetch teacher of this course
    course_info = conn.execute("""
        SELECT c.Course_Code, c.Course_Name,
               t.Teacher_ID, t.Name AS Teacher_Name
        FROM enrollments e
        JOIN courses c ON e.Course_Code = c.Course_Code
        LEFT JOIN teacher_courses tc ON c.Course_Code = tc.Course_Code
        LEFT JOIN teachers t ON tc.Teacher_ID = t.Teacher_ID
        WHERE e.Roll_No = ? AND e.Course_Code = ?
    """, (roll_no, course_code)).fetchone()

    conn.close()

    if not course_info:
        flash("Course or teacher not found!", "danger")
        return redirect(url_for('student_feedback_form'))

    return render_template('student_feedback_form.html', course=course_info)



@app.route('/student/feedback/submit', methods=['POST'])
def submit_feedback():
    if 'user' not in session:
        return redirect(url_for('student_login'))
    
    roll_no = session['user']
    course_code = request.form.get('course_code')
    teacher_id = request.form.get('teacher_id')

    if not course_code or not teacher_id:
        flash("Invalid submission. Missing course or teacher information.", "danger")
        return redirect(url_for('student_feedback_form'))

    # Ratings (1-5)
    teaching_quality = request.form.get('teaching_quality')
    course_content = request.form.get('course_content')
    difficulty_level = request.form.get('difficulty_level')
    teacher_rating = request.form.get('teacher_rating')

    # MCQ fields
    classroom_env = request.form.get('classroom_environment')
    assessment = request.form.get('assessment_fairness')
    resources = request.form.get('learning_resources')
    organization = request.form.get('course_organization')

    # Suggestions
    suggestions = request.form.get('suggestions')

    conn = get_db()

    # Prevent duplicate
    existing = conn.execute(
        'SELECT id FROM feedback WHERE Roll_No = ? AND Course_Code = ?',
        (roll_no, course_code)
    ).fetchone()

    if existing:
        flash('You have already submitted feedback for this course', 'warning')
        conn.close()
        return redirect(url_for('student_feedback_form'))

    conn.execute("""
        INSERT INTO feedback (
            Roll_No, Course_Code, Teacher_ID,
            teaching_quality, course_content, difficulty_level, teacher_rating,
            classroom_environment, assessment_fairness, learning_resources,
            course_organization, suggestions, submitted_date
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        roll_no, course_code, teacher_id,
        teaching_quality, course_content, difficulty_level, teacher_rating,
        classroom_env, assessment, resources, organization,
        suggestions, datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ))

    conn.commit()
    conn.close()

    flash('Feedback submitted successfully!', 'success')
    return redirect(url_for('student_feedback_form'))



# ============ TEACHER FEEDBACK ROUTES ============

@app.route('/teacher/feedback', methods=['GET'])
def teacher_feedback_view():
    """Teachers view feedback for their courses only"""
    if 'user' not in session:
        flash('Please login as teacher', 'error')
        return redirect(url_for('teacher_login'))
    
    teacher_id = session['Teacher_ID']
    conn = get_db()
    
    # Get teacher's courses
    courses = conn.execute('''
        SELECT DISTINCT tc.Course_Code, c.Course_Name
        FROM teacher_courses tc
        JOIN courses c ON tc.Course_Code = c.Course_Code
        WHERE tc.Teacher_ID = ?
    ''', (teacher_id,)).fetchall()
    
    # Get feedback for selected course or all courses
    selected_course = request.args.get('course_code', 'all')
    
    if selected_course == 'all':
        feedbacks = conn.execute('''
            SELECT f.*, c.Course_Name
            FROM feedback f
            JOIN courses c ON f.Course_Code = c.Course_Code
            WHERE f.Teacher_ID = ?
            ORDER BY f.submitted_date DESC
        ''', (teacher_id,)).fetchall()
    else:
        feedbacks = conn.execute('''
            SELECT f.*, c.Course_Name
            FROM feedback f
            JOIN courses c ON f.Course_Code = c.Course_Code
            WHERE f.Teacher_ID = ? AND f.Course_Code = ?
            ORDER BY f.submitted_date DESC
        ''', (teacher_id, selected_course)).fetchall()
    
    # Calculate statistics
    if selected_course == 'all':
        stats = conn.execute('''
            SELECT 
                COUNT(*) as total_feedback,
                AVG(teacher_rating) as avg_teacher_rating,
                AVG(teaching_quality) as avg_teaching_quality,
                AVG(course_content) as avg_course_content
            FROM feedback
            WHERE Teacher_ID = ?
        ''', (teacher_id,)).fetchone()
    else:
        stats = conn.execute('''
            SELECT 
                COUNT(*) as total_feedback,
                AVG(teacher_rating) as avg_teacher_rating,
                AVG(teaching_quality) as avg_teaching_quality,
                AVG(course_content) as avg_course_content
            FROM feedback
            WHERE Teacher_ID = ? AND Course_Code = ?
        ''', (teacher_id, selected_course)).fetchone()
    
    conn.close()
    return render_template('teacher_feedback_view.html', 
                         courses=courses, 
                         feedbacks=feedbacks, 
                         selected_course=selected_course,
                         stats=stats)

# ============ ADMIN FEEDBACK ROUTES ============

@app.route('/admin/feedback', methods=['GET'])
def admin_feedback_view():
    """Admin views all feedback with teacher/course filter"""
    if 'user' not in session:
        flash('Please login as admin', 'error')
        return redirect(url_for('admin_login'))
    
    conn = get_db()
    
    # Get all teachers with their courses
    teacher_courses = conn.execute('''
        SELECT DISTINCT t.Teacher_ID, t.Name as Teacher_Name, 
               tc.Course_Code, c.Course_Name
        FROM teachers t
        JOIN teacher_courses tc ON t.Teacher_ID = tc.Teacher_ID
        JOIN courses c ON tc.Course_Code = c.Course_Code
        ORDER BY t.Name, c.Course_Code
    ''').fetchall()
    
    # Filter logic
    selected_teacher = request.args.get('teacher_id', 'all')
    selected_course = request.args.get('course_code', 'all')
    
    query = '''
        SELECT f.*, c.Course_Name, t.Name as Teacher_Name
        FROM feedback f
        JOIN courses c ON f.Course_Code = c.Course_Code
        JOIN teachers t ON f.Teacher_ID = t.Teacher_ID
        WHERE 1=1
    '''
    params = []
    
    if selected_teacher != 'all':
        query += ' AND f.Teacher_ID = ?'
        params.append(selected_teacher)
    
    if selected_course != 'all':
        query += ' AND f.Course_Code = ?'
        params.append(selected_course)
    
    query += ' ORDER BY f.submitted_date DESC'
    
    feedbacks = conn.execute(query, params).fetchall()
    
    # Overall statistics
    stats_query = 'SELECT COUNT(*) as total_feedback, AVG(teacher_rating) as avg_teacher_rating, AVG(teaching_quality) as avg_teaching_quality, COUNT(DISTINCT Teacher_ID) as teachers_count, COUNT(DISTINCT Course_Code) as courses_count FROM feedback WHERE 1=1'
    stats_params = []
    
    if selected_teacher != 'all':
        stats_query += ' AND Teacher_ID = ?'
        stats_params.append(selected_teacher)
    
    if selected_course != 'all':
        stats_query += ' AND Course_Code = ?'
        stats_params.append(selected_course)
    
    stats = conn.execute(stats_query, stats_params).fetchone()
    
    conn.close()
    return render_template('admin_feedback_view.html',
                         teacher_courses=teacher_courses,
                         feedbacks=feedbacks,
                         selected_teacher=selected_teacher,
                         selected_course=selected_course,
                         stats=stats)

# ========== MESSAGE HISTORY ==========
@app.route('/messages/<receiver_id>', methods=['GET', 'POST'])
def messages(receiver_id):
    if 'user' not in session:
        return jsonify([])

    sender_id = session['user']
    conn = sqlite3.connect('flake.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if request.method == 'GET':
        cur.execute("""
            SELECT sender_id, receiver_id, message, timestamp
            FROM messages
            WHERE (sender_id = ? AND receiver_id = ?)
               OR (sender_id = ? AND receiver_id = ?)
            ORDER BY timestamp ASC
        """, (sender_id, receiver_id, receiver_id, sender_id))
        msgs = [dict(row) for row in cur.fetchall()]
        conn.close()
        return jsonify(msgs)

    elif request.method == 'POST':
        data = request.get_json()
        message = data.get('text', '').strip()
        if not message:
            return jsonify({'status': 'error', 'message': 'Empty message'}), 400
        sender_type = session.get('user_type', 'student')
        receiver_type = data.get('receiver_type', 'teacher')

        cur.execute("""
            INSERT INTO messages (sender_type, sender_id, receiver_type, receiver_id, message, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (sender_type, sender_id, receiver_type, receiver_id, message, datetime.utcnow()))
        conn.commit()
        conn.close()
        return jsonify({'status': 'ok'})


# ========== SOCKET.IO EVENTS ==========

@socketio.on('join')
def on_join(data):
    user_id = data['user_id']
    join_room(user_id)
    print(f"{user_id} joined room")


@socketio.on('private_message')
def handle_send_message(data):
    sender_id = session.get('user')
    sender_type = data.get('user_type')
    receiver_id = data.get('receiver_id')
    receiver_type = data.get('receiver_type')
    message = data.get('message', '').strip()

    if not message:
        return

    conn = sqlite3.connect('flake.db')
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO messages (sender_type, sender_id, receiver_type, receiver_id, message, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (sender_type, sender_id, receiver_type, receiver_id, message, datetime.utcnow()))
    conn.commit()
    conn.close()

    msg_data = {
        'sender_id': sender_id,
        'receiver_id': receiver_id,
        'message': message,
        'timestamp': datetime.utcnow().isoformat()
    }

    emit('receive_message', msg_data, to=receiver_id)
    emit('receive_message', msg_data, to=sender_id)  # echo to sender too



@app.route('/transcript')
def transcript():
    # --- Check if student is logged in ---
    if 'user' not in session:
        flash("Please login first", "warning")
        return redirect(url_for('student_login'))

    roll_no = session['user']  # use same session variable as feedback/login
    conn = get_db()

    # --- Get student info ---
    student = conn.execute(
        "SELECT Roll_No, Name FROM students WHERE Roll_No = ?",
        (roll_no,)
    ).fetchone()

    if not student:
        flash("Student record not found!", "danger")
        return redirect(url_for('student_home'))

    # --- Fetch passed courses for this student ---
    rows = conn.execute("""
        SELECT pc.Course_Code, c.Course_Name, c.Credit_Hr, pc.Grade
        FROM passed_courses pc
        JOIN courses c ON pc.Course_Code = c.Course_Code
        WHERE pc.Roll_No = ?
        ORDER BY pc.Course_Code
    """, (roll_no,)).fetchall()

    # --- Map course codes to semesters ---
    # Example: use course code to determine semester (simple heuristic)
    # e.g., Course_Code 'CS101' -> 'Semester 1', 'CS201' -> 'Semester 2', etc.
    def course_to_semester(code):
        match = re.search(r'(\d+)', code)
        if match:
            num_str = match.group(1)
            if num_str and num_str[0].isdigit():  # Safety check
                sem = int(num_str[0])  # Extract first digit as semester
                return f"Semester {sem}"
        return "Unknown"

    semesters_dict = {}
    for r in rows:
        sem = course_to_semester(r['Course_Code'])
        if sem not in semesters_dict:
            semesters_dict[sem] = []
        # Map grade to points
        GRADE_POINTS = {
            'A+':4.00, 'A':4.00, 'A-':3.67, 'B+':3.33, 'B':3.00, 'B-':2.67,
            'C+':2.33, 'C':2.00, 'C-':1.67, 'D':1.00, 'F':0.00,
            'S':0.00, 'NC':0.00
        }
        points = GRADE_POINTS.get(r['Grade'], 0.0)
        semesters_dict[sem].append({
            'Course_Code': r['Course_Code'],
            'Course_Name': r['Course_Name'],
            'Section': '',        # optional, blank
            'CrdHrs': r['Credit_Hr'],
            'Grade': r['Grade'],
            'Points': points,
            'Type': 'Core',
            'Remarks': ''
        })

    # --- Compute SGPA per semester and total CGPA ---
    semesters = []
    total_weighted = 0
    total_credits = 0
    for sem_name, courses in semesters_dict.items():
        sem_credits = sum(c['CrdHrs'] for c in courses)
        sem_weighted = sum(c['CrdHrs']*c['Points'] for c in courses)
        sgpa = round((sem_weighted/sem_credits if sem_credits else 0.0) + 1e-9, 2)
        semesters.append({
            'term': sem_name,
            'courses': courses,
            'sgpa': sgpa,
            'total_credits': sem_credits
        })
        total_weighted += sem_weighted
        total_credits += sem_credits

    cgpa = round((total_weighted / total_credits if total_credits else 0.0) + 1e-9, 2)

    conn.close()

    return render_template(
        'transcript.html',
        roll=roll_no,
        student=student,
        semesters=semesters,
        cgpa=cgpa
    )


# ============ TEACHER MARKS MANAGEMENT ============

DB = 'flake.db'

CATEGORIES = ["Assignment", "Quiz", "Sessional-I", "Sessional-II", "Project", "Final Exam"]

def get_db_conn():
    return sqlite3.connect(DB)

@app.route('/teacher/marks')
def teacher_marks():
    if 'user' not in session:
        flash('Please login as teacher', 'error')
        return redirect(url_for('teacher_login'))

    teacher_id = session.get('user')
    conn = get_db_conn()
    cur = conn.cursor()

    # Fetch teacher courses
    cur.execute('SELECT Course_Code FROM teacher_courses WHERE Teacher_ID=?', (teacher_id,))
    courses = [r[0] for r in cur.fetchall()]

    # Fetch mark items for these courses
    if courses:
        placeholder = ','.join('?'*len(courses))
        cur.execute(f'''
            SELECT id, Course_Code, Category, Item_No, Title, Total, Teacher_ID, Created_Date
            FROM mark_items
            WHERE Course_Code IN ({placeholder})
            ORDER BY Course_Code, Category, Item_No
        ''', courses)
        items = cur.fetchall()
    else:
        items = []

    conn.close()
    return render_template('teacher_marks.html', items=items)

@app.route('/teacher/marks/create', methods=['GET','POST'])
def teacher_create_mark_item():
    if 'user' not in session:
        flash('Please login as teacher', 'error')
        return redirect(url_for('teacher_login'))

    teacher_id = session.get('user')
    conn = get_db_conn()
    cur = conn.cursor()

    # teacher courses for the dropdown
    cur.execute('SELECT Course_Code FROM teacher_courses WHERE Teacher_ID=?', (teacher_id,))
    course_rows = cur.fetchall()
    courses = [r[0] for r in course_rows]

    if request.method == 'POST':
        course = request.form['course']
        category = request.form['category']
        item_no = int(request.form.get('item_no', 1))
        title = request.form.get('title') or f"{category} {item_no}"
        total = int(request.form['total'])

        cur.execute('''
            INSERT INTO mark_items (Course_Code, Category, Item_No, Title, Total, Teacher_ID)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (course, category, item_no, title, total, teacher_id))
        conn.commit()
        conn.close()
        flash('Mark item created', 'success')
        return redirect(url_for('teacher_marks'))

    conn.close()
    return render_template('teacher_create_mark_item.html', courses=courses, categories=CATEGORIES)

@app.route('/teacher/marks/add/<int:item_id>', methods=['GET','POST'])
def teacher_add_marks(item_id):
    if 'user' not in session:
        flash('Please login as teacher', 'error')
        return redirect(url_for('teacher_login'))

    conn = get_db_conn()
    cur = conn.cursor()

    # fetch item metadata
    cur.execute('SELECT id, Course_Code, Category, Item_No, Title, Total FROM mark_items WHERE id=?', (item_id,))
    item = cur.fetchone()
    if not item:
        flash('Mark item not found', 'error')
        return redirect(url_for('teacher_marks'))

    course_code = item[1]

    # fetch students enrolled in the course
    cur.execute('''
        SELECT s.Roll_No, s.Name
        FROM enrollments e
        JOIN students s ON e.Roll_No = s.Roll_No
        WHERE e.Course_Code = ?
        ORDER BY s.Roll_No
    ''', (course_code,))
    students = cur.fetchall()

    if request.method == 'POST':
        # expected inputs named obtained_<roll_no>
        for roll, _name in students:
            key = f'obtained_{roll}'
            val = request.form.get(key, '').strip()
            obtained = int(val) if val != '' else None

            # insert or update student_marks
            cur.execute('''
                SELECT id FROM student_marks WHERE mark_item_id=? AND Roll_No=?
            ''', (item_id, roll))
            existing = cur.fetchone()
            if existing:
                cur.execute('UPDATE student_marks SET Obtained=? WHERE id=?', (obtained, existing[0]))
            else:
                cur.execute('INSERT INTO student_marks (mark_item_id, Roll_No, Obtained) VALUES (?, ?, ?)',
                            (item_id, roll, obtained))
        conn.commit()
        conn.close()
        flash('Marks saved for item', 'success')
        return redirect(url_for('teacher_marks'))

    # load existing marks
    cur.execute('SELECT Roll_No, Obtained FROM student_marks WHERE mark_item_id=?', (item_id,))
    existing_marks = {r[0]: r[1] for r in cur.fetchall()}

    conn.close()
    return render_template('teacher_add_marks.html', item=item, students=students, existing_marks=existing_marks)

@app.route('/teacher/marks/edit/<int:item_id>', methods=['GET','POST'])
def teacher_edit_mark_item(item_id):
    if 'user' not in session:
        flash('Please login as teacher', 'error')
        return redirect(url_for('login'))

    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute('SELECT id, Course_Code, Category, Item_No, Title, Total FROM mark_items WHERE id=?', (item_id,))
    item = cur.fetchone()
    if not item:
        flash('Not found', 'error')
        return redirect(url_for('teacher_marks'))

    if request.method == 'POST':
        title = request.form.get('title')
        total = int(request.form.get('total'))
        cur.execute('UPDATE mark_items SET Title=?, Total=? WHERE id=?', (title, total, item_id))
        conn.commit()
        conn.close()
        flash('Item updated', 'success')
        return redirect(url_for('teacher_marks'))

    conn.close()
    return render_template('teacher_edit_mark_item.html', item=item)

@app.route('/teacher/marks/delete/<int:item_id>', methods=['POST'])
def teacher_delete_mark_item(item_id):
    if 'user' not in session :
        flash('Please login as teacher', 'error')
        return redirect(url_for('teacher_login'))

    conn = get_db_conn()
    cur = conn.cursor()
    # delete student marks then item
    cur.execute('DELETE FROM student_marks WHERE mark_item_id=?', (item_id,))
    cur.execute('DELETE FROM mark_items WHERE id=?', (item_id,))
    conn.commit()
    conn.close()
    flash('Item and its marks deleted', 'success')
    return redirect(url_for('teacher_marks'))



@app.route('/student/marks')
def student_marks():
    # Same pattern as student_attendance
    if 'user' not in session:
        return redirect(url_for('student_login'))

    roll = session['user']

    conn = get_db()
    cur = conn.cursor()

    # Get all enrolled courses
    cur.execute('SELECT Course_Code FROM enrollments WHERE Roll_No=?', (roll,))
    courses = [r['Course_Code'] for r in cur.fetchall()]

    course_reports = []

    for course in courses:
        # get mark items for course
        cur.execute('''
            SELECT id, Category, Item_No, Title, Total
            FROM mark_items
            WHERE Course_Code=?
            ORDER BY Category, Item_No
        ''', (course,))
        items = cur.fetchall()

        entries = []
        for it in items:
            item_id = it['id']
            category = it['Category']
            item_no = it['Item_No']
            title = it['Title']
            total = it['Total']

            cur.execute(
                'SELECT Obtained FROM student_marks WHERE mark_item_id=? AND Roll_No=?',
                (item_id, roll)
            )
            r = cur.fetchone()
            obtained = r['Obtained'] if r else None

            entries.append({
                'id': item_id,
                'category': category,
                'title': title,
                'item_no': item_no,
                'total': total,
                'obtained': obtained
            })

        category_agg = {}
        total_possible = 0
        total_obtained = 0

        for e in entries:
            total_possible += e['total'] or 0
            if e['obtained'] is not None:
                total_obtained += e['obtained']

            cat = e['category']
            if cat not in category_agg:
                category_agg[cat] = {'possible': 0, 'obtained': 0}

            category_agg[cat]['possible'] += e['total'] or 0
            category_agg[cat]['obtained'] += e['obtained'] or 0

        course_reports.append({
            'course': course,
            'items': entries,
            'category_agg': category_agg,
            'total_possible': total_possible,
            'total_obtained': total_obtained,
            'percentage': round(total_obtained / total_possible * 100, 2)
                          if total_possible > 0 else None
        })

    conn.close()
    return render_template('student_marks.html', reports=course_reports)

@app.route('/admit_card')
def admit_card():
    # --- Check login ---
    if 'user' not in session:
        flash("Please login first", "warning")
        return redirect(url_for('student_login'))

    roll_no = session['user']

    conn = get_db()
    cur = conn.cursor()

    # --- Student info ---
    cur.execute("""
        SELECT Roll_No, Name, Gender, DOB
        FROM students
        WHERE Roll_No = ?
    """, (roll_no,))
    student = cur.fetchone()
    if not student:
        conn.close()
        flash("Student record not found!", "danger")
        return redirect(url_for('student_home'))

    # --- Registered courses (only those in enrollments) ---
    cur.execute("""
        SELECT c.Course_Code, c.Course_Name, c.Credit_Hr
        FROM enrollments e
        JOIN courses c ON e.Course_Code = c.Course_Code
        WHERE e.Roll_No = ?
        ORDER BY c.Course_Code
    """, (roll_no,))
    courses = cur.fetchall()

    conn.close()

    # Optional: derive batch/degree/section from Roll_No same as student_home
    roll_parts = student['Roll_No'].split('-')
    batch = roll_parts[1] if len(roll_parts) > 1 else "N/A"
    degree_code = roll_parts[2] if len(roll_parts) > 2 else "N/A"
    section = roll_parts[3][0] if len(roll_parts) > 3 else "N/A"

    degree_map = {
        'SE': 'Software Engineering',
        'AI': 'Artificial Intelligence',
        'DS': 'Data Science',
        'CY': 'Cyber Security'
    }
    degree_name = degree_map.get(degree_code, degree_code)

    return render_template(
        'admit_card.html',
        student=student,
        batch=batch,
        degree_name=degree_name,
        section=section,
        courses=courses
    )




@app.route("/admin/teacher-courses")
def admin_teacher_courses():
    if "user" not in session:
        return redirect(url_for("adminlogin"))

    q = request.args.get("q", "").strip().lower()

    conn = sqlite3.connect("flake.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            t.Teacher_ID,
            t.Name AS Teacher_Name,
            t.Department,
            c.Course_Code,
            c.Course_Name,
            c.Credit_Hr
        FROM teacher_courses tc
        JOIN teachers t ON tc.Teacher_ID = t.Teacher_ID
        JOIN courses c ON tc.Course_Code = c.Course_Code
        ORDER BY t.Department, t.Teacher_ID, c.Course_Code
    """)
    rows = cur.fetchall()
    conn.close()

    # Build tabs by department
    tabs = {
        "SE": {"label": "Software Engineering", "items": []},
        "AI": {"label": "Artificial Intelligence", "items": []},
        "DS": {"label": "Data Science", "items": []},
        "CY": {"label": "Cyber Security", "items": []},
        "OTHER": {"label": "Other", "items": []},
    }

    for r in rows:
        dept = (r["Department"] or "").upper()
        if dept not in tabs:
            dept = "OTHER"
        tabs[dept]["items"].append(r)

    # Apply search: only by teacher name or course code
    if q:
        for code, info in tabs.items():
            filtered = []
            for r in info["items"]:
                name = (r["Teacher_Name"] or "").lower()
                ccode = (r["Course_Code"] or "").lower()
                if q in name or q in ccode:
                    filtered.append(r)
            tabs[code]["items"] = filtered

    return render_template(
        "admin_teacher_courses.html",
        user=session.get("user"),
        tabs=tabs,
        q=q
    )




def get_degree_from_roll(roll_no):
    # Very simple: find any 2-letter alpha token that matches known degrees
    degreemap = {"SE": "Software Engineering", "AI": "Artificial Intelligence",
                 "DS": "Data Science", "CY": "Cyber Security"}
    try:
        import re
        tokens = re.split(r"[-_]", roll_no)
        for tok in tokens:
            alpha = "".join(ch for ch in tok if ch.isalpha()).upper()
            if len(alpha) == 2 and alpha in degreemap:
                return alpha, degreemap[alpha]
    except:
        pass
    return None, None


from flask import request

@app.route("/admin/student-departments")
def admin_student_departments():
    if "user" not in session:
        return redirect(url_for("adminlogin"))

    q = request.args.get("q", "").strip().lower()

    conn = sqlite3.connect("flake.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT Roll_No, Name FROM students ORDER BY Roll_No")
    students = cur.fetchall()
    conn.close()

    # build tabs
    tabs = {
        "SE": {"label": "Software Engineering", "students": []},
        "AI": {"label": "Artificial Intelligence", "students": []},
        "DS": {"label": "Data Science", "students": []},
        "CY": {"label": "Cyber Security", "students": []},
        "OTHER": {"label": "Other", "students": []},
    }

    def get_degree_from_roll(roll_no):
        parts = roll_no.split("-")
        for p in parts:
            code = "".join(ch for ch in p if ch.isalpha()).upper()
            if code in ["SE", "AI", "DS", "CY"]:
                return code
        return "OTHER"

    # group students
    for s in students:
        dept = get_degree_from_roll(s["Roll_No"])
        if dept not in tabs:
            dept = "OTHER"
        tabs[dept]["students"].append(s)

    # apply search ONLY by roll or name
    if q:
        for code, info in tabs.items():
            filtered = []
            for s in info["students"]:
                if q in s["Roll_No"].lower() or q in (s["Name"] or "").lower():
                    filtered.append(s)
            tabs[code]["students"] = filtered

    return render_template(
        "admin_student_departments.html",
        user=session.get("user"),
        tabs=tabs,
        q=q
    )



@app.route("/admin/student-courses")
def admin_student_courses():
    if "user" not in session:
        return redirect(url_for("adminlogin"))

    search = request.args.get("q", "").strip().lower()

    conn = sqlite3.connect("flake.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            s.Roll_No,
            s.Name AS Student_Name,
            c.Course_Code,
            c.Course_Name
        FROM students s
        LEFT JOIN enrollments e ON s.Roll_No = e.Roll_No
        LEFT JOIN courses c ON e.Course_Code = c.Course_Code
        ORDER BY s.Roll_No, c.Course_Code
    """)
    rows = cur.fetchall()
    conn.close()

    # Group students first
    students = {}
    for r in rows:
        rn = r["Roll_No"]
        if rn not in students:
            students[rn] = {
                "name": r["Student_Name"],
                "courses": []
            }
        if r["Course_Code"]:
            students[rn]["courses"].append({
                "code": r["Course_Code"],
                "name": r["Course_Name"]
            })

    # Helper to get dept from roll
    def get_degree_from_roll(roll_no):
        parts = roll_no.split("-")
        for p in parts:
            code = "".join(ch for ch in p if ch.isalpha()).upper()
            if code in ["SE", "AI", "DS", "CY"]:
                return code
        return "OTHER"

    # Build tabs by department
    tabs = {
        "SE": {"label": "Software Engineering", "students": []},
        "AI": {"label": "Artificial Intelligence", "students": []},
        "DS": {"label": "Data Science", "students": []},
        "CY": {"label": "Cyber Security", "students": []},
        "OTHER": {"label": "Other", "students": []},
    }

    for roll, info in students.items():
        dept = get_degree_from_roll(roll)
        if dept not in tabs:
            dept = "OTHER"
        tabs[dept]["students"].append({
            "roll": roll,
            "name": info["name"],
            "courses": info["courses"]
        })

    # Apply search only by roll or name
    if search:
        for code, info in tabs.items():
            filtered_students = []
            for s in info["students"]:
                if (search in s["roll"].lower()) or (search in (s["name"] or "").lower()):
                    filtered_students.append(s)
            tabs[code]["students"] = filtered_students

    return render_template(
        "admin_student_courses.html",
        user=session.get("user"),
        tabs=tabs,
        q=search
    )

@app.route("/teacher/courses")
def teacher_courses_list():
    if "user" not in session:
        return redirect(url_for("teacherlogin"))

    teacherid = session.get("user")  # same as used elsewhere for teacher
    conn = sqlite3.connect("flake.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get this teacher's department
    cur.execute("""
        SELECT Department
        FROM teachers
        WHERE Teacher_ID = ?
        LIMIT 1
    """, (teacherid,))
    row = cur.fetchone()
    dept = row["Department"] if row else None

    # Get all courses this teacher teaches (from teacher_courses)
    cur.execute("""
        SELECT
            tc.Course_Code,
            c.Course_Name,
            c.Credit_Hr,
            c.Prerequisite
        FROM teacher_courses tc
        JOIN courses c ON tc.Course_Code = c.Course_Code
        WHERE tc.Teacher_ID = ?
        ORDER BY tc.Course_Code
    """, (teacherid,))
    courses = cur.fetchall()
    conn.close()

    # Build tabs: only one dept (teacher's own) plus OTHER if needed
    tabs = {
        "MAIN": {"label": f"{dept or 'My'} Department", "courses": []},
        "OTHER": {"label": "Other", "courses": []},
    }

    for c in courses:
        code = c["Course_Code"] or ""
        # department prefix from course code, e.g. CS-0001 -> CS
        prefix = code.split("-")[0] if "-" in code else code[:2]
        if dept and prefix.upper() == dept.upper():
            tabs["MAIN"]["courses"].append(c)
        else:
            tabs["OTHER"]["courses"].append(c)

    return render_template(
        "teacher_course_list.html",
        user_name=session.get("username"),
        tabs=tabs
    )

@app.route("/teacher/students")
def teacher_students_list():
    if "user" not in session:
        return redirect(url_for("teacherlogin"))

    teacherid = session.get("user")
    conn = sqlite3.connect("flake.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get all courses taught by this teacher
    cur.execute("""
        SELECT
            tc.Course_Code,
            c.Course_Name
        FROM teacher_courses tc
        JOIN courses c ON tc.Course_Code = c.Course_Code
        WHERE tc.Teacher_ID = ?
        ORDER BY tc.Course_Code
    """, (teacherid,))
    teacher_courses = cur.fetchall()
    course_map = {c["Course_Code"]: c for c in teacher_courses}

    if not teacher_courses:
        conn.close()
        return render_template(
            "teacher_student_list.html",
            user_name=session.get("username"),
            tabs={}
        )

    # Fetch enrolled students for these courses
    placeholders = ",".join("?" * len(course_map))
    cur.execute(f"""
        SELECT
            e.Course_Code,
            s.Roll_No,
            s.Name
        FROM enrollments e
        JOIN students s ON e.Roll_No = s.Roll_No
        WHERE e.Course_Code IN ({placeholders})
        ORDER BY e.Course_Code, s.Roll_No
    """, tuple(course_map.keys()))
    rows = cur.fetchall()
    conn.close()

    # Build structure: dept tabs -> courses -> students
    tabs = {}

    for r in rows:
        course_code = r["Course_Code"]
        roll = r["Roll_No"]
        name = r["Name"]

        # department from course code prefix (CS, MT, SS, CL, etc.)
        prefix = course_code.split("-")[0] if "-" in course_code else course_code[:2]
        dept_code = prefix.upper()

        if dept_code not in tabs:
            tabs[dept_code] = {
                "label": dept_code,
                "courses": {}
            }

        dept_courses = tabs[dept_code]["courses"]
        if course_code not in dept_courses:
            course_info = course_map.get(course_code)
            dept_courses[course_code] = {
                "code": course_code,
                "name": course_info["Course_Name"] if course_info else "",
                "students": []
            }

        dept_courses[course_code]["students"].append({
            "roll": roll,
            "name": name
        })

    return render_template(
        "teacher_student_list.html",
        user_name=session.get("username"),
        tabs=tabs
    )

def generate_voucher_id():
    # Simple random voucher like FEE-2025-ABC123
    year = datetime.now().strftime("%Y")
    rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"FEE-{year}-{rand}"

@app.route('/student/fee')
def student_fee():
    if 'user' not in session:
        return redirect(url_for('studentlogin'))

    rollno = session['user']

    conn = sqlite3.connect('flake.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Student info
    cur.execute("SELECT Roll_No, Name, Email, Mobile_No FROM students WHERE Roll_No = ?", (rollno,))
    student = cur.fetchone()

    # Enrolled courses with credit hours
    cur.execute("""
        SELECT c.Course_Code, c.Course_Name, c.Credit_Hr
        FROM enrollments e
        JOIN courses c ON e.Course_Code = c.Course_Code
        WHERE e.Roll_No = ?
        ORDER BY c.Course_Code
    """, (rollno,))
    courses = cur.fetchall()

    conn.close()

    total_credits = sum(row['Credit_Hr'] or 0 for row in courses)
    fee_per_credit = 10000
    total_fee = total_credits * fee_per_credit

    voucher_id = generate_voucher_id()
    current_date = datetime.now().strftime("%d-%m-%Y")

    return render_template(
        'fee_details.html',
        student=student,
        courses=courses,
        total_credits=total_credits,
        fee_per_credit=fee_per_credit,
        total_fee=total_fee,
        voucher_id=voucher_id,
        current_date=current_date
    )



# ---------- FILE UPLOAD HELPER (local, not Firebase) ----------

UPLOAD_ROOT = os.path.join(os.path.dirname(__file__), "static", "uploads")

def save_uploaded_file(file_storage, subfolder="announcements"):
    """Save an uploaded file under static/uploads and return metadata dict."""
    if not file_storage or file_storage.filename == "":
        return None

    safe_name = secure_filename(file_storage.filename)
    ext = os.path.splitext(safe_name)[1]
    unique = f"{uuid.uuid4().hex}{ext}"

    folder = os.path.join(UPLOAD_ROOT, subfolder)
    os.makedirs(folder, exist_ok=True)

    path = os.path.join(folder, unique)
    file_storage.save(path)

    rel_url = f"/static/uploads/{subfolder}/{unique}"
    return {
        "filename": safe_name,
        "url": rel_url,
        "mime_type": file_storage.mimetype or "application/octet-stream",
    }


    
# ========== TEACHER ANNOUNCEMENTS (SQLite) ==========

@app.route("/teacher/announcements", methods=["GET"])
def teacher_announcements():
    if 'user' not in session or session.get('user_type') != 'teacher':
        return redirect(url_for('teacher_login'))

    tid = session['user']

    # courses from flake.db
    conn_main = get_db()
    curm = conn_main.cursor()
    curm.execute("""
        SELECT Course_Code, Course_Name, Department
        FROM teachers
        WHERE Teacher_ID = ?
    """, (tid,))
    rows = curm.fetchall()
    conn_main.close()

    courses = []
    for r in rows:
        courses.append({
            'code': r['Course_Code'],
            'name': r['Course_Name'],
            'department': r['Department']
        })

    selected_course = request.args.get('course')
    if not selected_course and courses:
        selected_course = courses[0]['code']

    announcements = []
    if selected_course:
        conn = get_ann_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM announcements
            WHERE course_code = ?
            ORDER BY datetime(created_at) DESC
            LIMIT 30
        """, (selected_course,))
        announcements = [dict(r) for r in cur.fetchall()]
        conn.close()

    return render_template(
        "Announcement_T.html",
        user=tid,
        user_name=session.get('user_name'),
        courses=courses,
        selected_course=selected_course,
        announcements=announcements
    )


@app.route("/teacher/announcements/create", methods=["POST"])
def teacher_announcements_create():
    if 'user' not in session or session.get('user_type') != 'teacher':
        return redirect(url_for('teacher_login'))

    title   = request.form.get('title', '').strip()
    body    = request.form.get('body', '').strip()
    course  = request.form.get('course_code')
    kind    = request.form.get('type', 'text')   # text | assignment
    due_str = request.form.get('due_at', '').strip()

    if not title or not body or not course:
        flash("Title, body and course are required.", "danger")
        return redirect(url_for('teacher_announcements', course=course or ""))

    due_iso = None
    if kind == 'assignment' and due_str:
        try:
            dt = datetime.fromisoformat(due_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            due_iso = dt.isoformat()
        except ValueError:
            flash("Invalid due date/time.", "danger")
            return redirect(url_for('teacher_announcements', course=course))

    conn = get_ann_db()
    cur = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()

    cur.execute("""
        INSERT INTO announcements
        (title, body, created_by, created_by_role, created_at,
         audience_role, batch, department, section, course_code, type, due_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        title, body,
        session['user'], 'teacher', now_iso,
        'student', None, None, None, course,
        kind, due_iso
    ))
    ann_id = cur.lastrowid

    if 'files' in request.files:
        for file in request.files.getlist('files'):
            meta = save_uploaded_file(file, subfolder="teacher")
            if meta:
                cur.execute("""
                    INSERT INTO announcement_attachments
                    (announcement_id, filename, url, mime_type)
                    VALUES (?, ?, ?, ?)
                """, (ann_id, meta['filename'], meta['url'], meta['mime_type']))

    conn.commit()
    conn.close()

    flash("Announcement created.", "success")
    return redirect(url_for('teacher_announcements', course=course))


# ========== STUDENT ANNOUNCEMENTS (SQLite) ==========

def parse_student_batch_dept_section(roll_no: str):
    parts = roll_no.split('-')
    batch = parts[1] if len(parts) > 1 else None
    section = parts[2] if len(parts) > 2 else None
    dept = None
    return batch, dept, section


@app.route("/student/announcements", methods=["GET"])
def student_announcements():
    if 'user' not in session or session.get('user_type') != 'student':
        return redirect(url_for('student_login'))

    sid = session['user']

    conn_main = get_db()
    conn_main.row_factory = sqlite3.Row
    curm = conn_main.cursor()
    curm.execute("SELECT Roll_No, Name FROM students WHERE Roll_No = ?", (sid,))
    stu = curm.fetchone()
    conn_main.close()
    if not stu:
        flash("Student not found.", "danger")
        return redirect(url_for('student_home'))

    roll_no = stu['Roll_No']
    batch, dept, section = parse_student_batch_dept_section(roll_no)

    conn = get_ann_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM announcements
        WHERE audience_role IN ('student','all')
        ORDER BY datetime(created_at) DESC
        LIMIT 50
    """)
    rows = cur.fetchall()
    conn.close()

    announcements = []
    for r in rows:
        data = dict(r)
        ok = True
        if data.get('batch') and batch and data['batch'] != batch:
            ok = False
        if data.get('department') and dept and data['department'] != dept:
            ok = False
        if data.get('section') and section and data['section'] != section:
            ok = False
        if ok:
            announcements.append(data)

    return render_template(
        "Announcement_S.html",
        user=sid,
        user_name=stu['Name'],
        announcements=announcements
    )


# ========== ADMIN ANNOUNCEMENTS (SQLite) ==========

@app.route("/admin/announcements", methods=["GET"])
def admin_announcements():
    if 'user' not in session or session.get('user_type') != 'admin':
        return redirect(url_for('admin_login'))

    audience = request.args.get('audience', 'students')
    batch    = request.args.get('batch') or None
    dept     = request.args.get('department') or None
    section  = request.args.get('section') or None

    conn = get_ann_db()
    cur = conn.cursor()

    sql = """
        SELECT * FROM announcements
        WHERE 1=1
    """
    params = []

    if audience == 'students':
        sql += " AND audience_role IN ('student','all')"
    elif audience == 'teachers':
        sql += " AND audience_role IN ('teacher','all')"

    if batch:
        sql += " AND batch = ?"
        params.append(batch)
    if dept:
        sql += " AND department = ?"
        params.append(dept)
    if section:
        sql += " AND section = ?"
        params.append(section)

    sql += " ORDER BY datetime(created_at) DESC LIMIT 30"

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    announcements = [dict(r) for r in rows]

    # simple lists; replace from flake.db if you want
    batches     = ["M-22", "M-23"]
    departments = ["SE", "CS", "EE"]
    sections    = ["A", "B", "C"]

    return render_template(
        "Announcement_A.html",
        user=session['user'],
        user_name="Admin",
        announcements=announcements,
        batches=batches,
        departments=departments,
        sections=sections,
        current_audience=audience,
        current_batch=batch or "",
        current_department=dept or "",
        current_section=section or "",
    )


@app.route("/admin/announcements/create", methods=["POST"])
def admin_announcements_create():
    if 'user' not in session or session.get('user_type') != 'admin':
        return redirect(url_for('admin_login'))

    title    = request.form.get('title', '').strip()
    body     = request.form.get('body', '').strip()
    audience = request.form.get('audience', 'students')
    batch    = request.form.get('batch') or None
    dept     = request.form.get('department') or None
    section  = request.form.get('section') or None

    if not title or not body:
        flash("Title and body are required.", "danger")
        return redirect(url_for('admin_announcements'))

    audience_role = 'all'
    if audience == 'students':
        audience_role = 'student'
    elif audience == 'teachers':
        audience_role = 'teacher'

    # save announcement
    conn = get_ann_db()
    cur = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()

    cur.execute("""
        INSERT INTO announcements
        (title, body, created_by, created_by_role, created_at,
         audience_role, batch, department, section, course_code, type, due_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        title, body,
        session['user'], 'admin', now_iso,
        audience_role, batch, dept, section, None,
        'text', None
    ))
    ann_id = cur.lastrowid

    # attachments
    if 'files' in request.files:
        for file in request.files.getlist('files'):
            meta = save_uploaded_file(file, subfolder="admin")
            if meta:
                cur.execute("""
                    INSERT INTO announcement_attachments
                    (announcement_id, filename, url, mime_type)
                    VALUES (?, ?, ?, ?)
                """, (ann_id, meta['filename'], meta['url'], meta['mime_type']))

    conn.commit()
    conn.close()

    flash("Announcement created.", "success")
    return redirect(url_for('admin_announcements'))

# ========== ANNOUNCEMNT ROUTES ========

@app.route("/announcements/<int:ann_id>/comments", methods=["GET", "POST"])
def announcement_comments(ann_id):
    if 'user' not in session:
        return jsonify({"error": "not_authenticated"}), 401

    conn = get_ann_db()
    cur = conn.cursor()

    if request.method == "GET":
        cur.execute("""
            SELECT * FROM announcement_comments
            WHERE announcement_id = ?
            ORDER BY datetime(created_at) ASC
        """, (ann_id,))
        rows = cur.fetchall()
        conn.close()
        comments = [dict(r) for r in rows]
        return jsonify(comments)

    # POST
    data = request.get_json(force=True)
    text = (data.get('text') or "").strip()
    if not text:
        conn.close()
        return jsonify({"error": "empty"}), 400

    now_iso = datetime.now(timezone.utc).isoformat()
    cur.execute("""
        INSERT INTO announcement_comments
        (announcement_id, author_id, author_role, text, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (ann_id, session['user'], session.get('user_type', 'student'), text, now_iso))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

@app.route("/announcements/<int:ann_id>/submit", methods=["POST"])
def announcement_submit(ann_id):
    if 'user' not in session or session.get('user_type') != 'student':
        return jsonify({"error": "not_allowed"}), 403

    conn = get_ann_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM announcements WHERE id = ?", (ann_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "not_found"}), 404

    ann = dict(row)
    if ann.get('type') != 'assignment':
        conn.close()
        return jsonify({"error": "not_assignment"}), 400

    now = datetime.now(timezone.utc)
    due_at = ann.get('due_at')
    if due_at:
        try:
            due_dt = datetime.fromisoformat(due_at)
            if due_dt.tzinfo is None:
                due_dt = due_dt.replace(tzinfo=timezone.utc)
            if now > due_dt:
                conn.close()
                return jsonify({"error": "late", "message": "Deadline has passed."}), 400
        except ValueError:
            # bad stored date; allow teacher to fix later
            pass

    file = request.files.get('submission_file')
    if not file or file.filename == "":
        conn.close()
        return jsonify({"error": "no_file"}), 400

    meta = save_uploaded_file(file, subfolder="submissions")
    if not meta:
        conn.close()
        return jsonify({"error": "upload_failed"}), 500

    now_iso = now.isoformat()
    cur.execute("""
        INSERT INTO announcement_submissions
        (announcement_id, student_id, filename, url, mime_type, submitted_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (ann_id, session['user'],
          meta['filename'], meta['url'], meta['mime_type'], now_iso))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})
@app.route('/student_timetable')
def student_timetable():
    if 'user' not in session:
        return redirect(url_for('student_login'))

    rollno = session['user']

    try:
        conn = sqlite3.connect('flake.db')
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # --- Get student info ---
        cur.execute("SELECT Roll_No, Name FROM students WHERE Roll_No = ?", (rollno,))
        student = cur.fetchone()
        if not student:
            conn.close()
            flash("Student not found", "danger")
            return redirect(url_for('student_home'))

        # --- Get student's section from Roll_No ---
        # Example formats:
        #   F-22-SE-A-3001  -> section = "Section A"
        #   M-22SE-A-3001   -> section = "Section A"
        section = None
        parts = rollno.split('-')

        # Case 1: F-22-SE-A-3001 → section letter is parts[3]
        if len(parts) >= 4:
            section_part = parts[3]
        # Case 2: older format M-22SE-A-3001 → section in parts[2]
        elif len(parts) >= 3:
            section_part = parts[2]
        else:
            section_part = ''

        letters = ''.join(ch for ch in section_part if ch.isalpha())
        if letters:
            section = f"Section {letters.upper()}"

        # Fallback default
        if not section:
            section = "Section A"

        # DEBUG: show what section we computed
        print("DEBUG [student_timetable] Roll_No:", rollno)
        print("DEBUG [student_timetable] computed section:", section)

        # --- Get enrolled course codes for this student ---
        cur.execute("SELECT Course_Code FROM enrollments WHERE Roll_No = ?", (rollno,))
        enrolled_courses = [row['Course_Code'] for row in cur.fetchall()]

        # DEBUG: show enrolled courses
        print("DEBUG [student_timetable] enrolled_courses:", enrolled_courses)

        if not enrolled_courses:
            conn.close()
            flash("You are not enrolled in any courses.", "info")
            return render_template(
                'student_timetable.html',
                student=student,
                schedule={},
                statistics={'total_classes': 0, 'total_hours': 0, 'total_students': 0},
                user=rollno,
                username=student['Name']
            )

        # --- Build timetable query for this student (by section + enrolled courses) ---
        placeholders = ','.join('?' for _ in enrolled_courses)
        query = f"""
            SELECT t.Day, t.Start_Time, t.End_Time, t.Room, t.Section, t.Class_Type,
                   t.Course_Code, c.Course_Name
            FROM timetable t
            JOIN courses c ON t.Course_Code = c.Course_Code
            WHERE t.Section = ? AND t.Course_Code IN ({placeholders})
            ORDER BY
                CASE t.Day
                    WHEN 'Monday' THEN 1
                    WHEN 'Tuesday' THEN 2
                    WHEN 'Wednesday' THEN 3
                    WHEN 'Thursday' THEN 4
                    WHEN 'Friday' THEN 5
                    WHEN 'Saturday' THEN 6
                END,
                t.Start_Time
        """
        params = [section] + enrolled_courses
        cur.execute(query, params)
        rows = cur.fetchall()

        # DEBUG: show how many rows we got and a sample
        print("DEBUG [student_timetable] timetable rows count:", len(rows))
        for r in rows[:5]:
            print("DEBUG [student_timetable] row:", dict(r))

        # --- Organize schedule by day ---
        schedule = {}
        for row in rows:
            day = row['Day']
            if day not in schedule:
                schedule[day] = []
            schedule[day].append({
                'start_time': row['Start_Time'],
                'end_time': row['End_Time'],
                'course_code': row['Course_Code'],
                'course_name': row['Course_Name'],
                'room': row['Room'],
                'section': row['Section'],
                'type': row['Class_Type'],
                'students': ''
            })

        # --- Statistics (total classes & hours) ---
        total_classes = sum(len(v) for v in schedule.values())
        total_hours = 0
        for classes in schedule.values():
            for cls in classes:
                s_h, s_m = map(int, cls['start_time'].split(':'))
                e_h, e_m = map(int, cls['end_time'].split(':'))
                start_min = s_h * 60 + s_m
                end_min = e_h * 60 + e_m
                total_hours += (end_min - start_min) / 60.0

        statistics = {
            'total_classes': total_classes,
            'total_hours': round(total_hours, 1),
            'total_students': 0
        }

        conn.close()
        return render_template(
            'student_timetable.html',
            student=student,
            schedule=schedule,
            statistics=statistics,
            user=rollno,
            username=student['Name']
        )

    except Exception as e:
        print("Error loading student timetable:", e)
        import traceback
        traceback.print_exc()
        flash("Error loading timetable", "danger")
        return redirect(url_for('student_home'))


# ------------------ RUN SERVER ------------------
if __name__ == '__main__':
    socketio.run(app, debug=True)

