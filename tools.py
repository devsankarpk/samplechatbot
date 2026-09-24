import datetime

import database

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_doctors",
            "description": "List of doctors, optinally filtered by specialty (e.g. 'Cardiology')",
            "parameters":{
                "type": "object",
                "properties": {
                    "specialty": {
                        "type": "string",
                        "description": "specialty to filter by, omit to list all doctors."
                    }
                },
                "required":[],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_available_slots",
            "description": "Get available appoinment time slots for a specific doctor,"
            "optionally restricted to one date. Slots are 30 minutes increments,"
            "weekdays 9am - 5pm, for the next 7 days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "doctor_id": {"type": "integer", "description": "The doctor's id"},
                    "date": {"type": "string", "description": "Optional date in YYYY-MM-DD format to filter to a single"}
                },
                "required": ["doctor_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book an appointment for current patient with a doctor at a specific date/time."
            "The slot must currently be available.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {"type": "integer", "description": "The patient's id."},
                    "doctor_id": {"type": "integer", "description": "The doctor's id."},
                    "appointment_time": {"type": "string", "description": "Date and time in 'YYYY-MM-DD HH:MM' 24-hour format."}
                },
                "required": ["patient_id", "doctor_id", "appointment_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_appointment",
            "description": "List the current patient's appointments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {"type": "integer", "description": "The patient's id."},
                    "status": {
                        "type": "string",
                        "enum": ["booked", "cancelled"],
                        "description": "Optional status filter. Omit to list all."
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_appointment",
            "description": "Cancel the current patient's own appointment by its id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {"type": "integer", "description": "The patient's id."},
                    "appointment_id": {"type": "integer", "description": "The appointment id to cancel."}
                },
                "required": ["patient_id", "appointment_id"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reschedule_appointment",
            "description": "Move one of the current patient's own appointment to a new date/time."
            "The new slot must be available.",
            "parameters": {
                "type": "object",
                "properties":{
                    "patient_id": {"type": "integer", "description": "The patient's id."},
                    "appointment_id": {"type": "integer", "description": "The appointment id to reschedule."},
                    "new_time":{"type": "string", "description": "New date and time in 'YYYY-MM-DD HH:MM' 24-hour format."}
                },
                "required": ["patient_id", "appointment_id", "new_time"]
            }
        },
    }
]

def _parse_datetime(value):
    return datetime.datetime.strptime(value.strip(), "%Y-%m-%d %H:%M")

def _parse_date(value):
    return datetime.datetime.strptime(value.strip(), "%Y-%m-%d").date()

def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M (%A)")

def tool_list_doctors(conn, speciality = None):
    rows = database.list_doctors(conn, speciality)
    if not rows:
        return {"doctors": [], "message": "No doctors found matching that specialty."}
    return {"doctors": rows}

def tool_get_available_slots(conn, doctor_id, date = None):
    doctor = database.get_doctor(conn = conn, doctor_id = doctor_id)
    if doctor is None:
        return {"error": f"No doctor with id {doctor_id}."}
    parsed_date = None

    if date:
        try:
            parsed_date = _parse_date(date)
        except:
            return {"error": f"Invalid date format {date!r}, expected YYYY-MM-DD."}
    slots = database.get_available_slots(conn = conn, doctor_id = doctor_id, date = parsed_date)
    return {
        "doctor": doctor,
        "available_slots": [_fmt(s) for s in slots[:40]],
        "note": "Showing up to 40 upcoming slots." if len(slots) > 40 else None
    }

def tool_book_appointment(conn, patient_id, doctor_id, appointment_time):
    doctor = database.get_doctor(conn = conn, doctor_id = doctor_id)
    if doctor is None:
        return {"error": f"No doctor with id {doctor_id}."}
    parsed_date = None

    try:
        parsed_date = _parse_datetime(appointment_time)
    except:
        return {"error": f"Invalid date format {appointment_time!r}, expected YYYY-MM-DD."}

    if parsed_date <= datetime.datetime.now():
        return {"error": "Can't book an appointment in the past."}

    if not database.is_slot_available(conn = conn, doctor_id = doctor_id, when = parsed_date):
        return {"error": f"{_fmt(parsed_date)} is not available for {doctor['name']}. Please choose another slot."}

    appointment_id = database.book_appointment(conn = conn, patient_id = patient_id, doctor_id = doctor_id, when = parsed_date)

    return {
        "success": True,
        "appointment_id": appointment_id,
        "doctor": doctor['name'],
        "appointment_time": _fmt(parsed_date)
    }

def tool_list_my_appointments(conn, patient_id, status = None):
    rows = database.list_appointments(conn = conn, patient_id = patient_id, status = status)

    if not rows:
        return {"appointments": [], "message": "No appointment fount."}

    for r in rows:
        r["appointment_time"] = _fmt(r["appointment_time"])

    return {"appointments": rows}

def tool_cancel_appointment(conn, patient_id, appointment_id):
    ok, reason = database.cancel_appointment(conn = conn, appointment_id = appointment_id, patient_id = patient_id)
    if ok:
        return {"success": True, "appointment_id": appointment_id}
    
    messages = {
        "not_found": f"No appointment with id {appointment_id} found for this patient.",
        "already_cancelled": f"Appointment {appointment_id} is already cancelled.",
    }
    return {"success": False, "error": messages.get(reason, reason)}

def tool_reschedule_appointment(conn, patient_id, appointment_id, new_time):
    try:
        parsed_date = _parse_datetime(new_time)
    except ValueError:
        return {"error": f"Invalid new_time {new_time!r}, expected 'YYYY-MM-DD HH:MM'."}

    if parsed_date <= datetime.datetime.now():
        return {"error": "Can't reschedule to a time in the past."}

    ok, reason = database.reschedule_appointment(conn = conn, appointment_id = appointment_id, patient_id = patient_id, new_when = parsed_date)
    if ok:
        return {"succes": True,  "appointment_id": appointment_id, "new_time": _fmt(parsed_date)}

    messages = {
        "not_found": f"No appointment with id {appointment_id} found for this patient.",
        "not_active": f"Appointment {appointment_id} is not active (already cancelled).",
        "slot_taken": f"{_fmt(parsed_date)} is not available. Please choose another slot.",
    }
    return {"success": False, "error": messages.get(reason, reason)}


DISPATCH = {
    "list_doctors": tool_list_doctors,
    "get_available_slots": tool_get_available_slots,
    "book_appointment": tool_book_appointment,
    "list_appointment": tool_list_my_appointments,
    "cancel_appointment": tool_cancel_appointment,
    "reschedule_appointment": tool_reschedule_appointment,
}