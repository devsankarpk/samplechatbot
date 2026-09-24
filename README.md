# Doctor Appointment Chatbot

A console chatbot for booking doctor appointments. Chat in plain English; a
DeepInfra-hosted LLM (OpenAI-compatible API) drives the conversation and calls
tool functions to look up doctors, check availability, and book/view/cancel/
reschedule appointments in a MySQL database.

## Status: working, verified end-to-end

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Configure environment:
   ```
   cp env.example .env
   ```
   `.env` is already filled in for local dev (DeepInfra key, and MySQL user
   `chemapp` / database `chatbot`).
3. Make sure MySQL is running locally. On this machine MySQL comes from
   Anaconda (no Homebrew mysql formula installed), so start it with:
   ```
   /opt/anaconda3/bin/mysqld_safe --basedir=/opt/anaconda3 --datadir=/opt/anaconda3/data \
       --lc-messages-dir=/opt/anaconda3/share/mysql &
   ```
   (First-time-only: if `/opt/anaconda3/data` doesn't exist yet, initialize it
   first with `mysqld --initialize-insecure --basedir=/opt/anaconda3
   --datadir=/opt/anaconda3/data --user=$(whoami)`, then create the app user:
   `CREATE USER 'chemapp'@'localhost' IDENTIFIED BY 'ChemApp123!';
   CREATE DATABASE chatbot; GRANT ALL PRIVILEGES ON chatbot.* TO
   'chemapp'@'localhost';`)

   The app itself creates the `chatbot` database's tables and sample doctors
   automatically on first run — no manual schema SQL needed once the server
   and user above exist.
4. Run:
   ```
   python main.py
   ```

## Design notes

- **Patient identity**: on launch, the app asks for name + phone. A new phone
  number creates a patient record; an existing one is looked up. No password.
- **Time slots**: computed on the fly — weekdays, 9am–5pm, 30-minute
  increments, for the next 7 days — minus whatever's already booked. Not
  stored as their own table.
- **Tools available to the LLM**: `list_doctors`, `get_available_slots`,
  `book_appointment`, `list_my_appointments`, `cancel_appointment`,
  `reschedule_appointment`. The patient id is always bound from the current
  session server-side, never taken from the LLM, so one patient can't act on
  another's appointments (verified — see below).
- **Model**: `meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo` via DeepInfra
  (`DEEPINFRA_MODEL` in `.env`).

## Verification performed

Ran the app and the tool-calling loop directly against the live DeepInfra API
and a local MySQL instance:

- **Browse**: "What doctors do you have for dermatology?" → correctly called
  `list_doctors(specialty="dermatology")` and returned the 2 real seeded
  dermatologists (no hallucinated names).
- **Availability + booking**: asked for Dr. Priya Nair's slots on
  `2026-09-28`, got the real 16 open slots, booked `10:00`, then `list my
  appointments` showed it, `cancel that appointment` cancelled it, and a
  follow-up listing showed it as `cancelled`. DB rows matched the transcript
  exactly (checked via `SELECT` on `patients`/`doctors`/`appointments`).
- **Double-booking rejected**: a second patient trying to book the exact same
  doctor/slot Alice had just booked was correctly told no slots were
  available at that time.
- **Cross-patient protection**: a second patient calling
  `cancel_appointment` with the first patient's real appointment id got
  `"No appointment with id 2 found for this patient"` — confirmed the
  ownership scoping in `db.get_appointment`/`cancel_appointment` works.
- **Known limitation**: the 8B model's *relative* date reasoning is
  unreliable — asked "what slots does Dr. Priya Nair have next Monday?" on a
  Monday, it computed `2026-09-26` (a Saturday) instead of the correct
  `2026-09-28`, so it (correctly, given its own bad date) reported no slots.
  Explicit dates (`2026-09-28`) work reliably. If this matters for real use,
  switch `DEEPINFRA_MODEL` in `.env` to a larger model (e.g.
  `meta-llama/Llama-3.3-70B-Instruct`) for better date arithmetic.

Test data created during verification (extra patients/appointments) has been
deleted from the `chatbot` database, so it's back to just the 6 seeded
doctors and no patients/appointments.
