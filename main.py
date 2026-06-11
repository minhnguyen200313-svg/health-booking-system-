import pandas as pd
import numpy as np
import datetime
from dateutil import parser
import uuid
import os

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

def calculate_distance(x1, y1, x2, y2):
    return np.sqrt((x1 - x2)**2 + (y1 - y2)**2)

def find_doctors_by_symptoms(doctors, symptoms):
    # symptoms is a list of strings
    matched_doctors = []
    for index, doctor in doctors.iterrows():
        doc_symptoms = [s.strip().lower() for s in str(doctor['symptoms_handled']).split(';')]
        # If any of the user's symptoms match the doctor's handled symptoms
        if any(symptom.lower() in doc_symptoms for symptom in symptoms):
            matched_doctors.append(doctor)
    
    if not matched_doctors:
        return pd.DataFrame(columns=doctors.columns)
    return pd.DataFrame(matched_doctors)

def find_best_clinic_and_doctor(patient, matched_doctors, clinics):
    best_options = []
    
    for _, doctor in matched_doctors.iterrows():
        clinic = clinics[clinics['clinic_id'] == doctor['clinic_id']].iloc[0]
        
        # Calculate distance
        dist = calculate_distance(patient['home_x'], patient['home_y'], clinic['location_x'], clinic['location_y'])
        
        best_options.append({
            'doctor_id': doctor['doctor_id'],
            'doctor_name': doctor['name'],
            'specialty': doctor['specialty'],
            'clinic_id': clinic['clinic_id'],
            'clinic_name': clinic['name'],
            'distance': dist,
            'base_fee': clinic['base_fee']
        })
        
    # Sort by distance, then fee
    best_options.sort(key=lambda x: (x['distance'], x['base_fee']))
    return best_options

def check_time_conflict(appointments, doctor_id, desired_time):
    # Parse desired time
    if isinstance(desired_time, str):
        desired_time = parser.parse(desired_time)
        
    if appointments.empty:
        return False
        
    doctor_appts = appointments[(appointments['doctor_id'] == doctor_id) & (appointments['status'] == 'Scheduled')].copy()
    if doctor_appts.empty:
        return False
        
    doctor_appts['datetime'] = pd.to_datetime(doctor_appts['datetime'])
    
    # Check if there is an appointment within 30 minutes
    time_window = pd.Timedelta(minutes=30)
    
    for _, appt in doctor_appts.iterrows():
        if abs(appt['datetime'] - desired_time) < time_window:
            return True # Conflict found
            
    return False

def suggest_alternative_times(appointments, doctor_id, desired_time):
    if isinstance(desired_time, str):
        desired_time = parser.parse(desired_time)
        
    alternatives = []
    
    # Look for next 3 available slots (30 min increments)
    check_time = desired_time + pd.Timedelta(minutes=30)
    while len(alternatives) < 3:
        if not check_time_conflict(appointments, doctor_id, check_time):
            # Also check if it's within working hours (e.g., 8:00 to 17:00)
            if 8 <= check_time.hour < 17:
                alternatives.append(check_time)
        check_time += pd.Timedelta(minutes=30)
        
    return alternatives

def send_email_reminder(patient, doctor_name, clinic_name, time):
    print(f"\n--- GỬI EMAIL NHẮC LỊCH ---")
    print(f"To: {patient['email']}")
    print(f"Subject: Xác nhận đặt lịch hẹn khám sức khỏe")
    print(f"Kính gửi {patient['name']},")
    print(f"Lịch hẹn khám của bạn đã được xác nhận thành công.")
    print(f"Bác sĩ: {doctor_name}")
    print(f"Phòng khám: {clinic_name}")
    print(f"Thời gian: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Vui lòng có mặt trước 15 phút.")
    print(f"---------------------------\n")

def book_appointment(patient_id, symptoms, desired_time_str):
    print(f"Yêu cầu đặt lịch cho Bệnh nhân: {patient_id}")
    print(f"Triệu chứng: {', '.join(symptoms)}")
    print(f"Thời gian mong muốn: {desired_time_str}")
    print("-" * 40)
    
    clinics, doctors, patients, appointments = load_data()
    
    if patient_id not in patients['patient_id'].values:
        print("Không tìm thấy bệnh nhân!")
        return
        
    patient = patients[patients['patient_id'] == patient_id].iloc[0]
    desired_time = parser.parse(desired_time_str)
    
    # 1. Choose specialty & doctor based on symptoms
    matched_doctors = find_doctors_by_symptoms(doctors, symptoms)
    if matched_doctors.empty:
        print("Không tìm thấy bác sĩ phù hợp với triệu chứng của bạn.")
        return
        
    # 2. Find convenient clinic (distance & fee)
    best_options = find_best_clinic_and_doctor(patient, matched_doctors, clinics)
    
    if not best_options:
        print("Không có phòng khám khả dụng.")
        return
        
    print("Các bác sĩ và phòng khám phù hợp (Sắp xếp theo khoảng cách gần nhất và phí):")
    for idx, opt in enumerate(best_options):
        print(f"{idx + 1}. Bác sĩ {opt['doctor_name']} ({opt['specialty']}) - {opt['clinic_name']}")
        print(f"   Khoảng cách: {opt['distance']:.2f} đv - Phí khám: {opt['base_fee']} VNĐ")
        
    # Pick the best option
    selected_option = best_options[0]
    print(f"\nĐã tự động chọn lựa chọn tốt nhất: Bác sĩ {selected_option['doctor_name']} tại {selected_option['clinic_name']}")
    
    # 3. Automatic conflict detection
    is_conflict = check_time_conflict(appointments, selected_option['doctor_id'], desired_time)
    
    if is_conflict:
        print(f"\nPHÁT HIỆN TRÙNG LỊCH: Bác sĩ đã có lịch hẹn vào khoảng thời gian {desired_time_str}.")
        alternatives = suggest_alternative_times(appointments, selected_option['doctor_id'], desired_time)
        print("Đề xuất các khung giờ thay thế:")
        for alt in alternatives:
            print(f" - {alt.strftime('%Y-%m-%d %H:%M:%S')}")
            
        # Simulating user selecting the first alternative
        final_time = alternatives[0]
        print(f"Hệ thống tự động chọn khung giờ thay thế đầu tiên: {final_time.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        final_time = desired_time
        print("\nKhông trùng lịch. Tiến hành đặt lịch.")
        
    # 4. Book appointment
    new_appt_id = f"A{len(appointments) + 1}"
    new_appointment = pd.DataFrame([{
        'appointment_id': new_appt_id,
        'patient_id': patient_id,
        'doctor_id': selected_option['doctor_id'],
        'clinic_id': selected_option['clinic_id'],
        'datetime': final_time.strftime('%Y-%m-%d %H:%M:%S'),
        'status': 'Scheduled'
    }])
    
    appointments = pd.concat([appointments, new_appointment], ignore_index=True)
    save_appointments(appointments)
    
    print("\nĐẶT LỊCH THÀNH CÔNG!")
    
    # 5. Reminder
    send_email_reminder(patient, selected_option['doctor_name'], selected_option['clinic_name'], final_time)

if __name__ == '__main__':
    # Test case 1: Normal booking
    print("\n========== TEST CASE 1: BÌNH THƯỜNG ==========")
    book_appointment('P1', ['sốt', 'đau đầu'], '2026-06-15 08:00:00')
    
    # Test case 2: Conflict booking
    print("\n========== TEST CASE 2: TRÙNG LỊCH ==========")
    # Book exactly at the time P2 booked D2 (which is A1: 2026-06-12 09:00:00)
    # We will simulate a patient wanting doctor D2 by querying 'tiêu chảy trẻ em'
    book_appointment('P1', ['tiêu chảy trẻ em'], '2026-06-12 09:10:00')
