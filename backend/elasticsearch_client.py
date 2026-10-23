import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_ES_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
DEFAULT_INDEX = os.getenv("ELASTICSEARCH_INDEX", "recovery-audit-decisions")


def build_elasticsearch_query(
    q: Optional[str] = None,
    failure_code: Optional[str] = None,
    action: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Pure function building an Elasticsearch Query DSL payload with filters and aggregations.
    """
    must_clauses: List[Dict[str, Any]] = []
    filter_clauses: List[Dict[str, Any]] = []

    if q and q.strip():
        search_term = q.strip()
        must_clauses.append(
            {
                "multi_match": {
                    "query": search_term,
                    "fields": [
                        "payment_id^3",
                        "customer_id^2",
                        "failure_code",
                        "policy_reason",
                        "chosen_action",
                        "execution_result",
                        "bank",
                    ],
                    "type": "best_fields",
                }
            }
        )

    if failure_code and failure_code.strip():
        filter_clauses.append(
            {"term": {"failure_code.keyword": failure_code.strip().upper()}}
        )

    if action and action.strip():
        action_val = action.strip().upper()
        filter_clauses.append(
            {
                "bool": {
                    "should": [
                        {"term": {"chosen_action.keyword": action_val}},
                        {"term": {"executed_action.keyword": action_val}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )

    if from_date or to_date:
        range_clause: Dict[str, Any] = {}
        if from_date:
            range_clause["gte"] = from_date
        if to_date:
            range_clause["lte"] = to_date
        filter_clauses.append({"range": {"timestamp": range_clause}})

    query_body: Dict[str, Any] = {
        "bool": {
            "must": must_clauses if must_clauses else [{"match_all": {}}],
            "filter": filter_clauses,
        }
    }

    return {
        "from": max(0, offset),
        "size": max(1, min(limit, 500)),
        "sort": [{"timestamp": {"order": "desc", "unmapped_type": "date"}}],
        "query": query_body,
        "aggs": {
            "by_action": {
                "terms": {
                    "field": "chosen_action.keyword",
                    "size": 20,
                    "missing": "UNKNOWN",
                }
            },
            "by_outcome": {
                "terms": {
                    "field": "execution_result.keyword",
                    "size": 20,
                    "missing": "PENDING",
                }
            },
        },
    }


class ElasticsearchAuditStore:
    def __init__(self, es_url: Optional[str] = None, index_name: str = DEFAULT_INDEX):
        self.es_url = es_url or DEFAULT_ES_URL
        self.index_name = index_name
        self._client = None
        self._available: Optional[bool] = None

    def _get_client(self):
        if self._client is None:
            try:
                from elasticsearch import Elasticsearch

                self._client = Elasticsearch(
                    self.es_url,
                    request_timeout=1.5,
                    max_retries=1,
                    retry_on_timeout=False,
                )
            except Exception as e:
                logger.warning(f"Could not initialize Elasticsearch client: {e}")
                self._client = None
        return self._client

    def is_healthy(self) -> bool:
        client = self._get_client()
        if client is None:
            return False
        try:
            return bool(client.ping())
        except Exception:
            return False

    def ensure_index(self) -> bool:
        client = self._get_client()
        if client is None:
            return False
        try:
            if not client.indices.exists(index=self.index_name):
                mapping = {
                    "mappings": {
                        "properties": {
                            "payment_id": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                            "customer_id": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                            "failure_code": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                            "chosen_action": {"type": "keyword"},
                            "recommended_action": {"type": "keyword"},
                            "executed_action": {"type": "keyword"},
                            "expected_value": {"type": "double"},
                            "policy_allowed": {"type": "boolean"},
                            "policy_reason": {"type": "text"},
                            "policy_outcome": {"type": "keyword"},
                            "execution_result": {"type": "keyword"},
                            "outcome": {"type": "keyword"},
                            "recovered": {"type": "boolean"},
                            "amount": {"type": "double"},
                            "timestamp": {"type": "date"},
                            "bank": {"type": "keyword"},
                            "payment_method": {"type": "keyword"},
                        }
                    }
                }
                client.indices.create(index=self.index_name, body=mapping)
            return True
        except Exception as e:
            logger.warning(f"Elasticsearch index ensure failed for '{self.index_name}': {e}")
            return False

    def index_decision(self, event: Dict[str, Any]) -> bool:
        client = self._get_client()
        if client is None:
            return False
        try:
            doc = {
                "payment_id": str(event.get("payment_id", "")),
                "customer_id": str(event.get("customer_id", "")),
                "amount": float(event.get("amount", 0.0) or 0.0),
                "failure_code": str(event.get("failure_code", "")),
                "chosen_action": str(event.get("executed_action") or event.get("recommended_action") or "NO_ACTION"),
                "recommended_action": str(event.get("recommended_action", "NO_ACTION")),
                "executed_action": str(event.get("executed_action", "NO_ACTION")),
                "expected_value": float(event.get("expected_value", 0.0) or 0.0),
                "policy_allowed": bool(event.get("policy_allowed", False)),
                "policy_reason": str(event.get("policy_reason", "")),
                "policy_outcome": "ALLOWED" if event.get("policy_allowed") else "BLOCKED",
                "execution_result": str(
                    event.get("outcome")
                    or ("RECOVERED" if event.get("recovered") is True else "FAILED" if event.get("recovered") is False else "PENDING")
                ),
                "outcome": event.get("outcome"),
                "recovered": event.get("recovered"),
                "timestamp": str(event.get("timestamp", "")),
                "bank": event.get("bank"),
                "payment_method": event.get("payment_method"),
            }
            client.index(
                index=self.index_name,
                id=doc["payment_id"],
                document=doc,
                refresh=False,
            )
            return True
        except Exception as e:
            logger.debug(f"Elasticsearch indexing skipped/failed for payment_id={event.get('payment_id')}: {e}")
            return False

    def search(
        self,
        q: Optional[str] = None,
        failure_code: Optional[str] = None,
        action: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Optional[Dict[str, Any]]:
        client = self._get_client()
        if client is None:
            return None
        try:
            body = build_elasticsearch_query(
                q=q,
                failure_code=failure_code,
                action=action,
                from_date=from_date,
                to_date=to_date,
                limit=limit,
                offset=offset,
            )
            res = client.search(index=self.index_name, body=body)
            hits_meta = res.get("hits", {})
            raw_hits = hits_meta.get("hits", [])
            total_val = hits_meta.get("total", {})
            total = total_val.get("value", 0) if isinstance(total_val, dict) else int(total_val or 0)

            results: List[Dict[str, Any]] = []
            for hit in raw_hits:
                src = hit.get("_source", {})
                results.append(src)

            aggs = res.get("aggregations", {})
            action_buckets = aggs.get("by_action", {}).get("buckets", [])
            outcome_buckets = aggs.get("by_outcome", {}).get("buckets", [])

            action_counts = {b["key"]: b["doc_count"] for b in action_buckets}
            outcome_counts = {b["key"]: b["doc_count"] for b in outcome_buckets}

            return {
                "total": total,
                "results": results,
                "aggregations": {
                    "by_action": action_counts,
                    "by_outcome": outcome_counts,
                },
                "source": "elasticsearch",
            }
        except Exception as e:
            logger.info(f"Elasticsearch search failed, triggering DB fallback: {e}")
            return None
