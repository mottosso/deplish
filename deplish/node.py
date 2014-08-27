#
# Depends
# Copyright (C) 2014 by Andrew Gardner & Jonas Unger.  All rights reserved.
# BSD license (LICENSE.txt for details).
#

import re
import copy
import uuid

import util
import variables
import data_packet


"""
A class defining a node in a workflow's dependency graph.  Each node contains
properties (inputs, outputs, and attributes), and the classes representing 
each are also defined here.  Related utility functions are also present, as 
well as functionality to automatically create read nodes for each registered
data type.  Finally, a collection of "built in" nodes are defined.

Defining one's own nodes consists of inheriting from the DagNode class and
overloading a series of functions that define the node's properties.  Each
inherited node should be as atomic as possible, performing one operation well.
"""


###############################################################################
## Utility
###############################################################################
def dagNodeTypes():
    """
    Return a list of node types presently loaded.
    """
    return DagNode.__subclasses__()


def cleanNodeName(name):
    """
    Return a cleaned version of a string, suitable for naming a node.
    Basically removes anything but alphanumeric characters and dots.
    """
    return re.sub(r'[^a-zA-Z0-9\n\.]', '_', name)    


###############################################################################
###############################################################################
class DagNodeAttribute(object):
    """
    An attribute property of a DagNode.  These contain a name, default value,
    a doc string, a potential custom file dialog specifier, and a flag stating
    if it's a file type or not.  The data is stored as a string, so whatever
    the user needs can be placed in here.
    """
    
    def __init__(self, name, defaultValue, isFileType=False, docString=None, customFileDialogName=None):
        """
        """
        self.name = name
        self.value = defaultValue
        self.seqRange = None
        self.docString = docString
        self.customFileDialogName = customFileDialogName

        # TODO: Implement usage of attribute as input and/or output (connect in graph)
        self.input = False
        self.output = False

        # Constants, not written to disk
        self.isFileType = isFileType


    # TODO: Should my dictionary keys be more interesting?
    def __hash__(self):
        return hash(self.name)
    def __eq__(self, other):
        return (self.name) == (other.name)


###############################################################################
## Base class
###############################################################################
class DagNode(object):
    """
    The base class from which all dependency graph nodes are created.  This
    class contains a custom dictionary to store its properties (inputs, 
    outputs, and attributes), a UUID insuring nodes do not get confused with
    eachother, and a name.  A series of property accessors exists, as well as 
    some general functionality.  When creating a new node, please refer to
    the section labeled "Children must inherit these" and "Children may 
    inherit these" as overloading these functions are how nodes distinguish
    themselves.
    """

    def __init__(self, name="", nUUID=None):
        """
        """
        self.set_name(name)
        self._properties = dict()
        self.uuid = nUUID if nUUID else uuid.uuid4()
        
        # Give the inputs, outputs, and attributes a place to live in the storage dict
        for input in self._defineInputs():
            self._properties[self._inputNameInPropertyDict(input.name)] = input
        for output in self._defineOutputs():
            self._properties[self._outputNameInPropertyDict(output.name)] = output
        for attribute in self._defineAttributes():
            self._properties[attribute.name] = attribute
            

    def __str__(self):
        """
        For printing.
        """
        return "DagNode - name:%s  type:%s  uuid:%s" % (self.name, type(self).__name__, str(self.uuid))


    def __lt__(self, other):
        """
        For sorting.
        """
        return self.name < other.name
    

    def __eq__(self, other):
        """
        The UUIDs are the basis for equivalence.
        """
        if isinstance(other, DagNode):
            return self.uuid == other.uuid
        return NotImplemented
    

    def __ne__(self, other):
        """
        Mirror of __eq__
        """
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result


    def __hash__(self):
        """
        For adding to dictionaries.
        """
        return hash(self.uuid)


    def _inputNameInPropertyDict(self, inputName):
        """
        The property dict stores inputs with an interesting key.  Compute it.
        """
        INPUT_ATTR_PREFIX = "INPUT"
        return INPUT_ATTR_PREFIX+"@"+inputName


    def _outputNameInPropertyDict(self, outputName):
        """
        The property dict stores outputs with an interesting key.  Compute it.
        """
        OUTPUT_ATTR_PREFIX = "OUTPUT"
        return OUTPUT_ATTR_PREFIX+"@"+outputName


    ###########################################################################
    ## Input functions
    ###########################################################################
    def inputs(self):
        """
            Return a list of all attributes that behave as outputs
        """
        return [attr for attr in self.attributes() if attr.input]

    def in_connections(self, connections=True):
        """
        Return a list of all input objects.
        """
        result = []
        for attr in self.input_attrs():
            connected = attr.input()
            if not connected:
                continue

            if connections:
                result.append((attr, connected))
            else:
                result.append(connected)

        return result

    
    ###########################################################################
    ## Output functions
    ###########################################################################
    def outputs(self):
        """
            Return a list of all attributes that behave as outputs
        """
        return [attr for attr in self.attributes() if attr.output]

    def out_connections(self, connections=True):
        """
        Return a list of all connected outputs.

        If connections is True return both the output attribute and it's connection else only return the connected
        attribute.

        """
        result = []
        for attr in self.output_attrs():
            connected = attr.output()
            if not connected:
                continue

            if connections:
                result.append((attr, connected))
            else:
                result.append(connected)

        return result


    ###########################################################################
    ## Attribute functions
    ###########################################################################
    def attributes(self):
        """
        Return a list of all attribute objects.
        """
        attributeList = list()
        for x in self._properties:
            if type(self._properties[x]) is DagNodeAttribute:
                attributeList.append(self._properties[x])
        return attributeList


    def set_attribute_value(self, attrName, value):
        """
        Set an attribute named the given name to the given string.
        """
        self.attribute_named(attrName).value = value


    def set_attribute_range(self, attrName, newRange):
        """
        Set the range of an attribute named the given name to the given range
        tuple (string, string).
        """
        self.attribute_named(attrName).seqRange = newRange


    def attribute_named(self, attrName):
        """
        Return an attribute object for the given name.
        """
        if attrName not in self._properties:
            raise RuntimeError('Attribute %s does not exist in node %s.' % (attrName, self.name))
        return self._properties[attrName]


    def attribute_value(self, attrName, variableSubstitution=True):
        """
        Return a value string for the given attribute name.  Workflow variables
        are substituted by default.
        """
        value = self.attribute_named(attrName).value
        if variableSubstitution:
            value = variables.substitute(value)
        return value


    def attribute_range(self, attrName, variableSubstitution=True):
        """
        Return a range tuple (string, string) for the given attribute name.  
        Workflow variables are substituted by default.
        """
        seqRange = self.attribute_named(attrName).seqRange
        if variableSubstitution:
            seqRange = (variables.substitute(seqRange[0]), variables.substitute(seqRange[1]))
        return seqRange


    #def attributeFramespec(self, attrName):
    #    """
    #    """


    ###########################################################################
    ## General
    ###########################################################################
    def typeStr(self):
        """
        Returns a human readable type string with CamelCaps->spaces.
        """
        # TODO: MAKE EXPLICIT!
        return re.sub(r'(?!^)([A-Z]+)', r' \1', type(self).__name__[len('DagNode'):])
    
    
    def set_name(self, name):
        """
        Set the name value, converting all special characters (and spaces) into
        underscores.
        """
        processedName = cleanNodeName(name)
        self.name = processedName


    def duplicate(self, nameExtension):
        """
        Return a duplicate of this node, but insure the parameters that need to be
        different to co-exist in a DAG are different (name, uuid, etc)
        """
        dupe = type(self)(name=self.name+nameExtension)
        for attribute in self.attributes():
            dupe._properties[attribute.name] = copy.deepcopy(attribute)
        for output in self.outputs():
            fullOutputName = self._outputNameInPropertyDict(output.name)
            dupe._properties[fullOutputName] = copy.deepcopy(output)
        return dupe


    def input_requirements_fulfilled(self, dataPackets):
        """
        Determine if all the data necessary to run is present.
        """
        dpInputs = [x[0] for x in dataPackets]
        return set(self.inputs()).issubset(set(dpInputs))


    def scene_graph_handle(self, specializationDict=None):
        """
        Handle this node in the context of the dependency engine scene graph.
        If the output is specialized to an inherited type, pass a dictionary
        in containing the specializations.  Currently multiple outputs exist
        for each node, so return a list of all data packets generated by this
        node.
        """
        # TODO: This loops over all outputs and works now because only a single
        #       output exists (see usages in dag.py).  This may be inadvisable.
        
        # (specialization is a dict keying off outputName, containing outputType)
        dpList = list()
        for output in self.outputs():
            outputType = output.dataPacketType
            # If a specializationDict has been supplied, use the given type
            if specializationDict and output.name in specializationDict:
                outputType = specializationDict[output.name]
            # Create the new datapacket and populate its attributes.
            newDataPacket = outputType(self, output.name)
            for fdName in newDataPacket.filenames:
                newDataPacket.setFilename(fdName, self.outputValue(output.name, fdName))
                # TODO: This happens multiple times right now.  Once the UI is fixed, it won't
                newDataPacket.setSequenceRange(self.outputRange(output.name, fdName))
            dpList.append(newDataPacket)
        return dpList
        

    ###########################################################################
    ## Children must inherit these
    ###########################################################################
    def _defineInputs(self):
        """
        Defines the list of input objects for the node.
        """
        print "Empty Define Inputs function called in parent 'DagNode' class."
        return list()
    
    
    def _defineOutputs(self):
        """
        Defines the list of output objects for the node.
        """
        print "Empty Define Outputs function called in parent 'DagNode' class."
        return list()
    
    
    def _defineAttributes(self):
        """
        Defines the list of attribute objects for the node.
        """
        print "Empty Define Attributes function called in parent 'DagNode' class."
        return list()
    
    
    def executeList(self):
        """
        Given a dict of input dataPackets, return a list of commandline arguments
        that are easily digested by an execution recipe.
        The splitOperations parameter is passed to nodes that are embarrassingly parallel.
        Nodes that execute with their operations split should return a list of
        lists of commandline arguments that basically run entire frame sequences
        as separate commands.
        """
        print "Empty Execute function in parent 'DagNode' class."
        return list()


    ###########################################################################
    ## Children may inherit these
    ###########################################################################
    def preProcess(self):
        """
        This runs *before* the executeList function is executed.
        Given a dict of input dataPackets (often times not used), create a list
        of commandline arguments that can be run by the subprocess module.
        """
        return list()


    def postProcess(self):
        """
        This runs *after* the executeList function is executed.
        Given a dict of input dataPackets (often times not used), create a list
        of commandline arguments that can be run by the subprocess module.
        """
        return list()


    def validate(self):
        """
        Each node is capable of setting their own validation routines that can
        do whatever the user wants, from verifying input parameters fall within
        a range to insuring files exist on disk.  Raising a runtime error is
        the preferred method of erroring out, but returning False is also a
        valid alarm.
        """
        return True


############ FUNCTION TO IMPORT PLUGIN NODES INTO THIS NAMESPACE  #############
def loadChildNodesFromPaths(pathList):
    """
    Given a list of directories, import all classes that reside in modules in those
    directories into the node namespace.
    """
    for path in pathList:
        nodeClassDict = util.allClassesOfInheritedTypeFromDir(path, DagNode)
        for nc in nodeClassDict:
            globals()[nc] = nodeClassDict[nc]

class DagNodeInput(object):
    """
    An input property of a DagNode.  Contains the datapacket type is accepts,
    a flag denoting if it's required or not, a name, and documentation.
    """

    def __init__(self, name, dataPacketType, required, docString=None):
        """
        """
        self.name = name
        self.value = ""
        self.seqRange = None
        self.docString = docString
        
        # Constants, not written to disk
        self.dataPacketType = dataPacketType
        self.required = required
    
    
    def allPossibleInputTypes(self):
        """
        Return a list of all possible DataPacket types this input accepts.
        This is interesting because inputs can accept DataPakcets of a type
        that is inherited from its base type.
        """
        inputTypeList = set([self.dataPacketType])
        inputTypeList |= set(util.allClassChildren(self.dataPacketType))
        return inputTypeList
        

    # TODO: Should my dictionary keys be more interesting?
    def __hash__(self):
        return hash(self.name)
    def __eq__(self, other):
        return (self.name) == (other.name)


class DagNodeOutput(object):
    """
    An output property of a DagNode.  Contains its data packet type, a doc
    string, a name, and potentially a string containing a custom file dialog
    that pops open when a button is pressed.  Each sub-output in a given output
    must contain the exact number of files as the rest of the sub-outputs, thus
    a single sequence range is present for an entire output.
    """
    
    def __init__(self, name, dataPacketType, docString=None, customFileDialogName=None):
        """
        """
        self.name = name
        self.value = dict()
        self.seqRange = None
        self.docString = docString
        self.customFileDialogName = customFileDialogName

        # Constants, not written to disk
        self.dataPacketType = dataPacketType

        # Note: We add the largest possible set of attributes this node can have from 
        #       its datapacket and all the datapacket's children types
        allPossibleFileDescriptorNames = set()
        for tipe in self.allPossibleOutputTypes():
            for fdName in data_packet.filenameDictForDataPacketType(tipe):
                allPossibleFileDescriptorNames.add(fdName)
        for fdName in allPossibleFileDescriptorNames:
            self.value[fdName] = ""
            self.seqRange = None


    def allPossibleOutputTypes(self):
        """
        Returns a list of all type data packet types this node can output.
        """
        outputTypeList = set([self.dataPacketType])
        outputTypeList |= set(util.allClassChildren(self.dataPacketType))
        return outputTypeList


    def subOutputNames(self):
        """
        Return a list of the names of each of this output's data packet sub-types.
        """
        subList = list()
        for subName in self.value:
            subList.append(subName)
        return subList


    def getSeqRange(self):
        """
        Gets the single sequence range for this output.
        """
        if not self.seqRange:
            return None
        if self.seqRange[0] is None or self.seqRange[1] is None:
            return None
        if self.seqRange[0] == "" or self.seqRange[1] == "":
            return None
        return self.seqRange
        

    # TODO: Should my dictionary keys be more interesting?
    def __hash__(self):
        return hash(self.name)
    def __eq__(self, other):
        return (self.name) == (other.name)
