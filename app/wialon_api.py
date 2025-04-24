import requests
import json
import os
from typing import Optional, Dict, Any

WIALON_API_URL = os.getenv("WIALON_API_URL", "https://hst-api.wialon.com/wialon/ajax.html")

def wialon_login(token: str, fl: int = 1) -> Dict[str, Any]:
    params = {
        "svc": "token/login",
        "params": json.dumps({"token": token, "fl": fl})
    }
    resp = requests.get(WIALON_API_URL, params=params)
    return resp.json()

def create_token(session_id: str, user_id: int, access_rights: int, duration: int, label: str = "", call_mode: str = "create") -> Dict[str, Any]:
    params = {
        "svc": "token/update",
        "sid": session_id,
        "params": json.dumps({
            "callMode": call_mode,
            "userId": user_id,
            "duration": duration,
            "access": access_rights,
            "label": label
        })
    }
    resp = requests.post(WIALON_API_URL, params=params)
    return resp.json()

def update_token(session_id: str, token: str, access_rights: Optional[int] = None, duration: Optional[int] = None, label: Optional[str] = None) -> Dict[str, Any]:
    params_obj = {
        "callMode": "update",
        "token": token
    }
    if access_rights is not None:
        params_obj["access"] = access_rights
    if duration is not None:
        params_obj["duration"] = duration
    if label is not None:
        params_obj["label"] = label
    params = {
        "svc": "token/update",
        "sid": session_id,
        "params": json.dumps(params_obj)
    }
    resp = requests.post(WIALON_API_URL, params=params)
    return resp.json()

def delete_token(session_id: str, token: str) -> Dict[str, Any]:
    params = {
        "svc": "token/update",
        "sid": session_id,
        "params": json.dumps({
            "callMode": "delete",
            "token": token
        })
    }
    resp = requests.post(WIALON_API_URL, params=params)
    return resp.json()

def list_tokens(session_id: str, user_id: int) -> Dict[str, Any]:
    params = {
        "svc": "token/list",
        "sid": session_id,
        "params": json.dumps({"userId": user_id})
    }
    resp = requests.post(WIALON_API_URL, params=params)
    return resp.json()

def check_token(token: str) -> Dict[str, Any]:
    params = {
        "svc": "token/login",
        "params": json.dumps({"token": token, "fl": 1})
    }
    resp = requests.get(WIALON_API_URL, params=params)
    return resp.json()
