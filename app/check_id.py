# Рабочий файл который делает правильные запросы по исходному токенк    
# 1. Авторизация
# 2. Создание токена
# 3. Обновление токена


import json
import requests
import urllib.parse

# URL API Wialon
wialon_api_url = "https://hst-api.wialon.com/wialon/ajax.html"

# Исходный токен для авторизации (замените на актуальное значение)
source_token = "256b9eacb5499330773461b9c2b261152B735751567316923E8CC8A610CB31BD79B2014C"

# -------------------------------------------------------------------
# Шаг 1: Авторизация через token/login
login_payload = {
    "svc": "token/login",
    "params": json.dumps({
        "token": source_token,
        "fl": 1
    })
}

print("Запрос token/login:")
print("Параметры:", login_payload["params"])

login_response = requests.get(wialon_api_url, params=login_payload)
login_result = login_response.json()
print("Результат token/login:")
print(json.dumps(login_result, indent=4, ensure_ascii=False))

if "error" in login_result:
    print("Ошибка авторизации:", login_result.get("error"), login_result.get("reason"))
    exit(1)

session_id = login_result.get("eid")
if not session_id:
    print("Не удалось получить SID")
    exit(1)

user_info = login_result.get("user", {})
user_id = user_info.get("id", 24313876)  # Используем значение по умолчанию, если id не найден
print("Полученный SID:", session_id)
print("User ID:", user_id)

# -------------------------------------------------------------------
# Шаг 2: Формирование запроса для создания токена согласно рабочему примеру:
# {{base_url}}/wialon/ajax.html?svc=token/update&params={
#    "callMode":"create",
#    "userId":"{{user_id}}",
#    "h":"TOKEN",
#    "app":"Wialon Hosting – a platform for GPS monitoring",
#    "at":0,
#    "dur":0,
#    "fl":512,
#    "p":"{}",
#    "items":[]
# }&sid={{sessionId}}

create_payload = {
    "callMode": "create",
    "userId": str(user_id),  # обязательно передаём в виде строки
    "h": "TOKEN",
    "app": "Wialon Hosting – a platform for GPS monitoring",
    "at": 0,
    "dur": 0,
    "fl": 512,
    "p": "{}",  # именно строка "{}"
    "items": []
}

non_encoded_params = json.dumps(create_payload, ensure_ascii=False)
create_request_payload = {
    "svc": "token/update",  # согласно примеру используем token/update
    "params": non_encoded_params,
    "sid": session_id
}

print("\nЗапрос token/create (словарь параметров):")
print(json.dumps(create_request_payload, indent=4, ensure_ascii=False))

create_response = requests.post(wialon_api_url, params=create_request_payload)
print("\nURL запроса token/create:")
print(create_response.request.url)

create_result = create_response.json()
print("\nРезультат token/create:")
print(json.dumps(create_result, indent=4, ensure_ascii=False))

if "error" in create_result:
    print("Ошибка создания токена:", create_result.get("error"), create_result.get("reason"))
else:
    new_token = create_result.get("h")
    print("Новый токен:", new_token)

# -------------------------------------------------------------------
# Шаг 3: Обновление токена (token/update)
# По примеру из Postman URL должен выглядеть так:
# {{base_url}}/wialon/ajax.html?svc=token/update&params={"callMode":"create",
# "userId":"{{user_id}}","h":"TOKEN","app":"Wialon Hosting – a platform for GPS monitoring",
# "at":0,"dur":0,"fl":512,"p":"{}","items":[]} &sid={{sessionId}}

update_payload = {
    "callMode": "create",  # согласно пример, здесь "create", а не "update"
    "userId": str(user_id),  # обязательно передаём userId как строку
    "h": "TOKEN",           # жёстко заданное значение "TOKEN"
    "app": "Wialon Hosting – a platform for GPS monitoring",
    "at": 0,
    "dur": 0,               # длительность 0 для обновления
    "fl": 512,
    "p": "{}",              # именно строка "{}"
    "items": []
}

non_encoded_update_params = json.dumps(update_payload, ensure_ascii=False)
encoded_update_params = urllib.parse.quote(non_encoded_update_params)

print("\nПараметры для token/update (не закодированные):")
print(non_encoded_update_params)
print("\nЗакодированные параметры для token/update:")
print(encoded_update_params)

update_request_payload = {
    "svc": "token/update",
    "params": non_encoded_update_params,
    "sid": session_id
}

print("\nЗапрос token/update (словарь параметров):")
print(json.dumps(update_request_payload, indent=4, ensure_ascii=False))

update_response = requests.post(wialon_api_url, params=update_request_payload)
print("\nURL запроса token/update:")
print(update_response.request.url)
update_result = update_response.json()
print("\nРезультат token/update:")
print(json.dumps(update_result, indent=4, ensure_ascii=False))

# Шаг 2: Запрос данных о сервисах через account/get_account_data
# Для получения данных по текущей учетной записи согласно документации используем:
# "id": 0 и "type": "services"
account_payload = {
    "id": 0,
    "type": "services"
}

data = {
    "svc": "account/get_account_data",
    "params": json.dumps(account_payload)
}

# Передаём SID отдельно в качестве query-параметра
params = {
    "sid": session_id
}
