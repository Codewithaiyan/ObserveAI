"""
Correlation engine to find relationships between metrics and logs
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import statistics
from models.incident import Anomaly
from utils.logger import logger


class CorrelationEngine:
    """Finds correlations between different observability signals"""
    
    def __init__(self):
        self.correlation_cache = defaultdict(list)
        self.pattern_memory = defaultdict(int)
    
    def correlate_error_with_endpoint(
        self,
        logs: List[Dict]
    ) -> Optional[Anomaly]:
        """
        Correlate errors with specific endpoints
        
        Identifies which endpoints are generating most errors
        """
        endpoint_errors = defaultdict(int)
        endpoint_total = defaultdict(int)
        
        for log in logs:
            # Extract endpoint from log
            endpoint = None
            message = log.get('message', '')
            
            # Try to extract endpoint from message
            if 'GET' in message or 'POST' in message:
                parts = message.split()
                for i, part in enumerate(parts):
                    if part in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
                        if i + 1 < len(parts):
                            endpoint = parts[i + 1]
                            break
            
            if not endpoint:
                endpoint = log.get('endpoint', 'unknown')
            
            endpoint_total[endpoint] += 1
            
            # Check if error
            level = log.get('level', '')
            if 'ERROR' in level or 'error' in message.lower():
                endpoint_errors[endpoint] += 1
        
        # Find endpoints with high error rate
        problematic_endpoints = []
        
        for endpoint, error_count in endpoint_errors.items():
            total = endpoint_total[endpoint]
            if total < 5:  # Need minimum sample size
                continue
            
            error_rate = error_count / total
            
            # Error rate > 30% is problematic
            if error_rate > 0.3:
                problematic_endpoints.append({
                    'endpoint': endpoint,
                    'error_count': error_count,
                    'total_requests': total,
                    'error_rate': error_rate
                })
        
        if problematic_endpoints:
            # Sort by error rate
            problematic_endpoints.sort(key=lambda x: x['error_rate'], reverse=True)
            top_endpoint = problematic_endpoints[0]
            
            score = min(1.0, top_endpoint['error_rate'])
            severity = "critical" if score > 0.8 else "high"
            
            logger.warning(
                "Endpoint correlation detected",
                endpoint=top_endpoint['endpoint'],
                error_rate=top_endpoint['error_rate']
            )
            
            return Anomaly(
                anomaly_type="endpoint_error_correlation",
                severity=severity,
                score=score,
                description=f"Endpoint '{top_endpoint['endpoint']}' has {top_endpoint['error_rate']*100:.1f}% error rate",
                metrics={
                    "endpoint": top_endpoint['endpoint'],
                    "error_count": top_endpoint['error_count'],
                    "total_requests": top_endpoint['total_requests'],
                    "error_rate": top_endpoint['error_rate'],
                    "all_problematic": problematic_endpoints
                }
            )
        
        return None
    
    def correlate_error_with_time(
        self,
        logs: List[Dict]
    ) -> Optional[Anomaly]:
        """
        Correlate errors with time of day
        
        Identifies if errors spike at specific times
        """
        if not logs:
            return None
        
        # Group errors by hour
        errors_by_hour = defaultdict(int)
        total_by_hour = defaultdict(int)
        
        for log in logs:
            timestamp_str = log.get('@timestamp') or log.get('timestamp')
            if not timestamp_str:
                continue
            
            try:
                # Parse timestamp
                if 'Z' in timestamp_str:
                    dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                else:
                    dt = datetime.fromisoformat(timestamp_str)
                
                hour = dt.hour
                total_by_hour[hour] += 1
                
                # Check if error
                level = log.get('level', '')
                message = log.get('message', '')
                if 'ERROR' in level or 'error' in message.lower():
                    errors_by_hour[hour] += 1
            
            except Exception as e:
                logger.debug(f"Failed to parse timestamp: {e}")
                continue
        
        if not errors_by_hour:
            return None
        
        # Find hour with highest error rate
        max_error_rate = 0
        problem_hour = None
        
        for hour, error_count in errors_by_hour.items():
            total = total_by_hour.get(hour, 0)
            if total < 5:  # Minimum sample
                continue
            
            error_rate = error_count / total
            if error_rate > max_error_rate:
                max_error_rate = error_rate
                problem_hour = hour
        
        # Alert if one hour has significantly more errors than average
        if problem_hour is not None and max_error_rate > 0.5:
            score = min(1.0, max_error_rate)
            severity = "medium"
            
            logger.info(
                "Time-based correlation detected",
                hour=problem_hour,
                error_rate=max_error_rate
            )
            
            return Anomaly(
                anomaly_type="time_based_error_pattern",
                severity=severity,
                score=score,
                description=f"Errors concentrated around hour {problem_hour}:00 UTC ({max_error_rate*100:.1f}% error rate)",
                metrics={
                    "problem_hour": problem_hour,
                    "error_rate": max_error_rate,
                    "errors_by_hour": dict(errors_by_hour),
                    "total_by_hour": dict(total_by_hour)
                }
            )
        
        return None
    
    def correlate_error_cascade(
        self,
        logs: List[Dict]
    ) -> Optional[Anomaly]:
        """
        Detect error cascades (one error causes others)
        
        Looks for rapid succession of different error types
        """
        if len(logs) < 10:
            return None
        
        # Extract error messages with timestamps
        error_events = []
        
        for log in logs:
            level = log.get('level', '')
            message = log.get('message', '')
            
            if 'ERROR' in level or 'error' in message.lower():
                timestamp_str = log.get('@timestamp') or log.get('timestamp')
                if timestamp_str:
                    try:
                        if 'Z' in timestamp_str:
                            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        else:
                            dt = datetime.fromisoformat(timestamp_str)
                        
                        error_events.append({
                            'timestamp': dt,
                            'message': message[:100],  # First 100 chars
                            'service': log.get('service', 'unknown')
                        })
                    except:
                        pass
        
        if len(error_events) < 5:
            return None
        
        # Sort by timestamp
        error_events.sort(key=lambda x: x['timestamp'])
        
        # Look for rapid succession (5+ errors within 30 seconds)
        cascade_windows = []
        
        for i in range(len(error_events) - 4):
            window_start = error_events[i]['timestamp']
            window_end = error_events[i + 4]['timestamp']
            
            time_diff = (window_end - window_start).total_seconds()
            
            # 5 errors within 30 seconds = cascade
            if time_diff <= 30:
                # Check if different error types
                messages = [error_events[j]['message'] for j in range(i, i + 5)]
                unique_messages = len(set(messages))
                
                # At least 3 different error types
                if unique_messages >= 3:
                    cascade_windows.append({
                        'start': window_start,
                        'end': window_end,
                        'duration': time_diff,
                        'error_count': 5,
                        'unique_types': unique_messages
                    })
        
        if cascade_windows:
            # Use first cascade window
            cascade = cascade_windows[0]
            
            score = min(1.0, cascade['unique_types'] / 5)
            severity = "high"
            
            logger.warning(
                "Error cascade detected",
                duration=cascade['duration'],
                error_count=cascade['error_count'],
                unique_types=cascade['unique_types']
            )
            
            return Anomaly(
                anomaly_type="error_cascade",
                severity=severity,
                score=score,
                description=f"Error cascade detected: {cascade['error_count']} errors ({cascade['unique_types']} types) in {cascade['duration']:.1f}s",
                metrics={
                    "duration_seconds": cascade['duration'],
                    "error_count": cascade['error_count'],
                    "unique_error_types": cascade['unique_types'],
                    "cascade_count": len(cascade_windows)
                }
            )
        
        return None
    
    def detect_error_clustering(
        self,
        logs: List[Dict]
    ) -> Optional[Anomaly]:
        """
        Detect if errors are clustered by similarity
        
        Identifies if many errors are variations of same issue
        """
        error_messages = []
        
        for log in logs:
            level = log.get('level', '')
            message = log.get('message', '')
            
            if 'ERROR' in level or 'error' in message.lower():
                # Normalize message (remove numbers, IDs)
                import re
                normalized = re.sub(r'\d+', 'N', message)
                normalized = re.sub(r'[a-f0-9]{8,}', 'ID', normalized)
                error_messages.append(normalized[:100])
        
        if len(error_messages) < 10:
            return None
        
        # Count message patterns
        pattern_counter = Counter(error_messages)
        most_common = pattern_counter.most_common(3)
        
        total_errors = len(error_messages)
        
        # Check if one pattern dominates
        for pattern, count in most_common:
            percentage = (count / total_errors) * 100
            
            # One pattern > 60% of errors = clustering
            if percentage > 60:
                score = min(1.0, percentage / 100)
                severity = "high" if percentage > 80 else "medium"
                
                logger.warning(
                    "Error clustering detected",
                    pattern=pattern[:50],
                    count=count,
                    percentage=percentage
                )
                
                return Anomaly(
                    anomaly_type="error_clustering",
                    severity=severity,
                    score=score,
                    description=f"Error pattern '{pattern[:50]}...' accounts for {percentage:.1f}% of errors",
                    metrics={
                        "dominant_pattern": pattern[:100],
                        "occurrence_count": count,
                        "percentage": percentage,
                        "total_errors": total_errors,
                        "top_patterns": [
                            {"pattern": p[:50], "count": c}
                            for p, c in most_common
                        ]
                    }
                )
        
        return None
    
    def analyze_correlations(self, logs: List[Dict]) -> List[Anomaly]:
        """Run all correlation analyses"""
        anomalies = []
        
        if not logs:
            return anomalies
        
        # Endpoint correlation
        endpoint_corr = self.correlate_error_with_endpoint(logs)
        if endpoint_corr:
            anomalies.append(endpoint_corr)
        
        # Time-based correlation
        time_corr = self.correlate_error_with_time(logs)
        if time_corr:
            anomalies.append(time_corr)
        
        # Error cascade
        cascade = self.correlate_error_cascade(logs)
        if cascade:
            anomalies.append(cascade)
        
        # Error clustering
        clustering = self.detect_error_clustering(logs)
        if clustering:
            anomalies.append(clustering)
        
        if anomalies:
            logger.info(f"Correlation analysis found {len(anomalies)} correlations")
        
        return anomalies


# Global correlation engine
correlation_engine = CorrelationEngine()
