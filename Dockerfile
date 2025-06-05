
FROM python:3.13-alpine

WORKDIR /usr/src/app

COPY src/ .

COPY requirements.txt .

# Install ffmpeg and any needed packages specified in requirements.txt
RUN apt-get update && \\
    apt-get install -y ffmpeg tzdata && \\
    pip install --no-cache-dir -r requirements.txt


# Run the Flask app
CMD ["python", "main.py"]