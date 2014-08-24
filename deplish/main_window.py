#
# Depends
# Copyright (C) 2014 by Andrew Gardner & Jonas Unger.  All rights reserved.
# BSD license (LICENSE.txt for details).
#

"""Main GUI

The main window which contains the dependency graph view widget and a dock for 
additional windows.  Executing the program from the commandline interface 
creates one of these windows (and therefore all startup routines execute), but 
does not display it.

"""

import os
import sys
import json
import tempfile
import itertools

from PySide import QtCore, QtGui

import dag
import node
import util
import variables
import data_packet
import file_dialog
import undo_commands
import property_widget
import variable_widget
import graphics_widgets
import scenegraph_widget


class MainWindow(QtGui.QMainWindow):
	"""Construct main UI

	This class constructs the UI, consisting of the many windows, menu items,
	undo managers, plugin systems, workflow variables, etc.  It also holds 
	functions to manage what happens when dag nodes change (see
	"DAG management" section) and loading and saving of DAG snapshots.

	"""

	def __init__(self, startFile="", parent=None):
		QtGui.QMainWindow.__init__(self, parent)

		# Add the DAG widget
		self.graphicsViewWidget = graphics_widgets.GraphicsViewWidget(self)
		self.graphicsScene = self.graphicsViewWidget.scene()
		self.setCentralWidget(self.graphicsViewWidget)

		# Create the docking widget for the properties dialog
		self.propDock = QtGui.QDockWidget()
		self.propDock.setObjectName('propDock')
		self.propDock.setAllowedAreas(QtCore.Qt.RightDockWidgetArea | QtCore.Qt.LeftDockWidgetArea)
		self.propDock.setWindowTitle("Properties")
		self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.propDock)

		# Create and add the properties dialog to the dock widget
		self.propWidget = property_widget.PropWidget(self)
		self.propDock.setWidget(self.propWidget)

		# Create the docking widget for the sceneGraph dialog
		self.sceneGraphDock = QtGui.QDockWidget()
		self.sceneGraphDock.setObjectName('sceneGraphDock')
		self.sceneGraphDock.setAllowedAreas(QtCore.Qt.RightDockWidgetArea | QtCore.Qt.LeftDockWidgetArea)
		self.sceneGraphDock.setWindowTitle("Scene Graph")
		self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.sceneGraphDock)

		# Create and add the sceneGraph dialog to the dock widget
		self.sceneGraphWidget = scenegraph_widget.SceneGraphWidget(self)
		self.sceneGraphDock.setWidget(self.sceneGraphWidget)

		# Create the docking widget for the variable dialog
		self.variableDock = QtGui.QDockWidget()
		self.variableDock.setObjectName('variableDock')
		self.variableDock.setAllowedAreas(QtCore.Qt.RightDockWidgetArea | QtCore.Qt.LeftDockWidgetArea)
		self.variableDock.setWindowTitle("Variables")
		self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.variableDock)

		# Create and add the variable dialog to the dock widget
		self.variableWidget = variable_widget.VariableWidget(self)
		self.variableDock.setWidget(self.variableWidget)
		self.variableDock.hide()

		# Set some locals
		self.dag = None
		self.undoStack = QtGui.QUndoStack(self)

		# Undo and Redo have built-in ways to create their menus
		undoAction = self.undoStack.createUndoAction(self, "&Undo")
		undoAction.setShortcuts(QtGui.QKeySequence.Undo)
		redoAction = self.undoStack.createRedoAction(self, "&Redo")
		redoAction.setShortcuts(QtGui.QKeySequence.Redo)

		# Create the menu bar
		fileMenu = self.menuBar().addMenu("&File")
		fileMenu.addAction(QtGui.QAction("&Open DAG...", self, shortcut="Ctrl+O", triggered=self.openDialog))
		fileMenu.addAction(QtGui.QAction("&Save DAG", self, shortcut="Ctrl+S", triggered=lambda: self.save(self.workingFilename)))
		fileMenu.addAction(QtGui.QAction("Save DAG &Version Up", self, shortcut="Ctrl+Space", triggered=self.saveVersionUp))
		fileMenu.addAction(QtGui.QAction("Save DAG &As...", self, shortcut="Ctrl+Shift+S", triggered=self.saveAs))
		fileMenu.addAction(QtGui.QAction("&Quit...", self, shortcut="Ctrl+Q", triggered=self.close))
		editMenu = self.menuBar().addMenu("&Edit")
		editMenu.addAction(undoAction)
		editMenu.addAction(redoAction)
		editMenu.addSeparator()
		createMenu = editMenu.addMenu("&Create Node")
		editMenu.addAction(QtGui.QAction("&Delete Node(s)", self, shortcut="Delete", triggered=self.deleteSelectedNodes))
		editMenu.addAction(QtGui.QAction("&Shake Node(s)", self, shortcut="Backspace", triggered=self.shakeSelectedNodes))
		editMenu.addAction(QtGui.QAction("D&uplicate Node", self, shortcut="Ctrl+D", triggered=self.duplicateSelectedNodes))
		editMenu.addSeparator()
		editMenu.addAction(QtGui.QAction("&Group Nodes", self, shortcut="Ctrl+G", triggered=self.groupSelectedNodes))
		editMenu.addAction(QtGui.QAction("&Ungroup Nodes", self, shortcut="Ctrl+Shift+G", triggered=self.ungroupSelectedNodes))
		executeMenu = self.menuBar().addMenu("E&xecute")
		executeMenu.addAction(QtGui.QAction("&Execute Graph", self, shortcut= "Ctrl+E", triggered=self.executeSelected))
		executeMenu.addAction(QtGui.QAction("Execute &Selected Node", self, shortcut= "Ctrl+Shift+E", triggered=lambda: self.executeSelected(executeImmediately=True)))
		executeMenu.addSeparator()
		executeMenu.addAction(QtGui.QAction("Version &Up outputs", self, shortcut= "Ctrl+U", triggered=self.versionUpSelectedOutputFilenames))
		executeMenu.addSeparator()
		executeMenu.addAction(QtGui.QAction("&Reload plugins", self, shortcut= "Ctrl+0", triggered=self.reloadPlugins))
		windowMenu = self.menuBar().addMenu("&Window")
		windowMenu.addAction(self.propDock.toggleViewAction())
		windowMenu.addAction(self.sceneGraphDock.toggleViewAction())
		windowMenu.addAction(self.variableDock.toggleViewAction())

		# Application settings
		self.settings = QtCore.QSettings('vcl', 'depends', self)
		self.restoreSettings()

		# Setup the variables, load the plugins, and auto-generate the read dag nodes
		self.setupStartupVariables()
		node.loadChildNodesFromPaths(variables.value('NODE_PATH').split(':'))
		file_dialog.loadChildFileDialogsFromPaths(variables.value('FILE_DIALOG_PATH').split(':'))
		node.generateReadDagNodes()

		# Generate the Create menu.  Must be done after plugins are loaded.
		for action in self.createCreateMenuActions():
			createMenu.addAction(action)

		# Load the starting filename or create a new DAG
		self.workingFilename = startFile
		self.dag = dag.DAG()
		self.graphicsScene.setDag(self.dag)
		if not self.open(self.workingFilename):
			self.setWindowTitle("Depends")
		self.undoStack.setClean()

		# This is a small workaround to insure the properties dialog doesn't 
		# try to redraw twice when two nodes are rapidly selected 
		# (within a frame of eachother).  There's a good chance the way I
		# construct a property dialog is strange, but a twice-at-once redraw
		# was making the entire UI destroy itself and spawn a temporary child
		# window that had the same name as the program 'binary'.
		self.selectionTimer = QtCore.QTimer(self)
		self.selectionTimer.setInterval(0)
		self.selectionTimer.timeout.connect(self.selectionRefresh)

		# Hook up some signals
		self.graphicsViewWidget.createNode.connect(self.create_node)
		self.graphicsScene.selectionChanged.connect(self.selectionChanged)
		self.graphicsScene.nodesDisconnected.connect(self.nodesDisconnected)
		self.graphicsScene.nodesConnected.connect(self.nodesConnected)
		self.propWidget.attrChanged.connect(self.propertyEdited)
		self.propWidget.rangeChanged.connect(self.propertyRangeEdited)
		self.propWidget.mouseover.connect(self.highlightDagNodes)
		self.propWidget.mouseover.connect(self.sceneGraphWidget.highlightRowsUsingNodes)
		self.sceneGraphWidget.mouseover.connect(self.highlightDagNodes)
		self.sceneGraphWidget.mouseover.connect(self.propWidget.highlightInputs)
		self.variableWidget.addVariable.connect(variables.add)
		self.variableWidget.setVariable.connect(variables.setx)
		self.variableWidget.removeVariable.connect(variables.remove)
		self.undoStack.cleanChanged.connect(self.setWindowTitleClean)

	def closeEvent(self, event):
		"""
		Save program settings and ask "are you sure" if there are unsaved changes.
		"""
		if not self.undoStack.isClean():
			if self.yesNoDialog("Current workflow is not saved.  Save it before quitting?"):
				if self.workingFilename:
					self.save(self.workingFilename)
				else:
					self.saveAs()
		self.saveSettings()
		QtGui.QMainWindow.closeEvent(self, event)

	def updateScenegraph(self, dagNodes):
		"""
		Rebuild the scenegraph widget based on the given dag nodes.
		"""
		if dagNodes and len(dagNodes) == 1:
			liveSceneGraph = self.dag.buildSceneGraph(dagNodes[0])
			self.sceneGraphWidget.rebuild(liveSceneGraph, dagNodes[0])
		else:
			self.sceneGraphWidget.rebuild(None, None)


	def selectedDagNodes(self):
		"""
		Return a list of all selected DagNodes in the scene.
		"""
		selectedDrawNodes = self.graphicsScene.selectedItems()
		return [sdn.dagNode for sdn in selectedDrawNodes]


	def setupStartupVariables(self):
		"""
		Each program starts with a set of workflow variables that are defined
		by where the program is executed from and potentially a set of
		environment variables.
		"""
		# The current session gets a "binary directory" variable
		variables.add('DEPENDS_DIR')
		variables.setx('DEPENDS_DIR', os.path.dirname(os.path.realpath(__file__)), readOnly=True)

		# ...And a path that points to where the nodes are loaded from
		variables.add('NODE_PATH')
		if not os.environ.get('DEPENDS_NODE_PATH'):
			variables.setx('NODE_PATH', os.path.join(variables.value('DEPENDS_DIR'), 'nodes'), readOnly=True)
		else:
			variables.setx('NODE_PATH', os.environ.get('DEPENDS_NODE_PATH'), readOnly=True)

		# ...And a path that points to where the File Dialogs come from
		variables.add('FILE_DIALOG_PATH')
		if not os.environ.get('DEPENDS_FILE_DIALOG_PATH'):
			variables.setx('FILE_DIALOG_PATH', os.path.join(variables.value('DEPENDS_DIR'), 'file_dialogs'), readOnly=True)
		else:
			variables.setx('FILE_DIALOG_PATH', os.environ.get('DEPENDS_FILE_DIALOG_PATH'), readOnly=True)

		
	def clearVariableDictionary(self):
		"""
		Clear all variables from the 'global' variable dictionary that aren't 
		"built-in" to the current session.
		"""
		for key in variables.names():
			if key == 'DEPENDS_DIR':
				continue
			if key == 'NODE_PATH':
				continue
		

	def saveSettings(self):
		"""
		Register the software's general settings with the QSettings object 
		and force a save with sync().
		"""
		self.settings.setValue("mainWindowGeometry", self.saveGeometry())
		self.settings.setValue("mainWindowState", self.saveState())
		self.settings.sync()
		
		
	def restoreSettings(self):
		"""
		Restore the software's general settings by pulling data out of the 
		current settings object.
		"""
		self.restoreGeometry(self.settings.value('mainWindowGeometry'))
		self.restoreState(self.settings.value('mainWindowState'))
		

	###########################################################################
	## Complex message handling
	###########################################################################
	def create_node(self, nodeType, nodeLocation):
		"""
		Create a new dag node with a safe name, add it to the dag, and register it with the QGraphicsScene.
		"""
		preSnap = self.dag.snapshot(nodeMetaDict=self.graphicsScene.nodeMetaDict(), connectionMetaDict=self.graphicsScene.connectionMetaDict())

		newDagNode = nodeType()
		nodeName = node.cleanNodeName(newDagNode.typeStr())
		nodeName = self.dag.safeNodeName(nodeName)
		newDagNode.setName(nodeName)
		self.dag.add_node(newDagNode)
		self.graphicsScene.addExistingDagNode(newDagNode, nodeLocation)

		currentSnap = self.dag.snapshot(nodeMetaDict=self.graphicsScene.nodeMetaDict(), connectionMetaDict=self.graphicsScene.connectionMetaDict())
		self.undoStack.push(undo_commands.DagAndSceneUndoCommand(preSnap, currentSnap, self.dag, self.graphicsScene))


	def delete_nodes(self, dagNodesToDelete):
		"""
		Delete an existing dag node and its edges, and make sure the QGraphicsScene cleans up as well.
		"""
		nodesAffected = list()
		preSnap = self.dag.snapshot(nodeMetaDict=self.graphicsScene.nodeMetaDict(), connectionMetaDict=self.graphicsScene.connectionMetaDict())

		# Clean up the graphics scene
		# TODO: Should be a signal that tells the scene what to do
		for dagNode in dagNodesToDelete:
			drawNode = self.graphicsScene.drawNode(dagNode)
			drawEdges = drawNode.drawEdges()
			for edge in drawEdges:
				edge.sourceDrawNode().removeDrawEdge(edge)
				edge.destDrawNode().removeDrawEdge(edge)
				self.graphicsScene.removeItem(edge)
			self.graphicsScene.removeItem(drawNode)

		# Remove the nodes from the dag
		for delNode in dagNodesToDelete:
			nodesAffected = nodesAffected + self.dagNodeDisconnected(delNode)
			nodesAffected.remove(delNode)
			self.dag.remove_node(delNode)

		currentSnap = self.dag.snapshot(nodeMetaDict=self.graphicsScene.nodeMetaDict(), connectionMetaDict=self.graphicsScene.connectionMetaDict())
		self.undoStack.push(undo_commands.DagAndSceneUndoCommand(preSnap, currentSnap, self.dag, self.graphicsScene))
		
		# Updates the drawNodes for each of the affected dagNodes
		self.graphicsScene.refreshDrawNodes(nodesAffected)
	
	
	def shakeNodes(self, dagNodesToShake):
		"""
		Pull a node out of the dependency chain without deleting it and without 
		losing downstream information.
		"""
		nodesAffected = list()
		preSnap = self.dag.snapshot(nodeMetaDict=self.graphicsScene.nodeMetaDict(), connectionMetaDict=self.graphicsScene.connectionMetaDict())

		for dagNode in dagNodesToShake:
			inNodes = self.dag.nodeConnectionsIn(dagNode)
			outNodes = self.dag.nodeConnectionsOut(dagNode)
			drawNode = self.graphicsScene.drawNode(dagNode)
			
			# Connect all previous dag nodes to all next nodes & add the draw edges
			for inputDagNode in inNodes:
				inputDrawNode = self.graphicsScene.drawNode(inputDagNode)
				for outputDagNode in outNodes:
					outputDrawNode = self.graphicsScene.drawNode(outputDagNode)
					self.dag.connect_nodes(inputDagNode, outputDagNode)
					newDrawEdge = self.graphicsScene.addExistingConnection(inputDagNode, outputDagNode)
					newDrawEdge.horizontalConnectionOffset = self.graphicsScene.drawEdge(drawNode, outputDrawNode).horizontalConnectionOffset
					newDrawEdge.adjust()
			
			# Disconnect this dag node from everything
			for inputDagNode in inNodes:
				self.dag.disconnect_nodes(inputDagNode, dagNode)
			for outputDagNode in outNodes:
				nodesAffected = nodesAffected + self.dagNodeDisconnected(dagNode)
				self.dag.disconnect_nodes(dagNode, outputDagNode)

			# Remove all draw edges
			for edge in drawNode.drawEdges():
				edge.sourceDrawNode().removeDrawEdge(edge)
				edge.destDrawNode().removeDrawEdge(edge)
				self.graphicsScene.removeItem(edge)
				
			# Nullify all our inputs
			for input in dagNode.inputs():
				dagNode.setInputValue(input.name, "")

		currentSnap = self.dag.snapshot(nodeMetaDict=self.graphicsScene.nodeMetaDict(), connectionMetaDict=self.graphicsScene.connectionMetaDict())
		self.undoStack.push(undo_commands.DagAndSceneUndoCommand(preSnap, currentSnap, self.dag, self.graphicsScene))

		# A few refreshes
		self.propWidget.refresh()
		self.updateScenegraph(self.selectedDagNodes())
		self.graphicsScene.refreshDrawNodes(nodesAffected)


	def duplicateNodes(self, dagNodesToDupe):
		"""
		Create identical copies of the given dag nodes, but drop their 
		incoming and outgoing connections.
		"""
		preSnap = self.dag.snapshot(nodeMetaDict=self.graphicsScene.nodeMetaDict(), connectionMetaDict=self.graphicsScene.connectionMetaDict())
		
		for dagNode in dagNodesToDupe:
			dupedNode = dagNode.duplicate("_Dupe")
			newLocation = self.graphicsScene.drawNode(dagNode).pos() + QtCore.QPointF(20, 20)
			self.dag.add_node(dupedNode)
			self.graphicsScene.addExistingDagNode(dupedNode, newLocation)
		
		currentSnap = self.dag.snapshot(nodeMetaDict=self.graphicsScene.nodeMetaDict(), connectionMetaDict=self.graphicsScene.connectionMetaDict())
		self.undoStack.push(undo_commands.DagAndSceneUndoCommand(preSnap, currentSnap, self.dag, self.graphicsScene))


	def versionUpOutputFilenames(self, dagNodesToVersionUp):
		"""
		Increment the filename version of all output filenames in a given
		list of dag nodes.
		"""
        # TODO: Likely remove this function for 'Publish' as it seems somewhat irrelevant?
		preSnap = self.dag.snapshot(nodeMetaDict=self.graphicsScene.nodeMetaDict(), connectionMetaDict=self.graphicsScene.connectionMetaDict())

		nodesAffected = list()
		for dagNode in self.selectedDagNodes():
			for output in dagNode.outputs():
				for soName in output.subOutputNames():
					if not output.value[soName]:
						continue
					currentValue = output.value[soName]
					updatedValue = util.nextFilenameVersion(currentValue)
					dagNode.setOutputValue(output.name, soName, updatedValue)
					nodesAffected = nodesAffected + self.dagNodeOutputChanged(dagNode, dagNode.outputNamed(output.name))
			nodesAffected = nodesAffected

		currentSnap = self.dag.snapshot(nodeMetaDict=self.graphicsScene.nodeMetaDict(), connectionMetaDict=self.graphicsScene.connectionMetaDict())
		self.undoStack.push(undo_commands.DagAndSceneUndoCommand(preSnap, currentSnap, self.dag, self.graphicsScene))

		# Updates the drawNodes for each of the affected dagNodes
    	    	self.propWidget.refresh()
		self.graphicsScene.refreshDrawNodes(nodesAffected)


	def nodesDisconnected(self, fromDagNode, toDagNode):
		"""
		When the user interface disconnects two nodes, tell the in-flight
		dag about it.
		"""
		nodesAffected = list()
		nodesAffected = nodesAffected + self.dagNodeDisconnected(fromDagNode)
		self.dag.disconnect_nodes(fromDagNode, toDagNode)

		# A few refreshes
		self.updateScenegraph(self.selectedDagNodes())
		self.propWidget.refresh()
		self.graphicsScene.refreshDrawNodes(nodesAffected)

	
	def nodesConnected(self, fromDagNode, toDagNode):
		"""
		When the user interface connects two nodes, tell the in-flight dag
		about it.
		"""
		self.dag.connect_nodes(fromDagNode, toDagNode)
		self.updateScenegraph(self.selectedDagNodes())


	def propertyEdited(self, dagNode, propName, newValue, propertyType=None):
		"""
		When the user interface edits a property of a node (meaning an attribute,
		input, or output), communicate this information to the in-flight dag
		and nodes, and handle the repercussions.
		"""
		somethingChanged = False
		preSnap = self.dag.snapshot(nodeMetaDict=self.graphicsScene.nodeMetaDict(), connectionMetaDict=self.graphicsScene.connectionMetaDict())

		nodesAffected = list()
		if propName == "Name" and propertyType is node.DagNodeAttribute:
			if newValue != dagNode.name:
				dagNode.setName(newValue)
				nodesAffected = nodesAffected + [dagNode]
				somethingChanged = True
		else:
			if propertyType is node.DagNodeInput:
				if newValue != dagNode.inputValue(propName):
					dagNode.setInputValue(propName, newValue)
					nodesAffected = nodesAffected + self.dagNodeInputChanged(dagNode, dagNode.inputNamed(propName))
					somethingChanged = True
					self.propWidget.refresh()

			elif propertyType is node.DagNodeOutput:
				bothNames = propName.split('.')
				if newValue != dagNode.outputValue(bothNames[0], bothNames[1]):
					dagNode.setOutputValue(bothNames[0], bothNames[1], newValue)
					nodesAffected = nodesAffected + self.dagNodeOutputChanged(dagNode, dagNode.outputNamed(bothNames[0]))
					somethingChanged = True
				
			elif propertyType is node.DagNodeAttribute:
				if newValue != dagNode.attributeValue(propName):
					dagNode.setAttributeValue(propName, newValue)
					nodesAffected = nodesAffected + [dagNode]
					somethingChanged = True

        # TODO: 'Publish' could set up some type of 'dirtying' the nodes down the chain. Though since it's likely
        #       going to be a "push"-style graph this doesn't make any sense. It would always re-evaluate completely
        #       right? Or can we allow to evaluate only the last part of the graph?
		#if somethingChanged:
		#   nodesAffected = nodesAffected
		
		# Undos aren't registered when the value doesn't actually change
		if somethingChanged:
			currentSnap = self.dag.snapshot(nodeMetaDict=self.graphicsScene.nodeMetaDict(), connectionMetaDict=self.graphicsScene.connectionMetaDict())
			self.undoStack.push(undo_commands.DagAndSceneUndoCommand(preSnap, currentSnap, self.dag, self.graphicsScene, self.propWidget))

		# Updates the drawNodes for each of the affected dagNodes
		self.graphicsScene.refreshDrawNodes(nodesAffected)


	def propertyRangeEdited(self, dagNode, propName, newRange, propertyType):
		"""
		When the user interface edits the range of a property (attribute, input,
		or output), modify the in-flight dag and nodes and insure everything
		needed changes accordingly.
		"""
		registerUndo = False
		preSnap = self.dag.snapshot(nodeMetaDict=self.graphicsScene.nodeMetaDict(), connectionMetaDict=self.graphicsScene.connectionMetaDict())

		# None is a legit value for a range value.  Make sure blanks are Nones.
		if newRange[0] == "":
			newRange = (None, newRange[1])
		if newRange[1] == "":
			newRange = (newRange[0], None)
		
		nodesAffected = list()
		if propertyType is node.DagNodeInput:
			if newRange != dagNode.inputRange(propName, variableSubstitution=False):
				dagNode.setInputRange(propName, newRange)
				nodesAffected = nodesAffected + [dagNode]
				registerUndo = True
				
		elif propertyType is node.DagNodeOutput:
			if newRange != dagNode.outputRange(propName, variableSubstitution=False):
				dagNode.setOutputRange(propName, newRange)
				nodesAffected = nodesAffected + [dagNode]
				registerUndo = True
				
		elif propertyType is node.DagNodeAttribute:
			if newRange != dagNode.attributeRange(propName, variableSubstitution=False):
				dagNode.setAttributeRange(propName, newRange)
				nodesAffected = nodesAffected + [dagNode]

		# Undos aren't registered when the value doesn't actually change, 
		if registerUndo:
			currentSnap = self.dag.snapshot(nodeMetaDict=self.graphicsScene.nodeMetaDict(), connectionMetaDict=self.graphicsScene.connectionMetaDict())
			self.undoStack.push(undo_commands.DagAndSceneUndoCommand(preSnap, currentSnap, self.dag, self.graphicsScene, self.propWidget))

		# Updates the drawNodes for each of the affected dagNodes
		self.graphicsScene.refreshDrawNodes(nodesAffected)


	def selectionRefresh(self):
		"""
		A small workaround for a property dialog refresh issue.  See comments 
		in constructor ("This is a small workaround...") for more details.
		"""
		selectedDagNodes = self.selectedDagNodes()
		self.propWidget.rebuild(self.dag, selectedDagNodes)
		self.updateScenegraph(selectedDagNodes)
		self.selectionTimer.stop()


	def selectionChanged(self):
		"""
		Fires off an instantaneous timer that rebuilds the scenegraph and 
		property widget based on a change of selection in the SceneWidget.
		Works in conjunction with self.selectionRefresh().
		"""
		if self.selectionTimer.isActive():
			return
		self.selectionTimer.start(0)


	def highlightDagNodes(self, dagNodeList):
		"""
		Given a list of DagNodes to highlight, derive their drawNodes, and 
		alert the graphics widgets that a highlight might be apropos.
		"""
		drawNodes = list()
		if dagNodeList:
			for dagNode in dagNodeList:
				drawNodes.append(self.graphicsScene.drawNode(dagNode))
		self.graphicsScene.setHighlightNodes(drawNodes)
	

	def setWindowTitleClean(self, isClean):
		"""
		Adjust the window title's clean state based on an incoming parameter.
		"""
		if isClean:
			self.setWindowTitle("%s" % self.windowTitle()[:-1])
		else:
			self.setWindowTitle("%s*" % self.windowTitle())
	

	###########################################################################
	## DAG management
	###########################################################################
	def dagNodeDisconnected(self, fromDagNode):
		"""
		When a node is disconnected, all nodes after it lose their inputs to
		nodes that come before it. This function is to be called before the DAG 
		removes any connections or deletes any nodes from its collection.
		"""
		nodesAffected = [fromDagNode]

		allNodesAfter = self.dag.allNodesAfter(fromDagNode)
		allNodesBefore = self.dag.allNodesBefore(fromDagNode) + [fromDagNode]
		for afterNode in allNodesAfter:
			for input in afterNode.inputs():
				inputNode = self.dag.nodeInputComesFromNode(afterNode, input)[0]
				if inputNode in allNodesBefore:
					afterNode.setInputValue(input.name, "")
					afterNode.setInputRange(input.name, None)
					nodesAffected.append(afterNode)
					nodesAffected = nodesAffected + self.dagNodeInputChanged(afterNode, input)

		return nodesAffected


	def dagNodeInputChanged(self, dagNode, input):
		"""
		When a node's input is changed, its range should be set to the same as
		the output connected to it.  Also, if there is an output that is affected
		by this input, its range should be changed as well.
		"""
		nodesAffected = list()
		
		# Gather the output that corresponds to the changed input
		affectedOutput = dagNode.outputAffectedByInput(input)

		# If you have changed the input source, set this input's range based on the extents of the incoming range.
		incomingDataPacket = self.dag.nodeOutputDataPacket(*data_packet.nodeAndOutputFromScenegraphLocationString(input.value, self.dag))
		if incomingDataPacket:
			if incomingDataPacket.sequenceRange:
				nodesAffected.append(dagNode)
				seqRange = (str(incomingDataPacket.sequenceRange[0]), str(incomingDataPacket.sequenceRange[1]))
				dagNode.setInputRange(input.name, seqRange)
				
				# A new association has been made, is there an output range that may also be affected?
				if affectedOutput:
					for subName in affectedOutput.subOutputNames():
						dagNode.setOutputRange(affectedOutput.name, seqRange)

		# Notify the system that there has been a changed output - this covers the case of the output range
		# change (loop just above this one) and the input type being changed, and thus cascading down.
		if affectedOutput:
			nodesAffected = nodesAffected + self.dagNodeOutputChanged(dagNode, affectedOutput)
			
		return nodesAffected
	
	
	def dagNodeOutputChanged(self, dagNode, output):
		"""
		When a node output's type or range is changed, inputs that connect to it 
		may need to be adjusted.  Incompatible types must be disconnected and 
		ranges should be clamped.
		"""
		nodesAffected = list()

		# Input types downstream may no longer be able to connect to this node.  Handle recursively.
		allAffectedNodes = self.dag.allNodesDependingOnNode(dagNode, recursion=False)
		for affectedNode in allAffectedNodes:
			for input in affectedNode.inputs():
				nodeComingInOutputType = self.dag.nodeOutputType(*self.dag.nodeInputComesFromNode(affectedNode, input))
				nodesAffected = nodesAffected + self.dagNodeInputChanged(affectedNode, input)
				if nodeComingInOutputType not in input.allPossibleInputTypes():
					affectedNode.setInputValue(input.name, "")
					affectedNode.setInputRange(input.name, None)
					nodesAffected.append(affectedNode)
		
		# The range of directly-connected inputs may need to be adjusted
		directlyAffectedNodes = self.dag.allNodesDependingOnNode(dagNode, recursion=False)
		for affectedNode in directlyAffectedNodes:
			for input in affectedNode.inputs():
				(incomingNode, incomingOutput) = self.dag.nodeInputComesFromNode(affectedNode, input)
				if input.seqRange != incomingOutput.getSeqRange():
					input.seqRange = incomingOutput.getSeqRange()
					nodesAffected.append(affectedNode)
					
		# Data that used to exist may no longer exist.  Therefore all directly affected nodes should refresh.
		nodesAffected = nodesAffected + [dagNode] + directlyAffectedNodes
				
		return nodesAffected


	def dagNodeVariablesUsed(self, dagNode):
		"""
		Returns a tuple containing a list of all the single-dollar and a list 
		of all the double-dollar variables used in the current DAG.
		"""
		singleDollarList = list()
		doubleDollarList = list()
		for input in dagNode.inputs():
			vps = variables.present(dagNode.inputValue(input.name, variableSubstitution=False))
			vss = (list(), list())
			vss2 = (list(), list())
			if dagNode.inputRange(input.name, variableSubstitution=False):
				vss = variables.present(dagNode.inputRange(input.name, variableSubstitution=False)[0])
				vss2 = variables.present(dagNode.inputRange(input.name, variableSubstitution=False)[1])
			singleDollarList += vps[0] + vss[0] + vss2[0]
			doubleDollarList += vps[1] + vss[1] + vss2[1]
		for attribute in dagNode.attributes():
			vps = variables.present(dagNode.attributeValue(attribute.name, variableSubstitution=False))
			vss = (list(), list())
			vss2 = (list(), list())
			if dagNode.attributeRange(attribute.name, variableSubstitution=False):
				vss = variables.present(dagNode.attributeRange(attribute.name, variableSubstitution=False)[0])
				vss2 = variables.present(dagNode.attributeRange(attribute.name, variableSubstitution=False)[1])
			singleDollarList += vps[0] + vss[0] + vss2[0]
			doubleDollarList += vps[1] + vss[1] + vss2[1]
		for output in dagNode.outputs():
			for subName in output.subOutputNames():
				vps = variables.present(dagNode.outputValue(output.name, subName, variableSubstitution=False))
				vss = (list(), list())
				vss2 = (list(), list())
				if dagNode.outputRange(output.name, variableSubstitution=False):
					vss = variables.present(dagNode.outputRange(output.name, variableSubstitution=False)[0])
					vss2 = variables.present(dagNode.outputRange(output.name, variableSubstitution=False)[1])
				singleDollarList += vps[0] + vss[0] + vss2[0]
				doubleDollarList += vps[1] + vss[1] + vss2[1]
		return (list(set(singleDollarList)), list(set(doubleDollarList)))
		

	def dagNodesSanityCheck(self, dagNodes):
		"""
		Runs a series of sanity tests on the given dag nodes to make sure they
		are fit to be executed in their current state.
		"""
		#
		# Full DAG validation
		#
		# Insure all $ variables that are used, exist
		for dagNode in dagNodes:
			(singleDollarVariables, doubleDollarVariables) = self.dagNodeVariablesUsed(dagNode)
			for sdVariable in singleDollarVariables:
				if sdVariable not in variables.names():
					raise RuntimeError("Depends variable $%s used in node '%s' does not exist in current environment." % (sdVariable, dagNode.name))

		# Insure all $$ variables that are used, are present in the current environment
		for dagNode in dagNodes:
			(singleDollarVariables, doubleDollarVariables) = self.dagNodeVariablesUsed(dagNode)
			for ddVariable in doubleDollarVariables:
				if ddVariable not in os.environ:
					raise RuntimeError("Environment variable $%s used in node '%s' does not exist in current environment." % (ddVariable, dagNode.name))
		
		#
		# Individual node validation
		#
		for dagNode in dagNodes:
			# Insure all the inputs are connected
			if not self.dag.nodeAllInputsConnected(dagNode):
				raise RuntimeError("Node '%s' is missing a required input." % (dagNode.name))
			
			# Insure the inputs match what are connected to them
			for input in dagNode.inputs():
				incomingDataPacketType = type(self.dag.nodeInputDataPacket(dagNode, input))
				if incomingDataPacketType not in input.allPossibleInputTypes():
					raise RuntimeError("Node '%s' has an incoming DataPacket that doesn't match its input's ('%s') type." % (dagNode.name, input.name))
			
			# Insure each input's range is within the output that's connected to it's range
			for input in dagNode.inputs():
				if not input.seqRange:
					continue
				inputRange = (int(input.seqRange[0]), int(input.seqRange[1]))
				incomingDataPacket = self.dag.nodeInputDataPacket(dagNode, input)
				incomingRange = incomingDataPacket.sequenceRange
				if inputRange[0] < incomingRange[0] or inputRange[1] > incomingRange[1]:
					(outputNode, output) = self.dag.nodeInputComesFromNode(dagNode, input)
					raise RuntimeError("Input range of node '%s' input '%s' extends beyond the bounds of output from node '%s' output '%s'" % 
									   (dagNode.name, input.name, outputNode.name, output.name))
			
			# Insure the number of input frames match the number of output frames for nodes that are embarassingly parallel.
			# NOTE: This one can go away someday after careful thought - this restriction exists, at the moment, for simplicity's sake.
			if dagNode.isEmbarrassinglyParallel():			# and self.dag.nodeGroupCount(dagNode) > 0:
				for input in dagNode.inputs():
					if not input.seqRange:
						continue
					inputRange = (int(input.seqRange[0]), int(input.seqRange[1]))
					outputRangePreSubstitution = dagNode.outputAffectedByInput(input).getSeqRange()
					outputRange = (int(outputRangePreSubstitution[0]), int(outputRangePreSubstitution[1]))
					if inputRange != outputRange:
						raise RuntimeError("The parallel node, '%s', that lives in group '%s' is trimming its inputs a bit.  This is currently a no-no" %
										   (dagNode.name, self.dag.nodeInGroupNamed(dagNode)))
			
			# Insure all your outputs are filled-in
			# Insure output paths exist (most nodes don't create paths if they aren't present)
			# Insure the output paths can be written to
			# Insure if there is an output sequence marker (#), there are sequence numbers
			for output in dagNode.outputs():
				# NOTE: This doesn't work at the moment because of how inclusive the values dict is.  Fix!
				#for field in output.value.values():
				#	if not field:
				#		raise RuntimeError("Node '%s' is missing a value in its output field '%s'." % (dagNode.name, output.name))
				for field in output.value.values():
					if not field: 
						continue
					dirName = os.path.dirname(field)
					if not os.path.exists(dirName):
						raise RuntimeError("Node '%s' will attempt to write to a directory that doesn't exist (%s)." % (dagNode.name, dirName))
				for field in output.value.values():
					if not field: 
						continue
					dirName = os.path.dirname(field)
					if not os.access(dirName, os.W_OK | os.X_OK):
						raise RuntimeError("Node '%s' will attempt to write to a directory that you don't have permissions to (%s)." % (dagNode.name, dirName))
				for key in output.value:
					if util.framespec.hasFrameSymbols(output.value[key]):
						if not output.getSeqRange():
							raise RuntimeError("Node '%s' output '%s' has a string with frame symbols, but has no sequence range defined." % (dagNode.name, output.name))
			
			# Insure the validation function passes for each node.
			try:
				dagNode.validate()
			except Exception, err:
				raise RuntimeError("Dag node '%s' did not pass its validation test with the error:\n%s" % (dagNode.name, err))
		
		#
		# Node group validation
		#
		# Insure all nodes in each node group are embarrassingly parallel
		for groupName in self.dag.nodeGroupDict:
			for dagNode in self.dag.nodeGroupDict[groupName]:
				if not dagNode.isEmbarrassinglyParallel():
					raise RuntimeError("Node '%s' in group '%s' is not embarrassingly parallel." % (dagNode.name, groupName))
		
		# Insure all input and output ranges are identical in each dag group
		# NOTE: This check can be removed with some careful thought and changes in the execution engine.
		for groupName in self.dag.nodeGroupDict:
			seqRange = None
			for dagNode in self.dag.nodeGroupDict[groupName]:
				for output in dagNode.outputs():
					if not seqRange and output.getSeqRange():
						seqRange = (int(output.getSeqRange()[0]), int(output.getSeqRange()[1]))
					else:
						if seqRange != (int(output.getSeqRange()[0]), int(output.getSeqRange()[1])):
							raise RuntimeError("Sequence ranges in group '%s' do not match.  Detection occurred on node '%s'." % (groupName, dagNode.name))
		
		# Insure no node is in two groups at once
		for dagNode in dagNodes:
			if self.dag.nodeGroupCount(dagNode) > 1:
				raise RuntimeError("Node '%s' is present in multiple groups." % (dagNode.name))


	def dagExecuteNode(self, dagNode):
		"""Evaluate the given node in the graph"""
        # TODO: 'Publish': this is where most changes must still occur. Since here the behaviour differs a lot from
        #       'Depends'. We should somehow create a Context that passes on to the nodes in the graph (and keep in
        #       account the branching that can occur in the graph!)

		# Convert this ordered list into an execution recipe and give it to a plugin that knows what to do with it.
		orderedDependencies = self.dag.orderedNodeDependenciesAt(dagNode)
		try:
			self.dagNodesSanityCheck(orderedDependencies)
		except Exception, err:
			print err
			print "Aborting Dag execution."
			return

		# TODO: 'Publish' - We likely don't need to store in an execution list first, but can directly traverse the
        #       graph while executing each node as we pass it and pass on the data/outputs required.
        #       For now I have commented out all lines corresponding with 'executionList'
		#executionList = list()
		for dagNode in orderedDependencies:
			# A dictionary with key=input & data=datapacket
			dataPacketDict = dict(self.dag.nodeOrderedDataPackets(dagNode))
			
			# Pre-execution hook
			preCommandList = dagNode.preProcess()
			#if preCommandList:
			#	executionList.append((dagNode.name + " [Pre-execution]", preCommandList))

			# Command execution
			commandList = dagNode.execute()
			#executionList.append((dagNode.name, commandList))
			
			# Post-execution hook
			postCommandList = dagNode.postProcess()
			#if postCommandList:
			#	executionList.append((dagNode.name + " [Post-execution]", postCommandList))
		

	###########################################################################
	## Menu operations
	###########################################################################
	def open(self, filename):
		"""
		Loads a snapshot, in the form of a json, file off disk and applies the
		values it pulls to the currently active dependency graph.  Cleans up
		the UI accordingly.
		"""
		if not os.path.exists(filename):
			return False
		
		# Load the snapshot off disk
		with open(filename, 'rb') as fp:
		    snapshot = json.loads(fp.read())
			
		# Apply the data to the in-flight Dag
		self.dag.restoreSnapshot(snapshot["DAG"])

		# Initialize the objects inside the graphWidget & restore the scene
		self.graphicsScene.restoreSnapshot(snapshot["DAG"])

		# Tell the sceneGraphWidget about the new groups
		for key in self.dag.nodeGroupDict:
			self.graphicsScene.addExistingGroupBox(key, self.dag.nodeGroupDict[key])

		# Variable substitutions
		self.clearVariableDictionary()
		for v in snapshot["DAG"]["VARIABLE_SUBSTITIONS"]:
			variables.variableSubstitutions[v["NAME"]] = (v["VALUE"], False)

		# The current session gets a variable representing the location of the current workflow
		if 'WORKFLOW_DIR' not in variables.names():
			variables.add('WORKFLOW_DIR')
		variables.setx('WORKFLOW_DIR', os.path.dirname(filename), readOnly=True)

		# Additional meta-data loading
		if "RELOAD_PLUGINS_FILENAME_TEMP" in snapshot:
			filename = snapshot["RELOAD_PLUGINS_FILENAME_TEMP"]

		# UI tidies
		self.undoStack.clear()
		self.undoStack.setClean()
		self.workingFilename = filename
		self.setWindowTitle("Depends (%s)" % self.workingFilename)
		self.variableWidget.rebuild(variables.variableSubstitutions)
		return True

		
	def openDialog(self):
		"""
		Pops open a file dialog, recovers a filename from it, and calls self.open()
		on the results.
		"""
		# TODO: This code is used twice almost identically.  Can it go into yesNoDialog?
		if not self.undoStack.isClean():
			if self.yesNoDialog("Current workflow is not saved.  Save it before opening?"):
				if self.workingFilename:
					self.save(self.workingFilename)
				else:
					self.saveAs()
		filename, throwaway = QtGui.QFileDialog.getOpenFileName(self, caption='Open Workflow', filter="Workflow files (*.json)")
		if not filename:
			return
		self.open(filename)
		
	
	def save(self, filename, additionalFileDictionary=None):
		"""
		Functionality for writing snapshots of the software's running state
		to a json file.  Modifies the UI accordingly.
		"""
		if not filename:
			return

		# Create a nested meta dict for saving node locations
		nodeMetaDict = self.graphicsScene.nodeMetaDict()

		# Create a nested meta dict for saving connection offsets
		connectionMetaDict = self.graphicsScene.connectionMetaDict()

		# Store all but read-only variables to the state
		varDicts = variables.changeableList()

		# TODO: A generic way to pass additional dicts into the snapshot function might be good.
		#       The parameter list is getting long and specific!  (also, variableList->variableDict)
		#       Or maybe we should just merge it all right here?
		# Concoct a full snapshot from the current DAG and additional information fed into the function
		snapshot = self.dag.snapshot(nodeMetaDict=nodeMetaDict, connectionMetaDict=connectionMetaDict, variableMetaList=varDicts)
		fullSnap = {"DAG":snapshot}
		if additionalFileDictionary:
			fullSnap = dict({"DAG":snapshot}.items() + additionalFileDictionary.items())

		# Serialize to disk
		fp = open(filename, 'wb')
		fp.write(json.dumps(fullSnap, sort_keys=True, indent=4))
		fp.close()
		
		# UI tidies
		self.undoStack.setClean()
		self.workingFilename = filename
		self.setWindowTitle("Depends (%s)" % self.workingFilename)
		
		
	def saveAs(self):
		"""
		Save the DAG to a filename pulled out of a file dialog.
		"""
		currentDir = os.path.dirname(self.workingFilename)
		filename, throwaway = QtGui.QFileDialog.getSaveFileName(self, caption='Save Workflow As', filter="Workflow files (*.json)", dir=currentDir)
		if not filename:
			return
		self.save(filename)


	def saveVersionUp(self):
		"""
		Save the next version of the current file.
		"""
		nextVersionFilename = util.nextFilenameVersion(self.workingFilename)
		self.save(nextVersionFilename)
		

	def yesNoDialog(self, text):
		"""
		A simple yes/no dialog box.
		"""
		reply = QtGui.QMessageBox.question(self, "Notice", text, QtGui.QMessageBox.Yes|QtGui.QMessageBox.No)
		if (reply == QtGui.QMessageBox.Yes):
			return True
		return False


	def reloadPlugins(self):
		"""
		This menu item reloads all the plugin files off disk by restarting 
		depends in-place.  If the current workflow has been modified, save 
		a temporary copy and reload it on startup.
		"""
		self.saveSettings()
		args = QtGui.qApp.arguments()
		if not self.undoStack.isClean():
			(osJunk, filename) = tempfile.mkstemp(prefix="dependsreload_", suffix=".json")
	
			metaDict = {"RELOAD_PLUGINS_FILENAME_TEMP":self.workingFilename}
			self.save(filename, metaDict)
	
			filenameIndexMinusOne = args.index('-workflow')
			args[filenameIndexMinusOne+1] = filename
		util.restartProgram(args)
		
	
	def executeSelected(self, executeImmediately=False):
		"""
		Execute the selected node using self.dagExecuteNode().
		"""
		selectedDagNodes = self.selectedDagNodes()
		if len(selectedDagNodes) > 1 or not selectedDagNodes:
			# TODO: Status bar
			return
		self.dagExecuteNode(selectedDagNodes[0])


	def deleteSelectedNodes(self):
		"""
		Delete selected nodes using self.delete_nodes().
		"""
		dagNodesToDelete = self.selectedDagNodes()
		if not dagNodesToDelete:
			return
		self.delete_nodes(dagNodesToDelete)


	def shakeSelectedNodes(self):
		"""
		"Shake" selected nodes from the dag using self.shakeNodes().
		"""
		dagNodesToShake = self.selectedDagNodes()
		if not dagNodesToShake:
			return
		self.shakeNodes(dagNodesToShake)


	def duplicateSelectedNodes(self):
		"""
		Duplicate selected nodes using self.duplicateNodes().
		"""
		dagNodesToDupe = self.selectedDagNodes()
		if not dagNodesToDupe:
			return
		self.duplicateNodes(dagNodesToDupe)


	def groupSelectedNodes(self):
		"""
		Group selected nodes into an execution collection.
		"""
		selDagNodes = self.selectedDagNodes()
		for dagNode in selDagNodes:
			if self.dag.nodeGroupCount(dagNode) > 0:
				raise RuntimeError("Nodes cannot currently be in more than one group.")
		groupName = util.generateUniqueNameSimiarToExisting('group', self.dag.nodeGroupDict.keys())
		self.dag.addNodeGroup(groupName, selDagNodes)
		self.graphicsScene.addExistingGroupBox(groupName, selDagNodes)


	def ungroupSelectedNodes(self):
		"""
		If all selected nodes are in a group together, remove their node group
		from the in-flight dependency graph.
		"""
		selDagNodes = self.selectedDagNodes()
		groupNameInDag = self.dag.nodeGroupName(selDagNodes)
		if not groupNameInDag:
			return
		self.graphicsScene.removeExistingGroupBox(groupNameInDag)
		self.dag.removeNodeGroup(nodeListToRemove=selDagNodes)
		

	def versionUpSelectedOutputFilenames(self):
		"""
		Version up the output filenames for each of the selected nodes using
		self.versionUpOutputFilenames().
		"""
		dagNodesToVersionUp = self.selectedDagNodes()
		if not dagNodesToVersionUp:
			return
		self.versionUpOutputFilenames(dagNodesToVersionUp)


	def createNodeFromMenuStub(self):
		"""
		Create a new node from scratch.  The stub funciton is theoretically 
		temporary until I can figure out how to make a deep copy of a type.
		"""
		nodeType = self.sender().data()[0]
		# No nodelocation is supplied for actions that come from the menu, so compute now and apply.
		nodeLocation = self.sender().data()[1]
		if nodeLocation is None:
			nodeLocation = self.graphicsViewWidget.centerCoordinates()
		self.create_node(nodeType, nodeLocation)


	def createCreateMenuActions(self):
		"""
		Creates all the menu commands that create nodes from all the dag node
		types present in the current session.
		"""
		actionList = list()
		for tipe in node.dagNodeTypes():
			menuAction = QtGui.QAction(tipe().typeStr(), self, triggered=self.createNodeFromMenuStub)
			menuAction.setData((tipe, None))
			actionList.append(menuAction)
		return actionList
		
	
	def testMenuItem(self):
		"""
		You can do whatever you want in here!
		"""
		#selectedDrawNodes = self.graphicsScene.selectedItems()
		#if len(selectedDrawNodes) > 1 or not selectedDrawNodes:
		#	return
		#an = self.dag.allNodesDependingOnNode(selectedDrawNodes[0].dagNode, recursion=False)
		#an = self.dag.allNodesAfter(selectedDrawNodes[0].dagNode)
		#an = self.dag.nodeOutputGoesTo(selectedDrawNodes[0].dagNode, selectedDrawNodes[0].dagNode.outputs()[0])
		#for n in an:
		#	print n
		#	#print n[1].name
		#self.save('/tmp/foo.json')
		#self.open('/tmp/foo.json')
		#self.yesNoDialog("FOOBar")
		
		#print util.nextFilenameVersion('/tmp/foo.bar.000.tif')
		#print util.nextFilenameVersion('/tmp/foobar_v001.tif')
		#print util.nextFilenameVersion('/tmp/foo.bar.001')		# "Fails" - but what does one expect?
		#print util.nextFilenameVersion('/tmp/foobar001')
		#print util.nextFilenameVersion('foo.bar.001.tif')
		#print util.nextFilenameVersion('foobar001')
		#print util.nextFilenameVersion('/tmp/foobar_v015.tif')
		#print util.nextFilenameVersion('/home/gardner/devDag/june01.json')
		#print util.nextFilenameVersion("/tmp/foo.####.tif")
		#print util.nextFilenameVersion("/tmp/foo005.####.tif")
		#print util.nextFilenameVersion("/tmp/foo####.tif")
		#print util.nextFilenameVersion("/tmp/foov002_####.tif")
		#print util.nextFilenameVersion("/tmp/foo.bar####.tif")
		#print util.nextFilenameVersion("/tmp/foo.003.####.tif")
		#print util.nextFilenameVersion("/tmp/foo.003.####.####.tif")
		
		#print variables.present('/$FOO/$HI/BOOBER/$$SRC_ROOT.$FOO')
		#selectedDrawNodes = self.graphicsScene.selectedItems()
		#if selectedDrawNodes:
		#	executeNode = selectedDrawNodes[0].dagNode
		#util.dagSnapshotDiff(self.undoStack.command(0).oldSnap, self.undoStack.command(0).newSnap)

		#self.dag.addNodeGroup([self.dag.node(name="Image_Transform"), 
		#					   self.dag.node(name="Image_Transform_Dupe")])
		#print self.dag.nodeGroupList
		
		#print self.dag.nodeInGroupNamed(self.selectedDagNodes()[0])

		print self.dagNodeVariablesUsed(self.selectedDagNodes()[0])
