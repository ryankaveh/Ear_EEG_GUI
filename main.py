import os, sys, serial, struct
import numpy as np
import multiprocessing as mp
from time import sleep
from random import randint
from ctypes import Structure, c_ubyte, c_ushort, c_uint
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow, QGridLayout, QVBoxLayout, QHBoxLayout, QWidget, QComboBox, QPushButton
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtCore import Qt, QTimer, QProcess, QObject
from pyqtgraph import PlotWidget, plot, mkPen

class MainWindow(QMainWindow):

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.setWindowTitle("Ear EEG GUI")

        numPlots = 4 # Number of graphs to create, will probally end at 32
        numChannels = 7 # Number of channels to expect, will definitely break if value is incorrect

        possPlotData = []

        colors = ['b', 'g', 'r', 'c', 'm', 'y', 'k', 'w'] # Background colors of the graphs, currently used as otherwise all graphs would look identical

        running = mp.Value('i', False) # Univerally controls whether the DataProcesses run and CustomGraphWidgets redraw themselves

        channelDataArr = []
        for i in range(0,numChannels):
            lock = mp.RLock()
            channelDataArr.append(mp.Value(ChannelData, 0, 0, 0, 0, lock=lock))

        port = "./ttyGUI"
        serialReader = SerialReader(port, channelDataArr)
        serialReader.startSerialReader()

        # Currently creates 'numPlots' identical test graphs, eventually each graph will be created individually
        for i in range(numPlots): 
            dataProcess = SampleDataProcess(running, channelDataArr[i%numChannels])
            p = mp.Process(target=dataProcess.startUpdateData)
            p.daemon = True
            p.start()

            # List of all DataProcesses that can become graphs (and then be shown) during runtime
            # First item in the tuple is supposed to be the name of the graph, is currently just its color
            possPlotData.append((colors[i % len(colors)], dataProcess))

        layout = CustomGridLayout(running, possPlotData, serialReader)

        mainWidget = QWidget()
        mainWidget.setLayout(layout)

        self.setCentralWidget(mainWidget)

class CustomGridLayout(QGridLayout):

    def __init__(self, running, possPlotData, serialReader):

        self.parent = super()
        self.parent.__init__()

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

        # Adds plots and dropdown menus in a grid format, will have to add other buttons to row 1 later (start/stop, etc.)
        self.parent.addLayout(combindedPlotColumnLayout, 0, 0, 1, 4)
        self.parent.addWidget(StartStop(running), 1, 0)
        self.parent.addWidget(columnDropdowns0, 1, 2)
        self.parent.addWidget(columnDropdowns1, 1, 3)
        self.parent.addWidget(serialReader, 1, 4)

        current.append([possPlotData[0], possPlotData[1]]) # 
        current.append([possPlotData[2], possPlotData[3]])
        current.append([columnDropdowns0, columnDropdowns1]) # Last item in current is list of ColumnDropdowns so they can reference each other
        
class StartStop(QWidget):

    def __init__(self, running):

        super().__init__()

        self.running = running
        self.layout = QHBoxLayout()

        startButton = QPushButton("Start")
        startButton.clicked.connect(self.start)

        stopButton = QPushButton("Stop")
        stopButton.clicked.connect(self.stop)

        self.layout.addWidget(startButton, 1)
        self.layout.addWidget(stopButton, 1)

        self.setLayout(self.layout)
    
    def start(self):
        self.running.value = True

    def stop(self):
        self.running.value = False

    

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

    def __init__(self, running, dataProcess, color):

        super().__init__()
        self.running = running
        self.setBackground(color) # Used to distinguish identical plots
        self.dataProcess = dataProcess

        self.refreshRate = 25 # How fast to redraw graph in milliseconds, currently not a parameter as will probably be same for every graph

        self.pen = mkPen(color=(0,0,0), width=3) # Sets color and size of line drawn on graph

        self.setMouseEnabled(x=False, y=False) # Removes ability to drag graph with mouse

        x, y = self.dataProcess.getData()

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
            x, y = self.dataProcess.getData()
            self.data_line.setData(x, y)

# Abstract class defining methods needed in all data processes, each distinct graph will have an implementation of this
class DataProcess():

    # Starts a loop to call the updateData function 
    def startUpdateData(self):
        raise Exception("Child class must implement this method")

    # Recalculates the graphical data to return based on the raw input
    def updateData(self):
        raise Exception("Child class must implement this method")

    # Returns the data neeeded to redraw the graph
    # This method will likely be the same for all children but isn't defined here so all variables remain in the child class
    def getData(self):
        raise Exception("Child class must implement this method")

# Data process for a simple sine wave
class SampleDataProcess(DataProcess):
    
    def __init__(self, running, channelData):

        self.running = running
        self.channelData = channelData
        self.currPacket = -1
        self.counter = 0 # Just used to confirm graphing correctness, should be removed right after

        # These lists are used to keep track of the true value as the lock can sometimes prevent a write
        self.trueX = list(np.arange(-100, 0, 1))
        self.trueY = [0] * 100
        # These must be multiprocessing arrays so the data can be shared back to the process drawing the graphs
        self.x = mp.Array('d', list(np.arange(-100, 0, 1)))
        self.y = mp.Array('d', [0] * 100)        

    def startUpdateData(self):

        while True:
            if bool(self.running.value):
                self.updateData()

            # This sleep is just to cap the refresh rate to lower the load on the computer, really no need to go full speed
            sleep(.01)

    def updateData(self):
        newX = self.counter + 1
        with self.channelData.get_lock():
            packetId = self.channelData.packetId
            newY = self.channelData.chxEEG

        if self.currPacket != packetId:
            self.trueX = self.trueX[1:] + [newX]
            self.trueY = self.trueY[1:] + [newY]
            for i in range(len(self.x)):
                self.x[i] = self.trueX[i]
                self.y[i] = self.trueY[i]
            self.currPacket = packetId
            self.counter = newX 

    def getData(self):
        # [:] needed to extract array from multiprocessing.Array
        return self.x[:], self.y[:]

class SerialReader(QWidget):

    def __init__(self, port, channelDataArr):

        super().__init__()
        self.serialGUISide = None
        while not self.serialGUISide: # This waits for the client (currently the emulator) to create the port
            try:
                self.serialGUISide = serial.Serial(port, 9600, rtscts=True, dsrdtr=True)
            except:
                pass
        self.channelDataArr = channelDataArr

        self.refreshRate = 5

        self.hide()

    def startSerialReader(self):

        self.timer = QTimer()
        self.timer.setInterval(self.refreshRate)
        self.timer.timeout.connect(self.updateData)
        self.timer.start()

    def updateData(self):
        if self.serialGUISide.in_waiting > 0:
            val = b''
            for i in range(57):
                val += self.serialGUISide.read()

            packetId = int.from_bytes(val[:1], 'big')
            
            idx = 0
            for i in range(1, len(val) - 1, 8): # If the number of channels is not 7 this will fail to due to channelDataArr being the wrong size
                chxEEG = int.from_bytes(val[i:i+3], 'big')
                chxI = int.from_bytes(val[i+3:i+5], 'big')
                chxQ = int.from_bytes(val[i+5:i+7], 'big')
                chxEDO = int.from_bytes(val[i+7:i+8], 'big')

                with self.channelDataArr[idx].get_lock():
                    self.channelDataArr[idx].chxEEG = chxEEG
                    self.channelDataArr[idx].chxI = chxI
                    self.channelDataArr[idx].chxQ = chxQ
                    self.channelDataArr[idx].chxEDO = chxEDO
                    self.channelDataArr[idx].packetId = packetId
                idx += 1
            
            print("ID: " + str(packetId))

class ChannelData(Structure):
    _fields_ = [("packetId", c_ubyte), ("chxEEG", c_uint), ("chxI", c_ushort), ("chxQ", c_ushort), ("chxEDO", c_ubyte)]

def main():
    app = QApplication(sys.argv)
    main = MainWindow()
    main.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()