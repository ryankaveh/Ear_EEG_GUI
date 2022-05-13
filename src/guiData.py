import os, serial
from re import X
from time import sleep, time
from csv import writer
from ctypes import Structure, c_ubyte, c_short, c_int
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QCheckBox, QLineEdit
from PyQt5.QtCore import QTimer

class SerialReader():

    def __init__(self, port, numChannels, channelDataArr, saveDataQueue, connectionPipe, commandWriterPipe, commandResponsePipe):

        self.serialGUISide = None
        self.port = port
        self.numChannels = numChannels
        self.channelDataArr = channelDataArr
        self.saveDataQueue = saveDataQueue
        self.connectionPipe = connectionPipe
        self.commandWriterPipe = commandWriterPipe
        self.commandResponsePipe = commandResponsePipe

        self.refreshRate = 10 # # Refresh rate in ms, only used when in command mode
        self.commandMode = True # Controls whether serialReader is looking for data or command responses, always starts in command mode

    # Starts a loop to call the startSerialReader function 
    def startSerialReader(self):

        while not self.serialGUISide: # This waits for the client to create the port
            sleep(0.1) # This caps the refresh rate and lowers the load on the computer, full speed not needed
            try:
                # Connection is in startSerialReader because otherwise it doesn't really work with the multiprocessing
                # self.serialGUISide = serial.Serial(self.port, 9600, rtscts=True, dsrdtr=True) # Uncomment for emulator
                self.serialGUISide = serial.Serial(self.port, 115200, rtscts=True)
            except:
                pass

        self.connectionPipe.send(1) # Callback to notify main loop that device is connected
        print("Writing stop to chip")
        self.serialGUISide.write(("stop" + " \n").encode())
        self.serialGUISide.write(("stop" + " \n").encode())
        self.serialGUISide.write(("stop" + " \n").encode())

        while True:
            self.updateData()
            if self.commandWriterPipe.poll():
                command = self.commandWriterPipe.recv().strip()
                print("Writing " + command + " to chip")
                self.serialGUISide.write((command + " \n").encode())
                if command == "start" or command == "stop":
                    self.commandMode = (command == "stop")
                elif command == "pyserialReset":
                    self.serialGUISide.close()
                    self.serialGUISide = serial.Serial(self.port, 115200, rtscts=True)
                    self.serialGUISide.reset_output_buffer()
            
    def updateData(self):

        if self.commandMode:
            sleep(self.refreshRate * 0.001) # This caps the refresh rate and lowers the load on the computer, full speed not needed
            if self.serialGUISide.in_waiting > 0:
                sleep(0.1) # Make sure full response is transmitted
                val = b''
                val += self.serialGUISide.read(self.serialGUISide.in_waiting)
                # print("Chip response: " + val.decode())
                print("Chip response: " + str(val.hex()))
                # self.commandResponsePipe.send("Chip: " + val.decode())
                self.commandResponsePipe.send("Chip: " + str(val.hex()))
                # self.serialGUISide.reset_input_buffer() # Currently throws away text responses as they aren't consistent enought to deal with

        elif self.serialGUISide.in_waiting > 0:
            if self.serialGUISide.in_waiting < 6:
                self.serialGUISide.reset_input_buffer()

            val = b''
            val += self.serialGUISide.read(65) # Signal is of exactly length 65

            packetId = int.from_bytes(val[:1], "big")
            
            saveData = [packetId]

            idx = 0
            for i in range(1, len(val) - 1, self.numChannels):
                chxEEG = int.from_bytes(val[i:i+4], "big", signed=True)
                chxI = int.from_bytes(val[i+4:i+6], "big", signed=True)
                chxQ = int.from_bytes(val[i+6:i+8], "big", signed=True)

                with self.channelDataArr[idx].get_lock():
                    self.channelDataArr[idx].chxEEG = chxEEG
                    self.channelDataArr[idx].chxI = chxI
                    self.channelDataArr[idx].chxQ = chxQ
                    self.channelDataArr[idx].packetId = packetId
                idx += 1

                saveData.extend((chxEEG, chxI, chxQ))
            
            self.saveDataQueue.put(saveData) # We might want this to be put_nowait

class ChannelData(Structure):
    _fields_ = [("packetId", c_ubyte), ("chxEEG", c_int), ("chxI", c_short), ("chxQ", c_short)]

class SaveDataMenuButton(QPushButton):

    def __init__(self, running):

        super().__init__("Save Data")
        self.clicked.connect(self.showPopup)

        self.running = running

        self.saveState = 2 # 0 is unchecked, 2 is checked
        self.savePostprocessed = 0
        self.filename = str(time())
        self.updatedFilename = False

        self.menu = None

    def showPopup(self):

        if not self.menu:
            self.menu = SaveDataMenu(self, self.running, self.saveState, self.savePostprocessed, self.filename)
            self.menu.show()
        else:
            self.menu.show()

    def setSaveState(self, state):

        self.saveState = state

    def setSavePostprocessedState(self, state):

        self.savePostprocessed = state

    def setFilename(self, currText):

        self.filename = str(currText)
        self.updatedFilename = True

    def setChangeable(self, changeable):

        if self.menu:
            self.menu.setChangeable(changeable)

class SaveDataMenu(QWidget):

    def __init__(self, button, running, saveState, savePostprocessed, filename):

        super().__init__()
        layout = QVBoxLayout()

        self.button = button

        self.saveState = QCheckBox("Save Data")
        self.saveState.setCheckState(saveState)
        self.saveState.stateChanged.connect(button.setSaveState)
        self.saveState.setEnabled(not running.value)

        self.savePostprocessed = QCheckBox("Include Postprocessed Data")
        self.savePostprocessed.setCheckState(savePostprocessed)
        self.savePostprocessed.stateChanged.connect(button.setSavePostprocessedState)
        self.savePostprocessed.setEnabled(False)#(not running.value) This is not currently implemented so the checkbox is disabled TODO

        self.filenameLable = QLabel("Filename:")
        self.filename = QLineEdit(filename)
        self.filename.textChanged.connect(button.setFilename)
        self.filename.setEnabled(not running.value)

        self.filenameLayout = QHBoxLayout()
        self.filenameLayout.addWidget(self.filenameLable)
        self.filenameLayout.addWidget(self.filename)

        self.tooltip = QLabel("Please enter your desired filename\nOn each start and stop numbers will be added to the end\n(abc -> \"abc-0\")")

        layout.addWidget(self.saveState)
        layout.addWidget(self.savePostprocessed)
        layout.addLayout(self.filenameLayout)
        layout.addWidget(self.tooltip)

        self.setLayout(layout)

    def setChangeable(self, changeable):

        self.saveState.setEnabled(changeable)
        self.savePostprocessed.setEnabled(changeable)
        self.filename.setEnabled(changeable)

class SaveDataWriter(QWidget):

    def __init__(self, running, numChannels, saveDataQueue, saveDataMenuButton):

        super().__init__()

        # Header format: ["packet_id", "chx1_eeg", "chx1_i", "chx1_q", "chx2_eeg", "chx2_i", "chx2_q", ...]
        self.header = ["packet_id"] + [itm for lst in [[chxNum + "_eeg", chxNum + "_i", chxNum + "_q"] for chxNum in ["chx" + str(i) for i in range(numChannels)]] for itm in lst]

        self.running = running
        self.saveDataQueue = saveDataQueue
        self.saveDataMenuButton = saveDataMenuButton

        self.setCurrFilename()

        self.refreshRate = 5 # Refresh rate in ms, controls how often new data is looked for

        self.hide()

    def startSaveDataWriter(self):

        self.timer = QTimer()
        self.timer.setInterval(self.refreshRate)
        self.timer.timeout.connect(self.writeData)
        self.timer.start()

    def writeData(self):

        if bool(self.saveDataMenuButton.saveState) and bool(self.running.value) and not self.saveDataQueue.empty():
            saveData = self.saveDataQueue.get() # Possibly not exitable on windows? https://docs.python.org/3/library/queue.html#put
            shouldWriteHeader = not os.path.exists(self.currFilename)

            with open(self.currFilename, 'a') as csvfile:
                dataWriter = writer(csvfile) # CSV writer
                if shouldWriteHeader:
                    dataWriter.writerow(self.header)
                dataWriter.writerow(saveData)
            self.updatedExtenstion = False

        elif (not self.updatedExtenstion or self.saveDataMenuButton.updatedFilename) and not bool(self.running.value):
            self.setCurrFilename()

        # This clause works to empty the queue if the user hasn't yet clicked start
        elif not bool(self.running.value) and not self.saveDataQueue.empty():
            self.saveDataQueue.get()

    def setCurrFilename(self):

        idx = 0
        self.currFilename = "../data/" + str(self.saveDataMenuButton.filename) + "-" + str(idx) + ".csv"
        while os.path.exists(self.currFilename):
            idx += 1
            self.currFilename = "../data/" + str(self.saveDataMenuButton.filename) + "-" + str(idx) + ".csv"
        self.updatedExtenstion = True
        self.saveDataMenuButton.updatedFilename = False
        