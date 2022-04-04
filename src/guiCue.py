import numpy as np
import simpleaudio as sa
from PyQt5.QtWidgets import QLabel, QGridLayout, QVBoxLayout, QHBoxLayout, QWidget, QComboBox, QPushButton, QCheckBox, QLineEdit, QFrame
from PyQt5.QtGui import QRegExpValidator
from PyQt5.QtCore import QTimer, QRegExp

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
        self.cueStop.setEnabled(False)
        
        startStopSyncLabel = QLabel("Sync Start/Stop Buttons")
        self.startStopSync = QCheckBox()
        self.startStopSync.stateChanged.connect(self.syncStateChange)
        if self.running.value:
            self.startStopSync.setEnabled(False)
        # SetCueSync will always succeed as sync starts false, sync can't be true until connection is successful
        # Thus value should not be intialized to true (and will fail if it is)
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
        if not self.startStop.setCueSync(self, state): # Print and revert on failure
            print("Cannot sync until connection is made")
            self.startStopSync.setCheckState(0) # Uncheck box

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

        self.cueStart.setEnabled(False)
        self.startStopSync.setEnabled(False)
        self.cueStop.setEnabled(True)

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

        self.cueStop.setEnabled(False)
        self.startStopSync.setEnabled(True)
        self.cueStart.setEnabled(True)

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
            fullClicks = np.tile(clicks, numPeriods)

            # Start playback
            sa.play_buffer(fullClicks, 1, 4, samplingFreq)

        elif testName == "pureTone":
            inital = np.linspace(0, length, length * samplingFreq)
            amPiece = np.cos(2 * np.pi * self.amFreq * inital)
            carrierPiece = np.cos(2 * np.pi * self.carrierFreq * inital)
            fullTone = (self.carrierAmp + self.modAmp * amPiece * carrierPiece).astype(np.float32)

            # Start playback
            sa.play_buffer(fullTone, 1, 4, samplingFreq)

        elif testName == "whiteNoise":
            numSamples = 1200
            whiteNoise = np.random.normal(0, 0.5, size=numSamples) # Made std 0.5 because it kills my ears less but I don't know the "correct" value
            numRepeats = int((length * samplingFreq)/numSamples)

            inital = np.linspace(0, length, length * samplingFreq)
            amPiece = np.cos(2 * np.pi * self.amFreq * inital)
            whiteNoisePiece = np.tile(whiteNoise, numRepeats)
            fullSound = (self.carrierAmp + self.modAmp * amPiece * whiteNoisePiece).astype(np.float32)

        # Start playback
        sa.play_buffer(fullSound, 1, 4, samplingFreq)

class CuePrompt(QWidget):

    def __init__(self):

        super().__init__()
        layout = QVBoxLayout()
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

        layout.addWidget(self.cueText)
        layout.addLayout(durationLayout)
        layout.addLayout(runtimeLayout)

        self.setLayout(layout)

class BaseCueParamLayout(QFrame):

    def __init__(self):

        super().__init__()
        layout = QGridLayout()

        numValidator = QRegExpValidator(QRegExp("[0-9]*"))

        layout.addWidget(QLabel("Start Delay:"), 0, 0)
        self.startDelay = QLineEdit("0")
        self.startDelay.setValidator(numValidator)
        layout.addWidget(self.startDelay, 0, 1)

        layout.addWidget(QLabel("End Delay:"), 1, 0)
        self.endDelay = QLineEdit("0")
        self.endDelay.setValidator(numValidator)
        layout.addWidget(self.endDelay, 1, 1)

        layout.addWidget(QLabel("Repetitions:"), 2, 0)
        self.repetitions = QLineEdit("1")
        self.repetitions.setValidator(numValidator)
        layout.addWidget(self.repetitions, 2, 1)

        layout.addWidget(QLabel("Cue Length:"), 0, 2)
        self.cueLength = QLineEdit("5")
        self.cueLength.setValidator(numValidator)
        layout.addWidget(self.cueLength, 0, 3)

        layout.addWidget(QLabel("Rest Length:"), 1, 2)
        self.restLength = QLineEdit("5")
        self.restLength.setValidator(numValidator)
        layout.addWidget(self.restLength, 1, 3)

        self.setLayout(layout)

class EyeBlinksLayout(QWidget):

    def __init__(self, cueSystem):

        super().__init__()

        self.name = "eyeBlinks"
        layout = QGridLayout()

        layout.addWidget(QLabel("Cue Audio:"), 0, 0)
        self.cueAudio = QCheckBox()
        layout.addWidget(self.cueAudio, 0, 1)

        self.setLayout(layout)

class AlphaLayout(QWidget):

    def __init__(self, cueSystem):

        super().__init__()

        self.name = "alpha"
        layout = QGridLayout()

        layout.addWidget(QLabel("Cue Audio:"), 0, 0)
        self.cueAudio = QCheckBox()
        layout.addWidget(self.cueAudio, 0, 1)

        self.setLayout(layout)

class ClicksLayout(QWidget):

    def __init__(self, cueSystem):

        super().__init__()

        self.name = "clicks"
        layout = QGridLayout()

        numValidator = QRegExpValidator(QRegExp("[0-9]*"))

        layout.addWidget(QLabel("Click Frequency:"), 0, 0)
        self.clickFreq = QLineEdit()
        self.clickFreq.setValidator(numValidator)
        layout.addWidget(self.clickFreq, 0, 1)

        self.setLayout(layout)

class PureToneLayout(QWidget):

    def __init__(self, cueSystem):

        super().__init__()

        self.name = "pureTone"
        layout = QGridLayout()

        numValidator = QRegExpValidator(QRegExp("[0-9]*"))

        layout.addWidget(QLabel("Carrier Amp:"), 0, 0)
        self.carrierAmp = QLineEdit()
        self.carrierAmp.setValidator(numValidator)
        layout.addWidget(self.carrierAmp, 0, 1)

        layout.addWidget(QLabel("Modulating Amp:"), 1, 0)
        self.modAmp = QLineEdit()
        self.modAmp.setValidator(numValidator)
        layout.addWidget(self.modAmp, 1, 1)

        layout.addWidget(QLabel("Carrier Frequency:"), 0, 2)
        self.carrierFreq = QLineEdit()
        self.carrierFreq.setValidator(numValidator)
        layout.addWidget(self.carrierFreq, 0, 3)

        layout.addWidget(QLabel("AM Frequency:"), 1, 2)
        self.amFreq = QLineEdit()
        self.amFreq.setValidator(numValidator)
        layout.addWidget(self.amFreq, 1, 3)

        self.setLayout(layout)

class WhiteNoiseLayout(QWidget):

    def __init__(self, cueSystem):

        super().__init__()

        self.name = "whiteNoise"
        layout = QGridLayout()

        numValidator = QRegExpValidator(QRegExp("[0-9]*"))

        layout.addWidget(QLabel("Carrier Amp:"), 0, 0)
        self.carrierAmp = QLineEdit()
        self.carrierAmp.setValidator(numValidator)
        layout.addWidget(self.carrierAmp, 0, 1)

        layout.addWidget(QLabel("Modulating Amp:"), 1, 0)
        self.modAmp = QLineEdit()
        self.modAmp.setValidator(numValidator)
        layout.addWidget(self.modAmp, 1, 1)

        layout.addWidget(QLabel("AM Frequency:"), 0, 2)
        self.amFreq = QLineEdit()
        self.amFreq.setValidator(numValidator)
        layout.addWidget(self.amFreq, 0, 3)

        self.setLayout(layout)