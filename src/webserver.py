from flask import Flask, request, render_template_string, jsonify, send_file
import paho.mqtt.client as mqtt
import mysql.connector
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io

app = Flask(__name__)

# MQTT settings
MQTT_BROKER = 'localhost'
MQTT_PORT = 1883
MQTT_TOPIC_TIMER = '/phone/timer_setting'

# Default timer in minutes
timer_setting = 5

# MQTT client initialization
mqtt_client = mqtt.Client()
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
mqtt_client.loop_start()

# MySQL connection config
db_config = {
    "host": "localhost",
    "user": "root",
    "password": "yuyu1234",
    "database": "sleep_db"
}

TABLE_NAME = 'usage_logs'

@app.route('/')
def index():
    html = '''
    <html>
    <head><title>Timer Setting</title></head>
    <body>
      <h2>Set Smartphone Usage Timer (minutes)</h2>
      <form id="timerForm">
        <input type="number" id="timerInput" value="{{timer}}" min="1" max="180" />
        <button type="submit">Set</button>
      </form>
      <p id="result"></p>
      <a href="/usage">📊 View Usage Records</a>

      <script>
        const form = document.getElementById('timerForm');
        const input = document.getElementById('timerInput');
        const result = document.getElementById('result');

        form.addEventListener('submit', e => {
          e.preventDefault();
          fetch('/api/set_timer', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({timer: Number(input.value)})
          })
          .then(res => res.json())
          .then(data => {
            result.textContent = data.message;
          });
        });
      </script>
    </body>
    </html>
    '''
    return render_template_string(html, timer=timer_setting)

@app.route('/api/set_timer', methods=['POST'])
def set_timer():
    global timer_setting
    data = request.get_json()
    timer = data.get('timer')

    if not isinstance(timer, int) or timer < 1 or timer > 180:
        return jsonify({'message': 'Please enter a value between 1 and 180.'}), 400

    timer_setting = timer
    mqtt_client.publish(MQTT_TOPIC_TIMER, str(timer))
    return jsonify({'message': f'Timer set to {timer} minutes.'})

@app.route('/usage')
def usage_chart():
    conn = None
    cursor = None
    rows = []
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"""
            SELECT id, client_id, usage_date, start_time, used_sec, esp_timestamp, logged_at 
            FROM {TABLE_NAME} 
            ORDER BY usage_date DESC, start_time DESC 
            LIMIT 100
        """)
        rows = cursor.fetchall()
    except Exception as e:
        print("DB error:", e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    html = '''
    <html>
    <head>
      <title>Usage Records</title>
      <style>
        table, th, td { border: 1px solid black; border-collapse: collapse; padding: 5px; }
        th { background-color: #eee; }
      </style>
    </head>
    <body>
      <h2>Daily Smartphone Usage Time</h2>
      <img src="/usage/chart.png" alt="Usage Chart" />
      <p><a href="/">← Back to Timer Setting</a></p>

      <h3>Last 100 Usage Records</h3>
      <table>
        <tr>
          <th>ID</th><th>Client ID</th><th>Usage Date</th><th>Start Time</th><th>Used Seconds</th><th>ESP Timestamp</th><th>Logged At</th>
        </tr>
        {% for row in rows %}
        <tr>
          <td>{{ row.id }}</td>
          <td>{{ row.client_id }}</td>
          <td>{{ row.usage_date }}</td>
          <td>{{ row.start_time }}</td>
          <td>{{ row.used_sec }}</td>
          <td>{{ row.esp_timestamp }}</td>
          <td>{{ row.logged_at }}</td>
        </tr>
        {% endfor %}
      </table>
    </body>
    </html>
    '''
    return render_template_string(html, rows=rows)

@app.route('/usage/chart.png')
def usage_chart_img():
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        # Create table if not exists (optional)
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
        """)
        conn.commit()

        query = f"""
        SELECT usage_date, SUM(used_sec)
        FROM {TABLE_NAME}
        GROUP BY usage_date
        ORDER BY usage_date;
        """
        cursor.execute(query)
        results = cursor.fetchall()

        if not results:
            return "No data available", 404

        dates = [datetime.strptime(row[0], "%Y-%m-%d").strftime("%m-%d") for row in results]
        minutes = [round(row[1] / 60, 2) for row in results]

        plt.figure(figsize=(10, 4))
        plt.bar(dates, minutes, color='skyblue')
        plt.title("Daily Smartphone Usage Time (minutes)")
        plt.xlabel("Date")
        plt.ylabel("Usage Time (minutes)")
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()

        return send_file(buf, mimetype='image/png')

    except mysql.connector.Error as err:
        print("MySQL error:", err)
        return "DB error", 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
