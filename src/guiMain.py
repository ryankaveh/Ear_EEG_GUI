import os, sys, atexit, argparse
from time import sleep
from csv import reader, writer
from serial.tools import list_ports
import multiprocessing as mp
from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QVBoxLayout, QHBoxLayout, QWidget, QComboBox

import guiCue
import guiData
import guiOptions
import guiPlots

###
# Known Issues:
#
# AttributeError: 'ForkAwareLocal' object has no attribute 'connection' appears to be something with the sync manager shutting down? Or maybe too many simultaneous manager reads? 
# A rare error but problematic. 
# UPDATE: Hasn't shown up in a very long time, other changes possibly resolved this
# 
# Clean Code
#   Set qwidget/qlayout parent
#   TODOS
#   Comments + documentation
# Testing
# Split mac/windows
###
class MainWindow(QMainWindow):

    def __init__(self, commandLinePort):

        super().__init__()

        self.setWindowTitle("Ear EEG GUI")

        numChannels = 8 # Number of channels to expect, will definitely break if value is incorrect
        vid = 0x1915 # Nordic device vendor id, used for auto connect, change if desired connectionb device changes
        pid = 0x521A # Corrosponding product id, use same as vendor id
        configFilename = "guiConfig.csv"

        # List of all DataProcesses that can become graphs (and then be shown) during runtime
        # First item in the tuple is supposed to be the name of the graph, is currently just its color
        possPlotData = []

        self.manager = mp.Manager()

        running = mp.Value('i', False) # Univerally controls whether the DataProcesses run and CustomGraphWidgets redraw themselves

        # Creates SerialReader object to read data from serial port "port", populate channelDataArr and save the data to saveDataQueue
        if commandLinePort:
            port = commandLinePort
        else:
            # port = "./ttyGUI" # Emulator
            # port = "/dev/cu.usbmodem0000000000001" Can be used to manually set port (instead of auto), if so comment out following block
            set = False
            for device in list_ports.comports():
                if device.vid == vid and device.pid == pid:
                    port = device.device
                    print("Correct port found to be " + port + ", connecting...")
                    set = True
            if not set:
                port = "/dev/cu.usbmodem0000000000001"
                print("Auto connection failed, no device with correct vendor and product id found, reverting to default: " + port)
            

        channelDataArr = []
        for i in range(0, numChannels):
            lock = mp.RLock()
            channelDataArr.append(mp.Value(guiData.ChannelData, 0, 0, 0, 0, lock=lock))

        saveDataQueue = self.manager.Queue()

        connectionPipe, sRConnectionPipe = mp.Pipe()
        commandWriterPipe, sRCommandWriterPipe = mp.Pipe()
        commandResponsePipe, sRCommandResponsePipe = mp.Pipe()

        serialReader = guiData.SerialReader(port, channelDataArr, saveDataQueue, sRConnectionPipe, sRCommandWriterPipe, commandResponsePipe)
        self.serialReaderProcess = mp.Process(target=serialReader.startSerialReader)
        self.serialReaderProcess.daemon = True
        self.serialReaderProcess.start()

        xAxisLength = 100

        self.processes = []
        for i in range(numChannels):
            managedX = self.manager.list()
            managedY = self.manager.list()
            managedAxisLen = mp.Value('i', xAxisLength)
            managedCounter = mp.Value('i', -1)
            eegPlusEDODataProcess = guiPlots.EEGPlusEDODataProcess(running, channelDataArr[i % numChannels], managedX, managedY, managedAxisLen, managedCounter)
            p = mp.Process(target=eegPlusEDODataProcess.startUpdateData)
            p.daemon = True
            p.start()
            self.processes.append(p)

            possPlotData.append(("Ch " + str(i) + " EEG + EDO", eegPlusEDODataProcess))

            managedX = self.manager.list()
            managedY = self.manager.list()
            managedAxisLen = mp.Value('i', xAxisLength)
            managedCounter = mp.Value('i', -1)
            iQMagDataProcess = guiPlots.IQMagDataProcess(running, channelDataArr[i % numChannels], managedX, managedY, managedAxisLen, managedCounter)
            p = mp.Process(target=iQMagDataProcess.startUpdateData)
            p.daemon = True
            p.start()
            self.processes.append(p)

            possPlotData.append(("Ch " + str(i) + " mag(I&Q)", iQMagDataProcess))

            managedX = self.manager.list()
            managedY = self.manager.list()
            managedAxisLen = mp.Value('i', xAxisLength)
            managedCounter = mp.Value('i', -1)
            iQPhaseDataProcess = guiPlots.IQPhaseDataProcess(running, channelDataArr[i % numChannels], managedX, managedY, managedAxisLen, managedCounter)
            p = mp.Process(target=iQPhaseDataProcess.startUpdateData)
            p.daemon = True
            p.start()
            self.processes.append(p)

            possPlotData.append(("Ch " + str(i) + " phase(I&Q)", iQPhaseDataProcess))

        plotLayout = []
        if os.path.exists(configFilename):
            print("Loading config")
            with open(configFilename, 'r') as config:
                configReader = reader(config) # CSV reader
                for plotCol in configReader:
                    plotLayout.append([int(plotNum) for plotNum in plotCol]) # Converts to ints from strings and adds the row to the layout

        if (not os.path.exists(configFilename)) or (not len(plotLayout) == 2): # There are two columns, this needs to be changed if the number of columns changes
            print("Config missing or broken, regenerating")
            plotLayout = [[0,1],[2,3]]
            with open(configFilename, 'w') as config:
                configWriter = writer(config) # CSV writer
                configWriter.writerows(plotLayout)


        layout = CustomGridLayout(running, possPlotData, plotLayout, configFilename, serialReader, connectionPipe, commandWriterPipe, sRCommandResponsePipe, saveDataQueue, xAxisLength, self.manager)

        mainWidget = QWidget()
        mainWidget.setLayout(layout)

        self.setCentralWidget(mainWidget)

        atexit.register(self.exitGracefully)

    def exitGracefully(self):
        for p in self.processes:
            p.terminate()
        self.serialReaderProcess.terminate()
        sys.exit()

class CustomGridLayout(QGridLayout):

    def __init__(self, running, possPlotData, plotLayout, configFilename, serialReader, connectionPipe, commandWriterPipe, sRCommandResponsePipe, saveDataQueue, xAxisLength, manager):

        self.parent = super()
        self.parent.__init__()

        self.manager = manager # This might have help the "AttributeError: 'ForkAwareLocal' object has no attribute 'connection'" error but idk

        current = [] # 2d list of current plots being shown

        labels = [str(d[0]) for d in possPlotData] # Extracts the names of the graphs for the dropdown menu

        # Sets maximum number of plots that can be shown at once, one column can't ever show more than half the graphs or more than 8 graphs
        normalMaxNumPlots = 8
        maxNumPlots = min(normalMaxNumPlots, int(len(possPlotData) / 2))

        # Creates intial plots and puts them into the PlotColumn objects

        defaultPlots = []
        defaultPlotDropdowns = []
        for column in plotLayout:
            currentSublist = []
            defaultPlotsSublist = []
            defaultPlotDropdownsSublist = []

            for plotNum in column:
                currentSublist.append(possPlotData[plotNum])

                plot = guiPlots.CustomPlotWidget(running, possPlotData[plotNum][1], possPlotData[plotNum][0]) # Creates plot widget from a DataProcess
                plot.startRedraw()
                defaultPlotsSublist.append(plot)

                dd = QComboBox() # Creates the starting dropdown menue
                dd.addItems(labels) # Adds the graph names to the dropdown menu
                dd.setCurrentIndex(plotNum) # Sets the item that it should start on, must come before connecting 'currentIndexChanged'
                defaultPlotDropdownsSublist.append(dd)

            current.append(currentSublist)
            defaultPlots.append(defaultPlotsSublist)
            defaultPlotDropdowns.append(defaultPlotDropdownsSublist)
                

        plotColumn0 = guiPlots.PlotColumn(defaultPlots[0], 0, maxNumPlots) # Creates a plot column from a list of plots, an index and the max number of plots
        plotColumn1 = guiPlots.PlotColumn(defaultPlots[1], 1, maxNumPlots)

        columnDropdowns0 = guiOptions.ColumnDropdowns(running, defaultPlotDropdowns[0], plotColumn0, possPlotData, labels, current, maxNumPlots)
        columnDropdowns1 = guiOptions.ColumnDropdowns(running, defaultPlotDropdowns[1], plotColumn1, possPlotData, labels, current, maxNumPlots)

        columnDropdownsLayout = QVBoxLayout()
        columnDropdownsLayout.addWidget(columnDropdowns0)
        columnDropdownsLayout.addWidget(columnDropdowns1)

        combindedPlotColumnLayout = QHBoxLayout()
        combindedPlotColumnLayout.addWidget(plotColumn0)
        combindedPlotColumnLayout.addWidget(plotColumn1)

        saveDataMenuButton = guiData.SaveDataMenuButton(running)

        saveDataWriter = guiData.SaveDataWriter(running, saveDataQueue, saveDataMenuButton)
        saveDataWriter.startSaveDataWriter()

        chatWindow = guiOptions.ChatWindow(commandWriterPipe, sRCommandResponsePipe)
        chatWindow.startUpdate()

        startStop = guiOptions.StartStop(running, connectionPipe, saveDataMenuButton, chatWindow)
        cueSystemButton = guiCue.CueSystemButton(running, startStop)

        xAxisResizer = guiOptions.XAxisResizer(possPlotData, xAxisLength)

        layoutSaver = guiOptions.LayoutSaver(configFilename, columnDropdowns0, columnDropdowns1, chatWindow)

        optionsRowLayout = QHBoxLayout()
        optionsRowLayout.addWidget(saveDataMenuButton)
        optionsRowLayout.addWidget(cueSystemButton)
        optionsRowLayout.addWidget(startStop)
        optionsRowLayout.addWidget(xAxisResizer)
        optionsRowLayout.addWidget(layoutSaver)

        optionsLayout = QVBoxLayout()
        optionsLayout.addLayout(optionsRowLayout)
        optionsLayout.addLayout(columnDropdownsLayout)

        optionsChatLayout = QHBoxLayout()
        optionsChatLayout.addLayout(optionsLayout, 3) # The second param on this line/next line is the stretch. Thus 3/1 gives 75% of the space to the options and 25% to chat
        optionsChatLayout.addWidget(chatWindow, 1)

        self.parent.addLayout(combindedPlotColumnLayout, 0, 0)
        self.parent.addLayout(optionsChatLayout, 1, 0)

        # self.parent.addWidget(serialReader, 4, 0) # The SerialReader and SaveDataWriter both hide themselves, are only attached to be in the event loop
        self.parent.addWidget(saveDataWriter, 4, 1) # TODO check if needed

        current.append([columnDropdowns0, columnDropdowns1]) # Last item in current is list of ColumnDropdowns so they can reference each other

        sleep(1) # Program has to wait for other processes to connect to device before checking
        # 1s wait seems to work but if auto connection is failing but manually clicking works, try making the sleep longer
        startStop.connect("Automatic Connection Attempt Failed") # Automatically clicks "connect" button, gives unique error message on failure
        

def main(port):
    app = QApplication(sys.argv)
    main = MainWindow(port)
    main.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", help="Chip Port Name, /dev/cu.*")
    args = parser.parse_args()
    main(args.port)