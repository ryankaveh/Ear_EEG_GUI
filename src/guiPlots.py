import math
import multiprocessing as mp
from time import sleep
from PyQt5.QtWidgets import QVBoxLayout, QWidget
from PyQt5.QtCore import QTimer
from pyqtgraph import PlotWidget, mkPen

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

        self.refreshRate = 50 # Refresh rate in ms, controls how often graphs are redrawn

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

        self.refreshRate = 4 # Refresh rate in ms, controls how often new data is looked for

    # Starts a loop to call the updateData function 
    def startUpdateData(self):
        
        while True:
            if bool(self.running.value):
                self.updateData()

            sleep(self.refreshRate * 0.001) # This caps the refresh rate and lowers the load on the computer, full speed not needed

    # Recalculates the graphical data to return based on the raw input
    def updateData(self):
        # newX = self.counter.value + 1 # Old version, use if difference between the current and next packet ID isn't working
        with self.channelData.get_lock():
            packetId = self.channelData.packetId
            newY = self.calculateY()
        newX = self.counter + ((packetId - self.currPacket) % 256) # Assuming no dropped packets this should be 1, % 256 as packets are 0-255

        if self.currPacket != packetId:
            # If the graph appears as if it is dropping packets you can in theory use a non-locked array to keep track of values
            with self.lock:
                self.x[:] = self.x[1:] + [newX] # FYI iterating through is super slow compared to this apperently
                self.y[:] = self.y[1:] + [newY]
                self.currPacket = packetId
                self.counter = newX 

    def resizeXAxis(self, newXAxisLength):
        currXAxisLength = self.xAxisLength.value
        if newXAxisLength > currXAxisLength:
            diff = newXAxisLength - currXAxisLength
            currEnd = self.counter + 1 - currXAxisLength

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
class EEGDataProcess(DataProcess):

    def calculateY(self):

        return self.channelData.chxEEG

# Data process for a simple sine wave
class IQMagDataProcess(DataProcess):

    def calculateY(self):
        
        return math.sqrt(self.channelData.chxI**2 + self.channelData.chxQ**2)
    
# Data process for a simple sine wave
class IQPhaseDataProcess(DataProcess):

    def calculateY(self):
        if self.channelData.chxI == 0:
            return 0
        return math.atan(self.channelData.chxQ / self.channelData.chxI)