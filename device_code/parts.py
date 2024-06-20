import uos as os
import machine
import lib.sdcard as sdcard
import time
from machine import I2C, Pin
from lib.ds3231 import DS3231
from lib.wifi import connect_to_wifi, wifi_status
import ntptime
from lib.dht import DHT11

############################ built-in LED ###########################
# use led.toggle() to change the status
def blink(repeat, target = False):
    if not target:
        led = machine.Pin("LED", machine.Pin.OUT)
    else:
        led = target
    for i in range(repeat):
        led.on()
        time.sleep(0.1) 
        led.off()
        time.sleep(0.1)
def toggle(target = False):
    if not target:
          led = machine.Pin("LED", machine.Pin.OUT)
    else:
          led = target
    led = machine.Pin("LED", machine.Pin.OUT)
    led.toggle()

############################ DHT11 ###########################
def set_dht11():
    pin = Pin(28, Pin.OUT, Pin.PULL_DOWN)
    sensor = DHT11(pin)
    return sensor

def read_dht11(sensor):
    attempts = 5
    for _ in range(attempts):
        try:
            t = sensor.temperature
            h = sensor.humidity
            return t, h
        except Exception as e:
            print("Error reading DHT11:", e)
            time.sleep(2)  # prevent the "not enough pause problem"
    raise Exception("Failed to read from DHT11 sensor after {} attempts".format(attempts))

############################ ds3231 ###########################
def set_ds3231():
    sda_pin = Pin(4)
    scl_pin = Pin(5)
    i2c = I2C(0, scl=scl_pin, sda=sda_pin)
    ds = DS3231(i2c)
    return ds

def set_ds3231_from_ntp(ds, retry=5):
    ntptime.host = 'time.google.com'  
    for attempt in range(retry):
        print("Attempt {}/{}: Local time before synchronization: {}".format(
            attempt + 1, retry, str(time.localtime())))
        if wifi_status():  
            try:
                time.sleep(1)  
                ntptime.settime()  
                synchronized_time = time.localtime()  
                print("Local time after synchronization: {}".format(str(synchronized_time)))
                ds.set_time(synchronized_time)  
                return True  
            except OSError as e:
                if e.args[0] == 110:  
                    print("Connection timed out, try again in 5 seconds...")
                    time.sleep(5)  
                else:
                    print("Network error:", e)
                    return False  
            except Exception as e:
                print("Failed to synchronize time due to:", e)
                return False 
        else:
            print("Wi-Fi is not connected. Unable to synchronize time.")
            return False  
    print("Failed to synchronize time after {} attempts".format(retry))
    return False  

############################ SD card ###########################
def mount_sd():
    cs = machine.Pin(17, machine.Pin.OUT)
    spi = machine.SPI(0,
                        baudrate=1000000,
                        polarity=0,
                        phase=0,
                        bits=8,
                        firstbit=machine.SPI.MSB,
                        sck=machine.Pin(18),
                        mosi=machine.Pin(19),
                        miso=machine.Pin(16))

    try:
        if "sd" in os.listdir():
            os.umount("/sd")
            print("SD card exite already?! Unmounted successfully.")

        sd = sdcard.SDCard(spi, cs)
        vfs = os.VfsFat(sd)
        os.mount(vfs, "/sd")
        print("SD card mounted successfully!!!")
        return True
    except Exception as e:
        print("Error mounting SD card:", e)
        return False