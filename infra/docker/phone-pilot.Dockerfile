FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY src /app/src
COPY backend /app/backend
COPY scripts/start_phone_pilot.py /app/scripts/start_phone_pilot.py
RUN useradd --create-home pilot && chown -R pilot:pilot /app
USER pilot
EXPOSE 8765
CMD ["python", "scripts/start_phone_pilot.py"]
