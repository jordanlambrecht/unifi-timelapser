# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /usr/src/app

# Copy the current directory contents into the container at /usr/src/app
COPY . .

# Install ffmpeg and any needed packages specified in requirements.txt
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    pip install --no-cache-dir -r requirements.txt


# Run the Flask app
CMD ["gunicorn", "-b", "0.0.0.0:8080", "capture_images:app"]