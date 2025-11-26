"""
Adaptive baseline learning - system learns normal behavior over time
"""
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import deque
import statistics
import json
from pathlib import Path
from utils.logger import logger


class AdaptiveBaseline:
    """Learns and adapts to normal system behavior over time"""
    
    def __init__(self, persistence_path: str = "/data/baselines.json"):
        """
        Initialize adaptive baseline
        
        Args:
            persistence_path: Path to save/load baseline data
        """
        self.persistence_path = Path(persistence_path)
        
        # Historical data (last 24 hours at 30s intervals = 2880 points max)
        self.error_rate_history = deque(maxlen=2880)
        self.log_volume_history = deque(maxlen=2880)
        
        # Learned baselines by hour of day (0-23)
        self.hourly_baselines = {
            hour: {
                'error_rate': {'mean': 0, 'std': 0, 'samples': 0},
                'log_volume': {'mean': 0, 'std': 0, 'samples': 0}
            }
            for hour in range(24)
        }
        
        # Day of week patterns (0=Monday, 6=Sunday)
        self.daily_baselines = {
            day: {
                'error_rate': {'mean': 0, 'std': 0, 'samples': 0},
                'log_volume': {'mean': 0, 'std': 0, 'samples': 0}
            }
            for day in range(7)
        }
        
        # Overall baseline (fallback)
        self.overall_baseline = {
            'error_rate': {'mean': 0, 'std': 1, 'samples': 0},
            'log_volume': {'mean': 100, 'std': 50, 'samples': 0}
        }
        
        # Load existing baselines if available
        self._load_baselines()
        
        logger.info("Adaptive baseline initialized", path=str(self.persistence_path))
    
    def update(
        self,
        error_rate: float,
        log_volume: int,
        timestamp: Optional[datetime] = None
    ):
        """
        Update baselines with new data point
        
        Args:
            error_rate: Current error rate (errors per check)
            log_volume: Current log volume
            timestamp: Timestamp of measurement (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        # Add to history
        data_point = {
            'timestamp': timestamp.isoformat(),
            'error_rate': error_rate,
            'log_volume': log_volume
        }
        
        self.error_rate_history.append(data_point)
        self.log_volume_history.append(data_point)
        
        # Update hourly baseline
        hour = timestamp.hour
        self._update_baseline_stats(
            self.hourly_baselines[hour],
            error_rate,
            log_volume
        )
        
        # Update daily baseline
        day = timestamp.weekday()
        self._update_baseline_stats(
            self.daily_baselines[day],
            error_rate,
            log_volume
        )
        
        # Update overall baseline
        self._update_baseline_stats(
            self.overall_baseline,
            error_rate,
            log_volume
        )
        
        # Persist every 10 updates
        if self.overall_baseline['error_rate']['samples'] % 10 == 0:
            self._save_baselines()
        
        logger.debug(
            "Baseline updated",
            hour=hour,
            day=day,
            error_rate=error_rate,
            log_volume=log_volume,
            total_samples=self.overall_baseline['error_rate']['samples']
        )
    
    def _update_baseline_stats(
        self,
        baseline: Dict,
        error_rate: float,
        log_volume: int
    ):
        """Update baseline statistics using online algorithm"""
        
        # Update error rate (Welford's online algorithm for running stats)
        n = baseline['error_rate']['samples']
        old_mean = baseline['error_rate']['mean']
        
        n += 1
        new_mean = old_mean + (error_rate - old_mean) / n
        
        # Update variance (for standard deviation)
        if n > 1:
            old_var = baseline['error_rate']['std'] ** 2
            new_var = ((n - 1) * old_var + (error_rate - old_mean) * (error_rate - new_mean)) / n
            new_std = new_var ** 0.5
        else:
            new_std = 0
        
        baseline['error_rate'] = {
            'mean': new_mean,
            'std': max(new_std, 0.1),  # Minimum std to avoid division by zero
            'samples': n
        }
        
        # Update log volume
        n_vol = baseline['log_volume']['samples']
        old_mean_vol = baseline['log_volume']['mean']
        
        n_vol += 1
        new_mean_vol = old_mean_vol + (log_volume - old_mean_vol) / n_vol
        
        if n_vol > 1:
            old_var_vol = baseline['log_volume']['std'] ** 2
            new_var_vol = ((n_vol - 1) * old_var_vol + (log_volume - old_mean_vol) * (log_volume - new_mean_vol)) / n_vol
            new_std_vol = new_var_vol ** 0.5
        else:
            new_std_vol = 1
        
        baseline['log_volume'] = {
            'mean': new_mean_vol,
            'std': max(new_std_vol, 1),
            'samples': n_vol
        }
    
    def get_expected_baseline(
        self,
        timestamp: Optional[datetime] = None
    ) -> Dict[str, Dict[str, float]]:
        """
        Get expected baseline for given time
        
        Returns best available baseline (hourly > daily > overall)
        """
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        hour = timestamp.hour
        day = timestamp.weekday()
        
        # Prefer hourly if we have enough samples (at least 10)
        if self.hourly_baselines[hour]['error_rate']['samples'] >= 10:
            return self.hourly_baselines[hour]
        
        # Fall back to daily if available
        if self.daily_baselines[day]['error_rate']['samples'] >= 10:
            return self.daily_baselines[day]
        
        # Fall back to overall
        return self.overall_baseline
    
    def is_anomalous(
        self,
        error_rate: float,
        log_volume: int,
        timestamp: Optional[datetime] = None,
        sensitivity: float = 2.0
    ) -> Tuple[bool, Optional[Dict]]:
        """
        Check if values are anomalous compared to learned baseline
        
        Args:
            error_rate: Current error rate
            log_volume: Current log volume
            timestamp: Time of measurement
            sensitivity: Number of standard deviations (default 2.0)
        
        Returns:
            (is_anomalous, details_dict)
        """
        baseline = self.get_expected_baseline(timestamp)
        
        # Not enough data yet
        if baseline['error_rate']['samples'] < 5:
            return False, None
        
        # Calculate z-scores
        error_mean = baseline['error_rate']['mean']
        error_std = baseline['error_rate']['std']
        error_z = (error_rate - error_mean) / error_std if error_std > 0 else 0
        
        volume_mean = baseline['log_volume']['mean']
        volume_std = baseline['log_volume']['std']
        volume_z = (log_volume - volume_mean) / volume_std if volume_std > 0 else 0
        
        # Check if beyond threshold
        is_error_anomalous = abs(error_z) > sensitivity
        is_volume_anomalous = abs(volume_z) > sensitivity
        
        if is_error_anomalous or is_volume_anomalous:
            details = {
                'error_rate': {
                    'current': error_rate,
                    'expected': error_mean,
                    'std': error_std,
                    'z_score': error_z,
                    'is_anomalous': is_error_anomalous
                },
                'log_volume': {
                    'current': log_volume,
                    'expected': volume_mean,
                    'std': volume_std,
                    'z_score': volume_z,
                    'is_anomalous': is_volume_anomalous
                },
                'baseline_samples': baseline['error_rate']['samples'],
                'sensitivity': sensitivity
            }
            
            logger.warning(
                "Anomaly detected via adaptive baseline",
                error_z_score=error_z,
                volume_z_score=volume_z,
                details=details
            )
            
            return True, details
        
        return False, None
    
    def get_confidence(self) -> float:
        """
        Get confidence in current baseline (0.0 to 1.0)
        
        Based on number of samples collected
        """
        samples = self.overall_baseline['error_rate']['samples']
        
        # Full confidence after 100 samples (~50 minutes)
        confidence = min(1.0, samples / 100)
        
        return confidence
    
    def _save_baselines(self):
        """Persist baselines to disk"""
        try:
            data = {
                'hourly_baselines': self.hourly_baselines,
                'daily_baselines': self.daily_baselines,
                'overall_baseline': self.overall_baseline,
                'last_updated': datetime.utcnow().isoformat()
            }
            
            self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.persistence_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info("Baselines saved", path=str(self.persistence_path))
        
        except Exception as e:
            logger.error("Failed to save baselines", error=str(e))
    
    def _load_baselines(self):
        """Load baselines from disk"""
        try:
            if not self.persistence_path.exists():
                logger.info("No existing baselines found, starting fresh")
                return
            
            with open(self.persistence_path, 'r') as f:
                data = json.load(f)
            
            # Convert string keys back to int
            self.hourly_baselines = {
                int(k): v for k, v in data['hourly_baselines'].items()
            }
            self.daily_baselines = {
                int(k): v for k, v in data['daily_baselines'].items()
            }
            self.overall_baseline = data['overall_baseline']
            
            samples = self.overall_baseline['error_rate']['samples']
            logger.info(
                "Baselines loaded",
                samples=samples,
                last_updated=data.get('last_updated')
            )
        
        except Exception as e:
            logger.error("Failed to load baselines", error=str(e))
    
    def get_summary(self) -> Dict:
        """Get summary of learned baselines"""
        return {
            'overall': self.overall_baseline,
            'confidence': self.get_confidence(),
            'total_samples': self.overall_baseline['error_rate']['samples'],
            'history_size': len(self.error_rate_history),
            'hours_with_data': sum(
                1 for h in self.hourly_baselines.values()
                if h['error_rate']['samples'] >= 10
            ),
            'days_with_data': sum(
                1 for d in self.daily_baselines.values()
                if d['error_rate']['samples'] >= 10
            )
        }


# Global adaptive baseline instance
adaptive_baseline = AdaptiveBaseline()
