import requests
import json
import os
from typing import Optional, Dict, Any, List

WIALON_API_URL = os.getenv("WIALON_API_URL", "https://hst-api.wialon.com/wialon/ajax.html")

def wialon_login(token: str, fl: int = 1) -> Dict[str, Any]:
    params = {
        "svc": "token/login",
        "params": json.dumps({"token": token, "fl": fl})
    }
    resp = requests.get(WIALON_API_URL, params=params)
    return resp.json()

async def get_available_objects(sid: str) -> List[Dict[str, Any]]:
    """Получает список доступных объектов с их правами доступа
    
    Args:
        sid: ID сессии Wialon
        
    Returns:
        List[Dict]: Список объектов с информацией о правах доступа
    """
    params = {
        "svc": "core/search_items",
        "params": json.dumps({
            "spec": {
                "itemsType": "avl_unit",
                "propName": "sys_name",
                "propValueMask": "*",
                "sortType": "sys_name"
            },
            "force": 1,
            "flags": 1,
            "from": 0,
            "to": 0
        }),
        "sid": sid
    }
    
    resp = requests.get(WIALON_API_URL, params=params)
    result = resp.json()
    
    if "error" in result:
        return []
    
    objects = []
    for item in result.get("items", []):
        obj_data = {
            "id": item.get("id"),
            "nm": item.get("nm"),  # name
            "type": "avl_unit",
            "uacl": item.get("uacl", 0),  # user access level
            "fl": item.get("fl", 0),  # flags
            "extra": {
                "creator": item.get("cr", 0),
                "creation_time": item.get("ct", 0),
                "last_message": item.get("lmsg", {}),
                "group_id": item.get("gd", 0)
            }
        }
        objects.append(obj_data)
    
    return objects

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
