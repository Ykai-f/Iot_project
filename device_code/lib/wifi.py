import network
import time

SSID = 'La Marq-510'
PASSWORD = ''

def connect_to_wifi(ssid, password, timeout=10):
  try:
      wlan = network.WLAN(network.STA_IF)
      wlan.active(True)
      wlan.connect(ssid, password)
      
      start_time = time.time()
      while not wlan.isconnected():
          if time.time() - start_time > timeout:
              print('Connection timed out')
              return False
          print(f'({time.time() - start_time}/{timeout})Waiting for connection...')
          time.sleep(1)
      
      print('Connected to Wi-Fi')
      print('Network config:', wlan.ifconfig())
      return True
  except Exception as e:
    print(e)
    return False

def wifi_status():
  wlan = network.WLAN(network.STA_IF)
  return wlan.isconnected()
    
if __name__ == '__main__':
    connect_to_wifi(SSID, PASSWORD)