from flask import Flask, render_template, request, redirect, url_for, session, flash
import pandas as pd
import numpy as np
import datetime
from dateutil import parser
import os
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = 'super-secret-key-for-health-system'

DATA_DIR = 'data'
CLINICS_FILE = os.path.join(DATA_DIR, 'clinics.csv')
DOCTORS_FILE = os.path.join(DATA_DIR, 'doctors.csv')
PATIENTS_FILE = os.path.join(DATA_DIR, 'patients.csv')
APPOINTMENTS_FILE = os.path.join(DATA_DIR, 'appointments.csv')

def load_data():
    clinics = pd.read_csv(CLINICS_FILE)
    doctors = pd.read_csv(DOCTORS_FILE)
    patients = pd.read_csv(PATIENTS_FILE)
    if os.path.exists(APPOINTMENTS_FILE):
        appointments = pd.read_csv(APPOINTMENTS_FILE)
    else:
        appointments = pd.DataFrame(columns=['appointment_id', 'patient_id', 'doctor_id', 'clinic_id', 'datetime', 'status'])
    return clinics, doctors, patients, appointments

def save_appointments(appointments):
    appointments.to_csv(APPOINTMENTS_FILE, index=False)

def save_patients(patients):
    patients.to_csv(PATIENTS_FILE, index=False)

def calculate_distance(x1, y1, x2, y2):
    return np.sqrt((x1 - x2)**2 + (y1 - y2)**2)

# Auth Decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'patient_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        _, _, patients, _ = load_data()
        
        user = patients[patients['email'] == email]
        if not user.empty:
            stored_password = str(user.iloc[0]['password'])
            if check_password_hash(stored_password, password):
                session['patient_id'] = user.iloc[0]['patient_id']
                session['patient_name'] = user.iloc[0]['name']
                return redirect(url_for('index'))
        
        return render_template('login.html', error="Email hoặc mật khẩu không đúng.")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        home_x = int(request.form.get('home_x'))
        home_y = int(request.form.get('home_y'))
        password = request.form.get('password')
        
        _, _, patients, _ = load_data()
        
        if email in patients['email'].values:
            return "Email đã tồn tại!"
            
        new_id = f"P{len(patients) + 1}"
        hashed_password = generate_password_hash(password)
        
        new_patient = pd.DataFrame([{
            'patient_id': new_id, 'name': name, 'email': email,
            'home_x': home_x, 'home_y': home_y, 'password': hashed_password
        }])
        
        patients = pd.concat([patients, new_patient], ignore_index=True)
        save_patients(patients)
        
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    clinics, doctors, _, appointments = load_data()
    
    # Get unique specialties for the dropdown
    specialties = sorted(doctors['specialty'].unique().tolist())
    
    user_appts = []
    if not appointments.empty:
        # Filter for current user and status 'Scheduled'
        my_appts = appointments[
            (appointments['patient_id'] == session['patient_id']) & 
            (appointments['status'] == 'Scheduled')
        ].copy()
        
        # Merge with doctors and clinics for better display
        if not my_appts.empty:
            for _, row in my_appts.iterrows():
                doc = doctors[doctors['doctor_id'] == row['doctor_id']].iloc[0]
                clinic = clinics[clinics['clinic_id'] == row['clinic_id']].iloc[0]
                user_appts.append({
                    'id': row['appointment_id'],
                    'doctor': doc['name'],
                    'clinic': clinic['name'],
                    'time': row['datetime']
                })
                
    return render_template('index.html', 
                           patient_name=session['patient_name'], 
                           user_appts=user_appts,
                           specialties=specialties)

@app.route('/cancel/<appt_id>', methods=['POST'])
@login_required
def cancel(appt_id):
    _, _, _, appointments = load_data()
    if not appointments.empty:
        # Find the appointment and update status
        idx = appointments[
            (appointments['appointment_id'] == appt_id) & 
            (appointments['patient_id'] == session['patient_id'])
        ].index
        
        if not idx.empty:
            appointments.at[idx[0], 'status'] = 'Cancelled'
            save_appointments(appointments)
            
    return redirect(url_for('index'))

@app.route('/book', methods=['POST'])
@login_required
def book():
    patient_id = session['patient_id']
    selected_specialty = request.form.get('specialty')
    symptoms_raw = request.form.get('symptoms', '')
    desired_time_str = request.form.get('desired_time')
    
    clinics, doctors, patients, appointments = load_data()
    patient = patients[patients['patient_id'] == patient_id].iloc[0]
    desired_time = parser.parse(desired_time_str)
    
    # 1. Matching Logic: Priority to Specialty, then Symptoms
    matched_doctors_df = pd.DataFrame()
    
    if selected_specialty and selected_specialty != 'Tất cả':
        matched_doctors_df = doctors[doctors['specialty'] == selected_specialty]
    elif symptoms_raw:
        symptoms = [s.strip() for s in symptoms_raw.split(',')]
        # Reuse logic to find by symptoms
        matched_list = []
        for _, doc in doctors.iterrows():
            doc_syms = [s.strip().lower() for s in str(doc['symptoms_handled']).split(';')]
            if any(s.strip().lower() in doc_syms for s in symptoms):
                matched_list.append(doc)
        if matched_list:
            matched_doctors_df = pd.DataFrame(matched_list)
    
    if matched_doctors_df.empty:
        specialties = sorted(doctors['specialty'].unique().tolist())
        return render_template('index.html', 
                               patient_name=session['patient_name'],
                               specialties=specialties,
                               result={'type': 'error', 'message': 'Không tìm thấy bác sĩ phù hợp với yêu cầu của bạn.'})
    
    # 2. Find best clinic (closest & cheapest)
    best_options = []
    for _, doc in matched_doctors_df.iterrows():
        clinic = clinics[clinics['clinic_id'] == doc['clinic_id']].iloc[0]
        dist = calculate_distance(patient['home_x'], patient['home_y'], clinic['location_x'], clinic['location_y'])
        best_options.append({
            'doctor_id': doc['doctor_id'], 'doctor_name': doc['name'],
            'clinic_id': clinic['clinic_id'], 'clinic_name': clinic['name'],
            'distance': dist, 'base_fee': clinic['base_fee']
        })
    best_options.sort(key=lambda x: (x['distance'], x['base_fee']))
    selected = best_options[0]
    
    # 3. Conflict check
    is_conflict = False
    if not appointments.empty:
        doctor_appts = appointments[(appointments['doctor_id'] == selected['doctor_id']) & (appointments['status'] == 'Scheduled')].copy()
        if not doctor_appts.empty:
            doctor_appts['datetime'] = pd.to_datetime(doctor_appts['datetime'])
            for _, appt in doctor_appts.iterrows():
                if abs(appt['datetime'] - desired_time) < pd.Timedelta(minutes=30):
                    is_conflict = True
                    break
                    
    final_time = desired_time
    result = {'type': 'success', 'message': 'Đặt lịch thành công!'}
    
    if is_conflict:
        # Suggest alternative
        final_time = desired_time + pd.Timedelta(minutes=30)
        result = {'type': 'warning', 'message': 'Bác sĩ đã có lịch! Hệ thống tự động dời sang khung giờ tiếp theo.'}
        
    # 4. Save
    new_appt = pd.DataFrame([{
        'appointment_id': f"A{len(appointments)+1}", 'patient_id': patient_id,
        'doctor_id': selected['doctor_id'], 'clinic_id': selected['clinic_id'],
        'datetime': final_time.strftime('%Y-%m-%d %H:%M:%S'), 'status': 'Scheduled'
    }])
    appointments = pd.concat([appointments, new_appt], ignore_index=True)
    save_appointments(appointments)
    
    result['appointment'] = {
        'doctor_name': selected['doctor_name'], 'clinic_name': selected['clinic_name'],
        'time': final_time.strftime('%Y-%m-%d %H:%M:%S'), 'fee': selected['base_fee']
    }
    
    # Reload data for display
    clinics, doctors, _, appointments = load_data()
    specialties = sorted(doctors['specialty'].unique().tolist())
    
    user_appts = []
    if not appointments.empty:
        my_appts = appointments[
            (appointments['patient_id'] == session['patient_id']) & 
            (appointments['status'] == 'Scheduled')
        ].copy()
        if not my_appts.empty:
            for _, row in my_appts.iterrows():
                doc = doctors[doctors['doctor_id'] == row['doctor_id']].iloc[0]
                clinic = clinics[clinics['clinic_id'] == row['clinic_id']].iloc[0]
                user_appts.append({
                    'id': row['appointment_id'], 'doctor': doc['name'],
                    'clinic': clinic['name'], 'time': row['datetime']
                })

    return render_template('index.html', 
                           patient_name=session['patient_name'], 
                           result=result, 
                           specialties=specialties,
                           user_appts=user_appts)

if __name__ == '__main__':
    # Use the port assigned by the hosting provider (default to 5050 for local)
    port = int(os.environ.get('PORT', 5050))
    app.run(debug=False, host='0.0.0.0', port=port)
