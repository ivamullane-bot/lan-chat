FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 3333

# Volume for persistent data
VOLUME ["/app/data"]

CMD ["python", "app.py"]
