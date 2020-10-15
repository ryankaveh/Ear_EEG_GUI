import os, subprocess, serial, time
import threading
from multiprocessing import Process, Queue

class serial_emulator(object):
    def __init__(self, device_port='./ttydevice', client_port='./ttyclient'):
        self.device_port = device_port
        self.client_port = client_port
        cmd=['/usr/local/Cellar/socat/1.7.3.4/bin/socat','-d','-d','PTY,link=%s,raw,echo=0' %
                self.device_port, 'PTY,link=%s,raw,echo=0' % self.client_port]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(1)
        self.serialW = serial.Serial(self.device_port, 9600, rtscts=True, dsrdtr=True)
        self.serialR = serial.Serial(self.client_port, 9600, rtscts=True, dsrdtr=True)
        self.err = ''
        self.out = ''

    def write(self, out):
        self.serialW.write(out)

    def read(self):
        line = ''
        while self.serialR.inWaiting() > 0:
            line += (self.serialR.read()).decode('utf-8')
        return line

    def __del__(self):
        self.stop()

    def stop(self):
        self.proc.kill()
        self.out, self.err = self.proc.communicate()


def earEEG_genDummyData(lastData):
    newData = lastData + 1
    print(newData)
    return (newData)

def earEEG_process(messageQueue, dataQueue):

    print("\nNew thread started!")

    # Make earEEG I/O emulator
    # Can write bytes with serial_emulator.write(string.encode('utf-8'))
    # Can read bytes from it with serial_emulator.read()
    earEEG = serial_emulator('./ttydevice','./ttyclient')

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
            line = earEEG.read()
            dataQueue.put(line)


    
    print("earEEG_process finished")

if __name__ == '__main__':

    # First we need to make the machinery
    # some queues and a multiprocesser object

    # queue from host side to earEEG_emulator
    # for star & stopping!
    messageQueue = Queue() 

    # queue from earEEG_emulator to host
    dataQueue = Queue()

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
    print("starting...")
    messageQueue.put("start")

    # put your code here
    # earEEG
    #
    print("sleeping...")
    time.sleep(5)
    while (dataQueue.empty() == False):
        msg = dataQueue.get()
        print(msg)
    #
    #

    # to stop data dumping
    print("stoping...")
    messageQueue.put("stop")
    earEEG_process.join()
