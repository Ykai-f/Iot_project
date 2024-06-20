import utime as time
import ujson as json
import uos as os
import urequests
import gc
import rp2
import machine
from parts import blink, toggle, set_dht11, read_dht11, set_ds3231, set_ds3231_from_ntp, mount_sd
from lib.wifi import connect_to_wifi, wifi_status

CONFIG_FILE = 'config.json'

class SDCardError(Exception):
    pass

class NetworkError(Exception):
    pass

class SensorError(Exception):
    pass

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return None

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

class IoTDevice:
    def __init__(self):
        self.config = load_config()
        self.unsent_data_path = "sd/unsent.json"
        self.data_buffer = []
        self.last_send_time = time.time()
        self.send_gap = 60
        self.len_buffer_max = 10
        self.red = machine.Pin(15, machine.Pin.OUT)
        self.dht_sensor = None
        self.ds = None
        self.sdcard_status = False
        self.button = machine.Pin(1, machine.Pin.IN, machine.Pin.PULL_UP)
        self.button.irq(trigger=machine.Pin.IRQ_FALLING, handler=self.enter_setup_mode)
        self.setup_mode = False

    def enter_setup_mode(self, pin):
        self.setup_mode = True

    def file_exists(self, filepath):
        try:
            os.stat(filepath)
            return True
        except OSError:
            return False

    def append_data_to_buffer(self, timestamp, temp, humidity):
        self.data_buffer.append({
            "time": timestamp,
            "temperature": temp,
            "humidity": humidity
        })

    def send_data_to_cloud(self):
        if len(self.data_buffer) > 0:
            try:
                response = urequests.post(
                    self.config['api_url'],
                    data=json.dumps(self.data_buffer),
                    headers={'Content-Type': 'application/json'})
                if response.status_code == 200:
                    print("Data sent successfully")
                    self.data_buffer.clear()
                else:
                    raise NetworkError("Failed to send data with status: {}".format(response.status_code))
            except Exception as e:
                blink(5, target=self.red)
                print("Error sending data:", e)
                self.log_error_to_sd(f"Error sending data: {e}")
                raise NetworkError(e)

    def save_data_locally(self):
        directory = '/'.join(self.unsent_data_path.split('/')[:-1])
        if not self.file_exists(directory):
            os.makedirs(directory)
        
        try:
            with open(self.unsent_data_path, "a") as file:
                for data in self.data_buffer:
                    json.dump(data, file)
                    file.write('\n')
        except Exception as e:
            self.log_error_to_sd(f"Error saving data locally: {e}")
            print("Error saving data locally:", e)
            raise SDCardError(e)

    def send_unsent_data(self):
        if self.file_exists(self.unsent_data_path):
            with open(self.unsent_data_path, "r") as file:
                unsent_data = file.readlines()

            if unsent_data:  # Check if the list is not empty
                all_data_sent = True
                for line in unsent_data:
                    data = json.loads(line)
                    try:
                        response = urequests.post(
                            self.config['api_url'],
                            data=json.dumps(data),
                            headers={'Content-Type': 'application/json'}
                        )
                        if response.status_code != 200:
                            print(f"Failed to send data with status: {response.status_code}")
                            all_data_sent = False
                            break
                    except Exception as e:
                        self.log_error_to_sd(f"Error sending unsent data: {e}")
                        blink(5, target=self.red)
                        print("Error sending unsent data:", e)
                        all_data_sent = False
                        break

                if all_data_sent:
                    with open(self.unsent_data_path, "w") as file:
                        pass  # Clear the file when all data sent

    def save_data_to_csv(self, timestamp, temp, humidity):
        if self.sdcard_status:
            csv_file_path = "sd/{}.csv".format(timestamp.split(",")[0])
            try:
                with open(csv_file_path, "a") as file:
                    file.write("{},{:.1f},{:.1f}\r\n".format(timestamp, temp, humidity))
                blink(3)
            except Exception as e:
                self.log_error_to_sd(f"Error saving data to CSV: {e}")
                raise SDCardError(e)

    def log_error_to_sd(self, message):
        log_file_path = "sd/error_log.txt"
        timestamp = time.localtime()
        timestamp_str = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(*timestamp[:6])
        
        try:
            with open(log_file_path, "a") as log_file:
                log_file.write(f"{timestamp_str} - {message}\n")
        except Exception as e:
            print("Error logging to SD card:", e)
            raise SDCardError(e)

    def initialize_components(self):
        try:
            connect_to_wifi(self.config['ssid'], self.config['password'])
        except Exception as e:
            raise NetworkError("Failed to connect to WiFi: {}".format(e))

        self.dht_sensor = set_dht11()
        self.ds = set_ds3231()
        time.sleep(0.5)
        set_ds3231_from_ntp(self.ds)
        self.sdcard_status = mount_sd()
        return self.dht_sensor, self.ds, self.sdcard_status

    def reconnect_wifi(self):
        print("Connecting to WiFi...")
        connect_to_wifi(self.config['ssid'], self.config['password'])
        if not wifi_status():
            self.send_gap = 600  # make the delay longer
            self.len_buffer_max = 120  # Record every 5 seconds, so normally should have 600 / 5 = 120 records
            self.send_unsent_data()
        else:
            print("Reconnect to WiFi!!")
            self.send_gap = 60
            self.len_buffer_max = 10

    def remount_sd_card(self):
        try:
            self.sdcard_status = mount_sd()
        except SDCardError as e:
            self.log_error_to_sd(f"Error remounting SD card: {e}")
            print("Failed to remount SD card:", e)
        except Exception as e:
            self.log_error_to_sd(f"Error remounting SD card: {e}")
            print("Failed to remount SD card:", e)

    def start_ap_mode(self):
        ap = network.WLAN(network.AP_IF)
        ap.active(True)
        ap.config(essid='SetupDevice', password='12345678')
        self.serve_web_config()

    def serve_web_config(self):
        import socket
        import ure

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('0.0.0.0', 80))
        s.listen(5)

        while self.setup_mode:
            conn, addr = s.accept()
            request = conn.recv(1024)
            request = str(request)

            ssid_match = ure.search(r'GET /ssid=(.+?)&', request)
            password_match = ure.search(r'password=(.+?)&', request)
            api_match = ure.search(r'api=(.+?) ', request)

            if ssid_match and password_match and api_match:
                ssid = ssid_match.group(1)
                password = password_match.group(1)
                api = api_match.group(1)

                self.config = {
                    'ssid': ssid,
                    'password': password,
                    'api_url': api
                }
                save_config(self.config)
                self.setup_mode = False

                response = 'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\nConfiguration saved! Rebooting...'
                conn.send(response)
                time.sleep(2)
                machine.reset()
            else:
                response = '''HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n
                    <html>
                    <body>
                    <h1>Configure Device</h1>
                    <form action="/" method="get">
                        SSID: <input type="text" name="ssid"><br>
                        Password: <input type="text" name="password"><br>
                        API URL: <input type="text" name="api"><br>
                        <input type="submit" value="Save">
                    </form>
                    </body>
                    </html>'''
                conn.send(response)
            conn.close()

    def main_loop(self):
        while True:
            if self.setup_mode:
                self.start_ap_mode()
                continue

            try:
                current_time = time.time()
                current_time_str = "{:04d}-{:02d}-{:02d},{:02d}:{:02d}:{:02d}".format(*self.ds.get_time())
                t, h = read_dht11(self.dht_sensor)
                print(f"Current time: {current_time_str}\nTemperature: {t}C\nHumidity: {h}%")
                if not wifi_status():
                    print("Warning! WIFI not connected!")
                if not self.sdcard_status:
                    print("Warning! SD not mounted correctly!")
                    self.remount_sd_card()
                print("")  # print gap between loops

                self.append_data_to_buffer(current_time_str, t, h)

                if (current_time - self.last_send_time) >= self.send_gap or len(self.data_buffer) >= self.len_buffer_max:
                    try:
                        # Detect again if the wifi is connected
                        if not wifi_status():
                            self.reconnect_wifi()
                        self.send_data_to_cloud()
                    except NetworkError as e:
                        blink(1, target=self.red)
                        print("Error sending data:", e)
                        self.log_error_to_sd(f"Error sending data: {e}")
                        print("Saving data locally...")
                        if self.sdcard_status:
                            self.save_data_locally()
                        else:
                            print("SD card not mounted. Data will be lost.")
                            self.log_error_to_sd("SD card not mounted. Data will be lost.")
                        blink(5)
                        self.data_buffer.clear()

                self.save_data_to_csv(current_time_str, t, h)
                blink(1)

                gc.collect()
                time.sleep(5)  # Sleep for 5 seconds between readings
            except SDCardError:
                self.sdcard_status = False  # Set sdcard_status to False when an SD card error occurs
            except NetworkError:
                self.reconnect_wifi()
            except SensorError:
                pass  # Add sensor-specific error handling here if needed
            except Exception as e:
                self.log_error_to_sd(f"Error while main loop: {e}")
                blink(1, target=self.red)
                print("Error:", e)
                time.sleep(5)
                gc.collect()
                continue



if __name__ == '__main__':
    device = IoTDevice()
    device.main_loop()