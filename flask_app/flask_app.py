import flask
from flask import request, jsonify
from flask import render_template
from connect_mysql import connect_to_db
from flask_cors import CORS
from datetime import datetime, timedelta, time
import pytz

app = flask.Flask(__name__)
CORS(app)

app.config['DEBUG'] = True


@app.route('/') # index page
def index():
    return render_template('index.html')

@app.route('/api/v1/update', methods=['POST'])
def update():
    # 尝试获取 JSON 数组
    records = request.get_json()
    if not records:
        return "No data provided", 400

    # 连接到数据库
    cnx = connect_to_db()
    if not cnx:
        return "Database connection failed", 500

    try:
        cursor = cnx.cursor()
        query = "INSERT INTO iot_records (record_time, temperature, humidity) VALUES (%s, %s, %s)"
        # 遍历数组中的每一条记录
        for data in records:
            if 'time' in data and 'temperature' in data and 'humidity' in data:
                cursor.execute(query, (data['time'], data['temperature'], data['humidity']))
            else:
                cnx.rollback()
                return "Missing data fields in some records", 400
        cnx.commit()
        return "Records inserted successfully", 200
    except Error as e:
        cnx.rollback()
        print("Error while inserting data", e)
        return "Database error", 500
    finally:
        cursor.close()
        cnx.close()


# get all records from the database
@app.route('/api/v1/get_all', methods=['GET'])
def get_all():
    cnx = connect_to_db()
    if cnx:
        cursor = cnx.cursor(dictionary = True)
        cursor.execute("SELECT * FROM iot_records ORDER BY record_time DESC LIMIT 10000")
        records = cursor.fetchall()
        cursor.close()
        cnx.close()
        return jsonify(records)
    return jsonify([])

@app.route('/api/v1/get_by_date', methods=['GET'])
def get_by_date():
    date_str = request.args.get('date')  # 从请求中获取日期参数
    timezone_str = request.args.get('timezone', 'UTC')  # 获取时区参数，默认使用 UTC
    if not date_str:
        return "No date provided", 400

    # 尝试将日期字符串转换为日期对象，确保其格式正确
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return "Invalid date format. Please use YYYY-MM-DD format.", 400

    # 获取用户时区
    try:
        timezone = pytz.timezone(timezone_str)
    except pytz.UnknownTimeZoneError:
        return "Invalid timezone.", 400

    # 将日期转换为目标时区的一天的开始和结束时间
    start_of_day = timezone.localize(datetime.combine(date_obj, datetime.min.time()))
    end_of_day = timezone.localize(datetime.combine(date_obj + timedelta(days=1), datetime.min.time()))

    # 将时间转换为 UTC
    start_of_day_utc = start_of_day.astimezone(pytz.utc)
    end_of_day_utc = end_of_day.astimezone(pytz.utc)

    cnx = connect_to_db()
    if cnx:
        cursor = cnx.cursor(dictionary=True)
        query = """
            SELECT * FROM iot_records
            WHERE record_time >= %s AND record_time < %s
            ORDER BY record_time DESC
            """
        cursor.execute(query, (start_of_day_utc.strftime('%Y-%m-%d %H:%M:%S'), end_of_day_utc.strftime('%Y-%m-%d %H:%M:%S')))
        records = cursor.fetchall()
        cursor.close()
        cnx.close()
        return jsonify(records)
    else:
        return jsonify([]), 500


@app.route('/api/v1/hourly_data')
def hourly_data():
    # 获取查询参数中的日期或默认使用当前日期
    date_str = request.args.get('date')
    timezone_str = request.args.get('timezone', 'UTC')  # 默认使用 UTC
    try:
        # 验证并格式化日期
        date = datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return "Invalid date format. Use YYYY-MM-DD.", 400

    # 获取用户时区
    try:
        timezone = pytz.timezone(timezone_str)
    except pytz.UnknownTimeZoneError:
        return "Invalid timezone.", 400

    # 将日期转换为目标时区的开始和结束时间
    start_of_day = datetime.combine(date, time(0, 0, 0))
    end_of_day = datetime.combine(date + timedelta(days=1), time(0, 0, 0))

    # 将本地时间转换为目标时区时间
    start_of_day_local = timezone.localize(start_of_day)
    end_of_day_local = timezone.localize(end_of_day)

    # 将时间转换为 UTC
    start_of_day_utc = start_of_day_local.astimezone(pytz.utc)
    end_of_day_utc = end_of_day_local.astimezone(pytz.utc)

    print(f"Start of day (local): {start_of_day_local}")
    print(f"End of day (local): {end_of_day_local}")
    print(f"Start of day (UTC): {start_of_day_utc}")
    print(f"End of day (UTC): {end_of_day_utc}")

    cnx = connect_to_db()
    if cnx:
        cursor = cnx.cursor(dictionary=True)
        query = """
            SELECT DATE_FORMAT(record_time, '%Y-%m-%d %H:00:00') AS hour,
                   ROUND(AVG(temperature), 1) AS average_temperature,
                   ROUND(AVG(humidity), 1) AS average_humidity
            FROM iot_records
            WHERE record_time >= %s AND record_time < %s
            GROUP BY DATE_FORMAT(record_time, '%Y-%m-%d %H')
            ORDER BY hour;
            """
        cursor.execute(query, (start_of_day_utc.strftime('%Y-%m-%d %H:%M:%S'), end_of_day_utc.strftime('%Y-%m-%d %H:%M:%S')))
        result = cursor.fetchall()
        cursor.close()
        cnx.close()
        return jsonify(result)
    else:
        return jsonify([]), 500



@app.route('/api/v1/get_latest', methods=['GET'])
def get_latest():
    cnx = connect_to_db()
    if cnx:
        cursor = cnx.cursor(dictionary = True)
        cursor.execute("SELECT * FROM iot_records ORDER BY record_time DESC LIMIT 1")
        record = cursor.fetchone()
        cursor.close()
        cnx.close()
        return jsonify(record)
    return jsonify({})

@app.route('/api/v1/get_by_period', methods=['GET'])
def get_by_period():
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    timezone_str = request.args.get('timezone', 'UTC')  # 默认使用 UTC

    if not start_date_str or not end_date_str:
        return "Both start_date and end_date are required", 400

    try:
        # 验证并格式化日期
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)  # 包含结束日期
    except ValueError:
        return "Invalid date format. Use YYYY-MM-DD.", 400

    # 获取用户时区
    try:
        timezone = pytz.timezone(timezone_str)
    except pytz.UnknownTimeZoneError:
        return "Invalid timezone.", 400

    # 将日期转换为目标时区的开始和结束时间
    start_of_day = timezone.localize(datetime.combine(start_date, datetime.min.time()))
    end_of_day = timezone.localize(datetime.combine(end_date, datetime.min.time()))

    # 将时间转换为 UTC
    start_date_utc = start_of_day.astimezone(pytz.utc)
    end_date_utc = end_of_day.astimezone(pytz.utc)

    cnx = connect_to_db()
    if cnx:
        cursor = cnx.cursor(dictionary=True)
        query = """
            SELECT * FROM iot_records
            WHERE record_time >= %s AND record_time < %s
            ORDER BY record_time DESC
        """
        cursor.execute(query, (start_date_utc.strftime('%Y-%m-%d %H:%M:%S'), end_date_utc.strftime('%Y-%m-%d %H:%M:%S')))
        records = cursor.fetchall()
        cursor.close()
        cnx.close()
        return jsonify(records)
    else:
        return jsonify([]), 500
    
@app.route('/api/v1/summary_by_day', methods=['GET'])
def summary_by_day():
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({"error": "Date parameter is required"}), 400
    
    date = datetime.strptime(date_str, '%Y-%m-%d')
    next_date = date + timedelta(days=1)
    
    hourly_data = session.query(
        func.date_trunc('hour', MyModel.record_time).label('hour'),
        func.avg(MyModel.temperature).label('avg_temperature'),
        func.avg(MyModel.humidity).label('avg_humidity')
    ).filter(
        MyModel.record_time >= date,
        MyModel.record_time < next_date
    ).group_by('hour').all()
    
    summary = session.query(
        func.max(MyModel.temperature).label('max_temperature'),
        func.min(MyModel.temperature).label('min_temperature'),
        func.avg(MyModel.temperature).label('avg_temperature'),
        func.avg(MyModel.humidity).label('avg_humidity')
    ).filter(
        MyModel.record_time >= date,
        MyModel.record_time < next_date
    ).one()
    
    result = {
        "hourly_data": [
            {
                "hour": hour.hour.strftime('%Y-%m-%d %H:%M:%S'),
                "avg_temperature": avg_temperature,
                "avg_humidity": avg_humidity
            } for hour, avg_temperature, avg_humidity in hourly_data
        ],
        "summary": {
            "max_temperature": summary.max_temperature,
            "min_temperature": summary.min_temperature,
            "avg_temperature": summary.avg_temperature,
            "avg_humidity": summary.avg_humidity
        }
    }
    
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True)
