FROM python:3.10-slim

# Install locale support
RUN apt-get update && \
    apt-get install -y locales && \
    sed -i '/id_ID.UTF-8/s/^# //g' /etc/locale.gen && \
    locale-gen

ENV LANG=id_ID.UTF-8
ENV LANGUAGE=id_ID:en
ENV LC_ALL=id_ID.UTF-8

# Sisa Dockerfile kamu
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["python", "app.py"]
