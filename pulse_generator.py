#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, os, time, queue
import numpy as np, pyaudio

try:
	# sudo apt-get install python3-pyqt5
	# ~ raise("Uncomment this line is to want to force fallback to PyQt4 for testing")
	from PyQt5.QtGui import *
	from PyQt5.QtCore import *
	from PyQt5.QtWidgets import *
	PYQT_VERSION = 5
	print("Using PyQt5")
except:
	# sudo apt-get install python-qtpy python3-qtpy
	from PyQt4.QtGui import *
	from PyQt4.QtCore import *
	PYQT_VERSION = 4
	print("Using PyQt4")

class PulsingSoundGenerator(QObject):
	SINE = 0
	SINE2 = 1
	SINE3 = 2
	TRIANGLE = 3
	REST_PERIOD = 0
	CSTFREQ_PERIOD = 1
	VARFREQ_PERIOD = 2

	def __init__(self, fs=22050):
		QObject.__init__(self)
		self.newFrequency = None
		self.newVolume = 0
		self.fs = float(fs)
		self.waveFormType = self.SINE
		self.periodMode = self.REST_PERIOD
		self.volume = 0
		self.frequency = 0
		self.baseFrequency = 0
		self.frequencyRaiseRate = 0
		self.frequencyRaiseDelta = 0
		self.maxVolume = 0
		self.currentVolumeFactor = 0
		self.volumeRaiseRate = 0
		self.volumeRaiseDelta = 0
		self.deltaPhase = 0 ; self.deltaTime = 0
		self.currentTimeInCycle = 0
		self.constantFrequencyDuration = 1
		self.stream = None
		self.p = pyaudio.PyAudio()
		self.output_device_index = -1
		self.frames_per_buffer = None

		for i in range(self.p.get_device_count()):
			name = self.p.get_device_info_by_index(i)['name']
			if 'pipewire' in name:
				self.output_device_index = i
			print("%2d %s%s" % (i, "*" if self.output_device_index == i else "", name))

		self.thread = QThread()
		self.thread.setObjectName("Sound Thread")
		self.moveToThread(self.thread)
		self.thread.started.connect(self._run)
		self.thread.start()

	def start(self, fs=None, frames_per_buffer=1000, buffers=3):
		if self.stream is None:
			if fs:
				self.fs = float(fs)

			self.buffers = buffers * [np.zeros(frames_per_buffer).astype(np.float32)]
			self.queue = queue.Queue(maxsize=buffers-1)
			self.buf_idx = 0
			self.bufferPreRoll = 20
			self.phase = 0
			self.currentVolumeFactor = 0
			self.deltaTime = 1/self.fs
			self.frames_per_buffer = frames_per_buffer

			while not self.queue.full():
				time.sleep(0.1)

			self.stream = self.p.open(format=pyaudio.paFloat32, channels=1, rate=int(self.fs), output=True, output_device_index=self.output_device_index, stream_callback=self.callback, frames_per_buffer=frames_per_buffer)
			self.stream.start_stream()

	def stop(self):
		self.frames_per_buffer = None
		if self.stream:
			s, self.stream = self.stream, None
			s.stop_stream()
			s.close()

	def _run(self):
		while not self.thread.isInterruptionRequested():
			if self.frames_per_buffer:
				self.generate()
			else:
				time.sleep(1)

	def callback(self, in_data, frame_count, time_info, status):
		buf = self.buffers[self.queue.get()]
		return (buf, pyaudio.paContinue)

	def generate(self):
		buf = self.buffers[self.buf_idx]

		# [currentVolumeFactor * maxVolume] ---> [newVolume] ---lpf---> [volume]
		for n in range(self.frames_per_buffer):
			if self.periodMode == self.REST_PERIOD:
				self.deltaPhase = 2*np.pi*self.baseFrequency/self.fs
				self.newVolume = 0
			else:
				# advance "time"
				self.currentTimeInCycle+= self.deltaTime

				# compute volume
				self.currentVolumeFactor+=self.volumeRaiseDelta
				if self.currentVolumeFactor > 1:
					self.currentVolumeFactor = 1

				self.newVolume = self.maxVolume * self.currentVolumeFactor

				if self.periodMode == self.VARFREQ_PERIOD:
					# compute frequency shift and signal phase
					self.frequency+=self.frequencyRaiseDelta
					if self.frequency > self.baseFrequency * 2:
						self.frequency = self.baseFrequency
						self.periodMode = self.CSTFREQ_PERIOD
						self.currentTimeInCycle = 0
					self.deltaPhase = 2*np.pi*self.frequency/self.fs

				else: # self.CSTFREQ_PERIOD:
					self.deltaPhase = 2*np.pi*self.frequency/self.fs
					if self.currentTimeInCycle > self.constantFrequencyDuration:
						self.periodMode = self.VARFREQ_PERIOD
						self.frequency = self.baseFrequency
						self.currentTimeInCycle = 0

			# update phase for each sample
			self.phase+=self.deltaPhase
			if self.phase > 2*np.pi:
				self.phase-=2*np.pi

			# make signal...
			if self.waveFormType == self.SINE:
				# simple sinewave
				buf[n] = self.volume * np.sin(self.phase)

			elif self.waveFormType == self.SINE2:
				# squared and alternated sinewave
				buf[n] = self.volume * np.sin(self.phase)**2 * (1 if self.phase > np.pi else -1)

			elif self.waveFormType == self.SINE3:
				# cubed sinewave
				buf[n] = self.volume * np.sin(self.phase)**3

			elif self.waveFormType == self.TRIANGLE:
				# triangle waveform
				if self.phase <= 0.5*np.pi:
					buf[n] = self.volume * (self.phase/(0.5*np.pi))
				elif self.phase <= np.pi*1.5:
					buf[n] = self.volume * (2-(self.phase/(0.5*np.pi)))
				else:
					buf[n] = self.volume * (-4+(self.phase/(0.5*np.pi)))

			else:
				buf[n] = 0

			# IIR low pass filter for volume control
			if self.newVolume != None:
				self.volume, self.oldVolume = self.volume * 0.998 + self.newVolume * 0.002, self.volume
				if self.volume == self.oldVolume:
					self.volume, self.newVolume = self.newVolume, None

		# ~ print("#" * int((time.time() - start)*1000))
		self.queue.put(self.buf_idx)
		self.buf_idx+=1
		if self.buf_idx >= len(self.buffers):
			self.buf_idx = 0

	def __del__(self):
		self.p.terminate()

	def isStreamActive(self):
		if self.stream == None:
			return False
		return self.stream.is_active()

	def setFrequency(self, baseFrequency):
		self.baseFrequency = baseFrequency
		if self.frequencyRaiseRate == 0:
			self.frequency = self.baseFrequency
		self.frequencyRaiseDelta = self.baseFrequency*self.frequencyRaiseRate/self.fs

	def setFrequencyRaiseRate(self, frequencyRaiseRate):
		self.frequencyRaiseRate = frequencyRaiseRate
		self.frequencyRaiseDelta = self.baseFrequency*self.frequencyRaiseRate/self.fs

	def setVolume(self, volume):
		self.maxVolume = volume

	def setVolumeRaiseRate(self, volumeRaiseRate):
		self.volumeRaiseRate = volumeRaiseRate
		self.volumeRaiseDelta = self.volumeRaiseRate/self.fs

	def setConstantFrequencyDuration(self, duration=None, frequency=None):
		if duration:
			self.constantFrequencyDuration = duration
		elif frequency:
			self.constantFrequencyDuration = 1.0/frequency

	def setWaveFormType(self, waveFormType):
		self.waveFormType = waveFormType

	def setActive(self, on=False):
		if on:
			self.periodMode = self.VARFREQ_PERIOD
			self.frequency = self.baseFrequency
		else:
			self.currentVolumeFactor = 0
			self.currentTimeInCycle = 0
			self.newVolume = 0
			self.periodMode = self.REST_PERIOD

class DoubleSlider(QSlider):
	def __init__(self, direction, minValue, maxValue, defaultValue, factor):
		QSlider.__init__(self, direction)
		self.factor = factor
		self.setRange(minValue, maxValue)
		self.setValue(defaultValue)

	def value(self):
		return QSlider.value(self) / float(self.factor)

	def setValue(self, value):
		QSlider.setValue(self, int(round(value * self.factor)))

	def setMinimum(self, minValue):
		QSlider.setMinimum(self, minValue * self.factor)

	def setMaximum(self, maxValue):
		QSlider.setMaximum(self, maxValue * self.factor)

	def setRange(self, minValue, maxValue):
		QSlider.setRange(self, minValue * self.factor, maxValue * self.factor)

class FrequencyPicker(QHBoxLayout):
	def __init__(self, unit="Hz", digitsNumber=6, decimals=2):
		QHBoxLayout.__init__(self)
		self.digitsNumber = digitsNumber
		self.decimals = decimals
		self.digits = {}
		self.digitChangedEvent = None
		self.addStretch()
		for i in range(self.digitsNumber-self.decimals-1, -self.decimals-1, -1):
			l = QLabel("0")
			l.setAlignment(Qt.AlignBottom)
			l.setObjectName("digit")
			l.setToolTip("Use scrollwheel on a digit to change it")
			l.wheelEvent = lambda event, i=i: self.wheelDigitEvent(event, i)
			self.addWidget(l)
			self.digits[i] = l
			if i == 0:
				l = QLabel(".")
				l.setAlignment(Qt.AlignBottom)
				l.setObjectName("digit")
				self.addWidget(l)
		l = QLabel(unit)
		l.setAlignment(Qt.AlignBottom)
		l.setObjectName("label")
		self.addStretch()
		self.updateGreyness()
		self.addWidget(l)

	def wheelDigitEvent(self, event, digit):
		def upDown(digit, inc):
			ret = False
			if digit >= (self.digitsNumber-self.decimals): return True
			digitValue = int(self.digits[digit].text())
			digitValue+=inc
			if digitValue>9:
				digitValue=0
				ret = upDown(digit+1, inc)
			elif digitValue<0:
				digitValue=9
				ret = upDown(digit+1, inc)
			if not ret:
				self.digits[digit].setText(str(digitValue))
			return ret

		if event.angleDelta().y() < 0:
			if digit >= self.firstSignificantDigit:
				if self.digits[digit].text() == "0" or self.digits[digit].text() == "1":
					return
			upDown(digit, -1) # decrement
		else:
			upDown(digit, +1) # increment

		for p in self.digits:
			if p < digit:
				self.digits[p].setText("0")
		self.updateGreyness()

		if self.digitChangedEvent != None:
			self.digitChangedEvent(self.value())

	def updateGreyness(self):
		style = "color: grey;"
		self.firstSignificantDigit = None
		for p in sorted(self.digits, reverse=True):
			if self.digits[p].text() != "0":
				style=""
				if self.firstSignificantDigit == None:
					self.firstSignificantDigit = p
			if p>0:
				self.digits[p].setStyleSheet(style)
		if self.firstSignificantDigit == None:
			self.firstSignificantDigit = p

	def value(self):
		frequency = 0
		for p in self.digits:
			frequency+=(10**p) * int(self.digits[p].text())
		return frequency

	def setValue(self, value):
		frequencyString = ("%0"+str(self.digitsNumber+1)+"."+str(self.decimals)+"f") % round(value, self.decimals);
		if len(frequencyString) > self.digitsNumber+1:
			frequencyString = "9" * self.digitsNumber
		digit = -self.decimals
		while frequencyString != "":
			frequencyString, digitString = frequencyString[:-1], frequencyString[-1:]
			if digitString.isdigit():
				self.digits[digit].setText(digitString)
				digit+=1
		self.updateGreyness()

class GUI(QWidget):
	def __init__(self):
		QWidget.__init__(self)
		self.initUI()
		self.sound = PulsingSoundGenerator()
		self.sound.setFrequency(50)
		self.frequencyPicker.setValue(self.sound.baseFrequency)
		self.frequencyPickerChanged(self.sound.baseFrequency)

	def enableSoundCardBtnClicked(self):
		if self.enableSoundCardBtn.isChecked():
			self.sound.setVolume(self.volumeSlider.value())
			self.sound.setVolumeRaiseRate(self.volumeRaiseRateSlider.value())
			self.sound.setFrequencyRaiseRate(self.frequencyRaiseRate.value())
			self.sound.setConstantFrequencyDuration(frequency=self.constantFrequencyDurationInverse.value())
			self.refreshIndicatorsTimer.start(40)
			self.sound.start()
		else:
			self.enableSoundCardBtn.setEnabled(False)
			self.sound.setVolume(0)
			self.soundOffTimer = QTimer()
			self.soundOffTimer.timeout.connect(self.soundOff)
			self.soundOffTimer.start(500)
			self.refreshIndicatorsTimer.stop()

	def soundOff(self):
		self.sound.stop()
		self.enableSoundCardBtn.setEnabled(True)
		self.soundOffTimer.stop()
		del self.soundOffTimer
		self.frequencyIndicator.setFormat("")
		self.frequencyIndicator.setValue(0)
		self.powerIndicator.setValue(0)

	def initUI(self):
		self.setStyleSheet("\
			QLabel { margin: 0px; padding: 0px; } \
			QSplitter::handle:vertical   { image: none; } \
			QSplitter::handle:horizontal { width:  2px; image: none; } \
			QLabel#digit { font-size: 40pt; padding-left: 0px; padding-right: 0px; } \
			QLabel#label { font-size: 30pt; } \
			QProgressBar { text-align: center; border: 1px solid grey; border-radius: 2px; } \
			QProgressBar#frequency::chunk { background-color: #00d0d0; } \
			QProgressBar#power::chunk { background-color: red; } \
		");
		"""
			#QSlider::groove:horizontal { border: 1px solid #999999; height: 10px; } \
			#QSlider::handle:horizontal { border: 1px solid black; background: white; width: 8px; margin: -2px 0; border-radius: 2px; } \
			#QSlider::add-page:horizontal {  } \
			#QSlider::sub-page:horizontal { background: red; } \
		"""

		def mkLabel(text=None, layout=None, alignment=Qt.AlignLeft, objectName=None):
			o = QLabel()
			if objectName:
				o.setObjectName(objectName)
			o.setAlignment(alignment)
			if text:
				o.setText(text)
			if layout != None:
				layout.addWidget(o)
			return o

		def mkButton(text, layout=None, function=None, gridPlacement=(0,0), gridSpan=(1,1), isCheckable=False):
			btn = QPushButton(text)
			btn.setFocusPolicy(Qt.TabFocus)
			btn.setCheckable(isCheckable)
			if function:
				btn.clicked.connect(function)
			if type(layout) == QGridLayout:
				layout.addWidget(btn, gridPlacement[0], gridPlacement[1], gridSpan[0], gridSpan[1])
			elif layout != None:
				layout.addWidget(btn)
			return btn

		def mkGroupBoxLayout(title, topLayout):
			a = QGroupBox(title)
			topLayout.addWidget(a)
			l = QVBoxLayout(a)
			return l

		layout = QVBoxLayout(self)
		layout2 = mkGroupBoxLayout("Signal Frequency", layout)
		self.frequencyIndicator = QProgressBar()
		self.frequencyIndicator.setFormat("%pHz")
		self.frequencyIndicator.setObjectName("frequency")
		layout2.addWidget(self.frequencyIndicator)

		self.frequencyPicker = FrequencyPicker()
		self.frequencyPicker.digitChangedEvent = self.frequencyPickerChanged
		layout2.addLayout(self.frequencyPicker)

		self.baseFrequency = DoubleSlider(Qt.Horizontal, minValue=25, defaultValue=50, maxValue=75, factor=100)
		self.baseFrequency.setToolTip("Adjust Frequency")
		self.baseFrequency.valueChanged.connect(self.frequencySliderMoved)
		layout2.addWidget(self.baseFrequency)

		self.radiobuttons = []
		self.radiobuttons.append(QRadioButton("&Sine"))
		self.radiobuttons.append(QRadioButton("Sine^&2"))
		self.radiobuttons.append(QRadioButton("Sine^&3"))
		self.radiobuttons.append(QRadioButton("&Triangle"))
		self.radiobuttons[0].setChecked(True)

		l = QHBoxLayout()
		self.buttonsgroup = QButtonGroup()
		self.buttonsgroup.buttonClicked.connect(lambda button: self.sound.setWaveFormType(button.waveType))
		for i, button in enumerate(self.radiobuttons):
			self.buttonsgroup.addButton(button)
			button.waveType = i
			l.addWidget(button)
		layout2.addLayout(l)

		mkLabel("Frequency raise rate factor [Hz/s]", layout2)
		self.frequencyRaiseRate = DoubleSlider(Qt.Horizontal, minValue=0, defaultValue=4, maxValue=75, factor=100)
		self.frequencyRaiseRate.setToolTip("Adjust frequency raise rate factor")
		self.frequencyRaiseRate.valueChanged.connect(lambda: self.sound.setFrequencyRaiseRate(self.frequencyRaiseRate.value()))
		layout2.addWidget(self.frequencyRaiseRate)

		mkLabel("Constant frequency period inverse duration [s^-1]", layout2)
		self.constantFrequencyDurationInverse = DoubleSlider(Qt.Horizontal, minValue=0, defaultValue=4, maxValue=75, factor=100)
		self.constantFrequencyDurationInverse.valueChanged.connect(lambda: self.sound.setConstantFrequencyDuration(frequency=self.constantFrequencyDurationInverse.value()))
		layout2.addWidget(self.constantFrequencyDurationInverse)

		layout2 = mkGroupBoxLayout("Amplitude", layout)
		self.powerIndicator = QProgressBar()
		self.powerIndicator.setObjectName("power")
		layout2.addWidget(self.powerIndicator)

		mkLabel("Maximum amplitude [%]", layout2)
		self.volumeSlider = DoubleSlider(Qt.Horizontal, minValue=0, maxValue=1, defaultValue=0.5, factor=100)
		self.volumeSlider.setToolTip("Adjust maximum amplitude")
		self.volumeSlider.valueChanged.connect(lambda: self.sound.setVolume(self.volumeSlider.value()))
		layout2.addWidget(self.volumeSlider)

		mkLabel("Amplitude raise rate [s^-1]", layout2)
		self.volumeRaiseRateSlider = DoubleSlider(Qt.Horizontal, minValue=0, maxValue=4, defaultValue=1, factor=100)
		self.volumeRaiseRateSlider.setToolTip("Adjust volume raise rate")
		self.volumeRaiseRateSlider.valueChanged.connect(lambda: self.sound.setVolumeRaiseRate(self.volumeRaiseRateSlider.value()))
		layout2.addWidget(self.volumeRaiseRateSlider)

		layout2 = mkGroupBoxLayout("Trigger", layout)

		mkLabel("Pulse repetition rate [min^-1]", layout2)
		self.pulseRepetitionRate = DoubleSlider(Qt.Horizontal, minValue=0, maxValue=120, defaultValue=0, factor=1)
		self.pulseRepetitionRate.valueChanged.connect(self.pulseRepetitionRateUpdate)
		layout2.addWidget(self.pulseRepetitionRate)

		mkLabel("Pulse duration [s]", layout2)
		self.pulseDuration = DoubleSlider(Qt.Horizontal, minValue=0, maxValue=10, defaultValue=1, factor=100)
		self.pulseDuration.valueChanged.connect(self.pulseDurationUpdate)
		layout2.addWidget(self.pulseDuration)

		self.manualPulseBtn = mkButton("Manual Pulse", layout2)
		def manualPulseBtnEvent(state):
			self.manualPulseBtn.isCurrentlyPressedOn = state
			self.sound.setActive(state)
		self.manualPulseBtn.pressed.connect(lambda: manualPulseBtnEvent(True))
		self.manualPulseBtn.released.connect(lambda: manualPulseBtnEvent(False))
		self.manualPulseBtn.isCurrentlyPressedOn = False

		mkLabel("Global Speed", layout)
		def globalRateValueChanged():
			globalRateValue = self.globalRateSlider.value()
			self.volumeRaiseRateSlider.setValue(globalRateValue / 4.0)
			self.frequencyRaiseRate.setValue(globalRateValue)
			self.constantFrequencyDurationInverse.setValue(globalRateValue)
			self.pulseRepetitionRate.setValue(60*globalRateValue/8.0)
			if globalRateValue != 0:
				self.pulseDuration.setValue(4.0/(globalRateValue))
		self.globalRateSlider = DoubleSlider(Qt.Horizontal, minValue=0, maxValue=16, defaultValue=4, factor=100)
		self.globalRateSlider.valueChanged.connect(globalRateValueChanged)
		layout.addWidget(self.globalRateSlider)

		self.enableSoundCardBtn = mkButton("&Enable soundcard", layout, self.enableSoundCardBtnClicked, isCheckable=True)

		self.setWindowTitle("Generator")
		self.setWindowIcon(getEmbeddedIcon())
		self.show()
		self.setMaximumHeight(self.height())

		self.refreshIndicatorsTimer = QTimer()
		self.refreshIndicatorsTimer.timeout.connect(self.refreshIndicators)

		self.triggerPulseTimer = QTimer()
		self.triggerPulseTimer.timeout.connect(self.startPulseTimerTimeout)
		self.stopPulseTimer = QTimer()
		self.stopPulseTimer.setSingleShot(True)
		self.stopPulseTimer.timeout.connect(self.stopPulseTimerTimeout)

	def pulseRepetitionRateUpdate(self):
		rate = self.pulseRepetitionRate.value() # in pulses per minutes
		if rate == 0:
			self.triggerPulseTimer.stop()
			if not self.manualPulseBtn.isCurrentlyPressedOn:
				self.sound.setActive(False)
		else:
			interval_ms = int(round(60000.0 / rate))
			self.pulseRepetitionRate.valueBkp = interval_ms

			try:
				remaining_ms = self.triggerPulseTimer.remainingTime()
			except: # remainingTime() is not available on Qt4
				remaining_ms = -1

			if remaining_ms == -1:
				self.triggerPulseTimer.start(interval_ms)
			elif remaining_ms > 2 * interval_ms:
				self.triggerPulseTimer.setInterval(interval_ms)

			interval_s = interval_ms / 1000.0
			if interval_s < self.pulseDuration.value():
				self.pulseDuration.setValue(interval_s)

	def pulseDurationUpdate(self):
		duration_s = self.pulseDuration.value() # seconds
		if duration_s > 0:
			maxRepetitionRate = 60.0 / duration_s
			if self.pulseRepetitionRate.value() > maxRepetitionRate:
				self.pulseRepetitionRate.setValue(maxRepetitionRate)

	def startPulseTimerTimeout(self):
		# update pulse repetition timer interval
		interval_ms = self.pulseRepetitionRate.valueBkp
		self.triggerPulseTimer.setInterval(interval_ms)

		duration_ms = int(self.pulseDuration.value() * 1000)
		self.stopPulseTimer.start(duration_ms)

		if not self.manualPulseBtn.isCurrentlyPressedOn:
			if self.sound.periodMode:
				self.sound.setActive(False)
			self.sound.setActive(True)

	def stopPulseTimerTimeout(self):
		if not self.manualPulseBtn.isCurrentlyPressedOn:
			self.sound.setActive(False)

	def refreshIndicators(self):
		if self.sound.periodMode:
			self.frequencyIndicator.setFormat("%.1f Hz" % self.sound.frequency)
			self.frequencyIndicator.setValue(min((100, int(round(self.sound.frequency)))))
		else:
			self.frequencyIndicator.setFormat("")
			self.frequencyIndicator.setValue(0)
		self.powerIndicator.setValue(int(round(self.sound.volume * 100)))

	def frequencyPickerChanged(self, frequency):
		self.sound.setFrequency(frequency)
		self.baseFrequency.blockSignals(True)
		self.baseFrequency.setValue(frequency)
		self.baseFrequency.blockSignals(False)

	def frequencySliderMoved(self):
		frequency = self.baseFrequency.value()
		self.frequencyPicker.setValue(frequency)
		self.sound.setFrequency(frequency)

def main():
	app = QApplication(sys.argv)
	gui = GUI()
	app.installEventFilter(gui)
	ret = app.exec_()
	sys.exit(ret)


def getEmbeddedIcon():
	qpm = QPixmap()
	icon = QIcon()
	qba_s = QByteArray(bytes(ICON.encode()))
	qba = QByteArray.fromBase64(qba_s)
	qpm.convertFromImage(QImage.fromData(qba.data(), 'PNG'))
	icon.addPixmap(qpm)
	return icon

ICON = "iVBORw0KGgoAAAANSUhEUgAAAGAAAABgCAMAAADVRocKAAAAM1BMVEVAAAAfIR8hIyAiJCFluWZm\
        umdnu2j/4Nn/4uH+6OT/6+f+7+r/8vP9+Pb/+vn//Pv9//wzqnAOAAAAAXRSTlMAQObYZgAAAZpJ\
        REFUaN7tmclywyAQRKUJcOb/vzYyKhyhBWZrV1xFn+yD+7kFDDBalqmpqamv0noQ1Nwfsj7K1z4f\
        5Ie4Ma8iB8Sz+zGI2p4G9lYEw/6NAPqrCVz7ikD6awgy/33KIv2lGeT+MoLGX0IglX8hEDdAzkoC\
        7gEJppLanxnB4M8joAE3/iElR8IFEDb/EJMX4Mk/heRDOAOKf86bf4oYQH3+KfIyDACP/uVjsBNO\
        gMY0BVYGEaD907wMMkCIna8KQN8/v6arjXAe4/P6SpwMvV1hWIc4y0GS4CrGcrABGJXPCNiGIUAB\
        pTpBAcOpZAbkwe5gB8R+ybADcuwOgwNgyxDDZWQ0xYif4W/2kqSaspfD4evqA6ib9RXnBSjLYa98\
        oYkz3JSJS9gPM6/qJ/CXHRxv/H0Be/VuV93wEmI6+6rOpp84Xn/X/QB/hTJcAlf+NRN6jVVH2H72\
        8z9aCYVAUn8Ct1vQDSMCt7zQTTt925G49sjGqaH1y24t06IVuDk+aO87v0FoIYR5B3IWLW7CviSq\
        EAKaT01NTUH1C9OX0YALDQPvAAAAAElFTkSuQmCC"


if __name__ == '__main__':
	main()

# clx.freeshell.org 2021
