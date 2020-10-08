import serial
import serial.tools.list_ports
import time
import threading
from multiprocessing import Process, Queue

# This class provides the I/o for the virtual com ports
# Ideally it opens a single port to emulate the Ear EEG side of the serial link
# A user would then use this class send dummy data from the "chip" to the user 
class win_emulator():
    def __init__(self):
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            if ('com0com' in p.description and ('COM7' not in p.description)):
                print(p)
                self.virtSerial = serial.Serial(p.device, baudrate=115200)
                if (self.virtSerial.isOpen() == False):
                    break
                self.virtSerial.close()


    def write(self, val):
        self.virtSerial.write(val.to_bytes(2,byteorder="big"))

    def read(self):
        stuff = self.virtSerial.read()
        print(stuff)

    def closePort(self):
        self.virtSerial.close()

    def openPort(self):
        self.virtSerial.open()

    def getSerialObject(self):
        return(self.virtSerial)

    def isOpen(self):
        return(self.virtSerial.is_open)

def earEEG_genDummyData(lastData):
    newData = lastData + 1
    print(newData)
    return (newData)

def earEEG_process(messageQueue, dataQueue):

    print("\nNew thread started!")

    # Make earEEG I/O emulator
    earEEG = win_emulator()

    # Open com port
    serDevice = earEEG.getSerialObject()
    print("thread starting on {}".format(serDevice.name))
    if (earEEG.isOpen() == False):
        earEEG.openPort()

    # set various flag & starting datapoint
    start_flag = 0
    lastData = 0

    while True:
        # time delay (1 mS)
        time.sleep(.001)
        #time.sleep(2) 
        
        # Check message from messageQueue
            # if start, flip start flag and start sending data through messageQueue
            # if quit, quit
            # else continue
        if (messageQueue.empty() == False):
            msg = messageQueue.get()

            if (msg == 'start'):
                print("starting earEEG dummy data generator")
                start_flag = 1
            
            if (msg == 'stop'):
                break

        if (start_flag == 1):
            # generate & write data to COM Port
            data = earEEG_genDummyData(lastData)
            lastData = data
            earEEG.write(data)
    
    print("earEEG_process finished")

if __name__ == '__main__':

    # First we need to make the machinery
    # some queues and a multiprocesser object

    # queue from host side to earEEG\
    # Use for starting data transfer and stopping process 
    # Eventually I will need to make this go through the com port
    messageQueue = Queue() 

    # queue from earEEG to host
    # just used for debug status updates
    # all data should be going through the com port 
    dataQueue = Queue()

    # earEEG_process = Process(target=earEEG_process, args=((messageQueue), (dataQueue),)).start()
    # earEEG_process.daemon = True
    # earEEG_process.start()
    earEEG_process = threading.Thread(target=earEEG_process, args=(messageQueue,dataQueue,))
    print("about to start thread")
    earEEG_process.start()

    # This block will grab the first virtual comport that isn't already open and reserve is as the "host side" port
    # ports = list(serial.tools.list_ports.comports())
    # for p in ports:
    #     if 'com0com' in p.description:
    #         ser = serial.Serial(p.device, baudrate=115200, timeout= 1)
    #         if (ser.isOpen() == False):
    #             ser.open()
    #             break

    # to start data dumping process
    messageQueue.put("start")

    # put your code here
    #
    time.sleep(1)
    #
    #

    # to stop data dumping
    messageQueue.put("stop")
    earEEG_process.join()


