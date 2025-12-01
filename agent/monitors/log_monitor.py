from alerts.alert_manager import alert_manager
"""
Continuous log monitoring with advanced detection and adaptive baseline
"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional
from models.incident import Incident, MonitoringState, LogEntry, Anomaly
from clients.elasticsearch_client import es_client
from monitors.anomaly_detector import detector
from monitors.advanced.timeseries_analyzer import ts_analyzer
from monitors.advanced.correlation_engine import correlation_engine
from monitors.advanced.adaptive_baseline import adaptive_baseline
from utils.logger import logger
from config.settings import settings


class LogMonitor:
    """Monitors logs continuously with ML-powered detection"""
    
    def __init__(self):
        self.state = MonitoringState(
            last_check=datetime.utcnow(),
            status="initializing"
        )
        self.running = False
        self.incidents: List[Incident] = []
        self.check_count = 0
    
    async def start(self):
        """Start continuous monitoring with adaptive learning"""
        self.running = True
        self.state.status = "healthy"
        
        baseline_confidence = adaptive_baseline.get_confidence()
        
        logger.info(
            "Starting log monitor with ML detection",
            interval=settings.log_check_interval,
            baseline_confidence=baseline_confidence,
            adaptive_learning="enabled"
        )
        
        while self.running:
            try:
                await self._check_logs()
                self.check_count += 1
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
        """Check logs with full ML detection pipeline"""
        check_start = datetime.utcnow()
        
        logger.debug(
            "ML monitoring cycle",
            check_number=self.check_count,
            baseline_confidence=adaptive_baseline.get_confidence()
        )
        
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
        
        logger.info(
            "Processing logs with ML pipeline",
            count=len(logs),
            check=self.check_count
        )
        
        # 3. Calculate metrics
        error_count = sum(
            1 for log in logs
            if "ERROR" in log.get("level", "") or "error" in log.get("message", "").lower()
        )
        
        log_volume = len(logs)
        
        # 4. Update adaptive baseline (learning phase)
        adaptive_baseline.update(
            error_rate=error_count,
            log_volume=log_volume,
            timestamp=check_start
        )
        
        # 5. Check against adaptive baseline
        baseline_anomalies = []
        is_anomalous, baseline_details = adaptive_baseline.is_anomalous(
            error_rate=error_count,
            log_volume=log_volume,
            timestamp=check_start,
            sensitivity=2.0  # 2 standard deviations
        )
        
        if is_anomalous:
            # Create anomaly from baseline detection
            severity = "critical" if abs(baseline_details['error_rate']['z_score']) > 3 else "high"
            score = min(1.0, abs(baseline_details['error_rate']['z_score']) / 3)
            
            baseline_anomaly = Anomaly(
                anomaly_type="adaptive_baseline_deviation",
                severity=severity,
                score=score,
                description=f"Deviation from learned baseline: {baseline_details['error_rate']['current']:.1f} errors (expected {baseline_details['error_rate']['expected']:.1f}±{baseline_details['error_rate']['std']:.1f})",
                metrics=baseline_details
            )
            
            baseline_anomalies.append(baseline_anomaly)
            
            logger.warning(
                "Adaptive baseline anomaly detected",
                error_z_score=baseline_details['error_rate']['z_score'],
                volume_z_score=baseline_details['log_volume']['z_score']
            )
        
        # 6. Add data point to time-series analyzer
        ts_analyzer.add_datapoint(
            error_count=error_count,
            log_volume=log_volume
        )
        
        # 7. Run basic anomaly detection
        basic_anomalies = detector.analyze_logs(logs)
        
        # 8. Run advanced time-series analysis (every 3rd check)
        ts_anomalies = []
        if self.check_count % 3 == 0:
            logger.debug("Running time-series analysis")
            ts_anomalies = ts_analyzer.analyze_patterns()
            
            if ts_anomalies:
                logger.info(
                    "Time-series patterns detected",
                    count=len(ts_anomalies),
                    types=[a.anomaly_type for a in ts_anomalies]
                )
        
        # 9. Run correlation analysis (every 2nd check)
        corr_anomalies = []
        if self.check_count % 2 == 0:
            logger.debug("Running correlation analysis")
            corr_anomalies = correlation_engine.analyze_correlations(logs)
            
            if corr_anomalies:
                logger.info(
                    "Correlations detected",
                    count=len(corr_anomalies),
                    types=[a.anomaly_type for a in corr_anomalies]
                )
        
        # 10. Combine all anomalies
        all_anomalies = (
            baseline_anomalies +
            basic_anomalies +
            ts_anomalies +
            corr_anomalies
        )
        
        self.state.anomalies_detected += len(all_anomalies)
        
        # 11. Log detection summary
        if all_anomalies:
            logger.info(
                "Anomalies detected in cycle",
                total=len(all_anomalies),
                baseline=len(baseline_anomalies),
                basic=len(basic_anomalies),
                timeseries=len(ts_anomalies),
                correlation=len(corr_anomalies)
            )
        
        # 12. Create incident if critical anomalies detected
        critical_anomalies = [
            a for a in all_anomalies
            if a.severity in ["critical", "high"]
        ]
        
        if critical_anomalies:
            incident = await self._create_incident(logs, critical_anomalies)
            if incident:
                self.incidents.append(incident)
                self.state.incidents_created += 1
                
                confidence = adaptive_baseline.get_confidence()
                
                logger.warning(
                    "Incident created with ML detection",
                    incident_id=incident.id,
                    severity=incident.severity,
                    anomaly_count=len(critical_anomalies),
                    baseline_confidence=confidence,
                    anomaly_types=[a.anomaly_type for a in critical_anomalies]
                )
        else:
            logger.debug(
                "Cycle complete - system healthy",
                total_anomalies=len(all_anomalies),
                baseline_confidence=adaptive_baseline.get_confidence()
            )
        
        # 13. Update state
        self.state.last_check = check_start
        self.state.status = "healthy"
    
    async def _create_incident(
        self,
        logs: List[dict],
        anomalies: List
    ) -> Optional[Incident]:
        """Create incident from anomalies with ML context"""
        
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
        
        # Determine severity
        severity_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        max_severity = max(anomalies, key=lambda a: severity_order[a.severity]).severity
        
        # Create title
        anomaly_types = list(set(a.anomaly_type for a in anomalies))
        title = f"ML-Detected Incident: {', '.join(anomaly_types[:3])}"
        if len(anomaly_types) > 3:
            title += f" (+{len(anomaly_types) - 3} more)"
        
        # Create description with ML context
        descriptions = []
        
        # Add baseline context if available
        baseline_anomalies = [a for a in anomalies if a.anomaly_type == "adaptive_baseline_deviation"]
        if baseline_anomalies:
            confidence = adaptive_baseline.get_confidence()
            descriptions.append(
                f"[BASELINE] System deviating from learned normal behavior (confidence: {confidence:.0%})"
            )
        
        # Add other anomalies
        for a in anomalies[:5]:
            descriptions.append(f"[{a.severity.upper()}] {a.description}")
        
        description = "\n".join(descriptions)
        if len(anomalies) > 5:
            description += f"\n\n... and {len(anomalies) - 5} more anomalies"
        
        # Sample logs
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
        
        # Metrics snapshot with ML context
        baseline_summary = adaptive_baseline.get_summary()
        
        metrics_snapshot = {
            "total_logs": len(logs),
            "error_logs": len(error_logs),
            "error_rate": len(error_logs) / len(logs) if logs else 0,
            "anomaly_breakdown": {
                a.anomaly_type: sum(1 for x in anomalies if x.anomaly_type == a.anomaly_type)
                for a in anomalies
            },
            "ml_context": {
                "baseline_confidence": baseline_summary['confidence'],
                "baseline_samples": baseline_summary['total_samples'],
                "hours_learned": baseline_summary['hours_with_data'],
                "detection_methods": list(set(a.anomaly_type for a in anomalies))
            }
        }
        
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
            sample_logs=sample_log_entries,
            metrics_snapshot=metrics_snapshot
        )
        
        logger.info(
            "ML-powered incident created",
            incident_id=incident.id,
            severity=incident.severity,
            ml_confidence=baseline_summary['confidence'],
            detection_types=anomaly_types
        )
        
        
        logger.info("Incident created - initiating RCA", incident_id=incident.id)
        
        # Perform RCA
        try:
            from ai_analysis.incident_analyzer import incident_analyzer
            from models.incident import RootCauseAnalysis
            
            rca_result = await incident_analyzer.analyze_incident(incident)
            
            if rca_result:
                incident.root_cause = rca_result.get('root_cause', '')
                incident.recommendations = rca_result.get('immediate_actions', [])
                incident.rca_analysis = RootCauseAnalysis(
                    root_cause=rca_result.get('root_cause', ''),
                    impact=rca_result.get('impact', ''),
                    technical_explanation=rca_result.get('technical_explanation', ''),
                    immediate_actions=rca_result.get('immediate_actions', []),
                    prevention=rca_result.get('prevention', []),
                    confidence=rca_result.get('confidence', 'Unknown'),
                    analyzed_at=rca_result.get('analyzed_at', ''),
                    full_analysis=rca_result.get('full_analysis', '')
                )
                logger.info("RCA completed", incident_id=incident.id)
        except Exception as e:
            logger.error("RCA failed", incident_id=incident.id, error=str(e))
        

        # Send alerts for incident
        try:
            await alert_manager.send_incident_alert(incident)
            logger.info("Alert sent for incident", incident_id=incident.id)
        except Exception as alert_err:
            logger.error("Failed to send alert", incident_id=incident.id, error=str(alert_err))

        # Store incident
        self.incidents.append(incident)
        self.state.incidents_created += 1
        
        return incident



    
    def get_state(self) -> MonitoringState:
        """Get current monitoring state"""
        return self.state
    
    def get_recent_incidents(self, limit: int = 10) -> List[Incident]:
        """Get recent incidents"""
        return self.incidents[-limit:]
    
    def get_statistics(self) -> dict:
        """Get monitoring statistics with ML metrics"""
        baseline_summary = adaptive_baseline.get_summary()
        
        return {
            "monitoring": {
                "total_checks": self.check_count,
                "logs_processed": self.state.logs_processed,
                "anomalies_detected": self.state.anomalies_detected,
                "incidents_created": self.state.incidents_created,
                "status": self.state.status,
                "last_check": self.state.last_check.isoformat()
            },
            "ml_baseline": {
                "confidence": baseline_summary['confidence'],
                "total_samples": baseline_summary['total_samples'],
                "history_size": baseline_summary['history_size'],
                "hours_with_data": baseline_summary['hours_with_data'],
                "days_with_data": baseline_summary['days_with_data'],
                "overall_baseline": baseline_summary['overall']
            },
            "uptime_seconds": (datetime.utcnow() - self.state.last_check).total_seconds()
        }


# Global monitor instance
monitor = LogMonitor()
