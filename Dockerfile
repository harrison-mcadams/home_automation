FROM python:3.9-slim

WORKDIR /app

# Install dependencies
RUN pip install flask pyserial

# Copy the bridge service script
COPY rf_bridge_service.py .

# We don't copy remote_codes.json here because we will mount it 
# efficiently in docker-compose to allow editing without rebuilding.

EXPOSE 5000

CMD ["python", "rf_bridge_service.py"]
