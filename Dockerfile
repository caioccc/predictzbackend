# Dockerfile para o backend Django
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python manage.py collectstatic --noinput
RUN python manage.py migrate
RUN python manage.py createsuperuser --noinput --username admin --email caiomarinho8@gmail.com
RUN python manage.py shell -c "from app.models import User; User.objects.filter(username='admin').update(is_staff=True, is_superuser=True)"

ENV PYTHONUNBUFFERED=1

CMD ["gunicorn", "app.wsgi:application", "--bind", "0.0.0.0:8000"]
