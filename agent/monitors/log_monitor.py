"""
Continuous log monitoring
"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional
from models.incident import Incident, MonitoringState, LogEntry
from clients.elasticsearch_client import es_client
from monitors.anomaly_detector import detector
from utils.logger import logger
from config.settings import settings


class LogMonitor:
    """Monitors logs continuously and detects anomalies"""
    
    def __init__(self):
        self.state = MonitoringState(
            last_check=datetime.utcnow(),
            status="initializing"
        )
        self.running = False
        self.incidents: List[Incident] = []
    
    async def start(self):
        """Start continuous monitoring"""
        self.running = True
        self.state.status = "healthy"
        
        logger.info("Starting log monitor", interval=settings.log_check_interval)
        
        while self.running:
            try:
                await self._check_logs()
                await asyncio.sleep(settings.log_check_interval)
            
            except Exception as e:
                logger.error("Error in monitoring loop", error=str(e))
                self.state.status = "error"
                await asyncio.sleep(settings.log_check_interval)
    
    async def stop(self):
        """Stop monitoring"""
        self.running = False
        self.state.status = "stopped"
        logger.info("Log monitor stopped")
    
    async def _check_logs(self):
        """Check logs for anomalies"""
        check_start = datetime.utcnow()
        
        logger.debug("Checking logs for anomalies")
        
        # 1. Check Elasticsearch health
        es_healthy = await es_client.health_check()
        if not es_healthy:
            logger.error("Elasticsearch unhealthy")
            self.state.status = "degraded"
            return
        
        # 2. Get recent logs (last 5 minutes)
        logs = await es_client.search_logs(
            query={
                "range": {
                    "@timestamp": {
                        "gte": "now-5m"
                    }
                }
            },
            size=500
        )
        
        self.state.logs_processed += len(logs)
        
        if not logs:
            logger.debug("No recent logs found")
            self.state.last_check = check_start
            return
        
        logger.info("Processing logs", count=len(logs))
        
        # 3. Run anomaly detection
        anomalies = detector.analyze_logs(logs)
        
        self.state.anomalies_detected += len(anomalies)
        
        # 4. Create incident if critical anomalies detected
        critical_anomalies = [a for a in anomalies if a.severity in ["critical", "high"]]
        
        if critical_anomalies:
            incident = await self._create_incident(logs, critical_anomalies)
            if incident:
                self.incidents.append(incident)
                self.state.incidents_created += 1
                logger.warning(
                    "Incident created",
                    incident_id=incident.id,
                    severity=incident.severity,
                    anomaly_count=len(critical_anomalies)
                )
        
        # 5. Update state
        self.state.last_check = check_start
        self.state.status = "healthy"
    
    async def _create_incident(
        self,
        logs: List[dict],
        anomalies: List
    ) -> Optional[Incident]:
        """Create incident from anomalies"""
        
        # Get error logs
        error_logs = [
            log for log in logs
            if "ERROR" in log.get("level", "") or "error" in log.get("message", "").lower()
        ]
        
        # Get affected services
        services = set()
        for log in error_logs:
            service = log.get("service") or log.get("kubernetes", {}).get("labels", {}).get("app")
            if service:
                services.add(service)
        
        # Determine severity (highest from anomalies)
        severity_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        max_severity = max(anomalies, key=lambda a: severity_order[a.severity]).severity
        
        # Create title
        anomaly_types = [a.anomaly_type for a in anomalies]
        title = f"Incident: {', '.join(set(anomaly_types))}"
        
        # Create description
        descriptions = [a.description for a in anomalies]
        description = "\n".join(f"- {d}" for d in descriptions)
        
        # Sample logs (first 5 errors)
        sample_log_entries = []
        for log in error_logs[:5]:
            sample_log_entries.append(LogEntry(
                timestamp=log.get("@timestamp", ""),
                level=log.get("level", ""),
                message=log.get("message", "")[:200],
                service=log.get("service"),
                pod=log.get("kubernetes", {}).get("pod", {}).get("name"),
                namespace=log.get("kubernetes", {}).get("namespace")
            ))
        
        incident = Incident(
            id=f"INC-{int(datetime.utcnow().timestamp())}",
            title=title,
            description=description,
            severity=max_severity,
            started_at=datetime.utcnow() - timedelta(minutes=5),
            anomalies=anomalies,
            affected_services=list(services),
            log_count=len(logs),
            error_count=len(error_logs),
            sample_logs=sample_log_entries
        )
        
        logger.info(
            "Incident created",
            incident_id=incident.id,
            title=incident.title,
            severity=incident.severity,
            error_count=len(error_logs),
            services=list(services)
        )
        
        return incident
    
    def get_state(self) -> MonitoringState:
        """Get current monitoring state"""
        return self.state
    
    def get_recent_incidents(self, limit: int = 10) -> List[Incident]:
        """Get recent incidents"""
        return self.incidents[-limit:]


# Global monitor instance
monitor = LogMonitor()
