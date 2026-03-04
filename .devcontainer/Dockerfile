FROM python:3.10-slim

WORKDIR /app

# Copy dependency list and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy everything else
COPY . .

# Unbuffered output
CMD ["python", "-u", "main.py"]
