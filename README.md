# GameDayPicks

NFL pick'em site built with Django. Players pick winners each week, compete on
leaderboards, add friends, and issue challenges.

## Setup
    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt
    copy .env.example .env   # then fill in your own values
    python manage.py migrate
    python manage.py runserver

## Tests
    python manage.py test 
