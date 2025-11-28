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


@app.get("/api/advanced/timeseries")
async def get_timeseries_data() -> Dict[str, Any]:
    """Get time-series analysis data"""
    from monitors.advanced.timeseries_analyzer import ts_analyzer
    
    return {
        "error_rate_history": list(ts_analyzer.error_rate_history),
        "log_volume_history": list(ts_analyzer.log_volume_history),
        "window_size": ts_analyzer.window_size,
        "data_points": len(ts_analyzer.error_rate_history)
    }


@app.get("/api/advanced/patterns")
async def detect_patterns() -> Dict[str, Any]:
    """Manually trigger pattern detection"""
    from monitors.advanced.timeseries_analyzer import ts_analyzer
    
    anomalies = ts_analyzer.analyze_patterns()
    
    return {
        "patterns_detected": len(anomalies),
        "patterns": [
            {
                "type": a.anomaly_type,
                "severity": a.severity,
                "score": a.score,
                "description": a.description,
                "metrics": a.metrics
            }
            for a in anomalies
        ]
    }


@app.get("/api/advanced/correlations")
async def get_correlations() -> Dict[str, Any]:
    """Get correlation analysis results"""
    
    # Get recent logs
    logs = await es_client.search_logs(
        query={"range": {"@timestamp": {"gte": "now-10m"}}},
        size=500
    )
    
    from monitors.advanced.correlation_engine import correlation_engine
    
    correlations = correlation_engine.analyze_correlations(logs)
    
    return {
        "correlations_found": len(correlations),
        "logs_analyzed": len(logs),
        "correlations": [
            {
                "type": c.anomaly_type,
                "severity": c.severity,
                "score": c.score,
                "description": c.description,
                "metrics": c.metrics
            }
            for c in correlations
        ]
    }


@app.get("/api/ml/baseline")
async def get_baseline_info() -> Dict[str, Any]:
    """Get adaptive baseline information"""
    from monitors.advanced.adaptive_baseline import adaptive_baseline
    
    summary = adaptive_baseline.get_summary()
    confidence = adaptive_baseline.get_confidence()
    
    # Get current expected baseline
    expected = adaptive_baseline.get_expected_baseline()
    
    return {
        "confidence": confidence,
        "total_samples": summary['total_samples'],
        "history_size": summary['history_size'],
        "hours_with_data": summary['hours_with_data'],
        "days_with_data": summary['days_with_data'],
        "current_expected_baseline": {
            "error_rate": {
                "mean": expected['error_rate']['mean'],
                "std": expected['error_rate']['std'],
                "samples": expected['error_rate']['samples']
            },
            "log_volume": {
                "mean": expected['log_volume']['mean'],
                "std": expected['log_volume']['std'],
                "samples": expected['log_volume']['samples']
            }
        },
        "overall_baseline": summary['overall']
    }


@app.get("/api/ml/hourly-patterns")
async def get_hourly_patterns() -> Dict[str, Any]:
    """Get learned hourly patterns"""
    from monitors.advanced.adaptive_baseline import adaptive_baseline
    
    patterns = {}
    
    for hour in range(24):
        baseline = adaptive_baseline.hourly_baselines[hour]
        if baseline['error_rate']['samples'] >= 5:
            patterns[hour] = {
                "error_rate_mean": baseline['error_rate']['mean'],
                "log_volume_mean": baseline['log_volume']['mean'],
                "samples": baseline['error_rate']['samples']
            }
    
    return {
        "patterns": patterns,
        "hours_learned": len(patterns),
        "current_hour": datetime.utcnow().hour
    }


@app.post("/api/ml/check-anomaly")
async def check_if_anomalous(
    error_rate: float,
    log_volume: int
) -> Dict[str, Any]:
    """Manually check if values are anomalous"""
    from monitors.advanced.adaptive_baseline import adaptive_baseline
    
    is_anomalous, details = adaptive_baseline.is_anomalous(
        error_rate=error_rate,
        log_volume=log_volume
    )
    
    return {
        "is_anomalous": is_anomalous,
        "details": details,
        "confidence": adaptive_baseline.get_confidence()
    }


@app.get("/api/ml/baseline")
async def get_baseline_info() -> Dict[str, Any]:
    """Get adaptive baseline information"""
    from monitors.advanced.adaptive_baseline import adaptive_baseline
    
    summary = adaptive_baseline.get_summary()
    confidence = adaptive_baseline.get_confidence()
    
    # Get current expected baseline
    expected = adaptive_baseline.get_expected_baseline()
    
    return {
        "confidence": confidence,
        "total_samples": summary['total_samples'],
        "history_size": summary['history_size'],
        "hours_with_data": summary['hours_with_data'],
        "days_with_data": summary['days_with_data'],
        "current_expected_baseline": {
            "error_rate": {
                "mean": expected['error_rate']['mean'],
                "std": expected['error_rate']['std'],
                "samples": expected['error_rate']['samples']
            },
            "log_volume": {
                "mean": expected['log_volume']['mean'],
                "std": expected['log_volume']['std'],
                "samples": expected['log_volume']['samples']
            }
        },
        "overall_baseline": summary['overall']
    }


@app.get("/api/ml/hourly-patterns")
async def get_hourly_patterns() -> Dict[str, Any]:
    """Get learned hourly patterns"""
    from monitors.advanced.adaptive_baseline import adaptive_baseline
    
    patterns = {}
    
    for hour in range(24):
        baseline = adaptive_baseline.hourly_baselines[hour]
        if baseline['error_rate']['samples'] >= 5:
            patterns[hour] = {
                "error_rate_mean": baseline['error_rate']['mean'],
                "log_volume_mean": baseline['log_volume']['mean'],
                "samples": baseline['error_rate']['samples']
            }
    
    return {
        "patterns": patterns,
        "hours_learned": len(patterns),
        "current_hour": datetime.utcnow().hour
    }


@app.post("/api/ml/check-anomaly")
async def check_if_anomalous(
    error_rate: float,
    log_volume: int
) -> Dict[str, Any]:
    """Manually check if values are anomalous"""
    from monitors.advanced.adaptive_baseline import adaptive_baseline
    
    is_anomalous, details = adaptive_baseline.is_anomalous(
        error_rate=error_rate,
        log_volume=log_volume
    )
    
    return {
        "is_anomalous": is_anomalous,
        "details": details,
        "confidence": adaptive_baseline.get_confidence()
    }


# ============================================================================
# RCA ENDPOINTS
# ============================================================================

@app.get("/api/rca/status")
async def get_rca_status():
    """Get RCA system status"""
    from ai_analysis.incident_analyzer import incident_analyzer
    
    stats = incident_analyzer.get_statistics()
    
    return {
        "claude_api_enabled": stats['claude_enabled'],
        "total_analyses": stats['total_analyses'],
        "history_size": stats['history_size'],
        "status": "operational" if stats['claude_enabled'] else "disabled"
    }


@app.get("/api/rca/history")
async def get_rca_history(limit: int = 10):
    """Get RCA analysis history"""
    from ai_analysis.incident_analyzer import incident_analyzer
    
    history = incident_analyzer.get_analysis_history(limit=limit)
    stats = incident_analyzer.get_statistics()
    
    return {
        "history": [
            {
                "incident_id": h['incident_id'],
                "timestamp": h['timestamp'].isoformat(),
                "root_cause": h['root_cause'],
                "confidence": h['confidence']
            }
            for h in history
        ],
        "statistics": stats
    }


@app.post("/api/rca/quick-diagnose")
async def quick_diagnose(error_message: str):
    """Quick diagnosis of single error message"""
    from ai_analysis.incident_analyzer import incident_analyzer
    from ai_analysis.claude_client import claude_client
    
    diagnosis = await incident_analyzer.quick_diagnose(error_message)
    
    return {
        "error_message": error_message,
        "diagnosis": diagnosis,
        "claude_enabled": claude_client.enabled
    }


@app.get("/api/incidents/{incident_id}/rca")
async def get_incident_rca(incident_id: str):
    """Get RCA analysis for specific incident"""
    from monitors.log_monitor import monitor
    
    incidents = monitor.get_recent_incidents(limit=100)
    
    for incident in incidents:
        if incident.id == incident_id:
            if incident.rca_analysis:
                return {
                    "incident_id": incident_id,
                    "has_rca": True,
                    "rca": {
                        "root_cause": incident.rca_analysis.root_cause,
                        "impact": incident.rca_analysis.impact,
                        "technical_explanation": incident.rca_analysis.technical_explanation,
                        "immediate_actions": incident.rca_analysis.immediate_actions,
                        "prevention": incident.rca_analysis.prevention,
                        "confidence": incident.rca_analysis.confidence,
                        "analyzed_at": incident.rca_analysis.analyzed_at
                    }
                }
            else:
                return {
                    "incident_id": incident_id,
                    "has_rca": False,
                    "message": "RCA not available (Claude API may be disabled)"
                }
    
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Incident not found")



# ============================================================================
# ALERT ENDPOINTS
# ============================================================================

@app.get("/api/alerts/status")
async def get_alert_status():
    """Get alert system status and statistics"""
    from alerts.alert_manager import alert_manager
    
    stats = alert_manager.get_statistics()
    
    return {
        "alert_enabled": settings.alert_enabled,
        "slack_configured": stats['slack_enabled'],
        "webhook_configured": stats['webhook_enabled'],
        "total_alerts_sent": stats['total_alerts_sent'],
        "failed_alerts": stats['failed_alerts'],
        "success_rate": f"{stats['success_rate']:.1%}",
        "alert_severities": settings.alert_on_severities
    }


@app.get("/api/alerts/history")
async def get_alert_history(limit: int = 10):
    """Get recent alert history"""
    from alerts.alert_manager import alert_manager
    
    history = alert_manager.get_recent_alerts(limit=limit)
    
    return {
        "alerts": [
            {
                "incident_id": alert['incident_id'],
                "severity": alert['severity'],
                "timestamp": alert['timestamp'].isoformat(),
                "success": alert['success']
            }
            for alert in history
        ],
        "total": len(history)
    }


@app.post("/api/alerts/test")
async def test_alert():
    """Send a test alert to verify configuration"""
    from alerts.alert_manager import alert_manager
    from models.incident import Incident, Anomaly, LogEntry
    from datetime import datetime
    
    # Create test incident
    test_incident = Incident(
        id="TEST-ALERT-001",
        title="Test Alert: System Check",
        description="This is a test alert to verify webhook configuration",
        severity="high",
        started_at=datetime.utcnow(),
        log_count=100,
        error_count=25,
        affected_services=["test-service"],
        sample_logs=[
            LogEntry(
                timestamp=datetime.utcnow().isoformat(),
                level="ERROR",
                message="Test error message for alert verification",
                service="test-service"
            )
        ],
        anomalies=[
            Anomaly(
                anomaly_type="test_anomaly",
                severity="high",
                score=0.85,
                description="Test anomaly for alert verification"
            )
        ]
    )
    
    # Try to send alert
    success = await alert_manager.send_incident_alert(test_incident)
    
    if success:
        return {
            "status": "success",
            "message": "Test alert sent successfully",
            "incident_id": test_incident.id,
            "channels": {
                "slack": alert_manager.slack_webhook_url is not None,
                "webhook": alert_manager.generic_webhook_url is not None
            }
        }
    else:
        return {
            "status": "failed",
            "message": "Test alert failed to send. Check configuration and logs.",
            "incident_id": test_incident.id
        }


@app.get("/api/alerts/config")
async def get_alert_config():
    """Get current alert configuration (without sensitive data)"""
    return {
        "alert_enabled": settings.alert_enabled,
        "alert_on_severities": settings.alert_on_severities,
        "slack_configured": bool(settings.slack_webhook_url),
        "webhook_configured": bool(settings.generic_webhook_url),
        "slack_webhook_url": (
            settings.slack_webhook_url[:50] + "..." 
            if settings.slack_webhook_url 
            else None
        )
    }

