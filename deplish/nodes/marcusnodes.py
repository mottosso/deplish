import depends_node
import depends_data_packet


class DagNodeDir(depends_node.DagNode):
    """Implementation of the Windows `dir` command"""

    def _defineInputs(self):
        return []

    def _defineOutputs(self):
        return [depends_node.DagNodeOutput('File',
                depends_data_packet.DataPacketTextFile)]

    def _defineAttributes(self):
        docPath = ("A path to do a windows 'cmd' command on.")
        return [depends_node.DagNodeAttribute('listWindowsPath',
                "", docString=docPath)]

    def executeList(self, dataPacketDict, splitOperations=False):
        appList = list()

        outputTextFile = self.outputFramespec('File', 'filename')
        appList.extend(['dir'])
        appList.extend(['>', outputTextFile.filename])
        return appList
