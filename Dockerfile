FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy file requirements dan install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Salin semua file ke dalam container
COPY . .

# Jalankan aplikasi Flask
ENV FLASK_APP=app.py
CMD ["python", "app.py"]
