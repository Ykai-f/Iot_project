from iot_device import IoTDevice

if __name__ == "__main__":
    SSID = 'La Marq-510'
    PASSWORD = ''
    API_URL = 'https://yuekai.pythonanywhere.com/api/v1/update'

    device = IoTDevice(SSID, PASSWORD, API_URL)
    device.initialize_components()
    device.send_unsent_data()
    device.main_loop()