import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'attendance.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --------------------- DATABASE TABLES ---------------------
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    student_number = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    attendances = db.relationship('Attendance', backref='student', lazy=True)

class Lecturer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    lectures = db.relationship('Lecture', backref='lecturer', lazy=True)

class Lecture(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    is_active = db.Column(db.Boolean, default=False)
    lecturer_id = db.Column(db.Integer, db.ForeignKey('lecturer.id'), nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    attendances = db.relationship('Attendance', backref='lecture', lazy=True)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    lecture_id = db.Column(db.Integer, db.ForeignKey('lecture.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    present = db.Column(db.Boolean, default=True)

# --------------------- One‑time setup (replacement for before_first_request) ---------------------
_initialized = False

@app.before_request
def initialize():
    global _initialized
    if not _initialized:
        db.create_all()                     # creates tables if they don't exist
        if not Lecturer.query.filter_by(username='admin').first():
            hashed = generate_password_hash('admin123')
            lecturer = Lecturer(username='admin', password_hash=hashed)
            db.session.add(lecturer)
            db.session.commit()
            print("Default lecturer created: admin / admin123")
        _initialized = True

# --------------------- Routes ---------------------
@app.route('/')
def landing():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip()
        student_number = request.form['student_number'].strip()
        password = request.form['password']
        confirm = request.form['confirm_password']

        if password != confirm:
            flash('Passwords do not match', 'error')
            return redirect(url_for('signup'))

        if Student.query.filter((Student.email == email) | (Student.student_number == student_number)).first():
            flash('Email or Student Number already registered', 'error')
            return redirect(url_for('signup'))

        hashed = generate_password_hash(password)
        student = Student(name=name, email=email, student_number=student_number, password_hash=hashed)
        db.session.add(student)
        db.session.commit()
        flash('Registration successful. Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        student_number = request.form['student_number'].strip()
        password = request.form['password']
        student = Student.query.filter_by(student_number=student_number).first()
        if student and check_password_hash(student.password_hash, password):
            session['student_id'] = student.id
            return redirect(url_for('mark_attendance'))
        flash('Invalid student number or password', 'error')
    return render_template('login.html')

@app.route('/mark_attendance', methods=['GET', 'POST'])
def mark_attendance():
    if 'student_id' not in session:
        return redirect(url_for('login'))
    student = Student.query.get(session['student_id'])
    active_lecture = Lecture.query.filter_by(is_active=True).first()
    already_marked = False
    if active_lecture:
        already_marked = Attendance.query.filter_by(student_id=student.id, lecture_id=active_lecture.id).first() is not None

    if request.method == 'POST':
        if active_lecture and not already_marked:
            att = Attendance(student_id=student.id, lecture_id=active_lecture.id)
            db.session.add(att)
            db.session.commit()
        session.pop('student_id', None)
        return redirect(url_for('success'))

    return render_template('mark_attendance.html', student=student, active_lecture=active_lecture, already_marked=already_marked)

@app.route('/success')
def success():
    return render_template('success.html')

@app.route('/lecturer/login', methods=['GET', 'POST'])
def lecturer_login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        lecturer = Lecturer.query.filter_by(username=username).first()
        if lecturer and check_password_hash(lecturer.password_hash, password):
            session['lecturer_id'] = lecturer.id
            return redirect(url_for('lecturer_dashboard'))
        flash('Invalid username or password', 'error')
    return render_template('lecturer_login.html')

@app.route('/lecturer/dashboard', methods=['GET', 'POST'])
def lecturer_dashboard():
    if 'lecturer_id' not in session:
        return redirect(url_for('lecturer_login'))

    section = request.args.get('section', 'attendance')
    lecturer = Lecturer.query.get(session['lecturer_id'])

    # Handle POST actions
    if request.method == 'POST':
        form_type = request.form.get('form_type')
        if form_type == 'new_lecture':
            title = request.form['lecture_title'].strip()
            Lecture.query.filter_by(lecturer_id=lecturer.id, is_active=True).update({'is_active': False})
            new_lecture = Lecture(title=title, is_active=True, lecturer_id=lecturer.id)
            db.session.add(new_lecture)
            db.session.commit()
            return redirect(url_for('lecturer_dashboard', section='attendance'))

        elif form_type == 'set_active':
            lecture_id = int(request.form['lecture_id'])
            Lecture.query.filter_by(lecturer_id=lecturer.id, is_active=True).update({'is_active': False})
            lecture = Lecture.query.get(lecture_id)
            if lecture and lecture.lecturer_id == lecturer.id:
                lecture.is_active = True
                db.session.commit()
            return redirect(url_for('lecturer_dashboard', section='attendance'))

        elif form_type == 'add_student':
            name = request.form['name'].strip()
            email = request.form['email'].strip()
            student_number = request.form['student_number'].strip()
            password = request.form['password']
            add_message = None
            if not name or not email or not student_number or not password:
                add_message = "All fields are required."
            elif Student.query.filter((Student.email == email) | (Student.student_number == student_number)).first():
                add_message = "Email or Student Number already exists."
            else:
                hashed = generate_password_hash(password)
                student = Student(name=name, email=email, student_number=student_number, password_hash=hashed)
                db.session.add(student)
                db.session.commit()
                add_message = f"Student {name} added successfully."
            return render_template('lecturer_dashboard.html', section='add_student', add_message=add_message)

        elif form_type == 'search':
            query = request.form.get('query', '').strip()
            results = []
            if query:
                students = Student.query.filter(
                    (Student.name.contains(query)) | (Student.student_number.contains(query))
                ).all()
                results = [(s, Attendance.query.filter_by(student_id=s.id).count()) for s in students]
            return render_template('lecturer_dashboard.html', section='search', search_results=results, query=query)

    # GET: build data for each section
    if section == 'attendance':
        lectures = Lecture.query.filter_by(lecturer_id=lecturer.id).order_by(Lecture.date_created.desc()).all()
        lecture_id = request.args.get('lecture_id', type=int)
        selected_lecture = None
        attendance_list = []
        if lecture_id:
            selected_lecture = Lecture.query.get(lecture_id)
            if selected_lecture and selected_lecture.lecturer_id == lecturer.id:
                attendance_list = Attendance.query.filter_by(lecture_id=lecture_id).all()
        return render_template('lecturer_dashboard.html', section=section, lectures=lectures,
                               selected_lecture=selected_lecture, attendance_list=attendance_list)

    elif section == 'trends':
        lectures = Lecture.query.filter_by(lecturer_id=lecturer.id).order_by(Lecture.date_created.asc()).all()
        total_students = Student.query.count()
        trend_data = []
        for lec in lectures:
            present_count = Attendance.query.filter_by(lecture_id=lec.id).count()
            percentage = (present_count / total_students * 100) if total_students > 0 else 0
            trend_data.append({
                'lecture': lec,
                'present': present_count,
                'total': total_students,
                'percentage': round(percentage, 1)
            })
        return render_template('lecturer_dashboard.html', section=section, trend_data=trend_data)

    elif section == 'add_student':
        return render_template('lecturer_dashboard.html', section=section)

    elif section == 'search':
        return render_template('lecturer_dashboard.html', section=section, search_results=None, query='')

    elif section == 'print_attendance':
        lecture_id = request.args.get('lecture_id', type=int)
        selected_lecture = Lecture.query.get(lecture_id)
        if selected_lecture and selected_lecture.lecturer_id == lecturer.id:
            attendance_list = Attendance.query.filter_by(lecture_id=lecture_id).all()
            return render_template('lecturer_dashboard.html', section='print_attendance',
                                   selected_lecture=selected_lecture, attendance_list=attendance_list)
        return redirect(url_for('lecturer_dashboard', section='attendance'))

    return render_template('lecturer_dashboard.html', section=section)

@app.route('/lecturer/logout')
def lecturer_logout():
    session.pop('lecturer_id', None)
    return redirect(url_for('landing'))

# --------------------- Run ---------------------
if __name__ == '__main__':
    # With the @before_request hook above, tables and admin are created on first request.
    app.run(debug=True)
