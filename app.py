# app.py
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import json
import os
import gspread
from functools import wraps

# --- Firebase Admin SDK Imports ---
import firebase_admin
from firebase_admin import credentials, auth

# --- Flask App Setup ---
app = Flask(__name__)
app.secret_key = os.urandom(24) # Replace with a strong, permanent secret key in production

# --- Google Sheets Configuration ---
# IMPORTANT:
# 1. Go to Google Cloud Console: https://console.cloud.google.com/
# 2. Create a new project or select an existing one.
# 3. Enable the "Google Sheets API" and "Google Drive API".
# 4. Go to "Credentials" -> "Create Credentials" -> "Service Account".
# 5. Create a new service account, download the JSON key file, and place it in the same directory as this app.py file.
# 6. Share your Google Sheet with the email address of the service account (e.g., your-service-account-name@your-project-id.iam.gserviceaccount.com).
# 7. Replace 'your-google-sheet-id' with your actual Google Sheet ID (from the URL).
# 8. Replace 'your-service-account-key.json' with the actual filename of your downloaded JSON key.

GOOGLE_SHEET_ID = '1LcWVbB8GkCJ55S_MN78km3Y4xn1JxnAGN6EOrfouO7Y' # Updated with the provided ID
SERVICE_ACCOUNT_FILE = 'tws-question-bank-297ef7f605bf.json' # Service account file name

# --- Initialize Google Sheets Client ---
questions_worksheet = None # Initialize to None
try:
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        print(f"ERROR: Service account file '{SERVICE_ACCOUNT_FILE}' not found.")
        print("Please ensure the JSON key file is in the same directory as app.py for Google Sheets access.")
    else:
        # Use gspread.service_account() for a more robust authentication
        client = gspread.service_account(filename=SERVICE_ACCOUNT_FILE)
        
        # Use open_by_url instead of open_by_id as open_by_id was reported missing
        # Construct the full URL from the GOOGLE_SHEET_ID
        spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/edit"
        spreadsheet = client.open_by_url(spreadsheet_url)
        questions_worksheet = spreadsheet.worksheet("question") # Updated worksheet name to "question"
        print("Successfully connected to Google Sheets.")
        # Verify headers exist and are correct
        try:
            # Updated expected headers to include new fields, including 'Type'
            headers = questions_worksheet.row_values(1)
            expected_headers = [
                'Question', 'Answer', 'Category', 'Difficulty', 'Type', 'Author Name',
                'Option A', 'Option B', 'Option C', 'Option D', 'Correct Answer',
                'Context', 'Troubleshoot Step', 'Root Cause', 'Things to Avoid'
            ]
            if not all(h in headers for h in expected_headers):
                print(f"WARNING: Google Sheet headers do not fully match expected. Expected: {expected_headers}, Found: {headers}")
                print("Please ensure the first row of your 'question' sheet has all these headers.")
        except Exception as e:
            print(f"WARNING: Could not read Google Sheet headers. Please ensure the 'question' sheet is accessible and not empty. Error: {e}")

except gspread.exceptions.SpreadsheetNotFound:
    print(f"ERROR: Google Sheet with ID '{GOOGLE_SHEET_ID}' not found or accessible.")
    print("Please check the GOOGLE_SHEET_ID and ensure the service account has editor access to the sheet.")
except gspread.exceptions.WorksheetNotFound:
    print("ERROR: Worksheet named 'question' not found in the Google Sheet.")
    print("Please ensure there is a tab named 'question' in your Google Sheet.")
except Exception as e:
    print(f"CRITICAL ERROR connecting to Google Sheets: {e}")
    print("Please review your Google Cloud setup, API keys, and service account permissions.")

# --- Firebase Admin SDK Initialization ---
# IMPORTANT: Replace 'path/to/your/serviceAccountKey.json' with the actual path to your Firebase service account key file.
# You can download this from Firebase Console -> Project settings -> Service accounts -> Generate new private key.
FIREBASE_SERVICE_ACCOUNT_PATH = 'tws-question-bank-82a10-5d33d8483530.json' # Replace with your actual path

try:
    if not os.path.exists(FIREBASE_SERVICE_ACCOUNT_PATH):
        print(f"ERROR: Firebase service account file '{FIREBASE_SERVICE_ACCOUNT_PATH}' not found.")
        print("Please ensure the JSON key file is in the same directory as app.py for Firebase Admin SDK.")
    else:
        cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(cred)
        print("Successfully initialized Firebase Admin SDK.")
except Exception as e:
    print(f"CRITICAL ERROR initializing Firebase Admin SDK: {e}")
    print("Please review your Firebase service account key path and permissions.")


# --- Authentication Decorator ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        id_token = session.get('id_token')
        if not id_token:
            flash("You need to be logged in to access this page.", 'error')
            return redirect(url_for('login'))
        try:
            # Verify the ID token
            decoded_token = auth.verify_id_token(id_token)
            session['uid'] = decoded_token['uid']
            session['email'] = decoded_token['email']
            session['logged_in'] = True # Set logged_in based on successful token verification
        except Exception as e:
            print(f"Error verifying Firebase ID token: {e}")
            session.pop('id_token', None)
            session.pop('uid', None)
            session.pop('email', None)
            session['logged_in'] = False # Ensure logged_in is False on token verification failure
            flash("Your session has expired or is invalid. Please log in again.", 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Routes ---
@app.route('/')
def index():
    interview_questions = []
    if questions_worksheet:
        try:
            data = questions_worksheet.get_all_records()
            interview_questions = data[:3]
        except Exception as e:
            print(f"Error fetching data for home page demo from Google Sheets: {e}")
            interview_questions = [{"Question": "Error loading questions. Check server logs.", "Answer": "Please check Google Sheets configuration and permissions."}]
    else:
        interview_questions = [{"Question": "Google Sheets not connected.", "Answer": "Please check server logs for connection errors and setup instructions."}]
    return render_template('index.html', questions=interview_questions, logged_in=session.get('logged_in', False))

@app.route('/interview-questions')
def interview_questions_page():
    interview_based_questions = []
    scenario_questions = []
    live_interview_questions = []
    community_driven_questions = []
    
    type_filter = request.args.get('type_filter', 'all').lower() 

    if questions_worksheet:
        try:
            all_data = questions_worksheet.get_all_records()
            
            for q in all_data:
                q_type = q.get('Type', 'General').lower()

                if q_type == 'interview_based' or q_type == 'multiple_choice':
                    interview_based_questions.append(q)
                elif q_type == 'scenario_based':
                    scenario_questions.append(q)
                elif q_type == 'live_interview':
                    live_interview_questions.append(q)
                elif q_type == 'community_driven':
                    community_driven_questions.append(q)

        except Exception as e:
            print(f"Error fetching or categorizing data for interview questions page from Google Sheets: {e}")
            interview_based_questions = []
            scenario_questions = []
            live_interview_questions = []
            community_driven_questions = []
    else:
        print("Google Sheets not connected. Cannot fetch questions for categorization.")
        interview_based_questions = []
        scenario_questions = []
        live_interview_questions = []
        community_driven_questions = []
    
    return render_template(
        'interview_questions.html',
        interview_based_questions=interview_based_questions,
        scenario_questions=scenario_questions,
        live_interview_questions=live_interview_questions,
        community_driven_questions=community_driven_questions,
        logged_in=session.get('logged_in', False),
        current_type_filter=type_filter
    )

@app.route('/jobs')
def jobs_page():
    return render_template('jobs.html', logged_in=session.get('logged_in', False))


@app.route('/add-question', methods=['GET', 'POST'])
@login_required # This page now requires login
def add_question():
    if request.method == 'POST':
        question_type = request.form.get('question_type')
        author_name = request.form.get('author_name', '')
        category = request.form.get('category', 'General')
        difficulty = request.form.get('difficulty', 'Medium')

        question_text = ''
        answer_text = ''
        option_a = ''
        option_b = ''
        option_c = ''
        option_d = ''
        correct_answer = ''
        scenario_question = ''
        context = ''
        troubleshoot_step = ''
        root_cause = ''
        things_to_avoid = ''

        if question_type == 'interview_based':
            question_text = request.form.get('question', '')
            answer_text = request.form.get('answer', '')
        elif question_type == 'scenario_based':
            scenario_question = request.form.get('scenario_question', '')
            context = request.form.get('context', '')
            troubleshoot_step = request.form.get('troubleshoot_step', '')
            root_cause = request.form.get('root_cause', '')
            things_to_avoid = request.form.get('things_to_avoid', '')
            question_text = scenario_question
            answer_text = f"Context: {context}\nTroubleshoot: {troubleshoot_step}\nRoot Cause: {root_cause}\nAvoid: {things_to_avoid}"
        elif question_type == 'multiple_choice':
            question_text = request.form.get('mcq_question', '')
            option_a = request.form.get('option_a', '')
            option_b = request.form.get('option_b', '')
            option_c = request.form.get('option_c', '')
            option_d = request.form.get('option_d', '')
            correct_answer = request.form.get('correct_answer', '')
            answer_text = correct_answer
        elif question_type == 'live_interview':
            question_text = request.form.get('question', '')
            answer_text = request.form.get('answer', '')
        elif question_type == 'community_driven':
            question_text = request.form.get('question', '')
            answer_text = request.form.get('answer', '')

        row_to_add = [
            question_text,
            answer_text,
            category,
            difficulty,
            question_type,
            author_name,
            option_a,
            option_b,
            option_c,
            option_d,
            correct_answer,
            context,
            troubleshoot_step,
            root_cause,
            things_to_avoid
        ]

        if questions_worksheet:
            try:
                questions_worksheet.append_row(row_to_add)
                print(f"Added new {question_type} question: {question_text}")
                return redirect(url_for('add_question', success='true', type=question_type))
            except Exception as e:
                print(f"ERROR: Failed to add question to Google Sheets: {e}")
                flash("Error adding question. Please check server logs and Google Sheet column setup.", 'error')
                return render_template('add_question.html', logged_in=session.get('logged_in', False), error_message="Error adding question.")
        else:
            print("ERROR: Attempted to add question, but Google Sheets connection is not established.")
            flash("Google Sheets not connected. Cannot add question. Check server logs for details.", 'error')
            return render_template('add_question.html', logged_in=session.get('logged_in', False), error_message="Google Sheets not connected.")
    return render_template('add_question.html', logged_in=session.get('logged_in', False))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        action = request.form.get('action') # 'login' or 'register'

        if not email or not password:
            flash('Email and password are required.', 'error')
            return redirect(url_for('login'))

        try:
            if action == 'register':
                user = auth.create_user(email=email, password=password)
                # After creating, you might want to sign them in immediately
                # For simplicity, we'll just redirect to login for now.
                flash(f'User {user.email} created successfully! Please log in.', 'success')
                return redirect(url_for('login'))
            elif action == 'login':
                # Firebase Admin SDK does not directly sign in users with email/password
                # It's primarily for server-side user management.
                # For email/password login, the client-side Firebase SDK handles the actual authentication
                # and sends an ID token to the backend.
                # Here, we'll simulate a successful login by assuming the client-side has authenticated
                # and passed the ID token.
                # In a real app, you'd receive an ID token from the client after they sign in,
                # then verify it on the server.
                # For this setup, we're relying on the client-side JavaScript to do the actual login,
                # and then redirecting to a page that will trigger the login_required decorator
                # which verifies the token.
                flash('Login process initiated. Please wait for redirection...', 'info')
                # The client-side JS will handle the actual sign-in and redirection with token.
                # This backend /login POST is primarily for registration or if you were
                # to implement a custom token generation flow.
                return jsonify({"status": "success", "message": "Proceed to client-side login."})
            else:
                flash('Invalid action.', 'error')
                return redirect(url_for('login'))

        except Exception as e:
            error_message = str(e)
            print(f"Firebase Auth Error: {error_message}")
            if "EMAIL_EXISTS" in error_message:
                flash('This email is already registered.', 'error')
            elif "INVALID_EMAIL" in error_message:
                flash('Invalid email format.', 'error')
            elif "WEAK_PASSWORD" in error_message:
                flash('Password should be at least 6 characters.', 'error')
            elif "EMAIL_NOT_FOUND" in error_message or "INVALID_PASSWORD" in error_message:
                flash('Invalid email or password.', 'error')
            else:
                flash(f'An error occurred: {error_message}', 'error')
            return render_template('login.html', logged_in=session.get('logged_in', False))
    
    # GET request for login page
    return render_template('login.html', logged_in=session.get('logged_in', False))


@app.route('/set-id-token', methods=['POST'])
def set_id_token():
    """
    Endpoint to receive and verify the Firebase ID token from the client-side.
    """
    data = request.get_json()
    id_token = data.get('idToken')

    if not id_token:
        return jsonify({"status": "error", "message": "ID token missing"}), 400

    try:
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        email = decoded_token.get('email', 'N/A')

        session['id_token'] = id_token
        session['uid'] = uid
        session['email'] = email
        session['logged_in'] = True
        flash(f'Successfully logged in as {email}!', 'success')
        print(f"User {email} (UID: {uid}) logged in successfully.")
        return jsonify({"status": "success", "redirect": url_for('index')})
    except Exception as e:
        print(f"Error verifying ID token: {e}")
        session.pop('id_token', None)
        session.pop('uid', None)
        session.pop('email', None)
        session['logged_in'] = False
        return jsonify({"status": "error", "message": "Invalid or expired token"}), 401


@app.route('/logout')
def logout():
    session.pop('id_token', None)
    session.pop('uid', None)
    session.pop('email', None)
    session['logged_in'] = False
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)

