FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements dulu (biar cache docker kepake)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy semua source code
COPY . .

EXPOSE 9000

# Run app pakai uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]
