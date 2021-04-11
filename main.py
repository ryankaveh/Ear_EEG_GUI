import os, sys, serial, struct, math, atexit
import numpy as np
import multiprocessing as mp
import simpleaudio as sa
import sounddevice as sd
from time import sleep, time
from queue import Queue
from csv import writer
from random import randint
from ctypes import Structure, c_ubyte, c_byte, c_short, c_int
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow, QGridLayout, QVBoxLayout, QHBoxLayout, QWidget, QComboBox, QPushButton, QCheckBox, QLineEdit, QFrame
from PyQt5.QtGui import QPalette, QColor, QRegExpValidator
from PyQt5.QtCore import Qt, QTimer, QProcess, QObject, QRegExp
from pyqtgraph import PlotWidget, plot, mkPen

###
# Known Issues:
#
# Sometimes you have to click start twice the first time. Its something weird with pyqt so idk how to fix it.
#
# AttributeError: 'ForkAwareLocal' object has no attribute 'connection' appears to be something with the manager shutting down? Or maybe too many simultanious manager reads? 
# A rare error but problematic. TODO
###
class MainWindow(QMainWindow):

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.setWindowTitle("Ear EEG GUI")

        numChannels = 8 # Number of channels to expect, will definitely break if value is incorrect

        # List of all DataProcesses that can become graphs (and then be shown) during runtime
        # First item in the tuple is supposed to be the name of the graph, is currently just its color
        possPlotData = []

        # colors = ['b', 'g', 'r', 'c', 'm', 'y', 'k', 'w'] # Background colors of the graphs, currently used as otherwise all graphs would look identical

        self.manager = mp.Manager()

        running = mp.Value('i', False) # Univerally controls whether the DataProcesses run and CustomGraphWidgets redraw themselves

        # Creates SerialReader object to read data from serial port "port", populate channelDataArr and save the data to saveDataQueue
        port = "./ttyGUI"

        channelDataArr = []
        for i in range(0, numChannels):
            lock = mp.RLock()
            channelDataArr.append(mp.Value(ChannelData, 0, 0, 0, 0, lock=lock))

        saveDataQueue = self.manager.Queue()

        condition = mp.Condition()

        serialReader = SerialReader(port, channelDataArr, saveDataQueue, condition)
        self.serialReaderProcess = mp.Process(target=serialReader.startSerialReader)
        self.serialReaderProcess.daemon = True
        self.serialReaderProcess.start()

        with condition:
            condition.wait() # Implies serial reader has connected

        xAxisLength = 100

        self.processes = []
        for i in range(numChannels):
            managedX = self.manager.list()
            managedY = self.manager.list()
            managedAxisLen = mp.Value('i', xAxisLength)
            managedCounter = mp.Value('i', -1)
            eegPlusEDODataProcess = EEGPlusEDODataProcess(running, channelDataArr[i % numChannels], managedX, managedY, managedAxisLen, managedCounter)
            p = mp.Process(target=eegPlusEDODataProcess.startUpdateData)
            p.daemon = True
            p.start()
            self.processes.append(p)

            possPlotData.append(("Ch " + str(i) + " EEG + EDO", eegPlusEDODataProcess))

            managedX = self.manager.list()
            managedY = self.manager.list()
            managedAxisLen = mp.Value('i', xAxisLength)
            managedCounter = mp.Value('i', -1)
            iQMagDataProcess = IQMagDataProcess(running, channelDataArr[i % numChannels], managedX, managedY, managedAxisLen, managedCounter)
            p = mp.Process(target=iQMagDataProcess.startUpdateData)
            p.daemon = True
            p.start()
            self.processes.append(p)

            possPlotData.append(("Ch " + str(i) + " mag(I&Q)", iQMagDataProcess))

            managedX = self.manager.list()
            managedY = self.manager.list()
            managedAxisLen = mp.Value('i', xAxisLength)
            managedCounter = mp.Value('i', -1)
            iQPhaseDataProcess = IQPhaseDataProcess(running, channelDataArr[i % numChannels], managedX, managedY, managedAxisLen, managedCounter)
            p = mp.Process(target=iQPhaseDataProcess.startUpdateData)
            p.daemon = True
            p.start()
            self.processes.append(p)

            possPlotData.append(("Ch " + str(i) + " phase(I&Q)", iQPhaseDataProcess))

        layout = CustomGridLayout(running, possPlotData, serialReader, saveDataQueue, xAxisLength, self.manager)

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

    def __init__(self, running, possPlotData, serialReader, saveDataQueue, xAxisLength, manager):

        self.parent = super()
        self.parent.__init__()

        self.manager = manager # This might have help the "AttributeError: 'ForkAwareLocal' object has no attribute 'connection'" error but idk

        current = [] # Universal 2d list of current plots being shown

        lables = [str(d[0]) for d in possPlotData] # Extracts the names of the graphs for the dropdown menu

        # Sets maximum number of plots that can be shown at once, one column can't ever show more than half the graphs or more than 8 graphs
        normalMaxNumPlots = 8
        maxNumPlots = min(normalMaxNumPlots, int(len(possPlotData) / 2))

        # Creates intial plots and puts them into the PlotColumn objects, currently hardcoded to initially show a 2x2 grid of plots
        plot0 = CustomPlotWidget(running, possPlotData[0][1], possPlotData[0][0]) # Creates plot widget from a DataProcess and a color, color will be removed after testing
        plot0.startRedraw() # Starts the plot widget redrawing itself

        plot1 = CustomPlotWidget(running, possPlotData[1][1], possPlotData[1][0])
        plot1.startRedraw()

        plot2 = CustomPlotWidget(running, possPlotData[2][1], possPlotData[2][0])
        plot2.startRedraw()

        plot3 = CustomPlotWidget(running, possPlotData[3][1], possPlotData[3][0])
        plot3.startRedraw()

        plotColumn0 = PlotColumn([plot0, plot1], 0, maxNumPlots) # Creates a plot column from a list of plots, an index and the max number of plots
        plotColumn1 = PlotColumn([plot2, plot3], 1, maxNumPlots)

        # Creates the starting dropdown menues
        d0 = QComboBox()
        d1 = QComboBox()
        d2 = QComboBox()
        d3 = QComboBox()

        d0.addItems(lables) # Adds the graph names to the dropdown menu
        d0.setCurrentIndex(0) # Sets the item that it should start on, must come before connecting 'currentIndexChanged'

        d1.addItems(lables)
        d1.setCurrentIndex(1)

        d2.addItems(lables)
        d2.setCurrentIndex(2)

        d3.addItems(lables)
        d3.setCurrentIndex(3)

        columnDropdowns0 = ColumnDropdowns(running, [d0, d1], plotColumn0, possPlotData, lables, current, maxNumPlots)
        columnDropdowns1 = ColumnDropdowns(running, [d2, d3], plotColumn1, possPlotData, lables, current, maxNumPlots)

        combindedPlotColumnLayout = QHBoxLayout()
        combindedPlotColumnLayout.addWidget(plotColumn0)
        combindedPlotColumnLayout.addWidget(plotColumn1)

        saveDataMenuButton = SaveDataMenuButton(running)

        saveDataWriter = SaveDataWriter(running, saveDataQueue, saveDataMenuButton)
        saveDataWriter.startSaveDataWriter()

        startStop = StartStop(running, saveDataMenuButton)
        cueSystemButton = CueSystemButton(running, startStop)

        # Adds plots and dropdown menus in a grid format, will have to add other buttons to row 1 later (start/stop, etc.)
        self.parent.addLayout(combindedPlotColumnLayout, 0, 0, 1, 6)
        self.parent.addWidget(saveDataMenuButton, 1, 0)
        self.parent.addWidget(cueSystemButton, 1, 1)
        self.parent.addWidget(startStop, 1, 2)
        self.parent.addWidget(XAxisResizer(possPlotData, xAxisLength), 1, 3)
        self.parent.addWidget(columnDropdowns0, 2, 0, 1, 6)
        self.parent.addWidget(columnDropdowns1, 3, 0, 1, 6)

        # self.parent.addWidget(serialReader, 4, 0) # The SerialReader and SaveDataWriter both hide themselves, are only attached to be in the event loop
        self.parent.addWidget(saveDataWriter, 4, 1)

        current.append([possPlotData[0], possPlotData[1]])
        current.append([possPlotData[2], possPlotData[3]])
        current.append([columnDropdowns0, columnDropdowns1]) # Last item in current is list of ColumnDropdowns so they can reference each other
        
class StartStop(QWidget):

    def __init__(self, running, saveDataMenuButton):

        super().__init__()

        self.running = running
        self.saveDataMenuButton = saveDataMenuButton
        self.layout = QHBoxLayout()

        self.startButton = QPushButton("Start")
        self.startButton.clicked.connect(self.start)

        self.stopButton = QPushButton("Stop")
        self.stopButton.clicked.connect(self.stop)
        self.stopButton.setDisabled(True)

        self.layout.addWidget(self.startButton, 1)
        self.layout.addWidget(self.stopButton, 1)

        self.setLayout(self.layout)

        self.cueSystem = None
        self.synced = None
    
    def start(self):

        self.running.value = True
        self.saveDataMenuButton.setChangeable(False)
        self.startButton.setDisabled(True)
        self.stopButton.setDisabled(False)

        if self.cueSystem:
            self.cueSystem.startStopSync.setDisabled(True)
        if self.synced:
            self.cueSystem.runTest()

    def stop(self):

        self.running.value = False
        self.saveDataMenuButton.setChangeable(True)
        self.stopButton.setDisabled(True)
        self.startButton.setDisabled(False)

        if self.cueSystem:
            self.cueSystem.startStopSync.setDisabled(False)
        if self.synced:
            self.cueSystem.stopTest()

    def setCueSync(self, cueSystem, syncState):

        self.cueSystem = cueSystem
        self.synced = syncState

class XAxisResizer(QWidget):

    def __init__(self, possPlotData, currXAxisLength):

        super().__init__()

        self.possPlotData = possPlotData
        self.currXAxisLength = currXAxisLength

        self.layout = QHBoxLayout()

        self.xAxisLength = QLineEdit()
        self.xAxisLength.setValidator(QRegExpValidator(QRegExp("[0-9]*")))

        self.xAxisResizeButton = QPushButton("Resize")
        self.xAxisResizeButton.clicked.connect(self.resize)
        #self.xAxisResizeButton.setDisabled(True) # TODO: setEnabled vs. setDisabled why do I use both

        self.layout.addWidget(self.xAxisLength)
        self.layout.addWidget(self.xAxisResizeButton)

        self.setLayout(self.layout)

    def resize(self):

        newLength = int(self.xAxisLength.text())
        for dataProcess in self.possPlotData:
            dataProcess[1].resizeXAxis(newLength)
        
# Class containing all of the dropdown menues corrosponding to a certain PlotColumn
class ColumnDropdowns(QWidget):

    def __init__(self, running, startingDropdowns, plotColumn, possPlotData, lables, current, maxNumPlots):

        super().__init__()
        self.layout = QHBoxLayout()

        self.running = running
        self.dropdowns = startingDropdowns
        self.plotColumn = plotColumn # PlotColumn that corrosponds to this set of dropdown menus
        self.possPlotData = possPlotData
        self.lables = lables
        self.current = current
        self.maxNumPlots = maxNumPlots

        self.numPlots = len(startingDropdowns)
        self.screenIdx = self.plotColumn.getScreenIdx() # Corrosponds to index on screen, used to select the right column when indexing into current

        sizeDropdown = QComboBox()
        sizeDropdown.addItems(str(val) for val in range(self.maxNumPlots + 1))
        sizeDropdown.setCurrentIndex(self.numPlots)
        sizeDropdown.currentIndexChanged.connect(self.changeSize)
        self.layout.addWidget(sizeDropdown, 1)

        # Uses lambda function to connect each intial dropdown to changePlotHelper with the right parameters and then adds it to the layout
        for idx, drop in enumerate(self.dropdowns):
            drop.currentIndexChanged.connect(lambda possPlotDataIdx, plotIdx=idx: self.changePlotHelper(possPlotDataIdx, plotIdx))
            self.layout.addWidget(drop, 1)
        
        # Fills dropdowns list so that indexing outside of the current self.numPlots value can be done
        for _ in range(self.maxNumPlots - self.numPlots):
            self.dropdowns.append(None)

        self.setLayout(self.layout)

    # Called when the size dropdown changes value
    def changeSize(self, newSize):

        if self.numPlots == 0:
            self.plotColumn.show()

        sizeDiff = newSize - self.numPlots

        # This section is called when the size goes down, it removes the extra dropdown menus and then tells the PlotColumn to reduce its size
        if sizeDiff < 0:
            for idx in range(newSize, self.numPlots):
                self.layout.removeWidget(self.dropdowns[idx])
                self.dropdowns[idx].deleteLater()
                self.dropdowns[idx] = None

            del self.current[self.screenIdx][newSize:self.numPlots]

            self.plotColumn.shrink(newSize)

            if newSize == 0:
                self.plotColumn.hide()
        
        # This section is called when the size goes up
        # It starts by finding the next sizeDiff DataProcesses that aren't already on screen and creates plot widgets from them
        # It then adds the neccesary dropdown menus and finally tells the PlotColumn to add these new plot widgets
        else:
            newPlots = []
            indices = [] # Used to set the intial value of the dropdown menus
            idx = 0
            while len(newPlots) < sizeDiff:
                possData = self.possPlotData[idx]
                exists = False
                for col in self.current:
                    if possData in col:
                        exists = True
                if not exists:
                    newPlot = CustomPlotWidget(self.running, possData[1], possData[0])
                    newPlot.startRedraw()
                    newPlots.append(newPlot)
                    indices.append(idx)
                    self.current[self.screenIdx].append(possData)
                idx += 1

            for idx in range(self.numPlots, newSize):
                newDrop = QComboBox()
                newDrop.addItems(self.lables)
                newDrop.setCurrentIndex(indices[idx - self.numPlots])
                newDrop.currentIndexChanged.connect(lambda possPlotDataIdx, plotIdx=idx: self.changePlotHelper(possPlotDataIdx, plotIdx))

                self.dropdowns[idx] = newDrop
                self.layout.addWidget(self.dropdowns[idx], 1)

            self.plotColumn.grow(newSize, newPlots)
        
        self.numPlots = newSize
    
    # Called when the user changes any of the plots with the dropdown menu
    def changePlotHelper(self, possPlotDataIdx, plotIdx):

        newPlotData = self.possPlotData[possPlotDataIdx]

        # Checks if the desired plot already exists anywhere on screen
        exists = False
        colIdx = -1 # Equiv to self.screenIdx but for the desired plot (that could be in any column onscreen currently)
        for idx, col in enumerate(self.current):
            if newPlotData in col:
                exists = True
                colIdx = idx

        if exists: # If the graph is already being displayed on screen swap the postion of the new graph and graph currently in the way

            # Primary refers to where the just selected graph will go, secondary refers to where the graph currently in the box will go
            oldSecondaryLoc = self.current[colIdx].index(newPlotData)

            secondary = self.current[-1][colIdx]

            self.plotColumn.tradePlot(plotIdx, secondary.plotColumn, oldSecondaryLoc) # Swaps the plots

            # Updates the secondary dropdown menu to the correct value
            secondaryDrop = secondary.dropdowns[oldSecondaryLoc]
            secondaryDrop.blockSignals(True)
            secondaryDrop.setCurrentIndex(self.possPlotData.index(self.current[self.screenIdx][plotIdx]))
            secondaryDrop.blockSignals(False)

            # Updates the current
            self.current[colIdx][oldSecondaryLoc] = self.current[self.screenIdx][plotIdx]
            self.current[self.screenIdx][plotIdx] = newPlotData

        else: # If the newly selected graph isn't already on the screen it just displays it

            newPlot = CustomPlotWidget(self.running, newPlotData[1], newPlotData[0])
            newPlot.startRedraw()
            self.plotColumn.swapOutPlot(plotIdx, newPlot)
            self.current[self.plotColumn.getScreenIdx()][plotIdx] = newPlotData

class PlotColumn(QWidget):

    def __init__(self, startingPlots, screenIdx, maxNumPlots):

        super().__init__()
        self.layout = QVBoxLayout()

        self.plots = startingPlots
        self.screenIdx = screenIdx

        self.numPlots = len(self.plots)
        self.maxNumPlots = maxNumPlots

        for plot in self.plots:
            self.layout.addWidget(plot, 1)

        # Fills dropdowns list so that indexing outside of the current self.numPlots value can be done
        for _ in range(self.maxNumPlots - self.numPlots):
            self.plots.append(None)

        self.setLayout(self.layout)

    # Used to display a plot that is not currently on the screen
    def swapOutPlot(self, plotIdx, newPlot):
        # This will remove the widget from being onscreen and then actually delete it from memory, very useful so we aren't "drawing" graphs that aren't onscreen
        self.layout.removeWidget(self.plots[plotIdx])
        self.plots[plotIdx].deleteLater()

        self.plots[plotIdx] = newPlot
        self.layout.insertWidget(plotIdx, self.plots[plotIdx], 1)
    
    # Used to trade the plot currently in this object with a plot in another (or even the same) 'PlotColumn' object
    def tradePlot(self, selfIdx, plotColumn, otherIdx):

        # Swaps plot objects in self.plots list
        otherPlot = plotColumn.plots[otherIdx]
        plotColumn.plots[otherIdx] = self.plots[selfIdx]
        self.plots[selfIdx] = otherPlot

        # Instead of deleting the plot widgets, this just removes them from their current layout, this means they don't have to be recreated 
        self.plots[selfIdx].setParent(None)
        plotColumn.plots[otherIdx].setParent(None)

        self.layout.insertWidget(selfIdx, self.plots[selfIdx], 1)
        plotColumn.layout.insertWidget(otherIdx, plotColumn.plots[otherIdx], 1)

    # Called when the PlotColumn needs to reduce the number of graphs it is displaying to newSize
    def shrink(self, newSize):

        for idx in range(newSize, self.numPlots):
            self.layout.removeWidget(self.plots[idx])
            self.plots[idx].deleteLater()
            self.plots[idx] = None
        
        self.numPlots = newSize

    # Called when the PlotColumn needs to increase the number of graphs it is displaying to newSize, adds plot widgets from newPlots
    def grow(self, newSize, newPlots):
        if newSize <= self.maxNumPlots:
            for idx in range(self.numPlots, newSize):
                self.plots[idx] = newPlots[idx - self.numPlots]
                self.layout.addWidget(self.plots[idx], 1)
                
            self.numPlots = newSize

    def getScreenIdx(self):
        return self.screenIdx

# Graphs data given and updated by dataProcess
class CustomPlotWidget(PlotWidget):

    def __init__(self, running, dataProcess, name):

        super().__init__()
        self.running = running
        self.setBackground('w')
        self.dataProcess = dataProcess

        self.refreshRate = 50 # How fast to redraw graph in milliseconds, currently not a parameter as will probably be same for every graph

        self.pen = mkPen(color=(0,0,0), width=3) # Sets color and size of line drawn on graph

        self.setMouseEnabled(x=False, y=False) # Removes ability to drag graph with mouse

        with self.dataProcess.lock:
                x = self.dataProcess.x[:]
                y = self.dataProcess.y[:]
        # x, y = self.dataProcess.getData()

        self.data_line = self.plot(x, y, pen=self.pen)

    # Starts the redrawing of the plot every 'refreshRate' millseconds
    def startRedraw(self):

        self.timer = QTimer()
        self.timer.setInterval(self.refreshRate)
        self.timer.timeout.connect(self.redrawPlot)
        self.timer.start()

    # Redraws plot with data recived from dataProcess
    def redrawPlot(self):
        if bool(self.running.value):
            # x, y = self.dataProcess.getData()
            with self.dataProcess.lock:
                x = self.dataProcess.x[:]
                y = self.dataProcess.y[:]
            self.data_line.setData(x, y)

# Abstract class defining methods needed in all data processes, each distinct graph will have an implementation of this
class DataProcess():

    def __init__(self, running, channelData, x, y, xAxisLength, counter):

        self.running = running
        self.channelData = channelData
        self.xAxisLength = xAxisLength
        self.currPacket = -1
        self.counter = counter # Starts at -1

        # These must be multiprocessing sync manager arrays so the data can be shared back to the process drawing the graphs
        self.x = x
        self.x[:] = list(range(-xAxisLength.value, 0))
        self.y = y
        self.y[:] = [0] * xAxisLength.value
        self.lock = mp.RLock()

        self.refreshRate = 10

    # Starts a loop to call the updateData function 
    def startUpdateData(self):
        
        while True:
            if bool(self.running.value):
                self.updateData()

            # This sleep is just to cap the refresh rate to lower the load on the computer, really no need to go full speed
            sleep(self.refreshRate*.001)

    # Recalculates the graphical data to return based on the raw input
    def updateData(self):
        newX = self.counter.value + 1 # TODO: This should prob be updated to use the difference between the current and next packet ID
        with self.channelData.get_lock():
            packetId = self.channelData.packetId
            newY = self.calculateY()

        if self.currPacket != packetId:
            # If the graph appears as if it is dropping packets you can in theory use a non-locked array to keep track of values
            with self.lock:
                self.x[:] = self.x[1:] + [newX] # FYI iterating through is super slow compared to this apperently
                self.y[:] = self.y[1:] + [newY]
                self.currPacket = packetId
                self.counter.value = newX 

    def resizeXAxis(self, newXAxisLength):
        currXAxisLength = self.xAxisLength.value
        if newXAxisLength > currXAxisLength:
            diff = newXAxisLength - currXAxisLength
            currEnd = self.counter.value + 1 - currXAxisLength

            with self.lock:
                self.x[:] = list(range(currEnd - diff, currEnd)) + self.x[:]
                self.y[:] = ([0] * diff) + self.y[:]

            with self.xAxisLength:
                self.xAxisLength.value = newXAxisLength

        elif newXAxisLength < currXAxisLength:
            diff = currXAxisLength - newXAxisLength

            with self.lock:
                self.x[:] = self.x[diff:]
                self.y[:] = self.y[diff:]

            with self.xAxisLength:
                self.xAxisLength.value = newXAxisLength

# Data process for a simple sine wave
class EEGPlusEDODataProcess(DataProcess):

    def calculateY(self):

        return self.channelData.chxEEG + self.channelData.chxEDO

# Data process for a simple sine wave
class IQMagDataProcess(DataProcess):

    def calculateY(self):
        
        return math.sqrt(self.channelData.chxI^2 + self.channelData.chxQ^2)
    
# Data process for a simple sine wave
class IQPhaseDataProcess(DataProcess):

    def calculateY(self):
        
        return math.atan(self.channelData.chxQ / self.channelData.chxI)

class SerialReader():

    def __init__(self, port, channelDataArr, saveDataQueue, condition):

        self.serialGUISide = None
        self.port = port
        self.channelDataArr = channelDataArr
        self.saveDataQueue = saveDataQueue
        self.condition = condition

        self.refreshRate = 10

    # Starts a loop to call the startSerialReader function 
    def startSerialReader(self):
        while not self.serialGUISide: # This waits for the client (currently the emulator) to create the port
            try:
                # Connection is in startSerialReader because otherwise it doesn't really work with the multiprocessing
                self.serialGUISide = serial.Serial(self.port, 9600, rtscts=True, dsrdtr=True)
            except:
                pass

        with self.condition:
            self.condition.notify_all() # Allows for continuing execution in the main thread

        while True:
            self.updateData()

            # This sleep is just to cap the refresh rate to lower the load on the computer, really no need to go full speed
            sleep(self.refreshRate*.001)

    def updateData(self):
        if self.serialGUISide.in_waiting > 0:
            val = b''
            for i in range(65):
                val += self.serialGUISide.read()

            packetId = int.from_bytes(val[:1], 'big')
            
            saveData = [packetId]

            idx = 0
            for i in range(1, len(val) - 1, 8): # If the number of channels is not 8 this will fail to due to channelDataArr being the wrong size
                chxEEG = int.from_bytes(val[i:i+3], 'big', signed=True)
                chxI = int.from_bytes(val[i+3:i+5], 'big', signed=True)
                chxQ = int.from_bytes(val[i+5:i+7], 'big', signed=True)
                chxEDO = int.from_bytes(val[i+7:i+8], 'big', signed=True)

                with self.channelDataArr[idx].get_lock():
                    self.channelDataArr[idx].chxEEG = chxEEG
                    self.channelDataArr[idx].chxI = chxI
                    self.channelDataArr[idx].chxQ = chxQ
                    self.channelDataArr[idx].chxEDO = chxEDO
                    self.channelDataArr[idx].packetId = packetId
                idx += 1

                saveData.extend((chxEEG, chxI, chxQ, chxEDO))
            
            self.saveDataQueue.put(saveData) # We might want this to be put_nowait

class ChannelData(Structure):
    _fields_ = [("packetId", c_ubyte), ("chxEEG", c_int), ("chxI", c_short), ("chxQ", c_short), ("chxEDO", c_byte)]

class SaveDataMenuButton(QPushButton):

    def __init__(self, running):

        super().__init__("Save Data Menu")
        self.clicked.connect(self.showPopup)

        self.running = running

        self.saveState = 0 # 0 is unchecked, 2 is checked
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
        self.layout = QVBoxLayout()

        self.button = button

        self.saveState = QCheckBox("Save Data")
        self.saveState.setCheckState(saveState)
        self.saveState.stateChanged.connect(button.setSaveState)
        self.saveState.setEnabled(not running.value)

        self.savePostprocessed = QCheckBox("Include Postprocessed Data")
        self.savePostprocessed.setCheckState(savePostprocessed)
        self.savePostprocessed.stateChanged.connect(button.setSavePostprocessedState)
        self.savePostprocessed.setEnabled(False)#(not running.value) This is not currently implemented so the checkbox is disabled

        self.filenameLable = QLabel("Filename:")
        self.filename = QLineEdit(filename)
        self.filename.textChanged.connect(button.setFilename)
        self.filename.setEnabled(not running.value)

        self.filenameLayout = QHBoxLayout()
        self.filenameLayout.addWidget(self.filenameLable)
        self.filenameLayout.addWidget(self.filename)

        self.tooltip = QLabel("Please enter your desired filename\nOn each start and stop numbers will be added to the end\n(abc -> \"abc-0\")")

        self.layout.addWidget(self.saveState)
        self.layout.addWidget(self.savePostprocessed)
        self.layout.addLayout(self.filenameLayout)
        self.layout.addWidget(self.tooltip)

        self.setLayout(self.layout)

    def setChangeable(self, changeable):

        self.saveState.setEnabled(changeable)
        self.savePostprocessed.setEnabled(changeable)
        self.filename.setEnabled(changeable)

class SaveDataWriter(QWidget):

    def __init__(self, running, saveDataQueue, saveDataMenuButton):

        super().__init__()

        self.header = ["packet_id", "chx1_eeg", "chx1_i", "chx1_q", "chx1_edo", "chx2_eeg", "chx2_i", "chx2_q", "chx2_edo", "chx3_eeg", "chx3_i", "chx3_q", "chx3_edo", "chx4_eeg", "chx4_i", "chx4_q", "chx4_edo", "chx5_eeg", "chx5_i", "chx5_q", "chx5_edo", "chx6_eeg", "chx6_i", "chx6_q", "chx6_edo", "chx7_eeg", "chx7_i", "chx7_q", "chx7_edo", "chx8_eeg", "chx8_i", "chx8_q", "chx8_edo"]

        self.running = running
        self.saveDataQueue = saveDataQueue
        self.saveDataMenuButton = saveDataMenuButton

        self.setCurrFilename()

        self.refreshRate = 5

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
                dataWriter = writer(csvfile)
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
        self.currFilename = "data/" + str(self.saveDataMenuButton.filename) + "-" + str(idx) + ".csv"
        while os.path.exists(self.currFilename):
            idx += 1
            self.currFilename = "data/" + str(self.saveDataMenuButton.filename) + "-" + str(idx) + ".csv"
        self.updatedExtenstion = True
        self.saveDataMenuButton.updatedFilename = False

class CueSystemButton(QPushButton):

    def __init__(self, running, startStop):

        super().__init__("Cue System")
        self.running = running
        self.startStop = startStop

        self.clicked.connect(self.showPopup)

        self.cueSystem = None

    def showPopup(self):
        if not self.cueSystem:
            self.cueSystem = CueSystem(self.running, self.startStop)
            self.cueSystem.show()
        else:
            self.cueSystem.show()

class CueSystem(QWidget):

    def __init__(self, running, startStop):

        super().__init__()

        self.running = running
        self.startStop = startStop

        self.layout = QVBoxLayout()

        self.cuePrompt = CuePrompt()
        self.cueParams = QVBoxLayout()

        # Loads beep notification sound
        self.beepWav = sa.WaveObject.from_wave_file("beep.wav")

        self.spacer = QFrame()
        self.spacer.setFrameShape(QFrame.HLine)
        self.spacer.setLineWidth(5)

        self.tooltipLabel = QLabel("")
        self.tooltipLabel.hide()

        # Params setup
        self.baseParams = BaseCueParamLayout()
        self.baseParams.setStyleSheet("BaseCueParamLayout {border: 1px solid black;}")
        self.cueParams.addWidget(self.baseParams)

        self.testSelection = QComboBox()
        self.testSelection.addItems(["Eye Blinks", "Alpha", "ASSR: Clicks", "ASSR: AM Pure Tone", "ASSR: AM White Noise"])
        self.testSelection.setCurrentIndex(0)
        self.currParams = 0
        self.testSelection.currentIndexChanged.connect(self.changeTest)
        self.cueParams.addWidget(self.testSelection)

        eyeBlinks = EyeBlinksLayout(self)
        alpha = AlphaLayout(self)
        clicks = ClicksLayout(self)
        pureTone = PureToneLayout(self)
        whiteNoise = WhiteNoiseLayout(self)

        self.paramList = [eyeBlinks, alpha, clicks, pureTone, whiteNoise]

        self.cueParams.addWidget(self.paramList[0])

        cueStartStopLayout = QGridLayout()

        self.cueStart = QPushButton("Start")
        self.cueStart.clicked.connect(self.runTest)
        cueStartStopLayout.addWidget(self.cueStart, 0, 0)
        self.cueStop = QPushButton("Stop")
        self.cueStop.clicked.connect(self.stopTest)
        cueStartStopLayout.addWidget(self.cueStop, 0, 1)
        self.cueStop.setDisabled(True)
        
        startStopSyncLabel = QLabel("Sync Start/Stop Buttons")
        self.startStopSync = QCheckBox()
        self.startStopSync.stateChanged.connect(self.syncStateChange)
        if self.running.value:
            self.startStopSync.setEnabled(False)
        self.startStop.setCueSync(self, False)
        startStopSyncLayout = QHBoxLayout()
        startStopSyncLayout.addWidget(startStopSyncLabel)
        startStopSyncLayout.addWidget(self.startStopSync)
        cueStartStopLayout.addLayout(startStopSyncLayout, 1, 0)

        self.splitWindowButton = QPushButton("Split Cue Window")
        self.splitWindowButton.clicked.connect(self.splitWindow)
        self.reformWindowButton = QPushButton("Reform Cue Window")
        self.reformWindowButton.clicked.connect(self.reformWindow)
        self.reformWindowButton.hide()

        self.layout.addWidget(self.cuePrompt)
        self.layout.addWidget(self.spacer)
        self.layout.addWidget(self.tooltipLabel)
        self.layout.addLayout(self.cueParams)
        self.layout.addLayout(cueStartStopLayout)
        self.layout.addWidget(self.splitWindowButton)
        self.layout.addWidget(self.reformWindowButton)

        self.setLayout(self.layout)

        self.totalRuntimer = None
        self.durationTimer = None

    def displayTooltip(self, msg):
        self.tooltipLabel.setText(msg)
        self.tooltipLabel.show()

    def resetTooltip(self):
        self.tooltipLabel.setText("")
        self.tooltipLabel.hide()

    def splitWindow(self):

        self.layout.removeWidget(self.cuePrompt)
        self.cuePrompt.setParent(None)
        self.cuePrompt.show()
        self.spacer.hide()
        self.splitWindowButton.hide()
        self.reformWindowButton.show()

    def reformWindow(self):

        self.spacer.show()
        self.cuePrompt.deleteLater() # This is obviously a little hacky but if we don't recreate the cue prompt it throws warnings about apple KVOs which seems worse
        self.cuePrompt = CuePrompt()
        self.layout.insertWidget(0, self.cuePrompt)
        self.reformWindowButton.hide()
        self.splitWindowButton.show()

    def syncStateChange(self, state):

            self.startStop.setCueSync(self, state)

    def changeTest(self, idx):

        self.layout.replaceWidget(self.paramList[self.currParams], self.paramList[idx])
        self.paramList[idx].show()
        self.paramList[self.currParams].hide()
        self.currParams = idx
    
    def startTotalRuntime(self):

        self.currRuntime = -1 # Needed for similar reason as +1 below, first tick should be 0s not 1s
        self.cuePrompt.runtime.setText("0s")

        if self.totalRuntimer and self.totalRuntimer.isActive():
            self.totalRuntimer.stop()
        self.totalRuntimer = QTimer(self)
        self.totalRuntimer.timeout.connect(self.updateTotalRuntime)
        self.totalRuntimer.start(1000)

    def updateTotalRuntime(self):

        self.currRuntime += 1
        self.cuePrompt.runtime.setText(str(self.currRuntime) + "s")

    def runTest(self):

        self.cueStart.setDisabled(True)
        self.startStopSync.setDisabled(True)
        self.cueStop.setDisabled(False)

        self.resetTooltip()

        if self.startStopSync.checkState() and not self.running.value: # And statment is to stop recursion
            self.startStop.start()

        testLayout = self.paramList[self.testSelection.currentIndex()]
        self.currTest = testLayout.name
        startDelayText = self.baseParams.startDelay.text()
        remainingRepsText = self.baseParams.repetitions.text()
        cueLengthText = self.baseParams.cueLength.text()
        restLengthText = self.baseParams.restLength.text()
        endDelayText = self.baseParams.endDelay.text()

        if not (startDelayText and remainingRepsText and cueLengthText and restLengthText and endDelayText):
            self.cuePrompt.cueText.setText("Missing Value")
            self.stopTest()
            return

        self.remainingStartDelay = int(startDelayText) + 1 # This is needed because it ticks down immediately upon reaching that stage

        self.remainingReps = int(remainingRepsText)

        self.originalCueTime = int(cueLengthText) + 1
        self.originalRestTime = int(restLengthText) + 1
        self.remainingCueTime = self.originalCueTime
        self.remainingRestTime = self.originalRestTime

        self.remainingEndDelay = int(endDelayText) + 1

        if self.currTest == "eyeBlinks" or self.currTest == "alpha":
            self.cueAudio = testLayout.cueAudio.isChecked()
        elif self.currTest == "clicks":
            clickFreqText = testLayout.clickFreq.text()
            if not clickFreqText:
                self.displayTooltip("Missing Value")
                self.stopTest()
                return
            self.clickFreq = int(clickFreqText)
        elif self.currTest == "pureTone" or self.currTest == "whiteNoise":
            amFreqText = testLayout.amFreq.text()
            carrierAmpText = testLayout.carrierAmp.text()
            modAmpText = testLayout.modAmp.text()
            
            if not (amFreqText and carrierAmpText and modAmpText):
                self.displayTooltip("Missing Value")
                self.stopTest()
                return

            self.amFreq = int(amFreqText)
            self.carrierAmp = int(carrierAmpText)
            self.modAmp = int(modAmpText)

            if self.currTest == "pureTone":
                carrierFreqText = testLayout.carrierFreq.text()
                if not carrierFreqText:
                    self.displayTooltip("Missing Value")
                    self.stopTest()
                    return
                self.carrierFreq = int(carrierFreqText)

        self.startTotalRuntime()

        if self.durationTimer and self.durationTimer.isActive():
            self.durationTimer.stop()
        self.durationTimer = QTimer(self)
        self.durationTimer.timeout.connect(self.updateDuration)
        self.durationTimer.start(1000)

    def updateDuration(self):

        if self.remainingStartDelay > 1:
            self.cuePrompt.cueText.setText("Wait for test to start...")
            self.remainingStartDelay -= 1
            self.cuePrompt.duration.setText(str(self.remainingStartDelay) + "s")

        elif self.remainingReps > 0:
            if self.currTest == "eyeBlinks":
                self.testEyeBlinks()
            elif self.currTest == "alpha":
                self.testAlpha()
            elif self.currTest in ["clicks", "pureTone", "whiteNoise"]:
                self.testAudio(self.currTest)

        elif self.remainingEndDelay > 1:
            self.cuePrompt.cueText.setText("Wait for test to end...")
            self.remainingEndDelay -= 1
            self.cuePrompt.duration.setText(str(self.remainingEndDelay) + "s")
        else:
            self.stopTest()

    def testEyeBlinks(self):

        if self.remainingRestTime > 1:
            if self.cueAudio and self.remainingRestTime == self.originalRestTime:
                self.beepWav.play()
            self.cuePrompt.cueText.setText("Rest")
            self.remainingRestTime -= 1
            self.cuePrompt.duration.setText(str(self.remainingRestTime) + "s")
        elif self.remainingCueTime > 1:
            if self.cueAudio and self.remainingCueTime == self.originalCueTime:
                self.beepWav.play()
            self.cuePrompt.cueText.setText("Blink")
            self.remainingCueTime -= 1
            self.cuePrompt.duration.setText(str(self.remainingCueTime) + "s")
            if self.remainingCueTime <= 1:
                self.remainingReps -= 1
                self.remainingRestTime = self.originalRestTime
                self.remainingCueTime = self.originalCueTime

    def testAlpha(self):

        if self.remainingRestTime > 1:
            if self.cueAudio and self.remainingRestTime == self.originalRestTime:
                self.beepWav.play()
            self.cuePrompt.cueText.setText("Eyes Open")
            self.remainingRestTime -= 1
            self.cuePrompt.duration.setText(str(self.remainingRestTime) + "s")
        elif self.remainingCueTime > 1:
            if self.cueAudio and self.remainingCueTime == self.originalCueTime:
                self.beepWav.play()
            self.cuePrompt.cueText.setText("Eyes Closed")
            self.remainingCueTime -= 1
            self.cuePrompt.duration.setText(str(self.remainingCueTime) + "s")
            if self.remainingCueTime <= 1:
                self.remainingReps -= 1
                self.remainingRestTime = self.originalRestTime
                self.remainingCueTime = self.originalCueTime

    def testAudio(self, testName):

        if self.remainingRestTime > 1:
            self.cuePrompt.cueText.setText("Rest")
            self.remainingRestTime -= 1
            self.cuePrompt.duration.setText(str(self.remainingRestTime) + "s")
        elif self.remainingCueTime > 1:
            if self.remainingCueTime == self.originalCueTime:
                self.playAudio(testName, self.originalCueTime - 1)
            self.cuePrompt.cueText.setText("Listen")
            self.remainingCueTime -= 1
            self.cuePrompt.duration.setText(str(self.remainingCueTime) + "s")
            if self.remainingCueTime <= 1:
                self.remainingReps -= 1
                self.remainingRestTime = self.originalRestTime
                self.remainingCueTime = self.originalCueTime

    def stopTest(self):

        if self.durationTimer:
            self.durationTimer.stop()
        if self.totalRuntimer:
            self.totalRuntimer.stop()
        self.cuePrompt.duration.setText("0s")
        self.cuePrompt.cueText.setText("No Test Running")

        self.cueStop.setDisabled(True)
        self.startStopSync.setDisabled(False)
        self.cueStart.setDisabled(False)

        self.resetTooltip()

        if self.startStopSync.checkState() and self.running.value:
            self.startStop.stop()

    def playAudio(self, testName, length):

        samplingFreq = 48000

        if testName == "clicks":
            numSamples = 1200
            pulseWidth = 1e-6
            periodLen = 1/self.clickFreq

            clicks = (np.zeros(numSamples) + (np.arange(numSamples) % periodLen < pulseWidth)).astype(np.float32)
            numPeriods = int((length * samplingFreq)/numSamples)
            fullSound = np.tile(clicks, numPeriods)

            # Start playback
            sa.play_buffer(fullClicks, 1, 4, samplingFreq)

        elif testName == "pureTone":
            inital = np.linspace(0, length, length * samplingFreq)
            amPiece = np.cos(2 * np.pi * self.amFreq * inital)
            carrierPiece = np.cos(2 * np.pi * self.carrierFreq * inital)
            fullSound = (self.carrierAmp + self.modAmp * amPiece * carrierPiece).astype(np.float32) # TODO: is this equation correct?

            # Start playback
            sa.play_buffer(fullTone, 1, 4, samplingFreq)

        elif testName == "whiteNoise":
            numSamples = 1200
            whiteNoise = np.random.normal(0, 0.5, size=numSamples) # Made std 0.5 because it kills my ears less but I don't know the "correct" value
            numRepeats = int((length * samplingFreq)/numSamples)

            inital = np.linspace(0, length, length * samplingFreq)
            amPiece = np.cos(2 * np.pi * self.amFreq * inital)
            whiteNoisePiece = np.tile(whiteNoise, numRepeats)
            fullSound = (self.carrierAmp + self.modAmp * amPiece * whiteNoisePiece).astype(np.float32) # TODO: is this equation correct?

        # Start playback
        sa.play_buffer(fullSound, 1, 4, samplingFreq)

class CuePrompt(QWidget):

    def __init__(self):

        super().__init__()
        self.layout = QVBoxLayout()
        # Prompt setup
        self.cueText = QLabel("No Test Running")

        durationLabel = QLabel("Cue Duration")
        self.currDuration = 0
        self.duration = QLabel(str(self.currDuration) + "s")
        self.duration.setStyleSheet("border: 1px solid black;")
        durationLayout = QHBoxLayout()
        durationLayout.addWidget(durationLabel)
        durationLayout.addWidget(self.duration)

        runtimeLabel = QLabel("Total Runtime")
        self.currRuntime = 0
        self.runtime = QLabel(str(self.currRuntime) + "s")
        self.runtime.setStyleSheet("border: 1px solid black;")
        runtimeLayout = QHBoxLayout()
        runtimeLayout.addWidget(runtimeLabel)
        runtimeLayout.addWidget(self.runtime)

        self.layout.addWidget(self.cueText)
        self.layout.addLayout(durationLayout)
        self.layout.addLayout(runtimeLayout)

        self.setLayout(self.layout)

class BaseCueParamLayout(QFrame):

    def __init__(self):

        super().__init__()
        self.layout = QGridLayout()

        numValidator = QRegExpValidator(QRegExp("[0-9]*"))

        self.layout.addWidget(QLabel("Start Delay:"), 0, 0)
        self.startDelay = QLineEdit("0")
        self.startDelay.setValidator(numValidator)
        self.layout.addWidget(self.startDelay, 0, 1)

        self.layout.addWidget(QLabel("End Delay:"), 1, 0)
        self.endDelay = QLineEdit("0")
        self.endDelay.setValidator(numValidator)
        self.layout.addWidget(self.endDelay, 1, 1)

        self.layout.addWidget(QLabel("Repetitions:"), 2, 0)
        self.repetitions = QLineEdit("1")
        self.repetitions.setValidator(numValidator)
        self.layout.addWidget(self.repetitions, 2, 1)

        self.layout.addWidget(QLabel("Cue Length:"), 0, 2)
        self.cueLength = QLineEdit("5")
        self.cueLength.setValidator(numValidator)
        self.layout.addWidget(self.cueLength, 0, 3)

        self.layout.addWidget(QLabel("Rest Length:"), 1, 2)
        self.restLength = QLineEdit("5")
        self.restLength.setValidator(numValidator)
        self.layout.addWidget(self.restLength, 1, 3)

        self.setLayout(self.layout)

class EyeBlinksLayout(QWidget):

    def __init__(self, cueSystem):

        super().__init__()

        self.name = "eyeBlinks"
        self.layout = QGridLayout()

        self.layout.addWidget(QLabel("Cue Audio:"), 0, 0)
        self.cueAudio = QCheckBox()
        self.layout.addWidget(self.cueAudio, 0, 1)

        self.setLayout(self.layout)

class AlphaLayout(QWidget):

    def __init__(self, cueSystem):

        super().__init__()

        self.name = "alpha"
        self.layout = QGridLayout()

        self.layout.addWidget(QLabel("Cue Audio:"), 0, 0)
        self.cueAudio = QCheckBox()
        self.layout.addWidget(self.cueAudio, 0, 1)

        self.setLayout(self.layout)

class ClicksLayout(QWidget):

    def __init__(self, cueSystem):

        super().__init__()

        self.name = "clicks"
        self.layout = QGridLayout()

        numValidator = QRegExpValidator(QRegExp("[0-9]*"))

        self.layout.addWidget(QLabel("Click Frequency:"), 0, 0)
        self.clickFreq = QLineEdit()
        self.clickFreq.setValidator(numValidator)
        self.layout.addWidget(self.clickFreq, 0, 1)

        self.setLayout(self.layout)

class PureToneLayout(QWidget):

    def __init__(self, cueSystem):

        super().__init__()

        self.name = "pureTone"
        self.layout = QGridLayout()

        numValidator = QRegExpValidator(QRegExp("[0-9]*"))

        self.layout.addWidget(QLabel("Carrier Amp:"), 0, 0)
        self.carrierAmp = QLineEdit()
        self.carrierAmp.setValidator(numValidator)
        self.layout.addWidget(self.carrierAmp, 0, 1)

        self.layout.addWidget(QLabel("Modulating Amp:"), 1, 0)
        self.modAmp = QLineEdit()
        self.modAmp.setValidator(numValidator)
        self.layout.addWidget(self.modAmp, 1, 1)

        self.layout.addWidget(QLabel("Carrier Frequency:"), 0, 2)
        self.carrierFreq = QLineEdit()
        self.carrierFreq.setValidator(numValidator)
        self.layout.addWidget(self.carrierFreq, 0, 3)

        self.layout.addWidget(QLabel("AM Frequency:"), 1, 2)
        self.amFreq = QLineEdit()
        self.amFreq.setValidator(numValidator)
        self.layout.addWidget(self.amFreq, 1, 3)

        self.setLayout(self.layout)

class WhiteNoiseLayout(QWidget):

    def __init__(self, cueSystem):

        super().__init__()

        self.name = "whiteNoise"
        self.layout = QGridLayout()

        numValidator = QRegExpValidator(QRegExp("[0-9]*"))

        self.layout.addWidget(QLabel("Carrier Amp:"), 0, 0)
        self.carrierAmp = QLineEdit()
        self.carrierAmp.setValidator(numValidator)
        self.layout.addWidget(self.carrierAmp, 0, 1)

        self.layout.addWidget(QLabel("Modulating Amp:"), 1, 0)
        self.modAmp = QLineEdit()
        self.modAmp.setValidator(numValidator)
        self.layout.addWidget(self.modAmp, 1, 1)

        self.layout.addWidget(QLabel("AM Frequency:"), 0, 2)
        self.amFreq = QLineEdit()
        self.amFreq.setValidator(numValidator)
        self.layout.addWidget(self.amFreq, 0, 3)

        self.setLayout(self.layout)

def main():
    app = QApplication(sys.argv)
    main = MainWindow()
    main.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()