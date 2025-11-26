"""
Time-series pattern analysis for trend detection
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from collections import deque
import statistics
from models.incident import Anomaly
from utils.logger import logger


class TimeSeriesAnalyzer:
    """Analyzes time-series data for trends and patterns"""
    
    def __init__(self, window_size: int = 12):
        """
        Initialize analyzer
        
        Args:
            window_size: Number of data points to keep (default 12 = 6 minutes at 30s intervals)
        """
        self.window_size = window_size
        self.error_rate_history = deque(maxlen=window_size)
        self.log_volume_history = deque(maxlen=window_size)
        self.response_time_history = deque(maxlen=window_size)
    
    def add_datapoint(
        self,
        error_count: int,
        log_volume: int,
        avg_response_time: Optional[float] = None
    ):
        """Add new data point to history"""
        timestamp = datetime.utcnow()
        
        self.error_rate_history.append({
            'timestamp': timestamp,
            'value': error_count
        })
        
        self.log_volume_history.append({
            'timestamp': timestamp,
            'value': log_volume
        })
        
        if avg_response_time is not None:
            self.response_time_history.append({
                'timestamp': timestamp,
                'value': avg_response_time
            })
    
    def detect_increasing_trend(
        self,
        data_history: deque,
        min_points: int = 5
    ) -> Optional[Anomaly]:
        """
        Detect consistently increasing trend
        
        Uses linear regression to identify upward trends
        """
        if len(data_history) < min_points:
            return None
        
        # Extract values
        values = [point['value'] for point in data_history]
        
        # Simple linear regression
        n = len(values)
        x = list(range(n))
        
        # Calculate slope
        x_mean = sum(x) / n
        y_mean = sum(values) / n
        
        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return None
        
        slope = numerator / denominator
        
        # Check if slope is significantly positive
        # Slope > 0.1 means values are increasing
        if slope > 0.1:
            # Calculate R-squared (goodness of fit)
            y_pred = [slope * x[i] + (y_mean - slope * x_mean) for i in range(n)]
            ss_tot = sum((values[i] - y_mean) ** 2 for i in range(n))
            ss_res = sum((values[i] - y_pred[i]) ** 2 for i in range(n))
            
            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
            
            # Strong trend if R² > 0.7
            if r_squared > 0.7:
                score = min(1.0, slope * r_squared)
                severity = "high" if score > 0.6 else "medium"
                
                logger.warning(
                    "Increasing trend detected",
                    slope=slope,
                    r_squared=r_squared,
                    score=score
                )
                
                return Anomaly(
                    anomaly_type="increasing_trend",
                    severity=severity,
                    score=score,
                    description=f"Detected upward trend with slope {slope:.2f} (R²={r_squared:.2f})",
                    metrics={
                        "slope": slope,
                        "r_squared": r_squared,
                        "data_points": n,
                        "start_value": values[0],
                        "end_value": values[-1]
                    }
                )
        
        return None
    
    def detect_error_rate_trend(self) -> Optional[Anomaly]:
        """Detect increasing error rate trend"""
        return self.detect_increasing_trend(self.error_rate_history)
    
    def detect_log_volume_trend(self) -> Optional[Anomaly]:
        """Detect increasing log volume trend"""
        return self.detect_increasing_trend(self.log_volume_history)
    
    def detect_oscillation(
        self,
        data_history: deque,
        min_points: int = 6
    ) -> Optional[Anomaly]:
        """
        Detect oscillating/unstable behavior
        
        High variance indicates instability
        """
        if len(data_history) < min_points:
            return None
        
        values = [point['value'] for point in data_history]
        
        if len(values) < 2:
            return None
        
        mean = statistics.mean(values)
        stdev = statistics.stdev(values)
        
        # Coefficient of variation (CV) = stdev / mean
        # High CV indicates instability
        if mean > 0:
            cv = stdev / mean
            
            # CV > 0.5 indicates high variability
            if cv > 0.5 and stdev > 5:
                score = min(1.0, cv)
                severity = "medium"
                
                logger.warning(
                    "Oscillation detected",
                    coefficient_of_variation=cv,
                    mean=mean,
                    stdev=stdev
                )
                
                return Anomaly(
                    anomaly_type="oscillation",
                    severity=severity,
                    score=score,
                    description=f"Unstable behavior detected (CV={cv:.2f})",
                    metrics={
                        "coefficient_of_variation": cv,
                        "mean": mean,
                        "stdev": stdev,
                        "data_points": len(values)
                    }
                )
        
        return None
    
    def detect_sudden_change(
        self,
        data_history: deque,
        threshold_multiplier: float = 2.0
    ) -> Optional[Anomaly]:
        """
        Detect sudden level change (step change)
        
        Compares recent average to historical average
        """
        if len(data_history) < 6:
            return None
        
        values = [point['value'] for point in data_history]
        
        # Split into first half and second half
        mid = len(values) // 2
        first_half = values[:mid]
        second_half = values[mid:]
        
        avg_first = statistics.mean(first_half)
        avg_second = statistics.mean(second_half)
        
        # Check for significant level shift
        if avg_first > 0:
            ratio = avg_second / avg_first
            
            # Level shifted up by >2x
            if ratio > threshold_multiplier:
                score = min(1.0, (ratio - threshold_multiplier) / threshold_multiplier)
                severity = "high" if score > 0.5 else "medium"
                
                logger.warning(
                    "Sudden level change detected",
                    before=avg_first,
                    after=avg_second,
                    ratio=ratio
                )
                
                return Anomaly(
                    anomaly_type="sudden_level_change",
                    severity=severity,
                    score=score,
                    description=f"Sudden increase from {avg_first:.1f} to {avg_second:.1f}",
                    metrics={
                        "before_avg": avg_first,
                        "after_avg": avg_second,
                        "ratio": ratio,
                        "data_points": len(values)
                    }
                )
        
        return None
    
    def analyze_patterns(self) -> List[Anomaly]:
        """Run all pattern analyses"""
        anomalies = []
        
        # Check for trends
        trend = self.detect_error_rate_trend()
        if trend:
            anomalies.append(trend)
        
        # Check for oscillation
        oscillation = self.detect_oscillation(self.error_rate_history)
        if oscillation:
            anomalies.append(oscillation)
        
        # Check for sudden changes
        change = self.detect_sudden_change(self.error_rate_history)
        if change:
            anomalies.append(change)
        
        return anomalies


# Global analyzer instance
ts_analyzer = TimeSeriesAnalyzer()
