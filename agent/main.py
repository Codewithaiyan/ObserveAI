"""
ObserveAI Agent - Main FastAPI Application
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from typing import List, Dict, Any
from datetime import datetime
import asyncio

from config.settings import settings
from monitors.log_monitor import monitor
from clients.elasticsearch_client import es_client
from models.incident import Incident, MonitoringState
from utils.logger import logger


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan"""
    # Startup
    logger.info("Starting ObserveAI Agent", version=settings.app_version)
    
    # Start monitoring in background
    monitoring_task = asyncio.create_task(monitor.start())
    
    logger.info("Agent started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down ObserveAI Agent")
    await monitor.stop()
    monitoring_task.cancel()
    await es_client.close()
    logger.info("Agent stopped")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-Powered DevOps Observability Agent",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    state = monitor.get_state()
    
    # Check Elasticsearch connectivity
    es_healthy = await es_client.health_check()
    
    health_status = {
        "status": "healthy" if es_healthy and state.status == "healthy" else "degraded",
        "elasticsearch": "connected" if es_healthy else "disconnected",
        "monitor_status": state.status,
        "uptime_seconds": (datetime.utcnow() - state.last_check).total_seconds(),
        "timestamp": datetime.utcnow().isoformat()
    }
    
    status_code = 200 if health_status["status"] == "healthy" else 503
    return JSONResponse(content=health_status, status_code=status_code)


@app.get("/api/status")
async def get_status() -> MonitoringState:
    """Get detailed monitoring status"""
    state = monitor.get_state()
    logger.info("Status requested", status=state.status)
    return state


@app.get("/api/incidents")
async def get_incidents(limit: int = 10) -> List[Incident]:
    """Get recent incidents"""
    incidents = monitor.get_recent_incidents(limit=limit)
    logger.info("Incidents retrieved", count=len(incidents))
    return incidents


@app.get("/api/incidents/{incident_id}")
async def get_incident(incident_id: str) -> Incident:
    """Get specific incident by ID"""
    incidents = monitor.get_recent_incidents(limit=100)
    
    for incident in incidents:
        if incident.id == incident_id:
            logger.info("Incident retrieved", incident_id=incident_id)
            return incident
    
    logger.warning("Incident not found", incident_id=incident_id)
    raise HTTPException(status_code=404, detail="Incident not found")


@app.get("/api/logs/search")
async def search_logs(
    query: str = None,
    level: str = None,
    service: str = None,
    limit: int = 100
) -> Dict[str, Any]:
    """Search logs with filters"""
    
    # Build Elasticsearch query
    must_clauses = []
    
    if query:
        must_clauses.append({"match": {"message": query}})
    
    if level:
        must_clauses.append({"match": {"level": level}})
    
    if service:
        must_clauses.append({"match": {"service": service}})
    
    # Add time range (last 1 hour)
    must_clauses.append({
        "range": {
            "@timestamp": {
                "gte": "now-1h"
            }
        }
    })
    
    es_query = {
        "bool": {
            "must": must_clauses
        }
    } if must_clauses else {"match_all": {}}
    
    # Search logs
    logs = await es_client.search_logs(query=es_query, size=limit)
    
    logger.info("Logs searched", count=len(logs), filters={"query": query, "level": level, "service": service})
    
    return {
        "count": len(logs),
        "logs": logs,
        "filters": {
            "query": query,
            "level": level,
            "service": service,
            "limit": limit
        }
    }


@app.get("/api/logs/errors")
async def get_recent_errors(minutes: int = 5, limit: int = 50) -> Dict[str, Any]:
    """Get recent error logs"""
    errors = await es_client.get_recent_errors(minutes=minutes, size=limit)
    
    logger.info("Recent errors retrieved", count=len(errors), minutes=minutes)
    
    return {
        "count": len(errors),
        "time_range": f"last {minutes} minutes",
        "errors": errors
    }


@app.get("/api/logs/aggregate")
async def aggregate_logs(
    field: str = "level",
    size: int = 10
) -> Dict[str, Any]:
    """Aggregate logs by field"""
    
    aggregation = await es_client.aggregate_by_field(field=field, size=size)
    
    logger.info("Logs aggregated", field=field, buckets=len(aggregation))
    
    return {
        "field": field,
        "aggregation": aggregation,
        "total_buckets": len(aggregation)
    }


@app.post("/api/analyze")
async def trigger_analysis(background_tasks: BackgroundTasks) -> Dict[str, str]:
    """Manually trigger log analysis"""
    
    logger.info("Manual analysis triggered")
    
    # Run check immediately in background
    background_tasks.add_task(monitor._check_logs)
    
    return {
        "status": "analysis_triggered",
        "message": "Log analysis started in background"
    }


@app.get("/api/stats")
async def get_statistics() -> Dict[str, Any]:
    """Get overall statistics"""
    
    state = monitor.get_state()
    
    # Get total log count
    total_logs = await es_client.count_logs()
    
    # Get error count (last 24h)
    error_count = await es_client.count_logs(
        query={
            "bool": {
                "must": [
                    {"match": {"message": "ERROR"}},
                    {"range": {"@timestamp": {"gte": "now-24h"}}}
                ]
            }
        }
    )
    
    # Get log counts by level
    level_counts = await es_client.aggregate_by_field("level")
    
    stats = {
        "monitoring": {
            "status": state.status,
            "logs_processed": state.logs_processed,
            "anomalies_detected": state.anomalies_detected,
            "incidents_created": state.incidents_created,
            "last_check": state.last_check.isoformat()
        },
        "logs": {
            "total_count": total_logs,
            "error_count_24h": error_count,
            "by_level": level_counts
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    logger.info("Statistics retrieved")
    
    return stats


# Webhook endpoint for Prometheus Alertmanager (future use)
@app.post("/api/webhook/alertmanager")
async def alertmanager_webhook(alert: Dict[str, Any]):
    """Receive alerts from Prometheus Alertmanager"""
    
    logger.info("Alert received from Alertmanager", alert=alert)
    
    # TODO: Process alert and trigger analysis
    # This will be implemented in Day 8
    
    return {"status": "received"}


if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting ObserveAI Agent server")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="info"
    )
