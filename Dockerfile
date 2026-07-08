FROM python:3.11-slim

WORKDIR /app

# Copy the requirements file
COPY backend/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend code
COPY backend/ /app/backend/

# Copy the dataset so it's bundled in the container (Alternatively, use COS in production)
COPY data/ /app/data/

# Expose the port FastAPI runs on
EXPOSE 8000

# Run the FastAPI server
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
