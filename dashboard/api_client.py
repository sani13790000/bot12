"""Galaxy Vast Streamlit Dashboard — API Client."""
import os
from typing import Any, Dict, Optional

import requests


class APIClient:
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")

    def health(self) -> Dict[str, Any]:
        try:
            r = requests.get(f"{self.base_url}/health", timeout=5)
            return r.json()
        except Exception as exc:
            return {"status": "unreachable", "error": str(exc)}

    def run_backtest(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = requests.post(f"{self.base_url}/research/institutional/backtest", json=payload, timeout=120)
        return r.json()

    def run_walk_forward(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = requests.post(f"{self.base_url}/research/institutional/walk-forward", json=payload, timeout=180)
        return r.json()

    def run_monte_carlo(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = requests.post(f"{self.base_url}/research/institutional/monte-carlo", json=payload, timeout=120)
        return r.json()

    def explain(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = requests.post(f"{self.base_url}/research/institutional/explain", json=payload, timeout=30)
        return r.json()

    def portfolio(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = requests.post(f"{self.base_url}/research/institutional/portfolio", json=payload, timeout=30)
        return r.json()

    def correlation(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = requests.post(f"{self.base_url}/research/institutional/correlation", json=payload, timeout=30)
        return r.json()

    def rl_train(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = requests.post(f"{self.base_url}/research/institutional/rl/train", json=payload, timeout=300)
        return r.json()

    def rl_predict(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = requests.post(f"{self.base_url}/research/institutional/rl/predict", json=payload, timeout=60)
        return r.json()
