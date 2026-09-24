import sys

import database
import llm_client

def prompt_patient_identity(conn):
    print("\nSet up")
    while True:
        name = input("Your name: ").strip()
        if name:
            break
        print(" Please enter name.")

    while True:
        phone = input("Your phone number: ").strip()
        if phone:
            break
        print(" Please enter phone number")

    patient, created = database.get_or_create_patient(conn = conn, name = name, phone = phone)
    if created:
        print(f"Welcome {patient['name']}! You are registered.")
    else:
        print(f"Welcome back, {patient['name']}!")

    return patient

def chat_loop(conn, patient):
    message = [{"role": "system", "content": llm_client.build_system_prompt(patient_name = patient["name"], patient_id = patient["id"])}]

    print("\nYou can ask about doctors, availability, or book/view/cancel/reschedule "
          "appointments. Type 'exit' or 'quit' to leave.\n")

    while True:
        try:
            user_input = input(f"{patient['name']}>").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            return

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print("\nGoodbye! Take care.")
            return

        message.append({"role": "user", "content": user_input})
        try:
            reply = llm_client.call_tools(conn = conn, patient = patient, messages = message)
        except llm_client.UpstreamError as e:
            print(f"Assistant: {e.message}")
            continue

        print(f"Assistant: {reply}")

def main():
    print(" Doctor Appointment Chatbot")

    print("\nConnecting to database")
    conn = database.init_database()
    if conn is None:
        print("\nCould not start: database is not available. See errors above.")
        sys.exit(1)

    try:
        patient = prompt_patient_identity(conn = conn)
        chat_loop(conn = conn, patient = patient)
    finally:
        conn.close()

if __name__ == "__main__":
    main()