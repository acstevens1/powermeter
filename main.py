import httplib, urllib
import time, datetime, sys
import serial
from xbee import xbee
import eeml
import sensorhistory
import optparse
from time import sleep, localtime, strftime

API_KEY = "SBK6PW8UFZQ81MZR" #API Key for ThingSpeak
API_URL = "api.thingspeak.com:80" #API URL

ENERGY_PRICE = 0.30

LOG_FILE = "log_power.csv" # store data in logfile

SERIALPORT = "/dev/ttyUSB0" #USB Serial port -> XBEE
BAUDRATE = 9600
CURRENTSENSE = 4
VOLTSENSE = 0
MAINSVPP = 325 * 2
vrefcalibration = [492,  #0
                   481,  #1
                   489,  #2
                   492,  #3
                   501,  #4
                   493]  #etc
CURRENTNORM = 15.5  # Amperes -> ADC
NUMWATTDATASAMPLES = 1800 # how many samples to watch in the plot window, 1 hr @ 2s samples
MAXWATTLISTLEN = 200

# open up the FTDI serial port to get data transmitted to xbee
ser = serial.Serial(SERIALPORT, BAUDRATE)

# open our datalogging file
logfile = None
try:
    logfile = open(LOG_FILE, 'r+')
except IOError:
    # didn't exist yet
    logfile = open(LOG_FILE, 'w+')
    logfile.write("#Date, time, sensornum, avgWatts\n");
    logfile.flush()

sensorhistories = sensorhistory.SensorHistories(logfile)
print sensorhistories

def update_graph(idleevent):
    global avgwattdataidx, sensorhistories, DEBUG

#get one packet from the xbee or timeout
    packet = xbee.find_packet(ser)
    if not packet:
        return #timeout

    xb = xbee(packet) #parse
    print xb.address_16

#n-1 samples as first one is not correct
    voltagedata = [-1] * (len(xb.analog_samples) - 1)
    ampdata = [-1] * (len(xb.analog_samples) -1)

#store in arrays
    for i in range(len(voltagedata)):
        voltagedata[i] = xb.analog_samples[i+1][VOLTSENSE]
        ampdata[i] = xb.analog_samples[i+1][CURRENTSENSE]

#normalising data
    min_v = 1024 #xbee adc is 10 bits so max = 1023
    max_v = 0
    for i in range(len(voltagedata)):
        if (min_v > voltagedata[i]):
            min_v = voltagedata[i]
        if (max_v < voltagedata[i]):
            max_v = voltagedata[i]

#average of min & max voltage

    avg_v = (max_v + min_v) / 2
    vpp = max_v-min_v #vpp

    for i in range(len(voltagedata)):
    #remove dc bias
        voltagedata[i] -= avg_v
        voltagedata[i] = (voltagedata[i] * MAINSVPP) / vpp

#normailse current

    for i in range(len(ampdata)):
        if vrefcalibration[xb.address_16]:
            ampdata[i] -= vrefcalibration[xb.address_16]
        else:
            ampdata[i] -= vrefcalibration[0]

    ampdata[i] /= CURRENTNORM

    print "Voltage: ", voltagedata
    print "Current: ", ampdata

#calculate power

    wattdata = [0] * len(voltagedata)
    for i in range(len(wattdata)):
        wattdata[i] = voltagedata[i] * ampdata[i]

#sum current over 1/50Hz
    avgamp = 0
#20 cycles per seccond

    for i in range(17):
	 avgamp += abs(ampdata[i])
    avgamp /= 17.0

#sum power over 1/50Hz
    avgwatt = 0

#20 cycles per seccond

    for i in range(17):
   	 avgwatt += abs(wattdata[i])
    avgwatt /= 17.0

    sensorhistory = sensorhistories.find(xb.address_16)
    print sensorhistory

    elapsedseconds = time.time() - sensorhistory.lasttime
    dwatthr = (avgwatt * elapsedseconds) / (60.0 * 60.0)  # 60 seconds in 60 minutes = 1 hr
    sensorhistory.lasttime = time.time() 
    print "\t\tWh used in last ",elapsedseconds," seconds: ",dwatthr
    sensorhistory.addwatthr(dwatthr)

# Determine the minute of the hour (ie 6:42 -> '42')
    currminute = (int(time.time())/60) % 10
# Figure out if its been five minutes since our last save
    if (((time.time() - sensorhistory.fiveminutetimer) >= 60.0)
        and (currminute % 2 == 0)
        ):
        wattsused = 0
        whused = 0
        for history in sensorhistories.sensorhistories:
                wattsused += history.avgwattover5min()
                whused += history.dayswatthr
        
        kwhused = whused/1000
        avgwatt = sensorhistory.avgwattover5min()
        cost = kwhused * ENERGY_PRICE
        cost = "%.2f" % cost

        params = urllib.urlencode({'field1': avgwatt, 'field2': kwhused, 'field3': cost, 'key': API_KEY})
        headers = {"content-type": "application/x-www-form-urlencoded","Accept": "text/plain"}
        conn = httplib.HTTPConnection(API_URL)

        try:
            conn.request("POST", "/update", params, headers)
            response = conn.getresponse()
            print response.status, response.reason
            data = response.read()
            conn.close()
        except:
            print "connection failed"


# Print out debug data, Wh used in last 5 minutes
        avgwattsused = sensorhistory.avgwattover5min()
        print time.strftime("%Y %m %d, %H:%M")+", "+str(sensorhistory.sensornum)+", "+str(sensorhistory.avgwattover5min())+"\n"
        
# Lets log it! Seek to the end of our log file
        if logfile:
            logfile.seek(0, 2) # 2 == SEEK_END. ie, go to the end of the file
            logfile.write(time.strftime("%Y %m %d, %H:%M")+", "+
                        str(sensorhistory.sensornum)+", "+
                        str(sensorhistory.avgwattover5min())+"\n")
            logfile.flush()

if __name__ == "__main__":
     while True:
             update_graph(None)
	                  
