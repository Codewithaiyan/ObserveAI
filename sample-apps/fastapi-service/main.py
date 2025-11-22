"""
Sample FastAPI microservice with structured logging and metrics
This service simulates a real production API
"""
from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, Histogram, generate_latest
from fastapi.responses import Response
import logging
import json
import random
import time
from datetime import datetime

# Configure structured logging (JSON format)
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="ObserveAI Sample Service", version="1.0.0")

# Prometheus metrics
request_count = Counter(
    'http_requests_total', 
    'Total HTTP requests', 
    ['method', 'endpoint', 'status']
)
request_duration = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)
error_count = Counter(
    'application_errors_total',
    'Total application errors',
    ['error_type']
)

def log_structured(level: str, message: str, **kwargs):
    """Create structured JSON logs"""
    log_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "level": level,
        "message": message,
        "service": "api-service",
        **kwargs
    }
    logger.info(json.dumps(log_data))

@app.get("/")
async def root():
    """Health check endpoint"""
    log_structured("INFO", "Health check accessed")
    request_count.labels(method="GET", endpoint="/", status="200").inc()
    return {"status": "healthy", "service": "observeai-sample"}

@app.get("/api/users/{user_id}")
async def get_user(user_id: int):
    """Simulate user fetch with random failures"""
    start_time = time.time()
    
    try:
        # Simulate processing time
        time.sleep(random.uniform(0.1, 0.5))
        
        # Randomly fail 10% of requests
        if random.random() < 0.1:
            log_structured(
                "ERROR",
                "User not found",
                user_id=user_id,
                error_type="NotFound"
            )
            error_count.labels(error_type="NotFound").inc()
            request_count.labels(method="GET", endpoint="/api/users", status="404").inc()
            raise HTTPException(status_code=404, detail="User not found")
        
        # Success case
        log_structured(
            "INFO",
            "User fetched successfully",
            user_id=user_id,
            response_time=time.time() - start_time
        )
        request_count.labels(method="GET", endpoint="/api/users", status="200").inc()
        
        return {
            "user_id": user_id,
            "name": f"User {user_id}",
            "email": f"user{user_id}@example.com"
        }
    
    finally:
        duration = time.time() - start_time
        request_duration.labels(method="GET", endpoint="/api/users").observe(duration)

@app.get("/api/slow")
async def slow_endpoint():
    """Simulate slow endpoint (for testing latency alerts)"""
    log_structured("WARNING", "Slow endpoint accessed")
    time.sleep(random.uniform(2, 5))  # 2-5 second delay
    request_count.labels(method="GET", endpoint="/api/slow", status="200").inc()
    return {"message": "This was slow"}

@app.get("/api/error")
async def error_endpoint():
    """Simulate server error (for testing error alerts)"""
    log_structured(
        "ERROR",
        "Internal server error triggered",
        error_type="InternalServerError",
        stack_trace="Simulated error for testing"
    )
    error_count.labels(error_type="InternalServerError").inc()
    request_count.labels(method="GET", endpoint="/api/error", status="500").inc()
    raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/cpu-intensive")
async def cpu_intensive():
    """Simulate CPU-intensive task"""
    log_structured("INFO", "CPU-intensive task started")
    
    # Simulate CPU load
    result = 0
    for i in range(1000000):
        result += i ** 2
    
    request_count.labels(method="GET", endpoint="/api/cpu-intensive", status="200").inc()
    return {"result": result, "message": "CPU task completed"}

@app.get("/metrics")
async def metrics():
    """Expose Prometheus metrics"""
    return Response(content=generate_latest(), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    log_structured("INFO", "Starting ObserveAI sample service", port=8000)
    uvicorn.run(app, host="0.0.0.0", port=8000)
