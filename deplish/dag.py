#
# Depends
# Copyright (C) 2014 by Andrew Gardner & Jonas Unger.  All rights reserved.
# BSD license (LICENSE.txt for details).
#

"""Directed Acyclic graph

This module contains a class defining a directed acyclic dependency graph for
the Depends workflow manager.  A series of DagNode objects are connected 
together using a networkx DiGraph.  Functionality relating to the nodes and
their relation to eachother is provided as well as scenegraph generation, node
relation, and snapshot generation.

"""

import re
import uuid
import copy

import networkx

import node
import util
import data_packet


class DAG(object):
    """Container of DiGraph and DagNode

    The primary dependency graph containing a networkx DiGraph of DagNode 
    objects connected to eachother.  Also keeps track of which nodes are
    members of various node groups.

    """

    def __init__(self):
        # The dependency graph
        self.network = networkx.DiGraph()
        
        # A list of node group sets
        self.nodeGroupDict = dict()


    def node(self, name=None, nUUID=None):
        """Return a node with the given name or UUID"""
        for dagNode in self.network:
            if name and dagNode.name == name:
                return dagNode
            if nUUID and dagNode.uuid == nUUID:
                return dagNode
        return None


    def nodes(self, nodeType=None):
        """Return a list of all nodes

        Or nodes of a certain type, or nodes that have 
        names that match a regex pattern.

        """

        returnList = list()
        for dagNode in self.network:
            if not nodeType:
                returnList.append(dagNode)
            elif dagNode is nodeType:
                returnList.append(dagNode)
        return returnList


    def connections(self):
        """Return a list of all edges in the DAG."""
        return self.network.edges()
    

    def nodeConnectionsIn(self, dagNode):
        """
        Return a list of all the edges going 'in' to a node.
        Note: Our definition of in and out is flipped from the DAG definition.
        """
        return [edge[1] for edge in self.network.out_edges(dagNode)]


    def nodeConnectionsOut(self, dagNode):
        """
        Return a list of all the edges leaving a node.
        Note: Our definition of in and out is flipped from the DAG definition.
        """
        return [edge[0] for edge in self.network.in_edges(dagNode)]

    
    def add_node(self, dagNode):
        """Adds a node to the DAG."""
        if self.node(dagNode.name):
            raise RuntimeError('Cannot add node named %s, as it already exists.' % dagNode.name)
        self.network.add_node(dagNode)


    def remove_node(self, dagNode=None, name=None):
        """Remove a node from the DAG."""
        if not dagNode:
            dagNode = self.node(name=name)
        self.network.remove_node(dagNode)


    def connect_nodes(self, startNode, endNode):
        """
        Attempts to connect two nodes in the DAG.  Raises an exeption if
        there is an issue.
        """
        if startNode not in self.network:
            raise RuntimeError('Node %s does not exist in DAG.' % startNode.name)
        if endNode not in self.network:
            raise RuntimeError('Node %s does not exist in DAG.' % endNode.name)
        if startNode in self.nodeConnectionsIn(endNode):
            raise RuntimeError("Attempting to duplicate outgoing connection.")
        self.network.add_edge(endNode, startNode)
        if not networkx.is_directed_acyclic_graph(self.network):
            raise RuntimeError('The directed graph is nolonger acyclic!')


    def disconnect_nodes(self, startNode, endNode):
        """
        Attempts to disconnect two nodes in the DAG.  Raises an exception if 
        there is an issue.
        """
        if startNode not in self.network:
            raise RuntimeError('Node %s does not exist in DAG.' % startNode.name)            
        if endNode not in self.network:
            raise RuntimeError('Node %s does not exist in DAG.' % endNode.name)
        self.network.remove_edge(endNode, startNode)
    

    ###########################################################################
    ## Graph Execution/Evaluation
    ###########################################################################
    def buildSceneGraph(self, atNode):
        """
        Evaluate the DAG in a postorder fashion to create a list of the data
        packets in the scene graph sorted by execution order.
        """
        dagPathList = list()
        nodeEvalOrder = networkx.dfs_postorder_nodes(self.network, atNode)
        for dagNode in nodeEvalOrder:
            # Retrieve specialized output types
            specializationDict = dict()
            #for output in dagNode.outputs():
            #    specializationDict[output.name] = self.nodeOutputType(dagNode, output)
            dagPathList.extend(dagNode.scene_graph_handle(specializationDict))
        return dagPathList


    def execute_node(self, node, contexts=None):
        """ Executes a single node with the given list of contexts  """
        print 'EXECUTING NODE::', node.name

        node.preProcess()
        data = node.execute()
        node.postProcess()

        return data


    def execute_up_to_node(self, node):
        """
            Execute everything required for and up to the given node and not beyond.
        """
        node_eval_order = networkx.dfs_postorder_nodes(self.network, node)
        self.execute_graph(node_eval=node_eval_order)


    def execute_graph(self, node_eval=None):
        """
            Executes the full graph in order or the nodes given by `node_eval` in the order of the input.

            Note: it is recommended to ensure `node_eval` is topologically sorted (in reverse).
        """
        # Get dag processing order
        if node_eval is None:
            node_eval = networkx.dfs_postorder_nodes(self.network)

        # TODO: Wherever the graph starts a new empty Context must be created (or possibly predefined?)
        # TODO: When graph branches a copy must be made of the Context so each branch operates on its own Context.
        # Execute each node
        for node in node_eval:
            self.execute_node(node)


    def nodeOrderedDataPackets(self, dagNode, onlyUnfulfilled=False, onlyFulfilled=False):
        """
        Given a node, return which datapackets are povided to it, filtered by some flags.
        Returns a list of tuples containing (Input, DataPacket).
        """
        validDataPackets = list()
        orderedDataPackets = self.buildSceneGraph(dagNode)
        scenegraphInputAndConnectedNode = [(i, self.nodeInputComesFromNode(dagNode, i)[0]) for i in dagNode.inputs()]

        # Loop over the data packets in order, picking out the input associated with it (TODO: functionize)
        for dataPacket in orderedDataPackets:
            if dataPacket.sourceNode is dagNode:
                continue
            if dataPacket.sourceNode not in [i[1] for i in scenegraphInputAndConnectedNode]:
                continue
            if onlyFulfilled and not dataPacket.dataPresent():
                continue
            if onlyUnfulfilled and dataPacket.dataPresent():
                continue
            
            # Recover the input that matches the current datapacket
            input = None
            for i in scenegraphInputAndConnectedNode:
                if i[1] == dataPacket.sourceNode:
                    input = i[0]
            
            validDataPackets.append((input, dataPacket))
        return validDataPackets


    def orderedNodeDependenciesAt(self, dagNode, includeGivenNode=True, onlyUnfulfilled=True, recursion=True):
        """
        Builds the evaluation order tree at the given node.
        Checks all requirements on each node (using the per-node input filters).
        """
        # Get a list of data packets *this* node needs that aren't already on disk.
        requiredDataPackets = [x[1] for x in self.nodeOrderedDataPackets(dagNode, onlyUnfulfilled=onlyUnfulfilled)]

        # If there are any unfulfilled datapackets in the chain, their owning
        # node must be executed, but it's possible they have dependencies not
        # yet covered in the lists collected so far.  Add these dependencies
        # in their proper locations.
        #
        # Append missing dependencies' required datapackets, maintaining execution order
        # This is effectively recursion in a while loop.
        i = 0
        while i < len(requiredDataPackets):
            packet = requiredDataPackets[i]
            packetRdp = [x[1] for x in self.nodeOrderedDataPackets(packet.sourceNode, onlyUnfulfilled=onlyUnfulfilled)]
            for p in packetRdp:
                if p.sourceNode in [dp.sourceNode for dp in requiredDataPackets]:
                    continue
                if recursion:
                    requiredDataPackets.append(p)
            i += 1  
        
        # Return a list of in-order nodes, including the given node.
        inOrderNodes = list()
        for dp in reversed(requiredDataPackets):
            inOrderNodes.append(dp.sourceNode)
        if includeGivenNode:
            inOrderNodes.append(dagNode)
        return inOrderNodes


    def all_nodes_before(self, dagNode):
        """
        Return a list of all nodes "before" the given node in the DAG.
        Effectively a list of nodes this node can use as input.
        """
        return list(networkx.descendants(self.network, dagNode))
    

    def all_nodes_after(self, dagNode):
        """
        Return a list of all nodes "after" the given node in the DAG.
        Effectively a list of nodes that might rely on this node for input.
        """
        return list(networkx.ancestors(self.network, dagNode))


    def all_nodes_depending_on_node(self, dependingOnNode, recursion=True):
        """
        This returns a list of all nodes recursively downstream that rely on the given node's
        output.  Can be nicely used to set a "dirty" flag on downstream nodes.
        """
        # All the nodes that rely on this node, indirectly or directly
        directlyNeedyNodeList = list()
        for dagNode in self.all_nodes_after(dependingOnNode):
            depends = self.orderedNodeDependenciesAt(dagNode, includeGivenNode=False, onlyUnfulfilled=False, recursion=recursion)
            if dependingOnNode in depends:
                directlyNeedyNodeList.append(dagNode)
        return directlyNeedyNodeList
        

    def nodeOutputType(self, dagNode, output):
        """
        Nodes can output different inherited data packet types based on their inputs
        and parameters.  This function reports exactly which data packet type is coming
        out of a given node.
        """
        # If your output has only one potential type, you've gotta' be what you are.
        if len(output.allPossibleOutputTypes()) == 1:
            return output.dataPacketType
        
        # Which input is associated with this output?
        input = dagNode.inputAffectingOutput(output)
        if not input:
            return output.dataPacketType
        
        # Return the type of the found input since the output is going to match.
        (inputNode, inputNodeOutput) = self.nodeInputComesFromNode(dagNode, input)
        if not inputNode:
            return output.dataPacketType
        return self.nodeOutputType(inputNode, inputNodeOutput)
        

    def nodeInputComesFromNode(self, dagNode, input):
        """
        Given a node and one of its inputs, return a tuple containing which 
        dagNode and which of its outputs is connected to the input.
        """
        inputString = dagNode.inputValue(input.name)
        (connectedNode, connectedNodeOutput) = data_packet.nodeAndOutputFromScenegraphLocationString(inputString, self)
        return (connectedNode, connectedNodeOutput)
    
    
    def nodeOutputGoesTo(self, dagNode, output):
        """
        Given a node and one of its outputs, return a list of tuples containing
        which dagNode and corresponding input is connected to the output.
        """
        connectedTuples = list()
        dependentNodes = self.all_nodes_depending_on_node(dagNode, recursion=False)
        for dNode in dependentNodes:
            for input in dNode.inputs():
                (outNode, nodeOutput) = self.nodeInputComesFromNode(dNode, input)
                if nodeOutput is output:
                    connectedTuples.append((dNode, input))
                    continue
        return connectedTuples


    def nodeInputDataPacket(self, dagNode, input):
        """
        Given a node and its input, return the datapacket that is coming in.
        """
        (outputNode, output) = self.nodeInputComesFromNode(dagNode, input)
        return self.nodeOutputDataPacket(outputNode, output)
    
    
    def nodeOutputDataPacket(self, dagNode, output):
        """
        Given a node and its output, return the DataPacket coming out of it.
        """
        if dagNode is None:
            return None
        
        # Retrieve specialized output types
        specializationDict = dict()
        for output in dagNode.outputs():
            specializationDict[output.name] = self.nodeOutputType(dagNode, output)
        # TODO: scene_graph_handle should not return an array - it should take a single output.
        return dagNode.scene_graph_handle(specializationDict)[0]


    ###########################################################################
    ## Helpers
    ###########################################################################
    def nodeAllInputsConnected(self, dagNode):
        """
        Returns a boolean stating whether this node has all of its required inputs connected.
        """
        foo = self.nodeOrderedDataPackets(dagNode)
        return dagNode.input_requirements_fulfilled(foo)
    
    
    def safeNodeName(self, nodeName):
        """
        Given a node name suggestion, returns a safe version of it that will work in this DAG.
        """
        localName = nodeName
        while self.node(name=localName):
            prefix = ""
            version = "0"
            if not localName[-1].isdigit():
                localName = localName + '1'
                continue
            prefix, version = re.match(r"(.*[^\d]+)([\d]+)$", localName).groups()
            localName = prefix + str(int(version)+1).rjust(len(version), '0')
        return localName


    ###########################################################################
    ## Group machinations
    ###########################################################################
    def addNodeGroup(self, name, nodeListToGroup):
        """
        Create a new node group with the given name, containing the given list
        of nodes.
        """
        if set(nodeListToGroup) in self.nodeGroupDict.values():
            raise RuntimeError("NodeGroup", nodeListToGroup, "already present in DAG group dict.")
        if name in self.nodeGroupDict:
            raise RuntimeError("NodeGroup named %s already exists in DAG group dict." % name)
        self.nodeGroupDict[name] = set(nodeListToGroup)
    
    
    def removeNodeGroup(self, nameToRemove=None, nodeListToRemove=None):
        """
        Remove an entire node group specified by either its name or the list of
        nodes potentially contained within.
        """
        if nameToRemove:
            if nameToRemove not in self.nodeGroupDict:
                raise RuntimeError("NodeGroup", nameToRemove, "not present in DAG group dict.")
            del self.nodeGroupDict[nameToRemove]
        elif nodeListToRemove:
            nodeSetToRemove = set(nodeListToRemove)
            if nodeSetToRemove not in self.nodeGroupDict.values():
                raise RuntimeError("NodeGroup", nodeListToRemove, "not present in DAG group dict.")
            for key in self.nodeGroupDict:
                if self.nodeGroupDict[key] == nodeSetToRemove:
                    del self.nodeGroupDict[key]
                    break
        

    def nodeGroupName(self, nodeListToQuery):
        """
        Given a list of nodes, return which group (if any) they represent.
        """
        nodeSetToQuery = set(nodeListToQuery)
        if nodeSetToQuery not in self.nodeGroupDict.values():
            return None
        for key in self.nodeGroupDict:
            if self.nodeGroupDict[key] == nodeSetToQuery:
                return key
        
    
    def nodeGroupCount(self, dagNode):
        """
        Returns whether the given node is a member of any group in the DAG.
        """
        groupCount = 0
        for group in self.nodeGroupDict.values():
            if dagNode in group:
                groupCount += 1
        return groupCount


    def nodeInGroupNamed(self, dagNode):
        """
        Returns which group name a given dag node resides in (if any).
        """
        for key in self.nodeGroupDict:
            if dagNode in self.nodeGroupDict[key]:
                return key
        return None


    ###########################################################################
    ## LOAD / SAVE
    ###########################################################################
    def snapshot(self, nodeMetaDict=None, connectionMetaDict=None, variableMetaList=None):
        """
        Creates a 'snapshot' dictionary from the current DAG.
        """
        nodes = list()
        for dagNode in self.nodes():
            nodes.append({"NAME":copy.deepcopy(dagNode.name),
                          "TYPE":type(dagNode).__name__,
                          "UUID":str(dagNode.uuid),
                          "INPUTS":[{"NAME":copy.deepcopy(x.name), "VALUE":copy.deepcopy(x.value), "RANGE":copy.deepcopy(x.seqRange)} for x in dagNode.inputs()],
                          "OUTPUTS":[{"NAME":copy.deepcopy(x.name), "VALUE":copy.deepcopy(x.value), "RANGE":copy.deepcopy(x.seqRange)} for x in dagNode.outputs()],
                          "ATTRIBUTES":[{"NAME":copy.deepcopy(x.name), "VALUE":copy.deepcopy(x.value), "RANGE":copy.deepcopy(x.seqRange)} for x in dagNode.attributes()] })
        
        edges = list()
        for connection in sorted(self.network.edges()):
            edges.append({"FROM":str(connection[1].uuid),
                          "TO":str(connection[0].uuid)})
        
        groups = list()
        for key in self.nodeGroupDict:
            groups.append({"NAME":copy.deepcopy(key),
                           "NODES":[str(x.uuid) for x in self.nodeGroupDict[key]]})
        
        snapshotDict = {"CONNECTION_META":connectionMetaDict,
                        "EDGES":edges,
                        "NODES":nodes,
                        "GROUPS":groups,
                        "NODE_META":nodeMetaDict,
                        "VARIABLE_SUBSTITIONS":variableMetaList}
        return snapshotDict
    
    
    def restoreSnapshot(self, snapshotDict):
        """
        Transfers the given JSON snapshot into the current dict.
        """
        # Clear out the existing DAG
        self.network.clear()
        self.nodeGroupDict.clear()
        
        # Loads of nodes
        for n in snapshotDict["NODES"]:
            nodeType = n["TYPE"]
            newNode = util.classTypeNamedFromModule(nodeType, 'node')
            newNode.name = n["NAME"]
            newNode.uuid = uuid.UUID(n['UUID'])
            for i in n["INPUTS"]:
                newNode.setInputValue(i["NAME"], i["VALUE"])
                newNode.setInputRange(i["NAME"], i["RANGE"])
            for o in n["OUTPUTS"]:
                for s in o["VALUE"]:
                    newNode.setOutputValue(o["NAME"], s, o["VALUE"][s])
                    if o["RANGE"]:
                        newNode.setOutputRange(o["NAME"], (o["RANGE"][0], o["RANGE"][1]))
            for a in n["ATTRIBUTES"]:
                newNode.set_attribute_value(a["NAME"], a["VALUE"])
                newNode.set_attribute_range(a["NAME"], a["RANGE"])
            self.add_node(newNode)
            
        # Edge loads
        for e in snapshotDict["EDGES"]:
            fromNode = self.node(nUUID=uuid.UUID(e["FROM"]))
            toNode = self.node(nUUID=uuid.UUID(e["TO"]))
            self.connect_nodes(fromNode, toNode)
        
        # Group loads
        for g in snapshotDict["GROUPS"]:
            self.nodeGroupDict[g["NAME"]] = set([self.node(nUUID=uuid.UUID(ns)) for ns in g["NODES"]])
