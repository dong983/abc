"""
8주차 — 공공데이터 API 연동 (완성 예시)

한국환경공단_에어코리아_대기오염정보(data.go.kr)에서 시도별 실시간 측정정보를 받아
필요한 값만 뽑아 정리한다. 실패(키 미승인·네트워크 오류 등)하면 샘플 데이터로 대체한다.

    python opendata.py   # 단독 실행 — 원본 JSON을 그대로 출력해 구조 확인용
"""
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getCtprvnRltmMesureDnsty"
SAMPLE_PATH = Path(__file__).resolve().parent / "data" / "sample_air_quality.json"

GRADE_LABELS = {"1": "좋음", "2": "보통", "3": "나쁨", "4": "매우나쁨"}


def fetch_raw(sido="인천"):
    api_key = os.environ.get("PUBLIC_DATA_API_KEY")
    params = {
        "serviceKey": api_key,
        "returnType": "json",
        "numOfRows": 100,
        "pageNo": 1,
        "sidoName": sido,
        "ver": "1.3",
    }
    response = requests.get(API_URL, params=params, timeout=5)
    return response.json()


def parse_items(raw):
    items = raw["response"]["body"]["items"]
    result = []
    for item in items:
        result.append({
            "station": item.get("stationName", "알 수 없음"),
            "pm10": int(item.get("pm10Value")) if str(item.get("pm10Value") or "").isdigit() else 0,
            "pm25": int(item.get("pm25Value")) if str(item.get("pm25Value") or "").isdigit() else 0,
            "grade": GRADE_LABELS.get(item.get("khaiGrade"), "정보없음"),
        })
    result.sort(key=lambda row: row["pm10"], reverse=True)
    return result


def load_sample():
    with open(SAMPLE_PATH, encoding="utf-8") as f:
        return parse_items(json.load(f))


def fetch_air_quality(sido="인천"):
    """성공하면 (실시간 데이터, "live"), 실패하면 (샘플 데이터, "sample")을 돌려준다.

    이 함수는 예외를 밖으로 던지지 않는다 — /dashboard가 항상 화면을 그릴 수 있어야 한다.
    """
    try:
        raw = fetch_raw(sido)
        return parse_items(raw), "live"
    except Exception as e:
        print(e)
        return load_sample(), "sample"


if __name__ == "__main__":
    print(fetch_raw())
