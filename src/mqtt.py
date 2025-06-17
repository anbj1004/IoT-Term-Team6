import paho.mqtt.client as mqtt
import mysql.connector # MySQL 라이브러리 임포트
from mysql.connector import Error # MySQL 오류 처리를 위함
import json
import datetime
import time
import os

# --- 설정 ---
MQTT_BROKER_HOST = "192.168.78.221"  # ESP32 코드의 mqtt_server 와 동일하게 설정
MQTT_BROKER_PORT = 1883
MQTT_TOPIC_DATA = "sleep_sense/data"

# MySQL 접속 정보 (사용자 환경에 맞게 수정하세요)
MYSQL_HOST = "localhost"  # MySQL 서버 주소
MYSQL_USER = "root" # MySQL 사용자 이름
MYSQL_PASSWORD = "yuyu1234" # MySQL 비밀번호
MYSQL_DB_NAME = "sleep_db" # 사용할 데이터베이스 이름
TABLE_NAME = "usage_logs"

# --- MySQL 연결 함수 ---
def create_mysql_connection():
    connection = None
    try:
        connection = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DB_NAME
        )
        if connection.is_connected():
            print(f"Successfully connected to MySQL database: {MYSQL_DB_NAME}")
    except Error as e:
        print(f"Error while connecting to MySQL: {e}")
    return connection

# --- 데이터베이스 및 테이블 초기화 ---
def init_db():
    # 먼저 데이터베이스 자체가 존재하는지 확인하고, 없으면 생성 (일반적으로 DB는 미리 생성해두는 것이 좋음)
    try:
        # 데이터베이스를 명시하지 않고 연결 시도 (서버 레벨 작업용)
        conn_server = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD
        )
        cursor_server = conn_server.cursor()
        cursor_server.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        print(f"Database '{MYSQL_DB_NAME}' checked/created.")
        cursor_server.close()
        conn_server.close()
    except Error as e:
        print(f"Error creating/checking database '{MYSQL_DB_NAME}': {e}")
        # DB 생성 실패 시 프로그램 종료 또는 다른 처리
        return 

    # 지정된 데이터베이스에 연결
    conn = create_mysql_connection()
    if conn is None or not conn.is_connected():
        print("Could not connect to MySQL database for table initialization. Exiting.")
        exit() # 연결 실패 시 종료

    cursor = conn.cursor()
    try:
        # 테이블이 없으면 생성
        # logged_at: 이 로거가 데이터를 받은 시간
        # esp_timestamp: ESP32가 측정한 시간을 ISO 형식 문자열로 저장 (DATETIME 타입 사용 가능)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id INT AUTO_INCREMENT PRIMARY KEY,
                client_id VARCHAR(255),
                usage_date VARCHAR(10),
                start_time VARCHAR(8),
                used_sec INT,
                esp_timestamp VARCHAR(20), 
                logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """) # ENGINE과 CHARSET 명시
        conn.commit()
        print(f"Table '{TABLE_NAME}' in database '{MYSQL_DB_NAME}' initialized.")
    except Error as e:
        print(f"Error creating table '{TABLE_NAME}': {e}")
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

# --- MQTT 콜백 함수 ---
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"Connected to MQTT Broker: {MQTT_BROKER_HOST}")
        client.subscribe(MQTT_TOPIC_DATA)
        print(f"Subscribed to topic: {MQTT_TOPIC_DATA}")
    else:
        print(f"Failed to connect, return code {rc}\n")

def on_message(client, userdata, msg):
    conn = None # Connection 객체 초기화
    try:
        payload_str = msg.payload.decode("utf-8")
        print(f"Received message on topic '{msg.topic}': {payload_str}")
        
        if msg.topic == MQTT_TOPIC_DATA:
            data = json.loads(payload_str)
            
            client_id = data.get("client_id")
            usage_date = data.get("usage_date") # YYYY-MM-DD
            start_time_str = data.get("start_time") # HH:MM:SS
            used_sec = data.get("used_sec")

            if not all([client_id, usage_date, start_time_str, used_sec is not None]):
                print("Error: Missing required fields in JSON payload.")
                return

            esp_dt_str = f"{usage_date}T{start_time_str}" # ISO 8601 유사 형태 (여기서는 TEXT로 저장)
            # 만약 MySQL의 DATETIME으로 저장하려면:
            # from dateutil import parser
            # esp_datetime_obj = parser.parse(f"{usage_date} {start_time_str}")
            # 그리고 INSERT 시 esp_datetime_obj를 전달. 테이블 컬럼도 DATETIME 타입으로.

            conn = create_mysql_connection()
            if conn is None or not conn.is_connected():
                print("MySQL connection lost or not available for saving data.")
                return

            cursor = conn.cursor()
            
            sql_insert_query = f"""
                INSERT INTO {TABLE_NAME} (client_id, usage_date, start_time, used_sec, esp_timestamp)
                VALUES (%s, %s, %s, %s, %s)
            """
            # MySQL 플레이스홀더는 %s 이며, 데이터는 튜플로 전달
            insert_tuple = (client_id, usage_date, start_time_str, used_sec, esp_dt_str)
            
            cursor.execute(sql_insert_query, insert_tuple)
            conn.commit()
            print(f"Data saved to MySQL DB: {data}")

    except json.JSONDecodeError:
        print(f"Error decoding JSON: {payload_str}")
    except Error as e: # MySQL 관련 오류 처리
        print(f"Error interacting with MySQL in on_message: {e}")
    except Exception as e:
        print(f"An error occurred in on_message: {e}")
    finally:
        if conn and conn.is_connected(): # conn이 None이 아니고, 연결되어 있을 때만 close
            # cursor.close() # cursor는 execute 후 자동으로 닫히거나, with 문 사용 시 자동 관리
            conn.close()
            # print("MySQL connection closed.")


# --- 메인 로직 ---
if __name__ == "__main__":
    # MySQL 서버에 접속하여 DB 및 테이블 확인/생성
    # 이 작업은 스크립트 시작 시 한 번만 수행합니다.
    init_db() 

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="python_logger_mysql_" + os.urandom(4).hex())


    client.on_connect = on_connect
    client.on_message = on_message

    retry_count = 0
    max_retries = 5
    retry_delay = 5  # seconds

    while retry_count < max_retries:
        try:
            client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, 60)
            break 
        except Exception as e:
            retry_count += 1
            print(f"MQTT Connection failed (attempt {retry_count}/{max_retries}): {e}")
            if retry_count >= max_retries:
                print("Max connection retries reached. Exiting.")
                exit()
            print(f"Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
    
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("Disconnecting from MQTT broker...")
        if client.is_connected():
             client.disconnect()
        print("Disconnected.")
    except Exception as e:
        print(f"An error occurred in MQTT loop: {e}")
        if client.is_connected():
            client.disconnect()