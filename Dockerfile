# Write Dockerfile to build a Docker image for the Python application
FROM python:3.11-slim
# Set the working directory
WORKDIR /app
# Copy the requirements file into the container
COPY requirements.txt .
# Install the required packages
RUN pip install --no-cache-dir -r requirements.txt
# Copy the application code into the container
COPY . .
# Expose the port the app runs on
# Command to run the application
CMD ["python", "app.py"]