import node
import data_packet


class DagNodeDir(node.DagNode):
    """Implementation of the Windows `dir` command"""

    def _defineInputs(self):
        return []

    def _defineOutputs(self):
        return [node.DagNodeOutput('File',
                data_packet.DataPacketTextFile)]

    def _defineAttributes(self):
        docPath = ("A path to do a windows 'cmd' command on.")
        return [node.DagNodeAttribute('listWindowsPath',
                "", docString=docPath)]

    def executeList(self, dataPacketDict, splitOperations=False):
        appList = list()

        outputTextFile = self.outputFramespec('File', 'filename')
        appList.extend(['dir'])
        appList.extend(['>', outputTextFile.filename])
        return appList
