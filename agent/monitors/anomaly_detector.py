"""
Anomaly detection logic
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import statistics
from models.incident import Anomaly, LogEntry
from utils.logger import logger


class AnomalyDetector:
    """Detects anomalies in logs and metrics"""
    
    def __init__(self):
        self.baseline = {
            "error_rate": 0.0,
            "log_volume": 0,
            "services": set()
        }
        self.history = defaultdict(list)
    
    def detect_error_spike(
        self,
        current_errors: int,
        time_window_minutes: int = 5
    ) -> Optional[Anomaly]:
        """Detect sudden spike in error count"""
        
        # Store historical error counts
        self.history["error_counts"].append({
            "timestamp": datetime.utcnow(),
            "count": current_errors
        })
        
        # Keep only last 1 hour of history
        cutoff = datetime.utcnow() - timedelta(hours=1)
        self.history["error_counts"] = [
            h for h in self.history["error_counts"]
            if h["timestamp"] > cutoff
        ]
        
        # Need at least 5 data points to establish baseline
        if len(self.history["error_counts"]) < 5:
            logger.debug("Insufficient history for error spike detection")
            return None
        
        # Calculate baseline (average of previous counts)
        recent_counts = [h["count"] for h in self.history["error_counts"][:-1]]
        avg_errors = statistics.mean(recent_counts)
        std_errors = statistics.stdev(recent_counts) if len(recent_counts) > 1 else 0
        
        # Detect spike: current > avg + 2*std_dev
        threshold = avg_errors + (2 * std_errors)
        
        if current_errors > threshold and current_errors > 10:
            # Calculate anomaly score (0-1)
            score = min(1.0, (current_errors - threshold) / (threshold + 1))
            
            severity = self._calculate_severity(score)
            
            logger.warning(
                "Error spike detected",
                current=current_errors,
                baseline=avg_errors,
                threshold=threshold,
                score=score
            )
            
            return Anomaly(
                anomaly_type="error_spike",
                severity=severity,
                score=score,
                description=f"Error rate spiked to {current_errors} (baseline: {avg_errors:.1f})",
                metrics={
                    "current_errors": current_errors,
                    "baseline_avg": avg_errors,
                    "threshold": threshold,
                    "time_window": f"{time_window_minutes}m"
                }
            )
        
        return None
    
    def detect_error_patterns(self, logs: List[Dict[str, Any]]) -> List[Anomaly]:
        """Detect patterns in error messages"""
        anomalies = []
        
        # Extract error messages
        error_messages = []
        for log in logs:
            message = log.get("message", "")
            if "ERROR" in message or "error" in message.lower():
                error_messages.append(message)
        
        if not error_messages:
            return anomalies
        
        # Count error types
        error_counter = Counter(error_messages)
        most_common = error_counter.most_common(5)
        
        # Detect if one error type dominates (>50% of errors)
        total_errors = len(error_messages)
        for error_msg, count in most_common:
            percentage = (count / total_errors) * 100
            
            if percentage > 50 and count > 5:
                score = min(1.0, percentage / 100)
                severity = self._calculate_severity(score)
                
                logger.warning(
                    "Dominant error pattern detected",
                    error_type=error_msg[:50],
                    count=count,
                    percentage=percentage
                )
                
                anomalies.append(Anomaly(
                    anomaly_type="dominant_error_pattern",
                    severity=severity,
                    score=score,
                    description=f"Error '{error_msg[:50]}' accounts for {percentage:.1f}% of errors",
                    metrics={
                        "error_message": error_msg[:100],
                        "count": count,
                        "percentage": percentage,
                        "total_errors": total_errors
                    }
                ))
        
        return anomalies
    
    def detect_service_degradation(
        self,
        logs: List[Dict[str, Any]]
    ) -> Optional[Anomaly]:
        """Detect if specific service is having issues"""
        
        # Count errors by service
        service_errors = defaultdict(int)
        service_total = defaultdict(int)
        
        for log in logs:
            service = log.get("service") or log.get("kubernetes", {}).get("labels", {}).get("app", "unknown")
            service_total[service] += 1
            
            message = log.get("message", "")
            level = log.get("level", "")
            
            if "ERROR" in level or "ERROR" in message or "error" in message.lower():
                service_errors[service] += 1
        
        # Calculate error rate per service
        for service, error_count in service_errors.items():
            total = service_total[service]
            error_rate = error_count / total if total > 0 else 0
            
            # If a service has >30% error rate and >10 errors
            if error_rate > 0.3 and error_count > 10:
                score = min(1.0, error_rate)
                severity = self._calculate_severity(score)
                
                logger.warning(
                    "Service degradation detected",
                    service=service,
                    error_count=error_count,
                    total_logs=total,
                    error_rate=error_rate
                )
                
                return Anomaly(
                    anomaly_type="service_degradation",
                    severity=severity,
                    score=score,
                    description=f"Service '{service}' has {error_rate*100:.1f}% error rate",
                    metrics={
                        "service": service,
                        "error_count": error_count,
                        "total_logs": total,
                        "error_rate": error_rate
                    }
                )
        
        return None
    
    def detect_unusual_log_volume(
        self,
        current_volume: int,
        time_window_minutes: int = 5
    ) -> Optional[Anomaly]:
        """Detect unusual spike or drop in log volume"""
        
        # Store history
        self.history["log_volume"].append({
            "timestamp": datetime.utcnow(),
            "volume": current_volume
        })
        
        # Keep only last hour
        cutoff = datetime.utcnow() - timedelta(hours=1)
        self.history["log_volume"] = [
            h for h in self.history["log_volume"]
            if h["timestamp"] > cutoff
        ]
        
        # Need baseline
        if len(self.history["log_volume"]) < 5:
            return None
        
        # Calculate baseline
        recent_volumes = [h["volume"] for h in self.history["log_volume"][:-1]]
        avg_volume = statistics.mean(recent_volumes)
        std_volume = statistics.stdev(recent_volumes) if len(recent_volumes) > 1 else 0
        
        # Detect unusual volume (too high or too low)
        upper_threshold = avg_volume + (3 * std_volume)
        lower_threshold = max(0, avg_volume - (3 * std_volume))
        
        if current_volume > upper_threshold:
            # Spike in volume
            score = min(1.0, (current_volume - upper_threshold) / (upper_threshold + 1))
            severity = "medium" if score < 0.7 else "high"
            
            logger.info(
                "Log volume spike detected",
                current=current_volume,
                baseline=avg_volume,
                threshold=upper_threshold
            )
            
            return Anomaly(
                anomaly_type="log_volume_spike",
                severity=severity,
                score=score,
                description=f"Log volume spiked to {current_volume} (baseline: {avg_volume:.1f})",
                metrics={
                    "current_volume": current_volume,
                    "baseline_avg": avg_volume,
                    "threshold": upper_threshold
                }
            )
        
        elif current_volume < lower_threshold and avg_volume > 100:
            # Drop in volume (might indicate service down)
            score = min(1.0, (avg_volume - current_volume) / (avg_volume + 1))
            severity = "high" if score > 0.5 else "medium"
            
            logger.warning(
                "Log volume drop detected",
                current=current_volume,
                baseline=avg_volume,
                threshold=lower_threshold
            )
            
            return Anomaly(
                anomaly_type="log_volume_drop",
                severity=severity,
                score=score,
                description=f"Log volume dropped to {current_volume} (baseline: {avg_volume:.1f}) - possible service issue",
                metrics={
                    "current_volume": current_volume,
                    "baseline_avg": avg_volume,
                    "threshold": lower_threshold
                }
            )
        
        return None
    
    def analyze_logs(self, logs: List[Dict[str, Any]]) -> List[Anomaly]:
        """Run all anomaly detection algorithms"""
        anomalies = []
        
        if not logs:
            logger.debug("No logs to analyze")
            return anomalies
        
        logger.info("Analyzing logs for anomalies", log_count=len(logs))
        
        # 1. Check for error spike
        error_count = sum(
            1 for log in logs
            if "ERROR" in log.get("level", "") or "error" in log.get("message", "").lower()
        )
        
        error_spike = self.detect_error_spike(error_count)
        if error_spike:
            anomalies.append(error_spike)
        
        # 2. Check for error patterns
        pattern_anomalies = self.detect_error_patterns(logs)
        anomalies.extend(pattern_anomalies)
        
        # 3. Check for service degradation
        service_anomaly = self.detect_service_degradation(logs)
        if service_anomaly:
            anomalies.append(service_anomaly)
        
        # 4. Check log volume
        volume_anomaly = self.detect_unusual_log_volume(len(logs))
        if volume_anomaly:
            anomalies.append(volume_anomaly)
        
        if anomalies:
            logger.warning("Anomalies detected", count=len(anomalies))
        else:
            logger.debug("No anomalies detected")
        
        return anomalies
    
    def _calculate_severity(self, score: float) -> str:
        """Calculate severity based on anomaly score"""
        if score >= 0.8:
            return "critical"
        elif score >= 0.6:
            return "high"
        elif score >= 0.4:
            return "medium"
        else:
            return "low"


# Global detector instance
detector = AnomalyDetector()
