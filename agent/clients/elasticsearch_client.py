"""
Elasticsearch client for querying logs
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import httpx
from config.settings import settings
from utils.logger import logger


class ElasticsearchClient:
    """Client for Elasticsearch API"""
    
    def __init__(self):
        self.base_url = settings.elasticsearch_url
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def health_check(self) -> bool:
        """Check if Elasticsearch is healthy"""
        try:
            response = await self.client.get(f"{self.base_url}/_cluster/health")
            data = response.json()
            status = data.get("status")
            logger.info("Elasticsearch health check", status=status)
            return status in ["green", "yellow"]
        except Exception as e:
            logger.error("Elasticsearch health check failed", error=str(e))
            return False
    
    async def count_logs(self, index: str = "logs-*", query: Optional[Dict] = None) -> int:
        """Count documents matching query"""
        try:
            url = f"{self.base_url}/{index}/_count"
            if query:
                response = await self.client.post(url, json={"query": query})
            else:
                response = await self.client.get(url)
            
            data = response.json()
            count = data.get("count", 0)
            return count
        except Exception as e:
            logger.error("Failed to count logs", error=str(e))
            return 0
    
    async def search_logs(
        self,
        index: str = "logs-*",
        query: Optional[Dict] = None,
        size: int = 100,
        sort: Optional[List] = None
    ) -> List[Dict[str, Any]]:
        """Search logs"""
        try:
            url = f"{self.base_url}/{index}/_search"
            
            body = {
                "size": size,
                "query": query or {"match_all": {}},
            }
            
            if sort:
                body["sort"] = sort
            else:
                body["sort"] = [{"@timestamp": "desc"}]
            
            response = await self.client.post(url, json=body)
            data = response.json()
            
            hits = data.get("hits", {}).get("hits", [])
            logs = [hit["_source"] for hit in hits]
            
            logger.info("Searched logs", count=len(logs), index=index)
            return logs
            
        except Exception as e:
            logger.error("Failed to search logs", error=str(e))
            return []
    
    async def get_recent_errors(
        self,
        minutes: int = 5,
        size: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent ERROR logs"""
        query = {
            "bool": {
                "must": [
                    {
                        "match": {
                            "message": "ERROR"
                        }
                    },
                    {
                        "range": {
                            "@timestamp": {
                                "gte": f"now-{minutes}m"
                            }
                        }
                    }
                ]
            }
        }
        
        return await self.search_logs(query=query, size=size)
    
    async def aggregate_by_field(
        self,
        field: str,
        index: str = "logs-*",
        query: Optional[Dict] = None,
        size: int = 10
    ) -> Dict[str, int]:
        """Aggregate logs by field"""
        try:
            url = f"{self.base_url}/{index}/_search"
            
            body = {
                "size": 0,
                "query": query or {"match_all": {}},
                "aggs": {
                    "by_field": {
                        "terms": {
                            "field": f"{field}.keyword",
                            "size": size
                        }
                    }
                }
            }
            
            response = await self.client.post(url, json=body)
            data = response.json()
            
            buckets = data.get("aggregations", {}).get("by_field", {}).get("buckets", [])
            result = {bucket["key"]: bucket["doc_count"] for bucket in buckets}
            
            return result
            
        except Exception as e:
            logger.error("Failed to aggregate logs", error=str(e), field=field)
            return {}
    
    async def close(self):
        """Close client"""
        await self.client.aclose()


# Global client instance
es_client = ElasticsearchClient()
