# axidraw.py
# Part of the AxiDraw driver for Inkscape
# https://github.com/evil-mad/AxiDraw
#
# Version 1.0.0, dated February 25, 2016.
# 
# Requires Pyserial 2.7.0 or newer. Pyserial 3.0 recommended.
#
# Copyright 2016 Windell H. Oskay, Evil Mad Scientist Laboratories
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA


from simpletransform import *
from math import sqrt
from array import *
import gettext
import simplepath
import serial
import string
import time

import ebb_serial		# https://github.com/evil-mad/plotink
import ebb_motion		# https://github.com/evil-mad/plotink  Requires version 0.5
import plot_utils		# https://github.com/evil-mad/plotink  Requires version 0.4

import axidraw_conf       	#Some settings can be changed here.

F_DEFAULT_SPEED = 1
N_PEN_DOWN_DELAY = 400    # delay (ms) for the pen to go down before the next move
N_PEN_UP_DELAY = 400      # delay (ms) for the pen to up down before the next move

N_PEN_UP_POS = 50      # Default pen-up position
N_PEN_DOWN_POS = 40      # Default pen-down position

N_SERVOSPEED = 50			# Default pen-lift speed 
N_DEFAULT_LAYER = 1			# Default inkscape layer

class WCB( inkex.Effect ):

	def __init__( self ):
		inkex.Effect.__init__( self )
		self.start_time = time.time()
		
		self.OptionParser.add_option( "--tab",
			action="store", type="string",
			dest="tab", default="controls",
			help="The active tab when Apply was pressed" )
			
		self.OptionParser.add_option( "--penUpPosition",
			action="store", type="int",
			dest="penUpPosition", default=N_PEN_UP_POS,
			help="Position of pen when lifted" )
		self.OptionParser.add_option( "--penDownPosition",
			action="store", type="int",
			dest="penDownPosition", default=N_PEN_DOWN_POS,
			help="Position of pen for painting" )	
			 
		self.OptionParser.add_option( "--setupType",
			action="store", type="string",
			dest="setupType", default="controls",
			help="The active option when Apply was pressed" )
			
		self.OptionParser.add_option( "--penDownSpeed",
			action="store", type="int",
			dest="penDownSpeed", default=F_DEFAULT_SPEED,
			help="Speed (step/sec) while pen is down." )

		self.OptionParser.add_option( "--rapidSpeed",
			action="store", type="int",
			dest="rapidSpeed", default=F_DEFAULT_SPEED,
			help="Rapid speed (percent) while pen is up." )


		self.OptionParser.add_option( "--ServoUpSpeed",
			action="store", type="int",
			dest="ServoUpSpeed", default=N_SERVOSPEED,
			help="Rate of lifting pen " )
		self.OptionParser.add_option( "--penUpDelay",
			action="store", type="int",
			dest="penUpDelay", default=N_PEN_UP_DELAY,
			help="Delay after pen up (msec)." )
		self.OptionParser.add_option( "--ServoDownSpeed",
			action="store", type="int",
			dest="ServoDownSpeed", default=N_SERVOSPEED,
			help="Rate of lowering pen " ) 
		self.OptionParser.add_option( "--penDownDelay",
			action="store", type="int",
			dest="penDownDelay", default=N_PEN_DOWN_DELAY,
			help="Delay after pen down (msec)." )

		self.OptionParser.add_option( "--report_time",
			action="store", type="inkbool",
			dest="report_time", default=False,
			help="Report time elapsed." )
						
		self.OptionParser.add_option( "--revMotor1",
			action="store", type="inkbool",
			dest="revMotor1", default=False,
			help="Reverse motion of Motor 1 (right)." )
		self.OptionParser.add_option( "--revMotor2",
			action="store", type="inkbool",
			dest="revMotor2", default=False,
			help="Reverse motion of Motor 2 (left)." )





		self.OptionParser.add_option( "--constSpeed",
			action="store", type="inkbool",
			dest="constSpeed", default=False,
			help="Use constant velocity mode when pen is down" )
			

		self.OptionParser.add_option( "--autoRotate",
			action="store", type="inkbool",
			dest="autoRotate", default=False,
			help="Print in portrait or landscape mode automatically" )
			
		self.OptionParser.add_option( "--smoothness",
			action="store", type="float",
			dest="smoothness", default=2.0,
			help="Smoothness of curves" )

		self.OptionParser.add_option( "--cornering",
			action="store", type="float",
			dest="cornering", default=2.0,
			help="cornering speed factor" )


		self.OptionParser.add_option( "--resolution",
			action="store", type="int",
			dest="resolution", default=3,
			help="Resolution factor." )	

		self.OptionParser.add_option( "--manualType",
			action="store", type="string",
			dest="manualType", default="controls",
			help="The active option when Apply was pressed" )
		self.OptionParser.add_option( "--WalkDistance",
			action="store", type="float",
			dest="WalkDistance", default=1,
			help="Distance for manual walk" )			
			
		self.OptionParser.add_option( "--resumeType",
			action="store", type="string",
			dest="resumeType", default="controls",
			help="The active option when Apply was pressed" )			
			
		self.OptionParser.add_option( "--layernumber",
			action="store", type="int",
			dest="layernumber", default=N_DEFAULT_LAYER,
			help="Selected layer for multilayer plotting" )			

		self.serialPort = None
		self.bPenIsUp = None  #Initial state of pen is neither up nor down, but _unknown_.
		self.virtualPenIsUp = False  #Keeps track of pen postion when stepping through plot before resuming
		self.ignoreLimits = False


		fX = None
		fY = None 
		self.fCurrX = axidraw_conf.StartPos_X
		self.fCurrY = axidraw_conf.StartPos_Y 
		self.ptFirst = ( axidraw_conf.StartPos_X, axidraw_conf.StartPos_Y)
		self.bStopped = False
		self.fSpeed = 1
		self.resumeMode = False
		self.nodeCount = int( 0 )		#NOTE: python uses 32-bit ints.
		self.nodeTarget = int( 0 )
		self.pathcount = int( 0 )
		self.LayersFoundToPlot = False
		
		#Values read from file:
		self.svgLayer_Old = int( 0 )
		self.svgNodeCount_Old = int( 0 )
		self.svgDataRead_Old = False
		self.svgLastPath_Old = int( 0 )
		self.svgLastPathNC_Old = int( 0 )
		self.svgLastKnownPosX_Old = float( 0.0 )
		self.svgLastKnownPosY_Old = float( 0.0 )
		self.svgPausedPosX_Old = float( 0.0 )
		self.svgPausedPosY_Old = float( 0.0 )	
		
		#New values to write to file:
		self.svgLayer = int( 0 )
		self.svgNodeCount = int( 0 )
		self.svgDataRead = False
		self.svgLastPath = int( 0 )
		self.svgLastPathNC = int( 0 )
		self.svgLastKnownPosX = float( 0.0 )
		self.svgLastKnownPosY = float( 0.0 )
		self.svgPausedPosX = float( 0.0 )
		self.svgPausedPosY = float( 0.0 )	

		self.backlashStepsX = int(0)
		self.backlashStepsY = int(0)	 
		self.XBacklashFlag = True
		self.YBacklashFlag = True
		
		self.manConfMode = False
		self.PrintFromLayersTab = False

		self.svgWidth = 0 
		self.svgHeight = 0
		self.printPortrait = False
		
		self.xBoundsMax = axidraw_conf.N_PAGE_WIDTH
		self.xBoundsMin = axidraw_conf.StartPos_X
		self.yBoundsMax = axidraw_conf.N_PAGE_HEIGHT
		self.yBoundsMin = axidraw_conf.StartPos_Y
		
		self.svgTransform = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
		
		self.stepsPerInch = 0 # must be set to a nonzero value before plotting.
		self.PenDownSpeed = 0.25 * axidraw_conf.Speed_Scale #Default speed when pen is down		
		self.PenUpSpeed = 0.75 * axidraw_conf.Speed_Scale #Default speed when pen is down	

		# So that we only generate a warning once for each
		# unsupported SVG element, we use a dictionary to track
		# which elements have received a warning
		self.warnings = {}
		self.warnOutOfBounds = False

	def effect( self ):
		'''Main entry point: check to see which tab is selected, and act accordingly.'''

		self.svg = self.document.getroot()
		self.CheckSVGforWCBData()
		useOldResumeData = True

		skipSerial = False
		if (self.options.tab == '"Help"'):
			skipSerial = True
 		if (self.options.tab == '"options"'):
			skipSerial = True 		
 		if (self.options.tab == '"timing"'):
			skipSerial = True
 		
 		if skipSerial == False:
 			self.serialPort = ebb_serial.openPort()
 			if self.serialPort is None:
				inkex.errormsg( gettext.gettext( "Failed to connect to AxiDraw. :(" ) )
		
			if self.options.tab == '"splash"': 
				self.LayersFoundToPlot = False
				useOldResumeData = False
				self.PrintFromLayersTab = False
				self.plotCurrentLayer = True
				if self.serialPort is not None:
					self.svgNodeCount = 0
					self.svgLastPath = 0
					unused_button = ebb_motion.QueryPRGButton(self.serialPort)	#Query if button pressed
					self.svgLayer = 12345;  # indicate (to resume routine) that we are plotting all layers.
					self.plotDocument()

			elif self.options.tab == '"resume"':
				if self.serialPort is None:
					useOldResumeData = True
				else:
					useOldResumeData = False
					unused_button = ebb_motion.QueryPRGButton(self.serialPort)	#Query if button pressed
					self.resumePlotSetup()
					if self.resumeMode:
						fX = self.svgPausedPosX_Old + axidraw_conf.StartPos_X
						fY = self.svgPausedPosY_Old + axidraw_conf.StartPos_Y
		 				self.resumeMode = False
	
						self.plotSegmentWithVelocity( fX, fY, 0, 0)
						
						self.resumeMode = True
						self.nodeCount = 0
						self.plotDocument() 
						
					elif ( self.options.resumeType == "justGoHome" ):
						fX = axidraw_conf.StartPos_X
						fY = axidraw_conf.StartPos_Y 

						self.plotSegmentWithVelocity( fX, fY, 0, 0)
							
						#New values to write to file:
						self.svgNodeCount = self.svgNodeCount_Old
						self.svgLastPath = self.svgLastPath_Old 
						self.svgLastPathNC = self.svgLastPathNC_Old 
						self.svgPausedPosX = self.svgPausedPosX_Old 
						self.svgPausedPosY = self.svgPausedPosY_Old
						self.svgLayer = self.svgLayer_Old 
		
					else:
						inkex.errormsg( gettext.gettext( "There does not seem to be any in-progress plot to resume." ) )
	
			elif self.options.tab == '"layers"':
				useOldResumeData = False 
				self.PrintFromLayersTab = True
				self.plotCurrentLayer = False
				self.LayersFoundToPlot = False
				self.svgLastPath = 0
				if self.serialPort is not None:
					unused_button = ebb_motion.QueryPRGButton(self.serialPort)	#Query if button pressed
					self.svgNodeCount = 0;
					self.svgLayer = self.options.layernumber
					self.plotDocument()

			elif self.options.tab == '"setup"':
				self.setupCommand()
				
			elif self.options.tab == '"manual"':
				if self.options.manualType == "strip-data":
					for node in self.svg.xpath( '//svg:WCB', namespaces=inkex.NSS ):
						self.svg.remove( node )
					for node in self.svg.xpath( '//svg:eggbot', namespaces=inkex.NSS ):
						self.svg.remove( node )
					inkex.errormsg( gettext.gettext( "I've removed all AxiDraw data from this SVG file. Have a great day!" ) )
					return	
				else:	
					useOldResumeData = False 
					self.svgNodeCount = self.svgNodeCount_Old
					self.svgLastPath = self.svgLastPath_Old 
					self.svgLastPathNC = self.svgLastPathNC_Old 
					self.svgPausedPosX = self.svgPausedPosX_Old 
					self.svgPausedPosY = self.svgPausedPosY_Old
					self.svgLayer = self.svgLayer_Old 
					self.manualCommand()

		if (useOldResumeData):	#Do not make any changes to data saved from SVG file.
			self.svgNodeCount = self.svgNodeCount_Old
			self.svgLastPath = self.svgLastPath_Old 
			self.svgLastPathNC = self.svgLastPathNC_Old 
			self.svgPausedPosX = self.svgPausedPosX_Old 
			self.svgPausedPosY = self.svgPausedPosY_Old
			self.svgLayer = self.svgLayer_Old 				
			self.svgLastKnownPosX = self.svgLastKnownPosX_Old
			self.svgLastKnownPosY = self.svgLastKnownPosY_Old 

		self.svgDataRead = False
		self.UpdateSVGWCBData( self.svg )
		if self.serialPort is not None:
			ebb_motion.doTimedPause(self.serialPort, 10) #Pause a moment for underway commands to finish...
			ebb_serial.closePort(self.serialPort)	
		
	def resumePlotSetup( self ):
		self.LayerFound = False
		if ( self.svgLayer_Old < 101 ) and ( self.svgLayer_Old >= 0 ):
			self.options.layernumber = self.svgLayer_Old 
			self.PrintFromLayersTab = True
			self.plotCurrentLayer = False
			self.LayerFound = True
		elif ( self.svgLayer_Old == 12345 ):  # Plot all layers 
			self.PrintFromLayersTab = False
			self.plotCurrentLayer = True
			self.LayerFound = True 	
		if ( self.LayerFound ):
			if ( self.svgNodeCount_Old > 0 ):
				self.nodeTarget = self.svgNodeCount_Old
				self.svgLayer = self.svgLayer_Old
				if self.options.resumeType == "ResumeNow":
					self.resumeMode = True
				if self.serialPort is None:
					return
				self.ServoSetup()
				self.penUp() 
				self.EnableMotors() #Set plotting resolution  
				self.fSpeed = self.options.penDownSpeed
				self.fCurrX = self.svgLastKnownPosX_Old + axidraw_conf.StartPos_X
				self.fCurrY = self.svgLastKnownPosY_Old + axidraw_conf.StartPos_Y
				 

	def CheckSVGforWCBData( self ):
		self.svgDataRead = False
		self.recursiveWCBDataScan( self.svg )
		if ( not self.svgDataRead ):    #if there is no WCB data, add some:
			WCBlayer = inkex.etree.SubElement( self.svg, 'WCB' )
			WCBlayer.set( 'layer', str( 0 ) )
			WCBlayer.set( 'node', str( 0 ) )			#node paused at, if saved in paused state
			WCBlayer.set( 'lastpath', str( 0 ) )		#Last path number that has been fully painted
			WCBlayer.set( 'lastpathnc', str( 0 ) )		#Node count as of finishing last path.
			WCBlayer.set( 'lastknownposx', str( 0 ) )  #Last known position of carriage
			WCBlayer.set( 'lastknownposy', str( 0 ) )
			WCBlayer.set( 'pausedposx', str( 0 ) )	   #The position of the carriage when "pause" was pressed.
			WCBlayer.set( 'pausedposy', str( 0 ) )
						
	def recursiveWCBDataScan( self, aNodeList ):
		if ( not self.svgDataRead ):
			for node in aNodeList:
				if node.tag == 'svg':
					self.recursiveWCBDataScan( node )
				elif node.tag == inkex.addNS( 'WCB', 'svg' ) or node.tag == 'WCB':
					try:
						self.svgLayer_Old = int( node.get( 'layer' ) )
						self.svgNodeCount_Old = int( node.get( 'node' ) )
						self.svgLastPath_Old = int( node.get( 'lastpath' ) )
						self.svgLastPathNC_Old = int( node.get( 'lastpathnc' ) )
						self.svgLastKnownPosX_Old = float( node.get( 'lastknownposx' ) )
						self.svgLastKnownPosY_Old = float( node.get( 'lastknownposy' ) ) 
						self.svgPausedPosX_Old = float( node.get( 'pausedposx' ) )
						self.svgPausedPosY_Old = float( node.get( 'pausedposy' ) ) 
						self.svgDataRead = True
					except:
						pass

	def UpdateSVGWCBData( self, aNodeList ):
		if ( not self.svgDataRead ):
			for node in aNodeList:
				if node.tag == 'svg':
					self.UpdateSVGWCBData( node )
				elif node.tag == inkex.addNS( 'WCB', 'svg' ) or node.tag == 'WCB':
					node.set( 'layer', str( self.svgLayer ) )
					node.set( 'node', str( self.svgNodeCount ) )
					node.set( 'lastpath', str( self.svgLastPath ) )
					node.set( 'lastpathnc', str( self.svgLastPathNC ) )
					node.set( 'lastknownposx', str( (self.svgLastKnownPosX ) ) )
					node.set( 'lastknownposy', str( (self.svgLastKnownPosY ) ) )
					node.set( 'pausedposx', str( (self.svgPausedPosX) ) )
					node.set( 'pausedposy', str( (self.svgPausedPosY) ) )
					
					self.svgDataRead = True
					 
	def setupCommand( self ):
		"""Execute commands from the "setup" tab"""

		if self.serialPort is None:
			return

		self.ServoSetupWrapper()

		if self.options.setupType == "align-mode":
			self.penUp()
			ebb_motion.sendDisableMotors(self.serialPort)	

		elif self.options.setupType == "toggle-pen":
			ebb_motion.TogglePen(self.serialPort)

	def manualCommand( self ):
		"""Execute commands from the "manual" tab"""

		if self.options.manualType == "none":
			return
			
		if self.serialPort is None:
			return 

		if self.options.manualType == "raise-pen":
			self.ServoSetupWrapper()
			self.penUp()

		elif self.options.manualType == "lower-pen":
			self.ServoSetupWrapper()
			self.penDown()

		elif self.options.manualType == "enable-motors":
			self.EnableMotors()

		elif self.options.manualType == "disable-motors":
			ebb_motion.sendDisableMotors(self.serialPort)	

		elif self.options.manualType == "version-check":
			strVersion = ebb_serial.query( self.serialPort, 'v\r' )
			inkex.errormsg( 'I asked the EBB for its version info, and it replied:\n ' + strVersion )

		else:  # self.options.manualType is walk motor:
			if self.options.manualType == "walk-y-motor":
				nDeltaX = 0
				nDeltaY = self.options.WalkDistance
			elif self.options.manualType == "walk-x-motor":
				nDeltaY = 0
				nDeltaX = self.options.WalkDistance
			else:
				return
			
			self.fSpeed = self.options.penDownSpeed
				
 			self.EnableMotors() #Set plotting resolution 
			self.fCurrX = self.svgLastKnownPosX_Old + axidraw_conf.StartPos_X
			self.fCurrY = self.svgLastKnownPosY_Old + axidraw_conf.StartPos_Y
			self.ignoreLimits = True
			fX = self.fCurrX + nDeltaX   #Note: Walking motors is STRICTLY RELATIVE TO INITIAL POSITION.
			fY = self.fCurrY + nDeltaY
			self.plotSegmentWithVelocity( fX, fY, 0, 0)



	def plotDocument( self ):
		'''Plot the actual SVG document, if so selected in the interface:'''
		#parse the svg data as a series of line segments and send each segment to be plotted

		if self.serialPort is None:
			return

		if (not self.getDocProps()):
			# Cannot handle the document's dimensions!!!
			inkex.errormsg( gettext.gettext(
			'This document does not have valid dimensions.\r' +
			'The document dimensions must be in either' +
			'millimeters (mm) or inches (in).\r\r'	+			
			'Consider starting with the "Letter landscape" or ' +
			'the "A4 landscape" template.\r\r' +
			'Document dimensions may also be set in Inkscape,\r' +
			'using File > Document Properties.') )
			return

		# Viewbox handling
		# Also ignores the preserveAspectRatio attribute
		viewbox = self.svg.get( 'viewBox' )
		if viewbox:
			vinfo = viewbox.strip().replace( ',', ' ' ).split( ' ' )
			if ( vinfo[2] != 0 ) and ( vinfo[3] != 0 ):
				sx = self.svgWidth / float( vinfo[2] )
				sy = self.svgHeight / float( vinfo[3] )
# 				inkex.errormsg( 'self.svgWidth:  ' + str(self.svgWidth) )
# 				inkex.errormsg( 'float( vinfo[2] ):  ' + str(float( vinfo[2] ) ))
# 				inkex.errormsg( 'sx:  ' + str(sx) )				
				self.svgTransform = parseTransform( 'scale(%f,%f) translate(%f,%f)' % (sx, sy, -float( vinfo[0] ), -float( vinfo[1])))
# 				inkex.errormsg( 'svgTransform:  ' + str(self.svgTransform) )

		self.ServoSetup()
		self.penUp() 
		self.EnableMotors() #Set plotting resolution

		try:
			# wrap everything in a try so we can for sure close the serial port 
			self.recursivelyTraverseSvg( self.svg, self.svgTransform )
			self.penUp()   #Always end with pen-up
 
			# return to home after end of normal plot
			if ( ( not self.bStopped ) and ( self.ptFirst ) ):
				self.xBoundsMin = axidraw_conf.StartPos_X
				self.yBoundsMin = axidraw_conf.StartPos_Y
				fX = self.ptFirst[0]
				fY = self.ptFirst[1] 
 				self.nodeCount = self.nodeTarget    
				self.plotSegmentWithVelocity( fX, fY, 0, 0)
				
			if ( not self.bStopped ): 
				if (self.options.tab == '"splash"') or (self.options.tab == '"layers"') or (self.options.tab == '"resume"'):
					self.svgLayer = 0
					self.svgNodeCount = 0
					self.svgLastPath = 0
					self.svgLastPathNC = 0
					self.svgLastKnownPosX = 0
					self.svgLastKnownPosY = 0
					self.svgPausedPosX = 0
					self.svgPausedPosY = 0
					#Clear saved position data from the SVG file,
					#  IF we have completed a normal plot from the splash, layer, or resume tabs.
			if (self.warnOutOfBounds):
				inkex.errormsg( gettext.gettext( 'Warning: Off-page elements found. AxiDraw movement was limited by its physical range of motion.' ) )
			if (self.options.report_time):
				elapsed_time = time.time() - self.start_time
				m, s = divmod(elapsed_time, 60)
				h, m = divmod(m, 60)
				inkex.errormsg("Elapsed time: %d:%02d:%02d" % (h, m, s) + " (Hours, minutes, seconds)")
				
		finally:
			# We may have had an exception and lost the serial port...
			pass

	def recursivelyTraverseSvg( self, aNodeList,
			matCurrent=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
			parent_visibility='visible' ):
		"""
		Recursively traverse the svg file to plot out all of the
		paths.  The function keeps track of the composite transformation
		that should be applied to each path.

		This function handles path, group, line, rect, polyline, polygon,
		circle, ellipse and use (clone) elements.  Notable elements not
		handled include text.  Unhandled elements should be converted to
		paths in Inkscape.
		"""
		for node in aNodeList:
			# Ignore invisible nodes
			v = node.get( 'visibility', parent_visibility )
			if v == 'inherit':
				v = parent_visibility
			if v == 'hidden' or v == 'collapse':
				pass

			# first apply the current matrix transform to this node's transform
			matNew = composeTransform( matCurrent, parseTransform( node.get( "transform" ) ) )

			if node.tag == inkex.addNS( 'g', 'svg' ) or node.tag == 'g':

				if ( node.get( inkex.addNS( 'groupmode', 'inkscape' ) ) == 'layer' ): 
					self.DoWePlotLayer( node.get( inkex.addNS( 'label', 'inkscape' ) ) )
					self.penUp()
				self.recursivelyTraverseSvg( node, matNew, parent_visibility=v )			
			
			elif node.tag == inkex.addNS( 'use', 'svg' ) or node.tag == 'use':

				# A <use> element refers to another SVG element via an xlink:href="#blah"
				# attribute.  We will handle the element by doing an XPath search through
				# the document, looking for the element with the matching id="blah"
				# attribute.  We then recursively process that element after applying
				# any necessary (x,y) translation.
				#
				# Notes:
				#  1. We ignore the height and width attributes as they do not apply to
				#     path-like elements, and
				#  2. Even if the use element has visibility="hidden", SVG still calls
				#     for processing the referenced element.  The referenced element is
				#     hidden only if its visibility is "inherit" or "hidden".

				refid = node.get( inkex.addNS( 'href', 'xlink' ) )
				if refid:
					# [1:] to ignore leading '#' in reference
					path = '//*[@id="%s"]' % refid[1:]
					refnode = node.xpath( path )
					if refnode:
						x = float( node.get( 'x', '0' ) )
						y = float( node.get( 'y', '0' ) )
						# Note: the transform has already been applied
						if ( x != 0 ) or (y != 0 ):
							matNew2 = composeTransform( matNew, parseTransform( 'translate(%f,%f)' % (x,y) ) )
						else:
							matNew2 = matNew
						v = node.get( 'visibility', v )
						self.recursivelyTraverseSvg( refnode, matNew2, parent_visibility=v )
					else:
						pass
				else:
					pass

			elif node.tag == inkex.addNS( 'path', 'svg' ):

				# if we're in resume mode AND self.pathcount < self.svgLastPath,
				#    then skip over this path.
				# if we're in resume mode and self.pathcount = self.svgLastPath,
				#    then start here, and set self.nodeCount equal to self.svgLastPathNC
				
				doWePlotThisPath = False 
				if (self.resumeMode): 
					if (self.pathcount < self.svgLastPath_Old ): 
						#This path was *completely plotted* already; skip.
						self.pathcount += 1 
					elif (self.pathcount == self.svgLastPath_Old ): 
						#this path is the first *not completely* plotted path:
						self.nodeCount =  self.svgLastPathNC_Old	#Nodecount after last completed path
						doWePlotThisPath = True 
				else:
					doWePlotThisPath = True
				if (doWePlotThisPath):
					self.pathcount += 1
					self.plotPath( node, matNew )
				
			elif node.tag == inkex.addNS( 'rect', 'svg' ) or node.tag == 'rect':

				# Manually transform 
				#    <rect x="X" y="Y" width="W" height="H"/> 
				# into 
				#    <path d="MX,Y lW,0 l0,H l-W,0 z"/> 
				# I.e., explicitly draw three sides of the rectangle and the
				# fourth side implicitly

				 
				# if we're in resume mode AND self.pathcount < self.svgLastPath,
				#    then skip over this path.
				# if we're in resume mode and self.pathcount = self.svgLastPath,
				#    then start here, and set
				# self.nodeCount equal to self.svgLastPathNC
				
				doWePlotThisPath = False 
				if (self.resumeMode): 
					if (self.pathcount < self.svgLastPath_Old ): 
						#This path was *completely plotted* already; skip.
						self.pathcount += 1 
					elif (self.pathcount == self.svgLastPath_Old ): 
						#this path is the first *not completely* plotted path:
						self.nodeCount =  self.svgLastPathNC_Old	#Nodecount after last completed path
						doWePlotThisPath = True 
				else:
					doWePlotThisPath = True
				if (doWePlotThisPath):
					self.pathcount += 1
					# Create a path with the outline of the rectangle
					newpath = inkex.etree.Element( inkex.addNS( 'path', 'svg' ) )
					x = float( node.get( 'x' ) )
					y = float( node.get( 'y' ) )
					w = float( node.get( 'width' ) )
					h = float( node.get( 'height' ) )
					s = node.get( 'style' )
					if s:
						newpath.set( 'style', s )
					t = node.get( 'transform' )
					if t:
						newpath.set( 'transform', t )
					a = []
					a.append( ['M ', [x, y]] )
					a.append( [' l ', [w, 0]] )
					a.append( [' l ', [0, h]] )
					a.append( [' l ', [-w, 0]] )
					a.append( [' Z', []] )
					newpath.set( 'd', simplepath.formatPath( a ) )
					self.plotPath( newpath, matNew )
					
			elif node.tag == inkex.addNS( 'line', 'svg' ) or node.tag == 'line':

				# Convert
				#
				#   <line x1="X1" y1="Y1" x2="X2" y2="Y2/>
				#
				# to
				#
				#   <path d="MX1,Y1 LX2,Y2"/>

				# if we're in resume mode AND self.pathcount < self.svgLastPath,
				#    then skip over this path.
				# if we're in resume mode and self.pathcount = self.svgLastPath,
				#    then start here, and set
				# self.nodeCount equal to self.svgLastPathNC

				doWePlotThisPath = False 
				if (self.resumeMode): 
					if (self.pathcount < self.svgLastPath_Old ): 
						#This path was *completely plotted* already; skip.
						self.pathcount += 1 
					elif (self.pathcount == self.svgLastPath_Old ): 
						#this path is the first *not completely* plotted path:
						self.nodeCount =  self.svgLastPathNC_Old	#Nodecount after last completed path
						doWePlotThisPath = True 
				else:
					doWePlotThisPath = True
				if (doWePlotThisPath):
					self.pathcount += 1
					# Create a path to contain the line
					newpath = inkex.etree.Element( inkex.addNS( 'path', 'svg' ) )
					x1 = float( node.get( 'x1' ) )
					y1 = float( node.get( 'y1' ) )
					x2 = float( node.get( 'x2' ) )
					y2 = float( node.get( 'y2' ) )
					s = node.get( 'style' )
					if s:
						newpath.set( 'style', s )
					t = node.get( 'transform' )
					if t:
						newpath.set( 'transform', t )
					a = []
					a.append( ['M ', [x1, y1]] )
					a.append( [' L ', [x2, y2]] )
					newpath.set( 'd', simplepath.formatPath( a ) )
					self.plotPath( newpath, matNew )
					

			elif node.tag == inkex.addNS( 'polyline', 'svg' ) or node.tag == 'polyline':

				# Convert
				#  <polyline points="x1,y1 x2,y2 x3,y3 [...]"/> 
				# to 
				#   <path d="Mx1,y1 Lx2,y2 Lx3,y3 [...]"/> 
				# Note: we ignore polylines with no points

				pl = node.get( 'points', '' ).strip()
				if pl == '':
					pass

				#if we're in resume mode AND self.pathcount < self.svgLastPath, then skip over this path.
				#if we're in resume mode and self.pathcount = self.svgLastPath, then start here, and set
				# self.nodeCount equal to self.svgLastPathNC
				
				doWePlotThisPath = False 
				if (self.resumeMode): 
					if (self.pathcount < self.svgLastPath_Old ): 
						#This path was *completely plotted* already; skip.
						self.pathcount += 1 
					elif (self.pathcount == self.svgLastPath_Old ): 
						#this path is the first *not completely* plotted path:
						self.nodeCount =  self.svgLastPathNC_Old	#Nodecount after last completed path
						doWePlotThisPath = True 
				else:
					doWePlotThisPath = True
				if (doWePlotThisPath):
					self.pathcount += 1
					
					pa = pl.split()
					if not len( pa ):
						pass
					# Issue 29: pre 2.5.? versions of Python do not have
					#    "statement-1 if expression-1 else statement-2"
					# which came out of PEP 308, Conditional Expressions
					#d = "".join( ["M " + pa[i] if i == 0 else " L " + pa[i] for i in range( 0, len( pa ) )] )
					d = "M " + pa[0]
					for i in range( 1, len( pa ) ):
						d += " L " + pa[i]
					newpath = inkex.etree.Element( inkex.addNS( 'path', 'svg' ) )
					newpath.set( 'd', d );
					s = node.get( 'style' )
					if s:
						newpath.set( 'style', s )
					t = node.get( 'transform' )
					if t:
						newpath.set( 'transform', t )
					self.plotPath( newpath, matNew )

			elif node.tag == inkex.addNS( 'polygon', 'svg' ) or node.tag == 'polygon':

				# Convert 
				#  <polygon points="x1,y1 x2,y2 x3,y3 [...]"/> 
				# to 
				#   <path d="Mx1,y1 Lx2,y2 Lx3,y3 [...] Z"/> 
				# Note: we ignore polygons with no points

				pl = node.get( 'points', '' ).strip()
				if pl == '':
					pass

				#if we're in resume mode AND self.pathcount < self.svgLastPath, then skip over this path.
				#if we're in resume mode and self.pathcount = self.svgLastPath, then start here, and set
				# self.nodeCount equal to self.svgLastPathNC

				doWePlotThisPath = False 
				if (self.resumeMode): 
					if (self.pathcount < self.svgLastPath_Old ): 
						#This path was *completely plotted* already; skip.
						self.pathcount += 1 
					elif (self.pathcount == self.svgLastPath_Old ): 
						#this path is the first *not completely* plotted path:
						self.nodeCount =  self.svgLastPathNC_Old	#Nodecount after last completed path
						doWePlotThisPath = True 
				else:
					doWePlotThisPath = True
				if (doWePlotThisPath):
					self.pathcount += 1
					
					pa = pl.split()
					if not len( pa ):
						pass
					# Issue 29: pre 2.5.? versions of Python do not have
					#    "statement-1 if expression-1 else statement-2"
					# which came out of PEP 308, Conditional Expressions
					#d = "".join( ["M " + pa[i] if i == 0 else " L " + pa[i] for i in range( 0, len( pa ) )] )
					d = "M " + pa[0]
					for i in range( 1, len( pa ) ):
						d += " L " + pa[i]
					d += " Z"
					newpath = inkex.etree.Element( inkex.addNS( 'path', 'svg' ) )
					newpath.set( 'd', d );
					s = node.get( 'style' )
					if s:
						newpath.set( 'style', s )
					t = node.get( 'transform' )
					if t:
						newpath.set( 'transform', t )
					self.plotPath( newpath, matNew )
					
			elif node.tag == inkex.addNS( 'ellipse', 'svg' ) or \
				node.tag == 'ellipse' or \
				node.tag == inkex.addNS( 'circle', 'svg' ) or \
				node.tag == 'circle':

					# Convert circles and ellipses to a path with two 180 degree arcs.
					# In general (an ellipse), we convert 
					#   <ellipse rx="RX" ry="RY" cx="X" cy="Y"/> 
					# to 
					#   <path d="MX1,CY A RX,RY 0 1 0 X2,CY A RX,RY 0 1 0 X1,CY"/> 
					# where 
					#   X1 = CX - RX
					#   X2 = CX + RX 
					# Note: ellipses or circles with a radius attribute of value 0 are ignored

					if node.tag == inkex.addNS( 'ellipse', 'svg' ) or node.tag == 'ellipse':
						rx = float( node.get( 'rx', '0' ) )
						ry = float( node.get( 'ry', '0' ) )
					else:
						rx = float( node.get( 'r', '0' ) )
						ry = rx
					if rx == 0 or ry == 0:
						pass

					
					#if we're in resume mode AND self.pathcount < self.svgLastPath, then skip over this path.
					#if we're in resume mode and self.pathcount = self.svgLastPath, then start here, and set
					# self.nodeCount equal to self.svgLastPathNC
					
					doWePlotThisPath = False 
					if (self.resumeMode): 
						if (self.pathcount < self.svgLastPath_Old ): 
							#This path was *completely plotted* already; skip.
							self.pathcount += 1 
						elif (self.pathcount == self.svgLastPath_Old ): 
							#this path is the first *not completely* plotted path:
							self.nodeCount =  self.svgLastPathNC_Old	#Nodecount after last completed path
							doWePlotThisPath = True 
					else:
						doWePlotThisPath = True
					if (doWePlotThisPath):
						self.pathcount += 1
					
						cx = float( node.get( 'cx', '0' ) )
						cy = float( node.get( 'cy', '0' ) )
						x1 = cx - rx
						x2 = cx + rx
						d = 'M %f,%f ' % ( x1, cy ) + \
							'A %f,%f ' % ( rx, ry ) + \
							'0 1 0 %f,%f ' % ( x2, cy ) + \
							'A %f,%f ' % ( rx, ry ) + \
							'0 1 0 %f,%f' % ( x1, cy )
						newpath = inkex.etree.Element( inkex.addNS( 'path', 'svg' ) )
						newpath.set( 'd', d );
						s = node.get( 'style' )
						if s:
							newpath.set( 'style', s )
						t = node.get( 'transform' )
						if t:
							newpath.set( 'transform', t )
						self.plotPath( newpath, matNew )
						
							
			elif node.tag == inkex.addNS( 'metadata', 'svg' ) or node.tag == 'metadata':
				pass
			elif node.tag == inkex.addNS( 'defs', 'svg' ) or node.tag == 'defs':
				pass
			elif node.tag == inkex.addNS( 'namedview', 'sodipodi' ) or node.tag == 'namedview':
				pass
			elif node.tag == inkex.addNS( 'WCB', 'svg' ) or node.tag == 'WCB':
				pass
			elif node.tag == inkex.addNS( 'eggbot', 'svg' ) or node.tag == 'eggbot':
				pass			
			elif node.tag == inkex.addNS( 'title', 'svg' ) or node.tag == 'title':
				pass
			elif node.tag == inkex.addNS( 'desc', 'svg' ) or node.tag == 'desc':
				pass
			elif node.tag == inkex.addNS( 'text', 'svg' ) or node.tag == 'text':
				if (not self.warnings.has_key( 'text' )) and (self.plotCurrentLayer):
					inkex.errormsg( gettext.gettext( 'Warning: Some elements omitted.\n' +
						'Please convert text to a path before drawing, using \n' +
						'Path > Object to Path. Or, use the Hershey Text extension, '+
						'which can be found under Extensions > Render.' ) )
					self.warnings['text'] = 1
				pass
			elif node.tag == inkex.addNS( 'image', 'svg' ) or node.tag == 'image':
				if (not self.warnings.has_key( 'image' )) and (self.plotCurrentLayer):
					inkex.errormsg( gettext.gettext( 'Warning: Some elements omitted.\n' +
						'Please convert images to line art before drawing. ' +
						' Consider using the Path > Trace bitmap tool. ' ) )
					self.warnings['image'] = 1
				pass
			elif node.tag == inkex.addNS( 'pattern', 'svg' ) or node.tag == 'pattern':
				pass
			elif node.tag == inkex.addNS( 'radialGradient', 'svg' ) or node.tag == 'radialGradient':
				# Similar to pattern
				pass
			elif node.tag == inkex.addNS( 'linearGradient', 'svg' ) or node.tag == 'linearGradient':
				# Similar in pattern
				pass
			elif node.tag == inkex.addNS( 'style', 'svg' ) or node.tag == 'style':
				# This is a reference to an external style sheet and not the value
				# of a style attribute to be inherited by child elements
				pass
			elif node.tag == inkex.addNS( 'cursor', 'svg' ) or node.tag == 'cursor':
				pass
			elif node.tag == inkex.addNS( 'color-profile', 'svg' ) or node.tag == 'color-profile':
				# Gamma curves, color temp, etc. are not relevant to single color output
				pass
			elif not isinstance( node.tag, basestring ):
				# This is likely an XML processing instruction such as an XML
				# comment.  lxml uses a function reference for such node tags
				# and as such the node tag is likely not a printable string.
				# Further, converting it to a printable string likely won't
				# be very useful.
				pass
			else:
				if (not self.warnings.has_key( str( node.tag ) )) and (self.plotCurrentLayer):
					t = str( node.tag ).split( '}' )
					inkex.errormsg( gettext.gettext( 'Warning: unable to draw <' + str( t[-1] ) +
						'> object, please convert it to a path first.' ) )
					self.warnings[str( node.tag )] = 1
				pass

	def DoWePlotLayer( self, strLayerName ):
		"""
			 
		First: scan first 4 chars of node id for first non-numeric character,
		and scan the part before that (if any) into a number
		Then, see if the number matches the layer.
		"""

		# Look at layer name.  Sample first character, then first two, and
		# so on, until the string ends or the string no longer consists of digit characters only.
		
		TempNumString = 'x'
		stringPos = 1	
		layerNameInt = -1
		layerMatch = False	
		self.plotCurrentLayer = True    #Temporarily assume that we are plotting the layer
		CurrentLayerName = string.lstrip( strLayerName ) #remove leading whitespace
		MaxLength = len( CurrentLayerName )
		if MaxLength > 0:
			while stringPos <= MaxLength:
				if str.isdigit( CurrentLayerName[:stringPos] ):
					TempNumString = CurrentLayerName[:stringPos] # Store longest numeric string so far
					stringPos = stringPos + 1
				else:
					break

		if ( str.isdigit( TempNumString ) ):
			layerNameInt = int( float( TempNumString ) )
			if ( self.svgLayer == layerNameInt ):
				layerMatch = True	#Match! The current layer IS named in the Layers tab.
			
		if ((self.PrintFromLayersTab) and (layerMatch == False)):
			self.plotCurrentLayer = False

		if (self.plotCurrentLayer == True):
			self.LayersFoundToPlot = True

	def plotPath( self, path, matTransform ):
		'''
		Plot the path while applying the transformation defined
		by the matrix [matTransform].
		'''
		# turn this path into a cubicsuperpath (list of beziers)...

		d = path.get( 'd' )
		if len( simplepath.parsePath( d ) ) == 0:
			return

		if self.plotCurrentLayer:
			p = cubicsuperpath.parsePath( d )

			# ...and apply the transformation to each point
			applyTransformToPath( matTransform, p )
	
			# p is now a list of lists of cubic beziers [control pt1, control pt2, endpoint]
			# where the start-point is the last point in the previous segment.
			for sp in p:
			
				plot_utils.subdivideCubicPath( sp, 0.02 / self.options.smoothness )
				nIndex = 0

				singlePath = []		
				if self.plotCurrentLayer:
					for csp in sp:
						if self.bStopped:
							return
						if (self.printPortrait):
							fX = float( csp[1][1] ) #Flipped X/Y
							fY = ( self.svgWidth) - float( csp[1][0] )
						else:
							fX = float( csp[1][0] ) # Set move destination
							fY = float( csp[1][1] )

						if nIndex == 0:
							if (plot_utils.distance(fX - self.fCurrX,fY - self.fCurrY) > axidraw_conf.MIN_GAP):
								self.penUp()
								self.plotSegmentWithVelocity( fX, fY, 0, 0)
						elif nIndex == 1:
							self.penDown() 
							# self.plotLineAndTime( fX, fY ) #Draw a segment - Legacy
						nIndex += 1

						singlePath.append([fX,fY])
	
					self.PlanTrajectory(singlePath)
	
			if ( not self.bStopped ):	#an "index" for resuming plots quickly-- record last complete path
				self.svgLastPath = self.pathcount #The number of the last path completed
				self.svgLastPathNC = self.nodeCount #the node count after the last path was completed.			


	def PlanTrajectory( self, inputPath ):
		'''
		Plan the trajectory for a full path, accounting for linear acceleration.
		Inputs: Ordered (x,y) pairs to cover.
		Output: A list of segments to plot, of the form (Xfinal, Yfinal, Vinitial, Vfinal)

		Note: Native motor axes are Motor 1, Motor 2.
			Motor1Steps = xSteps + ySteps
			Motor2Steps = xSteps - ysteps
			
		Important note: This routine uses *inch* units (inches, inches/second, etc.). 
		
		'''
		
# 		spewTrajectoryDebugData = True
		spewTrajectoryDebugData = False
		
		if spewTrajectoryDebugData:
			inkex.errormsg( '\nPlanTrajectory()\n')

		if self.bStopped:
			return
		if ( self.fCurrX is None ):
			return

		#check page size limits:
		if (self.ignoreLimits == False):
			for xy in inputPath:
				xy[0], xBounded = plot_utils.checkLimits( xy[0], self.xBoundsMin, self.xBoundsMax )
				xy[1], yBounded = plot_utils.checkLimits( xy[1], self.yBoundsMin, self.yBoundsMax )
				if (xBounded or yBounded):
					self.warnOutOfBounds = True
							
		#Handle simple segments (lines) that do not require any complex planning:
		if (len(inputPath) < 3):
			if spewTrajectoryDebugData:
				inkex.errormsg( 'SHORTPATH ESCAPE: ')
			self.plotSegmentWithVelocity( xy[0], xy[1], 0, 0)							  
			return
			
		#For other trajectories, we need to go deeper.
		TrajLength = len(inputPath)

		if spewTrajectoryDebugData:
			for xy in inputPath:
				inkex.errormsg( 'x: %1.2f,  y: %1.2f' %(xy[0],xy[1]))
			inkex.errormsg( '\nTrajLength: '+str(TrajLength) + '\n')

		#Absolute maximum and minimum speeds allowed: 

		#Values such as PenUpSpeed are in units of _steps per second_.  
		# However, to simplify our kinematic calculations, 
		# we now presently switch into inches per second. 

		# Maximum travel speed
		if ( self.virtualPenIsUp ):	
			speedLimit = self.PenUpSpeed  / self.stepsPerInch
		else:		
			speedLimit = self.PenDownSpeed  / self.stepsPerInch

		TrajDists = array('f')	 #float, Segment length (distance) when arriving at the junction
		TrajVels = array('f')	 #float, Velocity when arriving at the junction
		TrajVectors = []		#Array that will hold normalized unit vectors along each segment

		TrajDists.append(0.0)	#First value, at time t = 0
		TrajVels.append(0.0)	#First value, at time t = 0

		for i in xrange(1, TrajLength):
			#Distance per segment:
			tmpDist = plot_utils.distance( inputPath[i][0] - inputPath[i - 1][0] ,
			inputPath[i][1] - inputPath[i - 1][1] )
			TrajDists.append(tmpDist)
			#Normalized unit vectors:
			
			if (tmpDist == 0):
				tmpDist = 1
			tmpX = (inputPath[i][0] - inputPath[i - 1][0]) / tmpDist
			tmpY = (inputPath[i][1] - inputPath[i - 1][1]) / tmpDist
			TrajVectors.append([tmpX,tmpY])

		if spewTrajectoryDebugData:
			for dist in TrajDists:
				inkex.errormsg( 'TrajDists: %1.3f' % dist )
			inkex.errormsg( '\n')

		#time to reach full speed (from zero), at maximum acceleration. Defined in settings:

		if ( self.virtualPenIsUp ):	
			tMax = axidraw_conf.ACCEL_TIME_PU			
		else:		
			tMax = axidraw_conf.ACCEL_TIME			

		# acceleration/deceleration rate: (Maximum speed) / (time to reach that speed)
		accelRate = speedLimit / tMax
		
		#Distance that is required to reach full speed, from zero speed:  (1/2) a t^2
		accelDist = 0.5 * accelRate * tMax  * tMax

		if spewTrajectoryDebugData:		
			inkex.errormsg( 'speedLimit: %1.3f' % speedLimit )
			inkex.errormsg( 'tMax: %1.3f' % tMax )
			inkex.errormsg( 'accelRate: %1.3f' % accelRate )
			inkex.errormsg( 'accelDist: %1.3f' % accelDist )
			CosinePrintArray = array('f')
			
			
		'''
		Now, step through every vertex in the trajectory, and calculate what the speed
		should be when arriving at that vertex.
		
		In order to do so, we need to understand how the trajectory will evolve in terms 
		of position and velocity for a certain amount of time in the future, past that vertex. 
		The most extreme cases of this is when we are traveling at 
		full speed initially, and must come to a complete stop.
			(This is actually more sudden than if we must reverse course-- that must also
			go through zero velocity at the same rate of deceleration, and a full reversal
			that does not occur at the path end might be able to have a 
			nonzero velocity at the endpoint.)
			
		Thus, we look ahead from each vertex until one of the following occurs:
			(1) We have looked ahead by at least tMax, or
			(2) We reach the end of the path.

		The data that we have to start out with is this:
			- The position and velocity at the previous vertex
			- The position at the current vertex
			- The position at subsequent vertices
			- The velocity at the final vertex (zero)

		To determine the correct velocity at each vertex, we will apply the following rules:
		
		(A) For the first point, V(i = 0) = 0.

		(B) For the last point point, Vi = 0 as well.
		
		(C) If the length of the segment is greater than the distance 
		required to reach full speed, then the vertex velocity may be as 
		high as the maximum speed.
		
		(D) However, if the length of the segment is less than the total distance
		required to get to full speed, then the velocity at that vertex
		is limited by to the value that can be reached from the initial
		starting velocity, in the distance given.
				
		(E) The maximum velocity through the junction is also limited by the
		turn itself-- if continuing straight, then we do not need to slow down
		as much as if we were fully reversing course. 
		We will model each corner as a short curve that we can accelerate around.
		
		(F) To calculate the velocity through each turn, we must _look ahead_ to
		the subsequent (i+1) vertex, and determine what velocity 
		is appropriate when we arrive at the next point. 
		
		Because future points may be close together-- the subsequent vertex could
		occur just before the path end -- we actually must look ahead past the 
		subsequent (i + 1) vertex, all the way up to the limits that we have described 
		(e.g., tMax) to understand the subsequent behavior. Once we have that effective
		endpoint, we can work backwards, ensuring that we will be able to get to the
		final speed/position that we require. 
		
		A less complete (but far simpler) procedure is to first complete the trajectory
		description, and then -- only once the trajectory is complete -- go back through,
		but backwards, and ensure that we can actually decelerate to each velocity.

		(G) The minimum velocity through a junction may be set to a constant.
		There is often some (very slow) speed -- perhaps a few percent of the maximum speed
		at which there are little or no resonances. Even when the path must directly reverse
		itself, we can usually travel at a non-zero speed. This, of course, presumes that we 
		still have a solution for getting to the endpoint at zero speed.
		'''

		delta = self.options.cornering / 1000  #Corner rounding/tolerance factor-- not sure how high this should be set.
		
		for i in xrange(1, TrajLength - 1):
			Dcurrent = TrajDists[i]		# Length of the segment leading up to this vertex
			VPrevExit = TrajVels[i-1]	# Velocity when leaving previous vertex

			'''
			Velocity at vertex: Part I
			
			Check to see what our plausible maximum speeds are, from 
			acceleration only, without concern about cornering, nor deceleration.
			'''

			if (Dcurrent > accelDist):		
				#There _is_ enough distance in the segment for us to either
				# accelerate to maximum speed or come to a full stop before this vertex.
				VcurrentMax = speedLimit
				if spewTrajectoryDebugData:
					inkex.errormsg( 'Speed Limit on vel : '+str(i))
			else:
				#There is _not necessarily_ enough distance in the segment for us to either
				# accelerate to maximum speed or come to a full stop before this vertex.
				# Calculate how much we *can* swing the velocity by:	
				
				VcurrentMax = plot_utils.vFinal_Vi_A_Dx(VPrevExit,accelRate, Dcurrent)
				if (VcurrentMax > speedLimit):
					VcurrentMax = speedLimit
					
				if spewTrajectoryDebugData:
					inkex.errormsg( 'TrajVels I: %1.3f' % VcurrentMax )
	
			'''
			Velocity at vertex: Part II 
			
			Assuming that we have the same velocity when we enter and
			leave a corner, our acceleration limit provides a velocity
			that depends upon the angle between input and output directions.
			
			The cornering algorithm models the corner as a slightly smoothed corner,
			to estimate the angular acceleration that we encounter:
			https://onehossshay.wordpress.com/2011/09/24/improving_grbl_cornering_algorithm/
			
			The dot product of the unit vectors is equal to the cosine of the angle between the
			two unit vectors, giving the deflection between the incoming and outgoing angles. 
			Note that this angle is (pi - theta), in the convention of that article, giving us
			a sign inversion. [cos(pi - theta) = - cos(theta)]
			'''
			
			cosineFactor = - plot_utils.dotProductXY(TrajVectors[i - 1],TrajVectors[i]) 

			if spewTrajectoryDebugData:
				CosinePrintArray.append(cosineFactor) 

			rootFactor = sqrt((1 - cosineFactor)/2)
			denominator =  1 - rootFactor
			if (denominator > 0.0001):
				Rfactor = (delta * rootFactor) / denominator
			else:	
				Rfactor = 100000
			VjunctionMax = sqrt(accelRate * Rfactor)
			
			if (VcurrentMax > VjunctionMax):
				VcurrentMax = VjunctionMax
				
			TrajVels.append( VcurrentMax)	# "Forward-going" speed limit for velocity at this particular vertex.
		TrajVels.append( 0.0 	)				# Add zero velocity, for final vertex.

		if spewTrajectoryDebugData:
			inkex.errormsg( ' ')
			for dist in CosinePrintArray:
				inkex.errormsg( 'Cosine Factor: %1.3f' % dist )
			inkex.errormsg( ' ')
			
			for dist in TrajVels:
				inkex.errormsg( 'TrajVels II: %1.3f' % dist )
			inkex.errormsg( ' ')	

		'''			
		Velocity at vertex: Part III

		We have, thus far, ensured that we could reach the desired velocities, going forward, but
		have also assumed an effectively infinite deceleration rate.		

		We now go through the completed array in reverse, limiting velocities to ensure that we 
		can properly decelerate in the given distances.		
		'''
		
		for j in xrange(1, TrajLength):
			i = TrajLength - j	# Range: From (TrajLength - 1) down to 1.

			Vfinal = TrajVels[i]
			Vinitial = TrajVels[i - 1]
			SegLength = TrajDists[i]



			if (Vinitial > Vfinal) and (SegLength > 0): 	
				VInitMax = plot_utils.vInitial_VF_A_Dx(Vfinal,-accelRate,SegLength)

				if spewTrajectoryDebugData:
					inkex.errormsg( 'VInit Calc: (Vfinal = %1.3f, accelRate = %1.3f, SegLength = %1.3f) ' 
					% (Vfinal, accelRate, SegLength))

				if (VInitMax < Vinitial):
					Vinitial = VInitMax 
				TrajVels[i - 1] = Vinitial
				
		if spewTrajectoryDebugData:
			for dist in TrajVels:
				inkex.errormsg( 'TrajVels III: %1.3f' % dist )

			inkex.errormsg( ' ')

		for i in xrange(1, TrajLength):			
			self.plotSegmentWithVelocity( inputPath[i][0] , inputPath[i][1] ,TrajVels[i-1] , TrajVels[i])

	def plotSegmentWithVelocity( self, xDest, yDest, Vi, Vf  ):
		''' 
		Control the serial port to command the machine to draw
		a straight line segment, with basic acceleration support. 
		
		Inputs: 	Destination (x,y)
					Initial velocity
					Final velocity
		
		Method: Divide the segment up into smaller segments, each
		of which has constant velocity. 
		Send commands out the com port as a set of short line segments
		(dx, dy) with specified durations (in ms) of how long each segment
		takes to draw.the segments take to draw. 
		Uses linear ("trapezoid") acceleration and deceleration strategy.
		
		Inputs are expected be in units of inches (for distance) 
			or inches per second (for velocity).
		
		'''	

 		spewSegmentDebugData = False
# 		spewSegmentDebugData = True

		if spewSegmentDebugData:
			inkex.errormsg( '\nPlotSegment (x = %1.2f, y = %1.2f, Vi = %1.2f, Vf = %1.2f ) ' 
			% (xDest, yDest, Vi, Vf))

		ConstantVelMode = False
		if (self.options.constSpeed and not self.virtualPenIsUp):
			ConstantVelMode = True

		if self.bStopped:
			return
		if ( self.fCurrX is None ):
			return
		
		# Distances to move, in motor-step units
		xMovementIdeal = self.stepsPerInch * ( xDest - self.fCurrX )	
		yMovementIdeal = self.stepsPerInch * ( yDest - self.fCurrY )

		# Velocity inputs, in motor-step units
		initialVel =  Vi * self.stepsPerInch		#Translate from "inches per second"
		finalVel = Vf * self.stepsPerInch		#Translate from "inches per second"


		# Look at distance to move along 45-degree axes, for native motor steps:
		motorSteps1 = int (round(xMovementIdeal + yMovementIdeal)) # Number of native motor steps required, Axis 1
		motorSteps2 = int (round(xMovementIdeal - yMovementIdeal)) # Number of native motor steps required, Axis 2

		plotDistance = plot_utils.distance( motorSteps1, motorSteps2 )
		if (plotDistance < 1.0): #if total movement is less than one step, skip this movement.
			return

			
		# Maximum travel speeds:
		# & acceleration/deceleration rate: (Maximum speed) / (time to reach that speed)

		if ( self.virtualPenIsUp ):	
			speedLimit = self.PenUpSpeed
			accelRate = speedLimit / axidraw_conf.ACCEL_TIME_PU	
			
			if plotDistance < (self.stepsPerInch * axidraw_conf.SHORT_THRESHOLD):
				accelRate = speedLimit / axidraw_conf.ACCEL_TIME	
				speedLimit = self.PenDownSpeed
		else:		
			speedLimit = self.PenDownSpeed
			accelRate = speedLimit / axidraw_conf.ACCEL_TIME	
			
		if (initialVel > speedLimit):
			initialVel = speedLimit
		if (finalVel > speedLimit):
			finalVel = speedLimit

		#Times to reach maximum speed, from our initial velocity 
		# vMax = vi + a*t  =>  t = (vMax - vi)/a
		# vf = vMax - a*t   =>  t = -(vf - vMax)/a = (vMax - vf)/a
		# -- These are _maximum_ values. We often do not have enough time/space to reach full speed.

		tAccelMax = (speedLimit - initialVel) / accelRate
		tDecelMax = (speedLimit - finalVel) / accelRate	

		if spewSegmentDebugData:
			inkex.errormsg( 'accelRate: ' + str(accelRate) )
			inkex.errormsg( 'speedLimit: ' + str(speedLimit) )
			inkex.errormsg( 'initialVel: ' + str(initialVel) )
			inkex.errormsg( 'finalVel: ' + str(finalVel) )
			inkex.errormsg( 'tAccelMax: ' + str(tAccelMax) )
			inkex.errormsg( 'tDecelMax: ' + str(tDecelMax) )

	
		#Distance that is required to reach full speed, from our start at speed initialVel:
		# distance = vi * t + (1/2) a t^2
		accelDistMax = ( initialVel * tAccelMax ) + ( 0.5 * accelRate * tAccelMax * tAccelMax )
		# Use the same model for deceleration distance; modeling it with backwards motion:
		decelDistMax = ( finalVel * tDecelMax ) + ( 0.5 * accelRate * tDecelMax * tDecelMax )

		timeSlice = axidraw_conf.TIME_SLICE	#(seconds): Slice travel into slices of time that are at least 0.050 seconds (50 ms) long

		self.nodeCount += 1		# This whole segment move counts as ONE pause/resume node in our plot
		if self.resumeMode:
			if ( self.nodeCount >= self.nodeTarget ):
				self.resumeMode = False
				if ( not self.virtualPenIsUp ):
					self.penDown()	

		# Declare arrays:
		# These are _normally_ 4-byte integers, but could (theoretically) be 2-byte integers on some systems.
		#   if so, this could cause errors in rare cases (very large/long moves, etc.). 
		# Set up an alert system, just in case!

		durationArray = array('I') # unsigned integer for duration -- up to 65 seconds for a move if only 2 bytes.
		distArray = array('f')	#float
		destArray1 = array('i')	#signed integer
		destArray2 = array('i')	#signed integer

		timeElapsed = 0.0		
		position = 0.0
		velocity = initialVel
		
		'''
		
		Next, we wish to estimate total time duration of this segment. 
		In doing so, we must consider the possible cases:

		Case 1: 'Trapezoid'
			Segment length is long enough to reach full speed.
			Segment length > accelDistMax + decelDistMax
			We will get to full speed, with an opportunity to "coast" at full speed
			in the middle.
			
		Case 2: 'Linear velocity ramp'
			For small enough moves -- say less than 10 intervals (typ 500 ms),
			we do not have significant time to ramp the speed up and down.
			Instead, perform only a simple speed ramp between initial and final.
			
		Case 3: 'Triangle'
			Segment length is not long enough to reach full speed.
			Accelerate from initial velocity to a local maximum speed,
			then decelerate from that point to the final velocity.

		Case 4: 'Constant velocity'
			Use a single, constant velocity for all pen-down movements.
			Also a fallback position, when moves are too short for linear ramps.
			
		In each case, we ultimately construct the trajectory in segments at constant velocity.
		In cases 1-3, that set of segments approximates a linear slope in velocity. 
		
		Because we may end up with slight over/undershoot in position along the paths
		with this approach, we perform a final scaling operation (to the correct distance) at the end.
		
		'''
		
		
		if (ConstantVelMode == False) or ( self.virtualPenIsUp ):	#Allow accel when pen is up.		
			if (plotDistance > (accelDistMax + decelDistMax + timeSlice * speedLimit)):
				''' 
				#Case 1: 'Trapezoid'
				'''
			
				if spewSegmentDebugData:
					inkex.errormsg( 'Type 1: Trapezoid'+ '\n')	
				speedMax = speedLimit	# We will reach _full cruising speed_!
			
				intervals = int(math.floor(tAccelMax / timeSlice))	# Number of intervals during acceleration
				
				#If intervals == 0, then we are already at (or nearly at) full speed.
				if (intervals > 0):			
					timePerInterval = tAccelMax / intervals			
	
					velocityStepSize = (speedMax - initialVel)/(intervals + 1.0)	
					# For six time intervals of acceleration, first interval is at velocity (max/7)
					# 6th (last) time interval is at 6*max/7
					# after this interval, we are at full speed.
					
					for index in range(0, intervals):		#Calculate acceleration phase
						velocity += velocityStepSize
						timeElapsed += timePerInterval
						position += velocity * timePerInterval
						durationArray.append(int(round(timeElapsed * 1000.0)))
						distArray.append(position)		#Estimated distance along direction of travel
					if spewSegmentDebugData:
						inkex.errormsg( 'Accel intervals: '+str(intervals))
							
				#Add a center "coasting" speed interval IF there is time for it.
				coastingDistance = plotDistance - (accelDistMax + decelDistMax)	
								
				if (coastingDistance > (timeSlice * speedMax)):
					# There is enough time for (at least) one interval at full cruising speed.
					velocity = speedMax
					cruisingTime = coastingDistance / velocity
					timeElapsed += cruisingTime
					durationArray.append(int(round(timeElapsed * 1000.0)))
					position += velocity * cruisingTime
					distArray.append(position)		#Estimated distance along direction of travel				
					if spewSegmentDebugData:
						inkex.errormsg( 'Coast Distance: '+str(coastingDistance))


	
				intervals = int(math.floor(tDecelMax / timeSlice))	# Number of intervals during deceleration
				
				if (intervals > 0):	
					timePerInterval = tDecelMax / intervals			
					velocityStepSize = (speedMax - finalVel)/(intervals + 1.0)	
	
					for index in range(0, intervals):		#Calculate deceleration phase
						velocity -= velocityStepSize
						timeElapsed += timePerInterval
						position += velocity * timePerInterval
						durationArray.append(int(round(timeElapsed * 1000.0)))
						distArray.append(position)		#Estimated distance along direction of travel
					if spewSegmentDebugData:
						inkex.errormsg( 'Decel intervals: '+str(intervals))

			else:
				''' 
				#Case 3: 'Triangle' 
				
				We will _not_ reach full cruising speed, but let's go as fast as we can!
				
				We begin with given: initial velocity, final velocity,
					maximum acceleration rate, distance to travel.
				
				The optimal solution is to accelerate at the maximum rate, to some maximum velocity Vmax,
				and then to decelerate at same maximum rate, to the final velocity. 
				This forms a triangle on the plot of V(t). 
				
				The value of Vmax -- and the time at which we reach it -- may be varied in order to
				accommodate our choice of distance-traveled and velocity requirements.
				(This does assume that the segment requested is self consistent, and planned 
				with respect to our acceleration requirements.)
				
				In a more detail, with short notation Vi = initialVel, Vf = finalVel, 
					Amax = accelRate, Dv = (Vf - Vi)
				
				(i) We accelerate from Vi, at Amax to some maximum velocity Vmax.
				This takes place during an interval of time Ta. 
				
				(ii) We then decelerate from Vmax, to Vf, at the same maximum rate, Amax.
				This takes place during an interval of time Td. 					
				
				(iii) The total time elapsed is Ta + Td
				
				(iv) v = v0 + a * t
					=>	Vmax = Vi + Amax * Ta
					and	Vmax = Vf + Amax * Td    (i.e., Vmax - Amax * Td = Vf)
				
					Thus Td = Ta - (Vf - Vi) / Amax, or    Td = Ta - (Dv / Amax)
					
				(v) The distance covered during the acceleration interval Ta is given by:
					Xa = Vi * Ta + (1/2) Amax * Ta^2
					
					The distance covered during the deceleration interval Td is given by:
					Xd = Vf * Td + (1/2) Amax * Td^2
					
					Thus, the total distance covered during interval Ta + Td is given by:
					plotDistance = Xa + Xd = Vi * Ta + (1/2) Amax * Ta^2 + Vf * Td + (1/2) Amax * Td^2

				(vi) Now substituting in Td = Ta - (Dv / Amax), we find:
					Amax * Ta^2 + 2 * Vi * Ta + ( Vi^2 - Vf^2 )/( 2 * Amax ) - plotDistance = 0
					
					Solving this quadratic equation for Ta, we find:
					Ta = ( sqrt(2 * Vi^2 + 2 * Vf^2 + 4 * Amax * plotDistance) - 2 * Vi ) / ( 2 * Amax )
					
					[We pick the positive root in the quadratic formula, since Ta must be positive.]
				
				(vii) From Ta and part (iv) above, we can find Vmax and Td.
				 
				'''
				
				if spewSegmentDebugData:	
					inkex.errormsg( '\nType 3: Triangle' )	
				Ta = ( sqrt(2 * initialVel * initialVel + 2 * finalVel * finalVel + 4 * accelRate * plotDistance) 
					- 2 * initialVel ) / ( 2 * accelRate )
					
				if (Ta < 0) :
					Ta = 0
					if spewSegmentDebugData:	
						inkex.errormsg( 'Warning: Negative transit time computed.') #Should not happen. :)

				Vmax = initialVel + accelRate * Ta
				if spewSegmentDebugData:	
					inkex.errormsg( 'Vmax: '+str(Vmax))

				intervals = int(math.floor(Ta / timeSlice))	# Number of intervals during acceleration

				if (intervals == 0):
					Ta = 0
				Td = Ta - (finalVel - initialVel) / accelRate
				Dintervals = int(math.floor(Td / timeSlice))	# Number of intervals during acceleration

				if ((intervals + Dintervals) > 4):
					if (intervals > 0):
						if spewSegmentDebugData:	
							inkex.errormsg( 'Triangle intervals UP: '+str(intervals))
	
						timePerInterval = Ta / intervals			
						velocityStepSize = (Vmax - initialVel)/(intervals + 1.0)	
						# For six time intervals of acceleration, first interval is at velocity (max/7)
						# 6th (last) time interval is at 6*max/7
						# after this interval, we are at full speed.
						
						for index in range(0, intervals):		#Calculate acceleration phase
							velocity += velocityStepSize
							timeElapsed += timePerInterval
							position += velocity * timePerInterval
							durationArray.append(int(round(timeElapsed * 1000.0)))
							distArray.append(position)		#Estimated distance along direction of travel				
					else:
						if spewSegmentDebugData:	
							inkex.errormsg( 'Note: Skipping accel phase in triangle.')
							
	
					if (Dintervals > 0):
						if spewSegmentDebugData:	
							inkex.errormsg( 'Triangle intervals Down: '+str(intervals))
		
						timePerInterval = Td / Dintervals			
						velocityStepSize = (Vmax - finalVel)/(Dintervals + 1.0)	
						# For six time intervals of acceleration, first interval is at velocity (max/7)
						# 6th (last) time interval is at 6*max/7
						# after this interval, we are at full speed.
						
						for index in range(0, Dintervals):		#Calculate acceleration phase
							velocity -= velocityStepSize
							timeElapsed += timePerInterval
							position += velocity * timePerInterval
							durationArray.append(int(round(timeElapsed * 1000.0)))
							distArray.append(position)		#Estimated distance along direction of travel				
					else:
						if spewSegmentDebugData:
							inkex.errormsg( 'Note: Skipping decel phase in triangle.')
				else:	
					''' 
					#Case 2: 'Linear or constant velocity changes' 
					
					Picked for segments that are shorter than 6 time slices. 
					Linear velocity interpolation between two endpoints.
					
					Because these are typically short segments (not enough time for a good "triangle"--
					we slightly boost the starting speed, by taking its average with Vmax for the segment.
					
					For very short segments (less than 2 time slices), use a single 
						segment with constant velocity.
					'''
					
					if spewSegmentDebugData:								
						inkex.errormsg( 'Type 2: Linear'+ '\n')	
					# xFinal = vi * t  + (1/2) a * t^2, and vFinal = vi + a * t 
					# Combining these (with same t) gives: 2 a x = (vf^2 - vi^2)  => a = (vf^2 - vi^2)/2x
					# So long as this 'a' is less than accelRate, we can linearly interpolate in velocity.

					initialVel = ( Vmax + initialVel) / 2  	#Boost initial speed for this segment
					velocity = initialVel					#Boost initial speed for this segment

					localAccel = (finalVel * finalVel - initialVel * initialVel)/ (2.0 * plotDistance)
					
					if (localAccel > accelRate):
						localAccel = accelRate
					elif (localAccel < -accelRate):
						localAccel = -accelRate
					if (localAccel == 0):
						#Initial velocity = final velocity -> Skip to constant velocity routine.
						ConstantVelMode = True
					else:	
						tSegment = (finalVel - initialVel) / localAccel		
							
					intervals = int(math.floor(tSegment / timeSlice))	# Number of intervals during deceleration
					if (intervals > 1):
						timePerInterval = tSegment / intervals			
						velocityStepSize = (finalVel - initialVel)/(intervals + 1.0)										
						# For six time intervals of acceleration, first interval is at velocity (max/7)
						# 6th (last) time interval is at 6*max/7
						# after this interval, we are at full speed.
						
						for index in range(0, intervals):		#Calculate acceleration phase
							velocity += velocityStepSize
							timeElapsed += timePerInterval
							position += velocity * timePerInterval
							durationArray.append(int(round(timeElapsed * 1000.0)))
							distArray.append(position)		#Estimated distance along direction of travel				
					else:
						#Short segment; Not enough time for multiple segments at different velocities. 
						initialVel = Vmax #These are _slow_ segments-- use fastest possible interpretation.
						ConstantVelMode = True

		if (ConstantVelMode):
			'''
			#Case 4: 'Constant Velocity mode'
			'''
			if spewSegmentDebugData:	
				inkex.errormsg( '-> [Constant Velocity Mode Segment]'+ '\n')	
			#Single segment with constant velocity.
			
			if (self.options.constSpeed and not self.virtualPenIsUp):
				velocity = self.PenDownSpeed 	#Constant pen-down speed		
			elif (finalVel > initialVel):
				velocity = finalVel
			elif (initialVel > finalVel):
				velocity = initialVel	
			elif (initialVel > 0):	#Allow case of two are equal, but nonzero	
				velocity = initialVel	
			else: #Both endpoints are equal to zero.	
				velocity = self.PenDownSpeed /10

			if spewSegmentDebugData:	
				inkex.errormsg( 'velocity: '+str(velocity))
					
			timeElapsed = plotDistance / velocity
			durationArray.append(int(round(timeElapsed * 1000.0)))
			distArray.append(plotDistance)		#Estimated distance along direction of travel
			position += plotDistance
			
		''' 
		The time & distance motion arrays for this path segment are now computed.
		Next: We scale to the correct intended travel distance, 
		round into integer motor steps and manage the process
		of sending the output commands to the motors.
		
		'''
		
		if spewSegmentDebugData:	
			inkex.errormsg( 'position/plotDistance: '+str(position/plotDistance))

		for index in range (0, len(distArray) ):
			#Scale our trajectory to the "actual" travel distance that we need:
			fractionalDistance = distArray[index] / position # Fractional position along the intended path
			destArray1.append ( int(round( fractionalDistance * motorSteps1)))
			destArray2.append ( int(round( fractionalDistance * motorSteps2)))

		prevMotor1 = 0
		prevMotor2 = 0
		prevTime = 0
		
		for index in range (0, len(destArray1) ):
			moveSteps1 = destArray1[index] - prevMotor1
			moveSteps2 = destArray2[index] - prevMotor2
			moveTime = durationArray[index] - prevTime
			prevTime = durationArray[index]

			if ( moveTime < 1 ):
				moveTime = 1		# don't allow zero-time moves.
	
			if (abs((float(moveSteps1) / float(moveTime))) < 0.002):	
				moveSteps1 = 0		#don't allow too-slow movements of this axis
			if (abs((float(moveSteps2) / float(moveTime))) < 0.002):	
				moveSteps2 = 0		#don't allow too-slow movements of this axis
	
			prevMotor1 += moveSteps1
			prevMotor2 += moveSteps2

			xSteps = (moveSteps1 + moveSteps2)/2.0	# Result will be a float.
			ySteps = (moveSteps1 - moveSteps2)/2.0	

			if ((moveSteps1 != 0) or (moveSteps2 != 0)): # if at least one motor step is required for this move....
	
				if (not self.resumeMode) and (not self.bStopped):
					if ( self.options.revMotor1 ):
						moveSteps1Copy = -moveSteps1
					else:
						moveSteps1Copy = moveSteps1
					if ( self.options.revMotor2):
						moveSteps2Copy = -moveSteps2
					else:
						moveSteps2Copy = moveSteps2 
					
					ebb_motion.doXYMove( self.serialPort, moveSteps2Copy, moveSteps1Copy, moveTime )			
					if (moveTime > 15):
						if self.options.tab != '"manual"':
							time.sleep(float(moveTime - 10)/1000.0)  #pause before issuing next command
					else:
						if spewSegmentDebugData:	
							inkex.errormsg( 'ShortMoves: ' + str( moveTime ) + '.' )

					self.fCurrX += xSteps / self.stepsPerInch   # Update current position
					self.fCurrY += ySteps / self.stepsPerInch		
	
					self.svgLastKnownPosX = self.fCurrX - axidraw_conf.StartPos_X
					self.svgLastKnownPosY = self.fCurrY - axidraw_conf.StartPos_Y	
					if spewSegmentDebugData:			
						inkex.errormsg( '\nfCurrX,fCurrY (x = %1.2f, y = %1.2f) ' % (self.fCurrX, self.fCurrY))
						
		strButton = ebb_motion.QueryPRGButton(self.serialPort)	#Query if button pressed
		if strButton[0] == '1': #button pressed
			self.svgNodeCount = self.nodeCount;
			self.svgPausedPosX = self.fCurrX - axidraw_conf.StartPos_X	#self.svgLastKnownPosX
			self.svgPausedPosY = self.fCurrY - axidraw_conf.StartPos_Y	#self.svgLastKnownPosY
			self.penUp()
			inkex.errormsg( 'Plot paused by button press after node number ' + str( self.nodeCount ) + '.' )
			inkex.errormsg( 'Use the "resume" feature to continue.' )
			self.bStopped = True
			return
		
		
	def plotLineAndTime( self, xDest, yDest ):
		'''
		Send commands out the com port as a line segment (dx, dy) and a time (ms) the segment
		should take to draw. Draws a single line segment with constant velocity.
		Important note: Everything up to this point uses *inch* scale. 
		Here, we convert to actual motor steps, w/ set DPI.
		'''

		inkex.errormsg( 'PlotLine: x, y: '+str(xDest)+', '+str(yDest))


		if (self.ignoreLimits == False):
			xDest, xBounded = plot_utils.checkLimits( xDest, self.xBoundsMin, self.xBoundsMax )
			yDest, yBounded = plot_utils.checkLimits( yDest, self.yBoundsMin, self.yBoundsMax )
			if (xBounded or yBounded):
				self.warnOutOfBounds = True

		if self.bStopped:
			return
		if ( self.fCurrX is None ):
			return

		# Distances to move:
		xMovementIdeal = self.stepsPerInch * ( xDest - self.fCurrX )	
		yMovementIdeal = self.stepsPerInch * ( yDest - self.fCurrY )

		# Look at distance to move along 45-degree axes, for native motor steps:
		motorSteps1 = int (round(xMovementIdeal + yMovementIdeal)) # Number of native motor steps required, Axis 1
		motorSteps2 = int (round(xMovementIdeal - yMovementIdeal)) # Number of native motor steps required, Axis 2

		plotDistance = plot_utils.distance( motorSteps1, motorSteps2 )

		if (plotDistance < 1.0): #if not moving at least one motor step...
			return

		#Set the speed at which we will plot this segment

		self.fSpeed = self.PenDownSpeed

		if self.resumeMode:		#Handle a "corner case" -- just in case.
			if ( self.nodeCount >= self.nodeTarget ):
				if ( not self.virtualPenIsUp ):
					self.fSpeed = self.PenDownSpeed

		nTime = int( math.ceil(1000.0 * plotDistance / self.fSpeed))	 #in milliseconds
		if ( nTime < 1 ):
			nTime = 1		# don't allow zero-time moves.

		if (abs((float(motorSteps1) / float(nTime))) < 0.002):	
			motorSteps1 = 0	#don't allow too-slow movements of this axis
		if (abs((float(motorSteps2) / float(nTime))) < 0.002):	
			motorSteps2 = 0	#don't allow too-slow movements of this axis

		xSteps = (motorSteps1 + motorSteps2)/2.0	# will force result to be a float.
		ySteps = (motorSteps1 - motorSteps2)/2.0	# will force result to be a float.

		if ((motorSteps1 != 0) or (motorSteps2 != 0)): # if at least one motor step is required for this move....
			self.nodeCount += 1

			if self.resumeMode:
				if ( self.nodeCount >= self.nodeTarget ):
					self.resumeMode = False
					if ( not self.virtualPenIsUp ):
						self.penDown()

			if (not self.resumeMode) and (not self.bStopped):
				if ( self.options.revMotor1 ):
					motorSteps1Copy = -motorSteps1
				else:
					motorSteps1Copy = motorSteps1
				if ( self.options.revMotor2):
					motorSteps2Copy = -motorSteps2
				else:
					motorSteps2Copy = motorSteps2 
				
				ebb_motion.doXYMove( self.serialPort, motorSteps2Copy, motorSteps1Copy, nTime )			
				if (nTime > 60):
					if self.options.tab != '"manual"':
						time.sleep(float(nTime - 50)/1000.0)  #pause before issuing next command
						
				self.fCurrX += xSteps / self.stepsPerInch   # Update current position
				self.fCurrY += ySteps / self.stepsPerInch		

				self.svgLastKnownPosX = self.fCurrX - axidraw_conf.StartPos_X
				self.svgLastKnownPosY = self.fCurrY - axidraw_conf.StartPos_Y	

			strButton = ebb_motion.QueryPRGButton(self.serialPort)	#Query if button pressed
			if strButton[0] == '1': #button pressed
				self.svgNodeCount = self.nodeCount;
				self.svgPausedPosX = self.fCurrX - axidraw_conf.StartPos_X	#self.svgLastKnownPosX
				self.svgPausedPosY = self.fCurrY - axidraw_conf.StartPos_Y	#self.svgLastKnownPosY
				self.penUp()
				inkex.errormsg( 'Plot paused by button press after node number ' + str( self.nodeCount ) + '.' )
				inkex.errormsg( 'Use the "resume" feature to continue.' )
				self.bStopped = True
				return

	def EnableMotors( self ):
		''' 
		Enable motors, set native motor resolution, and set speed scales.
		
		The "pen down" speed scale is adjusted with the following factors 
		that make the controls more intuitive: 
		* Reduce speed by factor of 2 when using 8X microstepping
		* Reduce speed by factor of 2 when disabling acceleration
		
		These factors prevent unexpected dramatic changes in speed when turning
		those two options on and off. 
		
		'''
		if ( self.options.resolution == 1 ):
			ebb_motion.sendEnableMotors(self.serialPort, 1) # 16X microstepping
			self.stepsPerInch = float( axidraw_conf.DPI_16X)						
			self.PenDownSpeed = self.options.penDownSpeed * axidraw_conf.Speed_Scale / 100.0
			self.PenUpSpeed = self.options.rapidSpeed * axidraw_conf.Speed_Scale / 100.0
		elif ( self.options.resolution == 2 ):
			ebb_motion.sendEnableMotors(self.serialPort, 2) # 8X microstepping
			self.stepsPerInch = float( axidraw_conf.DPI_16X / 2.0 )  
			self.PenDownSpeed = self.options.penDownSpeed * axidraw_conf.Speed_Scale / 200.0
			self.PenUpSpeed = self.options.rapidSpeed * axidraw_conf.Speed_Scale / 100.0
		if (self.options.constSpeed):
			self.PenDownSpeed = self.PenDownSpeed / 2
		
		TestArray = array('i')	#signed integer
		if (TestArray.itemsize < 4):
			inkex.errormsg( 'Internal array data length error. Please contact technical support.' )
	
	def penUp( self ):
		self.virtualPenIsUp = True  # Virtual pen keeps track of state for resuming plotting.
		if ( not self.resumeMode) and (not self.bPenIsUp):	# skip if pen is already up, or if we're resuming.
			ebb_motion.sendPenUp(self.serialPort, self.options.penUpDelay )				
			self.bPenIsUp = True

	def penDown( self ):
		self.virtualPenIsUp = False  # Virtual pen keeps track of state for resuming plotting.
		if (self.bPenIsUp != False):  # skip if pen is already down
			if ((not self.resumeMode) and ( not self.bStopped )): #skip if resuming or stopped
				ebb_motion.sendPenDown(self.serialPort, self.options.penUpDelay )						
				self.bPenIsUp = False

	def ServoSetupWrapper( self ):
		# Assert what the defined "up" and "down" positions of the servo motor should be,
		#    and determine what the pen state is.
		self.ServoSetup()
		strVersion = ebb_serial.query( self.serialPort, 'QP\r' )
		if strVersion[0] == '0':
			self.bPenIsUp = False
		else:
			self.bPenIsUp = True

	def ServoSetup( self ):
		''' Pen position units range from 0% to 100%, which correspond to
		    a typical timing range of 7500 - 25000 in units of 1/(12 MHz).
		    1% corresponds to ~14.6 us, or 175 units of 1/(12 MHz).
		'''
		
		servo_range = axidraw_conf.SERVO_MAX - axidraw_conf.SERVO_MIN
		servo_slope = float(servo_range) / 100.0
		
		intTemp = int(round(axidraw_conf.SERVO_MIN + servo_slope * self.options.penUpPosition))
		ebb_serial.command( self.serialPort,  'SC,4,' + str( intTemp ) + '\r' )	
				
		intTemp = int(round(axidraw_conf.SERVO_MIN + servo_slope * self.options.penDownPosition))
		ebb_serial.command( self.serialPort,  'SC,5,' + str( intTemp ) + '\r' )

		''' Servo speed units are in units of %/second, referring to the
			percentages above.  The EBB takes speeds in units of 1/(12 MHz) steps
			per 21 ms.  Scaling as above, 1% in 1 second corresponds to
			175 steps/s, or 0.175 steps/ms, which corresponds
			to ~3.6 steps/21 ms.  Rounding this to 4 steps/21 ms is sufficient.		'''
		
		intTemp = 4 * self.options.ServoUpSpeed
		ebb_serial.command( self.serialPort, 'SC,11,' + str( intTemp ) + '\r' )

		intTemp = 4 * self.options.ServoDownSpeed
		ebb_serial.command( self.serialPort,  'SC,12,' + str( intTemp ) + '\r' )
		
	def stop( self ):
		self.bStopped = True

	def getDocProps( self ):
		'''
		Get the document's height and width attributes from the <svg> tag.
		Use a default value in case the property is not present or is
		expressed in units of percentages.
		'''
		self.svgHeight = plot_utils.getLengthInches( self, 'height' )
		self.svgWidth = plot_utils.getLengthInches( self, 'width' )
		if (self.options.autoRotate) and (self.svgHeight > self.svgWidth ):
			self.printPortrait = True
		if ( self.svgHeight == None ) or ( self.svgWidth == None ):
			return False
		else:
			return True

e = WCB()
e.affect()